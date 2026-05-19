# Timestamp: 2026-04-20 20:05:00

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any, Iterable

from .schemas import CandidateRecord, MergeRecord, PromotionRecord


def parse_json_payload(payload: str, required_top_level: str | None = None) -> Any:
    decoder = json.JSONDecoder()
    attempts = [payload.strip(), payload.strip().removeprefix("```json").removesuffix("```").strip()]

    for candidate in attempts:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if required_top_level and (not isinstance(parsed, dict) or required_top_level not in parsed):
                raise ValueError(f"Missing required top level key: {required_top_level}")
            return parsed
        except (JSONDecodeError, ValueError):
            pass

    for index, character in enumerate(payload):
        if character not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(payload[index:])
            if required_top_level and (not isinstance(parsed, dict) or required_top_level not in parsed):
                raise ValueError(f"Missing required top level key: {required_top_level}")
            return parsed
        except (JSONDecodeError, ValueError):
            continue

    raise ValueError("Could not parse JSON payload")


def ensure_required_fields(payload: dict[str, Any], required_fields: Iterable[str]) -> None:
    missing = [field for field in required_fields if field not in payload]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")


def coerce_candidate_records(payload: Any) -> list[CandidateRecord]:
    if isinstance(payload, dict):
        if "items" in payload:
            payload = payload["items"]
        elif "candidates" in payload:
            payload = payload["candidates"]
    if not isinstance(payload, list):
        raise ValueError("Candidate payload must be a list")
    records: list[CandidateRecord] = []
    for item in payload:
        ensure_required_fields(
            item,
            [
                "surface_form",
                "normalized_form",
                "canonical_candidate",
                "candidate_type",
                "business_relevance",
                "general_reusability",
                "cross_domain_applicability",
                "relational_centrality",
                "abstraction_fitness",
                "ontological_clarity",
                "composability",
                "compression_survival_likelihood",
                "is_domain_specific",
                "generalizable",
                "suggested_generalization",
                "promotion_decision",
                "notes",
            ],
        )
        if "antonyms" not in item:
            item = {**item, "antonyms": []}
        records.append(CandidateRecord.from_dict(item))
    return records


def coerce_merge_records(payload: Any) -> list[MergeRecord]:
    if isinstance(payload, dict):
        payload = payload.get("items", payload.get("merge_records", payload))
    if not isinstance(payload, list):
        raise ValueError("Merge payload must be a list")
    return [MergeRecord.from_dict(item) for item in payload]


def coerce_promotion_records(payload: Any) -> list[PromotionRecord]:
    if isinstance(payload, dict):
        payload = payload.get("items", payload.get("promotion_records", payload))
    if not isinstance(payload, list):
        raise ValueError("Promotion payload must be a list")
    return [PromotionRecord.from_dict(item) for item in payload]
