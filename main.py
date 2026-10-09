"""Punto de entrada cuando el despliegue arranca en la raíz del repositorio.

Render ejecuta `uvicorn main:app` desde la raíz, pero el código vive en
`back/`. Este módulo carga back/main.py y expone `app` para que el arranque
funcione sin tocar la configuración del servicio.
"""

import importlib.util
import os
from pathlib import Path

_BASE = Path(__file__).resolve().parent
if "GEMINI_API_KEY" not in os.environ:
    # Solo para desarrollo local: en Render la clave viene del entorno.
    try:
        from dotenv import load_dotenv

        load_dotenv(_BASE / "back" / ".env")
    except ImportError:
        pass

_RUTA = _BASE / "back" / "main.py"
_ESPEC = importlib.util.spec_from_file_location("agente_vocal_main", _RUTA)
_MODULO = importlib.util.module_from_spec(_ESPEC)
if _ESPEC.loader is None:
    raise RuntimeError("No se encontró back/main.py")
_ESPEC.loader.exec_module(_MODULO)

app = _MODULO.app
