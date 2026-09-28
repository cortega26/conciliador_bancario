# Plan 004: Make `audit.jsonl` run-scoped so `seq` is a valid trace key

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 0704075..HEAD -- src/conciliador_bancario/audit/audit_log.py src/conciliador_bancario/pipeline.py src/conciliador_bancario/cli/errors.py tests/test_audit_contract.py tests/test_ux_contracts_cli.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `0704075`, 2026-09-28

## Why this matters

Running the identical command twice into the same `--out` produces a
byte-identical `run.json` but an `audit.jsonl` that **doubles**, with `seq`
**repeating**. Measured at `0704075`:

```
run 1: run.json sha=6290c7dc6bd1  audit.jsonl lines=5   seq=[0,1,2,3,4]
run 2: run.json sha=6290c7dc6bd1  audit.jsonl lines=10  seq=[0,1,2,3,4,0,1,2,3,4]
```

So `seq` is not a unique key, the audit trail is not a deterministic function of
the inputs, and the two runs are indistinguishable in the durable artifact. That
directly contradicts the README's core promise ("misma entrada → mismo `run.json`
(sin timestamps variables)") and `mvp_checklist.md:21` ("`audit.jsonl` incluye
`run_id` y `seq` (trazabilidad y determinismo)").

The trail exists so a reviewer can reconstruct what the tool decided. Two runs
that look identical in every respect except the volume of the file defeat that.

## Current state

The writer appends and restarts its counter per instance:

```python
# src/conciliador_bancario/audit/audit_log.py:17-41
class JsonlAuditWriter:
    def __init__(self, path: Path, *, run_id: str | None = None) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._run_id = run_id
        self._seq = 0                                  # <-- restarts at 0 every run

    def write(self, event: AuditEvent) -> None:
        payload: dict[str, Any] = {
            "seq": self._seq,
            "tipo": event.tipo,
            "mensaje": event.mensaje,
            "detalles": event.detalles,
        }
        if self._run_id is not None:
            payload["run_id"] = self._run_id
        line = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._path.open("a", encoding="utf-8") as f:   # <-- appends
            f.write(line + "\n")
        self._seq += 1
```

`run.json`, by contrast, is written truncating:

```python
# src/conciliador_bancario/pipeline.py:288-292
run_json.write_text(
    canonical_json_dumps(payload),
    encoding="utf-8",
)
```

The two artifacts disagree on what a re-run into the same directory means. The
writer is constructed per run at `pipeline.py:256`:

```python
audit = JsonlAuditWriter(out_dir / "audit.jsonl", run_id=run_id)
```

There is a second, worse writer. On failure, `cli/errors.py:112` opens the same
path again with **no `run_id` at all**, so a failure line is unattributable in an
otherwise run-scoped file:

- `src/conciliador_bancario/cli/errors.py:104-126` — `emit_failure_audit_best_effort`.

Existing tests: `tests/test_audit_contract.py:10-42` (42 lines) only ever inspects
a **single** run, so this is uncovered. `tests/test_ux_contracts_cli.py:179`
asserts an append-only property across runs — **read it carefully**, because this
plan changes what that assertion means. See "Out of scope" and the STOP
conditions.

## Design decision: truncate, or continue the sequence?

Two options:

- **Truncate on open** (mode `"w"`): each run's trail contains exactly that run.
  `seq` starts at 0 and is a valid key. Deterministic. But it **discards** the
  previous run's trail.
- **Continue the sequence** (keep `"a"`, seed `seq` from the existing line count):
  history is preserved, `seq` stays unique. But the file is still not a
  deterministic function of the inputs — the same input produces a different file
  depending on what ran before, which is the actual bug.

The repo's determinism requirement is explicit and repeated in `AGENTS.md`, the
README, and `mvp_checklist.md`. Preserving cross-run history is a *reporting*
concern, and the correct place for it is the user copying the previous `run_dir`
or using release automation — not a silent default in the writer.

**Chosen policy: truncate when a `run_id` is supplied (run-scoped); keep append
only for the best-effort failure writer.** And give the failure writer the
`run_id` so every line is attributable.

This makes a re-run into the same directory produce a byte-identical
`audit.jsonl` — the same guarantee `run.json` already has.

## Commands you will need

| Purpose | Command | Provenance | Expected on success |
|---------|---------|------------|---------------------|
| Install | `pip install -e ".[dev]"` | declared | exit 0 |
| Tests | `python -m pytest -q` | executed | 63 passed, 0 failed |
| Tests (audit) | `python -m pytest tests/test_audit_contract.py tests/test_ux_contracts_cli.py -q` | executed | all pass |
| Format | `python -m black --check src tests tools` | executed | 65 files unchanged |
| Lint | `python -m ruff check src tests tools` | executed | All checks passed |
| Goldens | `python -m pytest tests/test_golden_datasets.py tests/test_golden_examples.py -q` | executed | all pass |

