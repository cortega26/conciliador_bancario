# RELEASING (Maintainers) — Publicación a PyPI (Trusted Publishing)

Este documento es para maintainers. El manual de usuarios está en `RUNBOOK.md`.

## Checklist (pre-publish)

- `pyproject.toml`: `[project].name = "bankrecon"`.
- CI `main` verde.
- `python -m build` produce `sdist` + `wheel`.
- `python -m twine check dist/*` pasa.
- Smoke en venv limpio: `pip install bankrecon==X.Y.Z` + `python -c "import bankrecon"` + `concilia --help`.
- PyPI: Trusted Publisher configurado para `cortega26/conciliador_bancario` y workflow `.github/workflows/publish.yml`.

## 1. Pre-chequeos: repo correcto

Confirme que está operando dentro del repo OSS real (no en el folder “padre” de un workspace multi-root):

```powershell
git rev-parse --show-toplevel
git status
```

## 2. Versionado y tags `vX.Y.Z`

Fuente de verdad de versión:
- `src/conciliador_bancario/version.py`

Regla: el workflow `.github/workflows/publish.yml` publica cuando se pushea un tag `v*.*.*`.

Regla operacional (anti-olvido): **cada push a `main` con CI verde** gatilla un release automático que:
- hace bump automático de `patch`,
- actualiza `CHANGELOG.md`,
- crea tag `vX.Y.Z`,
- y empuja el commit/tag.

No se deben crear tags de release manualmente: `publish.yml` falla (fail-closed) si el tag no coincide con `version.py`.

### Opción A: automático (release workflow)

Un push a `main` con CI verde crea el commit de release, taggea y pushea (ver job `release` en `.github/workflows/ci.yml`).

### Opción B: manual (control de patch/minor/major)

```powershell
python -m pip install -e ".[dev]"

# Elija uno:
bump2version patch
# bump2version minor
# bump2version major

python tools/bump_changelog.py --version "<X.Y.Z>"

git add src/conciliador_bancario/version.py .bumpversion.cfg CHANGELOG.md
git commit -m "chore(release): v<X.Y.Z> [skip release]"
git tag "v<X.Y.Z>"
git push origin HEAD:main --follow-tags
```

## 3. Configurar Trusted Publisher en PyPI (una vez)

En PyPI:
1. Project -> Settings -> Publishing (Trusted Publishers).
2. Agregue un Trusted Publisher con:
   - Owner: `cortega26`
   - Repository: `conciliador_bancario`
   - Workflow path: `.github/workflows/publish.yml`
   - Environment: vacío (a menos que el workflow agregue `environment:`)

Nota: `publish.yml` requiere `permissions: id-token: write`.

## 4. Verificación post-publicación

En un entorno limpio:

```powershell
python -m venv .pypi_smoke
.\.pypi_smoke\Scripts\python -m pip install -U pip
.\.pypi_smoke\Scripts\pip install "bankrecon==<X.Y.Z>"
.\.pypi_smoke\Scripts\python -c "import bankrecon as br; print(br.__version__)"
.\.pypi_smoke\Scripts\concilia --help
```
