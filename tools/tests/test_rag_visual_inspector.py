# Timestamp: 2026-05-19 09:56:34

from __future__ import annotations

from pathlib import Path
import sys

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.visual_inspector import (  # noqa: E402
    _layout_nodes,
    build_evaluation_overview_payload,
    build_visual_graph_payload,
    render_visual_inspector_html,
)


def _sample_rag_payload() -> dict:
    return {
        "question": "오늘 운영자가 먼저 확인해야 할 이상 징후는 무엇인가?",
        "answer": "## 답변\n운영자는 station:152를 먼저 확인해야 합니다.\n\n## 근거 기반 판단\n- 이용량 변화가 확인됩니다.",
        "contract_pass": True,
        "requires_review": True,
        "review_reason": "추천 조치가 포함되어 사람 검토가 필요합니다.",
        "llm": {"mode": "live", "model": "gpt-5.2", "latency_ms": 1234.5},
        "quality_guard_notes": ["normalized_entity_reference"],
        "retrieval": {"top_k": 3, "latency_ms": 12.3, "matches": [{"id": "RAG-1", "score": 2.0}]},
        "evidence_documents": ["docs/project/aiplan.md"],
        "evidence_excerpt_list": [
            {"source": "docs/project/aiplan.md", "kind": "retrieved_context", "score": 2.0, "excerpt": "station:152 has usage metric 50"}
        ],
        "related_objects": [
            {"type": "Station", "id": "station:152", "label": "대여소 152"},
            {"type": "UsageMetric", "id": "metric:usage", "label": "이용량 50"},
        ],
        "related_relations": [
            {"source": "recommendation:1", "relation": "hasEvidence", "target": "docs/project/aiplan.md"},
            {"source": "recommendation:1", "relation": "forStation", "target": "station:152"},
        ],
        "quantitative_indicators": [
            {"metric": "metric_count", "value": 50, "source": "runtime_context"},
            {"metric": "retrieved_context_count", "value": 3, "source": "debug"},
        ],
        "recommended_actions": [
            {"target": "station:152", "action": "현장 점검", "reason": "이용량 변화 후보", "requires_human_approval": True}
        ],
        "data_gaps": ["station:152 has no detailed location/address attributes in current context.", "후보별 명시적 score가 부족합니다."],
    }


def test_build_visual_graph_payload_maps_rag_answer_to_user_visible_nodes() -> None:
    graph = build_visual_graph_payload(_sample_rag_payload(), debug_mode=False)

    node_types = {node["type"] for node in graph["nodes"]}
    assert {"question", "answer_claim", "evidence", "entity", "metric", "action", "data_gap", "review_gate"} <= node_types
    assert graph["summary"]["contractPass"] is True
    assert graph["summary"]["requiresReview"] is True
    assert any(node["label"] == "충무로역 3.4호선 (ST-152)" for node in graph["nodes"])
    assert any(node["type"] == "metric" and "metric_count=50" in node["label"] for node in graph["nodes"])
    assert any(edge["label"] == "대상 대여소" for edge in graph["edges"])
    assert all("hasEvidence" not in edge["label"] and "forStation" not in edge["label"] for edge in graph["edges"])
    assert all("retrieved_context_count" not in node["label"] for node in graph["nodes"] if node["visibleInUserView"])
    assert all("station:152" not in node["label"] for node in graph["nodes"] if node["visibleInUserView"])


def _sample_evaluation_rows() -> list[dict]:
    return [
        {
            "id": "Q-001",
            "question": "오늘 운영자가 먼저 확인해야 할 이상 징후는 무엇인가?",
            "category": "운영 모니터링",
            "status": "ok",
            "contract_pass": True,
            "requires_review": False,
            "llm_mode": "live",
            "data_gap_count": 1,
            "quality_guard_notes": [],
            "elapsed_ms": 120.5,
        },
        {
            "id": "Q-002",
            "question": "재배치 후보를 검토해줘",
            "category": "운영 모니터링",
            "status": "ok",
            "contract_pass": False,
            "requires_review": True,
            "llm_mode": "fallback_parse_error",
            "data_gap_count": 3,
            "quality_guard_notes": ["normalized_entity_reference"],
            "elapsed_ms": 250.0,
        },
        {
            "id": "Q-003",
            "question": "API 지연 상태는?",
            "category": "API/성능",
            "status": "error",
            "contract_pass": False,
            "requires_review": False,
            "llm_mode": "live",
            "data_gap_count": 0,
            "quality_guard_notes": ["profile_specific_guard"],
            "elapsed_ms": 500.0,
        },
    ]


def test_render_visual_inspector_html_separates_user_and_operator_debug() -> None:
    user_graph = build_visual_graph_payload(_sample_rag_payload(), debug_mode=False)
    user_html = render_visual_inspector_html(user_graph, debug_mode=False)

    assert "Answer Evidence Radial Graph" in user_html
    assert "<svg" in user_html
    assert "class=\"top-toolbar\"" in user_html
    assert "Node Type Legend" in user_html
    assert "data-node-type=\"review_gate\"" in user_html
    assert "<path class=\"edge" in user_html
    assert "function resetFocus()" in user_html
    assert "Escape" in user_html
    assert "id=\"label-size\"" in user_html
    assert "data-claim-id=\"claim:1\"" in user_html
    assert "connected-node-list" in user_html
    assert "충무로역 3.4호선 (ST-152)" in user_html
    assert "검토 필요" in user_html
    assert "retrieved_context_count" not in user_html
    assert "station:152" not in user_html
    assert "대여소 152" not in user_html
    assert "hasEvidence" not in user_html
    assert "forStation" not in user_html

    debug_graph = build_visual_graph_payload(_sample_rag_payload(), debug_mode=True)
    debug_html = render_visual_inspector_html(debug_graph, debug_mode=True)

    assert "Operator Debug" in debug_html
    assert "retrieved_context_count=3" in debug_html
    assert "llm_mode=live" in debug_html


def test_build_and_render_evaluation_overview_graph() -> None:
    graph = build_evaluation_overview_payload(_sample_evaluation_rows(), debug_mode=False)

    assert graph["kind"] == "evaluation_overview"
    assert graph["title"] == "RAG Evaluation Overview"
    assert graph["summary"]["questionCount"] == 3
    assert graph["summary"]["contractPassCount"] == 1
    assert graph["summary"]["failureCount"] == 2
    assert graph["summary"]["categoryCounts"] == {"운영 모니터링": 2, "API/성능": 1}
    assert graph["summary"]["llmModeCounts"] == {"live": 2, "fallback_parse_error": 1}
    positions = _layout_nodes(graph["nodes"])
    assert all(0 <= x <= 920 and 0 <= y <= 680 for x, y in positions.values())
    assert any(node["type"] == "category_cluster" and node["label"] == "운영 모니터링 (2)" for node in graph["nodes"])
    assert any(node["type"] == "evaluation_question" and node["status"] == "gap" for node in graph["nodes"])
    assert any(node["type"] == "evaluation_issue" and "contract_fail=2" in node["label"] for node in graph["nodes"])

    html = render_visual_inspector_html(graph, debug_mode=False)

    assert "RAG Evaluation Overview" in html
    assert "Evaluation Overview" in html
    assert "Category Clusters" in html
    assert "운영 모니터링 (2)" in html
    assert "contract_pass=1/3" in html
    assert "fallback_parse_error=1" in html
    assert "data-node-type=\"category_cluster\"" in html
    assert "data-node-type=\"evaluation_question\"" in html
