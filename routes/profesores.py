"""CRUD de profesores/instructores."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from database import execute, query, query_one
from helpers import dia_semana_nombre, email_valido, formatear_hora, login_required, registrar_auditoria
from models import listar_profesores

bp = Blueprint("profesores", __name__, url_prefix="/profesores")


def _extraer_datos(form) -> tuple[dict, list[str]]:
    errores = []
    datos = {
        "nombre": (form.get("nombre") or "").strip(),
        "apellido": (form.get("apellido") or "").strip(),
        "telefono": (form.get("telefono") or "").strip() or None,
        "email": (form.get("email") or "").strip() or None,
        "especialidad": (form.get("especialidad") or "").strip() or None,
        "observaciones": (form.get("observaciones") or "").strip() or None,
        "activo": form.get("activo", "1") == "1",
    }
    if not datos["nombre"]:
        errores.append("El nombre es obligatorio.")
    if not datos["apellido"]:
        errores.append("El apellido es obligatorio.")
    if datos["email"] and not email_valido(datos["email"]):
        errores.append("El email no es válido.")
    return datos, errores


def _horarios_del_profesor(profesor_id: int) -> list[dict]:
    return query(
        """
        SELECT h.*, a.nombre AS actividad
        FROM horarios h
        JOIN actividades a ON a.id = h.actividad_id
        WHERE h.profesor_id = %s
        ORDER BY h.dia_semana, h.hora_inicio
        """,
        (profesor_id,),
    )


@bp.route("/")
@login_required
def listado():
    return render_template("profesores/listado.html", profesores=listar_profesores())


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    if request.method == "POST":
        datos, errores = _extraer_datos(request.form)
        if errores:
            for e in errores:
                flash(e, "danger")
            return render_template("profesores/form.html", datos=datos, modo="nuevo"), 400
        fila = execute(
            """
            INSERT INTO profesores (nombre, apellido, telefono, email, especialidad,
                                    observaciones, activo)
            VALUES (%(nombre)s, %(apellido)s, %(telefono)s, %(email)s, %(especialidad)s,
                    %(observaciones)s, %(activo)s)
            RETURNING id
            """,
            datos,
        )["row"]
        registrar_auditoria("crear", "profesor", fila["id"],
                            f"{datos['nombre']} {datos['apellido']}")
        flash("Profesor creado correctamente.", "success")
        return redirect(url_for("profesores.listado"))
    return render_template("profesores/form.html", datos={}, modo="nuevo")


@bp.route("/<int:profesor_id>")
@login_required
def ficha(profesor_id):
    profesor = query_one("SELECT * FROM profesores WHERE id = %s", (profesor_id,))
    if not profesor:
        abort(404)
    return render_template(
        "profesores/ficha.html",
        profesor=profesor,
        horarios=_horarios_del_profesor(profesor_id),
        dia_semana_nombre=dia_semana_nombre,
        formatear_hora=formatear_hora,
    )


@bp.route("/<int:profesor_id>/editar", methods=["GET", "POST"])
@login_required
def editar(profesor_id):
    profesor = query_one("SELECT * FROM profesores WHERE id = %s", (profesor_id,))
    if not profesor:
        abort(404)
    if request.method == "POST":
        datos, errores = _extraer_datos(request.form)
        duplicado = query_one(
            "SELECT id FROM profesores WHERE lower(email) = lower(%s) AND id <> %s AND email IS NOT NULL",
            (datos["email"] or "", profesor_id),
        )
        if datos["email"] and duplicado:
            errores.append("Otro profesor ya tiene ese email.")
        if errores:
            for e in errores:
                flash(e, "danger")
            datos["id"] = profesor_id
            return render_template("profesores/form.html", datos=datos, modo="editar"), 400
        execute(
            """
            UPDATE profesores SET nombre = %(nombre)s, apellido = %(apellido)s,
                telefono = %(telefono)s, email = %(email)s, especialidad = %(especialidad)s,
                observaciones = %(observaciones)s, activo = %(activo)s
            WHERE id = %(id)s
            """,
            {**datos, "id": profesor_id},
        )
        registrar_auditoria("modificar", "profesor", profesor_id, datos["nombre"])
        flash("Profesor actualizado.", "success")
        return redirect(url_for("profesores.ficha", profesor_id=profesor_id))
    return render_template("profesores/form.html", datos=profesor, modo="editar")


@bp.route("/<int:profesor_id>/eliminar", methods=["POST"])
@login_required
def eliminar(profesor_id):
    profesor = query_one("SELECT * FROM profesores WHERE id = %s", (profesor_id,))
    if not profesor:
        abort(404)
    en_uso = query_one("SELECT COUNT(*) AS n FROM horarios WHERE profesor_id = %s",
                       (profesor_id,))["n"]
    if en_uso:
        execute("UPDATE profesores SET activo = FALSE WHERE id = %s", (profesor_id,))
        flash("El profesor tiene horarios asignados: se marcó como inactivo.", "warning")
    else:
        execute("DELETE FROM profesores WHERE id = %s", (profesor_id,))
        flash("Profesor eliminado.", "success")
    registrar_auditoria("eliminar", "profesor", profesor_id,
                        f"{profesor['nombre']} {profesor['apellido']}")
    return redirect(url_for("profesores.listado"))
