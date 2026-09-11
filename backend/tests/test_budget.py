"""The cost governor: the hard cap, spend accounting, ledger durability and
the response cache.

`tests/conftest.py`'s `_isolated_ai_ledger` fixture (autouse) already points
`app.ai.budget._LEDGER_PATH` / `_CACHE_DIR` at a throwaway directory for every
test in this suite, so these tests never touch the real `backend/ai_spend.json`
this project ships against.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.ai import budget
from app.core.config import Settings
from app.schemas.enums import UserRole


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "ai_provider": "mock",
        "ai_budget_usd": 10.0,
        "ai_cache_enabled": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


# ── the hard cap ──────────────────────────────────────────────────────────────


def test_budget_exceeded_raised_before_the_provider_call_body_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The point of `govern()`: the projected cost is checked, and can raise,
    *before* control is ever handed to the caller's `with` block - so a
    provider call inside that block genuinely never happens."""
    monkeypatch.setattr(budget, "get_settings", lambda: _settings(ai_budget_usd=0.0000001))

    provider_was_called = False

    with (
        pytest.raises(budget.BudgetExceeded),
        budget.govern(
            provider="openai",
            model="gpt-5-nano",
            tool_name="test_tool",
            estimated_prompt_tokens=1_000_000,
            estimated_completion_tokens=1_000_000,
        ) as record_usage,
    ):
        provider_was_called = True  # would only run if the guard failed
        record_usage(1_000_000, 1_000_000)

    assert provider_was_called is False
    status = budget.get_status()
    assert status.call_count == 0
    assert status.spent_usd == Decimal("0")


def test_budget_exceeded_carries_the_cap_and_remaining_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(budget, "get_settings", lambda: _settings(ai_budget_usd=0.10))

    with pytest.raises(budget.BudgetExceeded) as exc_info:
        budget.check_budget(Decimal("0.20"))

    err = exc_info.value
    assert err.cap == Decimal("0.10")
    assert err.remaining_budget == Decimal("0.10")
    assert err.projected_cost == Decimal("0.20")
    assert "0.10" in str(err) or "0.100000" in str(err)


def test_a_call_within_budget_is_allowed_and_billed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget, "get_settings", lambda: _settings(ai_budget_usd=10.0))

    with budget.govern(
        provider="openai",
        model="gpt-5-nano",
        tool_name="test_tool",
        estimated_prompt_tokens=1000,
        estimated_completion_tokens=500,
    ) as record_usage:
        record_usage(1000, 500)

    status = budget.get_status()
    assert status.call_count == 1
    assert status.spent_usd == budget.estimate_cost("gpt-5-nano", 1000, 500)


def test_a_failed_provider_call_is_never_billed(monkeypatch: pytest.MonkeyPatch) -> None:
    """`govern()`'s spend write only happens if the `with` block completes -
    an exception raised *inside* it (a real provider failure, as opposed to a
    budget rejection) must not be charged for."""
    monkeypatch.setattr(budget, "get_settings", lambda: _settings(ai_budget_usd=10.0))

    class SimulatedProviderError(Exception):
        pass

    with (
        pytest.raises(SimulatedProviderError),
        budget.govern(
            provider="openai",
            model="gpt-5-nano",
            tool_name="test_tool",
            estimated_prompt_tokens=100,
            estimated_completion_tokens=100,
        ),
    ):
        raise SimulatedProviderError

    assert budget.get_status().call_count == 0


# ── spend accounting ─────────────────────────────────────────────────────────


def test_spend_accumulates_across_successive_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget, "get_settings", lambda: _settings(ai_budget_usd=10.0))

    with budget.govern(
        provider="openai",
        model="gpt-5-nano",
        tool_name="t1",
        estimated_prompt_tokens=1000,
        estimated_completion_tokens=500,
    ) as record:
        record(1000, 500)
    with budget.govern(
        provider="openai",
        model="gpt-5-nano",
        tool_name="t2",
        estimated_prompt_tokens=2000,
        estimated_completion_tokens=1000,
    ) as record:
        record(2000, 1000)

    status = budget.get_status()
    assert status.call_count == 2
    expected = budget.estimate_cost("gpt-5-nano", 1000, 500) + budget.estimate_cost(
        "gpt-5-nano", 2000, 1000
    )
    assert status.spent_usd == expected
    assert status.remaining_usd == status.budget_usd - expected


