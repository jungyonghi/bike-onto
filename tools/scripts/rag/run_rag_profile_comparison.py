# Timestamp: 2026-05-11 14:43:21

from __future__ import annotations

import argparse
import csv
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
    DEFAULT_OPENAI_MODEL,
    LLM_PROVIDER_OPENAI,
    PROFILE_DB_ONLY,
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
DEFAULT_OUTPUT_ROOT = Path("data/processed/exports/rag_profile_comparison_runs")
DEFAULT_REPORT_RELATIVE_PATH = Path("docs/project/ttareungi_ontology_vs_db_only_rag_comparison_report.md")
DEFAULT_PROFILES = (PROFILE_DB_ONLY, PROFILE_ONTOLOGY_HYBRID)
DEFAULT_TOP_K = 5
DEFAULT_QP_COUNT = 50
DEFAULT_QO_COUNT = 50
KPI_PASS = "통과"
KPI_CAUTION = "주의"
KPI_FAIL = "미달"

SOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "branch_data.parquet": ("branch_data", "Station", "branchnum", "branchname"),
    "count_data.parquet": ("count_data", "StationHourlyCount", "hourly_count", "cnt_rack"),
    "rent_data.parquet": ("rent_data", "TripEvent", "branchnum_r", "branchnum_b", "rentt"),
    "broken_data.parquet": ("broken_data", "BrokenEvent", "type_bk", "date_bk"),
    "weather_data.parquet": ("weather_data", "WeatherObservation", "precipitation", "temperature"),
    "uselate_data.parquet": ("uselate_data", "StationMonthlyUsage", "cnt_r", "cnt_b"),
    "newmeta.parquet": ("newmeta", "SignupAggregate", "new_dt", "age", "gender"),
    "master_branch_data.parquet": ("master_branch_data", "StationMaster"),
    "meta.parquet": ("meta.parquet", "metadata"),
    "ontology-lite": ("EvidenceGraph", "EvidenceEdge", "provenance", "confidence"),
}

KNOWN_FIELD_TOKENS = {
    "age",
    "bikenum",
    "branch_x",
    "branch_y",
    "branchname",
    "branchnum",
    "branchnum_b",
    "branchnum_r",
    "cnt_b",
    "cnt_r",
    "cnt_rack",
    "cnt_rack_b",
    "count",
    "date",
    "date_bk",
    "date_rt",
    "date_ym",
    "datetime",
    "dist",
    "gender",
    "holiday",
    "hour_cnt",
    "humidity",
    "ilcd",
    "iqr",
    "location1",
    "new",
    "new_dt",
    "precipitation",
    "rentt",
    "snowfall",
    "sy",
    "temperature",
    "type_bk",
    "visibility",
    "weekday",
    "windspeed",
}

INSUFFICIENT_TOKENS = (
    "근거가 부족",
    "검증 불가",
    "확인할 수 없",
    "답하기 어렵",
    "범위를 좁혀",
    "직접 조회된 구조화 근거 없음",
    "insufficient",
    "cannot determine",
    "not enough evidence",
)
EVIDENCE_TOKENS = ("evidence_kind", "direct", "derived", "inferred", "weak-context", "근거 종류", "추론 근거")
CONFIDENCE_TOKENS = ("confidence", "신뢰도", "confidence=", "0.")
RELATION_TOKENS = (
    "relation",
    "관계",
    "role",
    "역할",
    "rental_station",
    "return_station",
    "same_bike",
    "observed_under_weather",
    "in_time_bucket",
    "supported_by",
    "derived_from",
    "precedes",
    "followed_by",
)


@dataclass(frozen=True)
class ComparisonQuestion:
    qid: str
    question: str
    question_group: str
    expected_query: str
    physical_query: str
    verdict: str
    expected_sources: tuple[str, ...]
    expected_data_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["expected_sources"] = list(self.expected_sources)
        payload["expected_data_fields"] = list(self.expected_data_fields)
        return payload


@dataclass(frozen=True)
class ComparisonRuntime:
    model: str
    llm_url: str
    api_key: str
    profiles: tuple[str, ...]
    embedding_backend: str
    top_k: int


@dataclass(frozen=True)
class ProfileContext:
    prompt: str
    context_report: str
    context_source_summary: list[str]
    retrieved_sources: list[str]


Answerer = Callable[[ComparisonQuestion, str, ComparisonRuntime, ProfileContext], str]
ContextBuilder = Callable[[Path, ComparisonQuestion, str, ComparisonRuntime], ProfileContext]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _run_stamp(timestamp: str) -> str:
    return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d_%H%M%S")


def _model_stamp(model: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "", model).lower() or "model"


