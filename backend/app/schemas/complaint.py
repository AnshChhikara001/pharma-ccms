"""The complaint contract.

Read this file first. Everything else in the project is downstream of it.

Three shapes, deliberately distinct:

  ComplaintCreate    - what a client submits to create a complaint. Required
                       fields are genuinely required.
  ComplaintUpdate    - every field optional. This is what the AI *edit* tool
                       emits, and optionality is what makes "update the batch
                       number without touching anything else" safe: unset is
                       distinguishable from null via exclude_unset=True.
  ExtractedComplaint - what the AI *extraction* tools emit. Every field optional
                       because a real complaint email rarely contains all of
                       them, plus explicit provenance describing which fields
                       were found, how confident the model is, and what is still
                       missing.

The distinction between ComplaintUpdate and ExtractedComplaint matters: an
extraction reports what a document *said*, while an update states what should
*change*. Collapsing them would make partial AI edits silently wipe fields.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.enums import (
    AIConfidence,
    ComplaintSource,
    ComplaintStatus,
    ComplaintType,
    DosageForm,
    Priority,
    QuantityUnit,
    Severity,
)

# ── Core complaint fields ─────────────────────────────────────────────────────
# Field groupings mirror the four sections of the intake screen so the form and
# the contract stay legible against each other.


class ComplaintBase(BaseModel):
    """Fields shared by create/read. Section numbers refer to the intake UI."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=False)

    # 1. Origin & customer details
    source: ComplaintSource | None = Field(None, description="How the complaint reached us.")
    customer_name: str | None = Field(
        None, max_length=200, description="Reporting customer or institution."
    )
    customer_contact: str | None = Field(None, max_length=200)
    reporter_name: str | None = Field(
        None, max_length=200, description="Individual who raised it, if named."
    )

    # 2. Product & batch identification
    product_name: str | None = Field(None, max_length=200)
    product_strength: str | None = Field(
        None, max_length=100, description='Strength or grade, e.g. "500 mg".'
    )
    dosage_form: DosageForm | None = None
    batch_number: str | None = Field(
        None, max_length=100, description="Batch / lot number as printed on pack."
    )
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    quantity_affected: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=3)
    quantity_unit: QuantityUnit | None = None

    # 3. Complaint details
    complaint_type: ComplaintType | None = None
    complaint_date: date | None = Field(
        None, description="Date the complaint was raised by the customer."
    )
    description: str | None = Field(
        None, max_length=8000, description="Detailed complaint description."
    )

    # 4. Initial assessment & priority
    severity: Severity | None = None
    priority: Priority | None = None

    # Investigation logistics
    assigned_investigator_id: int | None = None
    due_date: date | None = None

    @field_validator("batch_number", "product_strength", "customer_name", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        """Trim whitespace. AI extraction and OCR both tend to emit padding."""
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _expiry_after_manufacture(self) -> ComplaintBase:
        """A batch cannot expire before it was made.

        Caught here rather than in the DB so the AI extraction path surfaces it
        as a validation error the user can correct, not a 500.
        """
        if (
            self.manufacturing_date is not None
            and self.expiry_date is not None
            and self.expiry_date < self.manufacturing_date
        ):
            raise ValueError("expiry_date cannot be earlier than manufacturing_date")
        return self

    @model_validator(mode="after")
    def _quantity_needs_unit(self) -> ComplaintBase:
        """A bare number is ambiguous: 48 capsules and 48 kg are not the same
        complaint. Require the unit whenever a quantity is present."""
        if self.quantity_affected is not None and self.quantity_unit is None:
            raise ValueError("quantity_unit is required when quantity_affected is set")
        return self


class ComplaintCreate(ComplaintBase):
    """Creation payload. Description is the one field we insist on - a complaint
    with no narrative is not triageable, and the AI can derive most of the rest
    from it."""

    description: str = Field(..., min_length=10, max_length=8000)


class ComplaintUpdate(BaseModel):
    """Partial update. Every field optional by construction.

    Callers must serialise with `exclude_unset=True` so that "not mentioned"
    stays distinct from "explicitly cleared". The AI edit tool depends on this:
    it is the mechanism that preserves unrelated fields.
    """

    model_config = ConfigDict(from_attributes=True)

    source: ComplaintSource | None = None
    customer_name: str | None = Field(None, max_length=200)
    customer_contact: str | None = Field(None, max_length=200)
    reporter_name: str | None = Field(None, max_length=200)
    product_name: str | None = Field(None, max_length=200)
    product_strength: str | None = Field(None, max_length=100)
    dosage_form: DosageForm | None = None
    batch_number: str | None = Field(None, max_length=100)
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    quantity_affected: Decimal | None = Field(None, ge=0)
    quantity_unit: QuantityUnit | None = None
    complaint_type: ComplaintType | None = None
    complaint_date: date | None = None
    description: str | None = Field(None, max_length=8000)
    severity: Severity | None = None
    priority: Priority | None = None
    assigned_investigator_id: int | None = None
    due_date: date | None = None


class ComplaintRead(ComplaintBase):
    """Full complaint as returned by the API."""

    id: int
    reference_code: str = Field(..., description='Human-facing identifier, e.g. "CMP-2026-0042".')
    status: ComplaintStatus
    created_at: datetime
    updated_at: datetime
    created_by_id: int | None = None
    is_overdue: bool = False


class ComplaintListItem(BaseModel):
    """Trimmed projection for the list view.

    Separate from ComplaintRead on purpose: the list renders up to 50 rows and
    has no use for the 8 KB description field.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    reference_code: str
    customer_name: str | None
    product_name: str | None
    batch_number: str | None
    complaint_type: ComplaintType | None
    status: ComplaintStatus
    severity: Severity | None
    priority: Priority | None
    complaint_date: date | None
    due_date: date | None
    assigned_investigator_id: int | None
    is_overdue: bool
    created_at: datetime


# ── AI extraction contract ────────────────────────────────────────────────────


class FieldProvenance(BaseModel):
    """Per-field record of what the AI did.

    Drives the "AI populated this" highlighting in the intake UI. Without it the
    user cannot tell an extracted value from one they typed, which is exactly the
    kind of ambiguity a regulated workflow must not have.
    """

    field: str = Field(..., description="Field name on the complaint schema.")
    confidence: AIConfidence
    source_excerpt: str | None = Field(
        None,
        max_length=500,
        description="Verbatim span from the input that justified this value.",
    )


class ExtractedComplaint(BaseModel):
    """Structured output contract for every AI extraction tool.

    Bound directly as the LLM's structured-output schema, so the model is
    constrained to the same enums the database enforces and cannot return an
    unstorable value.
    """

    model_config = ConfigDict(from_attributes=True)

    fields: ComplaintUpdate = Field(
        default_factory=ComplaintUpdate,
        description="Only the fields actually found in the input.",
    )
    provenance: list[FieldProvenance] = Field(default_factory=list)
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Important fields absent from the input, for the UI to prompt on.",
    )
    clarifying_questions: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Questions to ask the user to close the gaps above.",
    )
    extraction_notes: str | None = Field(
        None, max_length=2000, description="Anything ambiguous worth flagging."
    )


class AIAssessment(BaseModel):
    """The AI's read on a complaint.

    Every consumer must render this behind an explicit advisory label. These are
    recommendations to a qualified reviewer, never confirmed regulatory
    determinations or established root causes.
    """

    model_config = ConfigDict(from_attributes=True)

    summary: str = Field(..., max_length=2000)
    recommended_severity: Severity | None = None
    recommended_priority: Priority | None = None
    severity_rationale: str | None = Field(None, max_length=1500)
    risk_factors: list[str] = Field(default_factory=list)
    completeness_score: int = Field(
        ..., ge=0, le=100, description="Percentage of triage-critical fields present."
    )
    missing_critical_fields: list[str] = Field(default_factory=list)
    potential_root_causes: list[str] = Field(
        default_factory=list, description="Hypotheses to investigate. NOT determinations."
    )
    investigation_steps: list[str] = Field(default_factory=list)
    capa_recommendations: list[str] = Field(default_factory=list)
    regulatory_considerations: list[str] = Field(default_factory=list)

    disclaimer: str = Field(
        default=(
            "AI-generated recommendation. Not a confirmed root cause or regulatory "
            "decision. Must be reviewed and approved by qualified QA personnel."
        ),
        description="Rendered verbatim wherever this assessment is shown.",
    )


class DuplicateMatch(BaseModel):
    """A possible duplicate surfaced during intake."""

    complaint_id: int
    reference_code: str
    similarity: float = Field(..., ge=0.0, le=1.0)
    matched_on: list[str] = Field(
        default_factory=list, description='e.g. ["batch_number", "complaint_type"].'
    )
    summary: str | None = None
