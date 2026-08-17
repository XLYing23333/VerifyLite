"""Public verify API and blob download links."""

import time
from io import BytesIO

from flask import Blueprint, current_app, jsonify, request, send_file, url_for
from itsdangerous import BadSignature, URLSafeSerializer

from app.defaults import FALLBACK_RESPONSES
from app.extensions import db
from app.models import BlobObject, LicenseKey, Project, Verification, VerifyLog, utcnow
from app.verify_engine import apply_success, build_variables, designed_response, evaluate_key

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def _serializer():
    """Build a serializer for blob download tokens.

    Tokens do not expire. Access is still limited to a signed payload
    issued after a successful verify.

    Returns:
        URLSafeSerializer: Serializer bound to the app secret.
    """
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="vl-blob")


def make_blob_token(blob_id, verification_id, key_id):
    """Create a download token for a blob.

    Args:
        blob_id: Stored blob primary key.
        verification_id: Scheme that authorized the download.
        key_id: License key that passed verification.

    Returns:
        str: URL-safe token with no expiry.
    """
    return _serializer().dumps(
        {"b": blob_id, "v": verification_id, "k": key_id},
    )


def _client_payload():
    """Read key and hwid from JSON, form, or query string.

    Returns:
        tuple: ``(key, hwid)`` strings.
    """
    data = request.get_json(silent=True) or {}
    key = data.get("key") or request.form.get("key") or request.args.get("key") or ""
    hwid = data.get("hwid") or request.form.get("hwid") or request.args.get("hwid") or ""
    return str(key).strip(), str(hwid).strip()


def _client_ip():
    """Best-effort client IP from proxy headers or the peer address.

    Returns:
        str: IP address string.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.remote_addr or "")[:64]


def _blob_urls(verification, key):
    """Build template blob URLs for objects on this scheme, project, or global.

    Args:
        verification: Current verification scheme.
        key: License key that succeeded.

    Returns:
        dict: Blob name to absolute download URL.
    """
    urls = {}
    for blob in BlobObject.visible_for(verification):
        token = make_blob_token(blob.id, verification.id, key.id)
        urls[blob.name] = url_for("api.download_blob", token=token, _external=True)
    return urls


def _write_log(verification, key, key_code, result, hwid, duration_ms):
    """Persist a verify-call log row.

    Args:
        verification: Scheme or ``None``.
        key: License key or ``None``.
        key_code: Submitted key string.
        result: Result code.
        hwid: Submitted hardware id.
        duration_ms: Handler duration in milliseconds.
    """
    if verification is None:
        return
    ua = (request.headers.get("User-Agent") or "")[:255]
    db.session.add(
        VerifyLog(
            verification_id=verification.id,
            key_id=key.id if key else None,
            key_code=key_code[:128],
            result=result,
            hwid=(hwid or None),
            ip=_client_ip(),
            user_agent=ua,
            duration_ms=duration_ms,
        )
    )


@api_bp.post("/<project_slug>/<verify_slug>")
def verify(project_slug, verify_slug):
    """Validate an uploaded key and return the designed JSON reply.

    Args:
        project_slug: Public project slug.
        verify_slug: Public verification slug.

    Returns:
        Response: JSON body designed in the admin editor.
    """
    started = time.perf_counter()
    key_code, hwid = _client_payload()
    now = utcnow()
    project = Project.query.filter_by(slug=project_slug).first()
    verification = None
    if project is not None:
        verification = Verification.query.filter_by(
            project_id=project.id,
            slug=verify_slug,
        ).first()
    key = None
    if verification is not None and key_code:
        key = LicenseKey.query.filter_by(
            verification_id=verification.id,
            key_code=key_code,
        ).first()
    result = evaluate_key(project, verification, key, hwid, now=now)
    blob_urls = {}
    if result == "success" and key is not None and verification is not None:
        apply_success(key, hwid, now=now)
        blob_urls = _blob_urls(verification, key)
    variables = build_variables(project, verification, key, hwid, now=now)
    payload = designed_response(verification, result, variables, blob_urls)
    duration_ms = int((time.perf_counter() - started) * 1000)
    _write_log(verification, key, key_code, result, hwid, duration_ms)
    db.session.commit()
    return jsonify(payload)


@api_bp.get("/blob/<token>")
def download_blob(token):
    """Download a blob authorized by a successful verify token.

    Args:
        token: Signed payload issued after a successful verify.

    Returns:
        Response: File bytes, or JSON error when the token is invalid.
    """
    try:
        data = _serializer().loads(token)
    except (BadSignature, TypeError, ValueError):
        return jsonify(FALLBACK_RESPONSES["invalid_key"]), 403
    blob = db.session.get(BlobObject, data.get("b"))
    key = db.session.get(LicenseKey, data.get("k"))
    verification = db.session.get(Verification, data.get("v"))
    if blob is None or key is None or verification is None:
        return jsonify(FALLBACK_RESPONSES["invalid_key"]), 403
    if key.verification_id != verification.id:
        return jsonify(FALLBACK_RESPONSES["invalid_key"]), 403
    if not blob.available_to(verification):
        return jsonify(FALLBACK_RESPONSES["invalid_key"]), 403
    return send_file(
        BytesIO(blob.data),
        mimetype=blob.content_type,
        as_attachment=True,
        download_name=blob.name,
    )
