"""Escritura atómica y cerrojo de directorio de salida.

## Por qué esto existe

Dos corridas simultáneas sobre el mismo `--out` **ambas salían con exit 0**, y
solo sobrevivía una: el constructor de `JsonlAuditWriter` abre el log en modo
`"w"` desde el principio, así que la segunda corrida trunca el archivo de la
primera, y al final gana la que termina último. El operador cree que Concilió dos
veces; en realidad una conciliación desapareció sin aviso.

El truncado **no es el bug**: el log de auditoría es la traza determinista de *esa*
corrida, así que reemplazarlo es lo correcto. El bug es hacerlo antes de saber si la
corrida va a funcionar, y no impedir que dos procesos compitan por el mismo
destino.

## Las tres piezas

1. **`escribir_atomico`**: escribe a un `.tmp` en el **mismo directorio** y luego
   `os.replace`. El mismo directorio importa: `os.replace` es atómico solo dentro
   del mismo filesystem, y un `.tmp` en `/tmp` cruzaría filesystems y degrimiría a
   copy+delete, que no es atómico. Con esto, un proceso muerto a mitad de escritura
   deja el artefacto viejo intacto, no uno truncado.

   **Que el helper exista no significa que los artefactos esten protegidos.** Este
   helper estuvo meses escrito y probado, sin que `run.json` ni el `.xlsx` lo llamaran
   una sola vez: la proteccion estaba en el codigo y no en el producto. Por eso
   `tests/test_escritura_atomica.py` verifica el uso y no la implementacion, y por que
   `audit.jsonl` queda fuera a proposito (ver `JsonlAuditWriter`).

2. **`CerrojoDeSalida`**: un archivo con `O_EXCL` que dice "esta salida está en
   uso". Si existe y el proceso dueño sigue vivo, la segunda corrida **falla con un
   mensaje claro** en vez de pisar. Si el proceso ya no existe (un crash dejó el
   cerrojo), se lo queda: un cerrojo zombie bloquearía la herramienta para
   siempre, que es peor que el problema que previene.

3. **Nombres**: el archivo de cerrojo es un punto, para que no se confunda con un
   artefacto del run. Y se nombra en el mensaje de error, para que el operador
   sepa qué borrar si de verdad se quedó pegado.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path
from typing import Any

NOMBRE_CERROJO = ".concilia.lock"

# `os.O_EXCL` sobre un archivo existente falla con EEXIST. Es la primitiva atómica
# del sistema operativo para "este nombre lo tomo yo", y no necesita locks de
# biblioteca ni coordination entre procesos.
_FLAGS_EXCL = os.O_CREAT | os.O_EXCL | os.O_WRONLY


def escribir_atomico(destino: Path, escribir: Any, *, sufijo: str = ".tmp") -> None:
    """Escribe `destino` de forma todo-o-nada.

    `escribir` recibe el path temporal y hace lo que tenga que hacer (openpyxl
    `wb.save`, json.dump, write_text). Se pasa el path en vez del contenido porque
    el reporte es un `.xlsx` que se guarda con una API propia, no con un
    `write_text`.

    El temporal va en el **mismo directorio** que el destino: `os.replace` solo es
    atómico dentro del mismo filesystem.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f"{destino.name}{sufijo}-{os.getpid()}")
    try:
        escribir(temporal)
        os.replace(temporal, destino)
    except BaseException:
        # Si falla la escritura o el replace, el temporal no se queda dando vueltas.
        # Un `.tmp` huérfano es basura; además, si el destino nunca se tocó, el
        # artefacto viejo sigue siendo el bueno.
        temporal.unlink(missing_ok=True)
        raise


class CerrojoDeSalida:
    """Impide que dos procesos escriban en el mismo `--out` a la vez.

    ## Por qué fallar y no sobrescribir

    La alternativa simpática es "la segunda gana". El problema es que las dos
    devuelven exit 0: el operador lanza dos conciliaciones, ve dos ejecuciones
    exitosas, y revisa un directorio con una sola. La reconciliación que desapareció
    no dejó rastro de que existió.

    Fallar es la opción fail-closed, y es la que el repo ya usa para todo lo demás.

    ## Cerrojos zombie

    Un proceso muerto a mitad de corrida deja el archivo. Se comprueba el pid: si ya
    no existe el proceso, el cerrojo es basura y se reclaima. Sin esto, un `kill -9`
    dejaría la herramienta inservible hasta que alguien borrara un archivo a mano,
    que es un remedio que nadie recuerda.
    """

    def __init__(self, out_dir: Path) -> None:
        self._path = out_dir / NOMBRE_CERROJO
        self._tomado = False

    def _propietario_muerto(self) -> bool:
        """True si el cerrojo existe pero su proceso ya no."""
        try:
            contenido = self._path.read_text(encoding="utf-8").strip()
        except OSError:
            return False
        if not contenido:
            return True
        try:
            pid = int(contenido.split()[0])
        except (ValueError, IndexError):
            return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False  # existe, es de otro usuario: vivo
        except OSError:
            return False
        return False

    def adquirir(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        for intento in (1, 2):
            try:
                fd = os.open(self._path, _FLAGS_EXCL, 0o600)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
                if intento == 1 and self._propietario_muerto():
                    # Cerrojo zombie: se lo queda esta corrida.
                    self._path.unlink(missing_ok=True)
                    continue
                pid = ""
                try:
                    pid = self._path.read_text(encoding="utf-8").strip()
                except OSError:
                    pass
                raise ErrorSalidaEnUso(
                    f"La salida ya está en uso por otra corrida (pid {pid or 'desconocido'}). "
                    f"Dos conciliaciones simultáneas sobre el mismo --out se pisan: "
                    f"una de las dos se perdería sin aviso.\n"
                    f"Si está seguro que no hay ninguna corrida corriendo, borre "
                    f"`{self._path}` y vuelva a intentarlo."
                ) from e
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(f"{os.getpid()} {self._path.name}")
                self._tomado = True
                return
        raise AssertionError("adquirir no deberia agotar los intentos")

    def liberar(self) -> None:
        if self._tomado:
            self._path.unlink(missing_ok=True)
            self._tomado = False

    def __enter__(self) -> CerrojoDeSalida:
        self.adquirir()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.liberar()


class ErrorSalidaEnUso(RuntimeError):
    """Dos corridas compitiendo por el mismo `--out`."""
