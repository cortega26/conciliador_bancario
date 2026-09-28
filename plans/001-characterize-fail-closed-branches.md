# Plan 001: Characterize the untested fail-closed matching branches

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 0704075..HEAD -- src/conciliador_bancario/matching/engine.py tests/test_matching_policy.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `0704075`, 2026-09-28

## Why this matters

`src/conciliador_bancario/matching/engine.py` makes the two most consequential
money decisions this tool can make: "a reference matches but the amount differs →
do **not** reconcile, escalate as `critica`", and "two expected movements share one
reference → do **not** reconcile". Both behaviors have **zero test coverage** and
appear in **none of the six golden fixtures**. Any refactor of the engine can
invert them and leave the suite fully green.

Four later plans (002, 003, 008, 009) change exactly this code. This plan is their
safety net and must land first.

## Current state

- `src/conciliador_bancario/matching/engine.py` (450 lines) — the matching engine.
  `conciliar()` is at line 125. The three untested branches:
  - `engine.py:168-192` — `ambiguedad_referencia` (a reference shared by >1
    expected movement). Note it **does** write an audit event at `:185-191`.
  - `engine.py:197-232` — `referencia_coincide_monto_difiere`, severity
    `SeveridadHallazgo.critica`. This is the **only** `critica` emitter in the
    whole codebase. Also writes an audit event at `:225-231`.
  - `engine.py:376-393` — `pendiente_banco` (a bank movement with no match).
    Also writes an audit event at `:387-393`.
- `tests/test_matching_policy.py` (111 lines) — the engine's only test file. It has
  exactly two tests: `test_pdf_ocr_no_autoconcilia_aun_con_ref` and
  `test_fail_closed_si_ambiguedad_monto_fecha`.
- `tests/golden/*_run.json` — six golden fixtures. Their `hallazgos` only ever
  contain `tx_con_match` and `pendiente_esperado`, at severities `info` and
  `advertencia` only.

Verification that the gap is real:

```bash
grep -rn "ambiguedad_referencia\|referencia_coincide_monto_difiere\|pendiente_banco" tests/
# returns nothing
```

### Conventions to match

Read `tests/test_matching_policy.py` in full before writing. The established
pattern, which you must follow:

- Module-level helpers `_campo(valor, score, origen)` build `CampoConConfianza`;
  `MetadataConfianza` is built inline when a shared instance is reused.
- `conciliar()` is called directly with `audit=NullAuditWriter()` and
  `run_id="..."` (a fixed literal).
- The call is annotated with `# type: ignore[arg-type]` because `NullAuditWriter`
  and `JsonlAuditWriter` are unrelated types. **Keep this comment** — it is
  load-bearing, and `mypy` is not in CI but the annotation documents the seam.
- Assertions are plain `assert` on `res.matches` / `res.hallazgos`, including
  `any(h.tipo == "..." for h in res.hallazgos)`.
- Every test is `def test_...() -> None:` — the return annotation is required by
  `pyproject.toml:110` (`disallow_untyped_defs`).
- Files start with `from __future__ import annotations`.
- The repo uses `__import__("datetime").date(...)` in places; a plain
  `from datetime import date` import is cleaner and also acceptable. Prefer the
  explicit import.

## Commands you will need

| Purpose | Command | Provenance | Expected on success |
|---------|---------|------------|---------------------|
| Install | `pip install -e ".[dev]"` | declared | exit 0 |
| Tests | `python -m pytest -q` | executed | 63 passed, 0 failed |
| Tests (this file) | `python -m pytest tests/test_matching_policy.py -q` | executed | 2 passed at baseline |
| Format | `python -m black --check src tests tools` | executed | 65 files unchanged |
| Lint | `python -m ruff check src tests tools` | executed | All checks passed |

The `Tests`, `Format`, and `Lint` rows were each run by the plan author against
commit `0704075` and passed. `Install` is `declared` (read from `ci.yml:29`);
if the environment already has the dependencies, skip it.

## Scope

**In scope** (the only files you may modify):
- `tests/test_matching_policy.py`

**Out of scope** (do NOT touch, even though they look related):
- `src/conciliador_bancario/matching/engine.py` — this plan adds tests only. If
  you believe the engine is wrong, that is a STOP condition, not a fix.
- `tests/golden/*.json` — the golden fixtures are not updated by this plan. They
  do not cover these branches, so they must not change.
- The other 19 test files. If you believe a new test belongs elsewhere, keep it
  here; `test_matching_policy.py` is the engine's home.

## Git workflow

- Branch: `advisor/001-characterize-fail-closed-branches`
- One commit, message style matching the repo's history
  (`git log --oneline -20` shows Conventional Commits, e.g.
  `build(deps): Bump pypdf in the pip group across 1 directory`,
  `fix(release): handle merge-tag file detection in verify_release_tag`).
  Use: `test(matching): characterize fail-closed branches`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 0: Establish a green baseline

Run the `Tests`, `Format`, and `Lint` rows on the unmodified checkout.

- If all pass: record that and proceed to Step 1.
- If any fails: the repo drifted since this plan was written. **STOP and report**
  it with the command and its exact output. Do not fix the build to get moving,
  and do not proceed against a red baseline.

**Verify**: `python -m pytest -q` → `63 passed`.

### Step 1: Add the three characterization tests

Append three test functions to `tests/test_matching_policy.py`. They must be
**table-driven or plain functions** in the style of the existing two — pick plain
functions, one per branch, as they read better here.

**Test 1 — `test_fail_closed_si_ambiguidad_de_referencia`**

