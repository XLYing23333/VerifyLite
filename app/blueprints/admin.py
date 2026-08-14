"""Server-rendered administrator console."""

import csv
import io
import json
import re
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from sqlalchemy import func
from werkzeug.utils import secure_filename

from app.auth import (
    admin_exists,
    create_admin,
    get_admin,
    login_admin,
    login_required,
    logout_admin,
    update_admin,
    validate_password,
    validate_username,
    verify_admin_credentials,
)
from app.defaults import (
    DEFAULT_CONFIG,
    DEFAULT_KEY_CHARSET,
    KEY_STATUS_ACTIVE,
    KEY_STATUS_REVOKED,
    LANG_EN,
    LANG_ZH,
    RESULT_CODES,
    SLUG_PATTERN,
    THEME_CHOICES,
    THEME_SYSTEM,
)
from app.extensions import db
from app.i18n import t
from app.keygen import generate_key_code
from app.models import (
    BlobObject,
    KeyBatch,
    LicenseKey,
    Project,
    Verification,
    VerifyLog,
    reset_database,
    utcnow,
)
from app.verify_engine import (
    normalize_config,
    parse_config,
    parse_iso_datetime,
    parse_unlimited_int,
    sync_columns_from_config,
)

admin_bp = Blueprint("admin", __name__)
SLUG_RE = re.compile(SLUG_PATTERN)
PER_PAGE = 30


def _safe_next(value):
    """Allow only relative next URLs after login.

    Args:
        value: Candidate redirect target.

    Returns:
        str: Safe path or the dashboard.
    """
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return url_for("admin.dashboard")


def _redirect_referrer(fallback):
    """Redirect to the same-origin referrer, else a fallback URL.

    Args:
        fallback: Path used when the referrer is missing or external.

    Returns:
        Response: Redirect response.
    """
    referrer = request.referrer or ""
    if referrer.startswith(request.host_url):
        return redirect(referrer)
    return redirect(fallback)


def _valid_slug(value):
    """Return whether a slug matches the public URL alphabet.

    Args:
        value: Candidate slug.

    Returns:
        bool: True when the slug is valid.
    """
    return bool(value and SLUG_RE.match(value))


def _int_or_none(raw):
    """Parse an optional integer form field.

    Args:
        raw: Raw form value.

    Returns:
        int | None: Parsed integer, or ``None`` when empty.
    """
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _load_project(project_id):
    """Load a project or abort with 404.

    Args:
        project_id: Primary key.

    Returns:
        Project: Loaded project.
    """
    project = db.session.get(Project, project_id)
    if project is None:
        abort(404)
    return project


def _load_pair(project_id, verification_id):
    """Load a project and nested verification or abort.

    Args:
        project_id: Project primary key.
        verification_id: Verification primary key.

    Returns:
        tuple: ``(project, verification)``.
    """
    project = _load_project(project_id)
    verification = db.session.get(Verification, verification_id)
    if verification is None or verification.project_id != project.id:
        abort(404)
    return project, verification


def _scheme_blobs(project, verification):
    """List blobs a scheme can reference (scheme, project, or global).

    Args:
        project: Parent project (kept for call-site compatibility).
        verification: Current verification scheme.

    Returns:
        list: BlobObject rows ordered by name.
    """
    return BlobObject.visible_for(verification)


def _blob_scope_options(projects):
    """Build ownership choices: all, each project, then each scheme.

    Args:
        projects: Projects in display order.

    Returns:
        list: ``(value, label)`` pairs excluding the all-scope option.
    """
    options = []
    for project in projects:
        options.append((f"p:{project.id}", project.name))
        for item in project.verifications.order_by(Verification.name.asc()):
            options.append((f"v:{item.id}", f"{project.name} / {item.name}"))
    return options


def _blob_scope_token(blob):
    """Encode a blob's ownership as a form value.

    Args:
        blob: BlobObject or ``None``.

    Returns:
        str: ``all``, ``p:<id>``, or ``v:<id>``.
    """
    if blob is None:
        return "all"
    if blob.verification_id:
        return f"v:{blob.verification_id}"
    if blob.project_id:
        return f"p:{blob.project_id}"
    return "all"


