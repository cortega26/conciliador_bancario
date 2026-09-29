from __future__ import annotations

import json
from pathlib import Path

from conciliador_bancario.cli import app
from typer.testing import CliRunner


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_e2e_run_csv(tmp_path: Path) -> None:
    cfg = tmp_path / "config_cliente.yaml"
    bank = tmp_path / "banco.csv"
    exp = tmp_path / "esperados.csv"
    out = tmp_path / "out"
    out.mkdir()

    _write(
        cfg,
        "\n".join(
            [
                "cliente: 'Cliente Test'",
                "rut_mask: '***123'",
                "ventana_dias_monto_fecha: 3",
                "umbral_autoconcilia: 0.85",
                "umbral_confianza_campos: 0.80",
                "permitir_ocr: false",
                "mask_por_defecto: true",
                "moneda_default: 'CLP'",
                "",
            ]
        ),
    )
    _write(
        bank,
        "\n".join(
            [
                "fecha_operacion,fecha_contable,monto,moneda,descripcion,referencia,cuenta",
                "05/01/2026,05/01/2026,150.000,CLP,Transferencia a ACME,FAC-1001,123456789012",
                "06/01/2026,06/01/2026,-250000,CLP,Pago nomina enero,NOM-ENE,123456789012",
                "",
            ]
        ),
    )
    _write(
        exp,
        "\n".join(
            [
                "id,fecha,monto,moneda,descripcion,referencia,tercero",
                "EXP-001,2026-01-05,150000,CLP,Pago proveedor ACME,FAC-1001,ACME Ltda",
                "EXP-002,2026-01-06,-250000,CLP,Pago remuneraciones,NOM-ENE,RRHH",
                "",
            ]
        ),
    )

    runner = CliRunner()
    r = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(cfg),
            "--bank",
            str(bank),
            "--expected",
            str(exp),
            "--out",
            str(out),
            "--dry-run",
        ],
    )
    assert r.exit_code == 0, r.stdout
    assert (out / "run.json").exists()
    assert (out / "audit.jsonl").exists()

    data = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert "run_id" in data
    assert len(data["matches"]) >= 2


def test_idempotencia_run_id(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "exp.csv"
    _write(
        cfg, "cliente: 'X'\npermitir_ocr: false\nmask_por_defecto: true\nmoneda_default: 'CLP'\n"
    )
    _write(
        bank,
        "fecha_operacion,monto,descripcion\n05/01/2026,1000,TEST\n",
    )
    _write(exp, "fecha,monto,descripcion\n05/01/2026,1000,TEST\n")
    out1 = tmp_path / "o1"
    out2 = tmp_path / "o2"
    out1.mkdir()
    out2.mkdir()

    r1 = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(cfg),
            "--bank",
            str(bank),
            "--expected",
            str(exp),
            "--out",
            str(out1),
            "--dry-run",
        ],
    )
    r2 = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(cfg),
            "--bank",
            str(bank),
            "--expected",
            str(exp),
            "--out",
            str(out2),
            "--dry-run",
        ],
    )
    assert r1.exit_code == 0, r1.stdout
    assert r2.exit_code == 0, r2.stdout
    run_id_1 = json.loads((out1 / "run.json").read_text(encoding="utf-8"))["run_id"]
    run_id_2 = json.loads((out2 / "run.json").read_text(encoding="utf-8"))["run_id"]
    assert run_id_1 == run_id_2


def test_run_crea_reporte_xlsx(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "exp.csv"
    _write(
        cfg, "cliente: 'X'\npermitir_ocr: false\nmask_por_defecto: true\nmoneda_default: 'CLP'\n"
    )
    _write(
        bank,
        "\n".join(
            [
                "fecha_operacion,monto,moneda,descripcion,referencia",
                "05/01/2026,1000,CLP,TEST,FAC-1",
                "",
            ]
        ),
    )
    _write(
        exp,
        "\n".join(
            [
                "fecha,monto,moneda,descripcion,referencia",
                "05/01/2026,1000,CLP,TEST,FAC-1",
                "",
            ]
        ),
    )
    out = tmp_path / "out"
    out.mkdir()

    r = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(cfg),
            "--bank",
            str(bank),
            "--expected",
            str(exp),
            "--out",
            str(out),
        ],
    )
    assert r.exit_code == 0, r.stdout
    assert (out / "reporte_conciliacion.xlsx").exists()


