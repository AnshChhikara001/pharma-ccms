"""Request middleware."""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.security import decode_access_token
from app.services.audit import reset_audit_actor, set_audit_actor


class AuditContextMiddleware(BaseHTTPMiddleware):
    """Bind the acting user into a ContextVar for the life of the request.

    The audit listeners run inside SQLAlchemy's flush, far from the request
    object, so the actor has to reach them out of band. Decoding the token here
    is cheap (signature check, no database hit) and means audit entries carry an
    actor even on code paths that never resolve a User.

    A bad or absent token is not rejected here - that is the endpoint
    dependency's job. This middleware only records who, when there is a who.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        token_value: tuple[int, str] | None = None

        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            payload = decode_access_token(header[7:])
            if payload and payload.get("sub"):
                try:
                    token_value = (int(payload["sub"]), payload.get("email", ""))
                except (TypeError, ValueError):
                    token_value = None

        reset_token = set_audit_actor(
            token_value[0] if token_value else None,
            token_value[1] if token_value else None,
        )
        try:
            return await call_next(request)
        finally:
            reset_audit_actor(reset_token)