def _parse_blob_scope(raw):
    """Parse the ownership select into project and verification ids.

    Args:
        raw: Form value ``all``, ``p:<id>``, or ``v:<id>``.

    Returns:
        tuple: ``(project_id, verification_id)``, either of which may be ``None``.
    """
    token = (raw or "all").strip()
    if token in ("", "all"):
        return None, None
    kind, _, rest = token.partition(":")
    try:
        pk = int(rest)
    except ValueError:
        abort(400)
    if kind == "p":
        project = db.session.get(Project, pk)
        if project is None:
            abort(404)
        return project.id, None
    if kind == "v":
        verification = db.session.get(Verification, pk)
        if verification is None:
            abort(404)
        return verification.project_id, verification.id
    abort(400)


def _read_blob_upload(required):
    """Read an optional or required upload, enforcing the size cap.

    Args:
        required: When True, missing files flash an error.

    Returns:
        tuple: ``(payload, filename, content_type)`` or ``None`` on a
        validation error that already flashed a message.
    """
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        if required:
            flash(t("blob_missing_file"), "danger")
            return None
        return b"", "", ""
    payload = upload.read()
    if len(payload) > current_app.config["MAX_BLOB_SIZE"]:
        flash(t("blob_too_large"), "danger")
        return None
    return payload, secure_filename(upload.filename), upload.mimetype or "application/octet-stream"


def _render_blobs(edit_blob=None):
    """Render the blob manager, optionally with an ownership editor.

    Args:
        edit_blob: Blob being edited, or ``None`` for upload mode.

    Returns:
        Response: Blob manager HTML.
    """
    blobs = BlobObject.query.order_by(BlobObject.created_at.desc()).all()
    projects = Project.query.order_by(Project.name.asc()).all()
    return render_template(
        "blobs/list.html",
        blobs=blobs,
        projects=projects,
        scope_options=_blob_scope_options(projects),
        edit_blob=edit_blob,
        selected_scope=_blob_scope_token(edit_blob),
        max_blob_size=current_app.config["MAX_BLOB_SIZE"],
    )


def _response_extras(config):
    """Strip code/msg from each designed reply, leaving extra JSON fields.

    Args:
        config: Normalized verification config.

    Returns:
        dict: Result code to extra-field mapping.
    """
    extras = {}
    responses = config.get("responses") or {}
    for code in RESULT_CODES:
        item = responses.get(code) or {}
        extras[code] = {
            key: value
            for key, value in item.items()
            if key not in ("code", "msg")
        }
    return extras


def _render_editor(project, verification, config, config_json):
    """Render the verification dual editor.

    Args:
        project: Parent project.
        verification: Current verification scheme.
        config: Normalized config mapping.
        config_json: JSON text shown in the preview pane.

    Returns:
        Response: Editor HTML.
    """
    return render_template(
        "verifications/editor.html",
        project=project,
        verification=verification,
        config=config,
        config_json=config_json,
        result_codes=RESULT_CODES,
        blobs=_scheme_blobs(project, verification),
        extras=_response_extras(config),
    )


def _paginate(query, page):
    """Paginate a SQLAlchemy query.

    Args:
        query: SQLAlchemy query.
        page: 1-based page number.

    Returns:
        tuple: ``(items, page, pages, total)``.
    """
    page = max(int(page or 1), 1)
    total = query.count()
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    items = query.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()
    return items, page, pages, total


@admin_bp.get("/prefs/lang/<code>")
def set_lang(code):
    """Switch the UI language and return to the previous page.

    Args:
        code: ``zh`` or ``en``.

    Returns:
        Response: Redirect to the referrer.
    """
    session.permanent = True
    session["lang"] = LANG_ZH if code != LANG_EN else LANG_EN
    return redirect(request.referrer or url_for("admin.dashboard"))


@admin_bp.get("/prefs/theme/<name>")
def set_theme(name):
    """Switch theme (system / dark / WeLight) and return to the previous page.

    Args:
        name: ``system``, ``dark``, or ``welight``.

    Returns:
        Response: Redirect to the referrer.
    """
    session.permanent = True
    session["theme"] = name if name in THEME_CHOICES else THEME_SYSTEM
    return redirect(request.referrer or url_for("admin.dashboard"))


