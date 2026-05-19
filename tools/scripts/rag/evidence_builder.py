# Timestamp: 2026-05-18 22:42:00

from __future__ import annotations

from dataclasses import asdict
from typing import Any

try:
    from .schemas import EvidenceBundle, RecommendedAction
except ImportError:  # Allow direct script execution.
    from schemas import EvidenceBundle, RecommendedAction


_DEBUG_METRIC_NAMES = {
    "retrieved_context_count",
    "evidence_document_count",
    "related_object_count",
    "related_relation_count",
    "recommended_action_count",
    "top1_retrieval_score",
    "top1_token_overlap",
}


def normalize_recommended_action(value: RecommendedAction | dict[str, Any], *, default_requires_review: bool = False) -> RecommendedAction:
    if isinstance(value, RecommendedAction):
        return value
    target = value.get("target") or value.get("target_id") or value.get("object_id") or value.get("station_id")
    action = str(value.get("action") or value.get("summary") or value.get("name") or value.get("type") or "근거 재검토")
    reason = str(value.get("reason") or value.get("rationale") or value.get("basis") or "검색된 추천 조치에 포함됨")
    requires_human_approval = bool(value.get("requires_human_approval", value.get("requires_review", default_requires_review)))
    auto_executable = bool(value.get("auto_executable", False))
    risk = value.get("risk") or value.get("risk_note")
    return RecommendedAction(
        target=str(target) if target else None,
        action=action,
        reason=reason,
        requires_human_approval=requires_human_approval,
        auto_executable=auto_executable,
        risk=str(risk) if risk else None,
    )


def recommended_action_to_dict(action: RecommendedAction | dict[str, Any]) -> dict[str, Any]:
    if isinstance(action, RecommendedAction):
        return asdict(action)
    normalized = normalize_recommended_action(action)
    return asdict(normalized)


def _context_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("content") or value.get("text") or value.get("excerpt") or "")
    return str(value or "")


def _document_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"path": str(value)}


def _debug_from_context(context: dict[str, Any]) -> dict[str, Any]:
    debug: dict[str, Any] = {}
    for item in context.get("quantitative_indicators") or []:
        if not isinstance(item, dict):
            continue
        metric = str(item.get("metric") or "")
        if metric in _DEBUG_METRIC_NAMES or metric.startswith("top1_"):
            debug[metric] = item.get("value")
    matches = context.get("retrieved_contexts") or []
    if "retrieved_context_count" not in debug:
        debug["retrieved_context_count"] = len(matches)
    if "evidence_document_count" not in debug:
        debug["evidence_document_count"] = len(context.get("evidence_documents") or [])
    if "related_object_count" not in debug:
        debug["related_object_count"] = len(context.get("related_objects") or [])
    if "related_relation_count" not in debug:
        debug["related_relation_count"] = len(context.get("related_relations") or [])
    if matches:
        first = matches[0] if isinstance(matches[0], dict) else {}
        debug.setdefault("top1_retrieval_score", first.get("score"))
        debug.setdefault("top1_token_overlap", first.get("token_overlap"))
    debug.update(context.get("debug") or {})
    return debug


def build_evidence_bundle(context: dict[str, Any]) -> EvidenceBundle:
    contexts = [_context_to_text(item) for item in context.get("retrieved_contexts") or context.get("contexts") or []]
    contexts = [item for item in contexts if item]
    default_requires_review = bool(context.get("requires_review"))
    return EvidenceBundle(
        contexts=contexts,
        evidence_documents=[_document_to_dict(item) for item in context.get("evidence_documents") or []],
        related_objects=[item for item in context.get("related_objects") or [] if isinstance(item, dict)],
        related_relations=[item for item in context.get("related_relations") or [] if isinstance(item, dict)],
        recommended_actions=[
            normalize_recommended_action(item, default_requires_review=default_requires_review)
            for item in context.get("recommended_actions") or []
            if isinstance(item, (dict, RecommendedAction))
        ],
        debug=_debug_from_context(context),
    )
