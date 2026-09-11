"""Authentication and authorisation dependencies.

Usage in an endpoint:

    @router.post("/complaints")
    def create(user: User = Depends(require(Permission.COMPLAINT_CREATE))):
        ...

`require()` returns a dependency that resolves the caller, checks the
permission, and either hands back the User or raises. An endpoint that forgets
it is simply unauthenticated - there is no half-protected state.
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rbac import Permission, has_permission
from app.core.security import decode_access_token
from app.models.user import User

# auto_error=False so we can raise our own 401 with a WWW-Authenticate header
# rather than FastAPI's default, which omits it.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the caller from the bearer token.

    The role is re-read from the database rather than trusted from the token
    claim. A token minted before a demotion must not keep its old authority, and
    a deactivated account must stop working immediately rather than at expiry.
    """
    if not token:
        raise _UNAUTHENTICATED

    payload = decode_access_token(token)
    if payload is None:
        raise _UNAUTHENTICATED

    subject = payload.get("sub")
    if subject is None:
        raise _UNAUTHENTICATED

    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise _UNAUTHENTICATED from None

    user = db.get(User, user_id)
    if user is None:
        raise _UNAUTHENTICATED

    if not user.is_active:
        # 403 not 401: the credentials were valid, the account is not permitted.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )

    return user


def require(*permissions: Permission) -> Callable[..., User]:
    """Dependency factory gating an endpoint on permissions.

    Multiple permissions are ANDed - the caller must hold every one.
    """

    def dependency(user: User = Depends(get_current_user)) -> User:
        missing = [p for p in permissions if not has_permission(user.role, p)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{user.role.value}' lacks required permission: "
                    f"{', '.join(sorted(p.value for p in missing))}"
                ),
            )
        return user

    return dependency
