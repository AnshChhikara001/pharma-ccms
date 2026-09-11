"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require
from app.core.rbac import Permission, permissions_for
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, Token, UserCreate, UserRead, UserWithPermissions

router = APIRouter()
settings = get_settings()

# One message for both "no such user" and "wrong password". Distinguishing them
# tells an attacker which emails are registered.
_BAD_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password",
    headers={"WWW-Authenticate": "Bearer"},
)


def _authenticate(db: Session, email: str, password: str) -> User:
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()

    # Verify even when the user is absent, against a throwaway hash, so a
    # missing account and a wrong password take the same time. Without this the
    # response latency itself enumerates valid emails.
    if user is None:
        verify_password(password, "$2b$12$" + "x" * 53)
        raise _BAD_CREDENTIALS

    if not verify_password(password, user.hashed_password):
        raise _BAD_CREDENTIALS

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )

    return user


def _token_for(user: User) -> Token:
    return Token(
        access_token=create_access_token(subject=user.id, role=user.role.value),
        expires_in_minutes=settings.access_token_expire_minutes,
    )


@router.post("/login", response_model=Token, summary="Log in (OAuth2 form)")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """Standard OAuth2 password flow. `username` carries the email address.

    This is the endpoint Swagger's Authorize button uses.
    """
    return _token_for(_authenticate(db, form.username, form.password))


@router.post("/login/json", response_model=Token, summary="Log in (JSON)")
def login_json(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    """JSON login, used by the React client."""
    return _token_for(_authenticate(db, payload.email, payload.password))


@router.get("/me", response_model=UserWithPermissions, summary="Current user")
def me(user: User = Depends(get_current_user)) -> UserWithPermissions:
    """The caller, with the permissions their role holds.

    The frontend uses the permission list to hide controls. It is a usability
    affordance, not a security boundary - every endpoint checks independently.
    """
    return UserWithPermissions(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        department=user.department,
        is_active=user.is_active,
        permissions=sorted(p.value for p in permissions_for(user.role)),
    )


@router.get("/users", response_model=list[UserRead], summary="List users")
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require(Permission.USER_READ)),
) -> list[User]:
    """Used to populate investigator-assignment dropdowns."""
    return list(db.execute(select(User).order_by(User.full_name)).scalars())


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require(Permission.USER_MANAGE)),
) -> User:
    """Admin-only. Emails are normalised to lowercase so login is case-insensitive."""
    email = payload.email.lower()

    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email {email} already exists",
        )

    user = User(
        email=email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        department=payload.department,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
