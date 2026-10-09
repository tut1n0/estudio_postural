"""Dashboard principal con métricas, actividad del día y alertas."""

from flask import Blueprint, g, render_template

from database import query, query_one
from helpers import formatear_hora, hoy, login_required

bp = Blueprint("dashboard", __name__)


def _metricas(fecha) -> dict:
    alumnos_activos = query_one(
        "SELECT COUNT(*) AS n FROM alumnos WHERE activo = TRUE"
    )["n"]
    alumnos_nuevos_mes = query_one(
        """
        SELECT COUNT(*) AS n FROM alumnos
        WHERE fecha_alta >= date_trunc('month', %s::date)::date
        """,
        (fecha,),
    )["n"]
    turnos_hoy = query_one(
        "SELECT COUNT(*) AS n FROM turnos WHERE fecha = %s AND estado <> 'cancelado'",
        (fecha,),
    )["n"]
    presentes_hoy = query_one(
        """
        SELECT COUNT(*) AS n FROM asistencias a
        JOIN turnos t ON t.id = a.turno_id
        WHERE t.fecha = %s AND a.estado = 'presente'
        """,
        (fecha,),
    )["n"]
    pagos_mes = query_one(
        """
        SELECT COALESCE(SUM(monto), 0) AS total, COUNT(*) AS n FROM pagos
        WHERE estado = 'pagado'
          AND fecha_pago >= date_trunc('month', %s::date)::date
          AND fecha_pago <= date_trunc('month', %s::date)::date + interval '1 month - 1 day'
        """,
        (fecha, fecha),
    )
    pendientes = query_one(
        "SELECT COALESCE(SUM(monto), 0) AS total, COUNT(*) AS n "
        "FROM pagos WHERE estado = 'pendiente'"
    )
    vencidos = query_one(
        "SELECT COALESCE(SUM(monto), 0) AS total, COUNT(*) AS n "
        "FROM pagos WHERE estado = 'vencido' OR (estado = 'pendiente' AND fecha_vencimiento < %s)",
        (fecha,),
    )
    inscripciones_activas = query_one(
        "SELECT COUNT(*) AS n FROM inscripciones WHERE estado = 'activa'"
    )["n"]
    profesores_activos = query_one(
        "SELECT COUNT(*) AS n FROM profesores WHERE activo = TRUE"
    )["n"]

    return {
        "alumnos_activos": alumnos_activos,
        "alumnos_nuevos_mes": alumnos_nuevos_mes,
        "turnos_hoy": turnos_hoy,
        "presentes_hoy": presentes_hoy,
        "pagos_mes_total": pagos_mes["total"],
        "pagos_mes_cantidad": pagos_mes["n"],
        "pendientes_total": pendientes["total"],
        "pendientes_cantidad": pendientes["n"],
        "vencidos_total": vencidos["total"],
        "vencidos_cantidad": vencidos["n"],
        "inscripciones_activas": inscripciones_activas,
        "profesores_activos": profesores_activos,
    }


def _actividad_hoy(fecha) -> list[dict]:
    return query(
        """
        SELECT t.id, t.hora_inicio, t.hora_fin, t.estado,
               a.nombre AS actividad, p.nombre || ' ' || p.apellido AS profesor,
               h.cupo_maximo, h.sala,
               COUNT(i.id) FILTER (WHERE i.estado = 'activa') AS inscriptos
        FROM turnos t
        JOIN horarios h ON h.id = t.horario_id
        JOIN actividades a ON a.id = h.actividad_id
        JOIN profesores p ON p.id = h.profesor_id
        LEFT JOIN inscripciones i ON i.horario_id = h.id
             AND i.estado = 'activa'
             AND i.fecha_inicio <= t.fecha
             AND (i.fecha_fin IS NULL OR i.fecha_fin >= t.fecha)
        WHERE t.fecha = %s
        GROUP BY t.id, a.nombre, p.nombre, p.apellido, h.cupo_maximo, h.sala
        ORDER BY t.hora_inicio
        """,
        (fecha,),
    )


