# Timestamp: 2026-05-11 12:31:00
# Timestamp: 2026-05-11 12:56:21
# Timestamp: 2026-05-11 13:04:20

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Sequence


TOOLS_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_SCRIPTS_DIR))

from rag.ttareungi_rag import (
    DEFAULT_OPENAI_API_KEY_ENV,
    DEFAULT_OPENAI_API_KEY_FILE,
    LLM_PROVIDER_OPENAI,
    PROFILE_ONTOLOGY_HYBRID,
    HashingEmbedder,
    SentenceTransformerEmbedder,
    build_context_report,
    build_prompt,
    call_qwen_chat,
    collect_fact_snippets,
    create_embedder_for_index,
    default_index_dir,
    find_project_root,
    index_is_ready,
    resolve_llm_runtime_settings,
    search_faiss_index,
)


QUESTION_BANK_RELATIVE_PATH = Path("docs/project/obybk_ontology_necessity_performance_question_bank.md")
DEFAULT_OUTPUT_ROOT = Path("data/processed/exports/ontology_question_runs")
DEFAULT_QUESTION_COUNT = 30
DEFAULT_TOP_K = 5


@dataclass(frozen=True)
class OntologyQuestion:
    qid: str
    question: str
    expected_query: str
    physical_query: str
    verdict: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ProbeRuntime:
    model: str
    llm_url: str
    api_key: str
    profile: str
    embedding_backend: str
    top_k: int


@dataclass(frozen=True)
class ProbeContext:
    prompt: str
    context_report: str
    context_source_summary: list[str]


Answerer = Callable[[OntologyQuestion, ProbeRuntime, ProbeContext], str]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _run_stamp(timestamp: str) -> str:
    return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d_%H%M%S")


def _split_markdown_table_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def parse_question_bank(project_root: Path) -> list[OntologyQuestion]:
    question_bank_path = project_root / QUESTION_BANK_RELATIVE_PATH
    records: list[OntologyQuestion] = []
    for line in question_bank_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| QO"):
            continue
        parts = _split_markdown_table_row(line)
        if len(parts) < 5 or not re.fullmatch(r"QO\d{2}", parts[0]):
            continue
        records.append(
            OntologyQuestion(
                qid=parts[0],
                question=parts[1],
                expected_query=parts[2],
                physical_query=parts[3],
                verdict=parts[4],
            )
        )
    return records


def select_qo_questions(project_root: Path, count: int = DEFAULT_QUESTION_COUNT) -> list[OntologyQuestion]:
    records = parse_question_bank(project_root)
    return records[:count]


def _sanitize_text(value: str, secrets: Sequence[str]) -> str:
    sanitized = value
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "[REDACTED]")
    return sanitized


def _jsonl_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(_jsonl_line(payload) + "\n")


def _context_source_summary(context_report: str) -> list[str]:
    sources: list[str] = []
    for line in context_report.splitlines():
        if "source=" in line or "source:" in line or "| source=" in line:
            sources.append(line.strip()[:240])
    return sources[:12]


def build_probe_context(
    project_root: Path,
    index_dir: Path,
    embedder: HashingEmbedder | SentenceTransformerEmbedder,
    question: OntologyQuestion,
    profile: str,
    top_k: int,
) -> ProbeContext:
    search_results = search_faiss_index(question.question, index_dir, embedder, top_k=top_k)
    facts = collect_fact_snippets(project_root, question.question, profile=profile)
    prompt = build_prompt(question.question, search_results, facts)
    context_report = build_context_report(question.question, search_results, facts)
    return ProbeContext(
        prompt=prompt,
        context_report=context_report,
        context_source_summary=_context_source_summary(context_report),
    )


def default_answerer(question: OntologyQuestion, runtime: ProbeRuntime, context: ProbeContext) -> str:
    return call_qwen_chat(
        prompt=context.prompt,
        llm_url=runtime.llm_url,
        model=runtime.model,
        api_key=runtime.api_key,
    )


def _response_row(
    question: OntologyQuestion,
    runtime: ProbeRuntime,
    context: ProbeContext,
    timestamp: str,
    latency_ms: int,
    status: str,
    answer: str = "",
    error_type: str = "",
    error_message: str = "",
    secrets: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "qid": question.qid,
        "question": question.question,
        "expected_query": question.expected_query,
        "model": runtime.model,
        "profile": runtime.profile,
        "status": status,
        "answer": _sanitize_text(answer, secrets),
        "context_report": _sanitize_text(context.context_report, secrets),
        "context_source_summary": [_sanitize_text(item, secrets) for item in context.context_source_summary],
        "latency_ms": latency_ms,
        "error_type": error_type,
        "error_message": _sanitize_text(error_message, secrets),
    }