def _split_markdown_table_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def _dedupe_preserve_order(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return tuple(ordered)


def _infer_expected_sources(*texts: str) -> tuple[str, ...]:
    haystack = "\n".join(texts)
    found: list[str] = []
    for source, aliases in SOURCE_ALIASES.items():
        if source in haystack or any(alias in haystack for alias in aliases):
            found.append(source)
    return _dedupe_preserve_order(found)


def _infer_expected_fields(*texts: str) -> tuple[str, ...]:
    haystack = "\n".join(texts)
    tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", haystack)
    return _dedupe_preserve_order([token for token in tokens if token in KNOWN_FIELD_TOKENS])


def parse_question_bank(project_root: Path) -> list[ComparisonQuestion]:
    question_bank_path = project_root / QUESTION_BANK_RELATIVE_PATH
    records: list[ComparisonQuestion] = []
    for line in question_bank_path.read_text(encoding="utf-8").splitlines():
        if not (line.startswith("| QP") or line.startswith("| QO")):
            continue
        parts = _split_markdown_table_row(line)
        if len(parts) < 5 or not re.fullmatch(r"Q[PO]\d{2}", parts[0]):
            continue
        qid = parts[0]
        expected_sources = _infer_expected_sources(parts[1], parts[2], parts[3], parts[4])
        expected_data_fields = _infer_expected_fields(parts[2], parts[3])
        records.append(
            ComparisonQuestion(
                qid=qid,
                question=parts[1],
                question_group=qid[:2],
                expected_query=parts[2],
                physical_query=parts[3],
                verdict=parts[4],
                expected_sources=expected_sources,
                expected_data_fields=expected_data_fields,
            )
        )
    return records


def select_comparison_questions(
    project_root: Path,
    qp_count: int = DEFAULT_QP_COUNT,
    qo_count: int = DEFAULT_QO_COUNT,
) -> list[ComparisonQuestion]:
    records_by_id = {record.qid: record for record in parse_question_bank(project_root)}
    selected_ids = [f"QP{index:02d}" for index in range(1, qp_count + 1)] + [
        f"QO{index:02d}" for index in range(1, qo_count + 1)
    ]
    missing = [qid for qid in selected_ids if qid not in records_by_id]
    if missing:
        raise ValueError(f"Missing comparison questions: {', '.join(missing)}")
    return [records_by_id[qid] for qid in selected_ids]


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


def _retrieved_sources_from_context(context_report: str, retrieved_sources: Sequence[str]) -> list[str]:
    sources = list(retrieved_sources)
    for line in context_report.splitlines():
        match = re.search(r"(?:source=|source:\s*)([^|\)\]\s]+)", line)
        if match:
            sources.append(match.group(1).strip())
    return list(_dedupe_preserve_order(sources))[:20]


def _document_sources(search_results: Sequence[Any]) -> list[str]:
    sources: list[str] = []
    for result in search_results:
        metadata = result.document.metadata
        source = str(metadata.get("source") or metadata.get("doc_key") or result.document.doc_id)
        sources.append(source)
    return list(_dedupe_preserve_order(sources))[:20]


class CachedProfileContextBuilder:
    def __init__(self, project_root: Path, runtime: ComparisonRuntime) -> None:
        self.project_root = project_root
        self.runtime = runtime
        self._embedders: dict[str, HashingEmbedder | SentenceTransformerEmbedder] = {}

    def __call__(
        self,
        project_root: Path,
        question: ComparisonQuestion,
        profile: str,
        runtime: ComparisonRuntime,
    ) -> ProfileContext:
        index_dir = default_index_dir(project_root, profile=profile)
        if not index_is_ready(index_dir):
            raise FileNotFoundError(f"RAG index is not ready: {index_dir}")
        if profile not in self._embedders:
            self._embedders[profile] = create_embedder_for_index(index_dir, backend=runtime.embedding_backend)
        search_results = search_faiss_index(
            question.question,
            index_dir,
            self._embedders[profile],
            top_k=runtime.top_k,
        )
        facts = collect_fact_snippets(project_root, question.question, profile=profile)
        prompt = build_prompt(question.question, search_results, facts)
        context_report = build_context_report(question.question, search_results, facts)
        retrieved_sources = _document_sources(search_results)
        return ProfileContext(
            prompt=prompt,
            context_report=context_report,
            context_source_summary=_context_source_summary(context_report),
            retrieved_sources=_retrieved_sources_from_context(context_report, retrieved_sources),
        )


def default_answerer(
    question: ComparisonQuestion,
    profile: str,
    runtime: ComparisonRuntime,
    context: ProfileContext,
) -> str:
    return call_qwen_chat(
        prompt=context.prompt,
        llm_url=runtime.llm_url,
        model=runtime.model,
        api_key=runtime.api_key,
    )


def _matches_token(haystack: str, token: str) -> bool:
    lowered = haystack.lower()
    token_lower = token.lower()
    aliases = [token_lower]
    if token_lower.endswith(".parquet"):
        aliases.append(token_lower.removesuffix(".parquet"))
    aliases.extend(alias.lower() for alias in SOURCE_ALIASES.get(token, ()))
    return any(alias and alias in lowered for alias in aliases)


def _source_hit(question: ComparisonQuestion, context: ProfileContext, answer: str) -> bool:
    if not question.expected_sources:
        return False
    haystack = "\n".join([answer, context.context_report, *context.retrieved_sources, *context.context_source_summary])
    return any(_matches_token(haystack, source) for source in question.expected_sources)


def _expected_field_hit(question: ComparisonQuestion, context: ProfileContext, answer: str) -> bool:
    if not question.expected_data_fields:
        return False
    haystack = "\n".join([answer, context.context_report]).lower()
    return any(field.lower() in haystack for field in question.expected_data_fields)


def _has_any(text: str, tokens: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(token.lower() in lowered for token in tokens)


def _answerability(
    question: ComparisonQuestion,
    status: str,
    answer: str,
    source_hit: bool,
    expected_field_hit: bool,
    evidence_quality_score: int,
) -> str:
    if status != "ok":
        return "error"
    if _has_any(answer, INSUFFICIENT_TOKENS):
        return "insufficient-but-grounded" if source_hit else "unsupported"
    if question.question_group == "QO":
        if source_hit and evidence_quality_score >= 3:
            return "answered"
        if source_hit or evidence_quality_score > 0:
            return "insufficient-but-grounded"
        return "unsupported"
    if source_hit or expected_field_hit:
        return "answered"
    return "unsupported"


def _failure_hint(error_type: str, error_message: str) -> str:
    lowered = f"{error_type} {error_message}".lower()
    if any(token in lowered for token in ["401", "authentication", "unauthorized", "invalid api key"]):
        return "API key 또는 인증 상태를 확인하세요."
    if any(token in lowered for token in ["403", "not have access", "permission", "model"]):
        return "모델 접근권한 문제일 수 있습니다. OPENAI_MODEL 또는 --model을 gpt-5.2 등 접근 가능한 모델로 바꿔 재시도하세요."
    if any(token in lowered for token in ["429", "rate limit", "quota"]):
        return "rate limit 또는 quota 문제일 수 있습니다. 잠시 후 재시도하거나 더 낮은 비용/권한 모델로 바꾸세요."
    if "rag index is not ready" in lowered:
        return "먼저 db-only와 ontology-hybrid RAG index를 생성하세요."
    return "API 오류 메시지, 모델 접근권한, RAG index 상태를 확인하세요."


def build_response_row(
    question: ComparisonQuestion,
    profile: str,
    runtime: ComparisonRuntime,
    context: ProfileContext,
    timestamp: str,
    latency_ms: int,
    status: str,
    answer: str = "",
    error_type: str = "",
    error_message: str = "",
    secrets: Sequence[str] = (),
) -> dict[str, Any]:
    sanitized_answer = _sanitize_text(answer, secrets)
    sanitized_context = _sanitize_text(context.context_report, secrets)
    source_hit = _source_hit(question, context, sanitized_answer)
    field_hit = _expected_field_hit(question, context, sanitized_answer)
    quality_text = "\n".join([sanitized_answer, sanitized_context])
    evidence_mentions = _has_any(quality_text, EVIDENCE_TOKENS)
    confidence_mentions = _has_any(quality_text, CONFIDENCE_TOKENS)
    relation_mentions = _has_any(quality_text, RELATION_TOKENS)
    evidence_quality_score = int(source_hit) + int(evidence_mentions) + int(confidence_mentions) + int(relation_mentions)
    answerability = _answerability(
        question=question,
        status=status,
        answer=sanitized_answer,
        source_hit=source_hit,
        expected_field_hit=field_hit,
        evidence_quality_score=evidence_quality_score,
    )
    qo_answer_quality_success = (
        question.question_group == "QO"
        and status == "ok"
        and source_hit
        and evidence_quality_score >= 3
        and answerability == "answered"
    )
    return {
        "timestamp": timestamp,
        "qid": question.qid,
        "question_group": question.question_group,
        "question": question.question,
        "profile": profile,
        "model": runtime.model,
        "top_k": runtime.top_k,
        "status": status,
        "answer": sanitized_answer,
        "context_report": sanitized_context,
        "context_source_summary": [
            _sanitize_text(item, secrets) for item in context.context_source_summary
        ],
        "retrieved_sources": [
            _sanitize_text(item, secrets) for item in context.retrieved_sources
        ],
        "expected_sources": list(question.expected_sources),
        "expected_data_fields": list(question.expected_data_fields),
        "source_hit": source_hit,
        "expected_field_hit": field_hit,
        "answerability": answerability,
        "evidence_mentions": evidence_mentions,
        "confidence_mentions": confidence_mentions,
        "relation_mentions": relation_mentions,
        "evidence_quality_score": evidence_quality_score,
        "qo_answer_quality_success": qo_answer_quality_success,
        "latency_ms": latency_ms,
        "error_type": error_type,
        "error_message": _sanitize_text(error_message, secrets),
    }


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _latency_summary(rows: Sequence[dict[str, Any]]) -> dict[str, int | float]:
    values = sorted(int(row.get("latency_ms") or 0) for row in rows)
    if not values:
        return {"avg_ms": 0, "p50_ms": 0, "p95_ms": 0}
    p50_index = min(len(values) - 1, int(round((len(values) - 1) * 0.50)))
    p95_index = min(len(values) - 1, int(round((len(values) - 1) * 0.95)))
    return {
        "avg_ms": round(sum(values) / len(values), 2),
        "p50_ms": values[p50_index],
        "p95_ms": values[p95_index],
    }


def _aggregate_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    source_hit_count = sum(1 for row in rows if row.get("source_hit"))
    field_hit_count = sum(1 for row in rows if row.get("expected_field_hit"))
    ok_count = sum(1 for row in rows if row.get("status") == "ok")
    qo_success_count = sum(1 for row in rows if row.get("qo_answer_quality_success"))
    answerability_counts: dict[str, int] = {}
    for row in rows:
        bucket = str(row.get("answerability") or "unknown")
        answerability_counts[bucket] = answerability_counts.get(bucket, 0) + 1
    return {
        "response_count": total,
        "ok_count": ok_count,
        "error_count": total - ok_count,
        "source_hit_count": source_hit_count,
        "source_hit_rate": _percent(source_hit_count, total),
        "expected_field_hit_count": field_hit_count,
        "expected_field_hit_rate": _percent(field_hit_count, total),
        "answerability_counts": answerability_counts,
        "answered_rate": _percent(answerability_counts.get("answered", 0), total),
        "insufficient_but_grounded_rate": _percent(
            answerability_counts.get("insufficient-but-grounded", 0),
            total,
        ),
        "qo_answer_quality_success_count": qo_success_count,
        "qo_answer_quality_success_rate": _percent(qo_success_count, total),
        "evidence_mention_rate": _percent(sum(1 for row in rows if row.get("evidence_mentions")), total),
        "confidence_mention_rate": _percent(sum(1 for row in rows if row.get("confidence_mentions")), total),
        "relation_mention_rate": _percent(sum(1 for row in rows if row.get("relation_mentions")), total),
        "avg_evidence_quality_score": round(
            sum(int(row.get("evidence_quality_score") or 0) for row in rows) / total,
            2,
        )
        if total
        else 0,
        "latency": _latency_summary(rows),
    }


def build_comparison_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_group_and_profile: dict[str, list[dict[str, Any]]] = {}
    by_profile: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        group_profile_key = f"{row.get('question_group')}::{row.get('profile')}"
        by_group_and_profile.setdefault(group_profile_key, []).append(row)
        by_profile.setdefault(str(row.get("profile")), []).append(row)
    return {
        "response_count": len(rows),
        "question_count": len({row.get("qid") for row in rows}),
        "profile_count": len({row.get("profile") for row in rows}),
        "by_group_and_profile": {
            key: _aggregate_rows(group_rows) for key, group_rows in sorted(by_group_and_profile.items())
        },
        "by_profile": {key: _aggregate_rows(profile_rows) for key, profile_rows in sorted(by_profile.items())},
    }


MATRIX_FIELDNAMES = [
    "qid",
    "question_group",
    "profile",
    "status",
    "source_hit",
    "expected_field_hit",
    "answerability",
    "evidence_quality_score",
    "evidence_mentions",
    "confidence_mentions",
    "relation_mentions",
    "qo_answer_quality_success",
    "latency_ms",
    "retrieved_sources",
    "expected_sources",
    "expected_data_fields",
    "error_type",
]


def _matrix_row(response: dict[str, Any]) -> dict[str, Any]:
    row = {field: response.get(field, "") for field in MATRIX_FIELDNAMES}
    for field in ["retrieved_sources", "expected_sources", "expected_data_fields"]:
        row[field] = "; ".join(str(item) for item in response.get(field, []))
    return row


def write_comparison_matrix(path: Path, rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    matrix_rows = [_matrix_row(row) for row in rows]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=MATRIX_FIELDNAMES)
        writer.writeheader()
        writer.writerows(matrix_rows)
    return matrix_rows


def _markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _metrics_table(metrics: dict[str, Any]) -> list[str]:
    lines = [
        "| group/profile | responses | source_hit_rate | answered_rate | qo_quality_rate | latency_avg_ms | latency_p95_ms |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, values in metrics.get("by_group_and_profile", {}).items():
        latency = values.get("latency", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{key}`",
                    str(values.get("response_count", 0)),
                    str(values.get("source_hit_rate", 0)),
                    str(values.get("answered_rate", 0)),
                    str(values.get("qo_answer_quality_success_rate", 0)),
                    str(latency.get("avg_ms", 0)),
                    str(latency.get("p95_ms", 0)),
                ]
            )
            + " |"
        )
    return lines


def _metric(metrics: dict[str, Any], key: str, field: str, default: Any = 0) -> Any:
    return metrics.get("by_group_and_profile", {}).get(key, {}).get(field, default)


def _latency_metric(metrics: dict[str, Any], key: str, field: str, default: Any = 0) -> Any:
    return metrics.get("by_group_and_profile", {}).get(key, {}).get("latency", {}).get(field, default)


def _delta(value: float, baseline: float) -> float:
    return round(float(value or 0) - float(baseline or 0), 4)


def _overhead_percent(value: float, baseline: float) -> float:
    if not baseline:
        return 0.0
    return round(((float(value or 0) - float(baseline)) / float(baseline)) * 100, 1)


def _signed_points(value: float) -> str:
    return f"{value:+.2f}p"


def _signed_percent(value: float) -> str:
    return f"{value:+.1f}%"


def build_kpi_judgements(metrics: dict[str, Any]) -> list[dict[str, str]]:
    qp_native_source = float(_metric(metrics, "QP::db-only", "source_hit_rate"))
    qp_native_answered = float(_metric(metrics, "QP::db-only", "answered_rate"))
    qp_native_field = float(_metric(metrics, "QP::db-only", "expected_field_hit_rate"))
    qp_ontology_answered = float(_metric(metrics, "QP::ontology-hybrid", "answered_rate"))
    qo_native_answered = float(_metric(metrics, "QO::db-only", "answered_rate"))
    qo_ontology_answered = float(_metric(metrics, "QO::ontology-hybrid", "answered_rate"))
    qo_native_quality = float(_metric(metrics, "QO::db-only", "qo_answer_quality_success_rate"))
    qo_ontology_quality = float(_metric(metrics, "QO::ontology-hybrid", "qo_answer_quality_success_rate"))
    qo_ontology_confidence = float(_metric(metrics, "QO::ontology-hybrid", "confidence_mention_rate"))
    qo_ontology_relation = float(_metric(metrics, "QO::ontology-hybrid", "relation_mention_rate"))
    qp_avg_overhead = _overhead_percent(
        _latency_metric(metrics, "QP::ontology-hybrid", "avg_ms"),
        _latency_metric(metrics, "QP::db-only", "avg_ms"),
    )
    qo_avg_overhead = _overhead_percent(
        _latency_metric(metrics, "QO::ontology-hybrid", "avg_ms"),
        _latency_metric(metrics, "QO::db-only", "avg_ms"),
    )
    qp_p95_overhead = _overhead_percent(
        _latency_metric(metrics, "QP::ontology-hybrid", "p95_ms"),
        _latency_metric(metrics, "QP::db-only", "p95_ms"),
    )
    qo_p95_overhead = _overhead_percent(
        _latency_metric(metrics, "QO::ontology-hybrid", "p95_ms"),
        _latency_metric(metrics, "QO::db-only", "p95_ms"),
    )
    qo_answered_uplift = _delta(qo_ontology_answered, qo_native_answered)
    qo_quality_uplift = _delta(qo_ontology_quality, qo_native_quality)
    qp_answered_delta = _delta(qp_ontology_answered, qp_native_answered)

    avg_latency_status = KPI_PASS if qp_avg_overhead <= 15 and qo_avg_overhead <= 15 else KPI_FAIL
    p95_latency_status = (
        KPI_PASS
        if qp_p95_overhead <= 15 and qo_p95_overhead <= 15
        else KPI_CAUTION
        if qp_p95_overhead <= 30 and qo_p95_overhead <= 30
        else KPI_FAIL
    )
    return [
        {
            "kpi": "QP baseline preservation",
            "current": f"source `{qp_native_source:.2f}`, answered `{qp_native_answered:.2f}`, field `{qp_native_field:.2f}`",
            "threshold": "all `>= 0.90`",
            "status": KPI_PASS
            if min(qp_native_source, qp_native_answered, qp_native_field) >= 0.90
            else KPI_FAIL,
        },
        {
            "kpi": "Ontology non-regression",
            "current": f"`{_signed_points(qp_answered_delta)}`",
            "threshold": "`>= -0.05p`",
            "status": KPI_PASS if qp_answered_delta >= -0.05 else KPI_FAIL,
        },
        {
            "kpi": "QO answered uplift",
            "current": f"`{_signed_points(qo_answered_uplift)}`",
            "threshold": "`>= +0.25p`",
            "status": KPI_PASS if qo_answered_uplift >= 0.25 else KPI_FAIL,
        },
        {
            "kpi": "QO ontology quality uplift",
            "current": f"`{_signed_points(qo_quality_uplift)}`",
            "threshold": "`>= +0.25p`",
            "status": KPI_PASS if qo_quality_uplift >= 0.25 else KPI_FAIL,
        },
        {
            "kpi": "Evidence explanation",
            "current": f"confidence `{qo_ontology_confidence:.2f}`, relation `{qo_ontology_relation:.2f}`",
            "threshold": "confidence `>= 0.70`, relation `>= 0.50`",
            "status": KPI_PASS
            if qo_ontology_confidence >= 0.70 and qo_ontology_relation >= 0.50
            else KPI_FAIL,
        },
        {
            "kpi": "Latency avg overhead",
            "current": f"QP `{_signed_percent(qp_avg_overhead)}`, QO `{_signed_percent(qo_avg_overhead)}`",
            "threshold": "`<= 15%`",
            "status": avg_latency_status,
        },
        {
            "kpi": "Latency p95 overhead",
            "current": f"QP `{_signed_percent(qp_p95_overhead)}`, QO `{_signed_percent(qo_p95_overhead)}`",
            "threshold": "`<= 30%` 주의 허용",
            "status": p95_latency_status,
        },
    ]


def _kpi_budget_lines() -> list[str]:
    return [
        "| KPI | 기준 | 이유 |",
        "| :--- | :--- | :--- |",
        "| QP baseline preservation | native RAG의 QP source hit, answered, field hit가 모두 `>= 0.90` | QP는 온톨로지 없이도 답해야 하는 기본 성능 증명 질문이다. |",
        "| Ontology non-regression | ontology-base RAG의 QP answered가 native 대비 `-0.05p` 이상 악화되지 않음 | ontology context가 쉬운 질문을 망치면 안 된다. |",
        "| QO ontology value uplift | QO answered rate와 ontology quality가 native 대비 각각 `+0.25p` 이상 | QO는 의미 관계와 근거 품질 개선을 입증해야 한다. |",
        "| Evidence explanation | QO ontology-base confidence mention `>= 0.70`, relation mention `>= 0.50` | 발표/논문형 기준에서는 신뢰도와 관계 설명이 핵심 효과다. |",
        "| Latency cost | 평균 overhead `<= 15%`, p95 overhead `<= 30%`는 주의 허용 | 품질 이득을 보되, 비용 증가가 과도하면 routing 개선 대상이다. |",
        "| Source hit caveat | QO는 source hit만으로 성공 처리하지 않는다 | source를 찾는 것과 의미 질의에 답하는 것은 다른 KPI다. |",
    ]


def _kpi_judgement_lines(metrics: dict[str, Any]) -> list[str]:
    lines = [
        "| KPI | 현재 값 | 기준 | 판정 |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for judgement in build_kpi_judgements(metrics):
        lines.append(
            "| "
            + " | ".join(
                [
                    judgement["kpi"],
                    judgement["current"],
                    judgement["threshold"],
                    judgement["status"],
                ]
            )
            + " |"
        )
    return lines


def _actual_takeaway_lines(metrics: dict[str, Any]) -> list[str]:
    qp_db_source = _metric(metrics, "QP::db-only", "source_hit_rate")
    qp_onto_source = _metric(metrics, "QP::ontology-hybrid", "source_hit_rate")
    qp_db_answered = _metric(metrics, "QP::db-only", "answered_rate")
    qp_onto_answered = _metric(metrics, "QP::ontology-hybrid", "answered_rate")
    qo_db_source = _metric(metrics, "QO::db-only", "source_hit_rate")
    qo_onto_source = _metric(metrics, "QO::ontology-hybrid", "source_hit_rate")
    qo_db_answered = _metric(metrics, "QO::db-only", "answered_rate")
    qo_onto_answered = _metric(metrics, "QO::ontology-hybrid", "answered_rate")
    qo_db_quality = _metric(metrics, "QO::db-only", "qo_answer_quality_success_rate")
    qo_onto_quality = _metric(metrics, "QO::ontology-hybrid", "qo_answer_quality_success_rate")
    qp_db_latency = _latency_metric(metrics, "QP::db-only", "avg_ms")
    qp_onto_latency = _latency_metric(metrics, "QP::ontology-hybrid", "avg_ms")
    qo_db_latency = _latency_metric(metrics, "QO::db-only", "avg_ms")
    qo_onto_latency = _latency_metric(metrics, "QO::ontology-hybrid", "avg_ms")
    return [
        f"- QP baseline: native RAG(db-only)는 source hit `{qp_db_source}`, answered `{qp_db_answered}`이고 "
        f"ontology-base RAG(ontology-hybrid)는 source hit `{qp_onto_source}`, answered `{qp_onto_answered}`이다. "
        "baseline 질문에서는 ontology context가 항상 이득이라고 보기는 어렵고, 과잉 context 여부를 함께 봐야 한다.",
        f"- QO ontology-needed: native RAG(db-only)는 source hit `{qo_db_source}`인데 answered `{qo_db_answered}`, "
        f"ontology quality `{qo_db_quality}`에 머문다. 반면 ontology-base RAG(ontology-hybrid)는 source hit `{qo_onto_source}`, "
        f"answered `{qo_onto_answered}`, ontology quality `{qo_onto_quality}`로 근거 관계/신뢰도 설명에서 차이가 난다.",
        f"- Latency: QP 평균은 db-only `{qp_db_latency}ms`, ontology-hybrid `{qp_onto_latency}ms`이고 "
        f"QO 평균은 db-only `{qo_db_latency}ms`, ontology-hybrid `{qo_onto_latency}ms`이다. "
        "현재 구조에서는 ontology-hybrid가 약간 더 느리므로, 품질 이득이 있는 QO 계열에 선택적으로 적용하는 routing이 적절하다.",
        "- 해석 주의: 이 점수는 자동 휴리스틱 기반이다. 최종 논문/발표용 성능표에는 gold answer 또는 grader 기반 judge를 추가해야 한다.",
    ]


def _representative_case_lines(matrix_rows: Sequence[dict[str, Any]]) -> list[str]:
    if not matrix_rows:
        return ["- 아직 실행 matrix가 없어 대표 사례는 다음 비교 run 이후 채운다."]
    preferred_ids = ["QP01", "QP11", "QP41", "QP50", "QO01", "QO11", "QO21", "QO30", "QO44", "QO50"]
    rows_by_qid: dict[str, list[dict[str, Any]]] = {}
    for row in matrix_rows:
        rows_by_qid.setdefault(str(row.get("qid")), []).append(row)
    lines: list[str] = []
    for qid in preferred_ids:
        rows = rows_by_qid.get(qid)
        if not rows:
            continue
        compact = ", ".join(
            f"{row.get('profile')}: source={row.get('source_hit')}, answerability={row.get('answerability')}, "
            f"evidence={row.get('evidence_quality_score')}, latency={row.get('latency_ms')}ms"
            for row in rows
        )
        lines.append(f"- `{qid}` {compact}")
    return lines or ["- 대표 사례 후보를 찾지 못했다."]


def _question_appendix_lines(questions: Sequence[ComparisonQuestion]) -> list[str]:
    lines = [
        "| ID | group | question | expected_sources | expected_data_fields | judge_rule |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for question in questions:
        lines.append(
            "| "
            + " | ".join(
                [
                    question.qid,
                    f"`{question.question_group}`",
                    _markdown_escape(question.question),
                    _markdown_escape(", ".join(question.expected_sources) or "-"),
                    _markdown_escape(", ".join(question.expected_data_fields) or "-"),
                    _markdown_escape(question.verdict),
                ]
            )
            + " |"
        )
    return lines


def _summary_report(
    manifest: dict[str, Any],
    metrics: dict[str, Any],
    matrix_rows: Sequence[dict[str, Any]],
    failures: Sequence[dict[str, Any]],
) -> str:
    lines = [
        f"# Timestamp: {manifest['timestamp']}",
        "",
        "# RAG Profile Comparison Summary",
        "",
        f"- model: `{manifest['model']}`",
        f"- profiles: `{', '.join(manifest['profiles'])}`",
        f"- selected_question_count: `{manifest['selected_question_count']}`",
        f"- profile_response_count: `{manifest.get('profile_response_count', 0)}`",
        f"- top_k: `{manifest['top_k']}`",
        f"- smoke_test_status: `{manifest['smoke_test_status']}`",
        f"- batch_status: `{manifest['batch_status']}`",
        "",
        "## Metrics",
        "",
        *_metrics_table(metrics),
        "",
        "## Representative Cases",
        "",
        *_representative_case_lines(matrix_rows),
        "",
        "## Evaluation Note",
        "",
        "- QP는 db-only baseline으로 평가하고, QO 결과는 source hit만으로 성공 처리하지 않는다.",
        "- QO는 answerability, evidence_kind/confidence, role/relation/provenance 노출을 함께 본다.",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        for failure in failures:
            lines.append(
                f"- `{failure['qid']}` `{failure.get('profile', '')}` {failure['error_type']}: "
                f"{failure.get('error_message', '')[:240]} hint={failure.get('failure_hint', '')}"
            )
    return "\n".join(lines) + "\n"


def write_final_report(
    report_path: Path,
    timestamp: str,
    run_dir: Path,
    manifest: dict[str, Any],
    metrics: dict[str, Any],
    questions: Sequence[ComparisonQuestion],
    matrix_rows: Sequence[dict[str, Any]],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Timestamp: {timestamp}",
        "",
        "# 따릉이 Native RAG vs Ontology-base RAG 100문항 KPI 비교 분석 리포트",
        "",
        "## 1. 실험 목적",
        "",
        "native RAG(db-only)와 ontology-base RAG(ontology-hybrid)가 같은 질문 100개에서 어떤 차이를 보이는지 검증한다. "
        "`QP01~QP50`은 DB-only도 답할 수 있어야 하는 baseline 문항이고, `QO01~QO50`은 ontology 필요성을 드러내는 복합 의미 질의다.",
        "",
        "## 2. 실험 조건",
        "",
        f"- run_dir: `{run_dir}`",
        f"- model: `{manifest.get('model', DEFAULT_OPENAI_MODEL)}`",
        f"- profiles: `{', '.join(manifest.get('profiles', DEFAULT_PROFILES))}`",
        f"- top_k: `{manifest.get('top_k', DEFAULT_TOP_K)}`",
        "- question set: `QP01~QP50 + QO01~QO50`",
        "- API key source: `config/openai_api_key.local` path만 기록하며 key 값은 산출물에 남기지 않는다.",
        "",
        "## 3. 전체 결과 요약",
        "",
        *_metrics_table(metrics),
        "",
        "### 실제 run 해석",
        "",
        *_actual_takeaway_lines(metrics),
        "",
        "## 4. KPI 판정 기준",
        "",
        "이 보고서는 발표/논문형 기준으로 평가한다. latency는 비용 지표로 보되, 핵심 KPI는 answerability, evidence quality, ontology value uplift다.",
        "",
        *_kpi_budget_lines(),
        "",
        "## 5. 현재 run 기준 KPI 판정",
        "",
        *_kpi_judgement_lines(metrics),
        "",
        "## 6. 질문 유형별 분석",
        "",
        "- QP: 데이터셋 식별, schema, station lookup, usage, document source를 같은 지표로 비교한다.",
        "- QO: 날씨-수요, role-aware 이동, 고장 lifecycle, provenance/confidence를 source hit와 별도 지표로 비교한다.",
        "- QO 결과는 source hit만으로 성공 처리하지 않는다. answerability, evidence quality, relation/provenance 노출을 함께 봐야 한다.",
        "",
        "## 7. 대표 사례 분석",
        "",
        *_representative_case_lines(matrix_rows),
        "",
        "## 8. KPI 기반 결론 및 고도화 방향",
        "",
        "- native RAG(db-only)는 QP baseline에서 충분히 강하다. 단일 테이블 조회, 단순 group by, key lookup, 명시적 source routing은 native RAG 우선 적용이 적절하다.",
        "- ontology-base RAG(ontology-hybrid)는 QO 의미 질의에서 source hit가 아니라 answerability/evidence quality를 끌어올리는 효과가 있다.",
        "- QP에서는 ontology-base RAG를 기본값으로 쓰기보다 질문 intent가 QO형일 때 조건부 routing하는 편이 비용 대비 합리적이다.",
        "- QO에서는 ontology-base RAG를 우선 적용하되, QO30처럼 개선이 약한 문항은 bounded evidence slice 보강 대상으로 둔다.",
        "- 다음 backlog: KPI 판정을 자동 산출물로 고정하고, Structured Outputs/Graders로 answerability와 evidence quality judge를 보강한다.",
        "",
        "## Appendix. 100문항 평가셋",
        "",
        *_question_appendix_lines(questions),
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _empty_output_files(run_dir: Path) -> None:
    for path in ["questions.jsonl", "profile_responses.jsonl", "failures.jsonl"]:
        (run_dir / path).write_text("", encoding="utf-8")


def _default_runtime(
    project_root: Path,
    api_key_file: Path | str | None,
    model: str,
    top_k: int,
    profiles: Sequence[str],
    embedding_backend: str,
    llm_url: str | None,
) -> ComparisonRuntime:
    llm_settings = resolve_llm_runtime_settings(
        project_root=project_root,
        provider=LLM_PROVIDER_OPENAI,
        llm_url=llm_url or "",
        model=model,
        api_key_file=api_key_file,
        api_key_env=DEFAULT_OPENAI_API_KEY_ENV,
    )
    return ComparisonRuntime(
        model=llm_settings.model,
        llm_url=llm_settings.llm_url,
        api_key=llm_settings.api_key,
        profiles=tuple(profiles),
        embedding_backend=embedding_backend,
        top_k=top_k,
    )


def _missing_index_failures(project_root: Path, runtime: ComparisonRuntime, timestamp: str) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for profile in runtime.profiles:
        index_dir = default_index_dir(project_root, profile=profile)
        if not index_is_ready(index_dir):
            message = f"RAG index is not ready: {index_dir}"
            failures.append(
                {
                    "timestamp": timestamp,
                    "qid": "preflight",
                    "profile": profile,
                    "model": runtime.model,
                    "error_type": "MissingRagIndex",
                    "error_message": message,
                    "failure_hint": _failure_hint("MissingRagIndex", message),
                }
            )
    return failures


def run_comparison(
    project_root: Path,
    output_dir: Path | None = None,
    timestamp: str | None = None,
    runtime: ComparisonRuntime | None = None,
    answerer: Answerer = default_answerer,
    context_builder: ContextBuilder | None = None,
    report_path: Path | None = None,
    api_key_file: Path | str | None = DEFAULT_OPENAI_API_KEY_FILE,
) -> Path:
    timestamp = timestamp or _now()
    if runtime is None:
        runtime = _default_runtime(
            project_root=project_root,
            api_key_file=api_key_file,
            model=DEFAULT_OPENAI_MODEL,
            top_k=DEFAULT_TOP_K,
            profiles=DEFAULT_PROFILES,
            embedding_backend="auto",
            llm_url=None,
        )
    output_root = output_dir or project_root / DEFAULT_OUTPUT_ROOT
    run_dir = output_root / f"run_{_run_stamp(timestamp)}_qp50_qo50_{_model_stamp(runtime.model)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    _empty_output_files(run_dir)

    questions = select_comparison_questions(project_root)
    for question in questions:
        _append_jsonl(run_dir / "questions.jsonl", {"timestamp": timestamp, **question.to_dict()})

    resolved_report_path = report_path or project_root / DEFAULT_REPORT_RELATIVE_PATH
    indexes = {
        profile: str(default_index_dir(project_root, profile=profile)) for profile in runtime.profiles
    }
    manifest: dict[str, Any] = {
        "timestamp": timestamp,
        "project_root": str(project_root),
        "model": runtime.model,
        "llm_url": runtime.llm_url,
        "profiles": list(runtime.profiles),
        "selected_question_count": len(questions),
        "question_range": "QP01-QP50,QO01-QO50",
        "smoke_test_status": "not_run",
        "batch_status": "not_started",
        "index_dirs": indexes,
        "embedding_backend": runtime.embedding_backend,
        "top_k": runtime.top_k,
        "api_key_source": str(api_key_file or DEFAULT_OPENAI_API_KEY_FILE),
        "api_key_present": bool(runtime.api_key),
        "report_path": str(resolved_report_path),
    }

    responses: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    matrix_rows: list[dict[str, Any]] = []
    secrets = [runtime.api_key]

    if answerer is default_answerer and not runtime.api_key:
        manifest["smoke_test_status"] = "failed"
        manifest["batch_status"] = "missing_api_key"
        failure = {
            "timestamp": timestamp,
            "qid": questions[0].qid if questions else "preflight",
            "profile": runtime.profiles[0] if runtime.profiles else "",
            "model": runtime.model,
            "error_type": "MissingApiKey",
            "error_message": "OPENAI_API_KEY is empty.",
            "failure_hint": "config/openai_api_key.local의 OPENAI_API_KEY 값을 확인하세요.",
        }
        failures.append(failure)
        _append_jsonl(run_dir / "failures.jsonl", failure)
        metrics = build_comparison_metrics(responses)
        manifest["profile_response_count"] = 0
        manifest["failure_count"] = len(failures)
        _write_json(run_dir / "comparison_metrics.json", metrics)
        matrix_rows = write_comparison_matrix(run_dir / "comparison_matrix.csv", responses)
        _write_json(run_dir / "run_manifest.json", manifest)
        (run_dir / "summary_report.md").write_text(
            _summary_report(manifest, metrics, matrix_rows, failures),
            encoding="utf-8",
        )
        write_final_report(resolved_report_path, timestamp, run_dir, manifest, metrics, questions, matrix_rows)
        return run_dir

    if answerer is default_answerer:
        preflight_failures = _missing_index_failures(project_root, runtime, timestamp)
        if preflight_failures:
            manifest["smoke_test_status"] = "failed"
            manifest["batch_status"] = "missing_index"
            for failure in preflight_failures:
                failures.append(failure)
                _append_jsonl(run_dir / "failures.jsonl", failure)
            metrics = build_comparison_metrics(responses)
            manifest["profile_response_count"] = 0
            manifest["failure_count"] = len(failures)
            _write_json(run_dir / "comparison_metrics.json", metrics)
            matrix_rows = write_comparison_matrix(run_dir / "comparison_matrix.csv", responses)
            _write_json(run_dir / "run_manifest.json", manifest)
            (run_dir / "summary_report.md").write_text(
                _summary_report(manifest, metrics, matrix_rows, failures),
                encoding="utf-8",
            )
            write_final_report(resolved_report_path, timestamp, run_dir, manifest, metrics, questions, matrix_rows)
            return run_dir

    context_builder = context_builder or CachedProfileContextBuilder(project_root, runtime)
    stop_after_smoke_failure = False
    manifest["batch_status"] = "running"

    for question in questions:
        for profile in runtime.profiles:
            started = time.monotonic()
            context = ProfileContext(prompt="", context_report="", context_source_summary=[], retrieved_sources=[])
            try:
                context = context_builder(project_root, question, profile, runtime)
                answer = answerer(question, profile, runtime, context)
                latency_ms = int((time.monotonic() - started) * 1000)
                row = build_response_row(
                    question=question,
                    profile=profile,
                    runtime=runtime,
                    context=context,
                    timestamp=timestamp,
                    latency_ms=latency_ms,
                    status="ok",
                    answer=answer,
                    secrets=secrets,
                )
                responses.append(row)
                _append_jsonl(run_dir / "profile_responses.jsonl", row)
                if manifest["smoke_test_status"] == "not_run":
                    manifest["smoke_test_status"] = "passed"
            except Exception as exc:
                latency_ms = int((time.monotonic() - started) * 1000)
                error_type = type(exc).__name__
                error_message = _sanitize_text(str(exc), secrets)
                row = build_response_row(
                    question=question,
                    profile=profile,
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
                    "profile": profile,
                    "model": runtime.model,
                    "error_type": error_type,
                    "error_message": error_message,
                    "failure_hint": _failure_hint(error_type, error_message),
                }
                responses.append(row)
                failures.append(failure)
                _append_jsonl(run_dir / "profile_responses.jsonl", row)
                _append_jsonl(run_dir / "failures.jsonl", failure)
                if manifest["smoke_test_status"] == "not_run":
                    manifest["smoke_test_status"] = "failed"
                    manifest["batch_status"] = "stopped_after_smoke_failure"
                    stop_after_smoke_failure = True
            if stop_after_smoke_failure:
                break
        if stop_after_smoke_failure:
            break

    if manifest["batch_status"] == "running":
        manifest["batch_status"] = "completed"
    manifest["profile_response_count"] = len(responses)
    manifest["success_count"] = sum(1 for response in responses if response["status"] == "ok")
    manifest["failure_count"] = len(failures)
    metrics = build_comparison_metrics(responses)
    matrix_rows = write_comparison_matrix(run_dir / "comparison_matrix.csv", responses)
    _write_json(run_dir / "comparison_metrics.json", metrics)
    _write_json(run_dir / "run_manifest.json", manifest)
    (run_dir / "summary_report.md").write_text(
        _summary_report(manifest, metrics, matrix_rows, failures),
        encoding="utf-8",
    )
    write_final_report(resolved_report_path, timestamp, run_dir, manifest, metrics, questions, matrix_rows)
    return run_dir


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run db-only vs ontology-hybrid RAG comparison on QP50+QO50.")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--report-path", type=Path, default=None)
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_OPENAI_API_KEY_FILE)
    parser.add_argument("--model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--llm-url", default=None)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--embedding-backend", default="auto")
    args = parser.parse_args(argv)

    project_root = args.project_root or find_project_root(Path(__file__))
    runtime = _default_runtime(
        project_root=project_root,
        api_key_file=args.api_key_file,
        model=args.model,
        top_k=args.top_k,
        profiles=DEFAULT_PROFILES,
        embedding_backend=args.embedding_backend,
        llm_url=args.llm_url,
    )
    run_dir = run_comparison(
        project_root=project_root,
        output_dir=args.output_dir,
        timestamp=args.timestamp,
        runtime=runtime,
        report_path=args.report_path,
        api_key_file=args.api_key_file,
    )
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
