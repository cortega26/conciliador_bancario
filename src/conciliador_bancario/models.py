from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MODELO_INTERNO_VERSION = "2"


class OrigenDato(str, Enum):
    xml = "xml"
    csv = "csv"
    xlsx = "xlsx"
    pdf_texto = "pdf_texto"
    pdf_ocr = "pdf_ocr"
    manual = "manual"


class NivelConfianza(str, Enum):
    alta = "alta"
    media = "media"
    baja = "baja"


class CBModel(BaseModel):
    # Forzamos schemas estables y evitamos que se cuelen campos inesperados.
    model_config = ConfigDict(extra="forbid", frozen=True)


class MetadataConfianza(CBModel):
    score: float = Field(ge=0.0, le=1.0)
    nivel: NivelConfianza
    origen: OrigenDato
    notas: str | None = None


class CampoConConfianza(CBModel):
    valor: Any
    confianza: MetadataConfianza


Moneda = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]

# Id externo de movimientos esperados: proviene del archivo del cliente y viaja
# hasta el reporte XLSX, donde un valor que empieza con = + - @ se convierte en
# celda de formula viva. Se rechaza en la frontera en vez de depender de que el
# renderizado lo sanee. Sin lookahead: pydantic compila `pattern` con el motor
# de Rust, que no soporta aserciones de antecipacion.
# ids reales (EXP-001, FAC-1001) no empiezan por ninguno de esos signos.
IdExterno = Annotated[str, Field(pattern=r"^[^=+\-@\x00-\x1f\x7f][^\x00-\x1f\x7f]*$")]


class TransaccionBancaria(CBModel):
    id: str = Field(min_length=1)
    cuenta_mask: str | None = None
    banco: str | None = None
    bloquea_autoconcilia: bool = False
    motivo_bloqueo_autoconcilia: str | None = None
    fecha_operacion: CampoConConfianza
    fecha_contable: CampoConConfianza | None = None
    monto: CampoConConfianza
    moneda: Moneda = "CLP"
    # True cuando `moneda` no vino del archivo y se relleno con
    # `cfg.moneda_default`. El motor compara divisas (H14), pero esa comparacion
    # solo vale si las dos etiquetas son reales: un extracto en USD sin columna de
    # moneda y un libro en CLP salen ambos marcados CLP y se concilian con exit 0
    # sin ninguna señal. El flag existe para que el motor pueda decirlo en voz
    # alta, y el adapter es el unico que sabe si la columna venía o no: el core
    # no debe conocer nombres de columnas.
    moneda_asumida: bool = False
    descripcion: CampoConConfianza
    referencia: CampoConConfianza | None = None
    archivo_origen: str = Field(min_length=1)
    origen: OrigenDato
    fila_origen: int | None = None

    @model_validator(mode="after")
    def _validar_bloqueo(self) -> TransaccionBancaria:
        if self.bloquea_autoconcilia and not (self.motivo_bloqueo_autoconcilia or "").strip():
            raise ValueError("motivo_bloqueo_autoconcilia requerido si bloquea_autoconcilia=True")
        if not isinstance(self.fecha_operacion.valor, date):
            raise ValueError("fecha_operacion.valor debe ser date")
        if (
            self.fecha_contable is not None
            and self.fecha_contable.valor is not None
            and not isinstance(self.fecha_contable.valor, date)
        ):
            raise ValueError("fecha_contable.valor debe ser date")
        if not isinstance(self.monto.valor, Decimal):
            raise ValueError("monto.valor debe ser Decimal")
        if not isinstance(self.descripcion.valor, str):
            raise ValueError("descripcion.valor debe ser str")
        if (
            self.referencia is not None
            and self.referencia.valor is not None
            and not isinstance(self.referencia.valor, str)
        ):
            raise ValueError("referencia.valor debe ser str")
        return self


