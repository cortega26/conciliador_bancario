from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.ingestion.pdf_ocr_adapter import cargar_transacciones_pdf_ocr
from conciliador_bancario.models import ConfiguracionCliente, MovimientoEsperado


def test_pdf_ocr_fail_closed_si_no_hay_dependencias(tmp_path: Path) -> None:
    has_pdf2image = importlib.util.find_spec("pdf2image") is not None
    has_pytesseract = importlib.util.find_spec("pytesseract") is not None
    if has_pdf2image and has_pytesseract:
        pytest.skip("Dependencias OCR instaladas; este test valida fail-closed cuando no estan.")

    pdf = _pdf_valido(tmp_path / "cartola.pdf")
    cfg = ConfiguracionCliente(cliente="X", permitir_ocr=True)
    with pytest.raises(ErrorIngestion):
        cargar_transacciones_pdf_ocr(pdf, cfg=cfg, audit=NullAuditWriter())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Contrato con las librerias OCR
#
# El golden con stubs ya cubre la logica de extraccion, pero el stub era
# permisivo: ignoraba los argumentos, asi que nada fijaba COMO llamamos a las
# librerias. Un cambio en nuestra llamada (o un breaking en la libreria) pasaba
# inadvertido. Estos tests fijan nuestro lado de la costura.
# ---------------------------------------------------------------------------


class _Recorder:
    """Falsificador que recuerda como lo invocaron, en vez de ignorarlo."""

    def __init__(self) -> None:
        self.convert_args: list[tuple[object, ...]] = []
        self.convert_kwargs: list[dict[str, object]] = []
        self.ocr_args: list[object] = []
        self.ocr_kwargs: list[dict[str, object]] = []