def test_actual_usage_is_billed_over_the_pre_call_estimate(monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider that reports real usage lower than the pre-call estimate
    must be billed for the real usage, not the (necessarily conservative)
    estimate used only to clear the budget check."""
    monkeypatch.setattr(budget, "get_settings", lambda: _settings(ai_budget_usd=10.0))

    with budget.govern(
        provider="openai",
        model="gpt-5-nano",
        tool_name="t",
        estimated_prompt_tokens=999_999,
        estimated_completion_tokens=999_999,
    ) as record:
        record(10, 5)  # real usage, much smaller than the estimate

    status = budget.get_status()
    assert status.spent_usd == budget.estimate_cost("gpt-5-nano", 10, 5)
    assert status.spent_usd < budget.estimate_cost("gpt-5-nano", 999_999, 999_999)


# ── ledger durability ────────────────────────────────────────────────────────


def test_ledger_persists_to_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget, "get_settings", lambda: _settings(ai_budget_usd=10.0))

    with budget.govern(
        provider="mock",
        model="mock",
        tool_name="my_tool",
        estimated_prompt_tokens=10,
        estimated_completion_tokens=10,
    ) as record:
        record(10, 10)

    assert budget._LEDGER_PATH.exists()
    import json

    data = json.loads(budget._LEDGER_PATH.read_text())
    assert data["call_count"] == 1
    assert len(data["calls"]) == 1
    assert data["calls"][0]["tool"] == "my_tool"
    assert data["calls"][0]["provider"] == "mock"


def test_corrupt_ledger_file_resets_rather_than_crashing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget, "get_settings", lambda: _settings(ai_budget_usd=10.0))

    budget._LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    budget._LEDGER_PATH.write_text("{not valid json at all")

    assert budget.current_spend() == Decimal("0")
    status = budget.get_status()
    assert status.spent_usd == Decimal("0")
    assert status.call_count == 0


def test_ledger_write_is_atomic_and_leaves_no_tmp_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget, "get_settings", lambda: _settings(ai_budget_usd=10.0))

    with budget.govern(
        provider="mock",
        model="mock",
        tool_name="t",
        estimated_prompt_tokens=5,
        estimated_completion_tokens=5,
    ) as record:
        record(5, 5)

    leftover = list(budget._LEDGER_PATH.parent.glob(".ai_spend-*.tmp"))
    assert leftover == []


# ── pricing table ─────────────────────────────────────────────────────────────


def test_estimate_cost_uses_the_pricing_table() -> None:
    assert budget.estimate_cost("gpt-5-nano", 1_000_000, 1_000_000) == Decimal("0.45")
    assert budget.estimate_cost("mock", 1_000_000, 1_000_000) == Decimal("0")
    assert budget.estimate_cost("gemini-2.5-flash", 1_000_000, 1_000_000) == Decimal("0")


def test_estimate_cost_unknown_model_prices_as_free_rather_than_raising() -> None:
    assert budget.estimate_cost("some-unlisted-model", 1_000_000, 1_000_000) == Decimal("0")


def test_estimate_tokens_is_never_zero_and_scales_with_length() -> None:
    assert budget.estimate_tokens("") == 1
    assert budget.estimate_tokens("a") == 1
    assert budget.estimate_tokens("a" * 400) == 100


# ── response cache ───────────────────────────────────────────────────────────


def test_cache_hit_is_not_billed_again(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ai import providers
    from app.ai.tools.extract import extract_complaint

    settings = _settings(ai_cache_enabled=True)
    monkeypatch.setattr(budget, "get_settings", lambda: settings)
    monkeypatch.setattr(providers, "get_settings", lambda: settings)

    text = "Product: X\nBatch number is ABC-123. 5 units affected."
    extract_complaint(text)
    extract_complaint(text)  # identical input - must be a cache hit

    assert budget.get_status().call_count == 1


def test_cache_disabled_bills_every_call(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ai import providers
    from app.ai.tools.extract import extract_complaint

    settings = _settings(ai_cache_enabled=False)
    monkeypatch.setattr(budget, "get_settings", lambda: settings)
    monkeypatch.setattr(providers, "get_settings", lambda: settings)

    text = "Product: X\nBatch number is ABC-123. 5 units affected."
    extract_complaint(text)
    extract_complaint(text)

    assert budget.get_status().call_count == 2


def test_cache_key_differs_for_different_input() -> None:
    a = budget.cache_key("mock", "mock", "extract_complaint", "Schema", "sys", "text one")
    b = budget.cache_key("mock", "mock", "extract_complaint", "Schema", "sys", "text two")
    assert a != b


def test_cache_lookup_miss_returns_none() -> None:
    assert budget.cache_lookup("no-such-key") is None


def test_cache_store_then_lookup_round_trips() -> None:
    key = budget.cache_key("mock", "mock", "tool", "Schema", "sys", "user")
    budget.cache_store(key, {"hello": "world"})
    assert budget.cache_lookup(key) == {"hello": "world"}


# ── the /budget endpoint ─────────────────────────────────────────────────────


def test_budget_endpoint_call_count_increases_after_an_extraction(
    client: TestClient, auth_headers
) -> None:
    headers = auth_headers(UserRole.COMPLAINT_OFFICER)
    before = client.get("/api/v1/ai/budget", headers=headers).json()

    response = client.post(
        "/api/v1/ai/extract",
        json={"text": "Product: X. Batch number is ABC-1. 3 units affected."},
        headers=headers,
    )
    assert response.status_code == 200

    after = client.get("/api/v1/ai/budget", headers=headers).json()
    assert after["call_count"] == before["call_count"] + 1
