# Timestamp: 2026-05-18 16:48:00

from __future__ import annotations

import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.ml_execution_pack import build_ml_execution_pack, run_lightweight_baseline  # noqa: E402
from rag.ontology_rag_fastapi_app import create_app  # noqa: E402
from rag.pgvector_integration_pack import build_pgvector_integration_pack  # noqa: E402


def _write_runtime_answers(path: Path) -> None:
    rows = [
        {
            "id": "RAG-EVAL-001",
            "question": "오전 부족 위험 대여소는 어디인가?",
            "answer": "Station 102는 오전 부족 위험이 높아 재배치 검토가 필요하다.",
            "evidence_documents": ["docs/project/aiplan.md", "data/processed/parquet/bike_cloud/count_data.parquet"],
            "related_objects": [{"type": "Station", "id": "station:102"}, {"type": "Recommendation", "id": "rec:001"}],
            "related_relations": [{"type": "FOR_STATION"}, {"type": "HAS_EVIDENCE"}],
            "recommended_actions": [{"type": "ReallocationAction", "summary": "야간 재배치 검토"}],
            "requires_review": True,
            "contract_pass": True,
        },
        {
            "id": "RAG-EVAL-002",
            "question": "기준 데이터셋은 무엇인가?",
            "answer": "bike_cloud Parquet 기준본과 문서 근거를 사용한다.",
            "evidence_documents": ["docs/project/db_catalog.md"],
            "related_objects": [{"type": "Dataset", "id": "dataset:bike_cloud"}],
            "related_relations": [{"type": "USES_DATASET"}],
            "recommended_actions": [],
            "requires_review": False,
            "contract_pass": True,
        },
        {
            "id": "RAG-EVAL-003",
            "question": "보류 문서는 핵심 근거로 쓰는가?",
            "answer": "보류 문서는 핵심 근거로 쓰지 않고 검토 대상으로 남긴다.",
            "evidence_documents": [],
            "related_objects": [{"type": "ReviewDecision", "id": "review:hold"}],
            "related_relations": [],
            "recommended_actions": [{"type": "ReviewAction", "summary": "보류 유지"}],
            "requires_review": True,
            "contract_pass": False,
        },
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_ml_pgvector_and_fastapi_execution_connectors(tmp_path: Path) -> None:
    runtime_answers = tmp_path / "graphrag_runtime_answers.jsonl"
    _write_runtime_answers(runtime_answers)

    ml_dir = tmp_path / "ml_pack"
    ml_pack = build_ml_execution_pack(runtime_answers, ml_dir)
    metrics = run_lightweight_baseline(ml_pack.feature_table_csv, ml_dir, target="label_requires_review")

    registry = json.loads(ml_pack.model_registry_path.read_text(encoding="utf-8"))
    assert "catboost_classifier" in {model["id"] for model in registry["models"]}
    assert ml_pack.row_count == 3
    assert metrics.metrics_path.exists()
    assert metrics.model_family in {"sklearn", "rule_fallback", "diagnostic"}

    pg_dir = tmp_path / "pgvector_pack"
    pg_pack = build_pgvector_integration_pack(runtime_answers, pg_dir, vector_dim=12)
    assert "CREATE EXTENSION IF NOT EXISTS vector" in pg_pack.schema_sql_path.read_text(encoding="utf-8")
    assert "embedding vector(12)" in pg_pack.schema_sql_path.read_text(encoding="utf-8")
    assert pg_pack.seed_count == 3

    app = create_app(
        runtime_answers_path=runtime_answers,
        ml_feature_table_path=ml_pack.feature_table_jsonl,
        pgvector_seed_path=pg_pack.seed_jsonl_path,
    )
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    features = client.get("/ml/features")
    assert features.status_code == 200
    assert features.json()["count"] == 3

    query = client.post("/query", json={"question": "오전 부족 위험 재배치 검토", "top_k": 2})
    assert query.status_code == 200
    payload = query.json()
    assert payload["answer_count"] >= 1
    assert payload["matches"][0]["id"] == "RAG-EVAL-001"


def test_catboost_optional_runner_reports_dependency_or_trains(tmp_path: Path) -> None:
    from rag.catboost_optional_baseline import run_catboost_optional_baseline

    runtime_answers = tmp_path / "graphrag_runtime_answers.jsonl"
    _write_runtime_answers(runtime_answers)
    ml_pack = build_ml_execution_pack(runtime_answers, tmp_path / "ml_pack")

    result = run_catboost_optional_baseline(
        feature_table_csv=ml_pack.feature_table_csv,
        output_dir=tmp_path / "catboost_optional",
        target="label_requires_review",
    )

    assert result.report_path.exists()
    assert result.status in {"trained", "dependency_missing", "single_class", "no_rows"}
    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert payload["model_id"] == "catboost_classifier"
