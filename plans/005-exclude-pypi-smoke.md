# Plan 005: Remove `.pypi_smoke` from the published sdist

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 0704075..HEAD -- .gitignore pyproject.toml RELEASING.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `0704075`, 2026-09-28

## Why this matters

A vendored Windows virtualenv — 477 files, 7.2 MB, including 11 `.exe` binaries
and a full copy of pip 26.0.1 that the maintainer did not build — is committed to
the repository and shipped in the published sdist.

This is not hypothetical. Building the sdist at `0704075` and listing its contents
gives:

```
$ tar tzf dist/bankrecon-0.2.14.tar.gz | grep -c "pypi_smoke"
477
$ tar tzf dist/bankrecon-0.2.14.tar.gz | grep -cE "\.exe$"
11
```

`bankrecon` is a financial-audit tool. Its sdist carries third-party Windows
binaries, which inflates every `pip install bankrecon` from source, widens the
supply-chain surface, and permanently freezes pip 26.0.1 in release history.
Published artifacts cannot be retracted.

The root cause is documented in the repo itself: `RELEASING.md:91-95` tells a
maintainer to create the verification venv **inside the repository root**, and
`CHANGELOG.md:65` records that the accident already happened once.

## Current state

The files are tracked and nothing excludes them:

```bash
$ git ls-files .pypi_smoke | wc -l
477
$ git check-ignore -v .pypi_smoke
# (no output — not ignored)
```

`.gitignore` (22 lines) has no entry for it, nor for `.smoke_venv` — which
`ci.yml:81` also creates. The current ignore list ends:

```
# Workspace boundaries / secretos (defensa adicional contra contaminacion accidental)
license.lic
*.pem
*.key
*.p12
*.pfx
*.code-workspace
```

`pyproject.toml:58-72` configures the build:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/conciliador_bancario", "src/bankrecon"]
include = [
  "src/conciliador_bancario/templates/*.yaml",
  "src/conciliador_bancario/templates/*.csv",
]

[tool.hatch.version]
path = "src/conciliador_bancario/version.py"

[tool.hatch.build]
exclude = [
  "**/__pycache__/**",
  "**/*.pyc",
]
```

There is **no `[tool.hatch.build.targets.sdist]` section**. The wheel is
correctly restricted to `src/`, so this only affects the sdist — which is why
`CHANGELOG.md:65`'s claim that it "no afecta el runtime del paquete" is true for
the wheel and false for the sdist.

The documented cause: `RELEASING.md:91-95` instructs creating a `.pypi_smoke`
venv in the repo root for post-publish verification.

## Scope

**In scope** (the only files you may modify):
- `.gitignore`
- `pyproject.toml`
- `RELEASING.md`

**Out of scope** (do NOT touch, even though they look related):
- **The tracked files under `.pypi_smoke/` themselves.** Do **not** `git rm` them.
  Deleting 477 tracked files is a separate decision with real consequences (see
  Maintenance notes) and the maintainer must make it. This plan makes them
  *stop being packaged*; it does not remove them from history.
- `.github/workflows/ci.yml` — the CI's `.smoke_venv` is created in a fresh
  runner and never committed. Adding an ignore rule for it is enough.
- `CHANGELOG.md` — do not add an entry; the maintainer should decide how to
  describe an already-published artifact after the fact.
- Git history. Do **not** rewrite it. See STOP conditions.

## Git workflow

- Branch: `advisor/005-exclude-pypi-smoke`
- Conventional Commits, matching `git log --oneline -20`. Suggested:
  `build: exclude .pypi_smoke from the sdist`
- Do NOT push or open a PR unless the operator instructed it.

## Commands you will need

| Purpose | Command | Provenance | Expected on success |
|---------|---------|------------|---------------------|
| Install | `pip install -e ".[dev]"` | declared | exit 0 |
| Install (build) | `python -m pip install build==1.2.2` | declared | exit 0 |
| Tests | `python -m pytest -q` | executed | 63 passed, 0 failed |
| Build | `python -m build --outdir dist` | executed | builds sdist + wheel |
| Inspect | `tar tzf dist/bankrecon-*.tar.gz \| grep -c pypi_smoke` | executed | **477** (the bug) |
| Format | `python -m black --check src tests tools` | executed | 65 files unchanged |
| Lint | `python -m ruff check src tests tools` | executed | All checks passed |

The `Inspect` row is the finding, measured by the plan author at `0704075`.
`Tests` and `Build` were also run. Note `dist/` is already gitignored
(`.gitignore:11`), so building does not dirty the tree — but check `git status`
afterwards anyway.

## Steps

### Step 0: Establish a green baseline and reproduce the packaging defect

Run `Tests`. Then run the `Build` and `Inspect` rows unmodified.

- All pass, and `Inspect` prints `477` → the defect is reproduced. Proceed.
- `Inspect` prints `0` → the defect is already fixed. **STOP and report**; do
  not make a redundant change.

**Verify**: `python -m pytest -q` → `63 passed`, and the inspect row prints a
number greater than zero.

### Step 1: Add the ignore rules

In `.gitignore`, add a clearly-commented section. Include at least:

```
# Entornos de verificacion de publicacion (creados por RELEASING.md / CI).
# Deben vivir FUERA del repo: si se commitean, terminan en el sdist.
.pypi_smoke/
.smoke_venv/
.hypothesis/
```

Add `.hypothesis/` because `git status --porcelain` currently reports it as
untracked noise, and that is how the `.pypi_smoke` accident happened in the first
place — a missing ignore rule.

**Verify**: `git check-ignore -v .pypi_smoke .smoke_venv .hypothesis` → all three
resolve to a rule in `.gitignore`.

### Step 2: Exclude it from the sdist explicitly

An ignore rule alone is **not sufficient** — hatchling's sdist includes tracked
files regardless of `.gitignore`. Add an explicit section to `pyproject.toml`:

```toml
[tool.hatch.build.targets.sdist]
exclude = [
  "**/.pypi_smoke/**",
  "**/.smoke_venv/**",
  "**/.hypothesis/**",
  "**/dist/**",
  "**/build/**",
]
```

Keep it separate from the existing `[tool.hatch.build] exclude` — that one is the
generic build exclusion; this one is sdist-specific. Add a short Spanish comment
explaining why (these are local verification venvs, not package content).

**Verify**: `python -m build --outdir dist` exits 0, then the inspect row prints
**`0`**.

### Step 3: Verify the wheel was never affected (and still is not)

The wheel should be unaffected by this whole issue, but confirm rather than
assume — the templates `include` list at `pyproject.toml:60-63` is load-bearing
for `concilia init`.

```bash
python -m zipfile -l dist/bankrecon-*.whl | grep -c "templates/"
```

**Verify**: that prints **3** (`config_cliente.yaml`, `movimientos_esperados.csv`,
`cartola_banco.csv`) and **0** for `pypi_smoke`.

### Step 4: Fix the documented cause

In `RELEASING.md`, read §"Opción B" / the post-publish verification steps around
lines 91-95, and change the instruction so the venv is created **outside** the
repository. Use a platform-appropriate temp location and keep the existing
verification commands working against it.

Read the surrounding section first: the same document reportedly contains a
contradiction ("No se deben crear tags de release manualmente" at `:35` versus an
"Opción B: manual" that ends in `git tag` at `:56-72`). **Do not** fix that
contradiction here — it is a separate documentation finding. Only change the venv
location instruction, and leave the surrounding text otherwise intact.

**Verify**: `git diff RELEASING.md` shows only the venv-location change.

### Step 5: Verify the full gate

**Verify**:
- `python -m pytest -q` → `63 passed, 0 failed`
- `python -m black --check src tests tools` → all unchanged
- `python -m ruff check src tests tools` → `All checks passed!`
- `python -m build --outdir dist` → exit 0
- `tar tzf dist/bankrecon-*.tar.gz | grep -c pypi_smoke` → **`0`**
- `git status --porcelain` shows no new untracked files from the build

## Test plan

This plan is packaging-only; there is no source behavior to unit-test. The
verification is the build-and-inspect loop in Steps 0, 2, and 3.

If you judge that a regression test is warranted, the cheapest durable guard is a
test that asserts `.gitignore` contains an entry for `.pypi_smoke` — it costs
three lines and would have caught the original omission. Add it to
`tests/test_workspace_boundaries.py` (which already tests tooling-adjacent
invariants) **only if** you can do so without inventing a new pattern; otherwise
skip it and note the decision in your report. `tests/test_workspace_boundaries.py`
is otherwise **out of scope**.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -m pytest -q` exits 0
- [ ] `python -m black --check src tests tools` exits 0
- [ ] `python -m ruff check src tests tools` exits 0
- [ ] `python -m build --outdir dist` exits 0
- [ ] `tar tzf dist/bankrecon-*.tar.gz | grep -c pypi_smoke` prints **`0`**
- [ ] `python -m zipfile -l dist/bankrecon-*.whl | grep -c "templates/"` prints `3`
- [ ] `git ls-files .pypi_smoke | wc -l` still prints `477` (this plan does **not**
      remove tracked files)
