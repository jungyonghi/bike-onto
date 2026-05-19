# Timestamp: 2026-05-19 09:56:34

from __future__ import annotations

import html
import json
import math
from pathlib import Path
import re
from typing import Any

try:
    from .answer_composer import display_entity_reference, entity_display_name, master_data_display_name, relation_label
    from .evidence_builder import build_evidence_bundle
except ImportError:  # Allow direct script execution.
    from answer_composer import display_entity_reference, entity_display_name, master_data_display_name, relation_label
    from evidence_builder import build_evidence_bundle


DEBUG_METRIC_NAMES = {
    "retrieved_context_count",
    "evidence_document_count",
    "related_object_count",
    "related_relation_count",
    "recommended_action_count",
}
NODE_TYPE_ORDER = {
    "question": 0,
    "evaluation_root": 0,
    "answer_claim": 1,
    "category_cluster": 1,
    "action": 2,
    "review_gate": 2,
    "evaluation_question": 2,
    "evidence": 3,
    "entity": 3,
    "metric": 3,
    "relation": 3,
    "evaluation_issue": 3,
    "data_gap": 4,
    "debug": 4,
}
PATTERN_CLASS = {
    "question": "pattern-question",
    "evaluation_root": "pattern-question",
    "answer_claim": "pattern-solid",
    "category_cluster": "pattern-horizontal",
    "evidence": "pattern-diagonal",
    "entity": "pattern-dots",
    "metric": "pattern-vertical",
    "relation": "pattern-horizontal",
    "action": "pattern-crosshatch",
    "data_gap": "pattern-dashed",
    "review_gate": "pattern-double",
    "evaluation_question": "pattern-dots",
    "evaluation_issue": "pattern-dashed",
    "debug": "pattern-debug",
}
NODE_TYPE_LABELS = {
    "question": "Question",
    "evaluation_root": "Evaluation",
    "answer_claim": "Claim",
    "category_cluster": "Category",
    "evidence": "Evidence",
    "entity": "Entity",
    "metric": "Metric",
    "relation": "Relation",
    "action": "Action",
    "data_gap": "Data Gap",
    "review_gate": "Review Gate",
    "evaluation_question": "Eval Question",
    "evaluation_issue": "Eval Issue",
    "debug": "Debug",
}
NODE_TYPE_HELP = {
    "question": "사용자 질문",
    "evaluation_root": "평가 overview 중심",
    "answer_claim": "답변 주장/판단",
    "category_cluster": "평가 category cluster",
    "evidence": "근거 문서·발췌",
    "entity": "장소·객체",
    "metric": "정량 지표",
    "relation": "관계 label",
    "action": "추천 조치",
    "data_gap": "추가 데이터 공백",
    "review_gate": "사람 검토 필요",
    "evaluation_question": "평가 질문",
    "evaluation_issue": "평가 issue/품질 신호",
    "debug": "operator-only meta",
}
USER_RELATION_IDS = (
    "hasEvidence",
    "forStation",
    "inTimeBucket",
    "affectedByWeather",
    "requiresReview",
    "approvedBy",
    "createsTask",
    "generatesRecommendation",
    "usesDataset",
    "servesUser",
    "helpsOperation",
    "measuresAnswer",
    "faultAtStation",
)


def _short(value: Any, limit: int = 92) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _slug(value: Any) -> str:
    text = str(value or "node").strip().lower()
    text = re.sub(r"[^0-9a-z가-힣_-]+", "-", text)
    return text.strip("-") or "node"


def _metric_is_debug(metric: str) -> bool:
    return metric in DEBUG_METRIC_NAMES or metric.startswith("top") or "latency" in metric or "token_overlap" in metric


def _first_answer_section(answer: str) -> str:
    if "## 답변" in answer:
        section = answer.split("## 답변", 1)[1]
        section = section.split("## ", 1)[0]
        return _short(section, 150)
    return _short(answer, 150)


def _answer_claims(answer: str) -> list[str]:
    claims = [_first_answer_section(answer)] if answer.strip() else []
    if "## 근거 기반 판단" in answer:
        section = answer.split("## 근거 기반 판단", 1)[1]
        section = section.split("## ", 1)[0]
        for line in section.splitlines():
            stripped = line.strip().lstrip("-• ").strip()
            if stripped:
                claims.append(_short(stripped, 140))
            if len(claims) >= 4:
                break
    return [claim for index, claim in enumerate(claims) if claim and claim not in claims[:index]][:4]


