"""Role-based access control.

The centrepiece is `test_full_role_permission_matrix`, which asserts the
complete 5 x 18 grid explicitly. Writing it out rather than deriving it from
ROLE_PERMISSIONS is the point: a derived test would pass no matter how the
policy changed, and would have caught nothing. This one fails the moment
anyone's authority silently widens.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.rbac import ROLE_PERMISSIONS, Permission, has_permission, permissions_for
from app.schemas.enums import UserRole

# ── The authorisation policy, stated independently of the implementation ─────
# Read as: role -> every permission it is intended to hold.
EXPECTED_MATRIX: dict[UserRole, set[Permission]] = {
    UserRole.VIEWER: {
        Permission.COMPLAINT_READ,
        Permission.INVESTIGATION_READ,
    },
    UserRole.INVESTIGATOR: {
        Permission.COMPLAINT_READ,
        Permission.INVESTIGATION_READ,
        Permission.COMPLAINT_UPDATE,
        Permission.WORKFLOW_TRANSITION,
        Permission.INVESTIGATION_WRITE,
        Permission.ROOT_CAUSE_PROPOSE,
        Permission.CAPA_WRITE,
        Permission.AI_ASSESS,
    },
    UserRole.COMPLAINT_OFFICER: {
        Permission.COMPLAINT_READ,
        Permission.INVESTIGATION_READ,
        Permission.COMPLAINT_CREATE,
        Permission.COMPLAINT_UPDATE,
        Permission.COMPLAINT_ASSIGN,
        Permission.WORKFLOW_TRANSITION,
        Permission.AI_EXTRACT,
        Permission.AI_ASSESS,
    },
    UserRole.QA_MANAGER: {
        Permission.COMPLAINT_READ,
        Permission.INVESTIGATION_READ,
        Permission.COMPLAINT_CREATE,
        Permission.COMPLAINT_UPDATE,
        Permission.COMPLAINT_DELETE,
        Permission.COMPLAINT_ASSIGN,
        Permission.WORKFLOW_TRANSITION,
        Permission.WORKFLOW_CLOSE,
        Permission.INVESTIGATION_WRITE,
        Permission.ROOT_CAUSE_PROPOSE,
        Permission.ROOT_CAUSE_CONFIRM,
        Permission.CAPA_WRITE,
        Permission.CAPA_APPROVE,
        Permission.AI_EXTRACT,
        Permission.AI_ASSESS,
        Permission.USER_READ,
        Permission.AUDIT_READ,
    },
    UserRole.ADMIN: set(Permission),
}


@pytest.mark.parametrize("role", list(UserRole))
@pytest.mark.parametrize("permission", list(Permission))
def test_full_role_permission_matrix(role: UserRole, permission: Permission) -> None:
    """Every role x every permission - 90 assertions, allowed and forbidden alike.

    Testing only the allowed pairs would miss the failure that actually matters:
    a role quietly gaining authority it should not have.
    """
    expected = permission in EXPECTED_MATRIX[role]
    actual = has_permission(role, permission)
    assert actual is expected, (
        f"Role '{role.value}' should {'have' if expected else 'NOT have'} '{permission.value}'"
    )


def test_every_role_is_covered_by_the_matrix() -> None:
    """A new role must not slip in untested."""
    assert set(EXPECTED_MATRIX) == set(UserRole)


def test_implementation_matches_declared_policy_exactly() -> None:
    for role, expected in EXPECTED_MATRIX.items():
        assert set(ROLE_PERMISSIONS[role]) == expected, f"mismatch for {role.value}"


# ── Segregation of duties ────────────────────────────────────────────────────
# GMP expects the person who performs work not to be the person who approves it.


def test_investigator_may_propose_but_not_confirm_a_root_cause() -> None:
    assert has_permission(UserRole.INVESTIGATOR, Permission.ROOT_CAUSE_PROPOSE)
    assert not has_permission(UserRole.INVESTIGATOR, Permission.ROOT_CAUSE_CONFIRM)


def test_investigator_may_write_capas_but_not_approve_them() -> None:
    assert has_permission(UserRole.INVESTIGATOR, Permission.CAPA_WRITE)
    assert not has_permission(UserRole.INVESTIGATOR, Permission.CAPA_APPROVE)


def test_only_qa_manager_and_admin_may_close_a_complaint() -> None:
    closers = {r for r in UserRole if has_permission(r, Permission.WORKFLOW_CLOSE)}
    assert closers == {UserRole.QA_MANAGER, UserRole.ADMIN}


def test_only_admin_may_manage_users() -> None:
    managers = {r for r in UserRole if has_permission(r, Permission.USER_MANAGE)}
    assert managers == {UserRole.ADMIN}


def test_viewer_holds_no_write_permission() -> None:
    for permission in permissions_for(UserRole.VIEWER):
        assert permission.value.endswith(":read"), f"{permission} is not read-only"


def test_complaint_officer_cannot_confirm_quality_decisions() -> None:
    """Triage is not approval - intake staff must not sign off root causes or CAPAs."""
    for permission in (
        Permission.ROOT_CAUSE_CONFIRM,
        Permission.CAPA_APPROVE,
        Permission.WORKFLOW_CLOSE,
    ):
        assert not has_permission(UserRole.COMPLAINT_OFFICER, permission)


# ── Enforcement at the HTTP boundary ─────────────────────────────────────────
# The table above is policy; these prove the policy is actually applied.


def test_user_list_allows_privileged_roles(client: TestClient, auth_headers) -> None:
    for role in (UserRole.ADMIN, UserRole.QA_MANAGER):
        response = client.get("/api/v1/auth/users", headers=auth_headers(role))
        assert response.status_code == 200, f"{role.value} should be allowed"


def test_user_list_forbids_unprivileged_roles(client: TestClient, auth_headers) -> None:
    for role in (UserRole.COMPLAINT_OFFICER, UserRole.INVESTIGATOR, UserRole.VIEWER):
        response = client.get("/api/v1/auth/users", headers=auth_headers(role))
        assert response.status_code == 403, f"{role.value} should be forbidden"


def test_user_creation_is_admin_only(client: TestClient, auth_headers) -> None:
    payload = {
        "email": "new.person@pharmaco.com",
        "full_name": "New Person",
        "password": "Str0ng-Pass!",
        "role": "viewer",
    }

    for role in (UserRole.QA_MANAGER, UserRole.COMPLAINT_OFFICER, UserRole.VIEWER):
        response = client.post("/api/v1/auth/users", json=payload, headers=auth_headers(role))
        assert response.status_code == 403, f"{role.value} must not create users"

    response = client.post("/api/v1/auth/users", json=payload, headers=auth_headers(UserRole.ADMIN))
    assert response.status_code == 201


def test_duplicate_email_is_rejected(client: TestClient, auth_headers, users) -> None:
    response = client.post(
        "/api/v1/auth/users",
        json={
            "email": users[UserRole.VIEWER].email,
            "full_name": "Impostor",
            "password": "Str0ng-Pass!",
            "role": "viewer",
        },
        headers=auth_headers(UserRole.ADMIN),
    )
    assert response.status_code == 409


def test_protected_endpoint_rejects_missing_and_bad_tokens(client: TestClient) -> None:
    assert client.get("/api/v1/auth/users").status_code == 401
    assert (
        client.get(
            "/api/v1/auth/users", headers={"Authorization": "Bearer forged.token.here"}
        ).status_code
        == 401
    )


def test_forbidden_response_names_the_missing_permission(client: TestClient, auth_headers) -> None:
    """A 403 should be debuggable without reading the source."""
    response = client.get("/api/v1/auth/users", headers=auth_headers(UserRole.VIEWER))
    assert response.status_code == 403
    assert "user:read" in response.json()["detail"]
