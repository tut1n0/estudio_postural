"""Calendario de turnos: vistas día/semana/mes e inscripción de alumnos."""

from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from database import execute, query, query_one
from helpers import (
    dia_semana_nombre,
    formatear_fecha,
    formatear_hora,
    login_required,
    registrar_auditoria,
    hoy,
)
from models import (
    alumnos_inscriptos_al_turno,
    alumnos_inscriptos_en_horario,
    alumnos_no_inscriptos_en_horario,
    inscriptos_disponibles,
    obtener_turno,
    turnos_por_fecha,
)

bp = Blueprint("turnos", __name__, url_prefix="/turnos")

ESTADOS_TURNO = ("programado", "confirmado", "cancelado", "completado")


def _parsear_fecha(valor: str | None) -> date:
    if valor:
        try:
            return datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError:
            pass
    return hoy()


def _rango_vista(vista: str, fecha: date) -> tuple[date, date, date]:
    """Devuelve (inicio, fin, fecha_centro) para la vista pedida."""
    if vista == "dia":
        return fecha, fecha, fecha
    if vista == "mes":
        inicio = fecha.replace(day=1)
        fin = inicio + timedelta(days=32)
        fin = fin.replace(day=1) - timedelta(days=1)
        return inicio, fin, fecha
    # semana (lunes a domingo)
    inicio = fecha - timedelta(days=fecha.weekday())
    fin = inicio + timedelta(days=6)
    return inicio, fin, fecha


def _destino(turno_id: int):
    """Vuelve a la pantalla de alumnos si el formulario lo pide; si no, al detalle."""
    if request.form.get("volver") == "alumnos":
        return redirect(url_for("turnos.alumnos", turno_id=turno_id))
    return redirect(url_for("turnos.detalle", turno_id=turno_id))