def _entity_reference_ids(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for obj in payload.get("related_objects", []) or []:
        obj_id = str(obj.get("id") or "").strip()
        if obj_id:
            values.append(obj_id)
    for candidate in payload.get("candidate_set", []) or []:
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        if candidate_id:
            values.append(candidate_id)
    for action in payload.get("recommended_actions", []) or []:
        target = str(action.get("target") or action.get("station") or "").strip()
        if target:
            values.append(target)
    return [value for index, value in enumerate(values) if value and value not in values[:index]]


def _normalize_answer_entity_references(answer: str, payload: dict[str, Any]) -> str:
    evidence = build_evidence_bundle(payload)
    normalized = answer
    for reference in _entity_reference_ids(payload):
        display = display_entity_reference(reference, evidence)
        if not display or display == reference or "명칭 미확인" in display:
            continue
        normalized = re.sub(re.escape(reference), display, normalized, flags=re.I)
        station_match = re.match(r"station:0*(\d+)$", reference, flags=re.I)
        st_match = re.match(r"st-0*(\d+)$", reference, flags=re.I)
        station_number = station_match.group(1) if station_match else st_match.group(1) if st_match else ""
        if station_number:
            normalized = re.sub(rf"\b대여소\s*0*{re.escape(station_number)}\b", display, normalized)
            normalized = re.sub(rf"\bstation\s*:?\s*0*{re.escape(station_number)}\b", display, normalized, flags=re.I)
    return normalized


def _node(
    node_id: str,
    node_type: str,
    label: str,
    *,
    description: str = "",
    status: str = "confirmed",
    visible: bool = True,
    value: Any = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "label": _short(label, 120),
        "description": _short(description, 500),
        "weight": 1.0,
        "status": status,
        "value": value,
        "visibleInUserView": visible,
        "metadata": metadata or {},
    }


def _edge(
    source: str,
    target: str,
    label: str,
    *,
    relation_type: str = "supports",
    strength: float = 1.0,
    visible: bool = True,
) -> dict[str, Any]:
    return {
        "id": f"edge:{_slug(source)}:{_slug(target)}:{_slug(label)}",
        "source": source,
        "target": target,
        "label": _short(label, 48),
        "strength": strength,
        "relationType": relation_type,
        "visibleInUserView": visible,
    }


def build_visual_graph_payload(payload: dict[str, Any], *, debug_mode: bool = False) -> dict[str, Any]:
    """Convert a /rag-answer payload into a UI-ready visual graph payload."""
    evidence = build_evidence_bundle(payload)
    answer = _normalize_answer_entity_references(str(payload.get("answer") or ""), payload)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    def add_node(node: dict[str, Any]) -> str:
        if node["id"] not in node_ids:
            nodes.append(node)
            node_ids.add(node["id"])
        return node["id"]

    def add_edge(edge: dict[str, Any]) -> None:
        if edge["source"] in node_ids and edge["target"] in node_ids:
            edges.append(edge)

    question_id = add_node(_node("question:root", "question", payload.get("question") or "질문", description="사용자 질문"))
    claim_ids: list[str] = []
    for index, claim in enumerate(_answer_claims(answer) or [answer or "답변"], start=1):
        claim_id = add_node(_node(f"claim:{index}", "answer_claim", claim, description="답변 claim"))
        claim_ids.append(claim_id)
        add_edge(_edge(question_id, claim_id, "답변", relation_type="explains"))

    primary_claim = claim_ids[0] if claim_ids else question_id

    document_node_by_path: dict[str, str] = {}
    for index, excerpt in enumerate(payload.get("evidence_excerpt_list", []) or [], start=1):
        source = str(excerpt.get("source") or f"evidence:{index}")
        label = _short(_normalize_answer_entity_references(str(excerpt.get("excerpt") or source), payload), 100)
        evidence_id = add_node(
            _node(
                f"evidence:{index}",
                "evidence",
                label,
                description=source,
                metadata={"source": source, "kind": excerpt.get("kind"), "score": excerpt.get("score")},
            )
        )
        document_node_by_path[source] = evidence_id
        add_edge(_edge(evidence_id, primary_claim, "근거", relation_type="supports"))

    for index, path in enumerate(payload.get("evidence_documents", []) or [], start=1):
        source = str(path)
        if source in document_node_by_path:
            continue
        evidence_id = add_node(_node(f"evidence_document:{index}", "evidence", Path(source).name or source, description=source))
        document_node_by_path[source] = evidence_id
        add_edge(_edge(evidence_id, primary_claim, "근거", relation_type="supports"))

    entity_node_by_ref: dict[str, str] = {}
    for index, obj in enumerate(payload.get("related_objects", []) or [], start=1):
        obj_id = str(obj.get("id") or obj.get("label") or f"entity:{index}")
        label = entity_display_name(obj)
        entity_id = add_node(_node(f"entity:{_slug(obj_id)}", "entity", label, description=obj.get("type") or "entity", metadata={"id": obj_id, "type": obj.get("type")}))
        entity_node_by_ref[obj_id] = entity_id
        add_edge(_edge(primary_claim, entity_id, "관련 객체", relation_type="uses"))

    for index, relation in enumerate(payload.get("related_relations", []) or [], start=1):
        label = relation_label(relation.get("relation") or relation.get("type") or "relation")
        relation_id = add_node(_node(f"relation:{index}", "relation", label, description=f"{relation.get('source')} → {relation.get('target')}"))
        add_edge(_edge(primary_claim, relation_id, label, relation_type="explains"))
        target = str(relation.get("target") or "")
        if target in entity_node_by_ref:
            add_edge(_edge(relation_id, entity_node_by_ref[target], label, relation_type="uses"))

    for index, item in enumerate(payload.get("quantitative_indicators", []) or [], start=1):
        metric = str(item.get("metric") or "metric")
        value = item.get("value")
        is_debug = _metric_is_debug(metric)
        metric_label = f"{relation_label(metric.split(':', 1)[1])}={value}" if metric.startswith("relation_count:") else f"{metric}={value}"
        metric_id = add_node(
            _node(
                f"metric:{index}",
                "metric" if not is_debug else "debug",
                metric_label,
                description=str(item.get("source") or "quantitative indicator"),
                status="debug_only" if is_debug else "confirmed",
                visible=debug_mode if is_debug else True,
                value=value,
                metadata=item,
            )
        )
        add_edge(_edge(metric_id, primary_claim, "정량 지표", relation_type="supports", visible=debug_mode if is_debug else True))

    for index, action in enumerate(payload.get("recommended_actions", []) or [], start=1):
        target = action.get("target") or action.get("station") or ""
        target_text = display_entity_reference(target, evidence) if target else "현재 근거에서 특정 대상 미확정"
        action_text = action.get("action") or action.get("summary") or action.get("type") or "권장 조치"
        label = f"{action_text} · {target_text}"
        action_id = add_node(_node(f"action:{index}", "action", label, description=action.get("reason") or "추천 조치", status="review_required"))
        add_edge(_edge(primary_claim, action_id, "권장 조치", relation_type="requires_review"))

    for index, gap in enumerate(payload.get("data_gaps", []) or [], start=1):
        gap_text = _normalize_answer_entity_references(str(gap), payload)
        gap_id = add_node(_node(f"gap:{index}", "data_gap", gap_text, description="추가 확인 필요", status="gap"))
        add_edge(_edge(primary_claim, gap_id, "부족한 근거", relation_type="missing"))

    if payload.get("requires_review"):
        review_id = add_node(_node("review:gate", "review_gate", "검토 필요", description=payload.get("review_reason") or "사람 검토·승인 필요", status="review_required"))
        add_edge(_edge(primary_claim, review_id, "승인 필요", relation_type="requires_review"))

    debug_values = [
        f"llm_mode={payload.get('llm', {}).get('mode')}",
        f"model={payload.get('llm', {}).get('model')}",
        f"contract_pass={payload.get('contract_pass')}",
        f"retrieval_latency_ms={payload.get('retrieval', {}).get('latency_ms')}",
    ]
    for note in payload.get("quality_guard_notes", []) or []:
        debug_values.append(f"quality_guard={note}")
    for item in payload.get("quantitative_indicators", []) or []:
        metric = str(item.get("metric") or "")
        if _metric_is_debug(metric):
            debug_values.append(f"{metric}={item.get('value')}")
    for index, value in enumerate([value for value in debug_values if value and "=None" not in value], start=1):
        debug_id = add_node(_node(f"debug:{index}", "debug", value, description="Operator Debug", status="debug_only", visible=debug_mode))
        add_edge(_edge(debug_id, primary_claim, "debug", relation_type="debug", visible=debug_mode))

    return {
        "kind": "single_answer",
        "title": "Answer Evidence Radial Graph",
        "question": str(payload.get("question") or ""),
        "answer": answer,
        "profile": str(payload.get("category") or payload.get("profile") or "GENERAL"),
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "contractPass": bool(payload.get("contract_pass")),
            "requiresReview": bool(payload.get("requires_review")),
            "llmMode": str(payload.get("llm", {}).get("mode") or "unknown"),
            "qualityGuardNotes": payload.get("quality_guard_notes") or [],
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
        },
    }


