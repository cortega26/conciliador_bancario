# Plan 003: Reject duplicate transaction/expected IDs at ingestion

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 0704075..HEAD -- src/conciliador_bancario/ingestion/base.py src/conciliador_bancario/ingestion/csv_adapter.py src/conciliador_bancario/ingestion/xlsx_adapter.py src/conciliador_bancario/pipeline.py tests/test_invalid_inputs_fail_closed.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: plans/001-characterize-fail-closed-branches.md
- **Category**: bug
- **Planned at**: commit `0704075`, 2026-09-28

## Why this matters

A repeated `id` in the expected-movements file makes one row disappear from the
reconciliation entirely — not as a flagged discrepancy, but as *nothing*. It is
absent from every match, absent from `run.json`, and never becomes a finding,
because the engine suppresses the `pendiente_esperado` hallazgo once that id is
already consumed. `concilia run` exits 0 and reports success.

Reproduced at `0704075`: two rows both carrying `EXP-001` (150.000 and 999.000
CLP) produced one match, **zero** `pendiente_esperado` findings, and a `run.json`
in which the 999.000 CLP movement has no representation at all. The accountant
sees a clean reconciliation that is missing a real liability.

`AGENTS.md` requires "cero errores silenciosos" and fail-closed behavior. A row
vanishing is the worst possible failure of that rule.

## Current state

Identity is a `set[str]` on both sides of the engine, and nothing validates that
incoming ids are unique.

```python
# src/conciliador_bancario/matching/engine.py:147-148
used_tx: set[str] = set()
used_exp: set[str] = set()
```

```python
# src/conciliador_bancario/matching/engine.py:395-396
for exp in esperados:
    if exp.id not in used_exp:          # <-- second EXP-001 lands here, no hallazgo
```

The expected-id derivation returns the file's `id` column verbatim, un-namespaced
and unchecked:

```python
# src/conciliador_bancario/ingestion/csv_adapter.py:74-77
def _id_exp(path: Path, fila: int, data_norm: dict[str, Any], id_externo: str | None) -> str:
    if id_externo and str(id_externo).strip():
        return str(id_externo).strip()          # <-- file-controlled, unvalidated
    return "EXP-" + sha256_json_estable({"file": path.name, "row": fila, "data": data_norm})[:12]
```

Same hole at `src/conciliador_bancario/ingestion/xlsx_adapter.py:313`
(`exp_id = id_ext if id_ext else _id(...)`).

The only existing invariant check inspects ids *inside matches*
(`core/contracts/run_schema.py:76-92`) — it never checks uniqueness of the input.

- `src/conciliador_bancario/ingestion/base.py` — 33 lines, holds `ErrorIngestion`
  and the ingestion-side base types. This is where a shared uniqueness check
  belongs.
- `src/conciliador_bancario/ingestion/csv_adapter.py:268-334` — the expected-rows
  loop, where rows are appended to `out` at `:324`.
- `src/conciliador_bancario/ingestion/xlsx_adapter.py` — the parallel expected-rows
  loop; read it to find the equivalent `out.append`.
- `src/conciliador_bancario/pipeline.py:264-266` — ingestion and normalization,
  the natural place for a whole-batch assertion.
- `tests/test_invalid_inputs_fail_closed.py` — 30 lines, the home for a
  fail-closed ingestion test.

### Conventions to match

- `ErrorIngestion` (from `ingestion/base.py`) is the exception every adapter
  raises for bad input. It is caught in `cli/errors.py:52-78` and maps to exit
  code 4 with category `ingestion`. Use it — do not invent a new exception.
- All messages are **Spanish, unaccented**. Adapters prefix row context as
  `f"Fila {i}: ..."`. Match that.
- `ingestion/limits.py` is the exemplar for how this repo writes a check that
  both **fails closed and audits**: it takes an `audit: JsonlAuditWriter` and
  writes an `AuditEvent` before raising (`limits.py:17-34`). Follow that shape.
