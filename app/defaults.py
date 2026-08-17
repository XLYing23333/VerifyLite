"""Default verification config and shared result codes."""

RESULT_CODES = (
    "success",
    "invalid_key",
    "not_yet_valid",
    "expired",
    "exhausted",
    "hwid_mismatch",
    "disabled",
)

FALLBACK_RESPONSES = {
    "success": {
        "code": 0,
        "msg": "ok",
        "expire": "{{expires_at}}",
        "remaining": "{{remaining_uses}}",
    },
    "invalid_key": {"code": 1, "msg": "invalid key"},
    "not_yet_valid": {"code": 2, "msg": "not yet valid"},
    "expired": {"code": 3, "msg": "expired"},
    "exhausted": {"code": 4, "msg": "no uses left"},
    "hwid_mismatch": {"code": 5, "msg": "hwid mismatch"},
    "disabled": {"code": 6, "msg": "disabled"},
}

DEFAULT_VALID_UNTIL = "2999-01-01 00:00:00"

DEFAULT_CONFIG = {
    "bind_hwid": False,
    "defaults": {
        "max_uses": None,
        "valid_from": None,
        "valid_until": DEFAULT_VALID_UNTIL,
    },
    "responses": {key: dict(value) for key, value in FALLBACK_RESPONSES.items()},
}

TEMPLATE_VARS = (
    "key",
    "hwid",
    "expires_at",
    "remaining_uses",
    "used_count",
    "project",
    "verification",
    "now",
)

DEFAULT_KEY_CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
KEY_STATUS_ACTIVE = "active"
KEY_STATUS_REVOKED = "revoked"
LANG_ZH = "zh"
LANG_EN = "en"
THEME_SYSTEM = "system"
THEME_DARK = "dark"
THEME_WELIGHT = "welight"
THEME_CHOICES = (THEME_SYSTEM, THEME_DARK, THEME_WELIGHT)
SLUG_PATTERN = r"^[a-z0-9][a-z0-9\-_]{0,62}$"
UNLIMITED_TOKENS = frozenset(
    {"", "inf", "infty", "infinity", "∞", "-1", "none", "null", "unlimited"},
)