@bp.route("/")
@login_required
def calendario():
    vista = request.args.get("vista", "semana")
    if vista not in ("dia", "semana", "mes"):
        vista = "semana"
    fecha = _parsear_fecha(request.args.get("fecha"))
    inicio, fin, _ = _rango_vista(vista, fecha)

    turnos = turnos_por_fecha(str(inicio), str(fin))

    # Navegación anterior/siguiente
    if vista == "dia":
        delta = timedelta(days=1)
    elif vista == "mes":
        delta = timedelta(days=31)
    else:
        delta = timedelta(days=7)
    anterior = (fecha - delta).isoformat()
    siguiente = (fecha + delta).isoformat()

    # Vista de mes: celdas del calendario
    calendario_mes: list[list[dict | None]] = []
    if vista == "mes":
        primero = inicio
        celdas: list[date | None] = [None] * primero.weekday()
        dia_actual = primero
        while dia_actual <= fin:
            celdas.append(dia_actual)
            dia_actual += timedelta(days=1)
        while len(celdas) % 7:
            celdas.append(None)
        por_dia: dict[str, list[dict]] = {}
        for t in turnos:
            por_dia.setdefault(str(t["fecha"]), []).append(t)
        fila: list[dict | None] = []
        for celda in celdas:
            if celda is None:
                fila.append(None)
            else:
                fila.append({"fecha": celda, "turnos": por_dia.get(str(celda), [])})
            if len(fila) == 7:
                calendario_mes.append(fila)
                fila = []
        if fila:
            calendario_mes.append(fila)

    return render_template(
        "turnos/calendario.html",
        vista=vista,
        fecha=fecha,
        inicio=inicio,
        fin=fin,
        turnos=turnos,
        anterior=anterior,
        siguiente=siguiente,
        calendario_mes=calendario_mes,
        dias=["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
        dia_semana_nombre=dia_semana_nombre,
        formatear_hora=formatear_hora,
        hoy=hoy,
    )


@bp.route("/generar-semana", methods=["POST"])
@login_required
def generar_semana():
    """Crea los turnos de la semana de un horario a partir de hoy + días indicados."""
    horario_id = request.form.get("horario_id", type=int)
    cantidad = min(request.form.get("cantidad", type=int) or 7, 60)
    horario = query_one("SELECT * FROM horarios WHERE id = %s AND activo", (horario_id,))
    if not horario:
        flash("Horario no encontrado o inactivo.", "danger")
        return redirect(url_for("horarios.grilla"))

    creados = 0
    existentes = 0
    fecha = hoy()
    for _ in range(cantidad + 7):
        if fecha.weekday() + 1 == horario["dia_semana"]:
            fila = query_one(
                "SELECT id FROM turnos WHERE horario_id = %s AND fecha = %s",
                (horario_id, fecha),
            )
            if fila:
                existentes += 1
            else:
                execute(
                    """
                    INSERT INTO turnos (horario_id, fecha, hora_inicio, hora_fin)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (horario_id, fecha) DO NOTHING
                    """,
                    (horario_id, fecha, horario["hora_inicio"], horario["hora_fin"]),
                )
                creados += 1
        fecha += timedelta(days=1)
        if creados >= cantidad:
            break

    registrar_auditoria("crear", "turno", horario_id,
                        f"Generación masiva: {creados} turnos")
    flash(f"Turnos generados: {creados} nuevos, {existentes} ya existían.", "success")
    return redirect(url_for("turnos.calendario"))


@bp.route("/<int:turno_id>")
@login_required
def detalle(turno_id):
    turno = obtener_turno(turno_id)
    if not turno:
        abort(404)
    inscriptos = alumnos_inscriptos_al_turno(turno_id)
    disponibles = max(0, (turno["cupo_maximo"] or 0) - len(inscriptos))
    # Alumnos activos que pueden sumarse al grupo (aún no inscriptos)
    no_inscriptos = alumnos_no_inscriptos_en_horario(turno["horario_id"])
    return render_template(
        "turnos/detalle.html",
        turno=turno,
        inscriptos=inscriptos,
        disponibles=disponibles,
        no_inscriptos=no_inscriptos,
        formatear_hora=formatear_hora,
        formatear_fecha=formatear_fecha,
        hoy=hoy(),
    )


@bp.route("/<int:turno_id>/alumnos")
@login_required
def alumnos(turno_id):
    """Editar los alumnos del grupo desde una clase puntual."""
    turno = obtener_turno(turno_id)
    if not turno:
        abort(404)
    buscar = request.args.get("q", "").strip()
    inscriptos = alumnos_inscriptos_en_horario(turno["horario_id"])
    disponibles = inscriptos_disponibles(turno["horario_id"])
    no_inscriptos = alumnos_no_inscriptos_en_horario(turno["horario_id"], buscar)
    return render_template(
        "turnos/alumnos.html",
        turno=turno,
        inscriptos=inscriptos,
        disponibles=disponibles,
        no_inscriptos=no_inscriptos,
        buscar=buscar,
        formatear_hora=formatear_hora,
        formatear_fecha=formatear_fecha,
    )


@bp.route("/<int:turno_id>/estado", methods=["POST"])
@login_required
def cambiar_estado(turno_id):
    turno = obtener_turno(turno_id)
    if not turno:
        abort(404)
    estado = request.form.get("estado")
    if estado not in ESTADOS_TURNO:
        flash("Estado no válido.", "danger")
        return redirect(url_for("turnos.detalle", turno_id=turno_id))
    execute("UPDATE turnos SET estado = %s WHERE id = %s", (estado, turno_id))
    registrar_auditoria("modificar", "turno", turno_id, f"Estado: {estado}")
    flash(f"Turno marcado como {estado}.", "success")
    return redirect(url_for("turnos.detalle", turno_id=turno_id))


@bp.route("/<int:turno_id>/agregar-alumno", methods=["POST"])
@login_required
def agregar_alumno(turno_id):
    turno = obtener_turno(turno_id)
    if not turno:
        abort(404)
    alumno_id = request.form.get("alumno_id", type=int)
    if not alumno_id:
        flash("Seleccioná un alumno.", "warning")
        return _destino(turno_id)

    if inscriptos_disponibles(turno["horario_id"]) <= 0:
        flash("No hay cupos disponibles en este horario.", "danger")
        return _destino(turno_id)

    from models import alumno_inscripto_en_horario, inscribir_alumno

    if alumno_inscripto_en_horario(alumno_id, turno["horario_id"]):
        flash("El alumno ya está inscripto en este horario.", "warning")
    else:
        inscribir_alumno(alumno_id, turno["horario_id"], str(hoy()))
        registrar_auditoria("crear", "inscripcion", alumno_id,
                            f"Alta desde turno {turno_id}")
        flash("Alumno agregado al horario del turno.", "success")
    return _destino(turno_id)


@bp.route("/<int:turno_id>/quitar-alumno/<int:alumno_id>", methods=["POST"])
@login_required
def quitar_alumno(turno_id, alumno_id):
    turno = obtener_turno(turno_id)
    if not turno:
        abort(404)
    execute(
        "UPDATE inscripciones SET estado = 'cancelada', fecha_fin = CURRENT_DATE "
        "WHERE horario_id = %s AND alumno_id = %s AND estado = 'activa'",
        (turno["horario_id"], alumno_id),
    )
    registrar_auditoria("modificar", "inscripcion", alumno_id,
                        f"Baja desde turno {turno_id}")
    flash("Alumno quitado del horario.", "success")
    return _destino(turno_id)


@bp.route("/<int:turno_id>/eliminar", methods=["POST"])
@login_required
def eliminar(turno_id):
    turno = obtener_turno(turno_id)
    if not turno:
        abort(404)
    asistencias = query_one(
        "SELECT COUNT(*) AS n FROM asistencias WHERE turno_id = %s", (turno_id,)
    )["n"]
    if asistencias:
        flash(
            "El turno tiene asistencias registradas: no se eliminó. "
            "Si ya no se dicta, cancelalo.",
            "warning",
        )
        return redirect(url_for("turnos.detalle", turno_id=turno_id))
    execute("DELETE FROM turnos WHERE id = %s", (turno_id,))
    registrar_auditoria("eliminar", "turno", turno_id,
                        f"Eliminación de turno {turno['fecha']}")
    flash("Turno eliminado.", "success")
    return redirect(url_for("turnos.calendario", fecha=str(turno["fecha"])))
