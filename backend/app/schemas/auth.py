"""Authentication request and response shapes."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.enums import UserRole


class Token(BaseModel):
    """OAuth2 bearer token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class UserRead(BaseModel):
    """A user as returned by the API. Never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    department: str | None = None
    is_active: bool


class UserWithPermissions(UserRead):
    """`/auth/me` response.

    Permissions are sent so the UI can hide controls the user cannot use. This is
    presentation only - every endpoint enforces independently, and a tampered
    client gains nothing.
    """

    permissions: list[str] = Field(default_factory=list)


class UserCreate(BaseModel):
    """Admin-only user creation."""

    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=8, max_length=72)
    role: UserRole = UserRole.VIEWER
    department: str | None = Field(None, max_length=120)


class LoginRequest(BaseModel):
    """JSON login, alongside the OAuth2 form endpoint."""

    email: EmailStr
    password: str
