# Timestamp: 2026-05-11 13:43:00

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import io
import json
from pathlib import Path
import re
from statistics import median
import sys
import time
from typing import Any, Sequence


TOOLS_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_SCRIPTS_DIR))

from rag.ttareungi_rag import (  # noqa: E402
    DEFAULT_OPENAI_MODEL,
    PROFILE_DB_ONLY,
    build_context_report,
    build_rag_index,
    create_embedder_for_index,
    default_index_dir,
    find_project_root,
    index_is_ready,
    search_faiss_index,
)


TARGET_SOURCE_HIT_RATE = 0.93
WEAK_SOURCE_TYPES = {"procurement_doc", "signup", "service_doc"}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _expected_sources(row: dict[str, Any]) -> list[str]:
    sources = row.get("expected_sources", [])
    if isinstance(sources, str):
        return [source.strip() for source in sources.split("|") if source.strip()]
    return [str(source) for source in sources if str(source).strip()]


def _combined_source_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ["retrieved_sources", "context_source_summary"]:
        value = row.get(key, [])
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
    current_context = str(row.get("context_report", ""))
    if current_context:
        parts.append(current_context)
    if not row.get("retrieved_sources") and not current_context:
        for key in ["actual_answer", "answer"]:
            parts.append(str(row.get(key, "")))
    return "\n".join(parts)


def _source_hit(row: dict[str, Any]) -> bool:
    source_text = _combined_source_text(row)
    expected_sources = _expected_sources(row)
    return any(_source_matches(expected, source_text) for expected in expected_sources)


def _source_matches(expected: str, source_text: str) -> bool:
    expected = expected.strip()
    if not expected:
        return False
    pattern = rf"(?<![0-9A-Za-z가-힣_]){re.escape(expected)}(?![0-9A-Za-z가-힣_])"
    return re.search(pattern, source_text) is not None


def _source_mentions(row: dict[str, Any]) -> list[str]:
    mentions = row.get("retrieved_sources")
    if isinstance(mentions, list) and mentions:
        return [str(item) for item in mentions]
    text = _combined_source_text(row)
    expected = _expected_sources(row)
    return [source for source in expected if _source_matches(source, text)]


def _latency_summary(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    values = [int(row.get("latency_ms", 0)) for row in rows if isinstance(row.get("latency_ms", 0), int)]
    if not values:
        return {"min": 0, "avg": 0, "p50": 0, "p95": 0, "max": 0}
    sorted_values = sorted(values)
    p95_index = max(0, min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * 0.95))))
    return {
        "min": min(values),
        "avg": round(sum(values) / len(values)),
        "p50": int(median(values)),
        "p95": sorted_values[p95_index],
        "max": max(values),
    }


def _counts(values: Sequence[str]) -> dict[str, int]:
    counted: dict[str, int] = {}
    for value in values:
        counted[value] = counted.get(value, 0) + 1
    return dict(sorted(counted.items()))


def build_latest_feature_experiment_spec() -> dict[str, dict[str, Any]]:
    return {
        "structured_outputs": {
            "status": "planned",
            "purpose": "평가 응답을 JSON schema로 고정해 source_used, answerability, confidence, missing_evidence를 안정적으로 파싱한다.",
            "schema_name": "DbOnlyRagEvaluationResult",
            "schema_fields": ["source_used", "answerability", "confidence", "missing_evidence"],
            "fallback": "schema parse 실패 시 fallback text report를 저장한다.",
        },
        "graders": {
            "status": "planned",
            "purpose": "source hit, answer correctness, partial credit judge를 분리한다.",
            "score_range": "0.0~1.0",
            "baseline_metric": "local_source_hit",
        },
        "prompt_caching": {
            "status": "planned",
            "purpose": "고정 system prompt와 rubric prefix를 재사용해 반복 평가 latency/cost를 측정한다.",
            "record_fields": ["cached_tokens", "latency_ms_p50", "latency_ms_p95"],
            "default_model": DEFAULT_OPENAI_MODEL,
        },
        "file_search": {
            "status": "experimental_only",
            "purpose": "문서/brief 전용 hosted retrieval을 local FAISS와 병렬 비교한다.",
            "scope_guard": "대형 Parquet raw row 업로드 금지, docs/brief 파일만 사용",
            "compare_against": "local_faiss_db_only",
        },
    }


