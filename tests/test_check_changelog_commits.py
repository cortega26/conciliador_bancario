"""Tests del guard de changelog, con foco en no dejar commits sin revisar.

La razon de testear el parser y no solo la regla: la primera version de
`tools/check_changelog_commits.py` usaba `%x1e` como separador de registro y
`.strip()` sobre la salida de git. Python considera `\\x1e` y `\\x1f` whitespace,
entonces `.strip()` se comia el separador del ultimo registro, ese registro
quedaba con un campo menos y el commit **mas reciente** se saltaba en silencio.

El guard pasaba en verde sin mirar el commit que acababa de mergearse, que es
justo el que mas importaba. Estos tests fijan que ningun commit se pierde.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from check_changelog_commits import (  # noqa: E402
    Commit,
    ErrorDeUso,
    RegistroInvalido,
    commits_desde,
    commits_que_duplican,
    resolver_base,
)

RAIZ = Path(__file__).resolve().parents[1]


# --- La regla -----------------------------------------------------------------


def _commit(asunto: str, cuerpo: str = "") -> Commit:
    return Commit(sha="0" * 40, asunto=asunto, cuerpo=cuerpo)


def test_merge_de_github_con_tipo_duplica() -> None:
    """La forma que produjo la duplicacion en 0.2.17 y varias releases previas."""
    c = _commit("Merge pull request #20 from org/rama", "fix(errors): el titulo del PR")
    assert commits_que_duplican([c])


def test_merge_de_github_sin_tipo_no_duplica() -> None:
    c = _commit("Merge pull request #20 from org/rama", "frontera de ingesta")
    assert not commits_que_duplican([c])


def test_merge_propio_con_tipo_en_el_titulo_duplica() -> None:
    """`Merge PR #n: fix(x): ...` tambien duplica: el titulo va despues de los dos puntos."""
    c = _commit("Merge PR #98: fix(x): algo")
    assert commits_que_duplican([c])


def test_merge_propio_sin_tipo_no_duplica() -> None:
    c = _commit("Merge PR #26: notas de 0.2.17 legibles")
    assert not commits_que_duplican([c])


def test_commit_normal_con_tipo_no_duplica() -> None:
    """Un commit de trabajo con tipo es lo correcto; solo los merges son problema."""
    c = _commit("fix(x): algo legitimo", "cuerpo largo\n\ncon parrafos")
    assert not commits_que_duplican([c])


def test_breaking_change_con_signo_exclamacion() -> None:
    c = _commit("Merge pull request #1 from o/r", "feat(api)!: breaking")
    assert commits_que_duplican([c])


def test_varios_commits_uno_solo_sospechoso() -> None:
    commits = [
        _commit("Merge pull request #1 from o/r", "fix(a): uno"),
        _commit("Merge pull request #2 from o/r", "sin tipo"),
        _commit("Merge PR #3: chore: dos"),
    ]
    assert len(commits_que_duplican(commits)) == 2


def test_texto_que_parece_tipo_pero_no_al_principio_no_dispara() -> None:
    """Una linea que empieza con `fix:` en medio del cuerpo no es el titulo del PR."""
    c = _commit(
        "Merge PR #30: algo",
        "El error era:\nfix(x): no deberia contar\nmas texto",
    )
    assert not commits_que_duplican([c])


# --- El parser: ningun commit se pierde ---------------------------------------


@pytest.fixture
def repo_temporal(tmp_path: Path) -> Path:
    """Repo git chico y aislado, con tags, para probar el parser de verdad."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    for nombre, usuario in (("user", "u@example.com"),):
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", nombre], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", usuario], check=True)

    def commit(mensaje: str) -> None:
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-q", "--allow-empty", "-m", mensaje], check=True
        )

    commit("chore: primero")
    subprocess.run(["git", "-C", str(tmp_path), "tag", "v1.0.0"], check=True)
    commit("Merge pull request #1 from o/r\n\nfix(a): dup")
    commit("Merge PR #2: sin tipo")
    commit("cuerpo\ncon\nlineas\n\ny un parrafo")
    return tmp_path


def _con_cwd(repo: Path):
    import os

    anterior = Path.cwd()
    os.chdir(repo)
    return anterior


def test_parser_no_pierde_el_ultimo_commit(repo_temporal: Path) -> None:
    """El commit mas reciente siempre tiene que estar en la lista.

    Este es el test que fija el bug del separador: con `%x1e` + `.strip()`, el
    ultimo commit se saltaba en silencio y el guard pasaba en verde.
    """
    anterior = _con_cwd(repo_temporal)
    try:
        commits = commits_desde("v1.0.0")
    finally:
        import os

        os.chdir(anterior)

    assert len(commits) == 3, [c.asunto for c in commits]
    # El ultimo es el que se perdia, asi que se afirma el contenido, no solo el largo.
    assert commits[-1].asunto.startswith("cuerpo")


def test_parser_preserva_cuerpos_con_varias_lineas(repo_temporal: Path) -> None:
    anterior = _con_cwd(repo_temporal)
    try:
        commits = commits_desde("v1.0.0")
    finally:
        import os

        os.chdir(anterior)

    con_cuerpo = next(c for c in commits if c.asunto.startswith("cuerpo"))
    assert "y un parrafo" in con_cuerpo.cuerpo


def test_parser_detecta_el_duplicado_real(repo_temporal: Path) -> None:
    anterior = _con_cwd(repo_temporal)
    try:
        sospechosos = commits_que_duplican(commits_desde("v1.0.0"))
    finally:
        import os

        os.chdir(anterior)

    assert len(sospechosos) == 1
    assert "fix(a): dup" in sospechosos[0][1]


def test_registro_invalido_falla_en_vez_de_saltearse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un registro mal formado es un error, no algo que se saltee.

    Saltearselo dejaria commits sin revisar creyendo que se revisaron, que es la
    falla que este guard existe para evitar.
    """
    import check_changelog_commits as mod

    monkeypatch.setattr(mod, "_git", lambda *a: "abc\x1f solo dos campos\x00")
    with pytest.raises(RegistroInvalido):
        mod.commits_desde("v1.0.0")


def test_resolver_base_usa_el_ultimo_tag(repo_temporal: Path) -> None:
    anterior = _con_cwd(repo_temporal)
    try:
        assert resolver_base(None) == "v1.0.0"
    finally:
        import os

        os.chdir(anterior)


def test_resolver_base_es_explicito_si_se_pasa(repo_temporal: Path) -> None:
    anterior = _con_cwd(repo_temporal)
    try:
        assert resolver_base("  v1.0.0  ") == "v1.0.0"
    finally:
        import os

        os.chdir(anterior)


def test_resolver_base_falla_cerrado_sin_tags(tmp_path: Path) -> None:
    """Sin tags no adivina: avisar es mejor que revisar de mas y quedar como ruido."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "u"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "u@e.com"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "--allow-empty", "-m", "x"], check=True
    )

    anterior = _con_cwd(tmp_path)
    try:
        with pytest.raises(ErrorDeUso):
            resolver_base(None)
    finally:
        import os

        os.chdir(anterior)
