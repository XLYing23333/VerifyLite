"""License-key string generation for batch distribution."""

import secrets

from app.defaults import DEFAULT_KEY_CHARSET


def generate_key_code(prefix="", length=64, charset=DEFAULT_KEY_CHARSET):
    """Build a random key, optionally prefixed, without grouping dashes.

    Args:
        prefix: Optional leading token placed before the random body.
        length: Number of random characters.
        charset: Alphabet used for random characters.

    Returns:
        str: A key such as ``VL`` followed by 64 random characters.

    Raises:
        ValueError: If length or charset is invalid.
    """
    if length < 4 or length > 64:
        raise ValueError("key length must be between 4 and 64")
    if not charset:
        raise ValueError("charset must not be empty")
    body = "".join(secrets.choice(charset) for _ in range(length))
    prefix = (prefix or "").strip().upper()
    if prefix:
        return f"{prefix}{body}"
    return body
