from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

from conciliador_bancario import __version__ as CORE_VERSION
from conciliador_bancario.cli import app
from typer.testing import CliRunner

_RUN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_OBJ_ID_RE = re.compile(r"^[MH]-[0-9a-f]{14}$")


def _normalize_run_json(payload: dict) -> dict:
    obj = deepcopy(payload)
    obj.pop("run_id", None)

    matches = []
    for m in obj.get("matches", []):
        m = dict(m)
        m.pop("id", None)
        m["transacciones_bancarias"] = sorted(m.get("transacciones_bancarias", []))
        m["movimientos_esperados"] = sorted(m.get("movimientos_esperados", []))
        matches.append(m)
    obj["matches"] = sorted(
        matches,
        key=lambda m: (
            m.get("regla", ""),
            ",".join(m.get("transacciones_bancarias", [])),
            ",".join(m.get("movimientos_esperados", [])),
            m.get("estado", ""),
            float(m.get("score", 0.0)),
            m.get("explicacion", ""),
        ),
    )

    hallazgos = []
    for h in obj.get("hallazgos", []):
        h = dict(h)
        h.pop("id", None)
        hallazgos.append(h)
    obj["hallazgos"] = sorted(
        hallazgos,
        key=lambda h: (
            h.get("entidad", ""),
            h.get("entidad_id") or "",
            h.get("tipo", ""),
            h.get("severidad", ""),
            h.get("mensaje", ""),
            json.dumps(h.get("detalles", {}), sort_keys=True, ensure_ascii=True),
        ),
    )
    return obj


def _assert_run_ids_well_formed(got: dict) -> None:
    assert _RUN_ID_RE.match(got.get("run_id", "")), f"run_id invalido: {got.get('run_id')!r}"

    match_ids = [m.get("id") for m in got.get("matches", [])]
    assert all(isinstance(mid, str) and _OBJ_ID_RE.match(mid) for mid in match_ids), match_ids
    assert len(match_ids) == len(set(match_ids)), "IDs de match duplicados (invariante)"

    hallazgo_ids = [h.get("id") for h in got.get("hallazgos", [])]
    assert all(isinstance(hid, str) and _OBJ_ID_RE.match(hid) for hid in hallazgo_ids), hallazgo_ids
    assert len(hallazgo_ids) == len(set(hallazgo_ids)), "IDs de hallazgo duplicados (invariante)"


def test_golden_examples_run_json(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "out"
    out.mkdir()

    res = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(Path("examples") / "config_cliente.yaml"),
            "--bank",
            str(Path("examples") / "banco_ejemplo.xml"),
            "--expected",
            str(Path("examples") / "movimientos_esperados.csv"),
            "--out",
            str(out),
            "--dry-run",
        ],
    )
    assert res.exit_code == 0, res.stdout

    got = json.loads((out / "run.json").read_text(encoding="utf-8"))
    expected = json.loads(
        (Path("tests") / "golden" / "examples_run.json").read_text(encoding="utf-8")
    )
    _assert_run_ids_well_formed(got)
    assert got["fingerprint"]["version"] == CORE_VERSION
    expected["fingerprint"]["version"] = CORE_VERSION
    assert _normalize_run_json(got) == _normalize_run_json(expected)
