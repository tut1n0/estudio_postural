"""CRUD de alumnos: listado, ficha, alta, edición y baja."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from helpers import (
    dia_semana_nombre,
    email_valido,
    formatear_fecha,
    formatear_moneda,
    hoy,
    login_required,
    registrar_auditoria,
)
from models import (
    alumno_duplicado,
    actualizar_alumno,
    baja_inscripcion,
    crear_alumno,
    estadisticas_asistencia,
    ficha_financiera,
    grilla_horarios,
    historial_asistencias,
    inscripciones_del_alumno,
    listar_actividades,
    listar_alumnos,
    obtener_alumno,
    obtener_horario,
)

bp = Blueprint("alumnos", __name__, url_prefix="/alumnos")

ESTADOS = {"todos", "activos", "inactivos"}


def _datos_formulario(form) -> tuple[dict, list[str]]:
    """Valida y extrae los datos del formulario. Devuelve (datos, errores)."""
    errores: list[str] = []
    datos = {
        "nombre": (form.get("nombre") or "").strip(),
        "apellido": (form.get("apellido") or "").strip(),
        "dni": (form.get("dni") or "").strip() or None,
        "fecha_nacimiento": form.get("fecha_nacimiento") or None,
        "telefono": (form.get("telefono") or "").strip() or None,
        "email": (form.get("email") or "").strip() or None,
        "direccion": (form.get("direccion") or "").strip() or None,
        "contacto_emergencia": (form.get("contacto_emergencia") or "").strip() or None,
        "telefono_emergencia": (form.get("telefono_emergencia") or "").strip() or None,
        "observaciones": (form.get("observaciones") or "").strip() or None,
        "fecha_alta": form.get("fecha_alta") or str(hoy()),
        "activo": form.get("activo", "1") == "1",
    }
    if not datos["nombre"]:
        errores.append("El nombre es obligatorio.")
    if not datos["apellido"]:
        errores.append("El apellido es obligatorio.")
    if datos["email"] and not email_valido(datos["email"]):
        errores.append("El email no es válido.")
    return datos, errores


@bp.route("/")
@login_required
def listado():
    buscar = (request.args.get("q") or "").strip()
    estado = request.args.get("estado", "todos")
    if estado not in ESTADOS:
        estado = "todos"
    actividad_id = request.args.get("actividad", type=int)
    sin_asistencia = request.args.get("sin_asistencia") == "1"
    pagina = max(1, request.args.get("pagina", 1, type=int))

    resultado = listar_alumnos(
        buscar=buscar, actividad_id=actividad_id, estado=estado,
        pagina=pagina, sin_asistencia=sin_asistencia,
    )
    return render_template(
        "alumnos/listado.html",
        resultado=resultado,
        buscar=buscar,
        estado=estado,
        actividad_id=actividad_id,
        sin_asistencia=sin_asistencia,
        actividades=listar_actividades(incluir_inactivas=False),
        formatear_fecha=formatear_fecha,
    )


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    if request.method == "POST":
        datos, errores = _datos_formulario(request.form)
        duplicado = alumno_duplicado(datos["dni"] or "", datos["email"] or "")
        if duplicado == "dni":
            errores.append("Ya existe un alumno con ese DNI.")
        elif duplicado == "email":
            errores.append("Ya existe un alumno con ese email.")

        if errores:
            for error in errores:
                flash(error, "danger")
            return render_template("alumnos/form.html", datos=datos, modo="nuevo"), 400

        fila = crear_alumno(datos)
        registrar_auditoria("crear", "alumno", fila["id"],
                            f"Alta de {datos['nombre']} {datos['apellido']}")
        flash("Alumno registrado correctamente.", "success")
        return redirect(url_for("alumnos.ficha", alumno_id=fila["id"]))

    return render_template("alumnos/form.html", datos={}, modo="nuevo")


@bp.route("/<int:alumno_id>")
@login_required
def ficha(alumno_id):
    alumno = obtener_alumno(alumno_id)
    if not alumno:
        abort(404)

    contexto = {
        "alumno": alumno,
        "inscripciones": inscripciones_del_alumno(alumno_id),
        "historial_asistencias": historial_asistencias(alumno_id),
        "estadisticas": estadisticas_asistencia(alumno_id),
        "finanzas": ficha_financiera(alumno_id),
        "horarios_disponibles": [
            h for h in grilla_horarios()
            if h["inscriptos"] < h["cupo_maximo"]
        ],
        "formatear_fecha": formatear_fecha,
        "formatear_moneda": formatear_moneda,
        "dia_semana_nombre": dia_semana_nombre,
        "hoy_iso": str(hoy()),
    }
    return render_template("alumnos/ficha.html", **contexto)


@bp.route("/<int:alumno_id>/editar", methods=["GET", "POST"])
@login_required
def editar(alumno_id):
    alumno = obtener_alumno(alumno_id)
    if not alumno:
        abort(404)

    if request.method == "POST":
        datos, errores = _datos_formulario(request.form)
        duplicado = alumno_duplicado(datos["dni"] or "", datos["email"] or "",
                                     excluir_id=alumno_id)
        if duplicado == "dni":
            errores.append("Otro alumno ya tiene ese DNI.")
        elif duplicado == "email":
            errores.append("Otro alumno ya tiene ese email.")

        if errores:
            for error in errores:
                flash(error, "danger")
            datos["id"] = alumno_id
            return render_template("alumnos/form.html", datos=datos, modo="editar"), 400

        actualizar_alumno(alumno_id, datos)
        registrar_auditoria("modificar", "alumno", alumno_id,
                            f"Edición de {datos['nombre']} {datos['apellido']}")
        flash("Alumno actualizado correctamente.", "success")
        return redirect(url_for("alumnos.ficha", alumno_id=alumno_id))

    return render_template("alumnos/form.html", datos=alumno, modo="editar")


@bp.route("/<int:alumno_id>/eliminar", methods=["POST"])
@login_required
def eliminar(alumno_id):
    alumno = obtener_alumno(alumno_id)
    if not alumno:
        abort(404)

    from database import execute

    # Baja lógica: nunca se borran datos de salud/pagos
    execute("UPDATE alumnos SET activo = FALSE WHERE id = %s", (alumno_id,))
    registrar_auditoria("eliminar", "alumno", alumno_id,
                        f"Baja lógica de {alumno['nombre']} {alumno['apellido']}")
    flash("Alumno dado de baja. Su historial se conserva.", "success")
    return redirect(url_for("alumnos.listado"))


@bp.route("/<int:alumno_id>/reactivar", methods=["POST"])
@login_required
def reactivar(alumno_id):
    alumno = obtener_alumno(alumno_id)
    if not alumno:
        abort(404)
    from database import execute

    execute("UPDATE alumnos SET activo = TRUE WHERE id = %s", (alumno_id,))
    registrar_auditoria("modificar", "alumno", alumno_id, f"Reactivación de {alumno['nombre']}")
    flash("Alumno reactivado.", "success")
    return redirect(url_for("alumnos.ficha", alumno_id=alumno_id))


@bp.route("/<int:alumno_id>/inscribir", methods=["POST"])
@login_required
def inscribir(alumno_id):
    from models import alumno_inscripto_en_horario, inscribir_alumno, inscriptos_disponibles

    alumno = obtener_alumno(alumno_id)
    if not alumno:
        abort(404)

    horario_id = request.form.get("horario_id", type=int)
    fecha_inicio = request.form.get("fecha_inicio") or str(hoy())
    fecha_fin = request.form.get("fecha_fin") or None

    horario = obtener_horario(horario_id) if horario_id else None
    if not horario or not horario["activo"]:
        flash("El horario seleccionado no existe o está inactivo.", "danger")
        return redirect(url_for("alumnos.ficha", alumno_id=alumno_id))

    if alumno_inscripto_en_horario(alumno_id, horario_id):
        flash("El alumno ya está inscripto en este horario.", "warning")
        return redirect(url_for("alumnos.ficha", alumno_id=alumno_id))

    if inscriptos_disponibles(horario_id) <= 0:
        flash("Este horario no tiene cupos disponibles.", "danger")
        return redirect(url_for("alumnos.ficha", alumno_id=alumno_id))

    inscribir_alumno(alumno_id, horario_id, fecha_inicio, fecha_fin)
    registrar_auditoria("crear", "inscripcion", alumno_id,
                        f"Inscripción a {horario['actividad']}")
    flash(f"Inscripción a {horario['actividad']} registrada.", "success")
    return redirect(url_for("alumnos.ficha", alumno_id=alumno_id))


@bp.route("/inscripcion/<int:inscripcion_id>/baja", methods=["POST"])
@login_required
def baja_inscripcion_route(inscripcion_id):
    from database import query_one

    insc = query_one("SELECT * FROM inscripciones WHERE id = %s", (inscripcion_id,))
    if not insc:
        abort(404)
    baja_inscripcion(inscripcion_id)
    registrar_auditoria("modificar", "inscripcion", inscripcion_id, "Baja de inscripción")
    flash("Inscripción dada de baja.", "success")
    return redirect(url_for("alumnos.ficha", alumno_id=insc["alumno_id"]))
