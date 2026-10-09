"""Configuración central de la aplicación.

Todos los valores sensibles llegan desde variables de entorno (.env).
Nunca se hardcodean credenciales ni datos del estudio.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Carga .env si existe (en Vercel las variables vienen del entorno)
load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    """Configuración base usada por todos los entornos."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    DATABASE_URL = os.environ.get("DATABASE_URL", "")

    # Zona horaria y datos del estudio
    ZONA_HORARIA = os.environ.get("ZONA_HORARIA", "America/Argentina/Buenos_Aires")
    NOMBRE_ESTUDIO = os.environ.get("NOMBRE_ESTUDIO", "Estudio Postural")
    MONEDA = os.environ.get("MONEDA", "$")
    SESION_HORAS = _int("SESION_HORAS", 12)

    # Pool de conexiones psycopg
    POOL_MAX_SIZE = _int("POOL_MAX_SIZE", 4)

    # Sesiones
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12  # 12 horas

    WTF_CSRF_TIME_LIMIT = None  # reservado (no se usa Flask-WTF)

    @staticmethod
    def validar():
        """Devuelve una lista de problemas de configuración detectados."""
        problemas = []
        if not Config.DATABASE_URL:
            problemas.append("Falta DATABASE_URL en .env (ver .env.example).")
        if Config.SECRET_KEY == "dev-secret-change-me":
            problemas.append("SECRET_KEY sigue siendo el valor por defecto.")
        return problemas


class TestingConfig(Config):
    TESTING = True