@admin_bp.route("/setup", methods=["GET", "POST"])
def setup():
    """Create the administrator account on first visit.

    Returns:
        Response: Setup form, or redirect after the account is created.
    """
    if admin_exists():
        return redirect(url_for("admin.login"))
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        error = validate_username(username) or validate_password(password, confirm)
        if error:
            flash(t(error), "danger")
            return render_template("setup.html", username=username.strip())
        create_admin(username, password)
        login_admin()
        flash(t("setup_done"), "success")
        return redirect(url_for("admin.dashboard"))
    return render_template("setup.html", username="")


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """Render and process the single-admin login form.

    Returns:
        Response: Login page or redirect into the console.
    """
    if not admin_exists():
        return redirect(url_for("admin.setup"))
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if verify_admin_credentials(username, password):
            login_admin()
            return redirect(_safe_next(request.form.get("next") or request.args.get("next")))
        flash(t("login_failed"), "danger")
    return render_template("login.html", next=request.args.get("next", ""))


@admin_bp.get("/logout")
def logout():
    """Clear the admin session and return to login.

    Returns:
        Response: Redirect to the login page.
    """
    logout_admin()
    if admin_exists():
        return redirect(url_for("admin.login"))
    return redirect(url_for("admin.setup"))


@admin_bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    """Change the administrator username and password.

    Returns:
        Response: Account form HTML or redirect after save.
    """
    account_row = get_admin()
    if account_row is None:
        return redirect(url_for("admin.setup"))
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        username = request.form.get("username", "")
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm", "")
        if not verify_admin_credentials(account_row.username, current_password):
            flash(t("current_password_wrong"), "danger")
            return render_template("account.html", admin_account=account_row)
        error = validate_username(username)
        if error:
            flash(t(error), "danger")
            return render_template("account.html", admin_account=account_row)
        if new_password or confirm:
            error = validate_password(new_password, confirm)
            if error:
                flash(t(error), "danger")
                return render_template("account.html", admin_account=account_row)
        update_admin(account_row, username, new_password or None)
        flash(t("account_updated"), "success")
        return redirect(url_for("admin.account"))
    return render_template("account.html", admin_account=account_row)


@admin_bp.post("/account/format")
@login_required
def account_format():
    """Erase all stored data and return to first-run admin setup.

    Returns:
        Response: Redirect to the setup page after wipe.
    """
    account_row = get_admin()
    if account_row is None:
        return redirect(url_for("admin.setup"))
    password = request.form.get("current_password", "")
    if not verify_admin_credentials(account_row.username, password):
        flash(t("current_password_wrong"), "danger")
        return redirect(url_for("admin.account"))
    reset_database()
    logout_admin()
    return redirect(url_for("admin.setup"))


def _optional_int(name):
    """Parse a positive integer query argument.

    Args:
        name: Query-string key.

    Returns:
        int | None: Parsed value, or ``None`` when missing/invalid.
    """
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _dashboard_scope():
    """Resolve dashboard project/verification filters.

    Returns:
        tuple: ``(project, verification, verification_ids)``. ``verification_ids``
        is ``None`` when the dashboard is unscoped (all projects).
    """
    project_id = _optional_int("project_id")
    verification_id = _optional_int("verification_id")
    project = db.session.get(Project, project_id) if project_id else None
    verification = db.session.get(Verification, verification_id) if verification_id else None
    if verification is not None:
        if project is not None and verification.project_id != project.id:
            verification = None
        else:
            project = verification.project
            return project, verification, [verification.id]
    if project is not None:
        ids = [
            row.id
            for row in Verification.query.filter_by(project_id=project.id).all()
        ]
        return project, None, ids
    return None, None, None


