"""Pure verification rules and safe response-template rendering."""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from datetime import datetime, timedelta

from app.defaults import (
    DEFAULT_CONFIG,
    FALLBACK_RESPONSES,
    KEY_STATUS_ACTIVE,
    RESULT_CODES,
    TEMPLATE_VARS,
    UNLIMITED_TOKENS,
)
from app.models import utcnow

PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")
BLOB_URL_RE = re.compile(r"\{\{blob_url:([a-zA-Z0-9._-]+)\}\}")


def parse_config(raw):
    """Parse and normalize a verification config JSON document.

    Args:
        raw: JSON string or mapping.

    Returns:
        dict: Config merged onto ``DEFAULT_CONFIG``.
    """
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            data = {}
    return normalize_config(data)


def normalize_config(data):
    """Fill missing keys so GUI and engine always see a complete config.

    Args:
        data: Partial config mapping.

    Returns:
        dict: Complete config object.
    """
    if not isinstance(data, dict):
        data = {}
    merged = deepcopy(DEFAULT_CONFIG)
    merged["bind_hwid"] = bool(data.get("bind_hwid", merged["bind_hwid"]))
    incoming_defaults = data.get("defaults") or {}
    if isinstance(incoming_defaults, dict):
        for field in ("ttl_seconds", "max_uses", "valid_from", "valid_until"):
            if field in incoming_defaults:
                merged["defaults"][field] = incoming_defaults[field]
        merged["defaults"]["max_uses"] = parse_unlimited_int(
            merged["defaults"].get("max_uses")
        )
    incoming_responses = data.get("responses") or {}
    if isinstance(incoming_responses, dict):
        for code in RESULT_CODES:
            item = incoming_responses.get(code)
            if isinstance(item, dict) and item:
                merged["responses"][code] = item
    return merged


