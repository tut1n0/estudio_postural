"""Acceso a PostgreSQL/Supabase con psycopg 3.

- Pool de conexiones a nivel módulo (compatible con serverless: min_size=0).
- Funciones query()/execute() que manejan transacciones y cierran recursos.
"""

from __future__ import annotations

import atexit
from contextlib import contextmanager
from typing import Any, Iterable

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from config import Config

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Devuelve (y crea si hace falta) el pool de conexiones."""
    global _pool
    if _pool is None:
        if not Config.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL no está definida. Configurá el archivo .env (ver .env.example)."
            )
        _pool = ConnectionPool(
            conninfo=Config.DATABASE_URL,
            min_size=0,
            max_size=Config.POOL_MAX_SIZE,
            open=False,  # se abre en el primer uso
            kwargs={
                "row_factory": dict_row,
                "autocommit": False,
                # Opciones de sesión para Supabase/pgbouncer
                "options": "-c idle_in_transaction_session_timeout=10000",
            },
            max_idle=300,
            timeout=10,
        )
        _pool.open(wait=True, timeout=10)
    return _pool


@contextmanager
def get_conn():
    """Context manager con conexión del pool (commit/rollback automáticos)."""
    pool = get_pool()
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def query(sql: str, params: Iterable[Any] | dict | None = None) -> list[dict]:
    """SELECT: devuelve lista de filas como diccionarios."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            return cur.fetchall()


def query_one(sql: str, params: Iterable[Any] | dict | None = None) -> dict | None:
    """SELECT: devuelve la primera fila o None."""
    filas = query(sql, params)
    return filas[0] if filas else None


def execute(sql: str, params: Iterable[Any] | dict | None = None) -> dict:
    """INSERT/UPDATE/DELETE: devuelve {'rowcount': n, ...} con fila insertada si RETURNING."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return {"rowcount": cur.rowcount}
            fila = cur.fetchone()
            return {"rowcount": cur.rowcount, "row": fila}


def execute_many(sql: str, seq_params: list) -> int:
    """Ejecuta un mismo SQL con muchas tuplas de parámetros."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, seq_params)
            return cur.rowcount


def close_pool() -> None:
    """Cierra el pool (útil en tests o al terminar scripts)."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


atexit.register(close_pool)
