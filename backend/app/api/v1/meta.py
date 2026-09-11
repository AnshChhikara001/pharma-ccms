"""Vocabulary endpoints.

The frontend populates every dropdown from these rather than hard-coding option
lists. That keeps the UI's choices identical to what the database accepts and to
what the AI is constrained to emit - one vocabulary, three consumers.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas import enums
from app.services import workflow

router = APIRouter()


class EnumOption(BaseModel):
    """A selectable option. `label` is display text derived from the value."""

    value: str
    label: str


def _options(enum_cls: type[enums.StrEnum]) -> list[EnumOption]:
    """Turn `appearance_discoloration` into `Appearance Discoloration`."""
    return [EnumOption(value=m.value, label=m.value.replace("_", " ").title()) for m in enum_cls]


class VocabularyResponse(BaseModel):
    """Every enum the intake form and filters need, in one round trip."""

    user_roles: list[EnumOption]
    complaint_statuses: list[EnumOption]
    severities: list[EnumOption]
    priorities: list[EnumOption]
    complaint_sources: list[EnumOption]
    complaint_types: list[EnumOption]
    dosage_forms: list[EnumOption]
    quantity_units: list[EnumOption]
    document_kinds: list[EnumOption]


@router.get("/vocabulary", response_model=VocabularyResponse, summary="All domain enums")
def get_vocabulary() -> VocabularyResponse:
    """Single source of dropdown options for the entire frontend."""
    return VocabularyResponse(
        user_roles=_options(enums.UserRole),
        complaint_statuses=_options(enums.ComplaintStatus),
        severities=_options(enums.Severity),
        priorities=_options(enums.Priority),
        complaint_sources=_options(enums.ComplaintSource),
        complaint_types=_options(enums.ComplaintType),
        dosage_forms=_options(enums.DosageForm),
        quantity_units=_options(enums.QuantityUnit),
        document_kinds=_options(enums.DocumentKind),
    )


class TransitionOptionResponse(BaseModel):
    """One legal next step, described well enough for a client to render it."""

    to_status: str
    label: str
    requires_reason: bool = Field(
        ..., description="A reason is mandatory for this move; the UI must prompt for one."
    )
    required_permissions: list[str] = Field(
        ..., description="Hide the control unless the current user holds all of these."
    )
    is_backward: bool = Field(..., description="Returns the complaint to an earlier stage.")


class WorkflowResponse(BaseModel):
    """The complaint lifecycle, exactly as the server enforces it."""

    lifecycle: list[EnumOption] = Field(
        ..., description="The statuses in order, for rendering a progress track."
    )
    transitions: dict[str, list[TransitionOptionResponse]] = Field(
        ..., description="Legal next steps, keyed by current status."
    )
    terminal_statuses: list[str] = Field(
        ..., description="Statuses nothing may follow. Currently only 'closed'."
    )


@router.get("/workflow", response_model=WorkflowResponse, summary="The lifecycle table")
def get_workflow() -> WorkflowResponse:
    """Serve the transition table so the UI never hard-codes the lifecycle.

    The buttons a user sees are derived from the same table
    `services/workflow.py` validates against, which is what stops the frontend
    from offering a move the server will reject - or hiding one it would allow.
    """
    return WorkflowResponse(
        lifecycle=[
            EnumOption(value=s.value, label=s.value.replace("_", " ").title())
            for s in workflow.LIFECYCLE
        ],
        transitions={
            current.value: [
                TransitionOptionResponse(
                    to_status=option.to_status.value,
                    label=option.to_status.value.replace("_", " ").title(),
                    requires_reason=option.requires_reason,
                    required_permissions=sorted(p.value for p in option.required_permissions),
                    is_backward=option.is_backward,
                )
                for option in workflow.options_from(current)
            ]
            for current in workflow.LIFECYCLE
        },
        terminal_statuses=[s.value for s in workflow.LIFECYCLE if workflow.is_terminal(s)],
    )
