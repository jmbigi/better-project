"""Sandbox de temporales para pytest (hallazgo 2026-10-03).

La suite usa tempfile.mkdtemp() con limpieza desigual; sin sandbox cada
corrida de pytest dejaba residuos en el TMPDIR del usuario (32 GB acumulados
llegaron a tumbar el hook pre-commit por agotamiento de /tmp). Estos hooks
aislan TMPDIR en un directorio propio de la sesion y lo eliminan al terminar.
"""

import os
import shutil
import tempfile

_BASE: str | None = None


def pytest_configure(config) -> None:
    global _BASE
    _BASE = tempfile.mkdtemp(prefix="better-tests-pytest-")
    os.environ["TMPDIR"] = _BASE
    tempfile.tempdir = None


def pytest_unconfigure(config) -> None:
    if _BASE:
        shutil.rmtree(_BASE, ignore_errors=True)
