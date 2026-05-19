# Timestamp: 2026-05-11 13:24:00

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import io
import json
from pathlib import Path
from statistics import median
import sys
from typing import Any, Sequence


TOOLS_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_SCRIPTS_DIR))

from rag.ttareungi_rag import DEFAULT_OPENAI_MODEL, find_project_root  # noqa: E402


KNOWN_SOURCES = [
    "ontology-lite",
    "branch_data.parquet",
    "rent_data.parquet",
    "count_data.parquet",
    "broken_data.parquet",
    "weather_data.parquet",
    "uselate_data.parquet",
    "newmeta.parquet",
]

INSUFFICIENT_TOKENS = [
    "특정할 수 없습니다",
    "확인할 수 없습니다",
    "산출할 수 없습니다",
    "직접 검증",
    "어렵습니다",
    "제공된 데이터만으로는",
    "현재 제공된 근거만으로는",
    "근거 부족",
]

GUARD_TOKENS = ["성능 가드", "row scan은 생략", "대용량 source", "전역 row scan"]


@dataclass(frozen=True)
class AnalysisResult:
    manifest: dict[str, Any]
    responses: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    metrics: dict[str, Any]
    matrix_rows: list[dict[str, Any]]
    backlog_items: list[dict[str, str]]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _combined_context(row: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(row.get("context_report", "")),
            "\n".join(str(item) for item in row.get("context_source_summary", []) or []),
        ]
    )


def _source_mentions(row: dict[str, Any]) -> list[str]:
    text = "\n".join([_combined_context(row), str(row.get("answer", ""))])
    return [source for source in KNOWN_SOURCES if source in text]


def _has_guard(row: dict[str, Any]) -> bool:
    text = _combined_context(row)
    return any(token in text for token in GUARD_TOKENS)


def _has_grounding(row: dict[str, Any]) -> bool:
    return bool(row.get("context_source_summary")) or bool(_source_mentions(row))


def classify_answerability(row: dict[str, Any]) -> str:
    if row.get("status") != "ok":
        return "error"
    answer = str(row.get("answer", ""))
    context = _combined_context(row)
    if "intent=unsupported" in context or "answerability=unanswerable" in context:
        return "unsupported"
    if any(token in answer for token in INSUFFICIENT_TOKENS):
        return "insufficient_but_grounded" if _has_grounding(row) else "unsupported"
    return "answered"


def _intent_group(qid: str) -> str:
    if not qid.startswith("QO"):
        return "baseline_or_other"
    try:
        number = int(qid[2:])
    except ValueError:
        return "baseline_or_other"
    if 1 <= number <= 10:
        return "weather_demand"
    if 11 <= number <= 20:
        return "station_role"
    if 21 <= number <= 30:
        return "bike_fault_lifecycle"
    if 41 <= number <= 50:
        return "provenance_confidence"
    return "ontology_other"


def _latency_summary(responses: list[dict[str, Any]]) -> dict[str, int]:
    values = [int(row["latency_ms"]) for row in responses if isinstance(row.get("latency_ms"), int)]
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


