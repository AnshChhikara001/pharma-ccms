"""Vocabulary endpoints.

The frontend populates every dropdown from these rather than hard-coding option
lists. That keeps the UI's choices identical to what the database accepts and to
what the AI is constrained to emit - one vocabulary, three consumers.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.schemas import enums

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
