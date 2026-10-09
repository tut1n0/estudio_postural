"""Módulo de pagos: listado, registro, edición y ficha financiera."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from database import execute, query, query_one
from helpers import formatear_fecha, formatear_moneda, hoy, login_required, registrar_auditoria
from models import (
    ficha_financiera,
    listar_alumnos,
    listar_pagos,
    marcar_vencidos,
    obtener_alumno,
    resumen_pagos,
)

bp = Blueprint("pagos", __name__, url_prefix="/pagos")

ESTADOS = ("pagado", "pendiente", "vencido", "cancelado")


def _metodos() -> list[dict]:
    return query("SELECT * FROM metodos_pago WHERE activo ORDER BY nombre")


def _extraer_datos(form) -> tuple[dict, list[str]]:
    errores = []
    datos = {
        "alumno_id": form.get("alumno_id", type=int),
        "concepto": (form.get("concepto") or "").strip(),
        "monto": form.get("monto", type=float),
        "fecha_pago": form.get("fecha_pago") or None,
        "fecha_vencimiento": form.get("fecha_vencimiento") or None,
        "metodo_pago_id": form.get("metodo_pago_id", type=int),
        "estado": form.get("estado") or "pendiente",
        "observaciones": (form.get("observaciones") or "").strip() or None,
    }
    if not datos["alumno_id"]:
        errores.append("Seleccioná un alumno.")
    if not datos["concepto"]:
        errores.append("El concepto es obligatorio.")
    if datos["monto"] is None or datos["monto"] <= 0:
        errores.append("El monto debe ser mayor a cero.")
    if datos["estado"] not in ESTADOS:
        errores.append("Estado de pago no válido.")
    if datos["estado"] == "pagado" and not datos["fecha_pago"]:
        errores.append("Un pago 'pagado' requiere fecha de pago.")
    return datos, errores


@bp.route("/")
@login_required
def listado():
    marcar_vencidos()

    filtros = {
        "estado": request.args.get("estado", ""),
        "alumno_id": request.args.get("alumno", type=int),
        "metodo_id": request.args.get("metodo", type=int),
        "desde": request.args.get("desde") or None,
        "hasta": request.args.get("hasta") or None,
    }
    pagina = max(1, request.args.get("pagina", 1, type=int))
    resultado = listar_pagos(pagina=pagina, **filtros)

    return render_template(
        "pagos/listado.html",
        resultado=resultado,
        filtros=filtros,
        resumen=resumen_pagos(),
        metodos=_metodos(),
        alumnos=listar_alumnos(estado="activos", por_pagina=500)["filas"],
        formatear_fecha=formatear_fecha,
        formatear_moneda=formatear_moneda,
    )


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def nuevo():
    alumno_pre = request.args.get("alumno", type=int)
    if request.method == "POST":
        datos, errores = _extraer_datos(request.form)
        if errores:
            for e in errores:
                flash(e, "danger")
            return render_template(
                "pagos/form.html", datos=datos, modo="nuevo",
                alumnos=listar_alumnos(estado="activos", por_pagina=500)["filas"],
                metodos=_metodos(),
            ), 400
        fila = execute(
            """
            INSERT INTO pagos (alumno_id, concepto, monto, fecha_pago, fecha_vencimiento,
                               metodo_pago_id, estado, observaciones)
            VALUES (%(alumno_id)s, %(concepto)s, %(monto)s, %(fecha_pago)s,
                    %(fecha_vencimiento)s, %(metodo_pago_id)s, %(estado)s, %(observaciones)s)
            RETURNING id
            """,
            datos,
        )["row"]
        registrar_auditoria("crear", "pago", fila["id"],
                            f"{datos['concepto']} {formatear_moneda(datos['monto'])}")
        flash("Pago registrado correctamente.", "success")
        return redirect(url_for("pagos.listado"))

    datos = {"alumno_id": alumno_pre, "fecha_pago": str(hoy()), "estado": "pagado"}
    return render_template(
        "pagos/form.html", datos=datos, modo="nuevo",
        alumnos=listar_alumnos(estado="activos", por_pagina=500)["filas"],
        metodos=_metodos(),
    )


@bp.route("/<int:pago_id>/editar", methods=["GET", "POST"])
@login_required
def editar(pago_id):
    pago = query_one("SELECT * FROM pagos WHERE id = %s", (pago_id,))
    if not pago:
        abort(404)
    if request.method == "POST":
        datos, errores = _extraer_datos(request.form)
        if errores:
            for e in errores:
                flash(e, "danger")
            datos["id"] = pago_id
            return render_template(
                "pagos/form.html", datos=datos, modo="editar",
                alumnos=listar_alumnos(estado="activos", por_pagina=500)["filas"],
                metodos=_metodos(),
            ), 400
        execute(
            """
            UPDATE pagos SET
                alumno_id = %(alumno_id)s, concepto = %(concepto)s, monto = %(monto)s,
                fecha_pago = %(fecha_pago)s, fecha_vencimiento = %(fecha_vencimiento)s,
                metodo_pago_id = %(metodo_pago_id)s, estado = %(estado)s,
                observaciones = %(observaciones)s
            WHERE id = %(id)s
            """,
            {**datos, "id": pago_id},
        )
        registrar_auditoria("modificar", "pago", pago_id, datos["concepto"])
        flash("Pago actualizado.", "success")
        return redirect(url_for("pagos.listado"))
    return render_template(
        "pagos/form.html", datos=pago, modo="editar",
        alumnos=listar_alumnos(estado="activos", por_pagina=500)["filas"],
        metodos=_metodos(),
    )


@bp.route("/<int:pago_id>/marcar-pagado", methods=["POST"])
@login_required
def marcar_pagado(pago_id):
    pago = query_one("SELECT * FROM pagos WHERE id = %s", (pago_id,))
    if not pago:
        abort(404)
    execute(
        "UPDATE pagos SET estado = 'pagado', fecha_pago = COALESCE(fecha_pago, CURRENT_DATE) "
        "WHERE id = %s",
        (pago_id,),
    )
    registrar_auditoria("modificar", "pago", pago_id, "Marcado como pagado")
    flash("Pago marcado como pagado.", "success")
    return redirect(request.referrer or url_for("pagos.listado"))


@bp.route("/<int:pago_id>/eliminar", methods=["POST"])
@login_required
def eliminar(pago_id):
    pago = query_one("SELECT * FROM pagos WHERE id = %s", (pago_id,))
    if not pago:
        abort(404)
    execute("DELETE FROM pagos WHERE id = %s", (pago_id,))
    registrar_auditoria("eliminar", "pago", pago_id, pago["concepto"])
    flash("Pago eliminado.", "success")
    return redirect(url_for("pagos.listado"))


@bp.route("/alumno/<int:alumno_id>")
@login_required
def ficha(alumno_id):
    alumno = obtener_alumno(alumno_id)
    if not alumno:
        abort(404)
    return render_template(
        "pagos/ficha.html",
        alumno=alumno,
        finanzas=ficha_financiera(alumno_id),
        formatear_fecha=formatear_fecha,
        formatear_moneda=formatear_moneda,
    )
