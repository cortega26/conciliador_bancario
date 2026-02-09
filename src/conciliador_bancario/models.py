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
    id: str = Field(min_length=1)
    fecha: CampoConConfianza
    monto: CampoConConfianza
    moneda: Moneda = "CLP"
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
    max_tabular_rows: int = Field(default=200_000, ge=1)
    max_tabular_cells: int = Field(default=5_000_000, ge=1)
    max_pdf_pages: int = Field(default=200, ge=1)
    max_pdf_text_chars: int = Field(default=5_000_000, ge=1)
    max_xml_movimientos: int = Field(default=200_000, ge=1)


class ConfiguracionCliente(CBModel):
    cliente: str = Field(min_length=1)
    rut_mask: str | None = None
    ventana_dias_monto_fecha: int = Field(default=3, ge=0)
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
