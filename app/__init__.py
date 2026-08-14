"""VerifyLite Flask application package."""

import json
from pathlib import Path

from flask import Flask, jsonify

from app.config import Config
from app.extensions import csrf, db
from app.i18n import get_locale, get_theme, t


def create_app(test_config=None):
    """Create and configure the Flask application.

    Args:
        test_config: Optional mapping used to override default config.

    Returns:
        Flask: Configured application instance.
    """
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    csrf.init_app(app)

    from app.blueprints.admin import admin_bp
    from app.blueprints.api import api_bp

    csrf.exempt(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @app.route("/healthz")
    def healthz():
        """Return a liveness probe payload."""
        return jsonify({"status": "ok"})

    @app.context_processor
    def inject_ui():
        """Expose i18n, theme, and auth helpers to all templates."""
        from app.auth import is_logged_in

        return {
            "t": t,
            "current_lang": get_locale(),
            "current_theme": get_theme(),
            "logged_in": is_logged_in(),
        }

    @app.template_filter("mask_key")
    def mask_key(value):
        """Mask a license key for compact log display.

        Args:
            value: Raw key string.

        Returns:
            str: Masked key.
        """
        text = value or ""
        if len(text) <= 8:
            return "****"
        return f"{text[:4]}****{text[-4:]}"

    @app.template_filter("response_extra")
    def response_extra(item):
        """Dump extra response fields (everything except code/msg) as JSON.

        Args:
            item: Response template mapping.

        Returns:
            str: Pretty-printed extra JSON object.
        """
        if not isinstance(item, dict):
            return "{}"
        extra = {key: val for key, val in item.items() if key not in ("code", "msg")}
        return json.dumps(extra, ensure_ascii=False, indent=2)

    @app.template_filter("filesize")
    def filesize(num_bytes):
        """Format a byte count using SI units (KB/MB/GB).

        Args:
            num_bytes: Size in bytes.

        Returns:
            str: Human-readable size.
        """
        try:
            size = int(num_bytes)
        except (TypeError, ValueError):
            return "0 B"
        if size < 0:
            size = 0
        units = ("B", "KB", "MB", "GB")
        value = float(size)
        unit = "B"
        for candidate in units:
            unit = candidate
            if value < 1000 or candidate == "GB":
                break
            value /= 1000
        if unit == "B":
            return f"{int(value)} B"
        return f"{value:.1f} {unit}"

    with app.app_context():
        from app import models  # noqa: F401

        db.create_all()

    return app
