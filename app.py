"""Application factory de Estudio Postural."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for

from config import Config
from helpers import verificar_csrf


def _configurar_logging(app: Flask) -> None:
    """Logs a archivo en producción; nada de errores internos al usuario."""
    if app.config.get("TESTING"):
        return
    logs_dir = Path(__file__).resolve().parent / "logs"
    try:
        logs_dir.mkdir(exist_ok=True)
        handler = RotatingFileHandler(
            logs_dir / "estudio.log", maxBytes=500_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        handler.setLevel(logging.WARNING)
        app.logger.addHandler(handler)
    except OSError:
        # En Vercel el filesystem es read-only: seguimos sin archivo de log
        app.logger.setLevel(logging.WARNING)


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    _configurar_logging(app)

    # Protección CSRF global para POST/PUT/DELETE
    @app.before_request
    def _csrf():
        if request.endpoint == "static":
            return
        verificar_csrf()

    # Bloquea el panel hasta cambiar la contraseña obligatoria del primer ingreso
    @app.before_request
    def _forzar_cambio_password():
        from routes.auth import endpoint_permitido_sin_cambio, guarda_flag_cambio_en_sesion

        if session.get("usuario") and "debe_cambiar_password" not in session:
            guarda_flag_cambio_en_sesion()
        if not endpoint_permitido_sin_cambio():
            flash("Primero cambiá tu contraseña para continuar.", "warning")
            return redirect(url_for("auth.cambiar_password"))

    # Context processor: datos globales en todos los templates
    @app.context_processor
    def inyectar_globales():
        from helpers import generar_token_csrf, hoy, usuario_actual

        fecha_hoy = hoy()
        return {
            "usuario": usuario_actual(),
            "csrf_token": generar_token_csrf(),
            "nombre_estudio": app.config["NOMBRE_ESTUDIO"],
            "moneda": app.config["MONEDA"],
            "hoy_texto": lambda: fecha_hoy.strftime("%A %d/%m/%Y"),
        }

    # Blueprints
    from routes import (
        actividades,
        asistencias,
        auth,
        buscador,
        configuracion,
        dashboard,
        horarios,
        alumnos,
        pagos,
        profesores,
        reportes,
        turnos,
        usuarios,
    )

    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(alumnos.bp)
    app.register_blueprint(actividades.bp)
    app.register_blueprint(profesores.bp)
    app.register_blueprint(horarios.bp)
    app.register_blueprint(turnos.bp)
    app.register_blueprint(asistencias.bp)
    app.register_blueprint(pagos.bp)
    app.register_blueprint(reportes.bp)
    app.register_blueprint(buscador.bp)
    app.register_blueprint(configuracion.bp)
    app.register_blueprint(usuarios.bp)

    # Errores
    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("403.html"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("404.html"), 404

    @app.errorhandler(400)
    def bad_request(_e):
        return render_template("400.html"), 400

    @app.errorhandler(500)
    def internal_error(_e):
        app.logger.exception("Error interno 500")
        return render_template("500.html"), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