def parse_unlimited_int(value):
    """Parse a count that may be unlimited (empty, inf, infty, ∞, -1).

    Args:
        value: Integer, string token, or empty.

    Returns:
        int | None: Finite count, or ``None`` for unlimited.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return None if value < 0 else value
    if isinstance(value, float):
        if not math.isfinite(value) or value < 0:
            return None
        return int(value)
    text = str(value).strip().lower()
    if text in UNLIMITED_TOKENS:
        return None
    try:
        parsed = int(text)
    except (TypeError, ValueError):
        try:
            parsed_float = float(text)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(parsed_float) or parsed_float < 0:
            return None
        parsed = int(parsed_float)
    if parsed < 0:
        return None
    return parsed


def parse_iso_datetime(value):
    """Parse an ISO-8601 string into a naive UTC datetime.

    Args:
        value: Datetime, ISO string, or empty.

    Returns:
        datetime | None: Parsed value, or ``None``.
    """
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo:
        return parsed.replace(tzinfo=None)
    return parsed


def compute_expires_at(key, now=None):
    """Compute the earliest expiry instant for a key.

    Args:
        key: License key ORM object.
        now: Optional clock used when TTL starts on this call.

    Returns:
        datetime | None: Expiry time, or ``None`` if unlimited.
    """
    candidates = []
    if key.valid_until:
        candidates.append(key.valid_until)
    first_used = key.first_used_at or now
    if key.ttl_seconds and first_used:
        candidates.append(first_used + timedelta(seconds=key.ttl_seconds))
    if not candidates:
        return None
    return min(candidates)


def remaining_uses(key):
    """Return remaining uses, or ``unlimited`` when max_uses is open.

    Args:
        key: License key ORM object.

    Returns:
        int | str: Remaining count or the token ``unlimited``.
    """
    if key.max_uses is None:
        return "unlimited"
    leftover = key.max_uses - key.used_count
    return leftover if leftover > 0 else 0


def evaluate_key(project, verification, key, hwid, now=None):
    """Evaluate a key against scheme rules without mutating state.

    Args:
        project: Parent project or ``None``.
        verification: Verification scheme or ``None``.
        key: Matching license key or ``None``.
        hwid: Optional machine identifier from the client.
        now: Evaluation timestamp; defaults to UTC now.

    Returns:
        str: One of ``RESULT_CODES``.
    """
    now = now or utcnow()
    if project is None or verification is None:
        return "invalid_key"
    if not project.enabled or not verification.enabled:
        return "disabled"
    if key is None:
        return "invalid_key"
    if key.status != KEY_STATUS_ACTIVE:
        return "disabled"
    if key.valid_from and now < key.valid_from:
        return "not_yet_valid"
    if key.valid_until and now > key.valid_until:
        return "expired"
    if key.ttl_seconds and key.first_used_at:
        expiry = key.first_used_at + timedelta(seconds=key.ttl_seconds)
        if now > expiry:
            return "expired"
    if key.max_uses is not None and key.used_count >= key.max_uses:
        return "exhausted"
    config = parse_config(verification.config_json)
    bind_hwid = bool(config.get("bind_hwid", verification.bind_hwid))
    if bind_hwid:
        supplied = (hwid or "").strip()
        if not supplied:
            return "hwid_mismatch"
        if key.hwid and key.hwid != supplied:
            return "hwid_mismatch"
    return "success"


def apply_success(key, hwid, now=None):
    """Record a successful verification on the key.

    Args:
        key: License key to update.
        hwid: Machine identifier to lock when binding is enabled.
        now: Timestamp of this success.

    Returns:
        LicenseKey: The mutated key instance.
    """
    now = now or utcnow()
    if key.first_used_at is None:
        key.first_used_at = now
    if hwid and not key.hwid:
        key.hwid = hwid.strip()
    key.used_count = int(key.used_count or 0) + 1
    return key


def _replace_text(text, variables, blob_urls):
    """Replace whitelisted placeholders and blob URL tokens in a string.

    Args:
        text: Template string.
        variables: Allowed ``{{name}}`` substitutions.
        blob_urls: Mapping of blob name to public URL.

    Returns:
        str: Rendered text.
    """
    def replace_blob(match):
        """Substitute a blob URL token."""
        return blob_urls.get(match.group(1), "")

    def replace_placeholder(match):
        """Substitute a whitelisted template variable."""
        name = match.group(1)
        if name in TEMPLATE_VARS and name in variables:
            value = variables[name]
            return "" if value is None else str(value)
        return match.group(0)

    rendered = BLOB_URL_RE.sub(replace_blob, text)
    return PLACEHOLDER_RE.sub(replace_placeholder, rendered)


def render_payload(payload, variables, blob_urls=None):
    """Recursively render a JSON-like response template.

    Args:
        payload: Dict, list, string, or scalar.
        variables: Whitelisted substitution values.
        blob_urls: Optional blob name to URL mapping.

    Returns:
        object: Rendered payload with the same shape.
    """
    blob_urls = blob_urls or {}
    if isinstance(payload, str):
        return _replace_text(payload, variables, blob_urls)
    if isinstance(payload, dict):
        return {
            key: render_payload(value, variables, blob_urls)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [render_payload(item, variables, blob_urls) for item in payload]
    return payload


def build_variables(project, verification, key, hwid, now=None):
    """Build the whitelist of template variables for a reply.

    Args:
        project: Project or ``None``.
        verification: Verification or ``None``.
        key: License key or ``None``.
        hwid: Client machine identifier.
        now: Clock used for ``now`` and expiry.

    Returns:
        dict: Template variable mapping.
    """
    now = now or utcnow()
    expires = compute_expires_at(key, now) if key else None
    return {
        "key": key.key_code if key else "",
        "hwid": (hwid or (key.hwid if key else "")) or "",
        "expires_at": expires.isoformat(sep=" ", timespec="seconds") if expires else "",
        "remaining_uses": remaining_uses(key) if key else "",
        "used_count": key.used_count if key else 0,
        "project": project.slug if project else "",
        "verification": verification.slug if verification else "",
        "now": now.isoformat(sep=" ", timespec="seconds"),
    }


def designed_response(verification, result, variables, blob_urls=None):
    """Return the admin-designed JSON body for a result code.

    Args:
        verification: Scheme that owns templates, or ``None``.
        result: Result code string.
        variables: Template variables.
        blob_urls: Optional blob URL mapping.

    Returns:
        dict: JSON-serializable response body.
    """
    if verification is not None:
        config = parse_config(verification.config_json)
        responses = config.get("responses") or {}
    else:
        responses = FALLBACK_RESPONSES
    payload = responses.get(result) or FALLBACK_RESPONSES.get(result) or {
        "code": -1,
        "msg": result,
    }
    return render_payload(payload, variables, blob_urls)


def sync_columns_from_config(verification):
    """Copy denormalized default columns from ``config_json``.

    Args:
        verification: Scheme to update in place.

    Returns:
        Verification: The same instance.
    """
    config = parse_config(verification.config_json)
    verification.config_json = json.dumps(config, ensure_ascii=False, indent=2)
    verification.bind_hwid = bool(config.get("bind_hwid"))
    defaults = config.get("defaults") or {}
    ttl = defaults.get("ttl_seconds")
    try:
        verification.default_ttl_seconds = int(ttl) if ttl not in (None, "") else None
    except (TypeError, ValueError):
        verification.default_ttl_seconds = None
    verification.default_max_uses = parse_unlimited_int(defaults.get("max_uses"))
    verification.default_valid_from = parse_iso_datetime(defaults.get("valid_from"))
    verification.default_valid_until = parse_iso_datetime(defaults.get("valid_until"))
    return verification
