"""Single-admin session authentication stored in SQLite."""

from functools import wraps

from flask import redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import AdminAccount

MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 80
MIN_PASSWORD_LENGTH = 8


def get_admin():
    """Return the stored administrator, if one exists.

    Returns:
        AdminAccount | None: The single admin row, or ``None``.
    """
    return AdminAccount.query.order_by(AdminAccount.id.asc()).first()


def admin_exists():
    """Return whether first-run setup has already been completed.

    Returns:
        bool: True when an admin account is present.
    """
    return get_admin() is not None


def hash_password(password):
    """Hash a plaintext password for storage.

    Args:
        password: Plaintext password.

    Returns:
        str: Werkzeug password hash.
    """
    return generate_password_hash(password)


def validate_username(username):
    """Validate a proposed administrator username.

    Args:
        username: Submitted username.

    Returns:
        str | None: Error message key, or ``None`` when valid.
    """
    name = (username or "").strip()
    if len(name) < MIN_USERNAME_LENGTH or len(name) > MAX_USERNAME_LENGTH:
        return "username_invalid"
    if any(ch.isspace() for ch in name):
        return "username_invalid"
    return None


def validate_password(password, confirm=None):
    """Validate a proposed administrator password.

    Args:
        password: Submitted password.
        confirm: Optional confirmation value that must match.

    Returns:
        str | None: Error message key, or ``None`` when valid.
    """
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return "password_too_short"
    if confirm is not None and password != confirm:
        return "password_mismatch"
    return None


def create_admin(username, password):
    """Persist the first administrator account.

    Args:
        username: Chosen username.
        password: Chosen plaintext password.

    Returns:
        AdminAccount: Newly stored account.
    """
    if get_admin() is not None:
        raise RuntimeError("administrator account already exists")
    account = AdminAccount(
        username=username.strip(),
        password_hash=hash_password(password),
    )
    db.session.add(account)
    db.session.commit()
    return account


def update_admin(account, username, password=None):
    """Update username and optionally password for the administrator.

    Args:
        account: Existing admin row.
        username: New username.
        password: Optional new plaintext password.

    Returns:
        AdminAccount: Updated account.
    """
    account.username = username.strip()
    if password:
        account.password_hash = hash_password(password)
    db.session.commit()
    return account


def verify_admin_credentials(username, password):
    """Check submitted credentials against the stored administrator.

    Args:
        username: Submitted username.
        password: Submitted password.

    Returns:
        bool: True when both values match the stored account.
    """
    account = get_admin()
    if account is None:
        return False
    user_ok = (username or "") == account.username
    pass_ok = check_password_hash(account.password_hash, password or "")
    return user_ok and pass_ok


def login_admin():
    """Mark the current session as an authenticated administrator."""
    session["logged_in"] = True
    session.permanent = True


def logout_admin():
    """Clear the administrator session flag."""
    session.pop("logged_in", None)


def is_logged_in():
    """Return whether the current session belongs to the administrator.

    Returns:
        bool: True when the admin session flag is set.
    """
    return bool(session.get("logged_in"))


def login_required(view):
    """Protect an admin view; send first-run users to setup.

    Args:
        view: Flask view function.

    Returns:
        callable: Wrapped view.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        """Redirect to setup or login when the session is anonymous."""
        if not admin_exists():
            return redirect(url_for("admin.setup"))
        if not is_logged_in():
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped
