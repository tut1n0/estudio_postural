"""Rutas de autenticación: /login, /logout y /cambiar-password."""

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import execute, query_one
from helpers import login_required, registrar_auditoria, verificar_csrf

bp = Blueprint("auth", __name__)

# Endpoints alcanzables antes de cambiar la contraseña obligatoria
RUTAS_PERMITIDAS_CAMBIO = {
    "auth.cambiar_password",
    "auth.logout",
    "static",
}


def guarda_flag_cambio_en_sesion() -> None:
    """Marca en la sesión si el usuario aún debe cambiar su contraseña."""
    if session.get("usuario"):
        usuario = query_one(
            "SELECT debe_cambiar_password FROM usuarios WHERE id = %s AND activo = TRUE",
            (session["usuario"]["id"],),
        )
        debe = bool(usuario and usuario["debe_cambiar_password"])
        session["debe_cambiar_password"] = debe


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("usuario"):
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        verificar_csrf()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Ingresá email y contraseña.", "warning")
            return render_template("login.html"), 400

        usuario = query_one(
            "SELECT * FROM usuarios WHERE lower(email) = %s AND activo = TRUE",
            (email,),
        )
        if not usuario or not check_password_hash(usuario["password_hash"], password):
            flash("Email o contraseña incorrectos.", "danger")
            return render_template("login.html"), 401

        session.clear()
        session["usuario"] = {
            "id": usuario["id"],
            "nombre": usuario["nombre"],
            "apellido": usuario["apellido"],
            "email": usuario["email"],
            "rol": usuario["rol"],
        }
        session["debe_cambiar_password"] = bool(usuario["debe_cambiar_password"])
        session.permanent = True
        g.usuario = session["usuario"]

        registrar_auditoria("login", "usuario", usuario["id"], f"Inicio de sesión de {email}")

        destino = request.args.get("next") or url_for("dashboard.index")
        if not destino.startswith("/"):
            destino = url_for("dashboard.index")
        if session["debe_cambiar_password"]:
            flash("Por seguridad, cambiá tu contraseña para continuar.", "warning")
            return redirect(url_for("auth.cambiar_password"))
        return redirect(destino)

    return render_template("login.html")


@bp.route("/logout", methods=["POST", "GET"])
@login_required
def logout():
    registrar_auditoria("logout", "usuario", session["usuario"]["id"], "Cierre de sesión")
    session.clear()
    flash("Cerraste sesión correctamente.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/cambiar-password", methods=["GET", "POST"])
def cambiar_password():
    """Cambio de contraseña (obligatorio en el primer ingreso de usuarios marcados)."""
    usuario = session.get("usuario")
    if not usuario:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        verificar_csrf()
        actual = request.form.get("password_actual") or ""
        nueva = request.form.get("password_nueva") or ""
        confirmacion = request.form.get("password_confirmacion") or ""

        # El hash nunca viaja en sesión: se consulta a la base
        fila = query_one("SELECT password_hash FROM usuarios WHERE id = %s", (usuario["id"],))
        if not fila or not check_password_hash(fila["password_hash"], actual):
            flash("La contraseña actual no es correcta.", "danger")
            return render_template("cambiar_password.html"), 400
        if len(nueva) < 8:
            flash("La nueva contraseña debe tener al menos 8 caracteres.", "danger")
            return render_template("cambiar_password.html"), 400
        if nueva != confirmacion:
            flash("La confirmación no coincide con la nueva contraseña.", "danger")
            return render_template("cambiar_password.html"), 400
        if nueva == actual:
            flash("La nueva contraseña debe ser distinta de la actual.", "danger")
            return render_template("cambiar_password.html"), 400

        execute(
            "UPDATE usuarios SET password_hash = %s, debe_cambiar_password = FALSE "
            "WHERE id = %s",
            (generate_password_hash(nueva), usuario["id"]),
        )
        session["debe_cambiar_password"] = False
        registrar_auditoria("modificar", "usuario", usuario["id"], "Cambio de contraseña")
        flash("Contraseña actualizada correctamente.", "success")
        return redirect(url_for("dashboard.index"))

    return render_template("cambiar_password.html")


def endpoint_permitido_sin_cambio() -> bool:
    """True si el endpoint actual puede usarse sin haber cambiado aún la contraseña."""
    if session.get("debe_cambiar_password") and request.endpoint not in RUTAS_PERMITIDAS_CAMBIO:
        return False
    return True
