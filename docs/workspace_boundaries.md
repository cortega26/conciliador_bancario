# Limites de Workspace: Core (OSS) vs Premium (Privado)

Este documento define reglas operacionales para trabajar en un **VS Code Workspace multi-root** con dos repos separados:

- **Core (OSS):** este repo (`conciliador_bancario`)
- **Premium (privado):** repo separado en otra carpeta del mismo workspace

Objetivo: **cero acoplamientos accidentales**, **cero filtracion** y **cero regresiones**.

## Principios

- ✅ Direccion de dependencias: **Premium puede depender del Core**; el Core **nunca** depende de Premium.
- ✅ Fail-closed: ante duda, el Core **no concilia** y genera hallazgos/auditoria.
- ✅ Determinismo y auditabilidad: decisiones trazables, artefactos reproducibles.
- ❌ No monorepo: los repos se mantienen separados.

Motivo: reduce riesgo legal (licencias), tecnico (regresiones) y operacional (filtracion).
Riesgo si se viola: dependencia circular, leaks de features premium, builds no reproducibles, y deuda tecnica no auditable.

## Reglas (Core)

- ✅ El Core puede definir **contratos/tipos** para extensiones (ej: `src/conciliador_core/premium_contracts/`).
- ✅ El Core genera artefactos tecnicos estables (ej: `run.json`, `audit.jsonl`, `reporte_conciliacion.xlsx`) para integraciones externas.
- ❌ El Core no debe importar ni referenciar codigo/paquetes premium (directo o indirecto).
- ❌ El Core no agrega dependencias que existan solo por premium.
- ❌ El Core no implementa features orientadas a ahorro de tiempo humano recurrente (regla comercial).

Motivo: mantener el Core publicable/OSS, con responsabilidades acotadas y politicas estrictas.
Riesgo si se viola: contaminación de licencias, “feature creep”, y comportamiento no gobernable.

## Contratos Core <-> Premium (estaticos y versionables)

- ✅ Contrato de plugins (tipos): `conciliador_core.premium_contracts` (Protocol/Interfaces, sin logica).
- ✅ Contrato por archivos: Premium puede leer los artefactos de salida del Core (`run.json`, `audit.jsonl`, XLSX tecnico).
- ✅ Contrato por CLI: Premium puede invocar el CLI del Core como “black box” si lo necesita.

Motivo: un contrato explicito reduce imports a internals y permite compatibilidad versionada.
Riesgo si se viola: premium “raspa” internals y cada refactor del Core rompe premium.

## Guardrails automaticos (Core)

- ✅ Boundary check: `python tools/check_boundaries.py`
- ✅ Secret scan (minimo): `python tools/secret_scan.py`
- ✅ Gate por tests: `pytest` ejecuta ambos checks.

Motivo: prevenir errores humanos, especialmente en workspace multi-root.
Riesgo si se viola: referencias cruzadas pasan a main sin ser detectadas.

## CI (si aplica)

- ✅ Minimo viable: un job que ejecute `python -m pytest` en el root del repo.
- ✅ Regla: el gate debe correr en PR y en push a main.

Motivo: que los guardrails no dependan del entorno local.
Riesgo si se viola: un PR puede saltarse checks por error humano.

## Ejemplos

Permitido:

- ✅ Agregar un `Protocol` o dataclass de contrato en `src/conciliador_core/premium_contracts/`.
- ✅ Documentar en `walkthrough.md` hooks o futuras extensiones como **stubs**.

Prohibido:

- ❌ Agregar imports/strings que apunten al repo/paquete premium.
- ❌ Mover logica “productividad” al Core (debe quedar fuera o como interfaz sin implementacion).

## Checklist de PR (Core)

- [ ] Corri `pytest`.
- [ ] Corri `python tools/check_boundaries.py`.
- [ ] Corri `python tools/secret_scan.py`.
- [ ] No se agregaron dependencias “solo premium”.
- [ ] Cambios con impacto en decisiones mantienen auditoria/explicaciones y politicas fail-closed.