- The adapters take `audit: JsonlAuditWriter` as a required keyword argument and
  already write `AuditEvent`s for delimiter detection (`csv_adapter.py:92-96`).

### Design decision: raise, or emit a finding?

Both are defensible; pick the one the repo's rules force.

- Raising `ErrorIngestion` **fails the whole run**. A user with one duplicated id
  in a 5.000-row export gets nothing, and must fix the file before seeing any
  reconciliation.
- Emitting a finding and dropping the row **produces a usable reconciliation**
  with the anomaly visible.

`AGENTS.md` says "Fail-closed siempre: ante duda o ambigüedad, **NO conciliar**" —
but it also says errors must be "explícitos (excepción/hallazgo) y visibles en
reportes", naming *either* mechanism. And the whole product premise is that an
accountant reviews findings; a run that dies on a data-quality issue is a worse
product than a run that flags it.

**Chosen policy: emit a finding and drop the duplicate row, with an audit event.**
This keeps the run usable while making the anomaly impossible to miss. The dropped
row is reported by id and by source row number.

**Exception**: if the duplicate arises from a *generated* id (the `EXP-<hash>`
path, meaning the file had no `id` column), that is effectively impossible because
the hash covers the row number — but if it ever happens it indicates a hash
collision and **must raise** rather than be dropped. Handle both branches
differently and say why in a comment.

## Commands you will need

| Purpose | Command | Provenance | Expected on success |
|---------|---------|------------|---------------------|
| Install | `pip install -e ".[dev]"` | declared | exit 0 |
| Tests | `python -m pytest -q` | executed | 63 passed, 0 failed |
| Format | `python -m black --check src tests tools` | executed | 65 files unchanged |
| Lint | `python -m ruff check src tests tools` | executed | All checks passed |
| Goldens | `python -m pytest tests/test_golden_datasets.py tests/test_golden_examples.py -q` | executed | all pass |

`Install` is `declared`; the rest were run at `0704075` and passed.

## Scope

**In scope** (the only files you may modify):
- `src/conciliador_bancario/ingestion/base.py`
- `src/conciliador_bancario/ingestion/csv_adapter.py`
- `src/conciliador_bancario/ingestion/xlsx_adapter.py`
- `src/conciliador_bancario/pipeline.py`
- `tests/test_invalid_inputs_fail_closed.py`
- `tests/test_e2e_cli.py` (only to add a fail-closed test — see Out of scope
  caveat below)

**Out of scope** (do NOT touch, even though they look related):
- `src/conciliador_bancario/matching/engine.py` — the fix belongs at the
  ingestion boundary, where the bad data enters. Changing the engine to defend
  against malformed input would put a band-aid on the wrong layer.
- `src/conciliador_bancario/models.py` — do not add a `Field` validator for
  uniqueness; a Pydantic validator cannot see across sibling rows.
- The `xml_adapter.py`, `pdf_text_adapter.py`, `pdf_ocr_adapter.py` — their ids
  are all generated from a hash over a row index, so they cannot collide from
  input. Extending the check to them is harmless but unnecessary; leave them.
- `tests/golden/**` — no golden fixture contains duplicate ids, so none should
  change. If one does, that is a STOP condition.

## Git workflow

- Branch: `advisor/003-reject-duplicate-ids`
- Conventional Commits, matching `git log --oneline -20`. Suggested:
  `fix(ingestion): surface duplicate expected ids as a finding`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 0: Establish a green baseline

Run the `Tests`, `Format`, `Lint`, and `Goldens` rows unmodified.

- All pass → proceed to Step 1.
- Any fails → **STOP and report** with the command and exact output.

**Verify**: `python -m pytest -q` → `63 passed`.

### Step 1: Add a test that reproduces the vanishing row

