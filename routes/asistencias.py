"""Registro de asistencias por turno e historial."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from database import query, query_one
from helpers import formatear_fecha, formatear_hora, hoy, login_required, registrar_auditoria
from models import (
    alumnos_inscriptos_al_turno,
    estadisticas_asistencia,
    historial_asistencias,
    listar_alumnos,
    obtener_alumno,
    obtener_turno,
    registrar_asistencia,
)

bp = Blueprint("asistencias", __name__, url_prefix="/asistencias")

ESTADOS_ASISTENCIA = ("presente", "ausente", "justificado")


@bp.route("/")
@login_required
def pendientes():
    """Turnos de hoy (y recientes) con lista para tomar asistencia."""
    fecha = request.args.get("fecha") or str(hoy())
    turnos = query(
        """
        SELECT t.id, t.fecha, t.hora_inicio, t.hora_fin, t.estado,
               a.nombre AS actividad, h.sala, h.cupo_maximo,
               p.nombre || ' ' || p.apellido AS profesor,
               (SELECT COUNT(*) FROM asistencias asis WHERE asis.turno_id = t.id) AS marcadas,
               (SELECT COUNT(*) FROM inscripciones i
                WHERE i.horario_id = h.id AND i.estado = 'activa'
                  AND i.fecha_inicio <= t.fecha
                  AND (i.fecha_fin IS NULL OR i.fecha_fin >= t.fecha)) AS inscriptos
        FROM turnos t
        JOIN horarios h ON h.id = t.horario_id
        JOIN actividades a ON a.id = h.actividad_id
        JOIN profesores p ON p.id = h.profesor_id
        WHERE t.fecha = %s AND t.estado <> 'cancelado'
        ORDER BY t.hora_inicio
        """,
        (fecha,),
    )
    return render_template(
        "asistencias/pendientes.html",
        turnos=turnos,
        fecha=fecha,
        formatear_hora=formatear_hora,
        formatear_fecha=formatear_fecha,
    )


@bp.route("/turno/<int:turno_id>", methods=["GET", "POST"])
@login_required
def tomar(turno_id):
    turno = obtener_turno(turno_id)
    if not turno:
        abort(404)

    if request.method == "POST":
        alumnos = alumnos_inscriptos_al_turno(turno_id)
        registradas = 0
        for alumno in alumnos:
            estado = request.form.get(f"estado_{alumno['id']}")
            if estado in ESTADOS_ASISTENCIA:
                registrar_asistencia(turno_id, alumno["id"], estado,
                                     request.form.get(f"obs_{alumno['id']}", ""))
                registradas += 1
        registrar_auditoria("crear", "asistencia", turno_id,
                            f"{registradas} asistencias registradas")
        flash(f"Asistencia guardada ({registradas} alumno(s)).", "success")
        return redirect(url_for("asistencias.pendientes", fecha=str(turno["fecha"])))

    inscriptos = alumnos_inscriptos_al_turno(turno_id)
    return render_template(
        "asistencias/tomar.html",
        turno=turno,
        inscriptos=inscriptos,
        formatear_hora=formatear_hora,
        formatear_fecha=formatear_fecha,
    )


@bp.route("/alumno/<int:alumno_id>")
@login_required
def historial(alumno_id):
    alumno = obtener_alumno(alumno_id)
    if not alumno:
        abort(404)
    return render_template(
        "asistencias/historial.html",
        alumno=alumno,
        historial=historial_asistencias(alumno_id),
        estadisticas=estadisticas_asistencia(alumno_id),
        formatear_fecha=formatear_fecha,
        formatear_hora=formatear_hora,
    )