@admin_bp.get("/")
@login_required
def dashboard():
    """Render the usage dashboard.

    Returns:
        Response: Dashboard HTML.
    """
    now = utcnow()
    today = now.date()
    start_today = datetime(today.year, today.month, today.day)
    start_week = start_today - timedelta(days=6)
    project, verification, verification_ids = _dashboard_scope()

    if verification is not None:
        project_count = 1
        verification_count = 1
        key_count = LicenseKey.query.filter_by(verification_id=verification.id).count()
    elif project is not None:
        project_count = 1
        verification_count = len(verification_ids)
        if verification_ids:
            key_count = LicenseKey.query.filter(
                LicenseKey.verification_id.in_(verification_ids)
            ).count()
        else:
            key_count = 0
    else:
        project_count = Project.query.count()
        verification_count = Verification.query.count()
        key_count = LicenseKey.query.count()

    logs = VerifyLog.query
    day_expr = func.date(VerifyLog.created_at)
    chart_q = db.session.query(
        day_expr.label("day"),
        VerifyLog.result,
        func.count(VerifyLog.id),
    ).filter(VerifyLog.created_at >= start_week)
    if verification_ids is not None:
        if verification_ids:
            logs = logs.filter(VerifyLog.verification_id.in_(verification_ids))
            chart_q = chart_q.filter(VerifyLog.verification_id.in_(verification_ids))
        else:
            logs = logs.filter(VerifyLog.id == -1)
            chart_q = chart_q.filter(VerifyLog.id == -1)

    calls_today = logs.filter(VerifyLog.created_at >= start_today).count()
    success_today = logs.filter(
        VerifyLog.created_at >= start_today,
        VerifyLog.result == "success",
    ).count()
    rows = chart_q.group_by(day_expr, VerifyLog.result).all()
    labels = []
    success_series = []
    fail_series = []
    grouped = {}
    for day, result, count in rows:
        key = str(day)
        bucket = grouped.setdefault(key, {"success": 0, "fail": 0})
        if result == "success":
            bucket["success"] += count
        else:
            bucket["fail"] += count
    for offset in range(6, -1, -1):
        day = (start_today - timedelta(days=offset)).date().isoformat()
        labels.append(day[5:])
        bucket = grouped.get(day, {"success": 0, "fail": 0})
        success_series.append(bucket["success"])
        fail_series.append(bucket["fail"])
    recent_logs = logs.order_by(VerifyLog.created_at.desc()).limit(20).all()
    projects = Project.query.order_by(Project.name.asc()).all()
    verifications = (
        Verification.query.order_by(Verification.name.asc()).all()
    )
    return render_template(
        "dashboard.html",
        project_count=project_count,
        verification_count=verification_count,
        key_count=key_count,
        calls_today=calls_today,
        success_today=success_today,
        chart_labels=labels,
        chart_success=success_series,
        chart_fail=fail_series,
        recent_logs=recent_logs,
        projects=projects,
        verifications=verifications,
        selected_project_id=project.id if project else None,
        selected_verification_id=verification.id if verification else None,
    )


@admin_bp.get("/projects")
@login_required
def project_list():
    """List all projects.

    Returns:
        Response: Project list HTML.
    """
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template("projects/list.html", projects=projects)


@admin_bp.route("/projects/new", methods=["GET", "POST"])
@login_required
def project_new():
    """Create a project.

    Returns:
        Response: Form HTML or redirect.
    """
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        slug = (request.form.get("slug") or "").strip().lower()
        description = request.form.get("description") or ""
        enabled = request.form.get("enabled") == "on"
        if not name or not _valid_slug(slug):
            flash(t("slug_invalid"), "danger")
            return render_template("projects/form.html", project=None)
        if Project.query.filter_by(slug=slug).first():
            flash(t("slug_taken"), "danger")
            return render_template("projects/form.html", project=None)
        project = Project(name=name, slug=slug, description=description, enabled=enabled)
        db.session.add(project)
        db.session.commit()
        flash(t("created"), "success")
        return redirect(url_for("admin.verification_list", project_id=project.id))
    return render_template("projects/form.html", project=None)


@admin_bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def project_edit(project_id):
    """Update a project.

    Args:
        project_id: Project primary key.

    Returns:
        Response: Form HTML or redirect.
    """
    project = _load_project(project_id)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        slug = (request.form.get("slug") or "").strip().lower()
        project.description = request.form.get("description") or ""
        project.enabled = request.form.get("enabled") == "on"
        if not name or not _valid_slug(slug):
            flash(t("slug_invalid"), "danger")
            return render_template("projects/form.html", project=project)
        clash = Project.query.filter(Project.slug == slug, Project.id != project.id).first()
        if clash:
            flash(t("slug_taken"), "danger")
            return render_template("projects/form.html", project=project)
        project.name = name
        project.slug = slug
        db.session.commit()
        flash(t("saved"), "success")
        return redirect(url_for("admin.verification_list", project_id=project.id))
    return render_template("projects/form.html", project=project)


