# Plan 007: Fix the `--mask`/`--no-mask` CLI wiring

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 0704075..HEAD -- src/conciliador_bancario/cli/app.py tests/test_cli_error_boundary.py tests/test_ux_contracts_cli.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `0704075`, 2026-09-28

## Why this matters

`concilia run --no-mask` cannot work. It exits 2 with
`Error (entrada) Flags incompatibles: --mask y --no-mask.` — a user-facing error
that blames the user for a wiring defect in the tool. The flag is documented in
`--help` ("Desactiva enmascaramiento (no recomendado)") and in the README, so
someone following the documentation is told they did something wrong.

Masking is a security control the README and `RUNBOOK.md` both describe as
protecting reports. A flag that looks like it turns it off but instead errors out
is worse than no flag: the operator concludes masking cannot be disabled and stops
thinking about it.

## Current state

Typer synthesizes a `--mask`/`--no-mask` boolean pair from a `bool` option with a
default. The code then re-registers the same flag name as a separate parameter,
so both exist and the mutual-exclusion guard trips:

```python
# src/conciliador_bancario/cli/app.py:109-112
    mask: bool = typer.Option(True, "--mask", help="Enmascarar datos sensibles en reporte/logs"),
    no_mask: bool = typer.Option(
        False, "--no-mask", help="Desactiva enmascaramiento (no recomendado)"
    ),
```

```python
# src/conciliador_bancario/cli/app.py:136-144
    try:
        if no_mask and mask:
            raise ErrorEntradaUsuario(
                "Flags incompatibles: --mask y --no-mask.",
                details={"flag_1": "--mask", "flag_2": "--no-mask"},
                hint="Use solo una de las dos opciones.",
            )
        if no_mask:
            mask = False
```

Because `mask` is still at its default `True` when `no_mask` is set, the guard at
`:137` always fires first.

Reproduced at `0704075` via `CliRunner`:

```
F#5 --no-mask exit code: 2
OUTPUT: Error (entrada) Flags incompatibles: --mask y --no-mask.
Detalles:
- flag_1: --mask
- flag_2: --no-mask
Como resolver: Use solo una de las dos opciones.
```

`--mask` and no-flag both work correctly (exit 0). Only `--no-mask` fails.

`mask` is part of the run fingerprint at `src/conciliador_bancario/pipeline.py:248`,
so it affects `run_id`. This plan does not change the default value of `mask`
(`True`), so `run_id` is unaffected for every existing invocation.

Existing tests: `tests/test_cli_error_boundary.py` (151 lines) covers CLI error
classification and is the natural home for a flag test. `grep` for `no-mask` /
`no_mask` across `tests/` currently returns nothing, so the flag is untested.

## Scope

**In scope** (the only files you may modify):
- `src/conciliador_bancario/cli/app.py`
- `tests/test_cli_error_boundary.py`
- `tests/test_ux_contracts_cli.py` (only if it asserts the current broken
  behavior — see Step 2)

**Out of scope** (do NOT touch, even though they look related):
- `src/conciliador_bancario/reporting/excel_report.py` — masking there works.
- `run.json` / `audit.jsonl` masking. Real finding (raw references reach both
  artifacts even with `--mask` on), but it changes the contract Premium consumes
  and needs a design decision. Separate item.
- `mask_por_defecto` and `rut_mask`. These are config keys with **no reader
  anywhere** in `src/`, documented at `RUNBOOK.md:278,283` and shipped in
  `templates/config_cliente.yaml:2,13`. Wiring them up is a separate finding —
  it changes the default and therefore `run_id`, which would invalidate all six
  golden fixtures. Explicitly out of scope.
- `pyproject.toml`'s per-file ignore for `cli/app.py`
  (`["B008", "UP007"]` at `:98`) — leave it.

## Git workflow

- Branch: `advisor/007-fix-mask-flag`
- Conventional Commits, matching `git log --oneline -20`. Suggested:
  `fix(cli): make --no-mask usable`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 0: Establish a green baseline

Run the `Tests`, `Format`, and `Lint` rows unmodified.

- All pass → proceed to Step 1.
- Any fails → **STOP and report** with the command and exact output.

**Verify**: `python -m pytest -q` → `63 passed`.

### Step 1: Pin all three flag behaviors as a failing test

Read `tests/test_cli_error_boundary.py` in full. Add a table-driven test invoking
`concilia run` with the real example fixtures, once per flag combination:

| invocation | expected |
|---|---|
| no flag | exit 0, report written |
| `--mask` | exit 0, report written |
| `--no-mask` | exit 0, report written, **and unmasked** |

Use `tmp_path` for `--out` so the test is isolated. The `CliRunner` usage pattern
is in `tests/test_e2e_cli.py`; read it and match it.

**Verify**: `python -m pytest tests/test_cli_error_boundary.py -q` → the
`--no-mask` case FAILS with exit 2. The other two pass.

### Step 2: Check whether any existing test depends on the broken behavior

```bash
grep -rn "no-mask\|no_mask\|Flags incompatibles" tests/
```

If nothing matches, no existing test is affected. If something asserts the current
failure, that is a test pinning a bug — report it before editing rather than
quietly updating it.

**Verify**: report what the grep returned.

### Step 3: Remove the redundant parameter and its guard

In `src/conciliador_bancario/cli/app.py`:

- Delete the `no_mask` parameter at `:110-112`.
- Delete the `if no_mask and mask: raise ErrorEntradaUsuario(...)` block at
  `:137-142`.
- Delete the `if no_mask: mask = False` at `:143-144`.

Typer's synthesized pair handles both directions: `--mask` sets `mask=True`,
`--no-mask` sets `mask=False`, and omitting the flag leaves the default `True`.

