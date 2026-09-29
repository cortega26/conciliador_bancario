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


def _fechas_de_linea(tokens: list[str]) -> list[date]:
    """Todas las fechas que la linea contiene, en orden.

    Una linea de cartola tiene **una** fecha. Dos o mas significan que el OCR
    fusiono dos transacciones en una, que es exactamente lo que pasa con un
    layout de dos columnas: los renglones de la izquierda y los de la derecha
    se leen intercalados en la misma linea de texto.
    """
    fechas: list[date] = []
    for tok in tokens:
        try:
            fechas.append(parse_fecha_chile(tok))
        except ErrorParseo:
            continue
    return fechas


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

    # Importacion dinamica a proposito.
    #
    # Con `import pytesseract  # type: ignore` el comentario hace falta cuando las
    # dependencias no estan y **sobra** cuando estan. Como `warn_unused_ignores`
    # esta activo, mypy falla en un caso o en el otro: con los pines de `dev`
    # (sin extras) dice que el ignore es necesario; con `.[pdf-ocr]` instalado
    # dice que sobra. No hay ningun entorno en que el gate pase, y desarrollo de
    # OCR es—justamente— trabajar con los extras puestos.
    #
    # Con `importlib` no hay import estatico que mypy pueda revisar, asi que el
    # gate dice lo mismo en los dos entornos. El fail-closed no cambia: la
    # ausencia de la dependencia sigue produciendo `ErrorIngestion`.
    import importlib

    try:
        pytesseract = importlib.import_module("pytesseract")
        convert_from_path = importlib.import_module("pdf2image").convert_from_path
    except ImportError as e:
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
    # Lineas que **parecian** una transaccion (tienen una fecha) pero no pudieron
    # leerse como una. Se cuentan y se reportan, porque descartarlas en silencio
    # hace que una lectura parcial se presente como una lectura completa.
    descartadas_fusion = 0
    descartadas_sin_monto = 0

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

        # Una linea con dos o mas fechas es la fusion de dos transacciones. El
        # monto se busca **desde el final**, asi que la fecha de una y el monto
        # de la otra se emparejan: el monto de la segunda con la fecha de la
        # primera. Se comprobo con un PDF de dos columnas, y el resultado es un
        # monto equivocado con exit 0:
        #
        #   '05/01/2026 PAGO ACME 150.000 06/01/2026 TRANSFER 1.234.500'
        #     -> fecha=2026-01-05  monto=1234500   (el real era 150.000)
        #
        # El numero equivocado es plausible, asi que ninguna validacion de rango
        # lo detecta, y la unica defensa es no construir la transaccion. La regla
        # es simple porque el dato lo permite: una transaccion tiene una fecha.
        if len(_fechas_de_linea(parts)) > 1:
            descartadas_fusion += 1
            continue

        monto = _monto_de_linea(parts)
        if monto is None:
            # Habia una fecha, o sea que la linea parecia una transaccion, pero no
            # se pudo leer el monto. Puede ser una linea que no es transaccion
            # (un encabezado, un pie de pagina) o una transaccion ilegible; en los
            # dos casos el operador tiene que saber que la linea existia.
            descartadas_sin_monto += 1
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
    audit.write(
        AuditEvent(
            "ingestion",
            "OCR finalizado",
            {
                "archivo": path.name,
                "txs": len(out),
                "lineas_descartadas_fusion": descartadas_fusion,
                "lineas_descartadas_sin_monto": descartadas_sin_monto,
            },
        )
    )
    # Una lectura parcial tiene que ser visible, no silenciosa. Si 7 de 8 lineas
    # se descartan y el operador recibe 1 transaccion con exit 0, la conclusion
    # razonable es "la cartola tiene una transaccion", que es falsa: el reporte
    # esta completo en apariencia y no lo esta.
    #
    # No se falla por esto: OCR produce basura con normalidad (encabezados, pies
    # de pagina) y rechazar por una linea ilegible seria inservible. Lo que no
    # es aceptable es que el descarte no quede en ningun lado.
    if out and (descartadas_fusion or descartadas_sin_monto):
        total = len(out) + descartadas_fusion + descartadas_sin_monto
        audit.write(
            AuditEvent(
                "hallazgo",
                "OCR leyo menos lineas de las que parecian transacciones",
                {
                    "archivo": path.name,
                    "transacciones": len(out),
                    "descartadas_fusion": descartadas_fusion,
                    "descartadas_sin_monto": descartadas_sin_monto,
                    "lineas_candidatas": total,
                    "recomendacion": (
                        "Revisar el PDF original: puede tener un layout de varias "
                        "columnas oTransactions ilegibles que no quedaron en el reporte."
                    ),
                },
            )
        )
    if not out:
        raise ErrorIngestion("OCR completado pero no se detectaron transacciones (heuristica).")
    return out