def _alertas(fecha) -> list[dict]:
    alertas: list[dict] = []

    vencidos = query_one(
        "SELECT COUNT(*) AS n FROM pagos WHERE estado = 'vencido' "
        "OR (estado = 'pendiente' AND fecha_vencimiento < %s)",
        (fecha,),
    )["n"]
    if vencidos:
        alertas.append({
            "tipo": "danger",
            "titulo": f"{vencidos} pago(s) vencido(s)",
            "texto": "Revisar cobranzas pendientes.",
            "url": "pagos.index",
            "parametros": {"estado": "vencido"},
        })

    llenos = query_one(
        """
        SELECT COUNT(*) AS n FROM (
            SELECT t.id
            FROM turnos t
            JOIN horarios h ON h.id = t.horario_id
            LEFT JOIN inscripciones i ON i.horario_id = h.id AND i.estado = 'activa'
            WHERE t.fecha >= %s AND t.estado <> 'cancelado'
            GROUP BY t.id, h.cupo_maximo
            HAVING COUNT(i.id) >= h.cupo_maximo
        ) sub
        """,
        (fecha,),
    )["n"]
    if llenos:
        alertas.append({
            "tipo": "warning",
            "titulo": f"{llenos} turno(s) al tope de cupo",
            "texto": "Verificá la lista de espera.",
            "url": "turnos.calendario",
            "parametros": {},
        })

    sin_asist = query_one(
        """
        SELECT COUNT(*) AS n FROM alumnos al
        WHERE al.activo = TRUE
          AND NOT EXISTS (
              SELECT 1 FROM asistencias asis
              JOIN turnos t ON t.id = asis.turno_id
              WHERE asis.alumno_id = al.id AND t.fecha >= %s - interval '30 days'
          )
          AND al.fecha_alta <= %s - interval '30 days'
        """,
        (fecha, fecha),
    )["n"]
    if sin_asist:
        alertas.append({
            "tipo": "info",
            "titulo": f"{sin_asist} alumno(s) sin asistencia reciente",
            "texto": "Sin clases registradas en los últimos 30 días.",
            "url": "alumnos.listado",
            "parametros": {"sin_asistencia": "1"},
        })

    por_vencer = query_one(
        """
        SELECT COUNT(*) AS n FROM inscripciones
        WHERE estado = 'activa'
          AND fecha_fin IS NOT NULL
          AND fecha_fin BETWEEN %s AND %s + interval '7 days'
        """,
        (fecha, fecha),
    )["n"]
    if por_vencer:
        alertas.append({
            "tipo": "warning",
            "titulo": f"{por_vencer} inscripción(es) por vencer",
            "texto": "Vencen en los próximos 7 días.",
            "url": "alumnos.listado",
            "parametros": {},
        })

    return alertas


@bp.route("/")
@login_required
def index():
    fecha = hoy()
    g.pagina = "dashboard"

    contexto = {
        "metricas": _metricas(fecha),
        "actividad_hoy": _actividad_hoy(fecha),
        "alertas": _alertas(fecha),
        "proximos_turnos": query(
            """
            SELECT t.fecha, t.hora_inicio, t.hora_fin, t.estado,
                   a.nombre AS actividad, h.sala,
                   p.nombre || ' ' || p.apellido AS profesor
            FROM turnos t
            JOIN horarios h ON h.id = t.horario_id
            JOIN actividades a ON a.id = h.actividad_id
            JOIN profesores p ON p.id = h.profesor_id
            WHERE t.fecha >= %s AND t.estado <> 'cancelado'
            ORDER BY t.fecha, t.hora_inicio
            LIMIT 8
            """,
            (fecha,),
        ),
    }
    # Formato de horas para la tabla
    for fila in contexto["actividad_hoy"]:
        fila["hora_inicio_f"] = formatear_hora(fila["hora_inicio"])
        fila["hora_fin_f"] = formatear_hora(fila["hora_fin"])

    return render_template("dashboard.html", **contexto)
