"""Gestión de usuarios del sistema (solo ADMIN)."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from database import execute, query, query_one
from helpers import email_valido, formatear_fecha, login_required, registrar_auditoria, rol_requerido

bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")

ROLES = ("ADMIN", "RECEPCION")


@bp.route("/")
@login_required
@rol_requerido("ADMIN")
def listado():
    return render_template(
        "usuarios/listado.html",
        usuarios=query("SELECT * FROM usuarios ORDER BY apellido, nombre"),
        formatear_fecha=formatear_fecha,
    )


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@rol_requerido("ADMIN")
def nuevo():
    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        apellido = (request.form.get("apellido") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        rol = request.form.get("rol") or "RECEPCION"
        errores = []
        if not nombre or not apellido:
            errores.append("Nombre y apellido son obligatorios.")
        if not email_valido(email):
            errores.append("Email inválido.")
        if len(password) < 8:
            errores.append("La contraseña debe tener al menos 8 caracteres.")
        if rol not in ROLES:
            errores.append("Rol inválido.")
        if query_one("SELECT id FROM usuarios WHERE lower(email) = %s", (email,)):
            errores.append("Ya existe un usuario con ese email.")
        if errores:
            for e in errores:
                flash(e, "danger")
            return render_template("usuarios/form.html", datos=request.form, modo="nuevo",
                                   roles=ROLES), 400

        fila = execute(
            """
            INSERT INTO usuarios (nombre, apellido, email, password_hash, rol, activo)
            VALUES (%s, %s, %s, %s, %s, TRUE)
            RETURNING id
            """,
            (nombre, apellido, email, generate_password_hash(password), rol),
        )["row"]
        registrar_auditoria("crear", "usuario", fila["id"], f"{nombre} {apellido} ({rol})")
        flash("Usuario creado correctamente.", "success")
        return redirect(url_for("usuarios.listado"))
    return render_template("usuarios/form.html", datos={}, modo="nuevo", roles=ROLES)


@bp.route("/<int:usuario_id>/editar", methods=["GET", "POST"])
@login_required
@rol_requerido("ADMIN")
def editar(usuario_id):
    usuario = query_one("SELECT * FROM usuarios WHERE id = %s", (usuario_id,))
    if not usuario:
        abort(404)
    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        apellido = (request.form.get("apellido") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        rol = request.form.get("rol") or usuario["rol"]
        password = request.form.get("password") or ""
        activo = request.form.get("activo", "1") == "1"
        forzar_cambio = request.form.get("forzar_cambio") == "1"
        errores = []
        if not nombre or not apellido:
            errores.append("Nombre y apellido son obligatorios.")
        if not email_valido(email):
            errores.append("Email inválido.")
        if rol not in ROLES:
            errores.append("Rol inválido.")
        if query_one("SELECT id FROM usuarios WHERE lower(email) = %s AND id <> %s",
                     (email, usuario_id)):
            errores.append("Otro usuario ya tiene ese email.")
        if errores:
            for e in errores:
                flash(e, "danger")
            return render_template("usuarios/form.html", datos=request.form, modo="editar",
                                   roles=ROLES, usuario_id=usuario_id), 400

        if password:
            if len(password) < 8:
                flash("La contraseña debe tener al menos 8 caracteres.", "danger")
                return render_template("usuarios/form.html", datos=request.form,
                                       modo="editar", roles=ROLES, usuario_id=usuario_id), 400
            execute(
                "UPDATE usuarios SET nombre=%s, apellido=%s, email=%s, rol=%s, activo=%s, "
                "password_hash=%s, debe_cambiar_password=%s WHERE id=%s",
                (nombre, apellido, email, rol, activo, generate_password_hash(password),
                 forzar_cambio, usuario_id),
            )
        else:
            execute(
                "UPDATE usuarios SET nombre=%s, apellido=%s, email=%s, rol=%s, activo=%s, "
                "debe_cambiar_password=%s WHERE id=%s",
                (nombre, apellido, email, rol, activo, forzar_cambio, usuario_id),
            )
        registrar_auditoria("modificar", "usuario", usuario_id, f"{nombre} {apellido}")
        flash("Usuario actualizado.", "success")
        return redirect(url_for("usuarios.listado"))
    return render_template("usuarios/form.html", datos=usuario, modo="editar",
                           roles=ROLES, usuario_id=usuario_id)
