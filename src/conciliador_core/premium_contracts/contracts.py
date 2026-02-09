from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

"""
CAPA PREMIUM (PAGO) - CONTRATOS (SIN IMPLEMENTACION)

Este modulo define interfaces para features premium.

Reglas:
- Disenado, no implementado.
- CERO logica real (sin heuristicas, sin reglas por banco).
- El core puede usar estos contratos como tipos, pero no depende de plugins.
"""


@dataclass(frozen=True)
class PremiumPluginInfo:
    name: str
    version: str
    vendor: str | None = None
    min_core_version: str | None = None
    metadata: Mapping[str, Any] | None = None


@runtime_checkable
class PremiumPlugin(Protocol):
    """
    Plugin premium principal (entrypoint).

    Implementaciones premium reales viven fuera del repo publico.
    """

    def plugin_info(self) -> PremiumPluginInfo:
        """Devuelve metadatos del plugin (sin side-effects)."""

    def rule_pack(self) -> PremiumRulePack:
        """Devuelve un pack de capacidades premium (reglas/reportes/batch)."""


@runtime_checkable
class PremiumRulePack(Protocol):
    """
    Agrega capacidades premium por categorias.

    Cada metodo puede devolver None si la capacidad no esta disponible en el plugin.
    """

    def bank_rule_provider(self) -> BankRuleProvider | None:
        """Reglas especificas por banco (premium)."""

    def executive_report_renderer(self) -> ExecutiveReportRenderer | None:
        """Reportes ejecutivos listos para cliente (premium)."""

    def operational_batch_runner(self) -> OperationalBatchRunner | None:
        """Batch operativo multi-cliente (premium)."""


@runtime_checkable
class BankRuleProvider(Protocol):
    """
    Provee reglas/heuristicas especificas por banco (premium).

    Importante:
    - El core NO debe implementar reglas por banco.
    - El core puede llamar estas APIs solo si un plugin premium esta activado.
    """

    def supported_banks(self) -> set[str]:
        """Lista de bancos soportados por este pack (identificadores internos del plugin)."""

    def apply_bank_specific_normalization(
        self, *, bank_id: str, raw: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """
        Normalizacion/mapeo especifico por banco.

        Disenado para ahorrar tiempo humano (premium). No implementado en el core.
        """

    def propose_additional_matching_hints(
        self, *, bank_id: str, context: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """
        Entrega "hints" para matching (ej: reglas por banco, claves especiales).

        Debe ser opcional y no determinante por si solo.
        """


@runtime_checkable
class ExecutiveReportRenderer(Protocol):
    """
    Renderizador de reportes ejecutivos (premium).

    El core solo genera reportes tecnicos/auditables.
    """

    def render(
        self, *, run_dir: Path, output_dir: Path, options: Mapping[str, Any] | None = None
    ) -> list[Path]:
        """
        Genera artefactos (PDF/HTML/etc) orientados a presentacion ejecutiva.

        Nota: no implementado en el core.
        """


@runtime_checkable
class OperationalBatchRunner(Protocol):
    """
    Ejecutor de batch operativo multi-cliente (premium).

    Por definicion, esto ahorra tiempo humano recurrente y puede introducir riesgos
    si se automatiza sin controles; por eso es premium y fuera del core.
    """

    def run_batch(
        self, *, manifest_path: Path, output_dir: Path, options: Mapping[str, Any] | None = None
    ) -> None:
        """Ejecuta una corrida batch en base a un manifiesto (disenado, no implementado)."""
