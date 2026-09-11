"""Cost governor for every AI provider call.

CLAUDE.md, non-negotiable #1: every model call goes through this module, which
enforces a hard cap *before* calling out. Nothing in `app/ai/providers.py` (or
anywhere else) may invoke a provider SDK without going through `govern()`
first.

Ledger
------
Spend is persisted at `<backend>/ai_spend.json`, written atomically (tmp file +
`os.replace`) so a crash mid-write can never leave a corrupt or truncated
ledger. The path is resolved from this file's own location, not the process's
current working directory - `uvicorn` and `pytest` are routinely started from
different directories, and both must agree on the one ledger.

Cache
-----
Optional response cache at `<backend>/.ai_cache/`, gated by
`settings.ai_cache_enabled`. Keyed off a hash of the exact request (provider,
model, tool, prompts), so a repeated extraction in a demo - or in a test run -
never costs twice. A cache hit is never billed and never written to the spend
ledger.

Concurrency
-----------
Good enough for a single dev-server process, not more: an in-process lock
serialises read-modify-write of the ledger, and the file itself is replaced
atomically so a concurrent reader (or a crash) never observes a half-written
file. Cross-process locking is out of scope for this phase.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from app.core.config import get_settings

# app/ai/budget.py -> app/ai -> app -> backend. Resolved once from this file's
# location so the ledger lands in the same place no matter where the process
# was launched from.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Module-level, not inlined into every function, so tests can redirect them
# (see tests/conftest.py's `_isolated_ai_ledger` fixture) without touching the
# real files this project ships against.
_LEDGER_PATH = _BACKEND_ROOT / "ai_spend.json"
_CACHE_DIR = _BACKEND_ROOT / ".ai_cache"

_LOCK = threading.Lock()

# USD per 1,000,000 tokens, as (input_rate, output_rate). Keyed by model name
# rather than provider name, since that is what the estimate is actually a
# function of. 'mock' and gemini's free tier are both zero-cost; gpt-5-nano's
# pricing matches the figure documented in .env.example.
PRICING_USD_PER_1M_TOKENS: dict[str, tuple[Decimal, Decimal]] = {
    "mock": (Decimal("0"), Decimal("0")),
    "gemini-2.5-flash": (Decimal("0"), Decimal("0")),
    "gpt-5-nano": (Decimal("0.05"), Decimal("0.40")),
}


class BudgetExceeded(Exception):  # noqa: N818 - name fixed by .env.example's own docs
    """Raised before any provider call whose projected cost would breach the cap."""

    def __init__(self, projected_cost: Decimal, remaining_budget: Decimal, cap: Decimal) -> None:
        self.projected_cost = projected_cost
        self.remaining_budget = remaining_budget
        self.cap = cap
        super().__init__(
            f"Projected cost ${projected_cost:.6f} exceeds the remaining AI budget "
            f"${remaining_budget:.6f} (cap ${cap:.2f}). Blocked before contacting the provider."
        )


@dataclass
class SpendStatus:
    """Everything `GET /api/v1/ai/budget` needs to render."""

    budget_usd: Decimal
    spent_usd: Decimal
    remaining_usd: Decimal
    call_count: int
    provider: str
    updated_at: str | None


class UsageRecorder:
    """Handed to the caller inside `govern()`'s `with` block.

    Starts holding the *estimated* token counts used for the pre-call check.
    A provider adapter that learns the real usage from the response calls this
    to correct it before the actual charge is written; one that has no better
    number (the mock adapter, or a provider response with no usage metadata)
    simply never calls it, and the estimate is billed instead.
    """

    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens

    def __call__(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


# ── Token & cost estimation ─────────────────────────────────────────────────


def estimate_tokens(text: str) -> int:
    """Cheap, provider-agnostic token estimate.

    ~4 characters per token is the standard rule of thumb for English prose,
    and it is what providers themselves quote when a real tokenizer is not
    available. It only has to be good enough to gate spend *before* the call;
    `govern()` lets the actual cost be corrected from real usage afterwards.
    """
    return max(1, -(-len(text) // 4))  # ceiling division, never zero


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Projected USD cost for a call, from the pricing table.

    An unrecognised model prices as free rather than raising - a new model
    string should fail open, not take the AI layer down over a pricing gap.
    """
    in_rate, out_rate = PRICING_USD_PER_1M_TOKENS.get(model, PRICING_USD_PER_1M_TOKENS["mock"])
    cost = (Decimal(prompt_tokens) * in_rate + Decimal(completion_tokens) * out_rate) / Decimal(
        "1000000"
    )
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


# ── Ledger persistence ───────────────────────────────────────────────────────


def _empty_ledger() -> dict[str, Any]:
    return {"total_cost_usd": "0", "call_count": 0, "updated_at": None, "calls": []}


