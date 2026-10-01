from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ErrorConciliador(Exception):
    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.details = dict(details or {})
        self.hint = hint


class ErrorEntradaUsuario(ErrorConciliador):
    pass


class ErrorConfiguracion(ErrorConciliador):
    pass


class ErrorContrato(ErrorConciliador):
    pass


class ErrorOperacionIO(ErrorConciliador):
    pass


class ErrorSalidaEnUso(ErrorOperacionIO):
    """Otra corrida tiene el `--out`. Es transitorio: se reintenta, no se corrige.

    ## Por que un tipo y no un `details`

    Porque el remedio es lo que define el codigo de salida, y un `details` con una
    cadena `"salida_en_uso"` seria el mismo discriminante fragil por el que un test de
    este repo dejo de poder fallar: si alguien escribe el texto distinto, el codigo
    cambia de numero sin que nada lo note. Con un tipo, `isinstance` no se equivoca.

    ## Por que vive aqui y no en `audit/atomic.py`

    Porque necesita heredar de `ErrorOperacionIO`. El error lo levanta el cerrojo, pero
    lo que la CLI necesita distinguir es la **categoria**, y esa vive en este modulo.
    `audit/atomic.py` lo importa desde aqui, asi que hay un solo tipo con dos nombres
    de modulo, no dos clases homonimas que un `isinstance` no podria igualar.

    Y con esto el pipeline deja de perder la identidad: antes reconvertia este error en
    `ErrorOperacionIO` a secas para no perder el `salida` del mensaje, y ahi se perdia
    justo el motivo que permite darle codigo propio.
    """
