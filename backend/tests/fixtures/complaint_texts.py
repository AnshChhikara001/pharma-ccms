"""Raw complaint text samples and the fields the mock adapter must extract
from each, in `ExtractedComplaint.fields` terms (string/enum-value form, as
they come off `ComplaintUpdate.model_dump()` before Pydantic coercion).

Each `expected_missing` is exactly the subset of the tool's five critical
fields (`product_name`, `batch_number`, `complaint_type`, `quantity_affected`,
`customer_name`) the text deliberately omits, so `missing_fields` and
`clarifying_questions` have something real to exercise too - not every
fixture is a "found everything" case.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExtractionCase:
    name: str
    text: str
    expected_fields: dict[str, Any] = field(default_factory=dict)
    expected_missing: tuple[str, ...] = ()


EXTRACTION_CASES: tuple[ExtractionCase, ...] = (
    ExtractionCase(
        name="discoloration_hospital_all_fields",
        text=(
            "Customer: Springfield General Hospital\n"
            "Product: Amoxicillin 500 mg\n"
            "Batch number is BMX 240602. Reported by phone call.\n"
            "Tablets in the blister appear mottled with brown spots on one face. "
            "Approximately 40 tablets affected."
        ),
        expected_fields={
            "customer_name": "Springfield General Hospital",
            "product_name": "Amoxicillin 500 mg",
            "batch_number": "BMX 240602",
            "quantity_affected": "40",
            "quantity_unit": "tablets",
            "complaint_type": "appearance_discoloration",
            "dosage_form": "tablet",
            "source": "phone",
        },
        expected_missing=(),
    ),
    ExtractionCase(
        name="foreign_matter_distributor_missing_customer",
        text=(
            "Product: Cefazolin Injection 1g\n"
            "A distributor reported foreign matter visible in several vials upon "
            "visual inspection prior to dispensing. Batch number: CFZ-99231. "
            "12 vials affected."
        ),
        expected_fields={
            "product_name": "Cefazolin Injection 1g",
            "batch_number": "CFZ-99231",
            "quantity_affected": "12",
            "quantity_unit": "vials",
            "complaint_type": "foreign_matter",
            "dosage_form": "injection",
            "source": "distributor",
        },
        expected_missing=("customer_name",),
    ),
    ExtractionCase(
        name="labeling_error_retail_pharmacy_missing_batch",
        text=(
            "Customer: Green Valley Retail Pharmacy\n"
            "Product: Metformin 850 mg\n"
            "A retail pharmacy reported a labeling error: the carton displayed the "
            "wrong strength printed on the outer label. 5 bottles affected."
        ),
        expected_fields={
            "customer_name": "Green Valley Retail Pharmacy",
            "product_name": "Metformin 850 mg",
            "quantity_affected": "5",
            "quantity_unit": "bottles",
            "complaint_type": "labeling_error",
            "source": "retail_pharmacy",
        },
        expected_missing=("batch_number",),
    ),
    ExtractionCase(
        name="vague_report_nothing_extractable",
        text=(
            "Received a vague complaint with no specific details about the "
            "product, the batch, or the issue type provided by the caller."
        ),
        expected_fields={},
        expected_missing=(
            "product_name",
            "batch_number",
            "complaint_type",
            "quantity_affected",
            "customer_name",
        ),
    ),
)


@dataclass(frozen=True)
class EditCase:
    name: str
    instruction: str
    expected_changes: dict[str, Any]


# The canonical example CLAUDE.md itself cites for the non-destructive edit
# guarantee: "the batch number is BMX 240602" must change exactly the fields
# the instruction states, nothing else - see tests/test_ai_tools.py.
EDIT_CASES: tuple[EditCase, ...] = (
    EditCase(
        name="batch_and_quantity_together",
        instruction="The batch number is BMX 240602 and affected quantity is 48 capsules.",
        expected_changes={
            "batch_number": "BMX 240602",
            "quantity_affected": "48",
            "quantity_unit": "capsules",
        },
    ),
    EditCase(
        name="customer_name_only",
        instruction="Update the customer name to Riverside Community Pharmacy.",
        expected_changes={"customer_name": "Riverside Community Pharmacy"},
    ),
)
