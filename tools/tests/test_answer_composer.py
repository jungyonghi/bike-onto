# Timestamp: 2026-05-19 01:08:25

from __future__ import annotations

from pathlib import Path
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.answer_composer import build_answer_prompt, compose_answer, entity_display_name  # noqa: E402
from rag.intent_classifier import classify_question_intent  # noqa: E402
from rag.schemas import AnswerProfile, EvidenceBundle, RecommendedAction  # noqa: E402


FORBIDDEN_USER_PHRASES = [
    "근거 5개를 기준으로 답변합니다",
    "관계 6개를 기준으로 답변합니다",
    "추천 조치 후보는 1개",
    "제공된 context 밖의 원천을 추가로 추정하지 않습니다",
    "retrieved_context_count",
    "top1_retrieval_score",
]


def _sample_evidence() -> EvidenceBundle:
    return EvidenceBundle(
        contexts=["station:152와 station:151이 이용량 변화 후보로 확인됨"],
        evidence_documents=[{"path": "docs/source.md", "title": "source"}],
        related_objects=[{"type": "Station", "id": "station:152"}, {"type": "Station", "id": "station:151"}],
        related_relations=[{"source": "metric:usage", "relation": "FLAGS", "target": "station:152"}],
        recommended_actions=[
            RecommendedAction(
                target="station:152",
                action="재배치 필요 여부 검토",
                reason="이용량 변화 후보에 포함됨",
                requires_human_approval=True,
                auto_executable=False,
            )
        ],
        debug={
            "retrieved_context_count": 5,
            "evidence_document_count": 6,
            "related_object_count": 2,
            "related_relation_count": 1,
            "top1_retrieval_score": 2.224,
            "top1_token_overlap": 3,
        },
    )


def test_compose_answer_hides_debug_and_forbidden_meta_by_default() -> None:
    answer = compose_answer(
        "오늘 운영자가 먼저 확인해야 할 이상 징후는 무엇인가?",
        _sample_evidence(),
        category="운영 모니터링",
        debug_mode=False,
    )

    assert answer.startswith("## 답변")
    assert "## 디버깅 정보" not in answer
    assert "충무로역 3.4호선 (ST-152)" in answer
    for phrase in FORBIDDEN_USER_PHRASES:
        assert phrase not in answer


def test_compose_answer_outputs_debug_only_when_enabled() -> None:
    answer = compose_answer(
        "오늘 운영자가 먼저 확인해야 할 이상 징후는 무엇인가?",
        _sample_evidence(),
        category="운영 모니터링",
        debug_mode=True,
    )

    assert "## 디버깅 정보" in answer
    assert "- retrieved_context_count: 5" in answer
    assert "- evidence_document_count: 6" in answer
    assert "- top1_retrieval_score: 2.224" in answer


def test_compose_answer_renders_recommended_action_details() -> None:
    answer = compose_answer(
        "station:152는 어떤 조치를 해야 하는가?",
        _sample_evidence(),
        category="추천/재배치/우선순위",
    )

    assert "대상: 충무로역 3.4호선 (ST-152)" in answer
    assert "조치: 재배치 필요 여부 검토" in answer
    assert "이유: 이용량 변화 후보에 포함됨" in answer
    assert "사람 검토 필요" in answer


def test_api_db_performance_profile_uses_latency_terms_not_demand_terms() -> None:
    evidence = EvidenceBundle(
        contexts=["검색 latency 저하가 관측됨"],
        evidence_documents=[],
        related_objects=[],
        related_relations=[],
        recommended_actions=[],
        debug={},
    )

    answer = compose_answer("검색 latency가 느려졌을 때 원인을 어떻게 분리해야 하는가?", evidence)

    assert classify_question_intent("검색 latency가 느려졌을 때 원인을 어떻게 분리해야 하는가?") == AnswerProfile.API_DB_PERFORMANCE
    for expected in ["API 처리 시간", "DB query time", "vector search time", "LLM generation time", "p95 latency"]:
        assert expected in answer
    assert "전일 대비 이용량" not in answer
    assert "station 후보" not in answer


def test_demand_usage_profile_uses_usage_terms_not_performance_terms() -> None:
    evidence = EvidenceBundle(
        contexts=["이용량 변화 후보를 산출해야 함"],
        evidence_documents=[],
        related_objects=[],
        related_relations=[],
        recommended_actions=[],
        debug={},
    )

    answer = compose_answer("전일 대비 이용량이 크게 달라진 후보를 어떻게 뽑아야 하는가?", evidence)

    assert classify_question_intent("전일 대비 이용량이 크게 달라진 후보를 어떻게 뽑아야 하는가?") == AnswerProfile.DEMAND_USAGE_ANALYSIS
    for expected in ["전일 대비 증감률", "최근 7일 평균", "동일 요일 평균", "시간대별 변화량"]:
        assert expected in answer
    assert "API latency" not in answer
    assert "DB query time" not in answer


