"""Configuración del estudio (clave/valor, sin hardcodear)."""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from database import query
from helpers import login_required, registrar_auditoria
from models import guardar_config, obtener_config

bp = Blueprint("configuracion", __name__, url_prefix="/configuracion")

CAMPOS = [
    ("nombre_estudio", "Nombre del estudio", "text"),
    ("telefono", "Teléfono", "text"),
    ("email", "Email", "email"),
    ("direccion", "Dirección", "text"),
    ("moneda", "Símbolo de moneda", "text"),
    ("sesion_horas", "Duración estándar de sesión (horas)", "number"),
]


def _metodos_pago() -> list[dict]:
    return query("SELECT * FROM metodos_pago ORDER BY nombre")


@bp.route("/", methods=["GET", "POST"])
@login_required
def editar():
    if request.method == "POST":
        if request.form.get("form") == "metodos":
            nombre = (request.form.get("nombre") or "").strip()
            if nombre:
                from database import execute

                execute(
                    "INSERT INTO metodos_pago (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING",
                    (nombre,),
                )
                registrar_auditoria("crear", "metodo_pago", None, nombre)
                flash("Método de pago agregado.", "success")
            return redirect(url_for("configuracion.editar"))

        for clave, _etiqueta, _tipo in CAMPOS:
            if clave in request.form:
                guardar_config(clave, (request.form.get(clave) or "").strip())
        registrar_auditoria("modificar", "configuracion", None, "Configuración actualizada")
        flash("Configuración guardada.", "success")
        return redirect(url_for("configuracion.editar"))

    return render_template(
        "configuracion/editar.html",
        config=obtener_config(),
        campos=CAMPOS,
        metodos=_metodos_pago(),
    )


@bp.route("/metodos/<int:metodo_id>/toggle", methods=["POST"])
@login_required
def toggle_metodo(metodo_id):
    from database import execute, query_one

    metodo = query_one("SELECT * FROM metodos_pago WHERE id = %s", (metodo_id,))
    if metodo:
        execute("UPDATE metodos_pago SET activo = NOT activo WHERE id = %s", (metodo_id,))
        registrar_auditoria("modificar", "metodo_pago", metodo_id, metodo["nombre"])
    return redirect(url_for("configuracion.editar"))
