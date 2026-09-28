# Plan 002: Fix single-separator amount parsing (10–100x money errors)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 0704075..HEAD -- src/conciliador_bancario/utils/parsing.py tests/test_parsing.py tests/test_property_parsing.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: plans/001-characterize-fail-closed-branches.md
- **Category**: bug
- **Planned at**: commit `0704075`, 2026-09-28

## Why this matters

`parse_monto_clp` deletes a lone decimal separator instead of reading it as one.
A Chilean bank CSV cell of `0,50` — fifty pesos — is ingested as **50**, a 100x
error, and the run reports success with no warning anywhere. Worse, accounting
negative parentheses are stripped entirely, so `(1.234,56)` becomes **+1235**: a
credit is silently booked as a debit. Both were reproduced end-to-end through
`concilia run` at commit `0704075`, producing a `reporte_conciliacion.xlsx` whose
amount column read `50` for a `0,50` source cell, exit code 0.

This is the money parser. Every adapter routes through it. A wrong amount either
fails to match or matches the wrong movement, and in the sign-inversion case can
survive reconciliation entirely.

## Current state

`src/conciliador_bancario/utils/parsing.py` (75 lines) — the whole file is
relevant. Current state, verbatim:

```python
# src/conciliador_bancario/utils/parsing.py:12
_MONEDA_RE = re.compile(r"[^0-9,\\.\\-]")

# src/conciliador_bancario/utils/parsing.py:15-45
def parse_monto_clp(texto: str) -> Decimal:
    """
    Parseo robusto para montos tipo:
    - 1.234.567
    - 1,234,567
    - 1234567
    - -1.234,00
    - $ 1.234.567
    Regla MVP: CLP sin decimales en la salida (si vienen, se redondea a entero).
    """
    t = texto.strip()
    if not t:
        raise ErrorParseo("Monto vacio")
    t = _MONEDA_RE.sub("", t)
    t = t.replace(" ", "")
    # Si contiene ambos separadores, asume "," decimal y "." miles (formato LATAM)
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        # Si solo hay comas, asume miles y las elimina (CLP).
        if "," in t and "." not in t:
            t = t.replace(",", "")
        # Si solo hay puntos, asume miles y los elimina (CLP).
        if "." in t and "," not in t:
            t = t.replace(".", "")
    try:
        d = Decimal(t)
    except InvalidOperation as e:
        raise ErrorParseo(f"Monto invalido: {texto!r}") from e
    # CLP: sin decimales
    return d.quantize(Decimal("1"))
```

The bug is the `else` branch at lines 33-39: with exactly one separator present,
it is removed. The `quantize` at line 45 then rounds whatever survived.

Measured behavior at `0704075` (executed by the plan author):

| input | current output | correct |
|-------|----------------|---------|
| `1.234.567` | `1234567` | `1234567` |
| `1,234,567` | `1234567` | `1234567` |
| `1234567` | `1234567` | `1234567` |
| `-1.234,00` | `-1234` | `-1234` |
| `$ 1.234.567` | `1234567` | `1234567` |
| `0,50` | **`50`** | `1` (0.50 rounds to 1, or is rejected) |
| `12,5` | **`125`** | `13` (half-up) or rejected |
| `1.5` | **`15`** | `2` or rejected |
| `12.50` | **`1250`** | `13` or rejected |
| `(1.234,56)` | **`+1235`** | `-1235` |
| `(1.234)` | **`+1234`** | `-1234` |

Callers — all three go through this one function:
- `src/conciliador_bancario/ingestion/csv_adapter.py:174` (bank) and `:303` (expected)
- `src/conciliador_bancario/ingestion/xlsx_adapter.py:174, :291`
- `src/conciliador_bancario/ingestion/xml_adapter.py:108`

### Design decision you must make, and the reasoning

The docstring says "CLP sin decimales en la salida (si vienen, se redondea a
entero)" — **rounding**, not deletion. So the function is *supposed* to accept
decimal amounts and round them. The single-separator branch contradicts its own
documented contract.

CLP has no decimal subunit. A Chilean statement should not contain centavos. So
the two defensible readings of a lone separator are:

- `0,50` — a malformed CLP amount (centavos on a zero-decimal currency), or
- `12.50` — a genuine thousands separator (1,250 CLP).

Both are defensible, which is exactly the ambiguity that must be **resolved
deterministically and visibly**, not silently.