- [ ] `git diff --name-only 0704075...HEAD` lists only `.gitignore`, `pyproject.toml`,
      `RELEASING.md`, and `plans/README.md`
- [ ] `plans/README.md` status row updated to DONE

## STOP conditions

Stop and report back (do not improvise) if:

- Any Step 0 command fails on the unmodified checkout.
- The `Inspect` row already prints `0` at baseline (nothing to fix).
- Removing the tracked `.pypi_smoke/` files appears to be **required** to make the
  build correct. It is not — report the situation instead of deleting 477 files.
- Anyone asks you to rewrite git history to purge them. **Do not.** That breaks
  existing clones and the release-please tag chain. Report it as a maintainer
  decision.
- You are tempted to modify `.github/workflows/publish.yml` or `ci.yml`. Out of
  scope; the CI venv is created on a fresh runner and is not the problem.
- The `templates/` count in the wheel is not 3. That means the build config is
  broken in some other way — report it, do not paper over it.

## Maintenance notes

- **Already-published artifacts are unrecoverable.** Versions on PyPI that were
  built from `0704075` still contain the vendored venv. This plan fixes future
  builds only. Whether to purge git history is a maintainer decision with
  real trade-offs, and the answer is usually "no" — say so plainly in your report
  rather than leaving it ambiguous.
- `git ls-files .pypi_smoke | wc -l` will keep printing 477 until someone
  explicitly removes them. That is expected after this plan. It is worth a
  follow-up issue, not a follow-up commit here.
- The real fix for the class of problem is a pre-commit hook enforcing ignore
  hygiene, so an untracked-but-unignored directory is caught before commit rather
  than at release. That is a separate DX finding; unblocked by nothing, it just
  was not worth mixing into a packaging fix.
- A reviewer should scrutinize Step 2: the `.gitignore` rule is *not* what makes
  the sdist correct. Only the `[tool.hatch.build.targets.sdist] exclude` does.
  If only `.gitignore` was changed, the fix is incomplete.
- **Deferred**: `RELEASING.md` reportedly contradicts itself about whether manual
  tags are allowed (`:35` vs `:56-72`), and `.bumpversion.cfg` is two versions
  stale (reads `0.2.12` while `version.py` reads `0.2.14`) so the documented
  manual path would downgrade the version. Both are real release-process defects,
  unblocked by nothing, and deliberately left alone here.