def test_grounded_fallback_lists_missing_data_and_next_checks() -> None:
    evidence = EvidenceBundle(
        contexts=[],
        evidence_documents=[],
        related_objects=[],
        related_relations=[],
        recommended_actions=[],
        debug={},
    )

    answer = compose_answer("검색 latency가 느려졌을 때 원인을 어떻게 분리해야 하는가?", evidence)

    assert "## 부족한 근거" in answer
    assert "## 다음 확인 필요" in answer
    assert "API endpoint별 p95 latency" in answer
    assert "DB query time" in answer
    assert "vector search time" in answer
    assert "현재 근거만으로는" in answer


def test_compose_answer_normalizes_relation_labels_and_prioritizes_entity_names() -> None:
    evidence = EvidenceBundle(
        contexts=["대여소 변화 후보가 확인됨"],
        evidence_documents=[],
        related_objects=[{"type": "Station", "id": "station:152", "label": "강남역 2번출구 대여소"}],
        related_relations=[
            {"source": "recommendation:1", "relation": "hasEvidence", "target": "evidence:1"},
            {"source": "recommendation:1", "relation": "forStation", "target": "station:152"},
        ],
        recommended_actions=[
            RecommendedAction(
                target="station:152",
                action="현장 점검",
                reason="이용량 변화 후보에 포함됨",
                requires_human_approval=True,
            )
        ],
        debug={},
    )

    answer = compose_answer("오늘 운영자가 먼저 확인해야 할 이상 징후는 무엇인가?", evidence, category="운영 모니터링")

    assert "충무로역 3.4호선 (ST-152)" in answer
    assert "대상: 충무로역 3.4호선 (ST-152)" in answer
    assert "강남역 2번출구 대여소 (station:152)" not in answer
    assert "근거" in answer
    assert "대상 대여소" in answer
    assert "hasEvidence" not in answer
    assert "forStation" not in answer
    assert "운영자는 station:152" not in answer


def test_entity_display_extracts_generic_place_name_from_address_before_id() -> None:
    obj = {
        "type": "Location",
        "id": "place:city-hall-exit5",
        "name": "서울특별시 중구 세종대로 110 시청역 5번출구",
    }

    assert entity_display_name(obj) == "시청역 5번출구 (place:city-hall-exit5)"


def test_compose_answer_prioritizes_generic_place_targets_over_metrics() -> None:
    evidence = EvidenceBundle(
        contexts=["운영 점검 후보와 지표가 함께 확인됨"],
        evidence_documents=[],
        related_objects=[
            {"type": "Metric", "id": "metric:p95", "label": "p95 latency"},
            {
                "type": "Location",
                "id": "place:city-hall-exit5",
                "address": "서울특별시 중구 세종대로 110 시청역 5번출구",
            },
        ],
        related_relations=[],
        recommended_actions=[],
        debug={},
    )

    answer = compose_answer("운영자가 어디를 먼저 봐야 해?", evidence, category="운영 모니터링")

    assert "시청역 5번출구 (place:city-hall-exit5)" in answer
    assert "운영자는 p95 latency" not in answer
    assert "서울특별시 중구 세종대로 110 시청역 5번출구" not in answer


def test_entity_display_prefers_generic_address2_place_name() -> None:
    obj = {
        "type": "Site",
        "id": "site:jongno3-exit2",
        "address": "서울특별시 종로구 종로 지하129",
        "address2": "종로3가역 2번출구 뒤",
    }

    assert entity_display_name(obj) == "종로3가역 2번출구 뒤 (site:jongno3-exit2)"


def test_build_answer_prompt_contains_output_contract_and_forbidden_rules() -> None:
    prompt = build_answer_prompt("무엇을 먼저 봐야 하는가?", AnswerProfile.OPERATIONS_MONITORING, _sample_evidence())

    assert "검색 결과의 존재를 설명하지 말고" in prompt
    assert "## 답변" in prompt
    assert "## 근거 기반 판단" in prompt
    assert "근거 N개를 기준으로 답변합니다" in prompt
    assert "권장 조치" in prompt
    assert "relation은 한국어 명사형 label" in prompt
    assert "엔티티는 id보다 display_name/name/label" in prompt
