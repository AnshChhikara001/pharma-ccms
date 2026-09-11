"""`extract_complaint`: turn a raw complaint narrative into structured fields.

Binds `ExtractedComplaint` end to end - the same schema FastAPI serves and the
frontend's generated types describe (see `app/schemas/complaint.py`). Nothing
in this module defines a shape of its own.
"""

from app.ai import providers
from app.ai.prompts.extract import SYSTEM_PROMPT
from app.schemas.complaint import ExtractedComplaint


def extract_complaint(text: str) -> ExtractedComplaint:
    """Extract whatever `text` actually states.

    Fields absent from the input are left unset in `.fields`, not guessed -
    see `.missing_fields` and `.clarifying_questions` for what to ask the
    reporter next. Text-only for this phase; document/image intake is
    Phase 4's concern.
    """
    user_prompt = f'Complaint narrative submitted by a reporter:\n"""\n{text.strip()}\n"""'
    return providers.extract_fields(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        source_text=text,
    )