Read `tests/test_invalid_inputs_fail_closed.py` in full first. Add a test that
writes a temp expected-CSV with two rows sharing `id` and asserts the row is
**visible**. Today it is not, so the test must fail.

Target behavior to assert:
- the run **succeeds** (exit 0 — the chosen policy is finding, not failure), and
- `run.json`'s `hallazgos` contains an entry whose `tipo` names the duplicate
  condition, carrying both offending row numbers and the shared id.

Choose the `tipo` string yourself, but make it Spanish, unaccented, and
self-describing — e.g. `id_duplicado_esperado`. The test asserts the value you
chose.

Also assert the **first** occurrence still reconciles normally, so the fix does
not over-reject.

**Verify**: `python -m pytest tests/test_invalid_inputs_fail_closed.py -q` → the
new test FAILS. If it passes, you have not reproduced the defect.

### Step 2: Add the shared uniqueness helper

In `src/conciliador_bancario/ingestion/base.py`, add a small function, e.g.

```python
def validar_ids_unicos(items: Sequence[_T], *, id_attr: str, audit: JsonlAuditWriter, label: str) -> list[_T]:
    ...
```

Behavior:
- Walk `items` in order, keeping a `set` of seen ids.
- On a repeat, **skip** the later row and record `(id, index)` in a list.
- Emit **one** `AuditEvent` of type `"ingestion"` summarizing the duplicates
  (ids + row indices) — one event per file, not one per duplicate row, so a file
  with 1.000 duplicates does not write 1.000 events.
