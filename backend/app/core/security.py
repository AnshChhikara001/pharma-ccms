"""Password hashing and JWT issuance.

bcrypt is used DIRECTLY, not through passlib. passlib 1.7.4 is unmaintained and
raises `AttributeError: module 'bcrypt' has no attribute '__about__'` against
bcrypt >= 4.1 - a failure that looks like a bug in your own code. Calling bcrypt
straight through is a dozen lines and has no such trap.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()

# bcrypt hashes at most 72 bytes and, depending on version, either truncates
# silently or raises. Rejecting longer input explicitly avoids the far worse
# outcome where two different long passwords authenticate the same account.
MAX_PASSWORD_BYTES = 72


class PasswordTooLongError(ValueError):
    """Raised when a password exceeds what bcrypt can safely hash."""


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash. Each call generates a fresh salt."""
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(
            f"Password exceeds {MAX_PASSWORD_BYTES} bytes, which bcrypt cannot hash safely."
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison via bcrypt.

    Returns False rather than raising on a malformed stored hash: a corrupt row
    should deny access, never surface a 500 that distinguishes it from a wrong
    password.
    """
    encoded = plain.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str | int,
    role: str,
    email: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Issue a signed JWT.

    `role` is embedded so permission checks need no database round trip, but it
    is always re-validated against the live user record in `get_current_user` -
    a token issued before a role change must not outrank the current one.

    `email` is embedded for the same reason `role` is: `AuditContextMiddleware`
    reads it straight off the token to attribute an audit entry, and a
    middleware has no business opening a database session just to label who
    made a change.
    """
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "email": email,
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and verify. Returns None for anything untrustworthy.

    Expiry and signature are checked by PyJWT. A None return covers expired,
    tampered and malformed tokens alike - the caller has no legitimate reason to
    tell them apart, and saying which would leak information.
    """
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError:
        return None
