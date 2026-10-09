"""Reportes con filtros y datos para gráficos (Chart.js)."""

from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, request

from database import query, query_one
from helpers import (
    dia_semana_nombre,
    formatear_fecha,
    formatear_hora,
    formatear_moneda,
    hoy,
    login_required,
)
from models import listar_actividades, listar_profesores

bp = Blueprint("reportes", __name__, url_prefix="/reportes")


def _fecha(valor: str | None, default: date) -> date:
    if valor:
        try:
            return datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError:
            pass
    return default


@bp.route("/")
@login_required
def index():
    desde = _fecha(request.args.get("desde"), hoy() - timedelta(days=30))
    hasta = _fecha(request.args.get("hasta"), hoy())
    actividad_id = request.args.get("actividad", type=int)
    profesor_id = request.args.get("profesor", type=int)

    # Ingresos por mes (últimos 6 meses)
    ingresos_mes = query(
        """
        SELECT to_char(date_trunc('month', fecha_pago), 'MM/YYYY') AS mes,
               date_trunc('month', fecha_pago) AS orden,
               COALESCE(SUM(monto), 0) AS total
        FROM pagos
        WHERE estado = 'pagado' AND fecha_pago >= (CURRENT_DATE - interval '6 months')
        GROUP BY 1, 2 ORDER BY 2
        """
    )

    # Ingresos del período
    ingresos_periodo = query_one(
        """
        SELECT COALESCE(SUM(monto), 0) AS total, COUNT(*) AS n FROM pagos
        WHERE estado = 'pagado' AND fecha_pago BETWEEN %s AND %s
        """,
        (desde, hasta),
    )

    # Alumnos nuevos por período (por mes)
    alumnos_nuevos = query(
        """
        SELECT to_char(date_trunc('month', fecha_alta), 'MM/YYYY') AS mes,
               date_trunc('month', fecha_alta) AS orden, COUNT(*) AS n
        FROM alumnos
        WHERE fecha_alta BETWEEN %s AND %s
        GROUP BY 1, 2 ORDER BY 2
        """,
        (desde, hasta),
    )

    # Asistencia por actividad
    asistencia_actividad = query(
        """
        SELECT a.nombre AS actividad,
               COUNT(*) FILTER (WHERE asis.estado = 'presente') AS presentes,
               COUNT(*) FILTER (WHERE asis.estado = 'ausente') AS ausentes,
               COUNT(*) FILTER (WHERE asis.estado = 'justificado') AS justificados
        FROM asistencias asis
        JOIN turnos t ON t.id = asis.turno_id
        JOIN horarios h ON h.id = t.horario_id
        JOIN actividades a ON a.id = h.actividad_id
        WHERE t.fecha BETWEEN %s AND %s
          AND (%s::bigint IS NULL OR a.id = %s)
        GROUP BY a.nombre ORDER BY a.nombre
        """,
        (desde, hasta, actividad_id, actividad_id),
    )

    # Ocupación por horario
    ocupacion = query(
        """
        SELECT a.nombre AS actividad, h.dia_semana, h.hora_inicio, h.hora_fin,
               h.cupo_maximo, h.sala,
               p.nombre || ' ' || p.apellido AS profesor,
               (SELECT COUNT(*) FROM inscripciones i
                WHERE i.horario_id = h.id AND i.estado = 'activa') AS inscriptos
        FROM horarios h
        JOIN actividades a ON a.id = h.actividad_id
        JOIN profesores p ON p.id = h.profesor_id
        WHERE h.activo
          AND (%s::bigint IS NULL OR a.id = %s)
          AND (%s::bigint IS NULL OR p.id = %s)
        ORDER BY inscriptos DESC, a.nombre
        """,
        (actividad_id, actividad_id, profesor_id, profesor_id),
    )
    for fila in ocupacion:
        cupo = fila["cupo_maximo"] or 0
        fila["porcentaje"] = round((fila["inscriptos"] / cupo) * 100) if cupo else 0

    # Pagos pendientes / vencidos del período
    pendientes = query_one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(monto), 0) AS total FROM pagos WHERE estado = 'pendiente'"
    )
    vencidos = query_one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(monto), 0) AS total FROM pagos "
        "WHERE estado = 'vencido' OR (estado = 'pendiente' AND fecha_vencimiento < CURRENT_DATE)"
    )

    # Asistencia por alumno (top)
    asistencia_alumno = query(
        """
        SELECT al.nombre || ' ' || al.apellido AS alumno,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE asis.estado = 'presente') AS presentes,
               ROUND(100.0 * COUNT(*) FILTER (WHERE asis.estado = 'presente') / NULLIF(COUNT(*), 0), 1) AS porcentaje
        FROM asistencias asis
        JOIN alumnos al ON al.id = asis.alumno_id
        WHERE asis.created_at::date BETWEEN %s AND %s
        GROUP BY al.id, al.nombre, al.apellido
        ORDER BY porcentaje DESC NULLS LAST, total DESC
        LIMIT 15
        """,
        (desde, hasta),
    )

    return render_template(
        "reportes/index.html",
        desde=desde, hasta=hasta,
        actividad_id=actividad_id, profesor_id=profesor_id,
        ingresos_mes=ingresos_mes,
        ingresos_periodo=ingresos_periodo,
        alumnos_nuevos=alumnos_nuevos,
        asistencia_actividad=asistencia_actividad,
        asistencia_alumno=asistencia_alumno,
        ocupacion=ocupacion,
        pendientes=pendientes,
        vencidos=vencidos,
        actividades=listar_actividades(incluir_inactivas=False),
        profesores=listar_profesores(incluir_inactivos=False),
        formatear_fecha=formatear_fecha,
        formatear_moneda=formatear_moneda,
        dia_semana_nombre=dia_semana_nombre,
        formatear_hora=formatear_hora,
    )