- Return the de-duplicated list.
- If the id looks **generated** (starts with the adapter's id prefix — `EXP-`),
  raise `ErrorIngestion` instead of dropping, per the design decision above.

`base.py` currently does **not** import from `audit`. Adding that import is fine
(`ingestion/csv_adapter.py` already imports both `base` and `audit`), but check
it does not create a cycle: `audit/audit_log.py` imports nothing from `ingestion`,
so `ingestion → audit` is already the established direction. Verify with
`python -c "import conciliador_bancario.ingestion.base"`.

Type annotations are **required** on every function in `src/` — `pyproject.toml:110`
sets `disallow_untyped_defs`. This is a real constraint, not advisory.

**Verify**: `python -c "import conciliador_bancario.ingestion.base"` → exit 0.
`python -m ruff check src` → `All checks passed!`.

### Step 3: Call the helper from the CSV expected loader

In `cargar_movimientos_esperados_csv` (`csv_adapter.py`, the `out.append(...)` at
`:324` inside the row loop), after the loop completes, call the helper on `out`
and replace the result. Pass the existing `audit` kwarg through.

Do the same for the **bank** transaction loader in the same file. Bank ids are
`TX-<hash of file+row+data>` so they cannot collide from input, but running the
check is free and defends against a future id scheme that is file-controlled.
Note in a comment why bank ids are structurally safe.

**Verify**: `python -m pytest tests/test_invalid_inputs_fail_closed.py -q` → the
Step 1 test now PASSES.

### Step 4: Call the helper from the XLSX expected loader

Read `xlsx_adapter.py` and find its expected-rows loop (the parallel to
`csv_adapter.py:324`, with `exp_id = id_ext if id_ext else _id(...)` at `:313`).
Apply the same call. This adapter has the **identical** hole, and leaving it would
mean the fix only holds for CSV.

Note: `xlsx_adapter.py` is close to a line-for-line duplicate of `csv_adapter.py`.
Match the existing structure rather than refactoring it — consolidating the two
adapters is explicitly out of scope.

**Verify**: add one XLSX equivalent of the Step 1 test, or extend it
table-driven over both `csv` and `xlsx`. `python -m pytest -q` → all pass.

### Step 5: Add the whole-batch assertion in the pipeline

At `src/conciliador_bancario/pipeline.py:266` (after `normalizar_lote`), assert
the post-normalization batch is unique. This is defense in depth: normalization
could in principle alter ids. On failure, raise `ErrorIngestion` — normalization
happens after the adapters, so at this point a duplicate is a genuine internal
defect, and failing closed is correct.

Keep it cheap (two `set` constructions and a length compare). Do not add it to
`run_schema.py`'s validator, which operates on the already-serialized payload.

**Verify**: `python -m pytest -q` → all pass.

### Step 6: Verify the full gate

**Verify**:
- `python -m pytest -q` → all pass (63 + your additions)
- `python -m black --check src tests tools` → all unchanged
- `python -m ruff check src tests tools` → `All checks passed!`
- `git diff 0704075 -- tests/golden/` → **empty**

### Step 7: Confirm the CLI end-to-end

Drive `CliRunner` from a throwaway script under `/tmp` (not committed) with a
duplicate-id expected CSV. Assert: exit code 0, one duplicate finding present, the
999.000 CLP row's amount **visible somewhere** in `run.json`.

**Verify**: the script prints the finding's `tipo` and the surviving match. Do not
commit the script.

## Test plan

- **New tests in `tests/test_invalid_inputs_fail_closed.py`**: duplicate expected
  id via CSV raises a visible finding and the first occurrence still reconciles;
  the same via XLSX.
- **Pattern to follow**: the existing contents of that file, and the `CliRunner`
  usage in `tests/test_e2e_cli.py`.
- **Regression pinned**: a duplicated id can never again produce zero findings for
  that id.
- Verification: `python -m pytest -q` → all pass, goldens unchanged.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -m pytest -q` exits 0
- [ ] `python -m black --check src tests tools` exits 0
- [ ] `python -m ruff check src tests tools` exits 0
- [ ] `git diff 0704075 -- tests/golden/` is **empty**
- [ ] `git diff --name-only 0704075...HEAD` lists only the in-scope files and
      `plans/README.md`
- [ ] A test asserts a duplicate expected id produces a visible finding
- [ ] Both `csv_adapter.py` and `xlsx_adapter.py` call the new helper
- [ ] `python -c "import conciliador_bancario.ingestion.base"` exits 0
- [ ] `plans/README.md` status row updated to DONE

## STOP conditions

Stop and report back (do not improvise) if:

- Any Step 0 command fails on the unmodified checkout.
- Any file under `tests/golden/` changes.
- The duplicate cannot be reproduced in Step 1 — the test passing immediately
  means the finding is wrong. Report, do not proceed.
- You conclude the fix belongs in `matching/engine.py` instead of at ingestion.
  Report the reasoning; do not move it there unilaterally.
- A real client's data turns out to legitimately contain duplicate external ids
  (e.g. a supplier reusing an invoice number across months). That is a policy
  question — the chosen policy may need a config escape hatch. Report it.
- The fix appears to require touching a file outside the in-scope list.

## Maintenance notes

- The de-duplication is **drop-with-finding**, not reject. A future maintainer
  reading only the code must be able to see that a row was intentionally dropped;
  keep the audit event and a clear comment.
- If id generation ever changes so that bank `TX-` ids become file-controlled,
  the Step 3 comment becomes wrong — update it.
- A reviewer should scrutinize the CSV and XLSX paths being genuinely symmetric;
  the two adapters have diverged before (`xlsx_adapter._campo` hardcodes
  `0.90` while `csv_adapter._campo` derives it from a table), and a one-sided fix
  is the exact failure mode here.
- This does **not** address the separate finding that `_id_tx` uses different hash
  key names across adapters (`{"file","row","data"}` vs `{"file","idx","data"}`),
  which makes the same statement get different ids depending on format. That is a
  cross-format contract change, deliberately excluded.
- **Deferred**: a `CHANGELOG.md` entry under `## [Unreleased]`, which currently
  sits mid-file at `CHANGELOG.md:19` and must be **moved above** the `0.2.14`
  heading at `:5` first, or `tools/bump_changelog.py` mis-splits on the next
  release. Same constraint as plan 002.