class MovimientoEsperado(CBModel):
    id: IdExterno = Field(min_length=1)
    fecha: CampoConConfianza
    monto: CampoConConfianza
    moneda: Moneda = "CLP"
    # True cuando `moneda` no vino del archivo y se relleno con
    # `cfg.moneda_default`. El motor compara divisas (H14), pero esa comparacion
    # solo vale si las dos etiquetas son reales: un extracto en USD sin columna de
    # moneda y un libro en CLP salen ambos marcados CLP y se concilian con exit 0
    # sin ninguna señal. El flag existe para que el motor pueda decirlo en voz
    # alta, y el adapter es el unico que sabe si la columna venía o no: el core
    # no debe conocer nombres de columnas.
    moneda_asumida: bool = False
    descripcion: CampoConConfianza
    referencia: CampoConConfianza | None = None
    tercero: CampoConConfianza | None = None

    @model_validator(mode="after")
    def _validar_tipos(self) -> MovimientoEsperado:
        if not isinstance(self.fecha.valor, date):
            raise ValueError("fecha.valor debe ser date")
        if not isinstance(self.monto.valor, Decimal):
            raise ValueError("monto.valor debe ser Decimal")
        if not isinstance(self.descripcion.valor, str):
            raise ValueError("descripcion.valor debe ser str")
        if (
            self.referencia is not None
            and self.referencia.valor is not None
            and not isinstance(self.referencia.valor, str)
        ):
            raise ValueError("referencia.valor debe ser str")
        if (
            self.tercero is not None
            and self.tercero.valor is not None
            and not isinstance(self.tercero.valor, str)
        ):
            raise ValueError("tercero.valor debe ser str")
        return self


class EstadoMatch(str, Enum):
    conciliado = "conciliado"
    sugerido = "sugerido"
    pendiente = "pendiente"
    rechazado = "rechazado"


class Match(CBModel):
    id: str = Field(min_length=1)
    estado: EstadoMatch
    score: float = Field(ge=0.0, le=1.0)
    regla: str = Field(min_length=1)
    explicacion: str = Field(min_length=1)
    transacciones_bancarias: list[str] = Field(min_length=1)
    movimientos_esperados: list[str] = Field(min_length=1)
    bloqueado_por_confianza: bool = False


class SeveridadHallazgo(str, Enum):
    info = "info"
    advertencia = "advertencia"
    critica = "critica"


class Hallazgo(CBModel):
    id: str = Field(min_length=1)
    severidad: SeveridadHallazgo
    tipo: str = Field(min_length=1)
    mensaje: str = Field(min_length=1)
    entidad: Literal["banco", "esperado", "match", "sistema"]
    entidad_id: str | None = None
    detalles: dict[str, Any] = Field(default_factory=dict)


class LimitesIngesta(CBModel):
    """
    Limites defensivos ante inputs hostiles o sobredimensionados.

    Politica:
    - Default: fail-closed con limites conservadores.
    - Override: via config (`limites_ingesta`) o flags CLI (`--max-*`).
    """

    max_input_bytes: int = Field(default=25_000_000, ge=1)  # ~25 MB
    # Un XLSX es un ZIP: `max_input_bytes` ve el archivo **comprimido**, que un
    # archivo con ratio de compresion alto puede reducir arbitrariamente. Sin
    # este limite, 399 KB se descomprimen a 400 MB y el proceso llega a 1.2 GB de
    # RSS antes de que ningun codigo del repo pueda mirarlo: el conteo de
    # `max_tabular_cells` ocurre despues de descomprimir, cuando el dano ya esta
    # hecho.
    #
    # El default es holgado a proposito (200 MB para 25 MB comprimidos): un
    # XLSX real de un banco tiene mucho aire, y un limite demasiado ajustado
    # rechazaria archivos que funcionan.
    max_xlsx_uncompressed_bytes: int = Field(default=200_000_000, ge=1)
    max_tabular_rows: int = Field(default=200_000, ge=1)
    max_tabular_cells: int = Field(default=5_000_000, ge=1)
    max_pdf_pages: int = Field(default=200, ge=1)
    max_pdf_text_chars: int = Field(default=5_000_000, ge=1)
    max_xml_movimientos: int = Field(default=200_000, ge=1)


class ConfiguracionCliente(CBModel):
    cliente: str = Field(min_length=1)
    rut_mask: str | None = None
    ventana_dias_monto_fecha: int = Field(default=3, ge=0)
    # Ventana de la regla ref_exacta (referencia + monto exactos). Es una senal
    # mas fuerte que monto+fecha, asi que por defecto es mas tolerante: un
    # desfase de liquidacion de una semana es normal, una referencia reciclada de
    # otro periodo no lo es.
    ventana_dias_ref_exacta: int = Field(default=7, ge=0)
    umbral_autoconcilia: float = Field(default=0.85, ge=0.0, le=1.0)
    umbral_confianza_campos: float = Field(default=0.80, ge=0.0, le=1.0)
    permitir_ocr: bool = False
    mask_por_defecto: bool = True
    moneda_default: Moneda = "CLP"
    limites_ingesta: LimitesIngesta = Field(default_factory=LimitesIngesta)


@dataclass(frozen=True)
class ResultadoConciliacion:
    transacciones_bancarias: list[TransaccionBancaria]
    movimientos_esperados: list[MovimientoEsperado]
    matches: list[Match]
    hallazgos: list[Hallazgo]
    run_id: str