`Install` is `declared`; the rest were run at `0704075` and passed.

## Scope

**In scope** (the only files you may modify):
- `src/conciliador_bancario/audit/audit_log.py`
- `src/conciliador_bancario/pipeline.py`
- `src/conciliador_bancario/cli/errors.py`
- `tests/test_audit_contract.py`
- `tests/test_ux_contracts_cli.py` (only if Step 2 shows the existing append
  assertion is now wrong — see that step)

**Out of scope** (do NOT touch, even though they look related):
- `src/conciliador_bancario/matching/engine.py` and the adapters — they call
  `audit.write(...)`; the signature is unchanged.
- `NullAuditWriter` — do not "optimize" or restructure it.
- `tests/golden/**` — the goldens compare `run.json`, not `audit.jsonl`. If one
  changes, that is a STOP condition.
- The XLSX report and `run.json` writing. This plan touches the audit trail only;
  atomic writes to the other two artifacts are a separate finding.
- The `open()`-per-event I/O pattern. It is what makes the append-only guarantee
  hold and what limits loss on abnormal termination. **Do not buffer.** See
  "Findings considered and rejected" in `plans/README.md`.

## Git workflow

- Branch: `advisor/004-run-scoped-audit-log`
- Conventional Commits, matching `git log --oneline -20`. Suggested:
  `fix(audit): scope audit.jsonl to a single run`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 0: Establish a green baseline

Run the `Tests`, `Format`, `Lint`, and `Goldens` rows unmodified.

- All pass → proceed to Step 1.
- Any fails → **STOP and report** with the command and exact output.

**Verify**: `python -m pytest -q` → `63 passed`.

### Step 1: Pin the current double-write as a failing test

Read `tests/test_audit_contract.py` in full. Add a test that runs `ejecutar_run`
**twice** into one `tmp_path` and asserts both artifacts are byte-identical and
`seq` is strictly increasing. Today it fails on `audit.jsonl`.

