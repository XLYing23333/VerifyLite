"""License-key string generation for batch distribution."""

import secrets

from app.defaults import DEFAULT_KEY_CHARSET


def generate_key_code(prefix="", length=16, charset=DEFAULT_KEY_CHARSET):
    """Build a grouped random key, optionally prefixed.

    Args:
        prefix: Optional leading token placed before the random body.
        length: Number of random characters before grouping.
        charset: Alphabet used for random characters.

    Returns:
        str: A key such as ``VL-A3K9-P2MX``.

    Raises:
        ValueError: If length or charset is invalid.
    """
    if length < 4 or length > 64:
        raise ValueError("key length must be between 4 and 64")
    if not charset:
        raise ValueError("charset must not be empty")
    raw = "".join(secrets.choice(charset) for _ in range(length))
    chunks = [raw[index:index + 4] for index in range(0, len(raw), 4)]
    body = "-".join(chunks)
    prefix = (prefix or "").strip().upper()
    if prefix:
        return f"{prefix}-{body}"
    return body
