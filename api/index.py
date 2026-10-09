"""Entrypoint para Vercel (serverless).

Vercel detecta este archivo y expone `app` como WSGI.
"""

import sys
from pathlib import Path

# Asegura que el raíz del proyecto esté en el path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app  # noqa: E402  (debe ir luego del sys.path)

# Vercel busca una variable llamada `app` o `handler`
handler = app