def _normalize_eval_row(row: dict[str, Any], timestamp: str) -> dict[str, Any]:
    normalized = dict(row)
    normalized.setdefault("timestamp", timestamp)
    normalized.setdefault("qid", normalized.get("id", ""))
    normalized.setdefault("status", "ok")
    normalized.setdefault("profile", PROFILE_DB_ONLY)
    normalized.setdefault("model", "context-only")
    normalized["expected_sources"] = _expected_sources(normalized)
    normalized["retrieved_sources"] = _source_mentions(normalized)
    normalized["source_hit"] = _source_hit(normalized)
    normalized["answerability_bucket"] = "source_found" if normalized["source_hit"] else "source_missing"
    return normalized


def _source_from_result_metadata(metadata: dict[str, Any]) -> str:
    for key in ["dataset_name", "doc_key", "dataset_id", "source"]:
        value = str(metadata.get(key, "")).strip()
        if value:
            return value
    return "unknown"


def run_context_only_retrieval(
    project_root: Path,
    rows: Sequence[dict[str, Any]],
    index_dir: Path | None = None,
    top_k: int = 5,
    embedding_backend: str = "auto",
    build_index: bool = False,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    resolved_index_dir = index_dir or default_index_dir(project_root, profile=PROFILE_DB_ONLY)
    if not index_is_ready(resolved_index_dir):
        if not build_index:
            raise FileNotFoundError(f"db-only index is not ready: {resolved_index_dir}")
        build_rag_index(
            project_root=project_root,
            index_dir=resolved_index_dir,
            embedding_backend=embedding_backend,
            profile=PROFILE_DB_ONLY,
        )
    embedder = create_embedder_for_index(resolved_index_dir, backend=embedding_backend)
    normalized_rows: list[dict[str, Any]] = []
    run_timestamp = timestamp or _now()
    for row in rows:
        start = time.perf_counter()
        results = search_faiss_index(str(row.get("question", "")), resolved_index_dir, embedder, top_k=top_k)
        latency_ms = round((time.perf_counter() - start) * 1000)
        retrieved_sources = [_source_from_result_metadata(result.document.metadata) for result in results]
        context_report = build_context_report(str(row.get("question", "")), results, [])
        normalized = dict(row)
        normalized.update(
            {
                "retrieved_sources": retrieved_sources,
                "context_report": context_report,
                "latency_ms": latency_ms,
                "status": "ok",
                "profile": PROFILE_DB_ONLY,
                "model": "context-only",
                "top_k": top_k,
            }
        )
        normalized_rows.append(_normalize_eval_row(normalized, run_timestamp))
    return normalized_rows


def summarize_rows(rows: Sequence[dict[str, Any]], timestamp: str | None = None) -> dict[str, Any]:
    normalized = [_normalize_eval_row(row, timestamp or _now()) for row in rows]
    row_count = len(normalized)
    source_hit_count = sum(1 for row in normalized if row.get("source_hit"))
    status_counts = _counts(str(row.get("status", "")) for row in normalized)
    question_type_counts = _counts(str(row.get("question_type", "")) for row in normalized)
    weak_question_types: dict[str, dict[str, Any]] = {}
    for question_type in sorted(WEAK_SOURCE_TYPES):
        typed_rows = [row for row in normalized if row.get("question_type") == question_type]
        if not typed_rows:
            continue
        hits = sum(1 for row in typed_rows if row.get("source_hit"))
        weak_question_types[question_type] = {
            "row_count": len(typed_rows),
            "source_hit_count": hits,
            "source_hit_rate": round(hits / len(typed_rows), 4),
        }
    source_hit_rate = round(source_hit_count / row_count, 4) if row_count else 0.0
    return {
        "timestamp": timestamp or _now(),
        "profile": PROFILE_DB_ONLY,
        "model": "context-only",
        "default_llm_model_for_future_judging": DEFAULT_OPENAI_MODEL,
        "row_count": row_count,
        "source_hit_count": source_hit_count,
        "source_hit_rate": source_hit_rate,
        "target_source_hit_rate": TARGET_SOURCE_HIT_RATE,
        "is_performance_success": source_hit_rate >= TARGET_SOURCE_HIT_RATE,
        "miss_count": row_count - source_hit_count,
        "status_counts": status_counts,
        "question_type_counts": question_type_counts,
        "weak_question_types": weak_question_types,
        "latency_ms": _latency_summary(normalized),
        "latest_feature_experiments": build_latest_feature_experiment_spec(),
    }


def _miss_rows(rows: Sequence[dict[str, Any]], timestamp: str) -> list[dict[str, Any]]:
    normalized = [_normalize_eval_row(row, timestamp) for row in rows]
    return [row for row in normalized if not row.get("source_hit")]


def _miss_cases_csv(rows: Sequence[dict[str, Any]], timestamp: str) -> str:
    fieldnames = ["qid", "question_type", "question", "expected_sources", "retrieved_sources", "status"]
    buffer = io.StringIO()
    buffer.write(f"# Timestamp: {timestamp}\n")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in _miss_rows(rows, timestamp):
        writer.writerow(
            {
                "qid": row.get("qid") or row.get("id", ""),
                "question_type": row.get("question_type", ""),
                "question": row.get("question", ""),
                "expected_sources": "|".join(_expected_sources(row)),
                "retrieved_sources": "|".join(_source_mentions(row)),
                "status": row.get("status", ""),
            }
        )
    return buffer.getvalue()


def _analysis_markdown(metrics: dict[str, Any]) -> str:
    weak = metrics["weak_question_types"]
    lines = [
        f"# Timestamp: {metrics['timestamp']}",
        "",
        "# DB-only RAG Performance Analysis",
        "",
        "## 결론",
        "",
        "- 이번 평가는 온톨로지 없는 `db-only` RAG의 source routing 성능을 보는 context-only 평가입니다.",
        f"- source_hit_rate: `{metrics['source_hit_rate']}` / target `{metrics['target_source_hit_rate']}`",
        f"- performance_success: `{metrics['is_performance_success']}`",
        "- QO 의미 질의는 이 지표의 정답률로 보지 않고, 온톨로지 없는 한계 진단으로 분리합니다.",
        "",
        "## 약점 Source",
        "",
    ]
    if weak:
        for question_type, payload in weak.items():
            lines.append(
                f"- `{question_type}`: {payload['source_hit_count']}/{payload['row_count']} "
                f"hit_rate=`{payload['source_hit_rate']}`"
            )
    else:
        lines.append("- 약점 source type 행이 없습니다.")
    lines.extend(
        [
            "",
            "## 최신 기능 실험 트랙",
            "",
            "- Structured Outputs: `source_used`, `answerability`, `confidence`, `missing_evidence` schema 고정.",
            "- Graders: source hit과 answer correctness를 0~1 점수로 분리.",
            "- Prompt Caching: 고정 prompt/rubric prefix의 cached_tokens와 latency p50/p95 기록.",
            "- File Search: docs/brief 전용 보조 검색으로만 실험하고 Parquet raw row는 올리지 않음.",
        ]
    )
    return "\n".join(lines) + "\n"


def _backlog_markdown(metrics: dict[str, Any]) -> str:
    lines = [
        f"# Timestamp: {metrics['timestamp']}",
        "",
        "# DB-only RAG Improvement Backlog",
        "",
        "- `P0` db-only index: `ttareungi_rag_index_db_only`를 정식 생성하고 manifest에 profile/model/top_k를 고정한다.",
        "- `P0` weak aliases: `newmeta.parquet`, `pricing_info`, `g2b_r26bk01319050_file1/file3` alias를 지속 보강한다.",
        "- `P0` source diversity: 같은 대형 Parquet brief 반복을 제한하고 운영 문서 source가 top-k에 들어오게 한다.",
        "- `P1` evaluator: Structured Outputs와 grader 기반 점수를 기존 source-hit 점수 옆에 저장한다.",
        "- `P1` file-search experiment: docs/brief만 hosted File Search에 올려 local FAISS와 hit rate를 비교한다.",
    ]
    return "\n".join(lines) + "\n"


def write_benchmark_outputs(
    eval_path: Path,
    output_dir: Path,
    project_root: Path | None = None,
    index_dir: Path | None = None,
    top_k: int = 5,
    embedding_backend: str = "auto",
    build_index: bool = False,
    timestamp: str | None = None,
) -> dict[str, Path]:
    run_timestamp = timestamp or _now()
    rows = _read_jsonl(eval_path)
    if project_root is not None:
        rows = run_context_only_retrieval(
            project_root=project_root,
            rows=rows,
            index_dir=index_dir,
            top_k=top_k,
            embedding_backend=embedding_backend,
            build_index=build_index,
            timestamp=run_timestamp,
        )
    else:
        rows = [_normalize_eval_row(row, run_timestamp) for row in rows]

    metrics = summarize_rows(rows, timestamp=run_timestamp)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "# Timestamp": run_timestamp,
        "profile": PROFILE_DB_ONLY,
        "model": "context-only",
        "default_llm_model_for_future_judging": DEFAULT_OPENAI_MODEL,
        "eval_path": str(eval_path),
        "index_dir": str(index_dir or default_index_dir(project_root, profile=PROFILE_DB_ONLY)) if project_root else "",
        "top_k": top_k,
        "embedding_backend": embedding_backend,
        "selected_question_count": len(rows),
        "target_source_hit_rate": TARGET_SOURCE_HIT_RATE,
    }

    paths = {
        "manifest": output_dir / "run_manifest.json",
        "responses": output_dir / "responses.jsonl",
        "metrics": output_dir / "db_only_rag_metrics.json",
        "report": output_dir / "db_only_rag_analysis.md",
        "miss_cases": output_dir / "source_miss_cases.csv",
        "backlog": output_dir / "retrieval_improvement_backlog.md",
        "latest_features": output_dir / "latest_feature_experiments.json",
    }
    _write_json(paths["manifest"], manifest)
    _write_jsonl(paths["responses"], rows)
    _write_json(paths["metrics"], metrics)
    paths["report"].write_text(_analysis_markdown(metrics), encoding="utf-8")
    paths["miss_cases"].write_text(_miss_cases_csv(rows, run_timestamp), encoding="utf-8")
    paths["backlog"].write_text(_backlog_markdown(metrics), encoding="utf-8")
    _write_json(paths["latest_features"], build_latest_feature_experiment_spec())
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or analyze a db-only Ttareung-i RAG source-routing benchmark.")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--eval-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--index-dir", type=Path, default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--embedding-backend", choices=["auto", "hashing", "sentence-transformers"], default="auto")
    parser.add_argument("--build-index", action="store_true")
    parser.add_argument("--timestamp", default=None)
    args = parser.parse_args(argv)

    project_root = args.project_root
    if project_root is None and (args.index_dir or args.build_index):
        project_root = find_project_root(Path(__file__))

    paths = write_benchmark_outputs(
        eval_path=args.eval_path,
        output_dir=args.output_dir,
        project_root=project_root,
        index_dir=args.index_dir,
        top_k=args.top_k,
        embedding_backend=args.embedding_backend,
        build_index=args.build_index,
        timestamp=args.timestamp,
    )
    print(f"# Timestamp: {args.timestamp or _now()}")
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