@admin_bp.post("/projects/<int:project_id>/delete")
@login_required
def project_delete(project_id):
    """Delete a project and nested records.

    Args:
        project_id: Project primary key.

    Returns:
        Response: Redirect to the project list.
    """
    project = _load_project(project_id)
    db.session.delete(project)
    db.session.commit()
    flash(t("deleted"), "success")
    return redirect(url_for("admin.project_list"))


@admin_bp.post("/projects/<int:project_id>/toggle")
@login_required
def project_toggle(project_id):
    """Enable or disable a project from the list.

    Args:
        project_id: Project primary key.

    Returns:
        Response: Redirect back to the project list.
    """
    project = _load_project(project_id)
    project.enabled = not project.enabled
    db.session.commit()
    flash(t("saved"), "success")
    return _redirect_referrer(url_for("admin.project_list"))


@admin_bp.get("/projects/<int:project_id>/verifications")
@login_required
def verification_list(project_id):
    """List verification schemes under a project.

    Args:
        project_id: Project primary key.

    Returns:
        Response: Verification list HTML.
    """
    project = _load_project(project_id)
    verifications = project.verifications.order_by(Verification.created_at.desc()).all()
    return render_template(
        "verifications/list.html",
        project=project,
        verifications=verifications,
    )


@admin_bp.route("/projects/<int:project_id>/verifications/new", methods=["GET", "POST"])
@login_required
def verification_new(project_id):
    """Create a verification scheme with default designed replies.

    Args:
        project_id: Project primary key.

    Returns:
        Response: Form HTML or redirect.
    """
    project = _load_project(project_id)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        slug = (request.form.get("slug") or "").strip().lower()
        enabled = request.form.get("enabled") == "on"
        if not name or not _valid_slug(slug):
            flash(t("slug_invalid"), "danger")
            return render_template("verifications/create.html", project=project)
        exists = Verification.query.filter_by(project_id=project.id, slug=slug).first()
        if exists:
            flash(t("slug_taken"), "danger")
            return render_template("verifications/create.html", project=project)
        verification = Verification(
            project_id=project.id,
            name=name,
            slug=slug,
            enabled=enabled,
            config_json=json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
        )
        sync_columns_from_config(verification)
        db.session.add(verification)
        db.session.commit()
        flash(t("created"), "success")
        return redirect(
            url_for(
                "admin.verification_edit",
                project_id=project.id,
                verification_id=verification.id,
            )
        )
    return render_template("verifications/create.html", project=project)


@admin_bp.route(
    "/projects/<int:project_id>/verifications/<int:verification_id>",
    methods=["GET", "POST"],
)
@login_required
def verification_edit(project_id, verification_id):
    """Edit scheme parameters via GUI and JSON preview.

    Args:
        project_id: Project primary key.
        verification_id: Verification primary key.

    Returns:
        Response: Dual-editor HTML or redirect.
    """
    project, verification = _load_pair(project_id, verification_id)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        slug = (request.form.get("slug") or "").strip().lower()
        enabled = request.form.get("enabled") == "on"
        raw_json = request.form.get("config_json") or ""
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            flash(t("config_invalid"), "danger")
            config = parse_config(verification.config_json)
            return _render_editor(project, verification, config, raw_json)
        if not name or not _valid_slug(slug):
            flash(t("slug_invalid"), "danger")
            config = normalize_config(parsed)
            return _render_editor(
                project,
                verification,
                config,
                json.dumps(config, ensure_ascii=False, indent=2),
            )
        clash = Verification.query.filter(
            Verification.project_id == project.id,
            Verification.slug == slug,
            Verification.id != verification.id,
        ).first()
        if clash:
            flash(t("slug_taken"), "danger")
            config = normalize_config(parsed)
            return _render_editor(
                project,
                verification,
                config,
                json.dumps(config, ensure_ascii=False, indent=2),
            )
        verification.name = name
        verification.slug = slug
        verification.enabled = enabled
        verification.config_json = json.dumps(normalize_config(parsed), ensure_ascii=False, indent=2)
        sync_columns_from_config(verification)
        db.session.commit()
        flash(t("saved"), "success")
        return redirect(
            url_for(
                "admin.verification_edit",
                project_id=project.id,
                verification_id=verification.id,
            )
        )
    config = parse_config(verification.config_json)
    return _render_editor(
        project,
        verification,
        config,
        json.dumps(config, ensure_ascii=False, indent=2),
    )


