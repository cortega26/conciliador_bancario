# Conciliador Bancario (MVP)

CLI local (Chile-first) para **conciliación bancaria** con enfoque **fail-closed**, **auditabilidad** y **salidas deterministas**.

[![CI](https://github.com/cortega26/conciliador_bancario/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/cortega26/conciliador_bancario/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Licencia](https://img.shields.io/github/license/cortega26/conciliador_bancario)

---

## Vista rápida (inputs → proceso → outputs)

```text
Entradas (por cliente)                    Proceso (core)                     Salidas (por corrida = run_dir)

  config_cliente.yaml   ┐                                                  ┌─ run.json          (resultado técnico + contrato)
  banco.csv|xlsx|xml|pdf ├─> ingestión -> normalización -> matching ->     ├─ audit.jsonl        (traza append-only, JSON Lines)
  esperados.csv|xlsx    ┘         validación estricta + auditoría          └─ reporte_conciliacion.xlsx (opcional; revisión humana)
```

Puntos no negociables:
- **Fail-closed:** ante ambigüedad o baja confianza, el sistema **no autoconcilia**.
- **Sin errores silenciosos:** validación estricta; errores explícitos.
- **Auditable:** evidencia técnica (`run.json`, `audit.jsonl`, XLSX).
- **Determinista:** misma entrada → mismo `run.json` (sin timestamps variables).

---

## Qué hace (y qué no)

### Qué hace
- Concilia movimientos del **banco** (cartola/extracto) contra movimientos **esperados** (ERP/planilla/registros internos).
- Genera **matches** y **hallazgos** (pendientes, advertencias, riesgos) con explicación.
- Produce artefactos reproducibles para cierre mensual y auditoría.

### Qué NO hace
- No se conecta a bancos, no descarga datos, no usa APIs bancarias.
- No es un ERP ni “reemplaza” criterio contable.
- No “adivina” para maximizar autoconciliación (por diseño, prioriza control de daño).
- No es SaaS: no hay telemetría ni envío de datos (todo corre local).

---

## Quick Start (5 minutos)

### 1) Instalar (pipx, recomendado)

```powershell
pipx install .
concilia --help
```

OCR (opcional para PDFs escaneados):
```powershell
pipx inject conciliador-bancario pdf2image pytesseract Pillow
```

### 2) Inicializar un “cliente”

```powershell
concilia init --out-dir .\mi_cliente
```

Esto crea plantillas:
- `.\mi_cliente\config_cliente.yaml`
- `.\mi_cliente\banco.csv`
- `.\mi_cliente\movimientos_esperados.csv`

### 3) Validar inputs (antes de correr)

```powershell
concilia validate --config .\mi_cliente\config_cliente.yaml --bank .\mi_cliente\banco.csv --expected .\mi_cliente\movimientos_esperados.csv
```

### 4) Ejecutar (modo seguro primero)

```powershell
concilia run --config .\mi_cliente\config_cliente.yaml --bank .\mi_cliente\banco.csv --expected .\mi_cliente\movimientos_esperados.csv --out .\salida --dry-run
```

Luego, para generar XLSX:
```powershell
concilia run --config .\mi_cliente\config_cliente.yaml --bank .\mi_cliente\banco.csv --expected .\mi_cliente\movimientos_esperados.csv --out .\salida
```

### 5) Explicar un caso puntual

```powershell
concilia explain --run-dir .\salida M-<match_id>
concilia explain --run-dir .\salida H-<hallazgo_id>
```

---

## Formatos soportados (MVP)

- Banco: CSV / XLSX / XML / PDF (texto).
- PDF escaneado: **solo** con OCR habilitado (opcional) y siempre con política conservadora (no autoconcilia).
- Movimientos esperados: CSV / XLSX.

---

## Calidad y confianza (lo que mira CI)

Este repo tiene guardrails para bloquear regresiones:
- Formato: **Black**
- Lint: **Ruff**
- SAST: **Bandit**
- SCA (supply-chain): **pip-audit** (vulnerabilidades en dependencias; ver `.pip-audit-ignore.txt`)
- SAST semántico: **Semgrep** (corre en CI sobre Ubuntu; en Windows requiere Docker/WSL)
- Tests: **pytest** (incluye tests “golden” para outputs contractuales)

Comandos locales:
```powershell
python -m pip install -e ".[dev]"

python -m black --check src tests tools
python -m ruff check src tests tools
python -m bandit -c .bandit.yml -r src
python tools/pip_audit_gate.py
python -m pytest -q
```

Semgrep (opcional local):
```powershell
# Requiere Docker o WSL2; en CI ya está integrado.
docker run --rm -v "${PWD}:/src" -w /src returntocorp/semgrep:1.95.0 semgrep scan --config .semgrep.yml --error --metrics=off src
```

---

## Contratos y artefactos (Core → Premium)

El artefacto `run.json` es un **contrato versionado** para consumo por herramientas externas (incluyendo premium).

- Especificación: `docs/contract_run_json.md`
- Glosario de términos: `GLOSARIO.md`

---

## Documentación

Empiece aquí:
- [Manual de Usuario (RUNBOOK)](RUNBOOK.md)
- [Glosario de Términos](GLOSARIO.md)

Referencia:
- `docs/guia_contadores.md`
- `docs/guia_tecnica.md`
- `docs/agregar_formato.md`
- `docs/contract_run_json.md`
- `walkthrough.md`
- `mvp_checklist.md`

---

## Público objetivo

### Sí
- Estudios contables, PyMEs y equipos que necesitan un flujo **reproducible** de conciliación con evidencia.
- Usuarios no técnicos o semi-técnicos que puedan ejecutar comandos y preparar archivos (CSV/XLSX/PDF).

### No
- Quien busca integración automática con bancos, sincronización online o una UI gráfica.
- Quien necesita maximizar “auto-match” a costa de riesgo (este proyecto prefiere conservadurismo).

---

## Estado del proyecto

MVP funcional:
- `concilia init`, `validate`, `run`, `explain` operativos.
- Ingestión para CSV/XLSX/XML/PDF texto; OCR opcional.
- Salidas: `run.json`, `audit.jsonl`, `reporte_conciliacion.xlsx`.

Roadmap (alto nivel, sin promesas de fecha):
- Endurecer compatibilidad por formatos bancarios reales (sin romper contrato).
- Mejoras de ergonomía y documentación operativa.

---

## Versionado y releases

- Source of truth: `src/conciliador_bancario/version.py`
- Historial de cambios: `CHANGELOG.md`
- Política (repo público): cada merge a `main` hace bump automático de `patch`, crea tag `vX.Y.Z` y (si está configurado) publica en PyPI.

---

## Premium (opcional)

Existe un repositorio premium separado orientado a productividad (revisión/agrupación/priorización), que **consume** el `run_dir` generado por este core.
Este repo no incluye el código premium.