def _read_ledger() -> dict[str, Any]:
    if not _LEDGER_PATH.exists():
        return _empty_ledger()
    try:
        data = json.loads(_LEDGER_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        # A half-written or hand-edited ledger must never take the AI layer
        # down - start fresh rather than crash over a bookkeeping file.
        return _empty_ledger()
    if not isinstance(data, dict):
        return _empty_ledger()
    return data


def _write_ledger(ledger: dict[str, Any]) -> None:
    """Atomic write: a tmp file in the same directory, then `os.replace`.

    `os.replace` is atomic on POSIX and Windows alike, so a concurrent reader
    - or a process crash mid-write - only ever sees the old ledger or the new
    one, never a truncated mix of both.
    """
    _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(_LEDGER_PATH.parent), prefix=".ai_spend-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(ledger, fh, indent=2)
        os.replace(tmp_name, _LEDGER_PATH)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


# In-file call history is capped so `ai_spend.json` cannot grow unboundedly
# across a long-running dev server; the running total, not the history, is
# what governs spend.
_MAX_RECENT_CALLS = 200


def _append_call(
    *,
    provider: str,
    model: str,
    tool_name: str,
    cost: Decimal,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    with _LOCK:
        ledger = _read_ledger()
        total = Decimal(str(ledger.get("total_cost_usd", "0"))) + cost
        now = datetime.now(UTC).isoformat()

        ledger["total_cost_usd"] = str(total)
        ledger["call_count"] = int(ledger.get("call_count", 0)) + 1
        ledger["updated_at"] = now

        calls = list(ledger.get("calls", []))
        calls.append(
            {
                "timestamp": now,
                "provider": provider,
                "model": model,
                "tool": tool_name,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_usd": str(cost),
            }
        )
        ledger["calls"] = calls[-_MAX_RECENT_CALLS:]

        _write_ledger(ledger)


def current_spend() -> Decimal:
    """Total spend recorded so far, read fresh from disk."""
    with _LOCK:
        return Decimal(str(_read_ledger().get("total_cost_usd", "0")))


def get_status() -> SpendStatus:
    """Everything `GET /api/v1/ai/budget` needs, in one read."""
    settings = get_settings()
    with _LOCK:
        ledger = _read_ledger()
    spent = Decimal(str(ledger.get("total_cost_usd", "0")))
    cap = Decimal(str(settings.ai_budget_usd))
    return SpendStatus(
        budget_usd=cap,
        spent_usd=spent,
        remaining_usd=max(cap - spent, Decimal("0")),
        call_count=int(ledger.get("call_count", 0)),
        provider=settings.ai_provider,
        updated_at=ledger.get("updated_at"),
    )


# ── The governor ─────────────────────────────────────────────────────────────


def check_budget(projected_cost: Decimal) -> None:
    """Raise `BudgetExceeded` if `projected_cost` would breach the cap.

    Exposed on its own (not only via `govern()`) so a caller can pre-flight a
    check without wrapping an entire call - e.g. to fail a request fast.
    """
    settings = get_settings()
    cap = Decimal(str(settings.ai_budget_usd))
    remaining = cap - current_spend()
    if projected_cost > remaining:
        raise BudgetExceeded(projected_cost, remaining, cap)


@contextmanager
def govern(
    *,
    provider: str,
    model: str,
    tool_name: str,
    estimated_prompt_tokens: int,
    estimated_completion_tokens: int,
) -> Iterator[UsageRecorder]:
    """Guard one provider call.

    Usage::

        with govern(provider=..., model=..., tool_name=..., ...) as record_usage:
            response = call_the_provider()
            record_usage(response.prompt_tokens, response.completion_tokens)

    The projected cost is checked against the remaining budget *before*
    control is ever yielded to the caller, so `BudgetExceeded` is always
    raised before anything that could reach a provider runs. Spend is written
    to the ledger only once the `with` block completes without raising - a
    failed call is never billed. Calling the yielded recorder is optional; if
    the caller never learns the real usage, the pre-call estimate is billed
    instead of nothing.
    """
    projected = estimate_cost(model, estimated_prompt_tokens, estimated_completion_tokens)
    check_budget(projected)

    recorder = UsageRecorder(estimated_prompt_tokens, estimated_completion_tokens)
    yield recorder

    actual_cost = estimate_cost(model, recorder.prompt_tokens, recorder.completion_tokens)
    _append_call(
        provider=provider,
        model=model,
        tool_name=tool_name,
        cost=actual_cost,
        prompt_tokens=recorder.prompt_tokens,
        completion_tokens=recorder.completion_tokens,
    )


# ── Response cache ───────────────────────────────────────────────────────────


def cache_key(*parts: str) -> str:
    """Stable key from the exact request shape. `\\x1f` (unit separator)
    joins the parts so no field can be confused with a delimiter that might
    legitimately appear inside a prompt."""
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def cache_lookup(key: str) -> dict[str, Any] | None:
    """A cached response for `key`, or None on a miss, a disabled cache, or a
    cache entry that fails to parse."""
    if not get_settings().ai_cache_enabled:
        return None
    path = _CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def cache_store(key: str, value: dict[str, Any]) -> None:
    """Persist `value` for `key`. A no-op while caching is disabled."""
    if not get_settings().ai_cache_enabled:
        return
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(_CACHE_DIR), prefix=".cache-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(value, fh)
        os.replace(tmp_name, _CACHE_DIR / f"{key}.json")
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
