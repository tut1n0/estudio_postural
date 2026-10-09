"""Capa de modelos: consultas SQL agrupadas por entidad.

Cada módulo expone funciones pequeñas que devuelven dicts/listas.
Las rutas nunca arman SQL crudo propio: pasan por acá.
"""

from __future__ import annotations

from typing import Any

from database import execute, query, query_one


# ------------------------------------------------------------
# Alumnos
# ------------------------------------------------------------

def listar_alumnos(buscar: str = "", actividad_id: int | None = None,
                   estado: str = "todos", pagina: int = 1,
                   por_pagina: int = 15, sin_asistencia: bool = False) -> dict:
    """Listado paginado con filtros. Devuelve {'filas', 'total', 'pagina', 'paginas'}."""
    condiciones: list[str] = ["TRUE"]
    params: list[Any] = []

    if buscar:
        condiciones.append(
            "(al.nombre ILIKE %s OR al.apellido ILIKE %s OR al.email ILIKE %s "
            "OR al.telefono ILIKE %s OR al.dni ILIKE %s)"
        )
        patron = f"%{buscar}%"
        params.extend([patron] * 5)
    if estado == "activos":
        condiciones.append("al.activo = TRUE")
    elif estado == "inactivos":
        condiciones.append("al.activo = FALSE")
    if actividad_id:
        condiciones.append(
            "EXISTS (SELECT 1 FROM inscripciones i JOIN horarios h ON h.id = i.horario_id "
            "WHERE i.alumno_id = al.id AND h.actividad_id = %s AND i.estado = 'activa')"
        )
        params.append(actividad_id)
    if sin_asistencia:
        condiciones.append(
            "NOT EXISTS (SELECT 1 FROM asistencias asis JOIN turnos t ON t.id = asis.turno_id "
            "WHERE asis.alumno_id = al.id AND t.fecha >= CURRENT_DATE - interval '30 days')"
        )

    where = " AND ".join(condiciones)
    total = query_one(f"SELECT COUNT(*) AS n FROM alumnos al WHERE {where}", params)["n"]

    offset = (pagina - 1) * por_pagina
    filas = query(
        f"""
        SELECT al.*,
               (SELECT string_agg(DISTINCT act.nombre, ', ' ORDER BY act.nombre)
                FROM inscripciones i
                JOIN horarios h ON h.id = i.horario_id
                JOIN actividades act ON act.id = h.actividad_id
                WHERE i.alumno_id = al.id AND i.estado = 'activa'
               ) AS actividades
        FROM alumnos al
        WHERE {where}
        ORDER BY al.apellido, al.nombre
        LIMIT %s OFFSET %s
        """,
        [*params, por_pagina, offset],
    )
    return {
        "filas": filas,
        "total": total,
        "pagina": pagina,
        "paginas": max(1, -(-total // por_pagina)),
    }


def obtener_alumno(alumno_id: int) -> dict | None:
    return query_one("SELECT * FROM alumnos WHERE id = %s", (alumno_id,))


def crear_alumno(datos: dict) -> dict:
    return execute(
        """
        INSERT INTO alumnos (nombre, apellido, dni, fecha_nacimiento, telefono, email,
                             direccion, contacto_emergencia, telefono_emergencia,
                             observaciones, fecha_alta)
        VALUES (%(nombre)s, %(apellido)s, %(dni)s, %(fecha_nacimiento)s, %(telefono)s,
                %(email)s, %(direccion)s, %(contacto_emergencia)s, %(telefono_emergencia)s,
                %(observaciones)s, %(fecha_alta)s)
        RETURNING id
        """,
        datos,
    )["row"]


def actualizar_alumno(alumno_id: int, datos: dict) -> None:
    datos = {**datos, "id": alumno_id}
    execute(
        """
        UPDATE alumnos SET
            nombre = %(nombre)s, apellido = %(apellido)s, dni = %(dni)s,
            fecha_nacimiento = %(fecha_nacimiento)s, telefono = %(telefono)s,
            email = %(email)s, direccion = %(direccion)s,
            contacto_emergencia = %(contacto_emergencia)s,
            telefono_emergencia = %(telefono_emergencia)s,
            observaciones = %(observaciones)s, activo = %(activo)s
        WHERE id = %(id)s
        """,
        datos,
    )


def alumno_duplicado(dni: str, email: str, excluir_id: int | None = None) -> str | None:
    """Devuelve 'dni' o 'email' si ya existe en otro alumno."""
    if dni:
        fila = query_one(
            "SELECT id FROM alumnos WHERE dni = %s AND id IS DISTINCT FROM %s",
            (dni, excluir_id),
        )
        if fila:
            return "dni"
    if email:
        fila = query_one(
            "SELECT id FROM alumnos WHERE lower(email) = lower(%s) AND id IS DISTINCT FROM %s",
            (email, excluir_id),
        )
        if fila:
            return "email"
    return None


def alumno_inscripto_en_horario(alumno_id: int, horario_id: int) -> bool:
    return bool(query_one(
        "SELECT id FROM inscripciones WHERE alumno_id = %s AND horario_id = %s AND estado = 'activa'",
        (alumno_id, horario_id),
    ))


def inscribir_alumno(alumno_id: int, horario_id: int, fecha_inicio: str,
                     fecha_fin: str | None = None, observaciones: str = "") -> dict:
    return execute(
        """
        INSERT INTO inscripciones (alumno_id, horario_id, fecha_inicio, fecha_fin, observaciones)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (alumno_id, horario_id, fecha_inicio, fecha_fin, observaciones),
    )["row"]


def inscripciones_del_alumno(alumno_id: int) -> list[dict]:
    return query(
        """
        SELECT i.*, h.dia_semana, h.hora_inicio, h.hora_fin, h.cupo_maximo, h.sala,
               a.nombre AS actividad, a.id AS actividad_id,
               p.nombre || ' ' || p.apellido AS profesor
        FROM inscripciones i
        JOIN horarios h ON h.id = i.horario_id
        JOIN actividades a ON a.id = h.actividad_id
        JOIN profesores p ON p.id = h.profesor_id
        WHERE i.alumno_id = %s
        ORDER BY i.estado = 'activa' DESC, h.dia_semana, h.hora_inicio
        """,
        (alumno_id,),
    )


def baja_inscripcion(inscripcion_id: int) -> None:
    execute(
        "UPDATE inscripciones SET estado = 'cancelada', fecha_fin = CURRENT_DATE "
        "WHERE id = %s AND estado = 'activa'",
        (inscripcion_id,),
    )


# ------------------------------------------------------------
# Actividades
# ------------------------------------------------------------

def listar_actividades(incluir_inactivas: bool = True) -> list[dict]:
    where = "" if incluir_inactivas else "WHERE activo = TRUE"
    return query(
        f"""
        SELECT a.*,
               (SELECT COUNT(*) FROM horarios h WHERE h.actividad_id = a.id AND h.activo) AS horarios_count
        FROM actividades a
        {where}
        ORDER BY a.nombre
        """
    )


def obtener_actividad(actividad_id: int) -> dict | None:
    return query_one("SELECT * FROM actividades WHERE id = %s", (actividad_id,))


# ------------------------------------------------------------
# Profesores
# ------------------------------------------------------------

def listar_profesores(incluir_inactivos: bool = True) -> list[dict]:
    where = "" if incluir_inactivos else "WHERE activo = TRUE"
    return query(
        f"""
        SELECT p.*,
               (SELECT COUNT(*) FROM horarios h WHERE h.profesor_id = p.id AND h.activo) AS horarios_count
        FROM profesores p
        {where}
        ORDER BY p.apellido, p.nombre
        """
    )


def obtener_profesor(profesor_id: int) -> dict | None:
    return query_one("SELECT * FROM profesores WHERE id = %s", (profesor_id,))


# ------------------------------------------------------------
# Horarios
# ------------------------------------------------------------

def grilla_horarios(activa: bool = True) -> list[dict]:
    where = "h.activo" if activa else "TRUE"
    return query(
        f"""
        SELECT h.*, a.nombre AS actividad, a.duracion_minutos,
               p.nombre || ' ' || p.apellido AS profesor,
               (SELECT COUNT(*) FROM inscripciones i
                WHERE i.horario_id = h.id AND i.estado = 'activa') AS inscriptos
        FROM horarios h
        JOIN actividades a ON a.id = h.actividad_id
        JOIN profesores p ON p.id = h.profesor_id
        WHERE {where}
        ORDER BY h.dia_semana, h.hora_inicio
        """
    )


def obtener_horario(horario_id: int) -> dict | None:
    return query_one(
        """
        SELECT h.*, a.nombre AS actividad, p.nombre || ' ' || p.apellido AS profesor
        FROM horarios h
        JOIN actividades a ON a.id = h.actividad_id
        JOIN profesores p ON p.id = h.profesor_id
        WHERE h.id = %s
        """,
        (horario_id,),
    )


# ------------------------------------------------------------
# Turnos
# ------------------------------------------------------------

def turnos_por_fecha(desde: str, hasta: str) -> list[dict]:
    return query(
        """
        SELECT t.*, h.dia_semana, h.cupo_maximo, h.sala,
               a.nombre AS actividad,
               p.nombre || ' ' || p.apellido AS profesor,
               (SELECT COUNT(*) FROM inscripciones i
                WHERE i.horario_id = h.id AND i.estado = 'activa'
                  AND i.fecha_inicio <= t.fecha
                  AND (i.fecha_fin IS NULL OR i.fecha_fin >= t.fecha)) AS inscriptos
        FROM turnos t
        JOIN horarios h ON h.id = t.horario_id
        JOIN actividades a ON a.id = h.actividad_id
        JOIN profesores p ON p.id = h.profesor_id
        WHERE t.fecha BETWEEN %s AND %s
        ORDER BY t.fecha, t.hora_inicio
        """,
        (desde, hasta),
    )


def obtener_turno(turno_id: int) -> dict | None:
    return query_one(
        """
        SELECT t.*, h.cupo_maximo, h.sala, h.actividad_id, h.profesor_id,
               a.nombre AS actividad,
               p.nombre || ' ' || p.apellido AS profesor
        FROM turnos t
        JOIN horarios h ON h.id = t.horario_id
        JOIN actividades a ON a.id = h.actividad_id
        JOIN profesores p ON p.id = h.profesor_id
        WHERE t.id = %s
        """,
        (turno_id,),
    )


def alumnos_inscriptos_al_turno(turno_id: int) -> list[dict]:
    return query(
        """
        SELECT al.id, al.nombre, al.apellido, al.telefono,
               asis.estado AS asistencia_estado, asis.id AS asistencia_id
        FROM turnos t
        JOIN inscripciones i ON i.horario_id = t.horario_id AND i.estado = 'activa'
        JOIN alumnos al ON al.id = i.alumno_id
        LEFT JOIN asistencias asis ON asis.turno_id = t.id AND asis.alumno_id = al.id
        WHERE t.id = %s AND i.fecha_inicio <= t.fecha
          AND (i.fecha_fin IS NULL OR i.fecha_fin >= t.fecha)
        ORDER BY al.apellido, al.nombre
        """,
        (turno_id,),
    )


def inscriptos_disponibles(horario_id: int) -> int:
    fila = query_one(
        """
        SELECT h.cupo_maximo - COUNT(i.id) AS disponibles
        FROM horarios h
        LEFT JOIN inscripciones i ON i.horario_id = h.id AND i.estado = 'activa'
        WHERE h.id = %s
        GROUP BY h.id, h.cupo_maximo
        """,
        (horario_id,),
    )
    return int(fila["disponibles"]) if fila else 0


def alumnos_inscriptos_en_horario(horario_id: int) -> list[dict]:
    """Alumnos con inscripción activa en el grupo (horario)."""
    return query(
        """
        SELECT al.id, al.nombre, al.apellido, al.telefono, al.dni,
               i.id AS inscripcion_id, i.fecha_inicio
        FROM inscripciones i
        JOIN alumnos al ON al.id = i.alumno_id
        WHERE i.horario_id = %s AND i.estado = 'activa'
        ORDER BY al.apellido, al.nombre
        """,
        (horario_id,),
    )


def alumnos_no_inscriptos_en_horario(horario_id: int, buscar: str = "") -> list[dict]:
    """Alumnos activos que aún no están inscriptos en el grupo (para agregar)."""
    condiciones = ["al.activo = TRUE"]
    params: list[Any] = []
    if buscar:
        condiciones.append(
            "(al.nombre ILIKE %s OR al.apellido ILIKE %s OR al.dni ILIKE %s)"
        )
        patron = f"%{buscar}%"
        params.extend([patron, patron, patron])
    where = " AND ".join(condiciones)
    return query(
        f"""
        SELECT al.id, al.nombre, al.apellido, al.telefono, al.dni
        FROM alumnos al
        WHERE {where}
          AND NOT EXISTS (
              SELECT 1 FROM inscripciones i
              WHERE i.alumno_id = al.id AND i.horario_id = %s AND i.estado = 'activa'
          )
        ORDER BY al.apellido, al.nombre
        """,
        [*params, horario_id],
    )


# ------------------------------------------------------------
# Asistencias
# ------------------------------------------------------------

def historial_asistencias(alumno_id: int, limite: int = 60) -> list[dict]:
    return query(
        """
        SELECT asis.*, t.fecha, t.hora_inicio, a.nombre AS actividad
        FROM asistencias asis
        JOIN turnos t ON t.id = asis.turno_id
        JOIN horarios h ON h.id = t.horario_id
        JOIN actividades a ON a.id = h.actividad_id
        WHERE asis.alumno_id = %s
        ORDER BY t.fecha DESC, t.hora_inicio DESC
        LIMIT %s
        """,
        (alumno_id, limite),
    )


def estadisticas_asistencia(alumno_id: int) -> dict:
    fila = query_one(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE estado = 'presente') AS presentes,
               COUNT(*) FILTER (WHERE estado = 'ausente') AS ausentes,
               COUNT(*) FILTER (WHERE estado = 'justificado') AS justificados
        FROM asistencias WHERE alumno_id = %s
        """,
        (alumno_id,),
    )
    total = fila["total"] or 0
    fila["porcentaje"] = round((fila["presentes"] / total) * 100, 1) if total else 0.0
    return fila


def registrar_asistencia(turno_id: int, alumno_id: int, estado: str,
                         observaciones: str = "") -> None:
    execute(
        """
        INSERT INTO asistencias (turno_id, alumno_id, estado, observaciones)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (turno_id, alumno_id)
        DO UPDATE SET estado = EXCLUDED.estado,
                      observaciones = EXCLUDED.observaciones,
                      updated_at = now()
        """,
        (turno_id, alumno_id, estado, observaciones),
    )


# ------------------------------------------------------------
# Pagos
# ------------------------------------------------------------

def listar_pagos(estado: str = "", alumno_id: int | None = None,
                 metodo_id: int | None = None, desde: str | None = None,
                 hasta: str | None = None, pagina: int = 1,
                 por_pagina: int = 20) -> dict:
    condiciones = ["TRUE"]
    params: list[Any] = []
    if estado:
        if estado == "vencido":
            condiciones.append("(p.estado = 'vencido' OR (p.estado = 'pendiente' AND p.fecha_vencimiento < CURRENT_DATE))")
        else:
            condiciones.append("p.estado = %s")
            params.append(estado)
    if alumno_id:
        condiciones.append("p.alumno_id = %s")
        params.append(alumno_id)
    if metodo_id:
        condiciones.append("p.metodo_pago_id = %s")
        params.append(metodo_id)
    if desde:
        condiciones.append("COALESCE(p.fecha_pago, p.fecha_vencimiento) >= %s")
        params.append(desde)
    if hasta:
        condiciones.append("COALESCE(p.fecha_pago, p.fecha_vencimiento) <= %s")
        params.append(hasta)

    where = " AND ".join(condiciones)
    total = query_one(f"SELECT COUNT(*) AS n FROM pagos p WHERE {where}", params)["n"]
    offset = (pagina - 1) * por_pagina
    filas = query(
        f"""
        SELECT p.*, al.nombre, al.apellido, m.nombre AS metodo_pago
        FROM pagos p
        JOIN alumnos al ON al.id = p.alumno_id
        LEFT JOIN metodos_pago m ON m.id = p.metodo_pago_id
        WHERE {where}
        ORDER BY COALESCE(p.fecha_vencimiento, p.fecha_pago) DESC, p.id DESC
        LIMIT %s OFFSET %s
        """,
        [*params, por_pagina, offset],
    )
    return {"filas": filas, "total": total, "pagina": pagina,
            "paginas": max(1, -(-total // por_pagina))}


def resumen_pagos() -> dict:
    mes = query_one(
        """
        SELECT COALESCE(SUM(monto), 0) AS total, COUNT(*) AS n
        FROM pagos
        WHERE estado = 'pagado'
          AND fecha_pago >= date_trunc('month', CURRENT_DATE)::date
        """
    )
    pendientes = query_one(
        "SELECT COALESCE(SUM(monto), 0) AS total, COUNT(*) AS n "
        "FROM pagos WHERE estado = 'pendiente'"
    )
    vencidos = query_one(
        "SELECT COALESCE(SUM(monto), 0) AS total, COUNT(*) AS n FROM pagos "
        "WHERE estado = 'vencido' OR (estado = 'pendiente' AND fecha_vencimiento < CURRENT_DATE)"
    )
    return {"mes": mes, "pendientes": pendientes, "vencidos": vencidos}


def ficha_financiera(alumno_id: int) -> dict:
    totales = query_one(
        """
        SELECT
            COALESCE(SUM(monto) FILTER (WHERE estado = 'pagado'), 0) AS total_pagado,
            COALESCE(SUM(monto) FILTER (WHERE estado = 'pendiente'), 0) AS total_pendiente,
            MAX(fecha_pago) FILTER (WHERE estado = 'pagado') AS ultimo_pago,
            MIN(fecha_vencimiento) FILTER (WHERE estado = 'pendiente') AS proximo_vencimiento
        FROM pagos WHERE alumno_id = %s
        """,
        (alumno_id,),
    )
    historial = query(
        """
        SELECT p.*, m.nombre AS metodo_pago
        FROM pagos p
        LEFT JOIN metodos_pago m ON m.id = p.metodo_pago_id
        WHERE p.alumno_id = %s
        ORDER BY COALESCE(p.fecha_pago, p.fecha_vencimiento) DESC, p.id DESC
        """,
        (alumno_id,),
    )
    return {"totales": totales, "historial": historial}


def marcar_vencidos() -> int:
    """Pasa a 'vencido' los pagos pendientes con fecha de vencimiento pasada."""
    return execute(
        "UPDATE pagos SET estado = 'vencido' "
        "WHERE estado = 'pendiente' AND fecha_vencimiento < CURRENT_DATE"
    )["rowcount"]


# ------------------------------------------------------------
# Configuración
# ------------------------------------------------------------

def obtener_config() -> dict:
    return {f["clave"]: f["valor"] for f in query("SELECT clave, valor FROM configuracion")}


def guardar_config(clave: str, valor: str) -> None:
    execute(
        """
        INSERT INTO configuracion (clave, valor, updated_at)
        VALUES (%s, %s, now())
        ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor, updated_at = now()
        """,
        (clave, valor),
    )
