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
import stat
import time
from pathlib import Path
from typing import Any

NOMBRE_CERROJO = ".concilia.lock"

# Un cerrojo sin PID se declara basura solo si lleva este tiempo sin escribirse.
# Es la holgura de la ventana entre `O_EXCL` y la escritura del PID: ver
# `CerrojoDeSalida._sin_pid_pero_viejo`.
_SEGUNDOS_PARA_DECLARAR_BASURA = 5.0

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
    temporal = destino.with_name(f".{destino.name}{sufijo}-{os.getpid()}")
    try:
        escribir(temporal)
        _conservar_permisos(temporal, destino)
        os.replace(temporal, destino)
    except BaseException:
        # Si falla la escritura o el replace, el temporal no se queda dando vueltas.
        # Un `.tmp` huérfano es basura; además, si el destino nunca se tocó, el
        # artefacto viejo sigue siendo el bueno.
        temporal.unlink(missing_ok=True)
        raise


def _conservar_permisos(temporal: Path, destino: Path) -> None:
    """Deja el temporal con los permisos que ya tenia el destino.

    `os.replace` cambia el inode, asi que el archivo nuevo nace con los permisos
    del umask y **los del destino anterior se pierden**: un `run.json` que el
    operador dejo en `0600` porque contiene datos de clientes quedaba en `0664`.

    Es un archivo financiero, y el permiso puesto a mano es una decision del
    operador que la herramienta no tiene por que deshacer. Solo se copia la
    mascara, no el propietario: el archivo lo crea el mismo proceso.
    """
    try:
        modo_destino = stat.S_IMODE(destino.stat().st_mode)
    except OSError:
        # El destino no existe todavia (primera corrida): se queda el umask, que
        # es lo correcto para un archivo que nadie ha declarado restricted.
        return
    try:
        os.chmod(temporal, modo_destino)
    except OSError:
        # Un filesystem que no soporta chmod (algunos montajes) no es motivo para
        # tumbar la corrida: el contenido esta bien y el permiso ya no.
        pass


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

    def _sin_pid_pero_viejo(self) -> bool:
        """Cerrojo sin PID y suficientemente viejo para ser basura.

        ## Por que hace falta esto

        `os.open(..., O_EXCL)` crea el archivo **vacío**. El PID se escribe justo
        después, en otra operación. Entre las dos hay una ventana: si el cerrojo se
        lee ahí, no tiene contenido.

        El código anterior trataba "sin contenido" como "dueño muerto" y lo
        reclamaba. Eso convierte una ventana de microsegundos en una carrera real:
        la corrida B ve el archivo vacío de la corrida A, cree que A murió, lo borra
        y entra. Las dos escriben en el mismo `--out` y el `audit.jsonl` queda con
        los `run_id` de las dos mezclados.

        Se vio en CI, no en local: en una máquina rápida las dos corridas no se
        solapan. Un test de concurrencia que solo pasa en local es un test que no
        sabe lo que mide.

        ## Por qué el tiempo y no solo el contenido

        Un cerrojo vacío **fresco** es alguien acquiring en este instante: no se
        toca. Uno **viejo** es basura de un proceso muerto entre las dos operaciones,
        y se reclaima para que la herramienta no quede inservible. El umbral es
        holgado a propósito: preferimos bloquear unos segundos de más a robarle el
        cerrojo a una corrida viva.
        """
        try:
            edad = time.time() - self._path.stat().st_mtime
        except OSError:
            return False
        return edad > _SEGUNDOS_PARA_DECLARAR_BASURA

    def _propietario_muerto(self) -> bool:
        """True si el cerrojo existe, tiene PID, y ese proceso ya no.

        Un cerrojo **sin PID** no se puede declarar muerto por el PID, asi que se
        decide por edad: vacio y viejo es basura, vacio y fresco es una adquisicion
        en curso. Ver `_sin_pid_pero_viejo`.
        """
        try:
            contenido = self._path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return True  # ya no existe: no hay dueño
        except OSError:
            return False
        if not contenido:
            return self._sin_pid_pero_viejo()
        # El nombre del archivo va en el mismo `write` que el PID, asi que su
        # presencia acts como una especie de checksum. Sin esta comprobacion, una
        # lectura parcial —el archivo se escribe justo mientras se lee— puede
        # devolver `"9"` de un `"999999 ..."` a medio escribir: se consultaria el
        # PID 9, que probablemente no exista, y se reclamaria el cerrojo de una
        # corrida **viva**. Un cerrojo robado deja pasar dos procesos al mismo
        # `--out`, que es el bug que este archivo arregla.
        if not contenido.endswith(self._path.name):
            return self._sin_pid_pero_viejo()
        try:
            pid = int(contenido.split()[0])
        except (ValueError, IndexError):
            return self._sin_pid_pero_viejo()
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
        """
        Suelta el cerrojo, y **nunca falla**.

        Se llama desde un `finally`: si `unlink` levantara, la excepcion escaparia
        sustituyendo a la que se estaba propagando y el cerrojo se quedaria puesto.
        Un cerrojo huerfano deja la herramienta inservible hasta que alguien borre
        un archivo a mano, que es el remedio que nadie recuerda.

        Por eso no hay `raise` aqui, ni siquiera con `--debug`: no hay nada que el
        operador pueda hacer con este error, y dejar el cerrojo puesto es peor que
        perder una limpieza.
        """
        if not self._tomado:
            return
        self._tomado = False
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass

    def __enter__(self) -> CerrojoDeSalida:
        self.adquirir()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.liberar()


class ErrorSalidaEnUso(RuntimeError):
    """Dos corridas compitiendo por el mismo `--out`."""