def test_explain_fail_closed_valida_run_json(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "out"
    out.mkdir()
    (out / "run.json").write_text('{"schema_version":"1.0.0"}', encoding="utf-8")

    r = runner.invoke(app, ["explain", "--run-dir", str(out), "ANY"])
    assert r.exit_code == 5
    assert "run.json invalido" in r.stdout


def test_explain_encuentra_match_por_id(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "exp.csv"
    _write(
        cfg, "cliente: 'X'\npermitir_ocr: false\nmask_por_defecto: true\nmoneda_default: 'CLP'\n"
    )
    _write(
        bank,
        "\n".join(
            [
                "fecha_operacion,monto,moneda,descripcion,referencia",
                "05/01/2026,1000,CLP,TEST,FAC-1",
                "",
            ]
        ),
    )
    _write(
        exp,
        "\n".join(
            [
                "fecha,monto,moneda,descripcion,referencia",
                "05/01/2026,1000,CLP,TEST,FAC-1",
                "",
            ]
        ),
    )
    out = tmp_path / "out"
    out.mkdir()

    r_run = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(cfg),
            "--bank",
            str(bank),
            "--expected",
            str(exp),
            "--out",
            str(out),
            "--dry-run",
        ],
    )
    assert r_run.exit_code == 0, r_run.stdout

    data = json.loads((out / "run.json").read_text(encoding="utf-8"))
    match_id = data["matches"][0]["id"]

    r = runner.invoke(app, ["explain", "--run-dir", str(out), match_id])
    assert r.exit_code == 0, r.stdout
    assert match_id in r.stdout


# ---------------------------------------------------------------------------
# `concilia init`: el primer comando de un usuario nuevo.
#
# Estava sin ninguna cobertura (pipeline.generar_plantillas_init y cmd_init, 0%).
# Es el camino de onboarding y escribe la config con la que corre todo lo demas:
# si la plantilla sale con un campo invalido o mal escrito, cada usuario nuevo
# arranca con la herramienta rota y el error aparece lejos de su causa.
# ---------------------------------------------------------------------------


def test_init_genera_plantillas_usable(tmp_path: Path) -> None:
    """Las plantillas se escriben y, ademas, son aceptadas por el propio core."""
    runner = CliRunner()
    res = runner.invoke(app, ["init", "--out-dir", str(tmp_path)])
    assert res.exit_code == 0, res.stdout
    assert "Plantillas generadas" in res.stdout

    for nombre in ("config_cliente.yaml", "movimientos_esperados.csv", "banco.csv"):
        destino = tmp_path / nombre
        assert destino.exists(), f"falta la plantilla {nombre}"
        assert destino.read_text(encoding="utf-8").strip(), f"plantilla vacia: {nombre}"


def test_init_config_generada_es_valida_para_el_core(tmp_path: Path) -> None:
    """
    La config que entrega `init` tiene que pasar el modelo, sin campos inventados.

    Es el contrato que hace util a la plantilla: si `generar_plantillas_init` o el
    template se desincronizan de `ConfiguracionCliente` (extra="forbid"), este
    test falla en vez de fallarle al usuario en su primer `concilia run`.
    """
    from conciliador_bancario.models import ConfiguracionCliente

    runner = CliRunner()
    res = runner.invoke(app, ["init", "--out-dir", str(tmp_path)])
    assert res.exit_code == 0, res.stdout

    import yaml

    datos = yaml.safe_load((tmp_path / "config_cliente.yaml").read_text(encoding="utf-8"))
    cfg = ConfiguracionCliente.model_validate(datos)  # extra="forbid": valida las claves
    assert cfg.cliente
    # Defaults que el motor lee: si `init` no los fija, el run aun funciona, pero
    # la politica documentada (fail-closed, ventanas) debe quedar explicita.
    assert cfg.umbral_confianza_campos > 0
    assert cfg.ventana_dias_monto_fecha >= 0
    assert cfg.limites_ingesta.max_input_bytes > 0