@admin_bp.post("/projects/<int:project_id>/verifications/<int:verification_id>/delete")
@login_required
def verification_delete(project_id, verification_id):
    """Delete a verification scheme.

    Args:
        project_id: Project primary key.
        verification_id: Verification primary key.

    Returns:
        Response: Redirect to the scheme list.
    """
    project, verification = _load_pair(project_id, verification_id)
    db.session.delete(verification)
    db.session.commit()
    flash(t("deleted"), "success")
    return redirect(url_for("admin.verification_list", project_id=project.id))


@admin_bp.post("/projects/<int:project_id>/verifications/<int:verification_id>/toggle")
@login_required
def verification_toggle(project_id, verification_id):
    """Enable or disable a verification scheme from the list.

    Args:
        project_id: Project primary key.
        verification_id: Verification primary key.

    Returns:
        Response: Redirect back to the scheme list.
    """
    project, verification = _load_pair(project_id, verification_id)
    verification.enabled = not verification.enabled
    db.session.commit()
    flash(t("saved"), "success")
    return _redirect_referrer(
        url_for("admin.verification_list", project_id=project.id)
    )


def _key_query(verification):
    """Build the key list query with optional search and status filters.

    Args:
        verification: Parent verification.

    Returns:
        Query: Filtered license-key query.
    """
    query = LicenseKey.query.filter_by(verification_id=verification.id)
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    if q:
        query = query.filter(LicenseKey.key_code.contains(q))
    if status in (KEY_STATUS_ACTIVE, KEY_STATUS_REVOKED):
        query = query.filter(LicenseKey.status == status)
    return query.order_by(LicenseKey.created_at.desc())


@admin_bp.get("/projects/<int:project_id>/verifications/<int:verification_id>/keys")
@login_required
def key_list(project_id, verification_id):
    """List keys and the batch-issue form.

    Args:
        project_id: Project primary key.
        verification_id: Verification primary key.

    Returns:
        Response: Key manager HTML.
    """
    project, verification = _load_pair(project_id, verification_id)
    items, page, pages, total = _paginate(_key_query(verification), request.args.get("page", 1))
    batches = verification.batches.order_by(KeyBatch.created_at.desc()).limit(20).all()
    return render_template(
        "keys/list.html",
        project=project,
        verification=verification,
        keys=items,
        page=page,
        pages=pages,
        total=total,
        batches=batches,
        charset=DEFAULT_KEY_CHARSET,
        q=request.args.get("q", ""),
        status=request.args.get("status", ""),
    )


