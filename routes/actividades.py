"""CRUD de actividades (Terapia Postural, Pilates, Yoga...)."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from database import execute, query_one
from helpers import login_required, registrar_auditoria
from models import listar_actividades

bp = Blueprint("actividades", __name__, url_prefix="/actividades")


def _extraer_datos(form) -> tuple[dict, list[str]]:
    errores = []
    datos = {
        "nombre": (form.get("nombre") or "").strip(),
        "descripcion": (form.get("descripcion") or "").strip() or None,
        "duracion_minutos": form.get("duracion_minutos", type=int) or 60,
        "precio": form.get("precio", type=float) or 0,
        "activo": form.get("activo", "1") == "1",
    }
    if not datos["nombre"]:
        errores.append("El nombre de la actividad es obligatorio.")
    if datos["duracion_minutos"] <= 0 or datos["duracion_minutos"] > 240:
        errores.append("La duración debe estar entre 1 y 240 minutos.")
    if datos["precio"] < 0:
        errores.append("El precio no puede ser negativo.")
    return datos, errores


@bp.route("/")
@login_required
def listado():
    return render_template("actividades/listado.html", actividades=listar_actividades())


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    if request.method == "POST":
        datos, errores = _extraer_datos(request.form)
        if query_one("SELECT id FROM actividades WHERE lower(nombre) = lower(%s)",
                     (datos["nombre"],)):
            errores.append("Ya existe una actividad con ese nombre.")
        if errores:
            for e in errores:
                flash(e, "danger")
            return render_template("actividades/form.html", datos=datos, modo="nuevo"), 400
        fila = execute(
            """
            INSERT INTO actividades (nombre, descripcion, duracion_minutos, precio, activo)
            VALUES (%(nombre)s, %(descripcion)s, %(duracion_minutos)s, %(precio)s, %(activo)s)
            RETURNING id
            """,
            datos,
        )["row"]
        registrar_auditoria("crear", "actividad", fila["id"], datos["nombre"])
        flash("Actividad creada correctamente.", "success")
        return redirect(url_for("actividades.listado"))
    return render_template("actividades/form.html", datos={}, modo="nuevo")


@bp.route("/<int:actividad_id>/editar", methods=["GET", "POST"])
@login_required
def editar(actividad_id):
    actividad = query_one("SELECT * FROM actividades WHERE id = %s", (actividad_id,))
    if not actividad:
        abort(404)
    if request.method == "POST":
        datos, errores = _extraer_datos(request.form)
        duplicada = query_one(
            "SELECT id FROM actividades WHERE lower(nombre) = lower(%s) AND id <> %s",
            (datos["nombre"], actividad_id),
        )
        if duplicada:
            errores.append("Ya existe otra actividad con ese nombre.")
        if errores:
            for e in errores:
                flash(e, "danger")
            datos["id"] = actividad_id
            return render_template("actividades/form.html", datos=datos, modo="editar"), 400
        execute(
            """
            UPDATE actividades SET nombre = %(nombre)s, descripcion = %(descripcion)s,
                duracion_minutos = %(duracion_minutos)s, precio = %(precio)s, activo = %(activo)s
            WHERE id = %(id)s
            """,
            {**datos, "id": actividad_id},
        )
        registrar_auditoria("modificar", "actividad", actividad_id, datos["nombre"])
        flash("Actividad actualizada.", "success")
        return redirect(url_for("actividades.listado"))
    return render_template("actividades/form.html", datos=actividad, modo="editar")


@bp.route("/<int:actividad_id>/eliminar", methods=["POST"])
@login_required
def eliminar(actividad_id):
    actividad = query_one("SELECT * FROM actividades WHERE id = %s", (actividad_id,))
    if not actividad:
        abort(404)
    en_uso = query_one("SELECT COUNT(*) AS n FROM horarios WHERE actividad_id = %s",
                       (actividad_id,))["n"]
    if en_uso:
        execute("UPDATE actividades SET activo = FALSE WHERE id = %s", (actividad_id,))
        flash("La actividad tiene horarios asociados: se marcó como inactiva.", "warning")
    else:
        execute("DELETE FROM actividades WHERE id = %s", (actividad_id,))
        flash("Actividad eliminada.", "success")
    registrar_auditoria("eliminar", "actividad", actividad_id, actividad["nombre"])
    return redirect(url_for("actividades.listado"))
