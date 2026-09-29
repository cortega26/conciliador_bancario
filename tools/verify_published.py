"""Verifica el paquete REALMENTE publicado en PyPI, no que el job haya pasado.

## Por que existe

`publish.yml` termina en verde cuando Trusted Publishing acepto los archivos. Eso
dice que la API de PyPI respondio bien, y nada mas.

En dos publicaciones consecutiveidas de este repo, el job dio `success` y:

- la API por version ya respondia 200, pero el **indice simple todavia no
  listaba la version** (minutos de retardo);
- `pip install bankrecon==<n>` fallaba con "no matching distribution", y el
  primer diagnostico fue "publicacion fallida" cuando en realidad era la cache
  local de indice de pip;
- y `pypi.org/pypi/<pkg>/json` (endpoint del proyecto) seguia reportando la
  version anterior por minutos, con lo que un chequeo rapido concluyo que
  "no se publico".

En las dos veces la conclusion correcta salio de mirar el sha256 del archivo y de
instalarlo en un venv limpio. Ese proceso estaba en la cabeza de quien operaba, no
en el repo. Este script lo convierte en un comando, y lo pone en el mismo lugar
que el resto de la verificacion.

## Que hace

1. Espera a que el **indice simple** liste la version (con cache-bust), que es lo
   que consulta `pip`. Es el retardo real, y el que importa.
2. Compara el sha256 del archivo descargado con el que publica la API.
3. Instala el wheel en un venv limpio.
4. Comprueba que el SBOM este dentro del paquete (PEP 770).
5. Corre entradas hostiles y exige **exit 4 de ingesta**, nunca exit 10 interno.
6. Corre una corrida valida y exige exit 0 con los tres artefactos.

Todo con red. Es un gate de post-publicacion, no algo que corra en cada push.

Uso:
    python tools/verify_published.py <version> [--index-url ...]
    python tools/verify_published.py 0.2.19 --solo-indice
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PAQUETE = "bankrecon"
RAIZ = Path(__file__).resolve().parents[1]

EXIT_INGESTION = 4
EXIT_OK = 0


class FallaDeVerificacion(RuntimeError):
    """El paquete publicado no cumple lo que se le pidio verificar."""


@dataclass(frozen=True)
class ArchivoPublicado:
    nombre: str
    url: str
    sha256: str
    tamano: int


def _http(url: str) -> bytes:
    peticion = urllib.request.Request(url, headers={"User-Agent": "bankrecon-verify"})
    with urllib.request.urlopen(peticion, timeout=60) as r:  # noqa: S310 - URLs de PyPI fijas
        return r.read()


def _json(url: str) -> dict:
    return json.loads(_http(url))


def indice_tiene_version(version: str, index_url: str) -> bool:
    """Si el indice simple lista los archivos de la version.

     Este es el retardo real: la API por version responde antes de que el indice
    -simple sirva los archivos, y `pip` lee el indice. Un chequeo hecho contra la
     API concluye "publicado" mientras `pip install` todavia falla.
    """
    sep = "&" if "?" in index_url else "?"
    url = f"{index_url.rstrip('/')}/{PAQUETE}/{sep}nocache={time.time_ns()}"
    html = _http(url).decode("utf-8", "replace")
    return f"{PAQUETE}-{version}-" in html


def esperar_indice(version: str, index_url: str, intentos: int, espera_s: int) -> None:
    for i in range(intentos):
        if indice_tiene_version(version, index_url):
            return
        restante = (intentos - i) * espera_s
        print(
            f"  el indice todavia no lista {version} " f"(puede reintentar en ~{restante}s)",
            flush=True,
        )
        time.sleep(espera_s)
    raise FallaDeVerificacion(
        f"tras {intentos * espera_s}s, el indice de {index_url} no lista {PAQUETE}-{version}. "
        "La publicacion puede no haber ocurrido, o PyPI no la indexo todavia. "
        "No se declara exito sin ver el archivo en el indice."
    )


def archivos_de(version: str) -> list[ArchivoPublicado]:
    datos = _json(f"https://pypi.org/pypi/{PAQUETE}/{version}/json")
    return [
        ArchivoPublicado(
            nombre=u["filename"],
            url=u["url"],
            sha256=u["digests"]["sha256"],
            tamano=u["size"],
        )
        for u in datos["urls"]
    ]


def descargar(archivo: ArchivoPublicado, destino: Path) -> str:
    """Descarga y devuelve el sha256, para compararlo con el que declara la API."""
    contenido = _http(archivo.url)
    destino.write_bytes(contenido)
    return hashlib.sha256(contenido).hexdigest()


def verificar_integridad(archivos: list[ArchivoPublicado], destino: Path) -> None:
    for a in archivos:
        local = descargar(a, destino / a.nombre)
        if local != a.sha256:
            raise FallaDeVerificacion(
                f"{a.nombre}: sha256 local {local[:16]} != el que declara PyPI {a.sha256[:16]}"
            )
        if (destino / a.nombre).stat().st_size != a.tamano:
            raise FallaDeVerificacion(f"{a.nombre}: el tamano no coincide con PyPI")
        print(f"  OK  {a.nombre}  sha256 {local[:16]}  {a.tamano} bytes")


def verificar_sbom(venv: Path) -> None:
    codigo = (
        "import json,pathlib,importlib.metadata as m;"
        "d=m.distribution('bankrecon');"
        "sb=[f for f in (d.files or []) if 'sboms' in str(f)];"
        "assert sb, 'el paquete publicado no trae SBOM (PEP 770)';"
        "b=json.loads(pathlib.Path(d.locate_file(sb[0])).read_text());"
        "print(b['bomFormat'], b['specVersion'], len(b['components']))"
    )
    salida = _venv_python(venv, "-c", codigo)
    print(f"  OK  SBOM embebido: {salida}")
    if not salida.startswith("CycloneDX"):
        raise FallaDeVerificacion(f"el SBOM no es CycloneDX: {salida!r}")


def _venv_python(venv: Path, *args: str) -> str:
    p = subprocess.run([str(venv / "bin" / "python"), *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise FallaDeVerificacion(
            f"comando fallo en el venv: {' '.join(args[:2])}\n"
            f"{(p.stderr or p.stdout).strip()[-1500:]}"
        )
    return (p.stdout or "").strip()


def _concilia(venv: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run([str(venv / "bin" / "concilia"), *args], capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _preparar_caso(venv: Path, raiz: Path) -> tuple[Path, Path]:
    """Un cliente inicializado y un archivo esperado valido."""
    cliente = raiz / "cliente"
    subprocess.run(
        [str(venv / "bin" / "concilia"), "init", "--out-dir", str(cliente)],
        capture_output=True,
        text=True,
        check=True,
    )
    config = next(cliente.rglob("*.yaml"))
    (raiz / "esperados.csv").write_text(
        "fecha,monto,descripcion\n05/01/2026,1000,prueba\n", encoding="utf-8"
    )
    return config, raiz / "esperados.csv"


def verificar_comportamiento(venv: Path, raiz: Path) -> None:
    """Exit codes en entradas hostiles, y una corrida valida.

    Es la parte que mas importa y la que ningun job de CI cubre: los jobs corren
    contra el repo, no contra el wheel publicado. Un error de packaging o un
    `.gitignore` que se comio un archivo solo se ve instalando lo publicado.
    """
    config, esperados = _preparar_caso(venv, raiz)
    entrada = raiz / "entrada"
    entrada.mkdir(exist_ok=True)

    hostiles: dict[str, bytes] = {
        "vacio.pdf": b"",
        "basura.pdf": b"no soy un pdf",
        "truncado.xlsx": b"PK\x03\x04\x00basura",
        "basura.csv": b"basura",
        "dtd.xml": (
            b'<?xml version="1.0"?><!DOCTYPE c [<!ENTITY lol "lol">]>'
            b"<cartola><descripcion>&lol;</descripcion></cartola>"
        ),
    }
    for nombre, contenido in hostiles.items():
        (entrada / nombre).write_bytes(contenido)
        code, salida = _concilia(
            venv,
            "validate",
            "--config",
            str(config),
            "--bank",
            str(entrada / nombre),
            "--expected",
            str(esperados),
        )
        if code != EXIT_INGESTION:
            raise FallaDeVerificacion(
                f"{nombre}: exit {code}, se esperaba {EXIT_INGESTION} (ingestion).\n"
                f"Un exit 10 significa 'internal error': el error del archivo se "
                f"reportaria como falla de la herramienta.\n{salida[-500:]}"
            )
        print(f"  OK  {nombre:16s} exit {code} (ingestion)")

    (entrada / "cartola.csv").write_text(
        "fecha_operacion,monto,descripcion,moneda,referencia\n" "05/01/2026,150000,Prueba,CLP,\n",
        encoding="utf-8",
    )
    salida_dir = raiz / "salida"
    code, salida = _concilia(
        venv,
        "run",
        "--config",
        str(config),
        "--bank",
        str(entrada / "cartola.csv"),
        "--expected",
        str(esperados),
        "--out",
        str(salida_dir),
    )
    if code != EXIT_OK:
        raise FallaDeVerificacion(f"una corrida valida dio exit {code}\n{salida[-500:]}")
    faltantes = [
        n
        for n in ("run.json", "audit.jsonl", "reporte_conciliacion.xlsx")
        if not (salida_dir / n).exists()
    ]
    if faltantes:
        raise FallaDeVerificacion(f"faltan artefactos: {faltantes}")
    print("  OK  corrida valida: exit 0 con run.json, audit.jsonl y reporte")


def crear_venv(destino: Path, wheel: Path) -> Path:
    base = shutil.which("python3") or sys.executable
    subprocess.run([base, "-m", "venv", str(destino)], check=True, capture_output=True)
    subprocess.run(
        [
            str(destino / "bin" / "python"),
            "-m",
            "pip",
            "install",
            "-q",
            "--no-cache-dir",
            "--upgrade",
            "pip",
        ],
        check=True,
        capture_output=True,
    )
    # Se instala el archivo, no "bankrecon==x": asi se verifica exactamente el
    # paquete publicado, sin depender del indice que es justamente lo que se
    # esta midiendo.
    subprocess.run(
        [
            str(destino / "bin" / "python"),
            "-m",
            "pip",
            "install",
            "-q",
            "--no-cache-dir",
            str(wheel),
        ],
        check=True,
        capture_output=True,
    )
    return destino


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("version", help="Version a verificar, p. ej. 0.2.19")
    ap.add_argument("--index-url", default="https://pypi.org/simple")
    ap.add_argument("--intentos", type=int, default=8)
    ap.add_argument("--espera", type=int, default=30)
    ap.add_argument(
        "--solo-indice",
        action="store_true",
        help="Solo esperar a que el indice liste la version (sin venv ni red extra).",
    )
    args = ap.parse_args(argv)

    try:
        print(f"1. esperando a que el indice liste {PAQUETE}-{args.version}")
        esperar_indice(args.version, args.index_url, args.intentos, args.espera)
        print("  OK  el indice lo lista")

        if args.solo_indice:
            print("verificacion parcial: solo el indice")
            return 0

        archivos = archivos_de(args.version)
        if not archivos:
            raise FallaDeVerificacion(f"PyPI no devuelve archivos para {args.version}")
        wheel = next((a for a in archivos if a.nombre.endswith(".whl")), None)
        if wheel is None:
            raise FallaDeVerificacion("la release no publico un wheel")

        print("2. verificando integridad contra lo que declara PyPI")
        with tempfile.TemporaryDirectory() as d:
            destino = Path(d)
            verificar_integridad(archivos, destino)

            print("3. instalando el wheel publicado en un venv limpio")
            venv = crear_venv(destino / "venv", destino / wheel.nombre)
            _venv_python(
                venv,
                "-c",
                f"import importlib.metadata as m;assert m.version('{PAQUETE}')=='{args.version}'",
            )
            print(f"  OK  {PAQUETE} {args.version} instalado")

            print("4. comprobando el SBOM embebido (PEP 770)")
            verificar_sbom(venv)

            print("5. comportamiento fail-closed en el paquete publicado")
            verificar_comportamiento(venv, destino)
    except FallaDeVerificacion as e:
        print(f"\nERROR: {e}")
        return 1
    except Exception as e:  # noqa: BLE001 - red y formatos de terceros
        print(f"\nERROR inesperado: {type(e).__name__}: {e}")
        return 2

    print(f"\n{PAQUETE} {args.version} verificado en PyPI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
