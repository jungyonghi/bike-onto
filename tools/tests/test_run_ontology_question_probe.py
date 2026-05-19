# Timestamp: 2026-05-11 12:31:00
# Timestamp: 2026-05-11 13:04:20

from pathlib import Path
import json
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TOOLS_DIR.parents[0]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

import rag.run_ontology_question_probe as probe  # noqa: E402


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_select_qo_questions_returns_qo01_to_qo30():
    questions = probe.select_qo_questions(PROJECT_ROOT, count=30)

    assert len(questions) == 30
    assert questions[0].qid == "QO01"
    assert questions[-1].qid == "QO30"
    assert all(question.qid.startswith("QO") for question in questions)
    assert questions[0].expected_query


def test_smoke_failure_stops_batch_and_does_not_leak_api_key(tmp_path):
    secret = "sk-should-not-appear"

    def fake_answerer(question, runtime, context):
        raise RuntimeError(f"unauthorized for key {secret}")

    run_dir = probe.run_probe(
        project_root=PROJECT_ROOT,
        output_dir=tmp_path,
        timestamp="2026-05-11 12:31:00",
        question_count=30,
        answerer=fake_answerer,
        runtime=probe.ProbeRuntime(
            model="gpt-oss-120b",
            llm_url="https://api.openai.com/v1",
            api_key=secret,
            profile="ontology-hybrid",
            embedding_backend="hashing",
            top_k=1,
        ),
    )

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    responses = _read_jsonl(run_dir / "responses.jsonl")
    failures = _read_jsonl(run_dir / "failures.jsonl")
    combined_text = "\n".join(path.read_text(encoding="utf-8") for path in run_dir.iterdir() if path.is_file())

    assert manifest["smoke_test_status"] == "failed"
    assert manifest["batch_status"] == "stopped_after_smoke_failure"
    assert len(responses) == 1
    assert len(failures) == 1
    assert responses[0]["qid"] == "QO01"
    assert secret not in combined_text


def test_successful_mock_run_writes_responses_and_summary(tmp_path):
    def fake_answerer(question, runtime, context):
        return f"{question.qid} answer using ontology evidence"

    run_dir = probe.run_probe(
        project_root=PROJECT_ROOT,
        output_dir=tmp_path,
        timestamp="2026-05-11 12:31:00",
        question_count=3,
        answerer=fake_answerer,
        runtime=probe.ProbeRuntime(
            model="gpt-oss-120b",
            llm_url="https://api.openai.com/v1",
            api_key="sk-test",
            profile="ontology-hybrid",
            embedding_backend="hashing",
            top_k=1,
        ),
    )

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    questions = _read_jsonl(run_dir / "questions.jsonl")
    responses = _read_jsonl(run_dir / "responses.jsonl")
    report = (run_dir / "summary_report.md").read_text(encoding="utf-8")

    assert manifest["smoke_test_status"] == "passed"
    assert manifest["batch_status"] == "completed"
    assert len(questions) == 3
    assert all(question["timestamp"] == "2026-05-11 12:31:00" for question in questions)
    assert len(responses) == 3
    assert all(response["status"] == "ok" for response in responses)
    assert "QO01" in report
    assert "success_count: `3`" in report


def test_summary_report_keeps_full_answers_without_preview_truncation():
    long_answer = "첫 문장입니다.\n" + ("중간 설명 " * 40) + "마지막 결론입니다."
    manifest = {
        "timestamp": "2026-05-11 13:10:00",
        "model": "gpt-5.2",
        "profile": "ontology-hybrid",
        "selected_question_count": 1,
        "smoke_test_status": "passed",
        "batch_status": "completed",
    }
    responses = [
        {
            "qid": "QO30",
            "question": "고장 기록이 있었는데도 곧바로 다시 대여된 자전거는 무엇인가?",
            "status": "ok",
            "answer": long_answer,
        }
    ]

    report = probe._summary_report(manifest, responses, failures=[])

    assert "### QO30 - ok" in report
    assert "고장 기록이 있었는데도 곧바로 다시 대여된 자전거는 무엇인가?" in report
    assert "마지막 결론입니다." in report
    assert "- `QO30` ok:" not in report