def _count_by(rows: list[dict[str, Any]], key: str, *, default: str = "미분류") -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or default)
        counts[value] = counts.get(value, 0) + 1
    return counts


def _row_contract_pass(row: dict[str, Any]) -> bool:
    return bool(row.get("contract_pass")) and str(row.get("status") or "ok").lower() not in {"error", "failed", "fail"}


def _row_question_id(row: dict[str, Any], index: int) -> str:
    return str(row.get("id") or row.get("question_id") or f"Q-{index:03d}")


def build_evaluation_overview_payload(rows: list[dict[str, Any]], *, debug_mode: bool = False, max_questions: int = 120) -> dict[str, Any]:
    """Build a category-cluster overview graph from 100-QA RAG evaluation rows."""
    rows = [dict(row) for row in rows]
    question_count = len(rows)
    contract_pass_count = sum(1 for row in rows if _row_contract_pass(row))
    failure_count = question_count - contract_pass_count
    review_count = sum(1 for row in rows if row.get("requires_review"))
    data_gap_total = sum(int(row.get("data_gap_count") or 0) for row in rows)
    quality_guard_count = sum(len(row.get("quality_guard_notes") or []) for row in rows)
    category_counts = _count_by(rows, "category")
    llm_mode_counts = _count_by(rows, "llm_mode", default="unknown")
    status_counts = _count_by(rows, "status", default="ok")
    elapsed_values = [float(row.get("elapsed_ms") or row.get("llm_latency_ms") or 0) for row in rows if row.get("elapsed_ms") is not None or row.get("llm_latency_ms") is not None]
    avg_elapsed_ms = round(sum(elapsed_values) / len(elapsed_values), 3) if elapsed_values else 0.0

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    def add_node(node: dict[str, Any]) -> str:
        if node["id"] not in node_ids:
            nodes.append(node)
            node_ids.add(node["id"])
        return node["id"]

    def add_edge(edge: dict[str, Any]) -> None:
        if edge["source"] in node_ids and edge["target"] in node_ids:
            edges.append(edge)

    root_id = add_node(
        _node(
            "evaluation:root",
            "evaluation_root",
            "Evaluation Overview",
            description=f"{question_count}개 RAG QA 평가 결과 category/profile별 overview",
            metadata={"question_count": question_count, "avg_elapsed_ms": avg_elapsed_ms},
        )
    )

    category_node_ids: dict[str, str] = {}
    for category, count in category_counts.items():
        category_rows = [row for row in rows if str(row.get("category") or "미분류") == category]
        category_pass = sum(1 for row in category_rows if _row_contract_pass(row))
        category_review = sum(1 for row in category_rows if row.get("requires_review"))
        category_gap = sum(int(row.get("data_gap_count") or 0) for row in category_rows)
        status = "confirmed" if category_pass == count else "gap"
        category_id = add_node(
            _node(
                f"category:{_slug(category)}",
                "category_cluster",
                f"{category} ({count})",
                description=f"contract_pass={category_pass}/{count}, review={category_review}, data_gap={category_gap}",
                status=status,
                metadata={"category": category, "count": count, "contract_pass": category_pass, "requires_review": category_review, "data_gap_count": category_gap},
            )
        )
        category_node_ids[category] = category_id
        add_edge(_edge(root_id, category_id, "category", relation_type="explains"))

    for index, row in enumerate(rows[:max_questions], start=1):
        question_id = _row_question_id(row, index)
        category = str(row.get("category") or "미분류")
        passed = _row_contract_pass(row)
        status = "confirmed" if passed else "gap"
        label = f"{question_id} · {_short(row.get('question') or row.get('answer') or '질문', 72)}"
        eval_question_id = add_node(
            _node(
                f"eval_question:{_slug(question_id)}",
                "evaluation_question",
                label,
                description=f"category={category}, status={row.get('status') or 'ok'}, contract_pass={bool(row.get('contract_pass'))}, llm_mode={row.get('llm_mode') or 'unknown'}",
                status=status,
                metadata={"id": question_id, "category": category, "llm_mode": row.get("llm_mode"), "data_gap_count": row.get("data_gap_count"), "quality_guard_notes": row.get("quality_guard_notes") or []},
            )
        )
        if category in category_node_ids:
            add_edge(_edge(category_node_ids[category], eval_question_id, "문항", relation_type="uses"))
        if not passed:
            issue_id = add_node(
                _node(
                    f"issue:{_slug(question_id)}:contract",
                    "evaluation_issue",
                    f"{question_id} contract_check",
                    description="contract_pass 실패 또는 status error",
                    status="gap",
                )
            )
            add_edge(_edge(eval_question_id, issue_id, "계약 확인", relation_type="missing"))
        if row.get("requires_review"):
            review_id = add_node(_node(f"issue:{_slug(question_id)}:review", "review_gate", f"{question_id} review", description="사람 검토 필요", status="review_required"))
            add_edge(_edge(eval_question_id, review_id, "검토 필요", relation_type="requires_review"))
        if row.get("quality_guard_notes"):
            guard_id = add_node(_node(f"issue:{_slug(question_id)}:guard", "evaluation_issue", f"{question_id} quality_guard", description=", ".join(map(str, row.get("quality_guard_notes") or [])), status="review_required"))
            add_edge(_edge(eval_question_id, guard_id, "quality guard", relation_type="requires_review"))

    overview_issue_labels = [
        f"contract_pass={contract_pass_count}/{question_count} · contract_fail={failure_count}",
        " · ".join(f"{mode}={count}" for mode, count in llm_mode_counts.items()),
        f"requires_review={review_count}",
        f"data_gap_total={data_gap_total}",
        f"quality_guard={quality_guard_count}",
        f"avg_elapsed_ms={avg_elapsed_ms}",
    ]
    for index, label in enumerate([label for label in overview_issue_labels if label], start=1):
        node_type = "evaluation_issue" if any(token in label for token in ("fail", "quality_guard", "fallback")) else "metric"
        status = "gap" if "fail" in label and not label.endswith("=0") else "confirmed"
        issue_id = add_node(_node(f"overview_metric:{index}", node_type, label, description="Evaluation overview metric", status=status, visible=debug_mode if "avg_elapsed" in label else True))
        add_edge(_edge(root_id, issue_id, "overview metric", relation_type="explains", visible=debug_mode if "avg_elapsed" in label else True))

    answer_summary = "\n".join(
        [
            "## Evaluation Overview",
            f"- question_count={question_count}",
            f"- contract_pass={contract_pass_count}/{question_count}",
            f"- failure_count={failure_count}",
            f"- requires_review={review_count}",
            f"- data_gap_total={data_gap_total}",
            f"- quality_guard={quality_guard_count}",
            "- category_counts=" + ", ".join(f"{category}:{count}" for category, count in category_counts.items()),
            "- llm_mode_counts=" + ", ".join(f"{mode}:{count}" for mode, count in llm_mode_counts.items()),
        ]
    )

    return {
        "kind": "evaluation_overview",
        "title": "RAG Evaluation Overview",
        "question": "Evaluation Overview",
        "answer": answer_summary,
        "profile": "Evaluation Overview",
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "contractPass": failure_count == 0,
            "requiresReview": review_count > 0 or quality_guard_count > 0 or failure_count > 0,
            "llmMode": "mixed" if len(llm_mode_counts) > 1 else next(iter(llm_mode_counts), "unknown"),
            "questionCount": question_count,
            "contractPassCount": contract_pass_count,
            "failureCount": failure_count,
            "reviewCount": review_count,
            "dataGapTotal": data_gap_total,
            "qualityGuardCount": quality_guard_count,
            "categoryCounts": category_counts,
            "llmModeCounts": llm_mode_counts,
            "statusCounts": status_counts,
            "avgElapsedMs": avg_elapsed_ms,
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
        },
    }


