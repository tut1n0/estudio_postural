"""Crea las tablas del esquema sobre PostgreSQL/Supabase.

Uso:
    python scripts/init_db.py
"""

import sys
from pathlib import Path

# Permite importar módulos del raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Config
from database import close_pool, get_conn


def main() -> None:
    if not Config.DATABASE_URL:
        print("ERROR: falta DATABASE_URL en .env (ver .env.example).")
        sys.exit(1)

    schema_path = Path(__file__).resolve().parent / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")

    print(f"Conectando a: {Config.DATABASE_URL.split('@')[-1]}")
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
    finally:
        close_pool()
    print("Esquema creado/verificado correctamente.")
    print("Siguiente paso: python scripts/seed.py")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR al crear el esquema: {exc}")
        sys.exit(1)
