# Timestamp: 2026-05-18 17:24:00

import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from PIL import Image


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.pgvector_integration_pack import build_pgvector_integration_pack  # noqa: E402
from rag.rag_llm_answer_endpoint import apply_answer_quality_guards, create_rag_llm_answer_app  # noqa: E402
from rag.rag_llm_answer_report import build_rag_llm_answer_report  # noqa: E402


def _write_runtime_answers(path: Path) -> None:
    rows = [
        {
            "id": "RAG-EVAL-001",
            "question": "재배치가 필요한 대여소 후보는 어디인가?",
            "answer": "Station 102는 재배치 검토가 필요하다.",
            "evidence_documents": ["docs/project/aiplan.md", "data/processed/parquet/bike_cloud/count_data.parquet"],
            "related_objects": [{"type": "Station", "id": "station:102", "label": "부족B"}],
            "related_relations": [{"source": "rec:001", "relation": "FOR_STATION", "target": "station:102"}],
            "recommended_actions": [{"type": "ReallocationAction", "summary": "야간 재배치 검토"}],
            "requires_review": True,
            "contract_pass": True,
        },
        {
            "id": "RAG-EVAL-002",
            "question": "기준 데이터는 무엇인가?",
            "answer": "bike_cloud Parquet 기준본을 사용한다.",
            "evidence_documents": ["docs/project/db_catalog.md"],
            "related_objects": [{"type": "Dataset", "id": "dataset:bike_cloud"}],
            "related_relations": [{"source": "service:obybk", "relation": "USES_DATASET", "target": "dataset:bike_cloud"}],
            "recommended_actions": [],
            "requires_review": False,
            "contract_pass": True,
        },
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def fake_llm(prompt: str, context: dict) -> dict:
    return {
        "answer": f"RAG 근거 기반 답변: {context['question']}에 대해 {len(context['retrieved_contexts'])}개 근거를 사용했습니다.",
        "evidence_documents": context["evidence_documents"][:3],
        "related_objects": context["related_objects"][:3],
        "related_relations": context["related_relations"][:3],
        "recommended_actions": context["recommended_actions"][:2],
        "requires_review": context["requires_review"],
        "review_reason": "추천 조치가 포함되어 사람 검토가 필요합니다." if context["requires_review"] else "자동 응답 후보입니다.",
        "uncertainty": "테스트 LLM",
        "_raw_text": "fake",
        "_meta": {"mode": "fake", "model": "fake-llm", "latency_ms": 1.0},
    }


def test_rag_llm_answer_endpoint_generates_grounded_answer(tmp_path: Path) -> None:
    runtime_answers = tmp_path / "graphrag_runtime_answers.jsonl"
    _write_runtime_answers(runtime_answers)
    pg_pack = build_pgvector_integration_pack(runtime_answers, tmp_path / "pgvector_pack", vector_dim=8)

    app = create_rag_llm_answer_app(
        runtime_answers_path=runtime_answers,
        pgvector_seed_path=pg_pack.seed_jsonl_path,
        llm_callable=fake_llm,
    )
    client = TestClient(app)

    response = client.post("/rag-answer", json={"question": "재배치가 필요한 대여소 후보", "top_k": 2})
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "rag_llm"
    assert "RAG 근거 기반 답변" in payload["answer"]
    assert payload["retrieval"]["matches"][0]["id"] == "RAG-EVAL-001"
    assert payload["llm"]["model"] == "fake-llm"
    assert payload["evidence_documents"]


def test_rag_llm_answer_report_generates_markdown_and_screenshots(tmp_path: Path) -> None:
    runtime_answers = tmp_path / "graphrag_runtime_answers.jsonl"
    _write_runtime_answers(runtime_answers)
    pg_pack = build_pgvector_integration_pack(runtime_answers, tmp_path / "pgvector_pack", vector_dim=8)

    result = build_rag_llm_answer_report(
        runtime_answers_path=runtime_answers,
        pgvector_seed_path=pg_pack.seed_jsonl_path,
        output_dir=tmp_path / "rag_llm_report",
        llm_callable=fake_llm,
        top_k=2,
    )

    assert result.question_count == 2
    assert result.screenshot_count == 2
    assert result.report_path.exists()
    markdown = result.report_path.read_text(encoding="utf-8")
    assert "RAG 기반 LLM 답변" in markdown
    assert "RAG 근거 기반 답변" in markdown
    assert markdown.count("![") == 2

    for screenshot in result.screenshot_paths:
        assert screenshot.exists()
        with Image.open(screenshot) as image:
            assert image.size[0] >= 1000
            assert image.size[1] >= 600


def test_rag_llm_context_enrichment_is_general_and_not_location_only(tmp_path: Path) -> None:
    runtime_answers = tmp_path / "graphrag_runtime_answers.jsonl"
    rows = [
        {
            "question_id": "RAG-EVAL-001",
            "question": "후보 엔티티는 어디이며 어떤 근거로 연결되는가?",
            "answer": "entity:152가 후보로 보인다.",
            "evidence_documents": ["docs/source.md"],
            "related_objects": [
                {"type": "Entity", "id": "entity:152", "label": "Entity 152"},
                {"type": "Recommendation", "id": "recommendation:sample", "label": "sample recommendation"},
            ],
            "related_relations": [
                {"source": "Metric", "relation": "FOR_ENTITY", "target": "Entity"},
                {"source": "Recommendation", "relation": "HAS_EVIDENCE", "target": "Evidence"},
            ],
            "recommended_actions": [{"type": "ReviewAction", "summary": "후보 검토"}],
            "requires_review": True,
            "contract_pass": True,
            "graph_metrics": {"entity_sample_preview": ["entity:152", "entity:151", "entity:150"], "metric_count": 50},
        }
    ]
    runtime_answers.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    pg_pack = build_pgvector_integration_pack(runtime_answers, tmp_path / "pgvector_pack", vector_dim=8)
    captured: dict = {}

    def checking_llm(prompt: str, context: dict) -> dict:
        captured["prompt"] = prompt
        captured["context"] = context
        return {
            "answer": "Entity 152는 현재 context에 상세 위치 속성이 없어 위치를 단정하지 않고 후보 목록과 정량 지표를 함께 제시합니다.",
            "evidence_documents": context["evidence_documents"],
            "related_objects": context["related_objects"],
            "related_relations": context["related_relations"],
            "recommended_actions": context["recommended_actions"],
            "requires_review": context["requires_review"],
            "review_reason": "후보 검토 필요",
            "uncertainty": "위치 속성 부족",
            "entity_cards": context["entity_cards"],
            "candidate_set": context["candidate_set"],
            "quantitative_indicators": context["quantitative_indicators"],
            "evidence_excerpt_list": context["evidence_excerpt_list"],
            "data_gaps": context["data_gaps"],
            "_meta": {"mode": "fake", "model": "fake-llm", "latency_ms": 1.0},
        }

    app = create_rag_llm_answer_app(
        runtime_answers_path=runtime_answers,
        pgvector_seed_path=pg_pack.seed_jsonl_path,
        llm_callable=checking_llm,
    )
    client = TestClient(app)
    response = client.post("/rag-answer", json={"question": "후보 엔티티는 어디이며 어떤 근거로 연결되는가?", "top_k": 1})
    assert response.status_code == 200
    payload = response.json()

    assert "파일 경로는 본문보다 발췌 목록" in captured["prompt"]
    assert "place_name/address2/address" in captured["prompt"]
    assert "역이름·지명 suffix" in captured["prompt"]
    assert captured["context"]["entity_cards"][0]["detail_status"] in {"minimal", "resolved"}
    assert any(candidate["candidate_id"] == "entity:151" for candidate in payload["candidate_set"])
    assert any(item["metric"] == "metric_count" and item["value"] == 50 for item in payload["quantitative_indicators"])
    assert payload["evidence_excerpt_list"]
    assert payload["data_gaps"]


def test_rag_llm_answer_quality_guard_candidate_note_prefers_display_names() -> None:
    answer, notes = apply_answer_quality_guards(
        "재배치 후보를 여러 개로 설명해줘",
        "후보는 station:152입니다.",
        {
            "related_objects": [{"type": "Station", "id": "station:152", "label": "강남역 2번출구 대여소"}],
            "candidate_set": [
                {"candidate_id": "station:152"},
                {"candidate_id": "station:151"},
            ],
        },
    )

    assert notes
    assert "충무로역 3.4호선 (ST-152)" in answer
    assert "가로판매대 (ST-151)" in answer
    assert "station:152" not in answer
    assert "대여소 152" not in answer
    assert "강남역 2번출구 대여소 (station:152)" not in answer


def test_rag_llm_answer_quality_guard_translates_relation_count_metrics() -> None:
    answer, notes = apply_answer_quality_guards(
        "특정 시간대 이용량이 줄어든 이유는 무엇인가?",
        "이유는 현재 근거만으로 확정할 수 없습니다.",
        {"quantitative_indicators": [{"metric": "relation_count:affectedByWeather", "value": 1}]},
    )

    assert notes
    assert "날씨 영향=1" in answer
    assert "affectedByWeather" not in answer


def test_rag_llm_answer_quality_guard_keeps_recommendation_reason_out_of_demand_template() -> None:
    answer, notes = apply_answer_quality_guards(
        "추천 후보가 1개만 나올 때 왜 위험한지 설명해줘",
        "위험은 현재 근거만으로 확정할 수 없습니다.",
        {"category": "추천/재배치/우선순위", "quantitative_indicators": []},
    )

    assert notes
    assert "후보 다양성" in answer
    assert "승인 조건" in answer
    assert "이용량 delta" not in answer
    assert "전일/지난 7일" not in answer


def test_rag_llm_answer_quality_guard_keeps_api_latency_diagnostic_out_of_demand_template() -> None:
    answer, notes = apply_answer_quality_guards(
        "검색 latency가 느려졌을 때 원인을 어떻게 분리해야 하는가?",
        "원인은 현재 근거만으로 확정할 수 없습니다.",
        {"category": "API/DB/성능", "quantitative_indicators": []},
    )

    assert notes
    assert "API 처리 시간" in answer
    assert "DB query time" in answer
    assert "vector search time" in answer
    assert "p95 latency" in answer
    assert "이용량 delta" not in answer
    assert "전일/지난 7일" not in answer
    assert "최근 7일 평균 대비 편차" not in answer


def test_rag_llm_answer_quality_guard_adds_active_analysis_for_weak_answer(tmp_path: Path) -> None:
    runtime_answers = tmp_path / "graphrag_runtime_answers.jsonl"
    rows = [
        {
            "question_id": "RAG-EVAL-002",
            "question": "특정 시간대에 이용량이 줄어든 이유는 무엇인가?",
            "answer": "요약 답변",
            "evidence_documents": ["docs/source.md"],
            "related_objects": [{"type": "UsageMetric", "id": "usage:count", "label": "50"}],
            "related_relations": [{"source": "UsageMetric", "relation": "IN_TIME_BUCKET", "target": "TimeBucket"}],
            "recommended_actions": [],
            "requires_review": False,
            "contract_pass": True,
            "graph_metrics": {"usage_metric_count": 50, "time_bucket_count": 1},
        }
    ]
    runtime_answers.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    pg_pack = build_pgvector_integration_pack(runtime_answers, tmp_path / "pgvector_pack", vector_dim=8)

    def weak_llm(prompt: str, context: dict) -> dict:
        return {
            "answer": "이유는 현재 근거만으로 확정할 수 없습니다.",
            "evidence_documents": context["evidence_documents"],
            "related_objects": context["related_objects"],
            "related_relations": context["related_relations"],
            "recommended_actions": [],
            "requires_review": False,
            "review_reason": "",
            "uncertainty": "weak",
            "_meta": {"mode": "fake", "model": "weak", "latency_ms": 1.0},
        }

    app = create_rag_llm_answer_app(
        runtime_answers_path=runtime_answers,
        pgvector_seed_path=pg_pack.seed_jsonl_path,
        llm_callable=weak_llm,
    )
    response = TestClient(app).post("/rag-answer", json={"question": "특정 시간대에 이용량이 줄어든 이유는 무엇인가?", "top_k": 1})
    payload = response.json()
    assert "기준 기간" in payload["answer"]
    assert "delta" in payload["answer"] or "증감" in payload["answer"]
    assert payload["quality_guard_notes"]