@admin_bp.post("/projects/<int:project_id>/verifications/<int:verification_id>/keys/batch")
@login_required
def key_batch(project_id, verification_id):
    """Issue a batch of keys and show them for distribution.

    Args:
        project_id: Project primary key.
        verification_id: Verification primary key.

    Returns:
        Response: Batch result HTML.
    """
    project, verification = _load_pair(project_id, verification_id)
    max_batch = current_app.config["MAX_BATCH_KEYS"]
    try:
        count = int(request.form.get("count") or 0)
        length = int(request.form.get("length") or 16)
    except ValueError:
        abort(400)
    count = max(1, min(count, max_batch))
    length = max(4, min(length, 64))
    prefix = (request.form.get("prefix") or "").strip()
    charset = (request.form.get("charset") or DEFAULT_KEY_CHARSET).strip() or DEFAULT_KEY_CHARSET
    note = (request.form.get("note") or "").strip()
    ttl = _int_or_none(request.form.get("ttl_seconds"))
    raw_uses = request.form.get("max_uses")
    if ttl is None:
        ttl = verification.default_ttl_seconds
    if raw_uses in (None, ""):
        max_uses = verification.default_max_uses
    else:
        max_uses = parse_unlimited_int(raw_uses)
    valid_from = parse_iso_datetime(request.form.get("valid_from")) or verification.default_valid_from
    valid_until = parse_iso_datetime(request.form.get("valid_until")) or verification.default_valid_until
    batch = KeyBatch(
        verification_id=verification.id,
        count=count,
        prefix=prefix,
        key_length=length,
        charset=charset,
        ttl_seconds=ttl,
        max_uses=max_uses,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    db.session.add(batch)
    db.session.flush()
    issued = []
    existing = {
        row.key_code
        for row in LicenseKey.query.filter_by(verification_id=verification.id).all()
    }
    attempts = 0
    while len(issued) < count and attempts < count * 20:
        attempts += 1
        code = generate_key_code(prefix=prefix, length=length, charset=charset)
        if code in existing:
            continue
        existing.add(code)
        key = LicenseKey(
            verification_id=verification.id,
            batch_id=batch.id,
            key_code=code,
            status=KEY_STATUS_ACTIVE,
            ttl_seconds=ttl,
            max_uses=max_uses,
            valid_from=valid_from,
            valid_until=valid_until,
            note=note,
        )
        db.session.add(key)
        issued.append(code)
    db.session.commit()
    flash(t("keys_issued", n=len(issued)), "success")
    return render_template(
        "keys/batch_result.html",
        project=project,
        verification=verification,
        batch=batch,
        issued=issued,
    )


@admin_bp.get("/projects/<int:project_id>/verifications/<int:verification_id>/keys/export")
@login_required
def key_export(project_id, verification_id):
    """Export keys as CSV or TXT.

    Args:
        project_id: Project primary key.
        verification_id: Verification primary key.

    Returns:
        Response: Downloadable file.
    """
    project, verification = _load_pair(project_id, verification_id)
    fmt = (request.args.get("fmt") or "csv").lower()
    keys = _key_query(verification).all()
    if fmt == "txt":
        body = "\n".join(item.key_code for item in keys) + "\n"
        return Response(
            body,
            mimetype="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename={project.slug}-{verification.slug}.txt"
            },
        )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "key_code",
            "status",
            "ttl_seconds",
            "max_uses",
            "used_count",
            "valid_from",
            "valid_until",
            "hwid",
            "note",
            "batch_id",
            "created_at",
        ]
    )
    for item in keys:
        writer.writerow(
            [
                item.key_code,
                item.status,
                item.ttl_seconds or "",
                item.max_uses if item.max_uses is not None else "",
                item.used_count,
                item.valid_from or "",
                item.valid_until or "",
                item.hwid or "",
                item.note,
                item.batch_id or "",
                item.created_at,
            ]
        )
    return Response(
        buffer.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={project.slug}-{verification.slug}.csv"
        },
    )


@admin_bp.post(
    "/projects/<int:project_id>/verifications/<int:verification_id>/keys/<int:key_id>/revoke"
)
@login_required
def key_revoke(project_id, verification_id, key_id):
    """Revoke a single license key.

    Args:
        project_id: Project primary key.
        verification_id: Verification primary key.
        key_id: License key primary key.

    Returns:
        Response: Redirect to the key list.
    """
    project, verification = _load_pair(project_id, verification_id)
    key = db.session.get(LicenseKey, key_id)
    if key is None or key.verification_id != verification.id:
        abort(404)
    key.status = KEY_STATUS_REVOKED
    db.session.commit()
    flash(t("saved"), "success")
    return redirect(
        url_for("admin.key_list", project_id=project.id, verification_id=verification.id)
    )


@admin_bp.post(
    "/projects/<int:project_id>/verifications/<int:verification_id>/keys/<int:key_id>/toggle"
)
@login_required
def key_toggle(project_id, verification_id, key_id):
    """Toggle a license key between active and revoked.

    Args:
        project_id: Project primary key.
        verification_id: Verification primary key.
        key_id: License key primary key.

    Returns:
        Response: Redirect back to the key list.
    """
    project, verification = _load_pair(project_id, verification_id)
    key = db.session.get(LicenseKey, key_id)
    if key is None or key.verification_id != verification.id:
        abort(404)
    if key.status == KEY_STATUS_REVOKED:
        key.status = KEY_STATUS_ACTIVE
    else:
        key.status = KEY_STATUS_REVOKED
    db.session.commit()
    flash(t("saved"), "success")
    return _redirect_referrer(
        url_for("admin.key_list", project_id=project.id, verification_id=verification.id)
    )


@admin_bp.post(
    "/projects/<int:project_id>/verifications/<int:verification_id>/keys/batch/<int:batch_id>/revoke"
)
@login_required
def key_batch_revoke(project_id, verification_id, batch_id):
    """Revoke every key in a batch.

    Args:
        project_id: Project primary key.
        verification_id: Verification primary key.
        batch_id: Batch primary key.

    Returns:
        Response: Redirect to the key list.
    """
    project, verification = _load_pair(project_id, verification_id)
    batch = db.session.get(KeyBatch, batch_id)
    if batch is None or batch.verification_id != verification.id:
        abort(404)
    LicenseKey.query.filter_by(batch_id=batch.id).update(
        {LicenseKey.status: KEY_STATUS_REVOKED}
    )
    db.session.commit()
    flash(t("saved"), "success")
    return redirect(
        url_for("admin.key_list", project_id=project.id, verification_id=verification.id)
    )


