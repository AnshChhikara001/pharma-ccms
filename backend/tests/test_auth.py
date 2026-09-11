"""Authentication behaviour."""

import pytest
from fastapi.testclient import TestClient

from app.core.security import (
    PasswordTooLongError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.schemas.enums import UserRole
from seeds.users import DEMO_PASSWORD

# ── Password hashing ─────────────────────────────────────────────────────────


def test_password_round_trip() -> None:
    hashed = hash_password("Correct-Horse-9")
    assert hashed != "Correct-Horse-9"
    assert verify_password("Correct-Horse-9", hashed)
    assert not verify_password("correct-horse-9", hashed)


def test_same_password_hashes_differently() -> None:
    """Each hash carries its own salt, so identical passwords must not collide -
    otherwise a leaked table reveals which users share a password."""
    assert hash_password("same") != hash_password("same")


def test_password_over_bcrypt_limit_is_rejected() -> None:
    """bcrypt silently truncates past 72 bytes. Two different long passwords
    would then unlock the same account, so refuse rather than truncate."""
    with pytest.raises(PasswordTooLongError):
        hash_password("x" * 73)


def test_verify_against_corrupt_hash_denies_rather_than_raises() -> None:
    assert verify_password("anything", "not-a-bcrypt-hash") is False


# ── Tokens ───────────────────────────────────────────────────────────────────


def test_token_carries_subject_and_role() -> None:
    payload = decode_access_token(create_access_token(42, "qa_manager"))
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["role"] == "qa_manager"


def test_token_carries_email_for_audit_attribution() -> None:
    """AuditContextMiddleware reads this claim straight off the token to
    attribute an audit entry, without a database round trip."""
    payload = decode_access_token(
        create_access_token(42, "qa_manager", email="qa.manager@pharmaco.com")
    )
    assert payload is not None
    assert payload["email"] == "qa.manager@pharmaco.com"


def test_tampered_token_is_rejected() -> None:
    token = create_access_token(1, "admin")
    assert decode_access_token(token[:-3] + "abc") is None


def test_garbage_token_is_rejected() -> None:
    assert decode_access_token("not.a.token") is None


# ── Login endpoint ───────────────────────────────────────────────────────────


def test_login_succeeds_with_valid_credentials(client: TestClient, users) -> None:
    response = client.post(
        "/api/v1/auth/login/json",
        json={"email": users[UserRole.ADMIN].email, "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_login_is_case_insensitive_on_email(client: TestClient, users) -> None:
    response = client.post(
        "/api/v1/auth/login/json",
        json={"email": users[UserRole.ADMIN].email.upper(), "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200


def test_login_rejects_wrong_password(client: TestClient, users) -> None:
    response = client.post(
        "/api/v1/auth/login/json",
        json={"email": users[UserRole.ADMIN].email, "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_unknown_email_and_wrong_password_are_indistinguishable(client: TestClient, users) -> None:
    """Different messages would let an attacker enumerate registered emails."""
    unknown = client.post(
        "/api/v1/auth/login/json",
        json={"email": "nobody@pharmaco.com", "password": DEMO_PASSWORD},
    )
    wrong = client.post(
        "/api/v1/auth/login/json",
        json={"email": users[UserRole.ADMIN].email, "password": "nope"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_oauth2_form_login_works(client: TestClient, users) -> None:
    """This is the flow Swagger's Authorize button uses."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": users[UserRole.ADMIN].email, "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200


def test_inactive_user_cannot_log_in(client: TestClient, db, users) -> None:
    user = users[UserRole.VIEWER]
    user.is_active = False
    db.commit()

    response = client.post(
        "/api/v1/auth/login/json",
        json={"email": user.email, "password": DEMO_PASSWORD},
    )
    assert response.status_code == 403


# ── /auth/me ─────────────────────────────────────────────────────────────────


def test_me_requires_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_identity_and_permissions(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/auth/me", headers=auth_headers(UserRole.QA_MANAGER))
    assert response.status_code == 200

    body = response.json()
    assert body["role"] == "qa_manager"
    assert "workflow:close" in body["permissions"]
    assert "user:manage" not in body["permissions"]


def test_me_never_exposes_the_password_hash(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/auth/me", headers=auth_headers(UserRole.ADMIN))
    assert "hashed_password" not in response.text
    assert "password" not in response.json()


def test_deactivated_user_loses_access_immediately(
    client: TestClient, db, users, auth_headers
) -> None:
    """A still-valid token must stop working the moment the account is disabled -
    the role is re-read from the database on every request, not trusted from the
    token claim."""
    headers = auth_headers(UserRole.VIEWER)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    users[UserRole.VIEWER].is_active = False
    db.commit()

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 403
