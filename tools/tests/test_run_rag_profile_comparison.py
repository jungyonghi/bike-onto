# Timestamp: 2026-05-11 14:43:21

from pathlib import Path
import csv
import json
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TOOLS_DIR.parents[0]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

import rag.run_rag_profile_comparison as comparison  # noqa: E402


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_select_comparison_questions_returns_qp50_and_qo50():
    questions = comparison.select_comparison_questions(PROJECT_ROOT)

    assert len(questions) == 100
    assert [question.qid for question in questions[:3]] == ["QP01", "QP02", "QP03"]
    assert questions[49].qid == "QP50"
    assert questions[50].qid == "QO01"
    assert questions[-1].qid == "QO50"
    assert sum(question.question_group == "QP" for question in questions) == 50
    assert sum(question.question_group == "QO" for question in questions) == 50
    assert questions[0].expected_sources
    assert questions[0].expected_data_fields


def test_mock_comparison_run_writes_profile_responses_and_matrix(tmp_path):
    def fake_context_builder(project_root, question, profile, runtime):
        return comparison.ProfileContext(
            prompt=f"{profile} prompt {question.qid}",
            context_report=(
                f"source={question.expected_sources[0] if question.expected_sources else 'branch_data.parquet'} "
                "field=branchnum confidence=0.80 evidence_kind=direct"
            ),
            context_source_summary=[question.expected_sources[0] if question.expected_sources else "branch_data.parquet"],
            retrieved_sources=list(question.expected_sources[:1]),
        )

    def fake_answerer(question, profile, runtime, context):
        return f"{question.qid} {profile} answer source confidence evidence_kind direct"

    run_dir = comparison.run_comparison(
        project_root=PROJECT_ROOT,
        output_dir=tmp_path,
        timestamp="2026-05-11 14:43:21",
        runtime=comparison.ComparisonRuntime(
            model="gpt-5.2",
            llm_url="https://api.openai.com/v1",
            api_key="sk-test",
            profiles=("db-only", "ontology-hybrid"),
            embedding_backend="hashing",
            top_k=1,
        ),
        answerer=fake_answerer,
        context_builder=fake_context_builder,
        report_path=tmp_path / "comparison_report.md",
    )

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    questions = _read_jsonl(run_dir / "questions.jsonl")
    responses = _read_jsonl(run_dir / "profile_responses.jsonl")
    metrics = json.loads((run_dir / "comparison_metrics.json").read_text(encoding="utf-8"))
    with (run_dir / "comparison_matrix.csv").open(encoding="utf-8") as file:
        matrix_rows = list(csv.DictReader(file))

    assert manifest["selected_question_count"] == 100
    assert manifest["profile_response_count"] == 200
    assert manifest["batch_status"] == "completed"
    assert len(questions) == 100
    assert len(responses) == 200
    assert len(matrix_rows) == 200
    assert set(row["profile"] for row in matrix_rows) == {"db-only", "ontology-hybrid"}
    assert set(metrics["by_group_and_profile"]) >= {
        "QP::db-only",
        "QP::ontology-hybrid",
        "QO::db-only",
        "QO::ontology-hybrid",
    }


def test_smoke_failure_does_not_leak_api_key(tmp_path):
    secret = "sk-secret-never-print"

    def fake_context_builder(project_root, question, profile, runtime):
        return comparison.ProfileContext(
            prompt="prompt",
            context_report="source=branch_data.parquet",
            context_source_summary=["source=branch_data.parquet"],
            retrieved_sources=["branch_data.parquet"],
        )

    def fake_answerer(question, profile, runtime, context):
        raise RuntimeError(f"unauthorized for {secret}")

    run_dir = comparison.run_comparison(
        project_root=PROJECT_ROOT,
        output_dir=tmp_path,
        timestamp="2026-05-11 14:43:21",
        runtime=comparison.ComparisonRuntime(
            model="gpt-5.2",
            llm_url="https://api.openai.com/v1",
            api_key=secret,
            profiles=("db-only", "ontology-hybrid"),
            embedding_backend="hashing",
            top_k=1,
        ),
        answerer=fake_answerer,
        context_builder=fake_context_builder,
        report_path=tmp_path / "comparison_report.md",
    )

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    responses = _read_jsonl(run_dir / "profile_responses.jsonl")
    failures = _read_jsonl(run_dir / "failures.jsonl")
    combined_text = "\n".join(path.read_text(encoding="utf-8") for path in run_dir.iterdir() if path.is_file())

    assert manifest["smoke_test_status"] == "failed"
    assert manifest["batch_status"] == "stopped_after_smoke_failure"
    assert len(responses) == 1
    assert len(failures) == 1
    assert secret not in combined_text