**Chosen policy** (the repo's stated rules make this the only consistent answer —
from `AGENTS.md`: "Fail-closed siempre: ante duda o ambigüedad, **NO conciliar**",
and "Cero errores silenciosos"):

1. **Two or more separators, or a well-formed thousands group** (3 digits after
   the separator) → read the last separator as the decimal point, the rest as
   thousands. `1.234.567` → `1234567`. `1,234,567` → `1234567`.
   `1.234` → `1234` (group of exactly 3 → unambiguously thousands).
2. **Exactly one separator with 1–2 digits after it** → this is a decimal amount
   on a currency that has no subunit. That is a real anomaly. **Raise
   `ErrorParseo`** naming the row value, so the run fails closed instead of
   guessing. `0,50` and `12,5` both raise.
3. **Leading or trailing `-` inside parentheses** → accounting negative. Map to a
   negative result. `(1.234,56)` → `-1235`.
4. **Otherwise, an unparseable residue** → `ErrorParseo`, as today.

This policy rejects rather than silently guessing, which is what the repo demands.
It is the conservative choice and the maintainer should be told it is a behavior
change for any client currently feeding centavos.

### Conventions to match

- All user-facing strings in this repo are **Spanish, unaccented** (`"Monto
  invalido"`, `"Fecha invalida"`, `"Monto vacio"`). Match that exactly — no
  accents, no anglicisms.
- `ErrorParseo` subclasses `ValueError` and is caught by every adapter, which
  re-wraps it as `ErrorIngestion(f"Fila {i}: monto invalido: {e}")`. Raising it
  therefore fails the whole run cleanly with a useful message. Do not introduce a
  new exception type.
- Comments in this file are in Spanish. Match.
- The repo uses `Decimal` throughout for money and quantizes explicitly. Keep
  using `Decimal`; do not introduce `float`.
- `tests/test_property_parsing.py` already exists (22 lines) and uses Hypothesis.
  It is the natural home for the generated cases.

## Commands you will need

| Purpose | Command | Provenance | Expected on success |
|---------|---------|------------|---------------------|
| Install | `pip install -e ".[dev]"` | declared | exit 0 |
| Tests | `python -m pytest -q` | executed | 63 passed, 0 failed |
| Tests (parsing) | `python -m pytest tests/test_parsing.py tests/test_property_parsing.py -q` | executed | all pass |
| Format | `python -m black --check src tests tools` | executed | 65 files unchanged |
| Lint | `python -m ruff check src tests tools` | executed | All checks passed |
| Goldens | `python -m pytest tests/test_golden_datasets.py tests/test_golden_examples.py -q` | executed | all pass |

`Install` is `declared`; all other rows were run at `0704075` and passed.

## Scope

**In scope** (the only files you may modify):
- `src/conciliador_bancario/utils/parsing.py`
- `tests/test_parsing.py`
- `tests/test_property_parsing.py`

**Out of scope** (do NOT touch, even though they look related):
- **Any adapter** (`csv_adapter.py`, `xlsx_adapter.py`, `xml_adapter.py`). They
  already propagate `ErrorParseo` correctly; changing them risks scope creep and
  is not needed for this fix.
- `tests/golden/*.json` and `tests/golden/datasets/**`. The golden fixtures use
  amounts with no single-separator ambiguity, so they must not change. If a golden
  DOES change, that is a STOP condition — see below.
- `src/conciliador_bancario/models.py` — do not change the `Moneda` pattern or
  any tolerance field. The ambiguity is resolved in the parser, not the model.
- The report's number formatting. Amounts being written to XLSX as text is a
  separate finding, not this one.

## Git workflow

- Branch: `advisor/002-fix-amount-parsing`
- Two commits, one per step group, Conventional Commits matching `git log --oneline -20`
  (e.g. `fix(release): handle merge-tag file detection in verify_release_tag`):
  - `fix(parsing): resolve single-separator amounts deterministically`
  - `test(parsing): cover ambiguous separators and accounting negatives`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 0: Establish a green baseline

Run the `Tests`, `Format`, `Lint`, and `Goldens` rows on the unmodified checkout.

- If all pass: record that and proceed to Step 1.
- If any fails: **STOP and report** with the command and exact output. Do not fix
  the build to get moving.

**Verify**: `python -m pytest -q` → `63 passed`.

### Step 1: Pin the current (buggy) behavior in a test before changing it

Read `tests/test_parsing.py` in full first. Add one test that documents today's
behavior as a **known defect** so the change in Step 2 is visible in the diff:

