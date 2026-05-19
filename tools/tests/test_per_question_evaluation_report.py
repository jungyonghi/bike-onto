# Timestamp: 2026-05-18 17:06:00

from __future__ import annotations

import json
from pathlib import Path
import sys

from PIL import Image


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.per_question_evaluation_report import build_per_question_evaluation_report  # noqa: E402
from rag.pgvector_integration_pack import build_pgvector_integration_pack  # noqa: E402


def _write_runtime_answers(path: Path) -> None:
    rows = [
        {
            "id": "RAG-EVAL-001",
            "question": "재배치가 필요한 대여소 후보는 어디인가?",
            "answer": "Station 102는 재배치 검토가 필요하다.",
            "evidence_documents": ["docs/project/aiplan.md"],
            "related_objects": [{"type": "Station", "id": "station:102"}],
            "related_relations": [{"type": "FOR_STATION"}],
            "recommended_actions": [{"type": "ReallocationAction", "summary": "검토"}],
            "requires_review": True,
            "contract_pass": True,
        },
        {
            "id": "RAG-EVAL-002",
            "question": "기준 데이터는 무엇인가?",
            "answer": "bike_cloud Parquet 기준본을 사용한다.",
            "evidence_documents": ["docs/project/db_catalog.md"],
            "related_objects": [{"type": "Dataset", "id": "dataset:bike_cloud"}],
            "related_relations": [{"type": "USES_DATASET"}],
            "recommended_actions": [],
            "requires_review": False,
            "contract_pass": True,
        },
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_per_question_evaluation_report_generates_markdown_and_screenshots(tmp_path: Path) -> None:
    runtime_answers = tmp_path / "graphrag_runtime_answers.jsonl"
    _write_runtime_answers(runtime_answers)
    pg_pack = build_pgvector_integration_pack(runtime_answers, tmp_path / "pgvector_pack", vector_dim=8)

    result = build_per_question_evaluation_report(
        runtime_answers_path=runtime_answers,
        pgvector_seed_path=pg_pack.seed_jsonl_path,
        output_dir=tmp_path / "question_eval",
        top_k=2,
    )

    assert result.question_count == 2
    assert result.screenshot_count == 2
    assert result.report_path.exists()
    markdown = result.report_path.read_text(encoding="utf-8")
    assert "RAG-EVAL-001" in markdown
    assert "실험 결과" in markdown
    assert "피드백" in markdown
    assert markdown.count("![") == 2

    for screenshot in result.screenshot_paths:
        assert screenshot.exists()
        with Image.open(screenshot) as image:
            assert image.size[0] >= 900
            assert image.size[1] >= 500