def _failure_hint(error_type: str, error_message: str) -> str:
    lowered = f"{error_type} {error_message}".lower()
    if any(token in lowered for token in ["401", "authentication", "unauthorized", "invalid api key"]):
        return "API key 또는 인증 상태를 확인하세요."
    if any(token in lowered for token in ["403", "not have access", "permission", "model"]):
        return "모델 접근권한 문제일 수 있습니다. OPENAI_MODEL을 gpt-5.2 등 접근 가능한 모델로 바꿔 재시도하세요."
    if any(token in lowered for token in ["429", "rate limit", "quota"]):
        return "rate limit 또는 quota 문제일 수 있습니다. 잠시 후 재시도하거나 더 낮은 비용/권한 모델로 바꾸세요."
    return "API 오류 메시지와 모델 접근권한을 확인하세요."


def _summary_report(manifest: dict[str, Any], responses: list[dict[str, Any]], failures: list[dict[str, Any]]) -> str:
    success_count = sum(1 for response in responses if response["status"] == "ok")
    failure_count = len(failures)
    lines = [
        f"# Timestamp: {manifest['timestamp']}",
        "",
        "# GPT API Ontology Question Probe Summary",
        "",
        f"- model: `{manifest['model']}`",
        f"- profile: `{manifest['profile']}`",
        f"- selected_question_count: `{manifest['selected_question_count']}`",
        f"- smoke_test_status: `{manifest['smoke_test_status']}`",
        f"- batch_status: `{manifest['batch_status']}`",
        f"- success_count: `{success_count}`",
        f"- failure_count: `{failure_count}`",
        "",
        "## Full Answers",
        "",
    ]
    for response in responses:
        status = response["status"]
        question = response.get("question", "")
        answer = response.get("answer", "").strip() or "(empty answer)"
        lines.extend(
            [
                f"### {response['qid']} - {status}",
                "",
                f"**Question**: {question}",
                "",
                "**Answer**",
                "",
                answer,
                "",
            ]
        )
    if failures:
        lines.extend(["", "## Failures", ""])
        for failure in failures:
            lines.append(
                f"- `{failure['qid']}` {failure['error_type']}: "
                f"{failure.get('error_message', '')[:240]} "
                f"hint={failure.get('failure_hint', '')}"
            )
    return "\n".join(lines) + "\n"


