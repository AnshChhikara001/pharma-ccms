"""`edit_complaint`: apply a natural-language instruction as a partial update.

Non-destructive by construction (CLAUDE.md non-negotiable #4, and this
project's dedicated regression test in `tests/test_ai_tools.py`). The model is
asked the same question the extract tool asks - "what does this text actually
say?" - over the *instruction* rather than the whole record, via
`providers.derive_edit`, which returns the same `ExtractedComplaint` shape
`extract_complaint` does.

The subtlety this module exists to handle: a naive `ComplaintUpdate(**json)`
built straight from a structured-output response would mark every key present
in that JSON as "set" - including fields the model filled with their schema
default (`None`) simply because the instruction never mentioned them. Passed
through `model_dump(exclude_unset=True)`, that would silently clear every
field the instruction was silent on, which is exactly the data-loss failure
CLAUDE.md calls out by name.

Instead, `ExtractedComplaint.provenance` - already part of the shared
contract, already meant to record "what the AI actually did" per field - is
used as the authoritative list of what changed. Only the field names present
in `provenance` are copied onto a freshly constructed `ComplaintUpdate`, so a
field the instruction didn't address stays genuinely unset on the result, not
merely null.
"""

import json
from typing import Any

from app.ai import providers
from app.ai.prompts.edit import SYSTEM_PROMPT
from app.schemas.complaint import ComplaintUpdate, FieldProvenance


def edit_complaint(
    existing: dict[str, Any], instruction: str
) -> tuple[ComplaintUpdate, list[FieldProvenance]]:
    """Return only the fields `instruction` actually asks to change.

    `existing` is the current complaint (e.g. `ComplaintRead(...).model_dump(mode="json")`),
    given purely as context so the model can resolve a relative instruction
    like "increase the affected quantity by ten" - the returned update still
    contains only the fields the instruction addressed.
    """
    user_prompt = (
        "Current complaint record, for context only - it is not a list of fields "
        f"to restate:\n{json.dumps(existing, default=str)}\n\n"
        "Instruction describing what should change:\n"
        f'"""\n{instruction.strip()}\n"""'
    )
    extraction = providers.derive_edit(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        instruction_text=instruction,
    )

    changed_field_names = {p.field for p in extraction.provenance}
    all_fields = extraction.fields.model_dump()
    changes = {name: value for name, value in all_fields.items() if name in changed_field_names}

    update = ComplaintUpdate(**changes)
    provenance = [p for p in extraction.provenance if p.field in changes]
    return update, provenance
