from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion, error_de_fila
from conciliador_bancario.ingestion.limits import LimitHints, enforce_counter, enforce_file_size
from conciliador_bancario.ingestion.pdf_reader import abrir_pdf
from conciliador_bancario.models import (
    CampoConConfianza,
    ConfiguracionCliente,
    MetadataConfianza,
    NivelConfianza,
    OrigenDato,
    TransaccionBancaria,
)
from conciliador_bancario.utils.hashing import sha256_json_estable
from conciliador_bancario.utils.parsing import (
    ErrorParseo,
    normalizar_texto,
    parse_fecha_chile,
    parse_monto_clp,
)


def _campo(valor: Any, *, notas: str | None = None, degrade: float = 0.0) -> CampoConConfianza:
    base = 0.30
    score = max(0.0, min(1.0, base - degrade))
    return CampoConConfianza(
        valor=valor,
        confianza=MetadataConfianza(
            score=score, nivel=NivelConfianza.baja, origen=OrigenDato.pdf_ocr, notas=notas
        ),
    )


def _id_tx(path: Path, idx: int, data_norm: dict[str, Any]) -> str:
    return "TX-" + sha256_json_estable({"file": path.name, "idx": idx, "data": data_norm})[:12]


def _parece_monto(texto: str) -> bool:
    """Si el token **parece** un monto, aunque no se pueda parsear.

    ## Por que existe

    El bucle de abajo busca el ultimo token que se pueda parsear. Con el
    parser endurecido (que rechaza centavos, notacion cientrica y hex), un
    token como `1.234,56` pasa a ser irreconocible, y el bucle seguia hacia
    atras y devolveria **otro** token: `05/01/2026 Pago 1.234,56` terminaria
    leyendo 2026 como monto.

    Eso es peor que no encontrar monto: es encontrar el numero equivocado con
    exit 0. Un token que tiene forma de monto pero no se puede leer hace que
    la linea se descarte, en vez de que se lea mal.

    ## Por que no basta "solo digitos y separadores"

    Un intento de monto puede traer letras: `1e5` (notacion cientrica) y
    `0x10` (hexadecimalo) los rechaza el parser, pero `_parece_monto` los
    declaraba "no son un monto" y el bucle hacia backtracking igual. Lo
    Verificado revirtiendo la guarda: el test parametrico falla para
    esos dos casos.

    La forma se decide por la estructura: tiene que haber **al menos un
    digito**, y todo lo demas tiene que ser digito, separador de miles, signo
    o moneda. `Pago` no entra porque no tiene digitos; `1e5` entra porque
    tiene un digito y una letra, que es justamente la forma sospechosa.
    """
    limpio = re.sub(r"[^\S]|USD|EUR|CLP|COP|UF|\$|€|£", "", texto)
    if not any(c.isdigit() for c in limpio):
        return False
    return all(c in "0123456789.,()-+eExX" for c in limpio)


def _monto_de_linea(tokens: list[str]) -> Decimal | None:
    """El monto de una linea de OCR, o None si no hay uno legible.

    Se busca desde el final, que es donde el OCR suele dejar el monto.

    ## La guarda

    Si el ultimo token tiene forma de monto pero no se puede parsear, la linea se
    descarta. Sin esa guarda, el bucle seguia hacia atras y devolvia **otro**
    token: `05/01/2026 Pago 1.234,56` terminaba leyendo 2026 como monto.

    Devolver el numero equivocado es peor que no devolver nada: es un monto
    inventado con exit 0, en un camino donde la politica es que OCR nunca
    autoconcilia pero si exige no inventar.

    Vive a nivel de modulo y no anidada para que sea testeable: una copia en el
    test puede quedar vieja sin que nada lo note.
    """
    for tok in reversed(tokens):
        try:
            return parse_monto_clp(tok)
        except ErrorParseo:
            pass
        if _parece_monto(tok):
            return None
    return None


def cargar_transacciones_pdf_ocr(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> list[TransaccionBancaria]:
    """
    OCR es un fallback controlado (baja confianza).
    Si OCR no esta disponible, se falla explicitamente (fail-closed).
    """
    enforce_file_size(
        path=path,
        max_bytes=cfg.limites_ingesta.max_input_bytes,
        audit=audit,
        hints=LimitHints(cfg_path="limites_ingesta.max_input_bytes", cli_flag="--max-input-bytes"),
        label="PDF banco (OCR)",
    )

    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_path  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise ErrorIngestion(
            "OCR no disponible. Instale extras: pip install -e '.[pdf_ocr]' y dependencias del sistema (poppler)."
        ) from e

    # Limit pages before converting to images (expensive). Keep it after the deps check so
    # missing OCR deps fails with a clean error even on invalid PDFs (contract test).
    reader = abrir_pdf(path, etiqueta="PDF banco (OCR)")
    enforce_counter(
        path=path,
        audit=audit,
        name="max_pdf_pages",
        value=len(reader.pages),
        max_value=cfg.limites_ingesta.max_pdf_pages,
        hints=LimitHints(cfg_path="limites_ingesta.max_pdf_pages", cli_flag="--max-pdf-pages"),
        label="PDF banco (OCR)",
    )

    audit.write(AuditEvent("ingestion", "OCR iniciado", {"archivo": path.name}))
    images = convert_from_path(str(path))
    texto = []
    total_chars = 0
    for im in images:
        chunk = pytesseract.image_to_string(im, lang="spa")
        total_chars += len(chunk)
        enforce_counter(
            path=path,
            audit=audit,
            name="max_pdf_text_chars",
            value=total_chars,
            max_value=cfg.limites_ingesta.max_pdf_text_chars,
            hints=LimitHints(
                cfg_path="limites_ingesta.max_pdf_text_chars", cli_flag="--max-pdf-text-chars"
            ),
            label="PDF banco (OCR)",
        )
        texto.append(chunk)
    full = "\n".join(texto)

    out: list[TransaccionBancaria] = []
    idx = 0

    def _try_parse_fecha(texto: str) -> date | None:
        try:
            return parse_fecha_chile(texto)
        except ErrorParseo:
            return None

    for raw_line in full.splitlines():
        line = normalizar_texto(raw_line)
        if not line:
            continue
        parts = line.split(" ")
        if len(parts) < 2:
            continue
        fecha_txt = parts[0]
        fecha = _try_parse_fecha(fecha_txt)
        if fecha is None:
            continue
        monto = _monto_de_linea(parts)
        if monto is None:
            continue
        desc = normalizar_texto(line.replace(fecha_txt, "", 1))
        idx += 1
        data_norm = {"fecha_operacion": str(fecha), "monto": str(monto), "descripcion": desc}
        tx_id = _id_tx(path, idx, data_norm)
        with error_de_fila(idx):
            out.append(
                TransaccionBancaria(
                    id=tx_id,
                    cuenta_mask=None,
                    bloquea_autoconcilia=True,
                    motivo_bloqueo_autoconcilia="Transaccion proviene de PDF escaneado procesado por OCR: requiere revision humana.",
                    fecha_operacion=_campo(fecha, notas="OCR"),
                    fecha_contable=None,
                    monto=_campo(monto, notas="OCR"),
                    moneda=cfg.moneda_default,
                    descripcion=_campo(desc, notas="OCR", degrade=0.05),
                    referencia=None,
                    archivo_origen=path.name,
                    origen=OrigenDato.pdf_ocr,
                    fila_origen=idx,
                )
            )
    audit.write(AuditEvent("ingestion", "OCR finalizado", {"archivo": path.name, "txs": len(out)}))
    if not out:
        raise ErrorIngestion("OCR completado pero no se detectaron transacciones (heuristica).")
    return out
