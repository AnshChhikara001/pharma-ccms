"""Role-based permissions.

The whole authorisation model is the one table below. It is data, not scattered
`if role == ...` checks, for three reasons: a reviewer can read the entire
policy at a glance, the test suite can assert the complete role x permission
matrix by iterating it, and adding a role cannot silently miss an endpoint.

Roles, and what they are for:

  ADMIN             - system administration and user management.
  QA_MANAGER        - owns quality decisions: approves root causes and CAPAs,
                      and is the only role that may close a complaint.
  COMPLAINT_OFFICER - intake and triage. Logs complaints, runs AI extraction,
                      assigns investigators.
  INVESTIGATOR      - performs assigned investigations and proposes root causes.
                      Cannot approve their own findings - segregation of duties
                      is a GMP expectation, not a nicety.
  VIEWER            - read-only. Auditors and observers.
"""

from enum import StrEnum

from app.schemas.enums import UserRole


class Permission(StrEnum):
    """Every capability the system gates on."""

    # Complaints
    COMPLAINT_READ = "complaint:read"
    COMPLAINT_CREATE = "complaint:create"
    COMPLAINT_UPDATE = "complaint:update"
    COMPLAINT_DELETE = "complaint:delete"
    COMPLAINT_ASSIGN = "complaint:assign"

    # Workflow
    WORKFLOW_TRANSITION = "workflow:transition"
    WORKFLOW_CLOSE = "workflow:close"

    # Investigation
    INVESTIGATION_READ = "investigation:read"
    INVESTIGATION_WRITE = "investigation:write"
    ROOT_CAUSE_PROPOSE = "root_cause:propose"
    ROOT_CAUSE_CONFIRM = "root_cause:confirm"
    CAPA_WRITE = "capa:write"
    CAPA_APPROVE = "capa:approve"

    # AI
    AI_EXTRACT = "ai:extract"
    AI_ASSESS = "ai:assess"

    # Administration
    USER_READ = "user:read"
    USER_MANAGE = "user:manage"
    AUDIT_READ = "audit:read"


# Read access is the floor: every authenticated role can see complaints. What
# separates the roles is what they may change.
_VIEWER: frozenset[Permission] = frozenset(
    {
        Permission.COMPLAINT_READ,
        Permission.INVESTIGATION_READ,
    }
)

_INVESTIGATOR: frozenset[Permission] = _VIEWER | {
    Permission.COMPLAINT_UPDATE,
    Permission.WORKFLOW_TRANSITION,
    Permission.INVESTIGATION_WRITE,
    Permission.ROOT_CAUSE_PROPOSE,
    Permission.CAPA_WRITE,
    Permission.AI_ASSESS,
}

_COMPLAINT_OFFICER: frozenset[Permission] = _VIEWER | {
    Permission.COMPLAINT_CREATE,
    Permission.COMPLAINT_UPDATE,
    Permission.COMPLAINT_ASSIGN,
    Permission.WORKFLOW_TRANSITION,
    Permission.AI_EXTRACT,
    Permission.AI_ASSESS,
}

_QA_MANAGER: frozenset[Permission] = _COMPLAINT_OFFICER | {
    Permission.COMPLAINT_DELETE,
    Permission.WORKFLOW_CLOSE,
    Permission.INVESTIGATION_WRITE,
    Permission.ROOT_CAUSE_PROPOSE,
    Permission.ROOT_CAUSE_CONFIRM,
    Permission.CAPA_WRITE,
    Permission.CAPA_APPROVE,
    Permission.USER_READ,
    Permission.AUDIT_READ,
}

_ADMIN: frozenset[Permission] = frozenset(Permission)

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.ADMIN: _ADMIN,
    UserRole.QA_MANAGER: _QA_MANAGER,
    UserRole.COMPLAINT_OFFICER: _COMPLAINT_OFFICER,
    UserRole.INVESTIGATOR: _INVESTIGATOR,
    UserRole.VIEWER: _VIEWER,
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    """True if `role` holds `permission`. Unknown roles hold nothing."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def permissions_for(role: UserRole) -> frozenset[Permission]:
    """Every permission a role holds. Sent to the frontend so the UI can hide
    controls the user cannot use - the server still enforces independently."""
    return ROLE_PERMISSIONS.get(role, frozenset())
