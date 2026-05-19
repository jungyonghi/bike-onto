# Timestamp: 2026-05-19 22:05:00

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Iterable

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]

TOOLS_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_SCRIPTS_DIR))

from rag.rag_llm_answer_endpoint import DEFAULT_KEY_FILE, chat_url, load_openai_settings  # noqa: E402

ALLOWED_LABELS = {
    "executable-with-data",
    "needs-parameter",
    "needs-metric-definition",
    "needs-schema-confirmation",
    "needs-provenance",
    "inferential-only",
    "needs-human-review",
}

FINAL_EDITOR_INSTRUCTIONS = """
당신은 데이터 분석 QA 벤치마크 문서를 다듬는 기술문서 편집자이자 RAG/GraphRAG 평가셋 설계자다.
입력된 QA Pair를 최종 제출용 평가셋 문서 항목으로 재작성한다.

프로젝트 포지셔닝:
- 특정 도메인 챗봇 문서가 아니라, 범용 RAG/GraphRAG inspection framework의 평가셋이다.
- 파일명과 컬럼명은 case-study binding으로 사용하되, 답변 문체는 범용 데이터 분석/RAG inspection 평가 패턴이 드러나야 한다.
- 실제 데이터 실행 결과를 지어내지 않는다. 원자료가 없으면 숫자, 순위, 고유명을 생성하지 말고 산출 방식, 필요한 파라미터, 검토 조건을 적는다.

Answerability 라벨은 반드시 아래 중 하나만 사용한다.
- executable-with-data: 원자료와 파라미터만 있으면 바로 실행 가능한 단순 질의
- needs-parameter: 특정 날짜, 시간, ID, 기간 등 입력값이 필요한 질의
- needs-metric-definition: 수요 유지, 급회복, 비어감, 부족, 과잉처럼 파생 지표 정의가 필요한 질의
- needs-schema-confirmation: 컬럼 의미, 단위, 시작/반납 역할, 좌표계, 시간대 경계 등 스키마 확인이 필요한 질의
- needs-provenance: 직접 근거와 추론 근거, source priority, confidence가 필요한 질의
- inferential-only: 직접 수치 산출보다 추론적 설명 또는 운영 가설 생성이 중심인 질의
- needs-human-review: 자동 산출은 가능하지만 기준 확정 또는 오탐 검토가 필요한 질의

Review 판단:
- 단순 COUNT, GROUP BY, SUM, AVG, ORDER BY LIMIT 질의는 데이터만 있으면 실행 가능하므로 review=False가 가능하다.
- 특정 날짜/기간/ID/시간 입력만 필요한 경우는 needs-parameter이며 review=False가 가능하다.
- 컬럼 의미, 단위, 타임존, 시작/반납 역할, 개인정보, baseline/임계치, 추론 조인, alias 해소, provenance/confidence가 필요하면 review=True다.
- 데이터가 지금 실행되지 않았다는 사실만으로 review=True로 만들지 않는다.
- review=False면 review_reason은 빈 문자열로 둔다.
- review=True면 사람이 왜 검토해야 하는지 한 문장으로 구체적으로 쓴다.

문체:
- 한국어 기술문서체로 작성한다.
- QP는 실행형 질의다. 2~4문장으로 짧고 단정하게 쓴다. 필터, 조인, 집계, 정렬, 반환 형태를 중심으로 설명한다.
- QO는 운영 추론/GraphRAG형 질의다. 3~5문장으로 필요한 조인, 파생 지표, baseline, 임계치, provenance, confidence 중 질문별 핵심만 설명한다.
- QP와 QO가 같은 템플릿 문장처럼 보이지 않게 한다.
- 같은 문장 구조를 연속해서 반복하지 않는다.
- "현재 근거만으로 수치 확정 불가", "현재 근거만으로 제시할 수 없다", "리뷰 게이트가 필요하다"를 반복하지 않는다.
- 대신 문맥에 맞게 "실제 값은 원본 실행 후 확정된다", "입력 파라미터가 주어지면 즉시 산출 가능하다", "지표 정의가 고정되어야 결과가 재현된다", "스키마 확인 전에는 해석을 제한해야 한다", "직접 근거와 추론 근거를 분리해 confidence를 표기해야 한다" 등을 자연스럽게 변주한다.

Evidence source:
- 실제로 필요한 source만 남긴다.
- ontology-lite는 class/relation/provenance/confidence/metric definition이 필요한 QO 항목에만 포함한다.
- 불필요한 source를 늘리지 않는다.

반환 규칙:
- 반드시 JSON object만 반환한다. markdown code fence 금지.
- qid와 question은 입력값을 유지한다.
- answer는 최종 문서에 바로 넣을 본문 문단만 반환한다. metadata bullet은 answer에 넣지 않는다.
- 반환 schema:
{"items":[{"qid":"QP01","question":"...","answer":"...","answerability":"needs-parameter","evidence_sources":["..."],"requires_review":false,"review_reason":""}]}
""".strip()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_no}")
        rows.append(item)
    return rows


def chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def build_prompt(batch: list[dict[str, Any]]) -> str:
    compact = []
    for row in batch:
        compact.append(
            {
                "qid": row.get("qid"),
                "question_group": row.get("question_group") or (str(row.get("qid") or "")[:2]),
                "question": row.get("question"),
                "current_answer": row.get("answer"),
                "current_answerability": row.get("answerability"),
                "current_evidence_sources": row.get("evidence_sources") or [],
                "current_requires_review": row.get("requires_review"),
                "current_review_reason": row.get("review_reason") or "",
                "expected_sources": row.get("expected_sources") or [],
                "expected_data_fields": row.get("expected_data_fields") or [],
            }
        )
    return FINAL_EDITOR_INSTRUCTIONS + "\n\n최종 재작성할 QA batch:\n" + json.dumps(compact, ensure_ascii=False)


def call_llm(prompt: str, *, key_file: Path, model_override: str | None = None, timeout: int = 240) -> dict[str, Any]:
    if requests is None:
        raise RuntimeError("requests is not installed")
    settings = load_openai_settings(key_file)
    api_key = settings.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is empty")
    model = model_override or settings.get("OPENAI_MODEL", "gpt-5.2") or "gpt-5.2"
    base_url = settings.get("OPENAI_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1"
    started = time.perf_counter()
    response = requests.post(
        chat_url(base_url),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You revise Korean RAG/GraphRAG benchmark QA items. Return JSON only."},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": 10000,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    response.raise_for_status()
    payload = response.json()
    parsed = json.loads(payload["choices"][0]["message"]["content"])
    parsed["_llm"] = {"model": model, "latency_ms": latency_ms, "usage": payload.get("usage", {})}
    return parsed


def normalize_final_item(source: dict[str, Any], item: dict[str, Any], llm_meta: dict[str, Any]) -> dict[str, Any]:
    qid = str(source.get("qid") or item.get("qid") or "").strip()
    answerability = str(item.get("answerability") or source.get("answerability") or "").strip()
    if answerability not in ALLOWED_LABELS:
        raise ValueError(f"Invalid answerability {answerability!r} for {qid}")
    requires_review = bool(item.get("requires_review"))
    review_reason = str(item.get("review_reason") or "").strip()
    if not requires_review:
        review_reason = ""
    elif not review_reason:
        review_reason = "사람 검토가 필요한 기준 또는 해석 조건이 비어 있다."
    evidence_sources = item.get("evidence_sources") or source.get("evidence_sources") or source.get("expected_sources") or []
    evidence_sources = [str(value).strip() for value in evidence_sources if str(value).strip()]
    if not evidence_sources:
        evidence_sources = ["domain artifact"]
    return {
        "finalized_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "qid": qid,
        "question": str(source.get("question") or item.get("question") or "").strip(),
        "answer": str(item.get("answer") or "").strip(),
        "answerability": answerability,
        "evidence_sources": evidence_sources,
        "requires_review": requires_review,
        "review_reason": review_reason,
        "question_group": source.get("question_group") or qid[:2],
        "expected_sources": source.get("expected_sources") or [],
        "expected_data_fields": source.get("expected_data_fields") or [],
        "llm": llm_meta,
        "mode": "final_benchmark_polish",
    }


def validate_batch(source_batch: list[dict[str, Any]], items: list[dict[str, Any]], batch_index: int) -> None:
    if len(items) != len(source_batch):
        raise RuntimeError(f"Batch {batch_index}: expected {len(source_batch)} items, got {len(items)}")
    for source, item in zip(source_batch, items):
        if str(source.get("qid")) != str(item.get("qid")):
            raise RuntimeError(f"Batch {batch_index}: qid mismatch {source.get('qid')} != {item.get('qid')}")


def lint_final_rows(rows: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    if len(rows) != 100:
        issues.append(f"expected 100 rows, got {len(rows)}")
    expected_qids = [f"QP{i:02d}" for i in range(1, 51)] + [f"QO{i:02d}" for i in range(1, 51)]
    qids = [str(row.get("qid")) for row in rows]
    if qids != expected_qids:
        issues.append("qid order mismatch")
    joined = "\n".join(row.get("answer", "") for row in rows)
    for phrase in ["insufficient-but-grounded", "현재 근거만으로 수치 확정 불가", "현재 근거만으로 제시할 수 없다", "리뷰 게이트가 필요하다"]:
        if phrase in joined:
            issues.append(f"overused/forbidden phrase remains: {phrase}")
    for row in rows:
        if row["answerability"] not in ALLOWED_LABELS:
            issues.append(f"{row['qid']}: invalid answerability")
        if not row.get("evidence_sources"):
            issues.append(f"{row['qid']}: empty evidence_sources")
        if not row["requires_review"] and row.get("review_reason"):
            issues.append(f"{row['qid']}: review false but review_reason not blank")
        if row["requires_review"] and not row.get("review_reason"):
            issues.append(f"{row['qid']}: review true but review_reason blank")
        if "`" in row["answerability"] or "`" in str(row.get("requires_review")):
            issues.append(f"{row['qid']}: metadata contains code backticks")
    return issues


def write_outputs(rows: list[dict[str, Any]], output_dir: Path, *, source_path: Path, batch_log_path: Path) -> dict[str, Any]:
    jsonl_path = output_dir / "llm_qa_pairs_100_final.jsonl"
    md_path = output_dir / "llm_qa_pairs_100_final.md"
    csv_path = output_dir / "llm_qa_pairs_100_final.csv"
    report_path = output_dir / "llm_qa_pairs_100_final_report.md"
    catalog_path = output_dir / "llm_qa_pairs_100_final_catalog.md"
    summary_path = output_dir / "llm_qa_pairs_100_final_summary.json"

    jsonl_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    md_lines = [
        "# OBYBK RAG/GraphRAG Inspection Benchmark 100",
        "",
        "Validated with a public mobility case-study binding.",
        "",
        f"- finalized_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- qa_count: {len(rows)}",
        "- QP01~QP50: 실행형 데이터 질의",
        "- QO01~QO50: relation, metric definition, provenance, review gate가 필요한 inspection 질의",
        "",
    ]
    for idx, row in enumerate(rows, start=1):
        md_lines.extend(
            [
                f"## {idx:03d}. {row['qid']} · {row['question']}",
                "",
                row["answer"].strip(),
                "",
                f"- answerability: {row['answerability']}",
                f"- evidence_sources: {', '.join(row.get('evidence_sources') or [])}",
                f"- requires_review: {str(bool(row['requires_review']))}",
                f"- review_reason: {row.get('review_reason') or ''}",
                "",
            ]
        )
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["qid", "question_group", "question", "answer", "answerability", "evidence_sources", "requires_review", "review_reason"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "qid": row["qid"],
                    "question_group": row.get("question_group", ""),
                    "question": row["question"],
                    "answer": row["answer"],
                    "answerability": row["answerability"],
                    "evidence_sources": ", ".join(row.get("evidence_sources") or []),
                    "requires_review": row["requires_review"],
                    "review_reason": row.get("review_reason") or "",
                }
            )

    catalog_lines = [
        "# OBYBK RAG/GraphRAG Inspection Benchmark 100 — Catalog",
        "",
        "| # | QID | Group | Answerability | Review | Question |",
        "|---:|---|---|---|---|---|",
    ]
    for idx, row in enumerate(rows, start=1):
        question = str(row["question"]).replace("|", "/")
        catalog_lines.append(f"| {idx} | {row['qid']} | {row.get('question_group','')} | {row['answerability']} | {row['requires_review']} | {question} |")
    catalog_path.write_text("\n".join(catalog_lines) + "\n", encoding="utf-8")

    label_counts = Counter(row["answerability"] for row in rows)
    review_counts = Counter(str(bool(row["requires_review"])) for row in rows)
    issues = lint_final_rows(rows)
    summary = {
        "finalized_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(source_path),
        "qa_count": len(rows),
        "answerability_counts": dict(label_counts),
        "review_counts": dict(review_counts),
        "lint_issues": issues,
        "outputs": {
            "markdown": str(md_path),
            "jsonl": str(jsonl_path),
            "csv": str(csv_path),
            "catalog": str(catalog_path),
            "report": str(report_path),
            "batch_log": str(batch_log_path),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_lines = [
        "# Final Benchmark QA Polish Report",
        "",
        f"- qa_count: {len(rows)}",
        f"- source: {source_path}",
        f"- lint_issues: {len(issues)}",
        "",
        "## Answerability Distribution",
        "",
        "| Label | Count |",
        "|---|---:|",
        *[f"| {label} | {count} |" for label, count in sorted(label_counts.items())],
        "",
        "## Review Distribution",
        "",
        "| requires_review | Count |",
        "|---|---:|",
        *[f"| {label} | {count} |" for label, count in sorted(review_counts.items())],
        "",
        "## Lint Issues",
        "",
    ]
    report_lines.extend([f"- {issue}" for issue in issues] or ["- none"])
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize 100 QA pairs as a less repetitive general RAG/GraphRAG benchmark document.")
    parser.add_argument("--input-jsonl", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--model")
    parser.add_argument("--no-llm", action="store_true", help="Do not rewrite with a live LLM; normalize/lint already revised rows and write final outputs.")
    args = parser.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = read_jsonl(args.input_jsonl)
    final_rows: list[dict[str, Any]] = []
    batch_log_path = args.output_dir / "final_polish_batch_log.jsonl"
    batch_log_path.write_text("", encoding="utf-8")

    if args.no_llm:
        llm_meta = {"mode": "no_llm_normalize", "model": "none", "latency_ms": 0.0, "usage": {}}
        for source in rows:
            final_rows.append(normalize_final_item(source, source, llm_meta))
        with batch_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"batch": 1, "count": len(final_rows), "llm": llm_meta}, ensure_ascii=False) + "\n")
        print(json.dumps({"batch": 1, "finalized": len(final_rows), "latency_ms": 0.0, "mode": "no_llm_normalize"}, ensure_ascii=False), flush=True)
    else:
        for batch_index, batch in enumerate(chunks(rows, args.batch_size), start=1):
            parsed = call_llm(build_prompt(batch), key_file=args.key_file, model_override=args.model)
            items = parsed.get("items") or []
            validate_batch(batch, items, batch_index)
            llm_meta = parsed.get("_llm", {})
            for source, item in zip(batch, items):
                final_rows.append(normalize_final_item(source, item, llm_meta))
            with batch_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"batch": batch_index, "count": len(items), "llm": llm_meta}, ensure_ascii=False) + "\n")
            print(json.dumps({"batch": batch_index, "finalized": len(final_rows), "latency_ms": llm_meta.get("latency_ms")}, ensure_ascii=False), flush=True)

    summary = write_outputs(final_rows, args.output_dir, source_path=args.input_jsonl, batch_log_path=batch_log_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary.get("lint_issues") else 0


if __name__ == "__main__":
    raise SystemExit(main())