def run_probe(
    project_root: Path,
    output_dir: Path | None = None,
    timestamp: str | None = None,
    question_count: int = DEFAULT_QUESTION_COUNT,
    answerer: Answerer = default_answerer,
    runtime: ProbeRuntime | None = None,
    index_dir: Path | None = None,
) -> Path:
    timestamp = timestamp or _now()
    output_root = output_dir or project_root / DEFAULT_OUTPUT_ROOT
    run_dir = output_root / f"run_{_run_stamp(timestamp)}_gpt_api_qo{question_count}"
    run_dir.mkdir(parents=True, exist_ok=True)

    questions = select_qo_questions(project_root, count=question_count)
    resolved_index_dir = index_dir or default_index_dir(project_root, profile=PROFILE_ONTOLOGY_HYBRID)
    if runtime is None:
        llm_settings = resolve_llm_runtime_settings(
            project_root=project_root,
            provider=LLM_PROVIDER_OPENAI,
            api_key_file=DEFAULT_OPENAI_API_KEY_FILE,
            api_key_env=DEFAULT_OPENAI_API_KEY_ENV,
        )
        runtime = ProbeRuntime(
            model=llm_settings.model,
            llm_url=llm_settings.llm_url,
            api_key=llm_settings.api_key,
            profile=PROFILE_ONTOLOGY_HYBRID,
            embedding_backend="auto",
            top_k=DEFAULT_TOP_K,
        )

    for path in ["questions.jsonl", "responses.jsonl", "failures.jsonl"]:
        (run_dir / path).write_text("", encoding="utf-8")
    for question in questions:
        _append_jsonl(run_dir / "questions.jsonl", {"timestamp": timestamp, **question.to_dict()})

    manifest: dict[str, Any] = {
        "timestamp": timestamp,
        "project_root": str(project_root),
        "model": runtime.model,
        "llm_url": runtime.llm_url,
        "profile": runtime.profile,
        "selected_question_count": len(questions),
        "question_range": f"{questions[0].qid}-{questions[-1].qid}" if questions else "",
        "smoke_test_status": "not_run",
        "batch_status": "not_started",
        "index_dir": str(resolved_index_dir),
        "embedding_backend": runtime.embedding_backend,
        "top_k": runtime.top_k,
        "api_key_source": str(DEFAULT_OPENAI_API_KEY_FILE),
        "api_key_present": bool(runtime.api_key),
    }

    responses: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    secrets = [runtime.api_key]

    if not questions:
        manifest["smoke_test_status"] = "failed"
        manifest["batch_status"] = "no_questions"
        _write_json(run_dir / "run_manifest.json", manifest)
        (run_dir / "summary_report.md").write_text(_summary_report(manifest, responses, failures), encoding="utf-8")
        return run_dir

    if answerer is default_answerer:
        if not runtime.api_key:
            manifest["smoke_test_status"] = "failed"
            manifest["batch_status"] = "missing_api_key"
            failure = {
                "timestamp": timestamp,
                "qid": questions[0].qid,
                "question": questions[0].question,
                "error_type": "MissingApiKey",
                "error_message": "OPENAI_API_KEY is empty.",
                "failure_hint": "config/openai_api_key.local의 OPENAI_API_KEY 값을 확인하세요.",
            }
            failures.append(failure)
            _append_jsonl(run_dir / "failures.jsonl", failure)
            _write_json(run_dir / "run_manifest.json", manifest)
            (run_dir / "summary_report.md").write_text(_summary_report(manifest, responses, failures), encoding="utf-8")
            return run_dir
        if not index_is_ready(resolved_index_dir):
            manifest["smoke_test_status"] = "failed"
            manifest["batch_status"] = "missing_index"
            failure = {
                "timestamp": timestamp,
                "qid": questions[0].qid,
                "question": questions[0].question,
                "error_type": "MissingRagIndex",
                "error_message": f"RAG index is not ready: {resolved_index_dir}",
                "failure_hint": "먼저 ontology-hybrid RAG index를 생성하세요.",
            }
            failures.append(failure)
            _append_jsonl(run_dir / "failures.jsonl", failure)
            _write_json(run_dir / "run_manifest.json", manifest)
            (run_dir / "summary_report.md").write_text(_summary_report(manifest, responses, failures), encoding="utf-8")
            return run_dir

    embedder = create_embedder_for_index(resolved_index_dir, backend=runtime.embedding_backend) if index_is_ready(resolved_index_dir) else HashingEmbedder()

    for index, question in enumerate(questions):
        started = time.monotonic()
        context = build_probe_context(
            project_root=project_root,
            index_dir=resolved_index_dir,
            embedder=embedder,
            question=question,
            profile=runtime.profile,
            top_k=runtime.top_k,
        )
        try:
            answer = answerer(question, runtime, context)
            latency_ms = int((time.monotonic() - started) * 1000)
            row = _response_row(
                question=question,
                runtime=runtime,
                context=context,
                timestamp=timestamp,
                latency_ms=latency_ms,
                status="ok",
                answer=answer,
                secrets=secrets,
            )
            responses.append(row)
            _append_jsonl(run_dir / "responses.jsonl", row)
            if index == 0:
                manifest["smoke_test_status"] = "passed"
                manifest["batch_status"] = "running"
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            error_type = type(exc).__name__
            error_message = _sanitize_text(str(exc), secrets)
            row = _response_row(
                question=question,
                runtime=runtime,
                context=context,
                timestamp=timestamp,
                latency_ms=latency_ms,
                status="error",
                error_type=error_type,
                error_message=error_message,
                secrets=secrets,
            )
            failure = {
                "timestamp": timestamp,
                "qid": question.qid,
                "question": question.question,
                "model": runtime.model,
                "error_type": error_type,
                "error_message": error_message,
                "failure_hint": _failure_hint(error_type, error_message),
            }
            responses.append(row)
            failures.append(failure)
            _append_jsonl(run_dir / "responses.jsonl", row)
            _append_jsonl(run_dir / "failures.jsonl", failure)
            if index == 0:
                manifest["smoke_test_status"] = "failed"
                manifest["batch_status"] = "stopped_after_smoke_failure"
                break

    if manifest["batch_status"] == "running":
        manifest["batch_status"] = "completed"
    manifest["success_count"] = sum(1 for response in responses if response["status"] == "ok")
    manifest["failure_count"] = len(failures)
    _write_json(run_dir / "run_manifest.json", manifest)
    (run_dir / "summary_report.md").write_text(_summary_report(manifest, responses, failures), encoding="utf-8")
    return run_dir


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run GPT API ontology-fit probes for Ttareungi QO questions.")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--question-count", type=int, default=DEFAULT_QUESTION_COUNT)
    parser.add_argument("--index-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    project_root = args.project_root or find_project_root(Path(__file__))
    run_dir = run_probe(
        project_root=project_root,
        output_dir=args.output_dir,
        timestamp=args.timestamp,
        question_count=args.question_count,
        index_dir=args.index_dir,
    )
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