def test_qo_source_hit_alone_is_not_answer_quality_success():
    question = comparison.ComparisonQuestion(
        qid="QO44",
        question="어떤 답변은 직접 조인 근거보다 추론 조인 근거가 더 많아서 신뢰도 표기가 필요한가?",
        question_group="QO",
        expected_query="EvidenceGraph WHERE inferred_edges > direct_edges",
        physical_query="현재는 질의별로 어떤 조인이 logical join인지 사람이 수동 추적해야 함",
        verdict="높음",
        expected_sources=("rent_data.parquet",),
        expected_data_fields=("bikenum",),
    )
    row = comparison.build_response_row(
        question=question,
        profile="ontology-hybrid",
        runtime=comparison.ComparisonRuntime(
            model="gpt-5.2",
            llm_url="https://api.openai.com/v1",
            api_key="",
            profiles=("ontology-hybrid",),
            embedding_backend="hashing",
            top_k=1,
        ),
        context=comparison.ProfileContext(
            prompt="prompt",
            context_report="source=rent_data.parquet",
            context_source_summary=["source=rent_data.parquet"],
            retrieved_sources=["rent_data.parquet"],
        ),
        timestamp="2026-05-11 14:43:21",
        latency_ms=10,
        status="ok",
        answer="rent_data.parquet를 참고합니다.",
    )

    assert row["source_hit"] is True
    assert row["qo_answer_quality_success"] is False
    assert row["evidence_quality_score"] < 2


def test_write_final_report_has_timestamp_and_100_question_appendix(tmp_path):
    questions = comparison.select_comparison_questions(PROJECT_ROOT)
    metrics = {
        "by_group_and_profile": {
            "QP::db-only": {
                "response_count": 50,
                "source_hit_rate": 0.92,
                "answered_rate": 0.94,
                "expected_field_hit_rate": 0.94,
                "latency": {"avg_ms": 6439.8, "p95_ms": 9494},
            },
            "QP::ontology-hybrid": {
                "response_count": 50,
                "source_hit_rate": 0.96,
                "answered_rate": 0.90,
                "expected_field_hit_rate": 0.98,
                "latency": {"avg_ms": 7200.76, "p95_ms": 12009},
            },
            "QO::db-only": {
                "response_count": 50,
                "source_hit_rate": 0.96,
                "answered_rate": 0.08,
                "qo_answer_quality_success_rate": 0.08,
                "confidence_mention_rate": 0.50,
                "relation_mention_rate": 0.20,
                "latency": {"avg_ms": 9656.52, "p95_ms": 15154},
            },
            "QO::ontology-hybrid": {
                "response_count": 50,
                "source_hit_rate": 0.98,
                "answered_rate": 0.42,
                "qo_answer_quality_success_rate": 0.42,
                "confidence_mention_rate": 0.82,
                "relation_mention_rate": 0.64,
                "latency": {"avg_ms": 10435.46, "p95_ms": 15155},
            },
        }
    }
    report_path = tmp_path / "report.md"

    comparison.write_final_report(
        report_path=report_path,
        timestamp="2026-05-11 14:43:21",
        run_dir=tmp_path,
        manifest={"model": "gpt-5.2", "profiles": ["db-only", "ontology-hybrid"], "top_k": 5},
        metrics=metrics,
        questions=questions,
        matrix_rows=[],
    )

    report = report_path.read_text(encoding="utf-8")

    assert report.startswith("# Timestamp: 2026-05-11 14:43:21")
    assert sum(line.startswith("| QP") and line[4:6].isdigit() for line in report.splitlines()) == 50
    assert sum(line.startswith("| QO") and line[4:6].isdigit() for line in report.splitlines()) == 50
    assert "db-only" in report
    assert "ontology-hybrid" in report
    assert "native RAG(db-only)" in report
    assert "ontology-base RAG(ontology-hybrid)" in report
    assert "## 4. KPI 판정 기준" in report
    assert "QP baseline preservation" in report
    assert "QO ontology value uplift" in report
    assert "## 5. 현재 run 기준 KPI 판정" in report
    assert "| QO answered uplift | `+0.34p` | `>= +0.25p` | 통과 |" in report
    assert "| Latency p95 overhead | QP `+26.5%`, QO `+0.0%` | `<= 30%` 주의 허용 | 주의 |" in report
    assert "QO 결과는 source hit만으로 성공 처리하지 않는다" in report