def _pdf_valido(path: Path, paginas: int = 1) -> Path:
    """PDF real y minimo: el adaptador abre el archivo con PdfReader antes de
    convertir, asi que un PDF de mentira cortaria antes de llegar a la costura."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(paginas):
        writer.add_blank_page(width=200, height=200)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def _inyectar_stubs(monkeypatch: pytest.MonkeyPatch, rec: _Recorder) -> None:
    import sys
    import types

    mod_pdf2image = types.ModuleType("pdf2image")

    def convert_from_path(*args: object, **kwargs: object) -> list[object]:
        rec.convert_args.append(args)
        rec.convert_kwargs.append(kwargs)
        return [object(), object()]  # dos paginas: tambien ejercita el limite

    mod_pdf2image.convert_from_path = convert_from_path
    monkeypatch.setitem(sys.modules, "pdf2image", mod_pdf2image)

    mod_pyt = types.ModuleType("pytesseract")

    def image_to_string(image: object, **kwargs: object) -> str:
        rec.ocr_args.append(image)
        rec.ocr_kwargs.append(kwargs)
        return "05/01/2026 Pago proveedor 150000\n"

    mod_pyt.image_to_string = image_to_string
    monkeypatch.setitem(sys.modules, "pytesseract", mod_pyt)


def test_ocr_usa_lang_spa_en_todas_las_paginas(tmp_path: Path, monkeypatch) -> None:
    """
    Fijamos el idioma con el que se llama a tesseract.

    `lang="spa"` esta hardcodeado a proposito (el proyecto es Chile-first), pero
    ningun test lo verificaba: el stub aceptaba cualquier valor. Si alguien lo
    cambia o la libreria deja de aceptarlo, aqui se ve.
    """
    rec = _Recorder()
    _inyectar_stubs(monkeypatch, rec)

    pdf = _pdf_valido(tmp_path / "cartola.pdf", paginas=2)
    cargar_transacciones_pdf_ocr(  # type: ignore[arg-type]
        pdf, cfg=ConfiguracionCliente(cliente="X", permitir_ocr=True), audit=NullAuditWriter()
    )

    assert len(rec.ocr_kwargs) == 2, "se esperaba una llamada a OCR por pagina"
    assert all(kw.get("lang") == "spa" for kw in rec.ocr_kwargs), rec.ocr_kwargs


def test_ocr_convierte_el_pdf_indicado(tmp_path: Path, monkeypatch) -> None:
    """La conversion recibe la ruta del PDF que se le pidio, no otra cosa."""
    rec = _Recorder()
    _inyectar_stubs(monkeypatch, rec)

    pdf = _pdf_valido(tmp_path / "cartola.pdf")
    cargar_transacciones_pdf_ocr(  # type: ignore[arg-type]
        pdf, cfg=ConfiguracionCliente(cliente="X", permitir_ocr=True), audit=NullAuditWriter()
    )

    assert len(rec.convert_args) == 1
    (ruta,) = rec.convert_args[0]
    assert str(ruta) == str(pdf)


def test_ocr_bloquea_autoconciliacion_aunque_haya_match(tmp_path: Path, monkeypatch) -> None:
    """
    Politica OCR: nunca autoconcilia, ni siquiera con monto y fecha identicos.

    Es el invariante central del modo OCR. El golden lo cubre via run.json; aqui
    se afirma sobre el modelo, que es donde el motor lo lee.
    """
    rec = _Recorder()
    _inyectar_stubs(monkeypatch, rec)

    pdf = _pdf_valido(tmp_path / "cartola.pdf")
    cfg = ConfiguracionCliente(cliente="X", permitir_ocr=True, umbral_autoconcilia=0.0)
    txs = cargar_transacciones_pdf_ocr(  # type: ignore[arg-type]
        pdf, cfg=cfg, audit=NullAuditWriter()
    )

    assert txs, "el stub deberia producir al menos una transaccion"
    for tx in txs:
        assert tx.bloquea_autoconcilia is True
        assert tx.motivo_bloqueo_autoconcilia
        # Confianza baja: por debajo del umbral de campos, aunque el umbral de
        # autoconciliacion se haya puesto a 0 para aislar el efecto.
        assert float(tx.monto.confianza.score) < cfg.umbral_confianza_campos


# ---------------------------------------------------------------------------
# Integracion real (tesseract + poppler)
#
# Los tests de arriba fijan NUESTRO lado de la costura con dobles. Este fija la
# costura misma: convierte un PDF de verdad con pdf2image, lo lee con
# tesseract, y comprueba que la politica OCR se sostiene. Es lo que permite
# validar un bump mayor de Pillow en vez de asumirlo.
#
# Se asserta sobre INVARIANTES, nunca sobre el texto exacto: la salida de OCR
# depende de la version de tesseract y de sus datos de idioma, asi que un
# assert de igualdad seria un test fragil que falla por el motivo equivocado.
# ---------------------------------------------------------------------------


def _binarios_ocr() -> bool:
    import shutil

    return bool(shutil.which("tesseract")) and bool(shutil.which("pdftoppm"))


def _extras_ocr() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in ("pdf2image", "pytesseract", "PIL"))


_OCR_INTEGRACION = pytest.mark.skipif(
    not (_extras_ocr() and _binarios_ocr()),
    reason="Requiere extras [pdf_ocr] y binarios de sistema tesseract + poppler-utils.",
)


def _pdf_escaneado(path: Path, lineas: list[str]) -> Path:
    """Construye un PDF con texto dibujado como imagen: eso es un escaneo."""
    from PIL import Image, ImageDraw, ImageFont

    fuentes = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/Library/Fonts/Menlo.ttc",
    )
    font = None
    for ruta in fuentes:
        try:
            font = ImageFont.truetype(ruta, 56)
            break
        except OSError:
            continue
    if font is None:
        try:
            font = ImageFont.load_default(size=56)
        except TypeError:  # Pillow antiguo sin `size`
            font = ImageFont.load_default()

    img = Image.new("L", (1700, 700), color=255)
    draw = ImageDraw.Draw(img)
    for i, linea in enumerate(lineas):
        draw.text((60, 60 + i * 140), linea, fill=0, font=font)
    img.save(path, "PDF", resolution=200.0)
    return path


@_OCR_INTEGRACION
def test_ocr_real_sobre_pdf_escaneado_respeta_la_politica(tmp_path: Path) -> None:
    """PDF -> imagen -> texto real, con las librerias reales instaladas."""
    pdf = _pdf_escaneado(
        tmp_path / "cartola.pdf",
        [
            "05-01-2026  PAGO PROVEEDOR ACME  150.000",
            "06-01-2026  PAGO NOMINA ENERO  -250000",
        ],
    )
    cfg = ConfiguracionCliente(cliente="X", permitir_ocr=True)
    txs = cargar_transacciones_pdf_ocr(  # type: ignore[arg-type]
        pdf, cfg=cfg, audit=NullAuditWriter()
    )

    assert txs, "OCR real no extrajo transacciones del PDF escaneado"
    for tx in txs:
        assert tx.origen.value == "pdf_ocr"
        # La politica central del modo OCR: revision humana obligatoria.
        assert tx.bloquea_autoconcilia is True
        assert tx.motivo_bloqueo_autoconcilia
        # Confianza baja por diseno, para que ningun match pueda autoconciliar.
        assert float(tx.fecha_operacion.confianza.score) < cfg.umbral_confianza_campos
        assert float(tx.monto.confianza.score) < cfg.umbral_confianza_campos
        assert tx.fecha_operacion.confianza.nivel.value == "baja"


@_OCR_INTEGRACION
def test_ocr_real_no_puede_autoconciliar_aunque_haya_match(tmp_path: Path) -> None:
    """
    Con monto y fecha identicos a un esperado, OCR igual no concilia solo.

    Se sube el umbral de autoconciliacion a 0 y aun asi el match debe quedar
    pendiente: es la garantia de que la confianza manda sobre el score.
    """
    pdf = _pdf_escaneado(tmp_path / "cartola.pdf", ["05-01-2026  PAGO PROVEEDOR  150000"])
    cfg = ConfiguracionCliente(
        cliente="X", permitir_ocr=True, umbral_autoconcilia=0.0, umbral_confianza_campos=0.0
    )
    txs = cargar_transacciones_pdf_ocr(  # type: ignore[arg-type]
        pdf, cfg=cfg, audit=NullAuditWriter()
    )
    assert txs
    for tx in txs:
        assert tx.bloquea_autoconcilia is True

    from conciliador_bancario.matching.engine import conciliar

    esperado = MovimientoEsperado(
        id="EXP-1",
        fecha=txs[0].fecha_operacion,
        monto=txs[0].monto,
        moneda="CLP",
        descripcion=txs[0].descripcion,
    )
    res = conciliar(
        cfg=cfg,
        transacciones=txs,
        esperados=[esperado],
        audit=NullAuditWriter(),  # type: ignore[arg-type]
        run_id="r",
    )
    assert all(m.estado.value != "conciliado" for m in res.matches), [
        (m.regla, m.estado.value, m.score) for m in res.matches
    ]
