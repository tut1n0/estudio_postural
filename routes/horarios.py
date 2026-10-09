"""Grilla semanal de horarios."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from database import execute, query_one
from helpers import dia_semana_nombre, login_required, registrar_auditoria
from models import grilla_horarios, listar_actividades, listar_profesores

bp = Blueprint("horarios", __name__, url_prefix="/horarios")

DIAS = list(range(1, 8))


def _extraer_datos(form) -> tuple[dict, list[str]]:
    errores = []
    datos = {
        "actividad_id": form.get("actividad_id", type=int),
        "profesor_id": form.get("profesor_id", type=int),
        "dia_semana": form.get("dia_semana", type=int),
        "hora_inicio": form.get("hora_inicio") or "",
        "hora_fin": form.get("hora_fin") or "",
        "cupo_maximo": form.get("cupo_maximo", type=int) or 8,
        "sala": (form.get("sala") or "").strip() or None,
        "activo": form.get("activo", "1") == "1",
    }
    if not datos["actividad_id"]:
        errores.append("Seleccioná una actividad.")
    if not datos["profesor_id"]:
        errores.append("Seleccioná un profesor.")
    if datos["dia_semana"] not in DIAS:
        errores.append("Seleccioná el día de la semana.")
    if not datos["hora_inicio"] or not datos["hora_fin"]:
        errores.append("Ingresá hora de inicio y fin.")
    elif datos["hora_fin"] <= datos["hora_inicio"]:
        errores.append("La hora de fin debe ser posterior a la de inicio.")
    if datos["cupo_maximo"] <= 0:
        errores.append("El cupo debe ser mayor a cero.")
    return datos, errores


def _hay_solapamiento(datos: dict, horario_id: int | None = None) -> bool:
    """True si otro horario activo se solapa en el mismo día y sala."""
    params: list = [datos["dia_semana"], horario_id]
    if datos["sala"]:
        condicion_sala = "AND sala = %s"
        params.append(datos["sala"])
    else:
        condicion_sala = "AND sala IS NULL"
    params.extend([datos["hora_inicio"], datos["hora_fin"]])
    sql = f"""
        SELECT id FROM horarios
        WHERE dia_semana = %s AND activo AND id IS DISTINCT FROM %s
          {condicion_sala}
          AND (hora_inicio, hora_fin) OVERLAPS (%s::time, %s::time)
    """
    return bool(query_one(sql, params))


@bp.route("/")
@login_required
def grilla():
    return render_template(
        "horarios/grilla.html",
        grilla=grilla_horarios(),
        dias=DIAS,
        dia_semana_nombre=dia_semana_nombre,
        actividades=listar_actividades(incluir_inactivas=False),
        profesores=listar_profesores(incluir_inactivos=False),
        filtro_actividad=request.args.get("actividad", type=int),
    )


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    if request.method == "POST":
        datos, errores = _extraer_datos(request.form)
        if not errores and _hay_solapamiento(datos):
            errores.append("Ya existe otro horario que se solapa en esa sala y día.")
        if errores:
            for e in errores:
                flash(e, "danger")
            return render_template(
                "horarios/form.html", datos=datos, modo="nuevo",
                actividades=listar_actividades(incluir_inactivas=False),
                profesores=listar_profesores(incluir_inactivos=False),
                dias=DIAS, dia_semana_nombre=dia_semana_nombre,
            ), 400
        fila = execute(
            """
            INSERT INTO horarios (actividad_id, profesor_id, dia_semana, hora_inicio,
                                  hora_fin, cupo_maximo, sala, activo)
            VALUES (%(actividad_id)s, %(profesor_id)s, %(dia_semana)s, %(hora_inicio)s,
                    %(hora_fin)s, %(cupo_maximo)s, %(sala)s, %(activo)s)
            RETURNING id
            """,
            datos,
        )["row"]
        registrar_auditoria("crear", "horario", fila["id"],
                            f"{datos['dia_semana']} {datos['hora_inicio']}")
        flash("Horario creado correctamente.", "success")
        return redirect(url_for("horarios.grilla"))
    return render_template(
        "horarios/form.html", datos={}, modo="nuevo",
        actividades=listar_actividades(incluir_inactivas=False),
        profesores=listar_profesores(incluir_inactivos=False),
        dias=DIAS, dia_semana_nombre=dia_semana_nombre,
    )


@bp.route("/<int:horario_id>/editar", methods=["GET", "POST"])
@login_required
def editar(horario_id):
    horario = query_one("SELECT * FROM horarios WHERE id = %s", (horario_id,))
    if not horario:
        abort(404)
    if request.method == "POST":
        datos, errores = _extraer_datos(request.form)
        if not errores and _hay_solapamiento(datos, horario_id):
            errores.append("Ya existe otro horario que se solapa en esa sala y día.")
        if errores:
            for e in errores:
                flash(e, "danger")
            datos["id"] = horario_id
            return render_template(
                "horarios/form.html", datos=datos, modo="editar",
                actividades=listar_actividades(incluir_inactivas=False),
                profesores=listar_profesores(incluir_inactivos=False),
                dias=DIAS, dia_semana_nombre=dia_semana_nombre,
            ), 400
        execute(
            """
            UPDATE horarios SET
                actividad_id = %(actividad_id)s, profesor_id = %(profesor_id)s,
                dia_semana = %(dia_semana)s, hora_inicio = %(hora_inicio)s,
                hora_fin = %(hora_fin)s, cupo_maximo = %(cupo_maximo)s,
                sala = %(sala)s, activo = %(activo)s
            WHERE id = %(id)s
            """,
            {**datos, "id": horario_id},
        )
        registrar_auditoria("modificar", "horario", horario_id, "Edición de horario")
        flash("Horario actualizado.", "success")
        return redirect(url_for("horarios.grilla"))
    return render_template(
        "horarios/form.html", datos=horario, modo="editar",
        actividades=listar_actividades(incluir_inactivas=False),
        profesores=listar_profesores(incluir_inactivos=False),
        dias=DIAS, dia_semana_nombre=dia_semana_nombre,
    )


@bp.route("/<int:horario_id>/eliminar", methods=["POST"])
@login_required
def eliminar(horario_id):
    horario = query_one("SELECT * FROM horarios WHERE id = %s", (horario_id,))
    if not horario:
        abort(404)
    futuros = query_one(
        "SELECT COUNT(*) AS n FROM turnos WHERE horario_id = %s AND fecha >= CURRENT_DATE",
        (horario_id,),
    )["n"]
    if futuros:
        execute("UPDATE horarios SET activo = FALSE WHERE id = %s", (horario_id,))
        flash("El horario tiene turnos futuros: se desactivó.", "warning")
    else:
        execute("DELETE FROM horarios WHERE id = %s", (horario_id,))
        flash("Horario eliminado.", "success")
    registrar_auditoria("eliminar", "horario", horario_id, "Baja de horario")
    return redirect(url_for("horarios.grilla"))