def _comparison_assessment(manifest: dict[str, Any], responses: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    profiles = {str(row.get("profile") or manifest.get("profile", "")) for row in responses}
    models = {str(row.get("model") or manifest.get("model", "")) for row in responses}
    if len(profiles) < 2:
        reasons.append("비교군이 없다")
    if manifest.get("model") != DEFAULT_OPENAI_MODEL:
        reasons.append(f"현재 실행 모델이 MVP 기본값({DEFAULT_OPENAI_MODEL})과 다르다")
    if not any(str(row.get("qid", "")).startswith("QP") for row in responses):
        reasons.append("DB-only baseline QP 질문이 없다")
    if not all(row.get("judge_rule") or row.get("expected_answer") for row in responses):
        reasons.append("정답 기준 judge rule이 없다")
    return {
        "is_valid_rag_performance_comparison": not reasons,
        "recommended_use": "diagnostic_answerability_probe" if reasons else "profile_performance_comparison",
        "profiles_seen": sorted(profile for profile in profiles if profile),
        "models_seen": sorted(model for model in models if model),
        "reasons": reasons,
    }


def _acceptance_slice(responses: list[dict[str, Any]]) -> dict[str, Any]:
    by_qid = {row.get("qid"): row for row in responses}
    slices = {
        "weather_demand": "QO01",
        "role_aware_flow": "QO11",
        "bike_fault_lifecycle": "QO21",
        "provenance_confidence": "QO44",
    }
    result: dict[str, Any] = {}
    for name, qid in slices.items():
        row = by_qid.get(qid)
        if not row:
            result[name] = {"qid": qid, "status": "missing"}
            continue
        result[name] = {
            "qid": qid,
            "status": row.get("status", ""),
            "answerability": classify_answerability(row),
            "guard_hit": _has_guard(row),
            "sources": _source_mentions(row),
        }
    return result


def _matrix_rows(manifest: dict[str, Any], responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for response in responses:
        sources = _source_mentions(response)
        rows.append(
            {
                "qid": response.get("qid", ""),
                "question": response.get("question", ""),
                "profile": response.get("profile") or manifest.get("profile", ""),
                "model": response.get("model") or manifest.get("model", ""),
                "top_k": manifest.get("top_k", ""),
                "status": response.get("status", ""),
                "latency_ms": response.get("latency_ms", ""),
                "answerability_bucket": classify_answerability(response),
                "guard_hit": str(_has_guard(response)).lower(),
                "intent_group": _intent_group(str(response.get("qid", ""))),
                "sources": "|".join(sources),
                "comparison_note": "missing_db_only_or_enhanced_profile",
            }
        )
    return rows


def _backlog_items(metrics: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "priority": "P0",
            "theme": "comparison harness",
            "item": f"Run QP baseline and QO probe with {DEFAULT_OPENAI_MODEL} across db-only, ontology-hybrid-current, ontology-hybrid-enhanced.",
        },
        {
            "priority": "P0",
            "theme": "weather-demand evidence",
            "item": "Add bounded weather_data + count_data evidence slices for QO01-QO10 instead of returning only large-scan guards.",
        },
        {
            "priority": "P0",
            "theme": "role-aware flow",
            "item": "Expose branchnum_r/rental_station and branchnum_b/return_station summaries for QO11-QO20.",
        },
        {
            "priority": "P0",
            "theme": "bike lifecycle",
            "item": "Expose rent_data.bikenum -> broken_data.bikenum time-window evidence for QO21-QO30.",
        },
        {
            "priority": "P1",
            "theme": "provenance slice",
            "item": "Include QO44-style provenance/confidence questions in the next formal acceptance run.",
        },
        {
            "priority": "P1",
            "theme": "reporting",
            "item": (
                "Separate answered, insufficient-but-grounded, unsupported, and error in reports; "
                f"current abstention rate is {metrics.get('abstention_rate', 0):.2f}."
            ),
        },
    ]


def analyze_probe_run(run_dir: Path, timestamp: str | None = None) -> AnalysisResult:
    manifest = _read_json(run_dir / "run_manifest.json")
    responses = _read_jsonl(run_dir / "responses.jsonl")
    failures = _read_jsonl(run_dir / "failures.jsonl")
    answerability_values = [classify_answerability(row) for row in responses]
    source_counts = {source: 0 for source in KNOWN_SOURCES}
    for row in responses:
        for source in _source_mentions(row):
            source_counts[source] += 1
    source_counts = {source: count for source, count in source_counts.items() if count}
    guard_hit_count = sum(1 for row in responses if _has_guard(row))
    response_count = len(responses)
    insufficient_count = sum(1 for value in answerability_values if value in {"insufficient_but_grounded", "unsupported"})
    metrics: dict[str, Any] = {
        "timestamp": timestamp or _now(),
        "run_dir": str(run_dir),
        "model": manifest.get("model", ""),
        "default_next_model": DEFAULT_OPENAI_MODEL,
        "profile": manifest.get("profile", ""),
        "top_k": manifest.get("top_k", ""),
        "embedding_backend": manifest.get("embedding_backend", ""),
        "question_range": manifest.get("question_range", ""),
        "response_count": response_count,
        "status_counts": _counts(str(row.get("status", "")) for row in responses),
        "answerability_counts": _counts(answerability_values),
        "abstention_count": insufficient_count,
        "abstention_rate": round(insufficient_count / response_count, 4) if response_count else 0.0,
        "guard_hit_count": guard_hit_count,
        "guard_hit_rate": round(guard_hit_count / response_count, 4) if response_count else 0.0,
        "latency_ms": _latency_summary(responses),
        "source_coverage_counts": source_counts,
        "intent_group_counts": _counts(_intent_group(str(row.get("qid", ""))) for row in responses),
        "comparison_assessment": _comparison_assessment(manifest, responses),
        "acceptance_slice": _acceptance_slice(responses),
    }
    matrix_rows = _matrix_rows(manifest, responses)
    backlog_items = _backlog_items(metrics)
    return AnalysisResult(
        manifest=manifest,
        responses=responses,
        failures=failures,
        metrics=metrics,
        matrix_rows=matrix_rows,
        backlog_items=backlog_items,
    )


def _report_markdown(result: AnalysisResult) -> str:
    metrics = result.metrics
    assessment = metrics["comparison_assessment"]
    answerability = metrics["answerability_counts"]
    lines = [
        f"# Timestamp: {metrics['timestamp']}",
        "",
        "# Ontology-RAG Performance Analysis",
        "",
        "## 결론",
        "",
        "- 현재 run은 API/runner end-to-end 검증 자료로는 유효합니다.",
        "- 성능 비교 근거로는 아직 부적절합니다.",
        f"- recommended_use: `{assessment['recommended_use']}`",
        f"- invalid_reasons: {', '.join(assessment['reasons']) or '없음'}",
        "",
        "## 핵심 지표",
        "",
        f"- model: `{metrics['model']}`",
        f"- next_default_model: `{metrics['default_next_model']}`",
        f"- profile: `{metrics['profile']}`",
        f"- responses: `{metrics['response_count']}`",
        f"- status_counts: `{metrics['status_counts']}`",
        f"- answerability_counts: `{answerability}`",
        f"- abstention_rate: `{metrics['abstention_rate']}`",
        f"- guard_hit_rate: `{metrics['guard_hit_rate']}`",
        f"- latency_ms: `{metrics['latency_ms']}`",
        f"- source_coverage_counts: `{metrics['source_coverage_counts']}`",
        "",
        "## Acceptance Slice",
        "",
    ]
    for name, payload in metrics["acceptance_slice"].items():
        lines.append(
            f"- {name}: qid=`{payload['qid']}`, status=`{payload['status']}`, "
            f"answerability=`{payload.get('answerability', '')}`, guard_hit=`{payload.get('guard_hit', '')}`"
        )
    lines.extend(
        [
            "",
            "## 해석",
            "",
            "- `success_count`는 API 응답 성공률이지 RAG 정답률이 아닙니다.",
            "- `insufficient_but_grounded`는 모델이 환각하지 않고 근거 부족을 보수적으로 말한 상태입니다.",
            "- 다음 비교 run은 `gpt-5.2`, 동일 `top_k`, 동일 질문셋으로 `db-only`와 `ontology-hybrid`를 나란히 실행해야 합니다.",
        ]
    )
    return "\n".join(lines) + "\n"


def _backlog_markdown(result: AnalysisResult) -> str:
    lines = [
        f"# Timestamp: {result.metrics['timestamp']}",
        "",
        "# Ontology-RAG Improvement Backlog",
        "",
    ]
    for item in result.backlog_items:
        lines.append(f"- `{item['priority']}` {item['theme']}: {item['item']}")
    return "\n".join(lines) + "\n"


def _comparison_matrix_csv(result: AnalysisResult) -> str:
    fieldnames = [
        "qid",
        "question",
        "profile",
        "model",
        "top_k",
        "status",
        "latency_ms",
        "answerability_bucket",
        "guard_hit",
        "intent_group",
        "sources",
        "comparison_note",
    ]
    buffer = io.StringIO()
    buffer.write(f"# Timestamp: {result.metrics['timestamp']}\n")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(result.matrix_rows)
    return buffer.getvalue()


def write_analysis_outputs(
    run_dir: Path,
    output_dir: Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Path]:
    result = analyze_probe_run(run_dir, timestamp=timestamp)
    target_dir = output_dir or run_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = target_dir / "rag_performance_metrics.json"
    report_path = target_dir / "rag_performance_analysis.md"
    matrix_path = target_dir / "comparison_matrix.csv"
    backlog_path = target_dir / "improvement_backlog.md"
    _write_json(metrics_path, result.metrics)
    report_path.write_text(_report_markdown(result), encoding="utf-8")
    matrix_path.write_text(_comparison_matrix_csv(result), encoding="utf-8")
    backlog_path.write_text(_backlog_markdown(result), encoding="utf-8")
    return {
        "metrics": metrics_path,
        "report": report_path,
        "matrix": matrix_path,
        "backlog": backlog_path,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze ontology RAG probe responses and write performance reports.")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    args = parser.parse_args(argv)
    project_root = find_project_root(Path(__file__))
    run_dir = args.run_dir if args.run_dir.is_absolute() else project_root / args.run_dir
    output_dir = args.output_dir
    if output_dir is not None and not output_dir.is_absolute():
        output_dir = project_root / output_dir
    paths = write_analysis_outputs(run_dir=run_dir, output_dir=output_dir, timestamp=args.timestamp)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