```python
def test_monto_con_un_solo_separador_ambiguo_falla_cerrado() -> None:
    """Un separador decimal aislado es ambiguo y debe fallar cerrado, no multiplicar por 100."""
    with pytest.raises(ErrorParseo):
        parse_monto_clp("0,50")
    with pytest.raises(ErrorParseo):
        parse_monto_clp("12,5")
```

Run it. It **must fail** (today these return `50` and `125` without raising).

**Verify**: `python -m pytest tests/test_parsing.py -q` → this new test FAILS.
A pass here means you did not reproduce the defect — fix the test first.

### Step 2: Rewrite the separator resolution

Replace the `else` branch at `parsing.py:33-39` and extend the character-class
strip at `:28` to preserve accounting parentheses.

Target shape (not verbatim — write it idiomatically for this file):

```python
# Preserva parentesis de contabilidad: (1.234) es negativo, no un caracter a eliminar.
_MONEDA_RE = re.compile(r"[^0-9,.()\\-]")
```

Then a helper that classifies by separator count, and rewrites
`parse_monto_clp` to call it. The decision table must be exactly:

| separators present | shape | action |
|---|---|---|
| both `,` and `.` | any | `.`=thousands, `,`=decimal → `1.234,56` → `1234.56` |
| only one kind, repeated | any | all but last are thousands, last is decimal → `1.234.567` → `1234567` |
| only one kind, single | 3 digits after | thousands → `1.234` → `1234` |
| only one kind, single | 1–2 digits after | **ambiguous → raise `ErrorParseo`** |
| only one kind, single | 0 digits after, or >3 | malformed → raise `ErrorParseo` |

Handle the accounting negative **before** the class strip removes the parens:
detect a leading `(` with a trailing `)`, note it, strip the parens, resolve the
magnitude, then negate. `(-1.234)` and `(1.234)` both → `-1234`.

Preserve the final `d.quantize(Decimal("1"))` and the `except InvalidOperation →
ErrorParseo` wrapper. Round-half-even is `Decimal`'s default and is what the
current code already does — do not introduce `ROUND_HALF_UP`; that would be an
undiscussed second behavior change.

Error messages must be Spanish and unaccented, and must **name the value** so the
operator can find the row, e.g.
`"Monto ambiguo (separador decimal en moneda sin decimales): '0,50'"`.

**Verify**: `python -m pytest tests/test_parsing.py -q` → the Step 1 test now
PASSES and every pre-existing test still passes.

### Step 3: Add the full behavior table as tests

In `tests/test_parsing.py`, add table-driven tests covering the entire table from
Step 2, including at minimum:

- `1.234.567` → `Decimal(1234567)`
- `1,234,567` → `Decimal(1234567)`
- `1234567` → `Decimal(1234567)`
- `-1.234,00` → `Decimal(-1234)`
- `$ 1.234.567` → `Decimal(1234567)`
- `1.234` → `Decimal(1234)`  (the 3-digit-group case, must still work)
- `0,50`, `12,5`, `1.5`, `12.50` → each raises `ErrorParseo`
- `(1.234)` → `Decimal(-1234)`  (accounting negative)
- `(1.234,56)` → `Decimal(-1235)`  (accounting negative with decimals)
- `""` → `ErrorParseo`
- `"abc"` → `ErrorParseo`

Use `pytest.mark.parametrize` — check whether the existing file already uses it
and match its style.

### Step 4: Add property-based tests

`tests/test_property_parsing.py` already imports Hypothesis. Add:

- A property that a well-formed CLP thousands-grouped amount always round-trips:
  generate a 7–9 digit integer, format it with `.` thousands separators, assert
  `parse_monto_clp(formatted) == Decimal(value)`.
- A property that accounting negatives are always negative: for any valid amount
  string, `parse_monto_clp("(" + s + ")")` is `-parse_monto_clp(s)`.

Read the file first and match its existing `@given`/`@settings` style. If it
already sets a deadline, keep it — a Hypothesis deadline failure on a slow machine
is a flaky-test source.

**Verify**: `python -m pytest tests/test_property_parsing.py -q` → all pass,
including the new ones.

### Step 5: Verify the full gate, including the untouched goldens

**Verify**:
- `python -m pytest -q` → all pass (expect 63 + the tests you added)
- `python -m black --check src tests tools` → all files unchanged
- `python -m ruff check src tests tools` → `All checks passed!`
- `git diff 0704075 -- tests/golden/` → **empty**. The golden fixtures must be
  byte-identical. If any changed, you have altered behavior on inputs the repo
  already pinned — STOP and report.