Covers `engine.py:168-192`. Build: one bank tx and **two** expected movements that
share the same `referencia` value (e.g. both `"FAC-1001"`) but have different
`monto`. Assert:

- `res.matches == []`
- exactly one hallazgo with `tipo == "ambiguedad_referencia"`
- that hallazgo has `severidad == SeveridadHallazgo.advertencia`
- `halazgo.entidad == "banco"` and `halazgo.entidad_id` is the tx id
- `halazgo.detalles` contains the key `"candidatos"` listing **both** expected ids

Import `SeveridadHallazgo` from `conciliador_bancario.models` (it is not
currently imported in this test file — add it to the existing import block, keep
the block alphabetically sorted, which is what ruff's `I` rule enforces).

**Test 2 — `test_referencia_coincide_monto_difiere_es_critica`**

Covers `engine.py:197-232`. Build: one bank tx and one expected movement with the
**same** `referencia` but **different** `monto` (e.g. tx `150000`, exp
`140000`). Assert:

- `res.matches == []`
- exactly one hallazgo with `tipo == "referencia_coincide_monto_difiere"`
- `severidad == SeveridadHallazgo.critica`
- `detalles` contains `"monto_tx"` and `"monto_exp"` with the correct values

This is the highest-value test in the plan: it pins the only `critica` path in the
codebase. Name it so the intent is unmistakable.

**Test 3 — `test_transaccion_banco_sin_match_queda_pendiente`**

Covers `engine.py:376-393`. Build: one bank tx and **zero** expected movements
(`esperados=[]`). Assert:

- `res.matches == []`
- exactly one hallazgo with `tipo == "pendiente_banco"`
- `severidad == SeveridadHallazgo.advertencia`
- `entidad == "banco"`, `entidad_id == ` the tx id

This also pins the asymmetric accounting: a bank row is either matched or
explicitly flagged, never silently dropped.

**Verify**: `python -m pytest tests/test_matching_policy.py -q` → `5 passed`
(2 pre-existing + 3 new).

### Step 2: Confirm the tests actually fail if the invariant is inverted

A characterization test that cannot fail is worthless. Temporarily break the
engine, confirm the new test goes red, then restore it exactly.

- In `engine.py:216-223`, temporarily change
  `severidad=SeveridadHallazgo.critica` to `severidad=SeveridadHallazgo.info`
  and run `python -m pytest tests/test_matching_policy.py -q` → test 2 MUST fail.
- Restore the line to `SeveridadHallazgo.critica` **exactly** as it was.

**Verify**: `git diff --stat src/conciliador_bancario/matching/engine.py` → **empty
output**. The engine must be byte-identical to how you found it.

### Step 3: Verify the full gate

**Verify**:
- `python -m pytest -q` → `66 passed, 0 failed`
- `python -m black --check src tests tools` → `66 files would be left unchanged`
  (one more than the 65 at baseline)
- `python -m ruff check src tests tools` → `All checks passed!`

## Test plan

- **What this plan adds**: 3 tests in `tests/test_matching_policy.py`, one per
  untested fail-closed branch. No source change at all.
- **Cases covered**: reference ambiguity, reference-match/amount-mismatch
  (the `critica` path), orphan bank row.
- **Pattern followed**: the two existing tests in the same file.
- **Not covered here** (deliberately): `tx_con_match`, `pendiente_esperado`, and
  the ingestion-limit paths all already have coverage elsewhere.
- Verification: `python -m pytest -q` → 66 passed, up from 63.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -m pytest -q` exits 0 with 66 passed
- [ ] `python -m pytest tests/test_matching_policy.py -q` exits 0 with 5 passed
- [ ] `python -m black --check src tests tools` exits 0
- [ ] `python -m ruff check src tests tools` exits 0
- [ ] `git diff --name-only 0704075...HEAD` lists only
      `tests/test_matching_policy.py` and `plans/README.md`
- [ ] `git diff 0704075 -- src/conciliador_bancario/matching/engine.py` is **empty**
- [ ] `git diff 0704075 -- tests/golden/` is **empty**
- [ ] `plans/README.md` status row updated to DONE

## STOP conditions

Stop and report back (do not improvise) if:

- Any Step 0 command fails on the unmodified checkout.
- The engine code at `engine.py:168-232` or `:376-393` does not match the
  behavior described above (the codebase has drifted).
- Any of the three new tests passes **before** you make the Step 2 temporary
  break — that means the test is not pinning what you think it is.
- A test requires touching a file outside `tests/test_matching_policy.py`.
- You find that one of these branches genuinely does not fire (e.g. rule 1 always
  takes the amount check first). That is a real engine finding, not something to
  work around — report it.

## Maintenance notes

- These tests are **characterization** tests: they pin today's behavior so that
  plans 002/003/008/009 can change it deliberately and reviewably. If a later
  change to the engine legitimately alters one of these behaviors, update the test
  in the same PR and say why in the commit message. Do not weaken an assertion to
  make a suite pass.
- The `critica` severity assertion is the single most important line in this
  plan. If someone later adds a second `critica` emitter, keep this test pinned to
  its `tipo`, not to a count of `critica` hallazgos.
- A reviewer should scrutinize Step 2's negative check: the value of this plan is
  entirely in whether the tests can actually go red.
- **Deferred**: the `ambiguedad_monto_fecha` and `tx_con_match` branches at
  `engine.py:293-308` and `:364-374` are exercised by existing tests for the
  former, but neither writes an `audit.write` event while their siblings do. That
  audit gap is a separate finding; unblocked by nothing, it just was not worth
  mixing into a tests-only plan.
