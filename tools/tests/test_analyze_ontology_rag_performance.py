# Timestamp: 2026-05-11 13:24:00

from pathlib import Path
import csv
import json
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

import rag.analyze_ontology_rag_performance as analysis  # noqa: E402


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _make_probe_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run_20260511_132400_gpt_api_qo03"
    run_dir.mkdir()
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "timestamp": "2026-05-11 13:24:00",
                "model": "chat-latest",
                "profile": "ontology-hybrid",
                "top_k": 5,
                "embedding_backend": "auto",
                "selected_question_count": 3,
                "success_count": 3,
                "failure_count": 0,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        run_dir / "responses.jsonl",
        [
            {
                "timestamp": "2026-05-11 13:24:00",
                "qid": "QO01",
                "question": "비 오는 출근시간에 가장 빨리 비어가는 대여소는 어디인가?",
                "model": "chat-latest",
                "profile": "ontology-hybrid",
                "status": "ok",
                "latency_ms": 4000,
                "answer": "현재 제공된 근거만으로는 특정할 수 없습니다.",
                "context_report": (
                    "Ontology-lite 성능 가드 intent=weather_demand_episode answerability=weak-context "
                    "evidence_kind=weak-context confidence=0.35 required_sources=weather_data.parquet,count_data.parquet "
                    "대용량 source count_data.parquet는 row scan은 생략했습니다."
                ),
                "context_source_summary": ["source: ontology-lite", "source: weather_data.parquet", "source: count_data.parquet"],
            },
            {
                "timestamp": "2026-05-11 13:24:00",
                "qid": "QO11",
                "question": "출근시간에는 대여 시작점이고 퇴근시간에는 반납 종착점으로 바뀌는 대여소는?",
                "model": "chat-latest",
                "profile": "ontology-hybrid",
                "status": "ok",
                "latency_ms": 3000,
                "answer": "role evidence로 일부 확인 가능합니다.",
                "context_report": "branchnum_r rental_station branchnum_b return_station answerability=direct confidence=0.90",
                "context_source_summary": ["source: rent_data.parquet"],
            },
            {
                "timestamp": "2026-05-11 13:24:00",
                "qid": "QO21",
                "question": "장거리 이동 직후 24시간 내 고장이 자주 나는 자전거는?",
                "model": "chat-latest",
                "profile": "ontology-hybrid",
                "status": "ok",
                "latency_ms": 5000,
                "answer": "현재 제공된 데이터만으로는 직접 검증하기 어렵습니다.",
                "context_report": "rent_data.bikenum -> broken_data.bikenum answerability=inferred confidence=0.64",
                "context_source_summary": ["source: rent_data.parquet", "source: broken_data.parquet"],
            },
        ],
    )
    (run_dir / "failures.jsonl").write_text("", encoding="utf-8")
    return run_dir


def test_analyze_probe_run_counts_answerability_and_warns_against_false_success(tmp_path):
    run_dir = _make_probe_run(tmp_path)

    result = analysis.analyze_probe_run(run_dir)

    assert result.metrics["response_count"] == 3
    assert result.metrics["status_counts"] == {"ok": 3}
    assert result.metrics["latency_ms"]["avg"] == 4000
    assert result.metrics["answerability_counts"]["insufficient_but_grounded"] == 2
    assert result.metrics["answerability_counts"]["answered"] == 1
    assert result.metrics["guard_hit_count"] == 1
    assert result.metrics["comparison_assessment"]["is_valid_rag_performance_comparison"] is False
    assert "비교군이 없다" in result.metrics["comparison_assessment"]["reasons"]


def test_write_analysis_outputs_generates_metrics_report_matrix_and_backlog(tmp_path):
    run_dir = _make_probe_run(tmp_path)

    output_paths = analysis.write_analysis_outputs(run_dir, timestamp="2026-05-11 13:24:00")

    assert output_paths["metrics"].name == "rag_performance_metrics.json"
    assert output_paths["report"].name == "rag_performance_analysis.md"
    assert output_paths["matrix"].name == "comparison_matrix.csv"
    assert output_paths["backlog"].name == "improvement_backlog.md"

    metrics = json.loads(output_paths["metrics"].read_text(encoding="utf-8"))
    report = output_paths["report"].read_text(encoding="utf-8")
    backlog = output_paths["backlog"].read_text(encoding="utf-8")
    matrix_lines = output_paths["matrix"].read_text(encoding="utf-8").splitlines()
    matrix_rows = list(csv.DictReader(line for line in matrix_lines if not line.startswith("#")))

    assert metrics["timestamp"] == "2026-05-11 13:24:00"
    assert metrics["default_next_model"] == "gpt-5.2"
    assert "성능 비교 근거로는 아직 부적절" in report
    assert "P0" in backlog
    assert matrix_rows[0]["qid"] == "QO01"
    assert matrix_rows[0]["profile"] == "ontology-hybrid"
    assert matrix_rows[0]["model"] == "chat-latest"
