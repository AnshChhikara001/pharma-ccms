"""System prompts for the three AI tools, one module each.

Each module exports `SYSTEM_PROMPT` (built from `app/schemas/enums.py`, never
from hand-typed option lists) and the `build_system_prompt()` function that
produced it, so a caller who wants a fresh prompt after the enums change
within the same process can regenerate it rather than trust the cached
constant.
"""
