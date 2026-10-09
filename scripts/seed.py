"""Carga de datos iniciales (idempotente).

- Usuario administrador inicial
- Actividades: Terapia Postural Activa, Pilates, Yoga
- Métodos de pago argentinos
- Configuración por defecto del estudio

Uso:
    python scripts/seed.py
    python scripts/seed.py --admin-email admin@estudio.com --admin-pass MiClave123
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from werkzeug.security import generate_password_hash

from config import Config
from database import close_pool, get_conn, query_one

ACTIVIDADES = [
    ("Terapia Postural Activa", "Trabajo postural activo con ejercicios de conciencia corporal y corrección.", 60, 38000),
    ("Pilates", "Pilates en aparatos y mat, foco en centro, control y movilidad.", 55, 40000),
    ("Yoga", "Práctica de yoga alineación, respiración y flexibilidad.", 60, 35000),
]

METODOS_PAGO = ["Efectivo", "Transferencia", "Mercado Pago", "Tarjeta", "Otro"]

CONFIG_DEFAULT = [
    ("nombre_estudio", "Nombre del estudio", None),
    ("telefono", "Teléfono de contacto", None),
    ("email", "Email de contacto", None),
    ("direccion", "Dirección", None),
    ("moneda", "Símbolo de moneda", "$"),
    ("sesion_horas", "Duración estándar de sesión (horas)", "12"),
]


def seed_actividades(conn) -> None:
    for nombre, desc, dur, precio in ACTIVIDADES:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO actividades (nombre, descripcion, duracion_minutos, precio)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (nombre) DO NOTHING
                """,
                (nombre, desc, dur, precio),
            )
    print(f"  - Actividades: {len(ACTIVIDADES)}")


def seed_metodos_pago(conn) -> None:
    for nombre in METODOS_PAGO:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO metodos_pago (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING",
                (nombre,),
            )
    print(f"  - Métodos de pago: {len(METODOS_PAGO)}")


def seed_config(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO configuracion (clave, valor, descripcion)
            VALUES (%s, %s, %s)
            ON CONFLICT (clave) DO NOTHING
            """,
            ("nombre_estudio", Config.NOMBRE_ESTUDIO, "Nombre del estudio"),
        )
        for clave, desc, valor in CONFIG_DEFAULT:
            if clave == "nombre_estudio":
                continue
            if clave == "sesion_horas":
                valor = valor or str(Config.SESION_HORAS)
            if clave == "moneda":
                valor = valor or Config.MONEDA
            cur.execute(
                """
                INSERT INTO configuracion (clave, valor, descripcion)
                VALUES (%s, %s, %s)
                ON CONFLICT (clave) DO NOTHING
                """,
                (clave, valor, desc),
            )
    print("  - Configuración por defecto")


def seed_admin(conn, email: str, password: str) -> None:
    existe = query_one("SELECT id FROM usuarios WHERE email = %s", (email,))
    if existe:
        print(f"  - Usuario admin '{email}' ya existe (id={existe['id']})")
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO usuarios (nombre, apellido, email, password_hash, rol,
                                  activo, debe_cambiar_password)
            VALUES (%s, %s, %s, %s, 'ADMIN', TRUE, TRUE)
            """,
            ("Admin", "Estudio", email, generate_password_hash(password)),
        )
    print(f"  - Usuario administrador creado: {email} (deberá cambiar su contraseña al ingresar)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed de datos iniciales")
    parser.add_argument("--admin-email", default="admin@estudio.com")
    parser.add_argument("--admin-pass", default="Admin123!")
    args = parser.parse_args()

    if not Config.DATABASE_URL:
        print("ERROR: falta DATABASE_URL en .env (ver .env.example).")
        sys.exit(1)

    print("Aplicando datos iniciales...")
    try:
        with get_conn() as conn:
            seed_actividades(conn)
            seed_metodos_pago(conn)
            seed_config(conn)
            seed_admin(conn, args.admin_email, args.admin_pass)
    finally:
        close_pool()
    print("Listo. Podés iniciar sesión con:")
    print(f"  email:    {args.admin_email}")
    print(f"  password: {args.admin_pass}  (cambialo tras el primer ingreso)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR en seed: {exc}")
        sys.exit(1)
