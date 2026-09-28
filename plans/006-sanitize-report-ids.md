# Plan 006: Sanitize user-controlled IDs in the XLSX report

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 0704075..HEAD -- src/conciliador_bancario/reporting/excel_report.py src/conciliador_bancario/utils/masking.py src/conciliador_bancario/models.py tests/test_reporting_security.py`
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

`reporte_conciliacion.xlsx` is the artifact a human opens to review the
reconciliation. Four cell values are written to it raw, bypassing the sanitization
helper the file already defines, and all four derive from the user's input files.

Reproduced at `0704075`: an expected-movements CSV with an `id` of
`=cmd|'/c calc'!A1` produced a cell in the `Esperados` sheet with openpyxl
`data_type='f'` — a **live formula cell**, not text. `prevenir_csv_injection`
exists in `utils/masking.py:29` for exactly this and simply is not called on these
paths. The accountant opens the report, Excel evaluates the cell, and the payload
reaches whatever that workstation can reach.

`AGENTS.md` requires preventing CSV/XLSX injection, and `mvp_checklist.md:22`
claims the report does. It does — for most columns. These four are the gap.

## Current state

The helper exists and is correct; it is simply not used everywhere.

```python
# src/conciliador_bancario/reporting/excel_report.py:25-34
def _mask_cell(v: object, *, mask: bool) -> object:
    if v is None:
        return ""
    if isinstance(v, (int, float, Decimal)):
        return v
    if isinstance(v, str):
        s = enmascarar_texto_sensible(v) if mask else v
        s = prevenir_csv_injection(s)
        return s
    return v
```

The four unguarded write sites:

```python
# excel_report.py:126  — Esperados.exp_id
                e.id,

# excel_report.py:158  — Matches.tx_ids
                ",".join(m.transacciones_bancarias),

# excel_report.py:186  — Matches.exp_ids
                ",".join(m.movimientos_esperados),

# excel_report.py:188  — Hallazgos.entidad_id
                h.entidad_id or "",
```

Compare with the guarded neighbours on the same lines — `excel_report.py:130-132`
(`_mask_cell(str(e.descripcion.valor), ...)`) — so the omission is visibly an
oversight, not a policy.

Provenance of the values is unambiguous: `MovimientoEsperado.id` comes from the
file's `id`/`id_externo` column verbatim (`ingestion/csv_adapter.py:74-77`,
`ingestion/xlsx_adapter.py:313`). `models.py:91` declares it with `min_length=1`
and no charset constraint, in contrast to `models.py:46` where `Moneda` is pinned
to `^[A-Z]{3}$`.

Existing coverage: `tests/test_reporting_security.py:31` asserts only the
`descripcion` column of the `Transacciones` sheet. One assertion wide.

### The whitespace bypass, and why it rides along here

```python
# src/conciliador_bancario/utils/masking.py:29-37
def prevenir_csv_injection(texto: str) -> str:
    """
    Previene injection de formulas en Excel/CSV.
    Si el texto comienza con = + - @, se antepone apostrofe.
    """
    t = texto or ""
    if t and t[0] in ("=", "+", "-", "@"):
        return "'" + t
    return t