@admin_bp.get("/projects/<int:project_id>/verifications/<int:verification_id>/logs")
@login_required
def log_list(project_id, verification_id):
    """Show verify-call logs for a scheme.

    Args:
        project_id: Project primary key.
        verification_id: Verification primary key.

    Returns:
        Response: Log list HTML.
    """
    project, verification = _load_pair(project_id, verification_id)
    query = verification.logs.order_by(VerifyLog.created_at.desc())
    result = (request.args.get("result") or "").strip()
    if result:
        query = query.filter(VerifyLog.result == result)
    items, page, pages, total = _paginate(query, request.args.get("page", 1))
    return render_template(
        "logs/list.html",
        project=project,
        verification=verification,
        logs=items,
        page=page,
        pages=pages,
        total=total,
        result=result,
        result_codes=RESULT_CODES,
    )


@admin_bp.route("/blobs", methods=["GET", "POST"])
@login_required
def blob_list():
    """Upload, list, and manage SQLite-backed blobs.

    Returns:
        Response: Blob manager HTML or redirect.
    """
    if request.method == "POST":
        uploaded = _read_blob_upload(required=True)
        if uploaded is None:
            return redirect(url_for("admin.blob_list"))
        payload, filename, content_type = uploaded
        name = (request.form.get("name") or "").strip() or filename or "blob"
        project_pk, verification_pk = _parse_blob_scope(request.form.get("scope"))
        blob = BlobObject(
            name=name,
            content_type=content_type,
            size=len(payload),
            data=payload,
            project_id=project_pk,
            verification_id=verification_pk,
        )
        db.session.add(blob)
        db.session.commit()
        flash(t("created"), "success")
        return redirect(url_for("admin.blob_list"))
    return _render_blobs()


@admin_bp.route("/blobs/<int:blob_id>/edit", methods=["GET", "POST"])
@login_required
def blob_edit(blob_id):
    """Change a blob's name, ownership, or file after upload.

    Args:
        blob_id: Blob primary key.

    Returns:
        Response: Editor HTML or redirect.
    """
    blob = db.session.get(BlobObject, blob_id)
    if blob is None:
        abort(404)
    if request.method == "POST":
        uploaded = _read_blob_upload(required=False)
        if uploaded is None:
            return redirect(url_for("admin.blob_edit", blob_id=blob.id))
        payload, filename, content_type = uploaded
        name = (request.form.get("name") or "").strip()
        if name:
            blob.name = name
        elif filename:
            blob.name = filename
        project_pk, verification_pk = _parse_blob_scope(request.form.get("scope"))
        blob.project_id = project_pk
        blob.verification_id = verification_pk
        if payload:
            blob.data = payload
            blob.size = len(payload)
            blob.content_type = content_type
        db.session.commit()
        flash(t("saved"), "success")
        return redirect(url_for("admin.blob_list"))
    return _render_blobs(edit_blob=blob)


@admin_bp.get("/blobs/<int:blob_id>/download")
@login_required
def blob_download(blob_id):
    """Download a blob from the admin console.

    Args:
        blob_id: Blob primary key.

    Returns:
        Response: File download.
    """
    blob = db.session.get(BlobObject, blob_id)
    if blob is None:
        abort(404)
    return send_file(
        io.BytesIO(blob.data),
        mimetype=blob.content_type,
        as_attachment=True,
        download_name=blob.name,
    )


@admin_bp.post("/blobs/<int:blob_id>/delete")
@login_required
def blob_delete(blob_id):
    """Delete a stored blob.

    Args:
        blob_id: Blob primary key.

    Returns:
        Response: Redirect to the blob list.
    """
    blob = db.session.get(BlobObject, blob_id)
    if blob is None:
        abort(404)
    db.session.delete(blob)
    db.session.commit()
    flash(t("deleted"), "success")
    return redirect(url_for("admin.blob_list"))
