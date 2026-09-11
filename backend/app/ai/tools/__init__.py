"""The three AI tools: extract, edit, assess (plus duplicate lookup).

Each module exposes one function bound to a schema from
`app/schemas/complaint.py`. None of them import a provider SDK directly - see
`app/ai/providers.py` for why that boundary matters.
"""

from app.ai.tools.assess import assess_complaint, find_duplicate_candidates
from app.ai.tools.edit import edit_complaint
from app.ai.tools.extract import extract_complaint

__all__ = [
    "assess_complaint",
    "edit_complaint",
    "extract_complaint",
    "find_duplicate_candidates",
]
