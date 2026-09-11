"""Single interface, three adapters.

Every provider-specific branch in the whole codebase lives in this module and
nowhere else - `app/ai/tools/*` never import a provider SDK, and never see the
word "gemini" or "openai". A tool builds a system prompt and a user prompt and
calls one of the three functions below; this module decides how to actually
get a filled-in instance of the requested Pydantic schema back, whether that
means calling out to Gemini, calling out to OpenAI, or - for `mock`, the only
provider the test suite is ever allowed to reach - running a small
deterministic, regex-based reader with zero network access and no API key.

Every path through `_dispatch()` goes through `app/ai/budget.py`'s `govern()`
first, so a call that would exceed the budget is rejected before anything here
tries to reach a provider.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

from app.ai import budget
from app.core.config import Settings, get_settings
from app.schemas.complaint import AIAssessment, ExtractedComplaint
from app.schemas.enums import (
    AIConfidence,
    ComplaintSource,
    ComplaintType,
    DosageForm,
    Priority,
    QuantityUnit,
    Severity,
)


class ProviderError(RuntimeError):
    """A provider call failed, or the requested provider is unavailable."""


def _model_name(provider: str, settings: Settings) -> str:
    if provider == "gemini":
        return settings.gemini_model
    if provider == "openai":
        return settings.openai_model
    return "mock"


def _dispatch[ModelT: BaseModel](
    *,
    tool_name: str,
    system_prompt: str,
    user_prompt: str,
    schema: type[ModelT],
    mock_response: Any,
) -> ModelT:
    """Shared plumbing for every tool call: cache, budget, dispatch, cache-fill.

    `mock_response` is a zero-argument callable producing the dict the mock
    provider should answer with; it is only ever invoked when
    `settings.ai_provider == "mock"`, so building it never costs anything and
    never needs network access even when the active provider is real.
    """
    settings = get_settings()
    provider = settings.ai_provider
    model = _model_name(provider, settings)

    key = budget.cache_key(provider, model, tool_name, schema.__name__, system_prompt, user_prompt)
    cached = budget.cache_lookup(key)
    if cached is not None:
        return schema.model_validate(cached)

    estimated_prompt_tokens = budget.estimate_tokens(system_prompt + user_prompt)
    estimated_completion_tokens = settings.ai_max_output_tokens

    with budget.govern(
        provider=provider,
        model=model,
        tool_name=tool_name,
        estimated_prompt_tokens=estimated_prompt_tokens,
        estimated_completion_tokens=estimated_completion_tokens,
    ) as record_usage:
        if provider == "mock":
            data = mock_response()
            usage = (
                estimated_prompt_tokens,
                budget.estimate_tokens(json.dumps(data, default=str)),
            )
        elif provider == "gemini":
            data, usage = _call_gemini(system_prompt, user_prompt, schema, settings)
        elif provider == "openai":
            data, usage = _call_openai(system_prompt, user_prompt, schema, settings)
        else:  # pragma: no cover - Settings.ai_provider is a Literal
            raise ProviderError(f"Unsupported AI provider: {provider!r}")

        record_usage(*usage)

    result = schema.model_validate(data)
    budget.cache_store(key, result.model_dump(mode="json"))
    return result


# ── Public tool-facing API ──────────────────────────────────────────────────


def extract_fields(*, system_prompt: str, user_prompt: str, source_text: str) -> ExtractedComplaint:
    """Structured extraction from `source_text` (a complaint narrative)."""
    return _dispatch(
        tool_name="extract_complaint",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=ExtractedComplaint,
        mock_response=lambda: _mock_extract(source_text),
    )


def derive_edit(
    *, system_prompt: str, user_prompt: str, instruction_text: str
) -> ExtractedComplaint:
    """Structured extraction from `instruction_text` (a change request).

    Returns `ExtractedComplaint`, the same shape `extract_fields` returns -
    `app/ai/tools/edit.py` is what turns this into a `ComplaintUpdate`, using
    the response's `provenance` list to decide which fields actually changed.
    """
    return _dispatch(
        tool_name="edit_complaint",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=ExtractedComplaint,
        mock_response=lambda: _mock_extract(instruction_text),
    )


def assess(*, system_prompt: str, user_prompt: str, complaint: dict[str, Any]) -> AIAssessment:
    """An advisory assessment of `complaint` (a JSON-mode complaint dict)."""
    return _dispatch(
        tool_name="assess_complaint",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=AIAssessment,
        mock_response=lambda: _mock_assess(complaint),
    )


# ── gemini ───────────────────────────────────────────────────────────────────


def _call_gemini[ModelT: BaseModel](
    system_prompt: str, user_prompt: str, schema: type[ModelT], settings: Settings
) -> tuple[dict[str, Any], tuple[int, int]]:
    """Structured output via `langchain-google-genai`. Imported lazily so the
    mock-only test suite never has to import (or configure) it."""
    if not settings.google_api_key:
        raise ProviderError("GOOGLE_API_KEY is not set; cannot call the gemini provider.")

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key,
        max_output_tokens=settings.ai_max_output_tokens,
        temperature=0,
    )
    structured = llm.with_structured_output(schema, include_raw=True)
    response = structured.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    )
    if not isinstance(response, dict):
        raise ProviderError(f"gemini returned an unexpected response shape for {schema.__name__}")

    parsed = response.get("parsed")
    if parsed is None:
        raise ProviderError(f"gemini returned no parseable {schema.__name__}")

    raw = response.get("raw")
    usage = getattr(raw, "usage_metadata", None) or {}
    prompt_tokens = usage.get("input_tokens") or budget.estimate_tokens(system_prompt + user_prompt)
    completion_tokens = usage.get("output_tokens") or budget.estimate_tokens(str(parsed))
    return parsed.model_dump(mode="json"), (int(prompt_tokens), int(completion_tokens))


# ── openai ───────────────────────────────────────────────────────────────────


def _call_openai[ModelT: BaseModel](
    system_prompt: str, user_prompt: str, schema: type[ModelT], settings: Settings
) -> tuple[dict[str, Any], tuple[int, int]]:
    """Structured output via `langchain-openai`. Imported lazily, same reason
    as `_call_gemini`."""
    if not settings.openai_api_key:
        raise ProviderError("OPENAI_API_KEY is not set; cannot call the openai provider.")

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        max_completion_tokens=settings.ai_max_output_tokens,
    )
    structured = llm.with_structured_output(schema, include_raw=True)
    response = structured.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    )
    if not isinstance(response, dict):
        raise ProviderError(f"openai returned an unexpected response shape for {schema.__name__}")

    parsed = response.get("parsed")
    if parsed is None:
        raise ProviderError(f"openai returned no parseable {schema.__name__}")

    raw = response.get("raw")
    usage = getattr(raw, "usage_metadata", None) or {}
    prompt_tokens = usage.get("input_tokens") or budget.estimate_tokens(system_prompt + user_prompt)
    completion_tokens = usage.get("output_tokens") or budget.estimate_tokens(str(parsed))
    return parsed.model_dump(mode="json"), (int(prompt_tokens), int(completion_tokens))


# ── mock ─────────────────────────────────────────────────────────────────────
#
# Deterministic, regex-based, zero network. This is what `tests/conftest.py`'s
# `_assert_never_live` fixture exercises for the entire suite, so it has to
# stand on its own as a genuine (if limited) reader of complaint text - not a
# stub that only satisfies a specific test's expectations.

# A mandatory connector (":", "-", "is", "was", "to") between the label and
# the value is what keeps these from firing on a bare mention of the word -
# "the customer reported..." must not read as a customer_name. That connector
# is what lets the same patterns serve both a labeled narrative header
# ("Customer: Acme Hospital") and a natural edit instruction ("update the
# customer name to Acme Hospital") without two separate implementations.
_LABELED_PATTERNS: dict[str, re.Pattern[str]] = {
    "customer_name": re.compile(
        r"\bcustomer(?:\s*name)?\b\s*(?:is|was|to|:|-)\s*"
        r"(?P<value>[A-Za-z0-9][A-Za-z0-9&.,'\- ]*?)(?=[.,;\n]|$)",
        re.I,
    ),
    "product_name": re.compile(
        r"\bproduct(?:\s*name)?\b\s*(?:is|was|to|:|-)\s*"
        r"(?P<value>[A-Za-z0-9][A-Za-z0-9%.,'\- ]*?)(?=[.,;\n]|$)",
        re.I,
    ),
    "reporter_name": re.compile(
        r"\breport(?:ed|er)?\s*by\b\s*(?:is|was|to|:|-)?\s*"
        r"(?!phone\b|call\b|email\b|letter\b|portal\b)"
        r"(?P<value>[A-Za-z][A-Za-z0-9'\- ]*?)(?=[.,;\n]|$)",
        re.I,
    ),
}

_BATCH_LABELED_RE = re.compile(
    r"\bbatch\b(?:\s+(?:number|no\.?|#))?\s*(?:is|was|of)?\s*[:\-]?\s*"
    r"(?P<value>[A-Za-z][A-Za-z0-9]*(?:[\s\-][A-Za-z0-9]+)?)",
    re.I,
)
_LOT_LABELED_RE = re.compile(
    r"\blot\b(?:\s+(?:number|no\.?|#))?\s*(?:is|was|of)?\s*[:\-]?\s*"
    r"(?P<value>[A-Za-z][A-Za-z0-9]*(?:[\s\-][A-Za-z0-9]+)?)",
    re.I,
)

_UNIT_LOOKUP: dict[str, QuantityUnit] = {
    "tablet": QuantityUnit.TABLETS,
    "tablets": QuantityUnit.TABLETS,
    "capsule": QuantityUnit.CAPSULES,
    "capsules": QuantityUnit.CAPSULES,
    "vial": QuantityUnit.VIALS,
    "vials": QuantityUnit.VIALS,
    "ampoule": QuantityUnit.AMPOULES,
    "ampoules": QuantityUnit.AMPOULES,
    "bottle": QuantityUnit.BOTTLES,
    "bottles": QuantityUnit.BOTTLES,
    "blister": QuantityUnit.BLISTERS,
    "blisters": QuantityUnit.BLISTERS,
    "sachet": QuantityUnit.SACHETS,
    "sachets": QuantityUnit.SACHETS,
    "tube": QuantityUnit.TUBES,
    "tubes": QuantityUnit.TUBES,
    "box": QuantityUnit.BOXES,
    "boxes": QuantityUnit.BOXES,
    "carton": QuantityUnit.CARTONS,
    "cartons": QuantityUnit.CARTONS,
    "unit": QuantityUnit.UNITS,
    "units": QuantityUnit.UNITS,
    "kg": QuantityUnit.KG,
    "gram": QuantityUnit.G,
    "grams": QuantityUnit.G,
    "g": QuantityUnit.G,
    "mg": QuantityUnit.MG,
    "liter": QuantityUnit.L,
    "liters": QuantityUnit.L,
    "litre": QuantityUnit.L,
    "litres": QuantityUnit.L,
    "l": QuantityUnit.L,
    "ml": QuantityUnit.ML,
}
_QUANTITY_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>" + "|".join(re.escape(u) for u in _UNIT_LOOKUP) + r")\b",
    re.I,
)
# Affected quantity is reported in countable units ("48 capsules affected") far
# more often than in weight/volume units, which almost always describe product
# *strength* instead ("Amoxicillin 500 mg"). Preferring a countable match stops
# a strength mention elsewhere in the same text from being misread as the
# affected quantity.
_COUNTABLE_UNITS = frozenset(
    {
        QuantityUnit.TABLETS,
        QuantityUnit.CAPSULES,
        QuantityUnit.VIALS,
        QuantityUnit.AMPOULES,
        QuantityUnit.BOTTLES,
        QuantityUnit.BLISTERS,
        QuantityUnit.SACHETS,
        QuantityUnit.TUBES,
        QuantityUnit.BOXES,
        QuantityUnit.CARTONS,
        QuantityUnit.UNITS,
    }
)


def _find_quantity(text: str) -> re.Match[str] | None:
    """The best `_QUANTITY_RE` match in `text`, preferring a countable unit
    and, among those, the one nearest the word "affected" when present."""
    matches = [m for m in _QUANTITY_RE.finditer(text) if m.group("unit").lower() in _UNIT_LOOKUP]
    if not matches:
        return None

    countable = [m for m in matches if _UNIT_LOOKUP[m.group("unit").lower()] in _COUNTABLE_UNITS]
    pool = countable or matches

    affected_at = text.lower().find("affected")
    if affected_at != -1:
        pool = sorted(pool, key=lambda m: abs(m.start() - affected_at))
    return pool[0]


_COMPLAINT_TYPE_KEYWORDS: list[tuple[str, ComplaintType]] = [
    (r"adverse (?:event|reaction)|side effect|allergic reaction", ComplaintType.ADVERSE_EVENT),
    (r"microbial|mo[u]?ld|fungus|bacteria", ComplaintType.CONTAMINATION_MICROBIAL),
    (r"cross[- ]contaminat", ComplaintType.CONTAMINATION_CROSS),
    (r"tamper", ComplaintType.TAMPER_EVIDENCE),
    (r"foreign (?:matter|object|particle|material)", ComplaintType.FOREIGN_MATTER),
    (r"dissolution", ComplaintType.DISSOLUTION_FAILURE),
    (r"assay|out of specification|\boos\b", ComplaintType.ASSAY_OUT_OF_SPECIFICATION),
    (r"stability|degrad", ComplaintType.STABILITY_DEFECT),
    (
        r"not working|no effect|ineffective|lack of efficacy|efficacy",
        ComplaintType.EFFICACY_COMPLAINT,
    ),
    (
        r"short count|missing (?:tablets|capsules|units)|underfill|short fill",
        ComplaintType.SHORT_COUNT_OR_FILL,
    ),
    (r"device (?:malfunction|failure)|malfunction", ComplaintType.DEVICE_MALFUNCTION),
    (r"label(?:l?ing)? (?:error|mix[- ]?up|incorrect|wrong)", ComplaintType.LABELING_ERROR),
    (r"broken|chipped|crack(?:ed)?", ComplaintType.BROKEN_OR_CHIPPED),
    (r"leak|damaged (?:packaging|box|carton)|crushed", ComplaintType.PHYSICAL_DAMAGE),
    (r"packaging (?:defect|fault)|seal (?:broken|missing)", ComplaintType.PACKAGING_DEFECT),
    (r"smell|odor|odour|taste|bitter", ComplaintType.ODOR_OR_TASTE),
    (r"discolor|discolour|mottled|dark spot", ComplaintType.APPEARANCE_DISCOLORATION),
]

_SOURCE_KEYWORDS: list[tuple[str, ComplaintSource]] = [
    (r"field alert", ComplaintSource.FIELD_ALERT),
    (r"regulatory authority|\bfda\b|\bmhra\b|\bema\b", ComplaintSource.REGULATORY_AUTHORITY),
    (r"hospital pharmacy", ComplaintSource.HOSPITAL_PHARMACY),
    (r"retail pharmacy", ComplaintSource.RETAIL_PHARMACY),
    (r"distributor", ComplaintSource.DISTRIBUTOR),
    (r"sales rep", ComplaintSource.SALES_REPRESENTATIVE),
    (r"customer portal|web portal|online portal", ComplaintSource.CUSTOMER_PORTAL),
    (r"written letter|\bletter\b", ComplaintSource.WRITTEN_LETTER),
    (r"\bphone\b|\bcalled\b|\bphone call\b", ComplaintSource.PHONE),
    (r"\be-?mail\b", ComplaintSource.EMAIL),
]

_CRITICAL_FIELDS = (
    "product_name",
    "batch_number",
    "complaint_type",
    "quantity_affected",
    "customer_name",
)
_CLARIFYING_QUESTIONS = {
    "product_name": "Which product does this complaint concern?",
    "batch_number": "What is the batch or lot number?",
    "complaint_type": "What kind of defect or issue is being reported?",
    "quantity_affected": "How many units are affected, and in what unit?",
    "customer_name": "Who is the reporting customer or institution?",
}


def _mock_extract(text: str) -> dict[str, Any]:
    """Deterministic, regex-based reading of `text` into `ExtractedComplaint`
    shape. Only populates a field when a recognisable pattern matches - never
    guesses - matching the same rule the real prompts impose on gemini/openai."""
    fields: dict[str, Any] = {}
    provenance: list[dict[str, Any]] = []

    def _set(field: str, value: Any, excerpt: str, confidence: AIConfidence) -> None:
        fields[field] = value
        provenance.append(
            {
                "field": field,
                "confidence": confidence.value,
                "source_excerpt": excerpt.strip()[:500],
            }
        )

    for field, labeled_pattern in _LABELED_PATTERNS.items():
        match = labeled_pattern.search(text)
        if match:
            value = match.group("value").strip().rstrip(".")
            if value:
                _set(field, value, match.group(0), AIConfidence.HIGH)

    batch_match = _BATCH_LABELED_RE.search(text) or _LOT_LABELED_RE.search(text)
    if batch_match:
        batch_value = batch_match.group("value").strip()
        _set("batch_number", batch_value, batch_match.group(0), AIConfidence.HIGH)

    # Blanked out (not sliced away) so every later span offset - and every
    # later keyword scan - still lines up with the original text.
    text_remaining = text

    qty_match = _find_quantity(text)
    if qty_match is not None:
        unit = _UNIT_LOOKUP[qty_match.group("unit").lower()]
        _set("quantity_affected", qty_match.group("value"), qty_match.group(0), AIConfidence.HIGH)
        _set("quantity_unit", unit.value, qty_match.group(0), AIConfidence.HIGH)
        start, end = qty_match.span()
        text_remaining = text[:start] + " " * (end - start) + text[end:]

    for type_pattern, complaint_type_member in _COMPLAINT_TYPE_KEYWORDS:
        match = re.search(type_pattern, text, re.I)
        if match:
            _set("complaint_type", complaint_type_member.value, match.group(0), AIConfidence.MEDIUM)
            break

    # Scanned against `text_remaining`, with the winning quantity's span
    # blanked out: a countable unit word like "capsules" or "tablets" in
    # "48 capsules affected" is a unit of measure, not necessarily a
    # statement about the product's dosage form.
    for dosage_form_member in DosageForm:
        if dosage_form_member is DosageForm.OTHER:
            continue
        match = re.search(rf"\b{dosage_form_member.value}s?\b", text_remaining, re.I)
        if match:
            _set("dosage_form", dosage_form_member.value, match.group(0), AIConfidence.MEDIUM)
            break

    for source_pattern, source_member in _SOURCE_KEYWORDS:
        match = re.search(source_pattern, text, re.I)
        if match:
            _set("source", source_member.value, match.group(0), AIConfidence.MEDIUM)
            break

    missing = [f for f in _CRITICAL_FIELDS if f not in fields]
    return {
        "fields": fields,
        "provenance": provenance,
        "missing_fields": missing,
        "clarifying_questions": [_CLARIFYING_QUESTIONS[f] for f in missing][:5],
        "extraction_notes": (
            None if fields else "No structured fields could be confidently identified in the input."
        ),
    }


_SEVERITY_BY_TYPE: dict[str, Severity] = {
    ComplaintType.ADVERSE_EVENT.value: Severity.CRITICAL,
    ComplaintType.CONTAMINATION_MICROBIAL.value: Severity.CRITICAL,
    ComplaintType.CONTAMINATION_CROSS.value: Severity.CRITICAL,
    ComplaintType.TAMPER_EVIDENCE.value: Severity.CRITICAL,
    ComplaintType.DISSOLUTION_FAILURE.value: Severity.MAJOR,
    ComplaintType.ASSAY_OUT_OF_SPECIFICATION.value: Severity.MAJOR,
    ComplaintType.STABILITY_DEFECT.value: Severity.MAJOR,
    ComplaintType.DEVICE_MALFUNCTION.value: Severity.MAJOR,
    ComplaintType.FOREIGN_MATTER.value: Severity.MAJOR,
    ComplaintType.EFFICACY_COMPLAINT.value: Severity.MAJOR,
    ComplaintType.LABELING_ERROR.value: Severity.MAJOR,
    # Short count / short fill is a fill-volume or unit-count process-control
    # failure, not a cosmetic or administrative one - for a dose-critical form
    # it is a potential underdose/overdose patient-safety issue, which puts it
    # outside this project's own Severity.MINOR definition (see enums.py).
    ComplaintType.SHORT_COUNT_OR_FILL.value: Severity.MAJOR,
    ComplaintType.PACKAGING_DEFECT.value: Severity.MINOR,
    ComplaintType.PHYSICAL_DAMAGE.value: Severity.MINOR,
    ComplaintType.BROKEN_OR_CHIPPED.value: Severity.MINOR,
    ComplaintType.ODOR_OR_TASTE.value: Severity.MINOR,
    ComplaintType.APPEARANCE_DISCOLORATION.value: Severity.MINOR,
    ComplaintType.OTHER.value: Severity.MINOR,
}
_PRIORITY_BY_SEVERITY: dict[Severity, Priority] = {
    Severity.CRITICAL: Priority.URGENT,
    Severity.MAJOR: Priority.HIGH,
    Severity.MINOR: Priority.MEDIUM,
}
_ROOT_CAUSE_HYPOTHESES: dict[str, list[str]] = {
    ComplaintType.FOREIGN_MATTER.value: [
        "Possible contamination during filling or packaging",
        "Possible foreign material carried in via a raw material",
    ],
    ComplaintType.CONTAMINATION_MICROBIAL.value: [
        "Possible breach in aseptic processing or environmental control",
        "Possible inadequate preservative efficacy",
    ],
    ComplaintType.PACKAGING_DEFECT.value: [
        "Possible seal integrity failure at the packaging line",
        "Possible in-transit damage to primary packaging",
    ],
    ComplaintType.LABELING_ERROR.value: [
        "Possible line-clearance failure allowing label mix-up",
        "Possible printing or artwork version-control error",
    ],
    ComplaintType.DISSOLUTION_FAILURE.value: [
        "Possible formulation or granulation process deviation",
        "Possible stability-related change during shelf life",
    ],
    ComplaintType.SHORT_COUNT_OR_FILL.value: [
        "Possible filling-line calibration drift",
        "Possible count-check step failure at packaging",
    ],
}
_GENERIC_ROOT_CAUSES = [
    "Insufficient information to hypothesize a root cause; further investigation needed"
]
_TRIAGE_FIELDS = (
    "product_name",
    "batch_number",
    "complaint_type",
    "quantity_affected",
    "quantity_unit",
    "customer_name",
    "description",
    "complaint_date",
)


def _mock_assess(complaint: dict[str, Any]) -> dict[str, Any]:
    """Deterministic, rule-based read on `complaint`. Every list below is
    explicitly framed as a hypothesis or a suggestion, never a finding - see
    `app/ai/prompts/assess.py` for why that framing matters."""
    complaint_type = complaint.get("complaint_type")
    severity = _SEVERITY_BY_TYPE.get(complaint_type) if complaint_type else None
    priority = _PRIORITY_BY_SEVERITY.get(severity) if severity else None

    present = [f for f in _TRIAGE_FIELDS if complaint.get(f) not in (None, "")]
    missing = [f for f in _TRIAGE_FIELDS if f not in present]
    completeness = round(100 * len(present) / len(_TRIAGE_FIELDS))

    product = complaint.get("product_name") or "an unspecified product"
    batch = complaint.get("batch_number") or "an unknown batch"
    type_label = (complaint_type or "unclassified").replace("_", " ")

    regulatory: list[str] = []
    if severity is Severity.CRITICAL:
        regulatory = [
            "Evaluate against field alert / recall criteria per 21 CFR 211.198 and internal SOPs",
            "Consider whether adverse event reporting obligations apply",
        ]
    elif severity is Severity.MAJOR:
        regulatory = [
            "Evaluate whether this complaint, alone or as part of a trend, "
            "warrants a field alert assessment"
        ]

    severity_label = severity.value if severity else "undetermined"
    return {
        "summary": (
            f"{type_label.title()} complaint reported for {product} (batch {batch}). "
            f"Recommended severity for reviewer evaluation: {severity_label}."
        ),
        "recommended_severity": severity.value if severity else None,
        "recommended_priority": priority.value if priority else None,
        "severity_rationale": (
            f"Complaint type '{type_label}' commonly falls in this severity band as a "
            "general heuristic; a qualified reviewer should confirm against the specifics "
            "of this batch and product."
            if severity
            else "Complaint type is not yet established, so no severity can be recommended."
        ),
        "risk_factors": (
            ["No batch number on record - the affected population cannot yet be scoped"]
            if not complaint.get("batch_number")
            else []
        ),
        "completeness_score": completeness,
        "missing_critical_fields": missing,
        "potential_root_causes": (
            _ROOT_CAUSE_HYPOTHESES.get(complaint_type, _GENERIC_ROOT_CAUSES)
            if complaint_type
            else _GENERIC_ROOT_CAUSES
        ),
        "investigation_steps": [
            "Review batch manufacturing and QC records for the reported lot",
            "Request a retained sample or photographs from the complainant if not already provided",
            "Cross-check for other complaints against the same batch or product",
        ],
        "capa_recommendations": [
            "Hold any corrective action proposal pending the investigation's findings",
        ],
        "regulatory_considerations": regulatory,
    }
