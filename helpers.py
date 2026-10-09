"""Funciones compartidas: seguridad, roles, auditoría y formato argentino."""

from __future__ import annotations

import re
from datetime import date, datetime
from functools import wraps
from zoneinfo import ZoneInfo

from flask import abort, flash, g, redirect, request, session, url_for

from config import Config

TZ = ZoneInfo(Config.ZONA_HORARIA)

# ------------------------------------------------------------
# Seguridad / sesiones
# ------------------------------------------------------------


def usuario_actual() -> dict | None:
    """Devuelve el usuario logueado desde la sesión (o None)."""
    if "usuario" in g:
        return g.usuario
    g.usuario = session.get("usuario")
    return g.usuario


def login_required(vista):
    """Exige sesión iniciada para acceder a la vista."""

    @wraps(vista)
    def envuelta(*args, **kwargs):
        if usuario_actual() is None:
            flash("Iniciá sesión para acceder al panel.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return vista(*args, **kwargs)

    return envuelta


def rol_requerido(*roles):
    """Exige que el usuario tenga uno de los roles indicados."""

    def decorador(vista):
        @wraps(vista)
        def envuelta(*args, **kwargs):
            usuario = usuario_actual()
            if usuario is None:
                flash("Iniciá sesión para acceder al panel.", "warning")
                return redirect(url_for("auth.login", next=request.path))
            if usuario.get("rol") not in roles:
                abort(403)
            return vista(*args, **kwargs)

        return envuelta

    return decorador


def es_admin() -> bool:
    usuario = usuario_actual()
    return bool(usuario and usuario.get("rol") == "ADMIN")


# ------------------------------------------------------------
# CSRF (token simple en sesión para todos los POST)
# ------------------------------------------------------------


def generar_token_csrf() -> str:
    import secrets

    token = session.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["csrf_token"] = token
    return token


def verificar_csrf() -> None:
    """Aborta 400 si el token CSRF del formulario no coincide."""
    if request.method != "POST":
        return
    esperado = session.get("csrf_token")
    recibido = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not esperado or not recibido or esperado != recibido:
        abort(400)


# ------------------------------------------------------------
# Auditoría
# ------------------------------------------------------------


def registrar_auditoria(accion: str, entidad: str, entidad_id: int | None = None,
                        descripcion: str = "") -> None:
    """Registra una acción importante. Nunca lanza errores hacia el usuario."""
    from database import execute

    usuario = usuario_actual()
    try:
        execute(
            """
            INSERT INTO auditoria (usuario_id, accion, entidad, entidad_id, descripcion)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (usuario["id"] if usuario else None, accion, entidad, entidad_id, descripcion),
        )
    except Exception:  # noqa: BLE001
        # La auditoría no debe romper la operación principal
        pass


# ------------------------------------------------------------
# Formato argentino
# ------------------------------------------------------------


def hoy() -> date:
    return datetime.now(TZ).date()


def ahora() -> datetime:
    return datetime.now(TZ)


def formatear_fecha(valor) -> str:
    """DD/MM/YYYY."""
    if not valor:
        return "—"
    if isinstance(valor, str):
        try:
            valor = date.fromisoformat(valor)
        except ValueError:
            return valor
    if isinstance(valor, datetime):
        valor = valor.date()
    return valor.strftime("%d/%m/%Y")


def formatear_hora(valor) -> str:
    """HH:MM."""
    if not valor:
        return "—"
    if isinstance(valor, str):
        return valor[:5]
    return valor.strftime("%H:%M")


def formatear_moneda(monto) -> str:
    """$ 40.000 (formato argentino)."""
    if monto is None:
        return "—"
    numero = float(monto)
    entero = int(numero)
    decimales = abs(numero - entero)
    if decimales:
        texto = f"{entero:,}".replace(",", ".") + f",{int(decimales * 100):02d}"
    else:
        texto = f"{entero:,}".replace(",", ".")
    return f"{Config.MONEDA} {texto}"


DIAS_SEMANA = ["", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def dia_semana_nombre(n: int) -> str:
    return DIAS_SEMANA[n] if 1 <= n <= 7 else ""


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def email_valido(email: str | None) -> bool:
    return not email or bool(EMAIL_RE.match(email.strip()))


def solo_digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")
