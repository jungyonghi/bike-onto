# Timestamp: 2026-04-20 20:05:00
# Timestamp: 2026-04-20 20:55:00

from __future__ import annotations

import json
from dataclasses import replace

from .runtime_llama import generate
from .schemas import CandidateRecord, PhaseContext, PromotionRecord, RunSummary
from .validators import coerce_candidate_records, coerce_promotion_records, parse_json_payload


GENERAL_CATEGORIES = [
    "actor/person",
    "organization",
    "place/location",
    "time/schedule",
    "object/asset",
    "event",
    "process/capability",
    "information/document",
    "contract/policy/right",
    "value/cost/revenue",
    "risk/compliance",
    "channel/interface/touchpoint",
]

RETAINED_DECISIONS = {
    "core_upper",
    "business_archetype",
    "general_reference",
    "needs_review",
    "hold_for_review",
}

BATCH_SIZE = 30


def _general_category_for_candidate(candidate: CandidateRecord) -> str:
    text = " ".join(
        part
        for part in [
            candidate.canonical_candidate,
            candidate.suggested_generalization,
            candidate.notes,
        ]
        if part
    ).lower()

    if any(token in text for token in ("actor", "customer", "client", "subscriber", "user", "person")):
        return "actor/person"
    if any(token in text for token in ("organization", "company", "department", "team")):
        return "organization"
    if any(token in text for token in ("place", "location", "station", "site", "facility", "point")):
        return "place/location"
    if any(token in text for token in ("time", "schedule", "interval", "date")):
        return "time/schedule"
    if any(token in text for token in ("asset", "object", "device", "product")):
        return "object/asset"
    if any(token in text for token in ("event", "incident", "transaction")):
        return "event"
    if any(token in text for token in ("process", "workflow", "operation", "capability")):
        return "process/capability"
    if any(token in text for token in ("document", "record", "information", "data")):
        return "information/document"
    if any(token in text for token in ("contract", "policy", "right", "entitlement", "obligation")):
        return "contract/policy/right"
    if any(token in text for token in ("value", "cost", "revenue", "price", "payment")):
        return "value/cost/revenue"
    if any(token in text for token in ("risk", "compliance", "control", "violation")):
        return "risk/compliance"
    if any(token in text for token in ("channel", "interface", "touchpoint", "portal", "kiosk")):
        return "channel/interface/touchpoint"
    return "object/asset"


def build_run_summary(
    promoted_candidates: list[CandidateRecord],
    review_count: int,
    rejected_count: int,
) -> RunSummary:
    target_ratio = {
        "business_archetype": 0.7,
        "general_reference_plus_core_upper": 0.3,
    }
    total = len(promoted_candidates)
    business_count = sum(1 for item in promoted_candidates if item.promotion_decision == "business_archetype")
    general_count = sum(
        1
        for item in promoted_candidates
        if item.promotion_decision in {"general_reference", "core_upper"}
    )
    observed_ratio = {
        "business_archetype": round(business_count / total, 4) if total else 0.0,
        "general_reference_plus_core_upper": round(general_count / total, 4) if total else 0.0,
    }

    general_category_balance = {category: 0 for category in GENERAL_CATEGORIES}
    for candidate in promoted_candidates:
        if candidate.promotion_decision not in {"general_reference", "core_upper"}:
            continue
        general_category_balance[_general_category_for_candidate(candidate)] += 1

    return RunSummary(
        target_ratio=target_ratio,
        observed_ratio=observed_ratio,
        general_category_balance=general_category_balance,
        review_count=review_count,
        rejected_count=rejected_count,
        notes="knowledge_source=llm_prior",
    )


def _build_prompt(template: str, candidates: list[CandidateRecord]) -> str:
    payload = {
        "instruction": template,
        "output_contract": (
            "Return JSON only. Use {'candidate_records': candidate_record[], 'promotion_records': promotion_record[]} "
            "as the top-level object."
        ),
        "antonym_policy": {
            "target_decisions": sorted(RETAINED_DECISIONS),
            "reject_antonyms": [],
            "semantic_basis": "conceptual opposite axis, not lexical opposite",
        },
        "candidates": [candidate.to_dict() for candidate in candidates],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _sanitize_antonyms(candidate: CandidateRecord) -> list[str]:
    if candidate.promotion_decision == "reject":
        return []
    if candidate.promotion_decision not in RETAINED_DECISIONS:
        return []
    seen: set[str] = set()
    antonyms: list[str] = []
    for item in candidate.antonyms:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        antonyms.append(normalized)
    return antonyms


def run_phase_g(
    context: PhaseContext,
    candidates: list[CandidateRecord],
) -> tuple[list[CandidateRecord], list[PromotionRecord], RunSummary]:
    phase_doc = context.protocol_bundle.phase_docs["phase_g"]
    promoted_candidates: list[CandidateRecord] = []
    promotion_records: list[PromotionRecord] = []

    for index in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[index : index + BATCH_SIZE]
        response = generate(
            prompt=_build_prompt(phase_doc.prompt_template, batch),
            system_prompt=context.protocol_bundle.system_prompt,
            host=context.host,
            port=context.port,
            max_tokens=4096,
        )
        parsed = parse_json_payload(response, required_top_level="candidate_records")
        batch_candidates = coerce_candidate_records(parsed["candidate_records"])
        if len(batch_candidates) != len(batch):
            raise ValueError("phase_g candidate count mismatch")
        if "promotion_records" not in parsed:
            raise ValueError("phase_g response missing promotion_records")
        batch_promotion_records = coerce_promotion_records(parsed["promotion_records"])

        promoted_candidates.extend(
            replace(candidate, antonyms=_sanitize_antonyms(candidate)) for candidate in batch_candidates
        )
        promotion_records.extend(batch_promotion_records)

    review_count = sum(
        1 for candidate in promoted_candidates if candidate.promotion_decision in {"hold_for_review", "needs_review"}
    )
    rejected_count = sum(1 for candidate in promoted_candidates if candidate.promotion_decision == "reject")
    summary = build_run_summary(promoted_candidates, review_count, rejected_count)
    return promoted_candidates, promotion_records, summary
