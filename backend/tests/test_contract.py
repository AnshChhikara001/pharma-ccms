"""Guards on the domain contract.

These tests exist because the contract is consumed by three independent
systems - the database, the AI structured-output binding, and the generated
frontend types. A silent change here breaks all three at once.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas.complaint import ComplaintCreate, ComplaintUpdate, ExtractedComplaint
from app.schemas.enums import ComplaintStatus, QuantityUnit, Severity


def test_workflow_has_exactly_the_seven_required_states() -> None:
    """The brief specifies this lifecycle; assert it verbatim so a later edit
    cannot quietly drop or rename a state."""
    assert [s.value for s in ComplaintStatus] == [
        "new",
        "under_review",
        "investigation",
        "root_cause_identified",
        "capa_required",
        "qa_review",
        "closed",
    ]


def test_expiry_before_manufacture_is_rejected() -> None:
    with pytest.raises(ValidationError, match="expiry_date cannot be earlier"):
        ComplaintCreate(
            description="Discoloration observed across the blister strip.",
            manufacturing_date=date(2026, 6, 1),
            expiry_date=date(2025, 6, 1),
        )


def test_quantity_without_unit_is_rejected() -> None:
    """48 capsules and 48 kg are different complaints; a bare number is unusable."""
    with pytest.raises(ValidationError, match="quantity_unit is required"):
        ComplaintCreate(
            description="Short fill reported by the distributor.",
            quantity_affected=Decimal("48"),
        )


def test_quantity_with_unit_is_accepted() -> None:
    complaint = ComplaintCreate(
        description="Short fill reported by the distributor.",
        quantity_affected=Decimal("48"),
        quantity_unit=QuantityUnit.CAPSULES,
    )
    assert complaint.quantity_affected == Decimal("48")


def test_partial_update_distinguishes_unset_from_null() -> None:
    """This is the mechanism that makes AI edits non-destructive.

    "The batch number is BMX 240602" must change batch_number and nothing else.
    exclude_unset=True is what guarantees the other columns are never written.
    """
    update = ComplaintUpdate(batch_number="BMX 240602")
    emitted = update.model_dump(exclude_unset=True)

    assert emitted == {"batch_number": "BMX 240602"}
    assert "severity" not in emitted
    assert "description" not in emitted


def test_explicit_null_is_distinguishable_from_unset() -> None:
    update = ComplaintUpdate(batch_number=None)
    assert update.model_dump(exclude_unset=True) == {"batch_number": None}


def test_extraction_defaults_are_empty_not_none() -> None:
    """Callers iterate these lists directly; None would crash the intake UI."""
    extracted = ExtractedComplaint()
    assert extracted.missing_fields == []
    assert extracted.provenance == []
    assert extracted.clarifying_questions == []
    assert extracted.fields.model_dump(exclude_unset=True) == {}


def test_severity_values_match_pharmaceutical_classification() -> None:
    assert {s.value for s in Severity} == {"critical", "major", "minor"}


def test_vocabulary_endpoint_exposes_every_enum(client: TestClient) -> None:
    """The frontend builds all dropdowns from this one call."""
    response = client.get("/api/v1/meta/vocabulary")
    assert response.status_code == 200
    body = response.json()

    assert len(body["complaint_statuses"]) == 7
    assert len(body["severities"]) == 3
    assert len(body["user_roles"]) == 5
    assert {o["value"] for o in body["user_roles"]} == {
        "admin",
        "qa_manager",
        "complaint_officer",
        "investigator",
        "viewer",
    }
    # Labels are humanised for direct display.
    labels = {o["value"]: o["label"] for o in body["complaint_types"]}
    assert labels["appearance_discoloration"] == "Appearance Discoloration"