def test_init_crea_el_directorio_si_no_existe(tmp_path: Path) -> None:
    """`init` debe crear su destino, no fallar si el usuario eligio uno nuevo."""
    destino = tmp_path / "anidado" / "cliente"
    assert not destino.exists()

    res = CliRunner().invoke(app, ["init", "--out-dir", str(destino)])
    assert res.exit_code == 0, res.stdout
    assert (destino / "config_cliente.yaml").exists()


def test_init_es_idempotente(tmp_path: Path) -> None:
    """Repetir `init` sobre el mismo directorio no debe fallar ni alterarlo."""
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--out-dir", str(tmp_path)]).exit_code == 0
    antes = (tmp_path / "config_cliente.yaml").read_bytes()

    res = runner.invoke(app, ["init", "--out-dir", str(tmp_path)])
    assert res.exit_code == 0, res.stdout
    assert (tmp_path / "config_cliente.yaml").read_bytes() == antes


def test_init_sobre_destino_ocupado_por_un_archivo_falla_visible(tmp_path: Path) -> None:
    """Un destino invalido se reporta como error de IO, no como exito."""
    ocupado = tmp_path / "ya_existe"
    ocupado.write_text("soy un archivo", encoding="utf-8")

    res = CliRunner().invoke(app, ["init", "--out-dir", str(ocupado)])
    assert res.exit_code == 6, res.stdout
    assert "Error (io)" in res.stdout


# ---------------------------------------------------------------------------
# `explain`: caminos de error.
#
# Los dos casos felices ya estaban cubiertos (run.json valido, run.json que no
# es JSON). Faltaban los errores que un usuario se encuentra en la practica:
# apuntar a un directorio sin run.json, o pedir un id que no existe.
# ---------------------------------------------------------------------------


def test_explain_sin_run_json_falla_contrato(tmp_path: Path) -> None:
    """Un run_dir sin run.json es el error mas comun; debe ser claro, no interno."""
    vacio = tmp_path / "vacio"
    vacio.mkdir()

    r = CliRunner().invoke(app, ["explain", "--run-dir", str(vacio), "M-1"])
    assert r.exit_code == 5, r.stdout
    assert "Falta run.json" in r.stdout


def test_explain_id_inexistente_falla_con_entrada(tmp_path: Path) -> None:
    """Un id mal escrito es error del usuario (exit 2), no del run (exit 5)."""
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "exp.csv"
    out = tmp_path / "out"
    out.mkdir()
    _write(cfg, "cliente: 'X'\npermitir_ocr: false\nmoneda_default: 'CLP'\n")
    _write(
        bank,
        "fecha_operacion,monto,moneda,descripcion,referencia\n05/01/2026,1000,CLP,Pago,FAC-1\n",
    )
    _write(exp, "fecha,monto,moneda,descripcion,referencia\n05/01/2026,1000,CLP,Pago,FAC-1\n")

    r_run = CliRunner().invoke(
        app,
        [
            "run",
            "--config",
            str(cfg),
            "--bank",
            str(bank),
            "--expected",
            str(exp),
            "--out",
            str(out),
            "--dry-run",
        ],
    )
    assert r_run.exit_code == 0, r_run.stdout

    r = CliRunner().invoke(app, ["explain", "--run-dir", str(out), "M-no-existe"])
    assert r.exit_code == 2, r.stdout
    assert "M-no-existe" in r.stdout
