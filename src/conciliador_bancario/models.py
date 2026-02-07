from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


MODELO_INTERNO_VERSION = "1"


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


class MetadataConfianza(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    nivel: NivelConfianza
    origen: OrigenDato
    notas: str | None = None


class CampoConConfianza(BaseModel):
    valor: Any
    confianza: MetadataConfianza


class TransaccionBancaria(BaseModel):
    id: str
    cuenta_mask: str | None = None
    banco: str | None = None
    bloquea_autoconcilia: bool = False
    motivo_bloqueo_autoconcilia: str | None = None
    fecha_operacion: CampoConConfianza
    fecha_contable: CampoConConfianza | None = None
    monto: CampoConConfianza
    moneda: str = "CLP"
    descripcion: CampoConConfianza
    referencia: CampoConConfianza | None = None
    archivo_origen: str
    origen: OrigenDato
    fila_origen: int | None = None


class MovimientoEsperado(BaseModel):
    id: str
    fecha: CampoConConfianza
    monto: CampoConConfianza
    moneda: str = "CLP"
    descripcion: CampoConConfianza
    referencia: CampoConConfianza | None = None
    tercero: CampoConConfianza | None = None


class EstadoMatch(str, Enum):
    conciliado = "conciliado"
    sugerido = "sugerido"
    pendiente = "pendiente"
    rechazado = "rechazado"


class Match(BaseModel):
    id: str
    estado: EstadoMatch
    score: float = Field(ge=0.0, le=1.0)
    regla: str
    explicacion: str
    transacciones_bancarias: list[str]
    movimientos_esperados: list[str]
    bloqueado_por_confianza: bool = False


class SeveridadHallazgo(str, Enum):
    info = "info"
    advertencia = "advertencia"
    critica = "critica"


class Hallazgo(BaseModel):
    id: str
    severidad: SeveridadHallazgo
    tipo: str
    mensaje: str
    entidad: Literal["banco", "esperado", "match", "sistema"]
    entidad_id: str | None = None
    detalles: dict[str, Any] = Field(default_factory=dict)


class ConfiguracionCliente(BaseModel):
    cliente: str
    rut_mask: str | None = None
    ventana_dias_monto_fecha: int = 3
    umbral_autoconcilia: float = 0.85
    umbral_confianza_campos: float = 0.80
    permitir_ocr: bool = False
    mask_por_defecto: bool = True
    moneda_default: str = "CLP"


@dataclass(frozen=True)
class ResultadoConciliacion:
    transacciones_bancarias: list[TransaccionBancaria]
    movimientos_esperados: list[MovimientoEsperado]
    matches: list[Match]
    hallazgos: list[Hallazgo]
    run_id: str
