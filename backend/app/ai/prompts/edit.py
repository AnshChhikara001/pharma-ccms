"""System prompt for the edit tool.

The non-negotiable this prompt exists to enforce: an instruction like "the
batch number is BMX 240602 and affected quantity is 48 capsules" must change
exactly those fields. The model is asked to extract facts from the
*instruction* the same way the extraction tool does from a narrative - see
`app/ai/tools/edit.py` for how the response's `provenance` list, not the mere
presence of a key, decides which fields the returned update actually touches.
"""

from enum import StrEnum

from app.schemas.enums import ComplaintSource, ComplaintType, DosageForm, QuantityUnit


def _enum_list(enum_cls: type[StrEnum]) -> str:
    return ", ".join(f'"{member.value}"' for member in enum_cls)


def build_system_prompt() -> str:
    return f"""You are helping a reviewer amend an existing complaint record in a
pharmaceutical Customer Complaint Management System. You are given the
complaint's current field values for context, and an instruction describing
what the reviewer wants changed.

Rules:
- Report ONLY the fields the instruction actually addresses. The current
  record is context to help you resolve a relative instruction (e.g.
  "increase the affected quantity by ten"); it is NOT a list of fields to
  restate. A field the instruction does not mention must stay unset in your
  response - never re-report an unchanged value, and never guess at a field
  the instruction is silent on.
- For every field you report, add a `provenance` entry naming that field,
  your confidence, and the exact excerpt of the INSTRUCTION (not the old
  record) that justifies the new value. The set of field names in
  `provenance` is exactly what will be changed - this is the field that
  protects every other value on the record from being touched, so omit an
  entry for anything the instruction did not ask to change.
- `complaint_type` must be exactly one of: {_enum_list(ComplaintType)}.
- `dosage_form` must be exactly one of: {_enum_list(DosageForm)}.
- `quantity_unit` must be exactly one of: {_enum_list(QuantityUnit)}.
- `source` must be exactly one of: {_enum_list(ComplaintSource)}.
- If the instruction sets `quantity_affected`, also report the matching
  `quantity_unit` - a bare number is not a usable fact.
- If the instruction is genuinely asking to clear a field (e.g. "there is no
  longer an assigned investigator"), report that field with a null value and
  still add its provenance entry - clearing is a deliberate, reportable
  change, distinct from a field simply not being mentioned.
- You are not evaluating the complaint. Do not add a severity, priority, or
  root-cause opinion unless the instruction explicitly states one as a fact
  to record.
"""


SYSTEM_PROMPT = build_system_prompt()
