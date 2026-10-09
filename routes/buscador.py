"""Buscador global: alumnos, profesores y turnos."""

from flask import Blueprint, render_template, request

from database import query
from helpers import formatear_fecha, formatear_hora, login_required

bp = Blueprint("buscador", __name__, url_prefix="/buscar")


@bp.route("/")
@login_required
def buscar():
    termino = (request.args.get("q") or "").strip()
    alumnos = []
    profesores = []
    turnos = []
    if termino:
        patron = f"%{termino}%"
        alumnos = query(
            """
            SELECT id, nombre, apellido, telefono, email, activo
            FROM alumnos
            WHERE nombre ILIKE %s OR apellido ILIKE %s OR dni ILIKE %s
               OR email ILIKE %s OR telefono ILIKE %s
            ORDER BY apellido, nombre LIMIT 20
            """,
            (patron, patron, patron, patron, patron),
        )
        profesores = query(
            """
            SELECT id, nombre, apellido, especialidad, activo
            FROM profesores
            WHERE nombre ILIKE %s OR apellido ILIKE %s OR especialidad ILIKE %s
            ORDER BY apellido LIMIT 20
            """,
            (patron, patron, patron),
        )
        turnos = query(
            """
            SELECT t.id, t.fecha, t.hora_inicio, t.hora_fin, t.estado,
                   a.nombre AS actividad, h.sala
            FROM turnos t
            JOIN horarios h ON h.id = t.horario_id
            JOIN actividades a ON a.id = h.actividad_id
            WHERE a.nombre ILIKE %s OR h.sala ILIKE %s
            ORDER BY t.fecha DESC, t.hora_inicio LIMIT 20
            """,
            (patron, patron),
        )
    return render_template(
        "buscador.html",
        termino=termino,
        alumnos=alumnos,
        profesores=profesores,
        turnos=turnos,
        formatear_fecha=formatear_fecha,
        formatear_hora=formatear_hora,
    )