Keep the `mask` parameter and its help text. Improve the help string so it
describes the single pair clearly — e.g. mention that `--no-mask` disables
masking and is not recommended — since the help is the only place a user learns
this.

Check whether `ErrorEntradaUsuario` is still imported and used elsewhere in the
file before removing anything from the import block
(`src/conciliador_bancario/errors.py:12-16`). If it becomes unused, ruff's `F401`
will flag it — remove it from the import in the same change.

**Verify**: `python -m ruff check src` → `All checks passed!`

### Step 4: Assert masking actually changes the report

Extending Step 1: for the `--no-mask` case, assert the produced workbook differs
from the masked one. Put a long account number (10+ digits) in a bank
`descripcion` value and assert it appears verbatim in one report and star-masked
(`masking.py:25`) in the other.

This is the assertion that proves the flag is not merely accepted but actually
functional — the current failure would also have been satisfied by an option that
parses and does nothing.

Note: `tests/test_reporting_security.py` also writes bank CSVs; read it for the
fixture-building pattern and keep your own test self-contained.

**Verify**: `python -m pytest tests/test_cli_error_boundary.py -q` → all pass,
including both masking assertions.

### Step 5: Verify the full gate

**Verify**:
- `python -m pytest -q` → all pass (63 + your additions)
- `python -m black --check src tests tools` → all unchanged
- `python -m ruff check src tests tools` → `All checks passed!`
- `git diff 0704075 -- tests/golden/` → **empty** (the default is unchanged, so
  no fingerprint changes)
- `git diff 0704075 -- src/conciliador_bancario/pipeline.py` → **empty** (no
  fingerprint change is needed or wanted here)

### Step 6: Confirm the CLI help and behavior by hand

```bash
PYTHONPATH=src python -c "
from typer.testing import CliRunner
from conciliador_bancario.cli.app import app
for args in ([], ['--mask'], ['--no-mask']):
    r = CliRunner().invoke(app, ['run','--config','examples/config_cliente.yaml',
        '--bank','examples/banco_ejemplo.csv','--expected','examples/movimientos_esperados.csv',
        '--out','/tmp/opencode/probe/flagcheck', *args])
    print(args, '->', r.exit_code)
"
```

**Verify**: all three print `-> 0`. Also run `concilia run --help` and confirm the
help text mentions both `--mask` and `--no-mask` and no longer advertises a flag
that errors.

## Test plan

- **New tests in `tests/test_cli_error_boundary.py`**: the three-way flag table,
  plus the masked-vs-unmasked workbook assertion.
- **Pattern to follow**: the existing contents of that file and the `CliRunner`
  usage in `tests/test_e2e_cli.py`.
- **Regression pinned**: `--no-mask` exits 0 and genuinely produces an unmasked
  report.
- Verification: `python -m pytest -q` → all pass, goldens unchanged.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -m pytest -q` exits 0
- [ ] `python -m black --check src tests tools` exits 0
- [ ] `python -m ruff check src tests tools` exits 0
- [ ] `git diff 0704075 -- tests/golden/` is **empty**
- [ ] `git diff 0704075 -- src/conciliador_bancario/pipeline.py` is **empty**
- [ ] `git diff --name-only 0704075...HEAD` lists only the in-scope files and
      `plans/README.md`
- [ ] `grep -n "no_mask" src/conciliador_bancario/cli/app.py` returns no match
- [ ] All three of `[]`, `["--mask"]`, `["--no-mask"]` exit 0
- [ ] A test asserts the masked and unmasked reports differ
- [ ] `plans/README.md` status row updated to DONE

## STOP conditions

Stop and report back (do not improvise) if:

- Any Step 0 command fails on the unmodified checkout.
- Any file under `tests/golden/` changes. This plan must not alter the `mask`
  default; if it does, something else moved and needs review.
- An existing test asserts the current `--no-mask` failure. Report before editing.
- You conclude `--no-mask` should not exist at all (i.e. masking should be
  mandatory). That is a defensible policy position for a financial-audit tool, but
  it is the maintainer's call and it contradicts the current documentation — report
  it, do not implement it.
- You are tempted to wire `mask_por_defecto` in while you are here. Out of scope;
  it changes `run_id` and would invalidate every golden fixture.

## Maintenance notes

- Typer's boolean-pair behavior is the whole bug: `typer.Option(True, "--mask")`
  on a `bool` already produces `--mask/--no-mask`. Do not "re-add" an explicit
  `--no-mask` parameter. If someone needs a tri-state (unset / on / off), the
  correct shape is `Optional[bool] = None` plus explicit resolution — that is the
  shape `mask_por_defecto` would need, and it belongs to that separate finding.
- The default stays `True`. Masking remains on unless someone explicitly opts out,
  which is the right posture for this tool.
- `mask` participates in the `run_id` fingerprint (`pipeline.py:248`), so
  `--no-mask` and `--mask` produce different `run_id`s for identical inputs. That
  is intended: the artifacts differ, so the identity of the run must differ. Do
  not "fix" it.
- A reviewer should scrutinize Step 4 specifically. A test that only asserts exit
  0 would also have passed against a flag that parses and does nothing.
- **Deferred**: raw bank references and counterparty identifiers reach `run.json`
  and `audit.jsonl` unmasked even with `--mask` on (masking is applied only to the
  XLSX path, `pipeline.py:305`). Threading masking into those artifacts changes
  the contract that Premium consumes and needs an explicit product decision. Also
  deferred: `mask_por_defecto` and `rut_mask` remain unread config keys. Both
  unblocked by nothing; both need a maintainer decision, not a mechanical fix.