```

`t[0]` only inspects the first character, so a value beginning with a space, tab,
or carriage return skips the guard entirely — a one-byte prefix defeats it. Since
this plan hardens this function anyway, fix it here rather than leaving a known
bypass in the primary defense.

## Commands you will need

| Purpose | Command | Provenance | Expected on success |
|---------|---------|------------|---------------------|
| Install | `pip install -e ".[dev]"` | declared | exit 0 |
| Tests | `python -m pytest -q` | executed | 63 passed, 0 failed |
| Tests (report) | `python -m pytest tests/test_reporting_security.py -q` | executed | all pass |
| Format | `python -m black --check src tests tools` | executed | 65 files unchanged |
| Lint | `python -m ruff check src tests tools` | executed | All checks passed |
| Goldens | `python -m pytest tests/test_golden_datasets.py tests/test_golden_examples.py -q` | executed | all pass |

`Install` is `declared`; the rest were run at `0704075` and passed.

## Scope

**In scope** (the only files you may modify):
- `src/conciliador_bancario/reporting/excel_report.py`
- `src/conciliador_bancario/utils/masking.py`
- `src/conciliador_bancario/models.py` (only the `MovimientoEsperado.id` field
  constraint — see Step 2)
- `tests/test_reporting_security.py`

**Out of scope** (do NOT touch, even though they look related):
- **The adapters.** Do not validate or strip ids at ingestion for this plan.
- `run.json` and `audit.jsonl`. The same raw value also flows there (a separate
  finding about masking not reaching the contract artifacts). This plan is about
  the spreadsheet.
- **Amounts as numbers.** `excel_report.py:100` and `:127` write
  `str(monto.valor)`, so money cells are stored as text and do not sum. Real
  finding, separate plan — do not "fix" it here; the fix interacts with the
  injection guard and deserves its own review.
- The `matches[].explicacion` and `hallazgos[].mensaje` columns — those are
  already masked at `:160` and `:186`.
- `tools/secret_scan.py` and the semgrep ruleset. Related hardening, separate
  findings.

## Git workflow

- Branch: `advisor/006-sanitize-report-ids`
- Conventional Commits, matching `git log --oneline -20`. Suggested:
  `fix(reporting): sanitize user-controlled id cells`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 0: Establish a green baseline

Run the `Tests`, `Format`, `Lint`, and `Goldens` rows unmodified.

- All pass → proceed to Step 1.
- Any fails → **STOP and report** with the command and exact output.

**Verify**: `python -m pytest -q` → `63 passed`.

### Step 1: Pin the vulnerability as a failing test

Read `tests/test_reporting_security.py` in full first. Add a test that builds a
report containing ids with the four injection prefixes (`=`, `+`, `-`, `@`) and
asserts every cell in the `Esperados`, `Matches`, and `Hallazgos` sheets is
**not** a formula.

The assertion that actually matters, and which you should use rather than
checking the string value:

```python
assert cell.data_type != "f"
```

Today this fails, because openpyxl writes an unprefixed `=...` value as a formula.

Cover all four sheets' id columns:
- `Esperados.exp_id` (`excel_report.py:126`)
- `Matches.tx_ids` and `Matches.exp_ids` (`:158`, `:186`)
- `Hallazgos.entidad_id` (`:188`)

**Verify**: `python -m pytest tests/test_reporting_security.py -q` → the new
test FAILS. If it passes, the finding is not reproducible — STOP.

### Step 2: Add a model-level constraint on `MovimientoEsperado.id`

Defense in depth: reject the dangerous shapes at the boundary rather than
relying on rendering to sanitize them.

In `src/conciliador_bancario/models.py`, tighten the `id` field on
`MovimientoEsperado` (currently at `:91`) to reject values that begin with
`=`, `+`, `-`, `@`, or contain control characters. Use a Pydantic `Field`
`pattern`, following the style already used at `:46` for `Moneda`
(`Annotated[str, Field(pattern=r"^[A-Z]{3}$")]`).

Add a Spanish comment explaining the rationale, since the reason is not obvious
from the pattern alone.

**Important trade-off to reason about, and report on:** `MovimientoBancaria.id`
is generated as `TX-<hash>` and is never affected. But a **legitimate** external
id could in principle start with `-`. If the pattern rejects ids that real
clients use, that is a behavior change. Test your pattern against the ids present
in `tests/golden/datasets/**` before committing, and report what you found.

**Verify**: `python -m pytest -q` → all pass, goldens included. If a golden fails
because its ids violate the new pattern, that is a STOP condition.

### Step 3: Route all four sites through `_mask_cell`

In `excel_report.py`, wrap the four values from "Current state" in `_mask_cell`:
`e.id`, both `",".join(...)` calls, and `h.entidad_id`.

Match the existing call style on the same rows. Note that `_mask_cell` returns
non-`str` values unchanged (`:28-29`), so this is safe for the `""` fallback
already used at `:188`.

Consider whether a small local helper for the two `",".join(...)` sites is
clearer than repeating `_mask_cell(",".join(...))` — your call, but keep it
readable.

**Verify**: `python -m pytest tests/test_reporting_security.py -q` → the Step 1
test now PASSES.

### Step 4: Harden `prevenir_csv_injection` against the whitespace prefix

In `utils/masking.py:35`, strip leading whitespace and C0 control characters
before the first-character test, so a value that Excel would still treat as a
formula cannot slip past.

Target behavior: a value whose first non-whitespace, non-control character is one
of `= + - @` gets the apostrophe prefix, and the original text (including any
leading whitespace) is preserved after it.

Keep the docstring accurate — update it to mention leading whitespace.

Add a Hypothesis case to `tests/test_reporting_security.py` (or
`tests/test_property_parsing.py` — read both first; `test_property_parsing.py`
already imports Hypothesis) generating payloads with a random amount of leading
whitespace, asserting none ever produce `data_type == "f"`.

**Verify**: `python -m pytest -q` → all pass.

### Step 5: Verify the full gate

**Verify**:
- `python -m pytest -q` → all pass (63 + your additions)
- `python -m black --check src tests tools` → all unchanged
- `python -m ruff check src tests tools` → `All checks passed!`
- `git diff 0704075 -- tests/golden/` → **empty**

### Step 6: Confirm the fix end-to-end

Reproduce the original scenario. Write a throwaway expected-CSV under `/tmp` with
`id` = `=cmd|'/c calc'!A1`, run the CLI through `CliRunner` in a **throwaway
script** (not committed), load the workbook, and print the `data_type` of the
`Esperados.exp_id` cell for that row.

**Verify**: it prints `'s'` (string), not `'f'`. Report the value.

## Test plan

- **New tests in `tests/test_reporting_security.py`**: (1) the four injection
  prefixes across the three sheets' id columns, asserting `data_type != "f"`;
  (2) the whitespace-prefixed payload; (3) a Hypothesis property over generated
  leading-whitespace payloads.
- **Pattern to follow**: the existing contents of that file.
- **Regression pinned**: an `id` beginning with `= + - @`, with or without leading
  whitespace, can never again be written as a live formula.
- Verification: `python -m pytest -q` → all pass, goldens unchanged.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -m pytest -q` exits 0
- [ ] `python -m black --check src tests tools` exits 0
- [ ] `python -m ruff check src tests tools` exits 0
- [ ] `git diff 0704075 -- tests/golden/` is **empty**
- [ ] `git diff --name-only 0704075...HEAD` lists only the in-scope files and
      `plans/README.md`
- [ ] `grep -n "^                e.id," src/conciliador_bancario/reporting/excel_report.py`
      returns no match (the raw write is gone)
- [ ] No cell in the `Esperados`, `Matches`, or `Hallazgos` sheets has
      `data_type == "f"` for a generated injection payload
- [ ] `plans/README.md` status row updated to DONE

## STOP conditions

Stop and report back (do not improvise) if:

- Any Step 0 command fails on the unmodified checkout.
- Any file under `tests/golden/` changes.
- The Step 1 test passes before you change anything — the finding is not
  reproducible; report rather than proceeding.
- The Step 2 pattern rejects ids that appear in `tests/golden/datasets/**` or in
  `examples/`. Real client data uses ids you cannot see; report the conflict
  instead of loosening the pattern to make tests pass.
- You are tempted to also fix the `str(monto.valor)` text-money cells. That is a
  different finding; report it, do not bundle it.
- The fix appears to require touching an adapter or `run_schema.py`.

## Maintenance notes

- The report is the **only** place injection is currently sanitized. `run.json`
  and `audit.jsonl` also carry the same raw values unmasked — a separate finding
  with a real design question attached (masking those changes the contract
  Premium consumes, and `run_id` includes `mask`). Do not "helpfully" extend this
  plan's fix to them; the design decision is not yours to make here.
- `_mask_cell` returning non-strings unchanged (`:28-29`) is what makes routing
  more values through it safe. Keep that behavior.
- The `models.py` constraint is the durable fix; the `_mask_cell` routing is the
  belt. Keep both — either alone leaves a gap if the other is refactored away.
- A reviewer should scrutinize Step 2's trade-off: a `pattern` that is too strict
  breaks legitimate external ids at ingestion, which is a fail-closed rejection
  the user will experience as a hard error. Check it against real-looking ids.
- **Deferred**: amounts are written to the XLSX as `str(...)` (`excel_report.py:100`,
  `:127`), so the money columns do not sum and sort lexicographically. Confirmed
  by reading the produced workbook: `data_type='s'`, `number_format='General'`. The
  fix is to write a scale-0 `Decimal` as a numeric cell, which `_mask_cell`
  already passes through untouched — but it interacts with the injection guard and
  with `Decimal` scale preservation (`"1234"` vs `"1234.00"`), so it needs its own
  plan and a workbook-type regression test. Unblocked by nothing.