Shape (match the file's existing fixture style — read it first):

```python
def test_re_run_en_mismo_out_dir_reescribe_audit_jsonl(tmp_path: Path) -> None:
    ejecutar_run(config=..., bank=..., expected=..., out_dir=tmp_path, mask=True, dry_run=True, log_level="INFO", enable_ocr=False)
    first = (tmp_path / "audit.jsonl").read_bytes()
    ejecutar_run(...)  # identical arguments
    assert (tmp_path / "audit.jsonl").read_bytes() == first
```

Then also assert `seq` values are `range(0, n)` with no repeats, by parsing each
line as JSON.

**Verify**: `python -m pytest tests/test_audit_contract.py -q` → the new test
FAILS on the second run. If it passes, the finding is not reproducible — STOP.

### Step 2: Read `test_ux_contracts_cli.py:179` and decide

Open `tests/test_ux_contracts_cli.py` and read the test containing line 179 — a
subagent flagged it as asserting an append-only property across runs. Determine
whether it:

- **(a)** asserts `audit.jsonl` *grows* across two runs, or
- **(b)** asserts every line has a `run_id` / the file is well-formed.

If (a), it directly contradicts this plan's chosen policy. Then, and only then,
update that assertion to the new semantics — with a comment explaining that
run-scoped truncation replaced cross-run append, and that history preservation is
now the user's responsibility (copy the `run_dir`). Update the plan's status row
in `plans/README.md` to note the changed assertion.

If (b), leave the file untouched.

Report which case you found either way.

**Verify**: `python -m pytest tests/test_ux_contracts_cli.py -q` → all pass.

### Step 3: Make the writer run-scoped

In `JsonlAuditWriter.__init__`, open with mode `"w"` (truncating) when
`run_id is not None`, and with `"a"` when it is `None`. Keep `self._seq = 0` in
both cases — with truncation, 0 is correct for every run.

Make the truncation **fail-closed**: wrap the open in `try/except OSError` and
re-raise. `pipeline.py:257-262` already catches `OSError` from the constructor
and converts it to a clean `ErrorOperacionIO`, so letting `OSError` propagate is
already the established contract — verify that by reading it.

Add a short Spanish comment stating the invariant: with a `run_id`, the file is
the deterministic, run-scoped trail; without one it is an append-only best-effort
log.

Keep `write()` exactly as it is otherwise. **Do not** add buffering.

**Verify**: `python -m pytest tests/test_audit_contract.py -q` → the Step 1 test
PASSES.

### Step 4: Give the failure writer a `run_id`

At `src/conciliador_bancario/cli/errors.py:104-126`, `emit_failure_audit_best_effort`
constructs a writer with no `run_id`, so its line is unattributable. It cannot
compute the `run_id` itself (that requires the config's sha256), so the fix is to
**pass the `out_dir`'s `run_id` down** where the caller knows it, or — if it
genuinely does not — to stop using the append path and instead write the failure
into a separate, clearly-named file.

`cli/app.py:170` calls it as
`emit_failure_audit_best_effort(out_dir=out, command="run", exc=e)`. Read the
whole of `errors.py` before deciding.

**Whichever route you take**, the requirement is: no line in `audit.jsonl` is
ever written without a `run_id`. If the only clean way is a separate failure file,
that is acceptable — say so in your report and add it to the plan's maintenance
notes.

**Verify**: add a test asserting every line of `audit.jsonl` after a **failed**
run has a `run_id` key.

### Step 5: Verify the full gate

**Verify**:
- `python -m pytest -q` → all pass (63 + your additions)
- `python -m black --check src tests tools` → all unchanged
- `python -m ruff check src tests tools` → `All checks passed!`
- `git diff 0704075 -- tests/golden/` → **empty**

### Step 6: Confirm determinism end-to-end

Drive `CliRunner` from a throwaway script under `/tmp` (not committed), running
`concilia run` twice into one directory with identical arguments. Print the
sha256 of `run.json` and `audit.jsonl` after each run.

**Verify**: both artifacts' sha256 are **identical** across the two runs. Report
the two hashes.

## Test plan

- **New tests in `tests/test_audit_contract.py`**: (1) two identical runs produce
  byte-identical `audit.jsonl`; (2) `seq` is strictly increasing with no repeats;
  (3) every line after a failed run carries a `run_id`.
- **Possible update in `tests/test_ux_contracts_cli.py`**: only if Step 2 finds
  case (a).
- **Pattern to follow**: the existing contents of `tests/test_audit_contract.py`.
- **Regression pinned**: a second run can never append to a prior run's trail.
- Verification: `python -m pytest -q` → all pass, goldens unchanged.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -m pytest -q` exits 0
- [ ] `python -m black --check src tests tools` exits 0
- [ ] `python -m ruff check src tests tools` exits 0
- [ ] `git diff 0704075 -- tests/golden/` is **empty**
- [ ] `git diff --name-only 0704075...HEAD` lists only the in-scope files and
      `plans/README.md`
- [ ] A test runs two identical runs into one `tmp_path` and asserts
      `audit.jsonl` is byte-identical
- [ ] Every line written to `audit.jsonl` has a `run_id` key
- [ ] `plans/README.md` status row updated to DONE

## STOP conditions

Stop and report back (do not improvise) if:

- Any Step 0 command fails on the unmodified checkout.
- Any file under `tests/golden/` changes.
- `tests/test_ux_contracts_cli.py:179` asserts cross-run **growth** and you cannot
  find a reading of it that survives this change. Report before editing.
- You conclude append-across-runs is deliberate product behavior (e.g. a
  documented multi-run trail). That is a policy question the maintainer must
  settle — report it, do not silently change the contract.
- You are tempted to buffer writes for performance. Do not; see Out of scope.
- The fix appears to require touching an adapter or the engine.

## Maintenance notes

- This is a **semantic change to a durable artifact**: re-running into an existing
  `run_dir` now overwrites the prior `audit.jsonl`. That is the intended fix and
  the intended cost, but it belongs in the changelog. `## [Unreleased]` currently
  sits mid-file at `CHANGELOG.md:19` and must be **moved above** the `0.2.14`
  heading at `:5` before adding to it, or `tools/bump_changelog.py` mis-splits on
  the next release. Move and edit in one change; do not run the bump tool.
- A reviewer should scrutinize the `OSError` path: truncation now happens at
  construction, so a permissions failure surfaces *earlier* than before. Confirm
  `pipeline.py:257-262` still produces the intended `ErrorOperacionIO` message.
- If cross-run history is genuinely needed later, the right place is a
  run-directory naming convention (e.g. `out/2026-09-28T.../`) or the release
  tooling — not the writer's default. Do not reintroduce appending.
- **Deferred**: `run.json` and the XLSX report are still written non-atomically
  (`pipeline.py:288-292` and `excel_report.py:194`), so an interrupted run can
  leave a truncated `run.json` that `concilia explain` then rejects as
  "no es JSON valido", and a failed XLSX write leaves a fresh `run.json` beside a
  stale report. Staging both through `*.tmp` + `os.replace` is a separate plan;
  it needs fault-injection tests and is unblocked by nothing but should not ride
  along here.