def _visible_items(items: list[dict[str, Any]], *, debug_mode: bool) -> list[dict[str, Any]]:
    return [item for item in items if debug_mode or item.get("visibleInUserView", True)]


def _reference_display_map(nodes: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for node in nodes:
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        raw_id = str(metadata.get("id") or "").strip()
        label = str(node.get("label") or "").strip()
        if raw_id and label and "명칭 미확인" not in label:
            mapping[raw_id] = label
    return mapping


def _sanitize_user_text(value: Any, reference_map: dict[str, str]) -> str:
    text = str(value or "")
    for raw, display in sorted(reference_map.items(), key=lambda item: len(item[0]), reverse=True):
        if raw and display and display != raw:
            text = re.sub(re.escape(raw), display, text, flags=re.I)
            station_match = re.match(r"station:0*(\d+)$", raw, flags=re.I)
            st_match = re.match(r"st-0*(\d+)$", raw, flags=re.I)
            station_number = station_match.group(1) if station_match else st_match.group(1) if st_match else ""
            if station_number:
                text = re.sub(rf"\b대여소\s*0*{re.escape(station_number)}\b", display, text)
                text = re.sub(rf"\bstation\s*:?\s*0*{re.escape(station_number)}\b", display, text, flags=re.I)
    def replace_master_reference(match: re.Match[str]) -> str:
        reference = match.group(0)
        return master_data_display_name(reference) or reference

    text = re.sub(r"\b(?:station|st)[-:]0*\d+\b", replace_master_reference, text, flags=re.I)
    for relation_id in USER_RELATION_IDS:
        text = re.sub(re.escape(relation_id), relation_label(relation_id), text, flags=re.I)
    return text


def _sanitize_render_nodes(nodes: list[dict[str, Any]], *, debug_mode: bool) -> list[dict[str, Any]]:
    if debug_mode:
        return nodes
    reference_map = _reference_display_map(nodes)
    sanitized: list[dict[str, Any]] = []
    for node in nodes:
        copied = dict(node)
        copied["label"] = _sanitize_user_text(copied.get("label"), reference_map)
        copied["description"] = _sanitize_user_text(copied.get("description"), reference_map)
        copied["metadata"] = {}
        sanitized.append(copied)
    return sanitized


def _sanitize_render_edges(edges: list[dict[str, Any]], nodes: list[dict[str, Any]], *, debug_mode: bool) -> list[dict[str, Any]]:
    if debug_mode:
        return edges
    reference_map = _reference_display_map(nodes)
    sanitized: list[dict[str, Any]] = []
    for edge in edges:
        copied = dict(edge)
        copied["label"] = _sanitize_user_text(copied.get("label"), reference_map)
        sanitized.append(copied)
    return sanitized


def _bounded(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _question_key_from_issue(node_id: str) -> str:
    match = re.match(r"issue:([^:]+):", node_id)
    return match.group(1) if match else ""


def _layout_evaluation_nodes(nodes: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    width, height = 920, 680
    margin_x, margin_y = 54, 44
    positions: dict[str, tuple[float, float]] = {}
    categories = sorted([node for node in nodes if node.get("type") == "category_cluster"], key=lambda node: str(node.get("id") or ""))
    questions = sorted([node for node in nodes if node.get("type") == "evaluation_question"], key=lambda node: str(node.get("id") or ""))
    issue_nodes = sorted([node for node in nodes if node.get("type") in {"evaluation_issue", "review_gate"}], key=lambda node: str(node.get("id") or ""))
    metrics = sorted([node for node in nodes if node.get("id", "").startswith("overview_metric:") or node.get("type") == "metric"], key=lambda node: str(node.get("id") or ""))
    roots = [node for node in nodes if node.get("type") == "evaluation_root"]

    if roots:
        positions[roots[0]["id"]] = (width / 2, margin_y + 12)
        for index, node in enumerate(roots[1:], start=1):
            positions[node["id"]] = (width / 2 + index * 36, margin_y + 12)

    category_x: dict[str, float] = {}
    if categories:
        step = (width - margin_x * 2) / max(1, len(categories) - 1)
        for index, node in enumerate(categories):
            x = margin_x if len(categories) == 1 else margin_x + step * index
            y = 126
            positions[node["id"]] = (x, y)
            category_x[str(node.get("id"))] = x

    questions_by_category: dict[str, list[dict[str, Any]]] = {}
    for node in questions:
        category = str((node.get("metadata") or {}).get("category") or "미분류")
        questions_by_category.setdefault(category, []).append(node)

    category_by_slug = {str((node.get("metadata") or {}).get("category") or "미분류"): node for node in categories}
    question_positions_by_slug: dict[str, tuple[float, float]] = {}
    for category, group in questions_by_category.items():
        category_node = category_by_slug.get(category)
        if category_node and category_node.get("id") in positions:
            x = positions[category_node["id"]][0]
            col_index = categories.index(category_node)
        else:
            col_index = len(question_positions_by_slug) % max(1, len(categories) or 1)
            x = margin_x + ((width - margin_x * 2) / max(1, (len(categories) or 1) - 1)) * col_index if len(categories) > 1 else width / 2
        for row_index, node in enumerate(group):
            y = 192 + row_index * 42
            if y > height - 82:
                x_offset = 16 if row_index % 2 else -16
                y = 192 + (row_index % 10) * 42
            else:
                x_offset = 0
            pos = (_bounded(x + x_offset, 28, width - 28), _bounded(y, 28, height - 60))
            positions[node["id"]] = pos
            question_positions_by_slug[str(node.get("id", "")).replace("eval_question:", "")] = pos

    issue_offsets = {
        "contract": (-18, -15),
        "review": (18, -15),
        "guard": (0, 18),
    }
    issue_fallback_index = 0
    for node in issue_nodes:
        node_id = str(node.get("id") or "")
        key = _question_key_from_issue(node_id)
        parent_pos = question_positions_by_slug.get(key)
        if parent_pos:
            suffix = node_id.rsplit(":", 1)[-1]
            dx, dy = issue_offsets.get(suffix, (18, 18))
            positions[node_id] = (_bounded(parent_pos[0] + dx, 18, width - 18), _bounded(parent_pos[1] + dy, 18, height - 18))
        else:
            positions[node_id] = (width - 126 + (issue_fallback_index % 3) * 34, height - 120 + (issue_fallback_index // 3) * 28)
            issue_fallback_index += 1

    for index, node in enumerate(metrics):
        x = width - 168 + (index % 2) * 92
        y = 82 + (index // 2) * 36
        positions[node["id"]] = (_bounded(x, 22, width - 22), _bounded(y, 22, height - 22))

    unplaced = [node for node in nodes if node.get("id") not in positions]
    for index, node in enumerate(unplaced):
        angle = -math.pi / 2 + 2 * math.pi * index / max(1, len(unplaced))
        radius = 286
        positions[node["id"]] = (width / 2 + math.cos(angle) * radius, height / 2 + math.sin(angle) * radius)

    return {node_id: (_bounded(x, 18, width - 18), _bounded(y, 18, height - 18)) for node_id, (x, y) in positions.items()}


def _layout_nodes(nodes: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    if any(node.get("type") in {"evaluation_root", "category_cluster", "evaluation_question"} for node in nodes):
        return _layout_evaluation_nodes(nodes)
    width, height = 920, 680
    cx, cy = width / 2, height / 2
    by_ring: dict[int, list[dict[str, Any]]] = {}
    for node in nodes:
        ring = NODE_TYPE_ORDER.get(node.get("type"), 3)
        by_ring.setdefault(ring, []).append(node)
    radii = {0: 0, 1: 118, 2: 218, 3: 292, 4: 314}
    angle_offsets = {1: -math.pi / 2, 2: -math.pi / 2 + math.pi / 8, 3: -math.pi / 2 + math.pi / 14, 4: -math.pi / 2 + math.pi / 5}
    positions: dict[str, tuple[float, float]] = {}
    for ring in sorted(by_ring):
        ring_nodes = sorted(by_ring[ring], key=lambda node: (NODE_TYPE_ORDER.get(node.get("type"), 3), str(node.get("type") or ""), str(node.get("id") or "")))
        if ring == 0 and ring_nodes:
            positions[ring_nodes[0]["id"]] = (cx, cy)
            for extra_index, node in enumerate(ring_nodes[1:], start=1):
                positions[node["id"]] = (_bounded(cx + extra_index * 38, 24, width - 24), cy)
            continue
        count = len(ring_nodes)
        radius = radii.get(ring, 292)
        if count > 24:
            radius = max(118, radius - 18)
        step = 2 * math.pi / max(1, count)
        for index, node in enumerate(ring_nodes):
            angle = angle_offsets.get(ring, -math.pi / 2) + (step * index)
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius
            positions[node["id"]] = (_bounded(x, 24, width - 24), _bounded(y, 24, height - 24))
    return positions


def _node_radius(node_type: str) -> int:
    if node_type in {"question", "answer_claim", "evaluation_root"}:
        return 21
    if node_type in {"review_gate", "category_cluster"}:
        return 18
    if node_type == "evaluation_question":
        return 13
    return 15


def _edge_path(source: tuple[float, float], target: tuple[float, float]) -> str:
    sx, sy = source
    tx, ty = target
    dx, dy = tx - sx, ty - sy
    length = math.hypot(dx, dy) or 1.0
    curve = min(92.0, max(26.0, length * 0.16))
    normal_x, normal_y = -dy / length, dx / length
    control_x = (sx + tx) / 2 + normal_x * curve
    control_y = (sy + ty) / 2 + normal_y * curve
    return f"M {sx:.1f} {sy:.1f} Q {control_x:.1f} {control_y:.1f} {tx:.1f} {ty:.1f}"


def _label_position(x: float, y: float, radius: int, *, width: int = 920, height: int = 680) -> tuple[float, float, str]:
    cx, cy = width / 2, height / 2
    dx, dy = x - cx, y - cy
    if abs(dx) > abs(dy):
        direction = 1 if dx >= 0 else -1
        return x + direction * (radius + 9), y + 4, "start" if direction > 0 else "end"
    vertical = -1 if dy < 0 else 1
    return x, y + vertical * (radius + 17), "middle"


def _legend_cards(*, debug_mode: bool) -> str:
    visible_types = [node_type for node_type in NODE_TYPE_LABELS if debug_mode or node_type != "debug"]
    return "\n".join(
        f'<div class="legend-item"><span class="swatch {PATTERN_CLASS.get(node_type, "pattern-debug")}"></span>'
        f'<span><strong>{html.escape(NODE_TYPE_LABELS[node_type])}</strong><small>{html.escape(NODE_TYPE_HELP[node_type])}</small></span></div>'
        for node_type in visible_types
    )


def _claim_jump_cards(nodes: list[dict[str, Any]]) -> str:
    claim_nodes = [node for node in nodes if node.get("type") == "answer_claim"]
    if not claim_nodes:
        return '<p class="meta">claim node가 없습니다.</p>'
    return "\n".join(
        f'<button type="button" class="claim-jump" data-claim-id="{html.escape(str(node["id"]))}" onclick="selectNode(\'{html.escape(str(node["id"]))}\')">'
        f'{html.escape(_short(node.get("label"), 86))}</button>'
        for node in claim_nodes
    )


def render_visual_inspector_html(graph: dict[str, Any], *, debug_mode: bool = False) -> str:
    raw_nodes = _visible_items(graph.get("nodes", []), debug_mode=debug_mode)
    raw_edges = _visible_items(graph.get("edges", []), debug_mode=debug_mode)
    nodes = _sanitize_render_nodes(raw_nodes, debug_mode=debug_mode)
    node_ids = {node["id"] for node in nodes}
    edges = _sanitize_render_edges([edge for edge in raw_edges if edge.get("source") in node_ids and edge.get("target") in node_ids], raw_nodes, debug_mode=debug_mode)
    render_answer = _sanitize_user_text(graph.get("answer") or "", _reference_display_map(raw_nodes)) if not debug_mode else str(graph.get("answer") or "")
    positions = _layout_nodes(nodes)
    width, height = 920, 680

    edge_svg: list[str] = []
    for edge in edges:
        source = positions.get(edge["source"])
        target = positions.get(edge["target"])
        if not source or not target:
            continue
        relation_type = html.escape(str(edge.get("relationType") or "supports"))
        edge_label = html.escape(str(edge.get("label") or ""))
        edge_svg.append(
            f'<path class="edge edge-{relation_type}" data-source="{html.escape(str(edge["source"]))}" data-target="{html.escape(str(edge["target"]))}" '
            f'data-edge-label="{edge_label}" d="{_edge_path(source, target)}"><title>{edge_label}</title></path>'
        )

    node_svg: list[str] = []
    for node in nodes:
        x, y = positions[node["id"]]
        node_type = str(node.get("type") or "debug")
        css_class = PATTERN_CLASS.get(node_type, "pattern-debug")
        radius = _node_radius(node_type)
        label = html.escape(str(node.get("label") or ""))
        svg_label = html.escape(_short(node.get("label"), 34))
        label_x, label_y, anchor = _label_position(x, y, radius, width=width, height=height)
        node_svg.append(
            f'<g class="node node-{html.escape(node_type)}" data-node-id="{html.escape(str(node["id"]))}" data-node-type="{html.escape(node_type)}" onclick="selectNode(\'{html.escape(str(node["id"]))}\')">'
            f'<circle class="node-circle {css_class}" cx="{x:.1f}" cy="{y:.1f}" r="{radius}" />'
            f'<text class="node-label" x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}">{svg_label}</text>'
            f'<title>{label}</title></g>'
        )

    node_cards = "\n".join(
        f'<li><button type="button" class="node-list-button" onclick="selectNode(\'{html.escape(str(node["id"]))}\')"><span class="swatch {PATTERN_CLASS.get(str(node.get("type")), "pattern-debug")}"></span>{html.escape(str(node.get("label") or ""))}</button></li>'
        for node in nodes[:80]
    )
    legend_cards = _legend_cards(debug_mode=debug_mode)
    claim_cards = _claim_jump_cards(nodes)
    category_cards = "\n".join(
        f'<li><button type="button" class="node-list-button" onclick="selectNode(\'{html.escape(str(node["id"]))}\')"><span class="swatch {PATTERN_CLASS.get(str(node.get("type")), "pattern-debug")}"></span>{html.escape(str(node.get("label") or ""))}<br><span class="meta">{html.escape(str(node.get("description") or ""))}</span></button></li>'
        for node in nodes
        if node.get("type") == "category_cluster"
    )
    category_section = f'<h2>Category Clusters</h2><ul>{category_cards}</ul>' if category_cards else ""
    summary = graph.get("summary", {}) if isinstance(graph.get("summary"), dict) else {}
    title = str(graph.get("title") or "Answer Evidence Radial Graph")
    status_badge = "PASS" if summary.get("contractPass") else "CHECK"
    review_badge = "Review" if summary.get("requiresReview") else "No Review"
    debug_badge = "Operator Debug ON" if debug_mode else "User View"
    graph_json = html.escape(json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False), quote=False)

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<style>
:root {{ --ink:#111; --muted:#777; --line:#c7c7c7; --paper:#fff; --panel:rgba(255,255,255,.92); --canvas:#fff; --faded:.10; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family: Inter, 'Noto Sans KR', system-ui, sans-serif; background:#f7f7f5; color:var(--ink); }}
.top-toolbar {{ min-height:64px; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:10px 18px; border-bottom:1px solid #ddd; background:rgba(255,255,255,.94); position:sticky; top:0; z-index:5; backdrop-filter:blur(10px); }}
.toolbar-left {{ display:flex; align-items:center; gap:10px; min-width:260px; }}
.toolbar-actions {{ display:flex; flex-wrap:wrap; align-items:center; justify-content:flex-end; gap:8px; }}
.toolbar-chip, .toolbar-button, .label-size-control {{ border:1px solid #111; border-radius:999px; background:#fff; color:#111; padding:6px 10px; font-size:12px; line-height:1; }}
.toolbar-button {{ cursor:pointer; font:inherit; font-size:12px; }}
.label-size-control {{ display:flex; align-items:center; gap:6px; }}
.label-size-control input {{ width:90px; accent-color:#111; }}
main {{ display:grid; grid-template-columns: 320px minmax(680px, 1fr) 360px; gap:14px; padding:14px; }}
.panel {{ background:var(--panel); border:1px solid #ddd; border-radius:14px; padding:16px; box-shadow:0 1px 2px rgba(0,0,0,.03); }}
.graph-panel {{ min-height:720px; overflow:auto; }}
h1 {{ font-size:16px; margin:0; white-space:nowrap; }}
h2 {{ font-size:13px; margin:0 0 12px; text-transform:uppercase; letter-spacing:.08em; color:#666; }}
h2:not(:first-child) {{ margin-top:18px; }}
.badge {{ display:inline-block; padding:4px 8px; border:1px solid #111; border-radius:999px; font-size:12px; margin-left:8px; }}
.answer {{ white-space:pre-wrap; max-height:280px; overflow:auto; border:1px solid #e2e2e2; border-radius:10px; padding:12px; background:#fff; font-size:13px; line-height:1.55; }}
.claim-jumps {{ display:grid; gap:7px; margin-bottom:10px; }}
.claim-jump {{ width:100%; text-align:left; border:1px solid #d8d8d8; border-radius:10px; background:#fff; padding:8px 10px; cursor:pointer; font:inherit; font-size:12px; line-height:1.4; }}
.claim-jump.active {{ border-color:#111; box-shadow:0 0 0 2px rgba(17,17,17,.08); }}
svg {{ width:920px; height:680px; background:#fff; border:1px solid #e1e1e1; border-radius:16px; }}
.edge {{ fill:none; stroke:#b6b6b6; stroke-width:1.25; opacity:.72; transition:opacity .16s ease, stroke-width .16s ease; }}
.edge-requires_review {{ stroke:#111; stroke-width:1.9; stroke-dasharray:5 4; }}
.edge-missing {{ stroke:#888; stroke-dasharray:2 5; }}
.edge-debug {{ stroke:#aaa; stroke-dasharray:2 3; opacity:.35; }}
.edge.active {{ opacity:1; stroke-width:2.6; }}
.node {{ cursor:pointer; transition:opacity .16s ease; }}
.node-label {{ font-size:10px; fill:#111; pointer-events:none; paint-order:stroke; stroke:#fff; stroke-width:4px; stroke-linejoin:round; }}
.node-circle {{ stroke:#111; stroke-width:1.2; fill:#fff; transition:stroke-width .16s ease; }}
.node.selected .node-circle {{ stroke-width:3; }}
.node.faded, .edge.faded {{ opacity:var(--faded); }}
.node.connected .node-circle {{ stroke-width:2.4; }}
.pattern-solid {{ fill:#111; }}
.pattern-question {{ fill:#fff; stroke-width:2.6; }}
.pattern-diagonal {{ fill:url(#diagonal); }}
.pattern-dots {{ fill:url(#dots); }}
.pattern-vertical {{ fill:url(#vertical); }}
.pattern-horizontal {{ fill:url(#horizontal); }}
.pattern-crosshatch {{ fill:url(#crosshatch); }}
.pattern-dashed {{ fill:#fff; stroke-dasharray:4 4; }}
.pattern-double {{ fill:#fff; stroke-width:2.4; }}
.pattern-debug {{ fill:#eee; stroke:#aaa; }}
.swatch {{ width:13px; height:13px; min-width:13px; border-radius:50%; border:1px solid #111; display:inline-block; margin-right:8px; vertical-align:-2px; background:#fff; }}
ul {{ list-style:none; padding:0; margin:0; }}
.node-list-button {{ width:100%; text-align:left; border:0; border-bottom:1px solid #eee; background:transparent; padding:8px 2px; cursor:pointer; font:inherit; font-size:12px; line-height:1.35; }}
.legend-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px 10px; }}
.legend-item {{ display:flex; align-items:flex-start; gap:2px; font-size:12px; }}
.legend-item small {{ display:block; margin-top:2px; color:#777; font-size:10px; line-height:1.25; }}
.meta {{ color:#555; font-size:12px; line-height:1.55; }}
#inspector-title {{ font-size:17px; margin-bottom:8px; font-weight:700; }}
#inspector-body {{ white-space:pre-wrap; font-size:13px; line-height:1.55; }}
.connected-node-list {{ display:grid; gap:6px; margin-top:8px; }}
.connected-node-list li {{ border:1px solid #eee; border-radius:9px; padding:7px 9px; background:#fff; font-size:12px; }}
@media (max-width: 1100px) {{ main {{ grid-template-columns:1fr; }} .top-toolbar {{ align-items:flex-start; flex-direction:column; }} }}
</style>
</head>
<body>
<header class="top-toolbar">
  <div class="toolbar-left">
    <h1>{html.escape(title)} <span class="badge">{html.escape(status_badge)}</span><span class="badge">{html.escape(debug_badge)}</span></h1>
  </div>
  <div class="toolbar-actions" aria-label="Visual inspector toolbar">
    <span class="toolbar-chip">View: {html.escape(debug_badge)}</span>
    <span class="toolbar-chip">Profile: {html.escape(str(graph.get('profile') or 'GENERAL'))}</span>
    <span class="toolbar-chip">Nodes {len(nodes)} / Edges {len(edges)}</span>
    <span class="toolbar-chip">LLM {html.escape(str(summary.get('llmMode', 'unknown')))}</span>
    <span class="toolbar-chip">{html.escape(review_badge)}</span>
    <label class="label-size-control" for="label-size">Label <input id="label-size" type="range" min="8" max="18" value="10" oninput="setLabelSize(this.value)" /></label>
    <button type="button" class="toolbar-button" onclick="resetFocus()">Reset Focus</button>
    <button type="button" class="toolbar-button" onclick="downloadGraphJson()">Export JSON</button>
  </div>
</header>
<main>
  <aside class="panel">
    <h2>Query Panel</h2>
    <p><strong>Question</strong><br>{html.escape(str(graph.get('question') or ''))}</p>
    <p class="meta">contractPass={html.escape(str(summary.get('contractPass')))}<br>requiresReview={html.escape(str(summary.get('requiresReview')))}<br>profile={html.escape(str(graph.get('profile') or 'GENERAL'))}</p>
    <h2>Node Type Legend</h2>
    <div class="legend-grid">{legend_cards}</div>
    {category_section}
    <h2>Nodes</h2>
    <ul>{node_cards}</ul>
  </aside>
  <section class="panel graph-panel">
    <svg viewBox="0 0 {width} {height}" role="img" aria-label="RAG answer evidence graph">
      <defs>
        <pattern id="diagonal" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M-2,8 L8,-2 M0,10 L10,0" stroke="#111" stroke-width="1.2"/></pattern>
        <pattern id="dots" width="8" height="8" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.2" fill="#111"/><circle cx="6" cy="6" r="1.2" fill="#111"/></pattern>
        <pattern id="vertical" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M2,0 V8 M6,0 V8" stroke="#111" stroke-width="1.2"/></pattern>
        <pattern id="horizontal" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M0,2 H8 M0,6 H8" stroke="#111" stroke-width="1.2"/></pattern>
        <pattern id="crosshatch" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M0,0 L8,8 M8,0 L0,8" stroke="#111" stroke-width=".9"/></pattern>
      </defs>
      {''.join(edge_svg)}
      {''.join(node_svg)}
    </svg>
    <h2 style="margin-top:14px">Answer Claims</h2>
    <div class="claim-jumps">{claim_cards}</div>
    <h2>Answer Preview</h2>
    <div class="answer">{html.escape(render_answer)}</div>
  </section>
  <aside class="panel">
    <h2>Inspector</h2>
    <div id="inspector-title">노드를 선택하세요</div>
    <div id="inspector-body" class="meta">Claim, evidence, entity, metric, action, data gap, review gate를 클릭하면 연결 정보가 표시됩니다.</div>
    <h2>Connected Nodes</h2>
    <ul id="connected-node-list" class="connected-node-list"><li class="meta">선택된 노드가 없습니다.</li></ul>
    {'<h2 style="margin-top:18px">Operator Debug</h2><p class="meta">Debug nodes and retrieval/LLM metadata are visible.</p>' if debug_mode else ''}
  </aside>
</main>
<script id="graph-data" type="application/json">{graph_json}</script>
<script>
const graph = JSON.parse(document.getElementById('graph-data').textContent);
function escapeHtml(value) {{
  return String(value || '').replace(/[&<>'"]/g, char => ({{ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }}[char]));
}}
function nodeLabel(id) {{
  const node = graph.nodes.find(n => n.id === id);
  return node ? node.label : id;
}}
function connectedEdges(id) {{
  return graph.edges.filter(e => e.source === id || e.target === id);
}}
function connectedIds(id) {{
  const ids = new Set([id]);
  for (const e of connectedEdges(id)) {{
    if (e.source === id) ids.add(e.target);
    if (e.target === id) ids.add(e.source);
  }}
  return ids;
}}
function resetFocus() {{
  document.querySelectorAll('.node').forEach(n => n.classList.remove('selected', 'connected', 'faded'));
  document.querySelectorAll('.edge').forEach(e => e.classList.remove('active', 'faded'));
  document.querySelectorAll('.claim-jump').forEach(b => b.classList.remove('active'));
  document.getElementById('inspector-title').textContent = '노드를 선택하세요';
  document.getElementById('inspector-body').textContent = 'Claim, evidence, entity, metric, action, data gap, review gate를 클릭하면 연결 정보가 표시됩니다.';
  document.getElementById('connected-node-list').innerHTML = '<li class="meta">선택된 노드가 없습니다.</li>';
}}
function selectNode(id) {{
  const ids = connectedIds(id);
  document.querySelectorAll('.node').forEach(n => {{
    const nid = n.dataset.nodeId;
    n.classList.toggle('selected', nid === id);
    n.classList.toggle('connected', ids.has(nid) && nid !== id);
    n.classList.toggle('faded', !ids.has(nid));
  }});
  document.querySelectorAll('.edge').forEach(e => {{
    const active = e.dataset.source === id || e.dataset.target === id;
    e.classList.toggle('active', active);
    e.classList.toggle('faded', !active);
  }});
  document.querySelectorAll('.claim-jump').forEach(b => b.classList.toggle('active', b.dataset.claimId === id));
  const node = graph.nodes.find(n => n.id === id);
  if (!node) return;
  const outgoing = connectedEdges(id);
  document.getElementById('inspector-title').textContent = node.label;
  document.getElementById('inspector-body').textContent = `type=${{node.type}}\nstatus=${{node.status}}\n\n${{node.description || ''}}`;
  const list = outgoing.map(e => {{
    const other = e.source === id ? e.target : e.source;
    return `<li><strong>${{escapeHtml(e.label)}}</strong><br>${{escapeHtml(nodeLabel(other))}}</li>`;
  }}).join('') || '<li class="meta">연결 노드가 없습니다.</li>';
  document.getElementById('connected-node-list').innerHTML = list;
}}
function setLabelSize(value) {{
  document.querySelectorAll('.node-label').forEach(label => label.style.fontSize = `${{value}}px`);
}}
function downloadGraphJson() {{
  const blob = new Blob([JSON.stringify(graph, null, 2)], {{ type: 'application/json' }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'answer_evidence_graph.json';
  a.click();
  URL.revokeObjectURL(url);
}}
document.addEventListener('keydown', event => {{
  if (event.key === 'Escape') resetFocus();
}});
</script>
</body>
</html>
"""

def write_visual_inspector_html(graph: dict[str, Any], output_path: Path | str, *, debug_mode: bool = False) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_visual_inspector_html(graph, debug_mode=debug_mode), encoding="utf-8")
    return path


__all__ = ["build_evaluation_overview_payload", "build_visual_graph_payload", "render_visual_inspector_html", "write_visual_inspector_html"]
