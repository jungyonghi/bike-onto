# Timestamp: 2026-04-20 20:05:00
# Timestamp: 2026-04-20 20:55:00
# Timestamp: 2026-04-20 21:10:00
# Timestamp: 2026-04-20 21:22:00
# Timestamp: 2026-04-20 21:34:00

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any, Callable, NamedTuple

from .runtime_llama import generate
from .schemas import CandidateRecord, PhaseContext, RawCandidateRecord
from .validators import coerce_candidate_records, parse_json_payload


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

PHASE_A_BATCH_SIZE = 30


class GenerationRequest(NamedTuple):
    generation_stratum: str
    target_count: int
    general_category: str | None = None


def _normalize_surface_form(value: str) -> str:
    collapsed = re.sub(r"[\s/_-]+", " ", value.strip())
    return collapsed.lower()


def _extract_phase_a_items(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("items", payload.get("candidates", payload))
    if not isinstance(payload, list):
        raise ValueError("phase_a candidate payload must be a list")
    return [item for item in payload if isinstance(item, dict)]


def _select_raw_term(item: dict[str, Any]) -> tuple[str, str]:
    for field in ("surface_form", "name", "term", "canonical_candidate", "normalized_form", "id"):
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip(), field
    return json.dumps(item, ensure_ascii=False, sort_keys=True), "raw_payload_json"


def _build_raw_candidate_records(
    items: list[dict[str, Any]],
    request: GenerationRequest,
) -> list[RawCandidateRecord]:
    records: list[RawCandidateRecord] = []
    for item in items:
        raw_term, source_field = _select_raw_term(item)
        records.append(
            RawCandidateRecord(
                raw_term=raw_term,
                source_field=source_field,
                generation_stratum=request.generation_stratum,
                general_category=request.general_category or "",
                description=str(item.get("description") or ""),
                notes=str(item.get("notes") or ""),
                raw_payload_json=json.dumps(item, ensure_ascii=False, sort_keys=True),
            )
        )
    return records


def _coerce_phase_a_records(payload: object, request: GenerationRequest) -> list[CandidateRecord]:
    try:
        return coerce_candidate_records(payload)
    except ValueError:
        pass

    if isinstance(payload, dict):
        payload = payload.get("items", payload.get("candidates", payload))
    if not isinstance(payload, list):
        raise ValueError("phase_a candidate payload must be a list")

    records: list[CandidateRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        surface_form = str(item.get("surface_form") or item.get("name") or item.get("term") or "").strip()
        if not surface_form:
            continue
        normalized_form = str(item.get("normalized_form") or _normalize_surface_form(surface_form))
        canonical_candidate = str(item.get("canonical_candidate") or normalized_form)
        description = str(item.get("description") or "").strip()
        notes = str(item.get("notes") or "").strip()
        merged_notes = " | ".join(part for part in [description, notes] if part)
        is_business = request.generation_stratum == "business"

        records.append(
            CandidateRecord(
                surface_form=surface_form,
                normalized_form=normalized_form,
                canonical_candidate=canonical_candidate,
                candidate_type=str(item.get("candidate_type") or "class_candidate"),
                business_relevance=int(item.get("business_relevance") or (5 if is_business else 2)),
                general_reusability=int(item.get("general_reusability") or 4),
                cross_domain_applicability=int(item.get("cross_domain_applicability") or 4),
                relational_centrality=int(item.get("relational_centrality") or 3),
                abstraction_fitness=int(item.get("abstraction_fitness") or 3),
                ontological_clarity=int(item.get("ontological_clarity") or 3),
                composability=int(item.get("composability") or 3),
                compression_survival_likelihood=int(item.get("compression_survival_likelihood") or 3),
                is_domain_specific=bool(item.get("is_domain_specific", is_business)),
                generalizable=bool(item.get("generalizable", not is_business)),
                suggested_generalization=str(item.get("suggested_generalization") or ""),
                promotion_decision=str(item.get("promotion_decision") or ""),
                notes=merged_notes,
                antonyms=[],
            )
        )
    if not records:
        raise ValueError("phase_a_generation_returned_unusable_candidates")
    return records


def _build_prompt(template: str, request: GenerationRequest, total_target: int) -> str:
    payload = {
        "instruction": template,
        "output_contract": "Return JSON only. Use {'items': candidate_record[]} as top-level object.",
        "mode": "corpus_free_generation",
        "knowledge_source": "llm_prior",
        "generation_stratum": request.generation_stratum,
        "general_category": request.general_category,
        "target_count": request.target_count,
        "distribution_target": {
            "business": round((total_target // 2) / total_target, 4) if total_target else 0.0,
            "non_business": round((total_target - (total_target // 2)) / total_target, 4) if total_target else 0.0,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _resolve_raw_target(context: PhaseContext) -> int:
    if context.phase_a_raw_target is None:
        return context.phase_a_max_candidates
    return context.phase_a_raw_target


def _build_generation_plan(total_target: int) -> list[GenerationRequest]:
    business_target = total_target // 2
    non_business_target = total_target - business_target
    requests: list[GenerationRequest] = []

    remaining_business = business_target
    while remaining_business > 0:
        batch_count = min(PHASE_A_BATCH_SIZE, remaining_business)
        requests.append(GenerationRequest(generation_stratum="business", target_count=batch_count))
        remaining_business -= batch_count

    if non_business_target <= 0:
        return requests

    base = non_business_target // len(GENERAL_CATEGORIES)
    remainder = non_business_target % len(GENERAL_CATEGORIES)
    for index, category in enumerate(GENERAL_CATEGORIES):
        category_target = base + (1 if index < remainder else 0)
        while category_target > 0:
            batch_count = min(PHASE_A_BATCH_SIZE, category_target)
            requests.append(
                GenerationRequest(
                    generation_stratum="non_business",
                    general_category=category,
                    target_count=batch_count,
                )
            )
            category_target -= batch_count

    return requests


def _annotate_record(record: CandidateRecord, request: GenerationRequest) -> CandidateRecord:
    note_parts = [record.notes, f"generation_stratum={request.generation_stratum}"]
    if request.general_category:
        note_parts.append(f"general_category={request.general_category}")
    return replace(record, notes=" | ".join(part for part in note_parts if part), antonyms=[])


def _generate_batch(
    context: PhaseContext,
    request: GenerationRequest,
    total_target: int,
) -> tuple[list[RawCandidateRecord], list[CandidateRecord], list[dict[str, Any]]]:
    phase_doc = context.protocol_bundle.phase_docs["phase_a"]
    response = generate(
        prompt=_build_prompt(phase_doc.prompt_template, request, total_target),
        system_prompt=context.protocol_bundle.system_prompt,
        host=context.host,
        port=context.port,
        max_tokens=4096,
    )
    parsed = parse_json_payload(response, required_top_level="items")
    raw_items = _extract_phase_a_items(parsed)
    raw_records = _build_raw_candidate_records(raw_items, request)
    records = _coerce_phase_a_records({"items": raw_items}, request)
    if not records:
        raise RuntimeError(
            f"phase_a_generation_returned_no_candidates[{request.generation_stratum}:{request.general_category or 'all'}]"
        )
    return (
        raw_records,
        [_annotate_record(record, request) for record in records[: request.target_count]],
        raw_items,
    )


def run_phase_a_with_artifacts(
    context: PhaseContext,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[RawCandidateRecord], list[CandidateRecord], list[dict[str, Any]]]:
    raw_target = _resolve_raw_target(context)
    collected_raw_records: list[RawCandidateRecord] = []
    collected: list[CandidateRecord] = []
    collected_raw_items: list[dict[str, Any]] = []
    plan = _build_generation_plan(raw_target)
    for batch_index, request in enumerate(plan, start=1):
        if len(collected_raw_records) >= raw_target:
            break
        batch_raw_records, batch_records, batch_raw_items = _generate_batch(
            context,
            request,
            raw_target,
        )
        remaining_raw = raw_target - len(collected_raw_records)
        collected_raw_records.extend(batch_raw_records[:remaining_raw])
        collected_raw_items.extend(batch_raw_items[:remaining_raw])

        remaining_candidates = context.phase_a_max_candidates - len(collected)
        if remaining_candidates > 0:
            collected.extend(batch_records[:remaining_candidates])
        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "phase_a",
                    "event": "batch_completed",
                    "batch_index": batch_index,
                    "batch_total": len(plan),
                    "raw_count": len(collected_raw_records),
                    "raw_target": raw_target,
                    "candidate_count": len(collected),
                    "candidate_target": context.phase_a_max_candidates,
                    "generation_stratum": request.generation_stratum,
                    "general_category": request.general_category or "",
                }
            )
    return collected_raw_records, collected, collected_raw_items


def run_phase_a(context: PhaseContext) -> list[CandidateRecord]:
    _, collected, _ = run_phase_a_with_artifacts(context)
    return collected
