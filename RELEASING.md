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

Regla operacional (anti-olvido): los releases se gestionan con **Release Please**:
- abre un PR de release con bump semántico + `CHANGELOG.md` generado desde commits/PRs,
- al mergear ese PR crea tag `vX.Y.Z`,
- el push del tag dispara `.github/workflows/publish.yml` (Trusted Publishing a PyPI).

No se deben crear tags de release manualmente: `publish.yml` falla (fail-closed) si el tag no coincide con `version.py`.

### Opción A: automático (release workflow)

Un push a `main` hace que `Release Please` mantenga (o cree) un PR de release.

Requisito (importante, fail-closed):
- Configure un token que NO sea el `GITHUB_TOKEN` por defecto, porque:
  - PRs creados con `GITHUB_TOKEN` no gatillan CI automáticamente.
  - tags pusheados con `GITHUB_TOKEN` no gatillan `publish.yml`.
- Use `RELEASE_PLEASE_TOKEN` (PAT classic con scope `repo`) como secret del repo.

Workflow: `.github/workflows/release-please.yml`

Convención mínima (para notas automáticas útiles):
- `feat:` nueva funcionalidad (SemVer minor).
- `fix:` corrección (SemVer patch).
- `docs:` documentación (puede aparecer en changelog, según configuración).
- `refactor:` refactor sin cambio funcional.
- `chore:` tareas de mantenimiento (idealmente sin impactar usuario).

#### Cómo mergear sin duplicar el changelog

**El título del PR no debe llevar el prefijo de tipo** (`fix:`, `feat:`, ...),
aunque los commits internos sí lo lleven.

No es una preferencia de estilo. Este repo mergea con merge commit, y GitHub
escribe el título del PR en el **cuerpo** del merge commit:

```
Merge pull request #20 from cortega26/fix/error-taxonomy-contract

fix(errors): ErrorIngestion cumple el contrato de la taxonomia; mypy a cero y en CI
```

Release-please parsea los cuerpos de los commits como mensajes conventional, así
que con el prefijo en el título la entrada aparece **dos veces** en el changelog:
una por el título del PR y otra por cada commit individual. Con un PR de 3
commits son 4 líneas, dos de ellas duplicadas.

Por eso se mergea localmente con un cuerpo sin tipo, en vez de dejar que GitHub
lo redacte:

```bash
# En vez de: gh pr merge <n> --merge
git checkout main && git pull --ff-only
git merge --no-ff <rama> -m "Merge PR #<n>: <titulo del PR sin prefijo de tipo>"
git push
```

La alternativa sería mergear con squash, pero eso destruiría el historial
granular con la explicación de cada commit, que es justamente lo que hace
revisable este repo. Con merge commit + cuerpo sin tipo se conservan las dos
cosas.

Las secciones del changelog están declaradas en
`changelog-sections` (`.github/release-please-config.json`). Sin esa clave los
commits `build:` y `test:` se descartan **en silencio**: el changelog se ve
completo y no avisa que le faltan entradas.

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

En un entorno limpio. El venv debe crearse **fuera del repositorio**: si queda
dentro, `hatchling` lo empaqueta en el sdist de la versión siguiente (los
`.gitignore` no protegen el build, que empaqueta lo que git rastrea).

```powershell
$smoke = Join-Path $env:TEMP "bankrecon_smoke"
python -m venv $smoke
& "$smoke\Scripts\python" -m pip install -U pip
& "$smoke\Scripts\pip" install "bankrecon==<X.Y.Z>"
& "$smoke\Scripts\python" -c "import bankrecon as br; print(br.__version__)"
& "$smoke\Scripts\concilia" --help
Remove-Item -Recurse -Force $smoke
```
