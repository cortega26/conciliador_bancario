# Migration Report: `conciliador_core` -> `conciliador_bancario.core`

Fecha: 2026-02-09

## Objetivo

Eliminar `conciliador_core` como paquete top-level y mover su codigo a un subpaquete interno:

- Antes: `src/conciliador_core/...`
- Despues: `src/conciliador_bancario/core/...`

## Fase 0 (antes de tocar): verificacion base

- `git status --porcelain=v1 -b`: limpio
- `python -m pytest -q`: PASS
- `python -m build`: PASS
- `python -m twine check dist/*`: PASS
- `python -c "import conciliador_bancario; print(conciliador_bancario.__version__)"`: imprime version
- `concilia --help`: exit code 0

## Fase 4 (despues de migrar): verificacion completa

- `python -m compileall .`: PASS
- `python -m black --check src tests tools`: PASS
- `python -m ruff check src tests tools`: PASS
- `python -m pytest -q`: PASS
- `python -m bandit -c .bandit.yml -r src`: PASS
- `python -m build`: PASS
- `python -m twine check dist/*`: PASS

### Venv limpio (wheel real)

- `pip install dist/*.whl`: PASS
- `python -c "import conciliador_bancario; print(conciliador_bancario.__version__)"`: PASS
- `concilia --help`: exit code 0
- `python -c "import importlib.util; print(importlib.util.find_spec('conciliador_core'))"`: imprime `None`

## Notas

- Se observan warnings de `openpyxl` por `datetime.utcnow()` deprecado; no afecta determinismo ni el contrato.