### Step 6: Confirm the end-to-end CLI fix

Reproduce the original defect scenario to prove the fix reaches the report.

Create a temp bank CSV whose monto cell is `0,50` with a `;` delimiter (matching
`examples/banco_ejemplo.csv`'s format), then:

```bash
PYTHONPATH=src python -m pytest -q   # still green first
```

Better, drive the CLI through the test runner's `CliRunner` (as
`tests/test_e2e_cli.py` does) rather than by hand, and assert the run **fails
closed** with a non-zero exit and a message mentioning the ambiguous amount. Add
this as a test in `tests/test_parsing.py`? No — it belongs with the CLI tests, but
`tests/test_e2e_cli.py` is **out of scope**. Instead assert the parser-level
contract only (Step 3) and verify the CLI path manually via `CliRunner` in a
throwaway script under `/tmp`, not committed.

**Verify**: the throwaway script prints a non-zero exit code and an error message
naming `0,50`. Do not commit that script.

## Test plan

- **New tests in `tests/test_parsing.py`**: the full decision table from Step 3,
  table-driven via `pytest.mark.parametrize`.
- **New tests in `tests/test_property_parsing.py`**: two Hypothesis properties
  (thousands round-trip; accounting-negative sign symmetry).
- **Pattern to follow**: the existing contents of both files. Read them first.
- **Regression this pins**: `0,50` must never again become `50`, and `(1.234,56)`
  must never again become positive.
- Verification: `python -m pytest -q` → all pass, including the goldens, which
  must be **unchanged**.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -m pytest -q` exits 0
- [ ] `python -m pytest tests/test_parsing.py tests/test_property_parsing.py -q` exits 0
- [ ] `python -m black --check src tests tools` exits 0
- [ ] `python -m ruff check src tests tools` exits 0
- [ ] `git diff 0704075 -- tests/golden/` is **empty** (goldens unchanged)
- [ ] `git diff --name-only 0704075...HEAD` lists only the three in-scope files
      and `plans/README.md`
- [ ] A test asserts `parse_monto_clp("0,50")` raises `ErrorParseo`
- [ ] A test asserts `parse_monto_clp("(1.234,56)") == Decimal(-1235)`
- [ ] A test asserts `parse_monto_clp("1.234") == Decimal(1234)` (regression guard
      for the pre-existing correct case)
- [ ] `plans/README.md` status row updated to DONE

## STOP conditions

Stop and report back (do not improvise) if:

- Any Step 0 command fails on the unmodified checkout.
- **Any file under `tests/golden/` changes.** That means the fix altered behavior
  on inputs the repo already pinned, which means the policy is wrong, not the
  golden.
- A golden dataset in `tests/golden/datasets/` turns out to contain a
  single-separator amount that **currently parses correctly by accident**. Report
  it — the maintainer must decide, not you.
- You believe rejecting `0,50` is wrong and want to round it instead. That is a
  policy decision, not an implementation detail: report it with the reasoning
  rather than choosing.
- The fix appears to require touching an adapter or a model.
- A verification command fails twice after a reasonable fix attempt.

## Maintenance notes

- The 3-digit-group rule (`1.234` → `1234`) is what keeps existing Chilean
  statements working. If a future client sends `1.234` meaning 1.23, that is a
  data problem the run should surface — do not add a heuristic to guess it.
- Rounding stays `Decimal`'s default (half-even) exactly as before. Changing it
  later changes every amount in the report; it needs its own decision.
- A reviewer should scrutinize: (a) that the accounting-negative path is applied
  *before* the character-class strip, not after; (b) that no `float` crept in;
  (c) that the goldens are untouched.
- This is a **behavior change for any client currently feeding centavos**. It
  belongs in `CHANGELOG.md` under `## [Unreleased]`, which currently sits
  mid-file at `CHANGELOG.md:19` and must be **moved to the top** (above the
  `0.2.14` heading at `:5`) before you add to it — otherwise
  `tools/bump_changelog.py` will mis-split the file on the next release. Make
  that move and the entry in one edit; do not run the bump tool.
- **Deferred**: the same function is used by all three adapters, and a caller
  could still pass an already-ambiguous value from a non-CLP currency. Enforcing
  `moneda != CLP` has no decimals would be the next step; unblocked by nothing,
  it needs the currency to be validated at ingestion first, which is a separate
  finding.
