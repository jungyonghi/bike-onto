# Timestamp: 2026-05-19 20:36:00

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
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

EDITOR_INSTRUCTIONS = """
당신은 데이터 분석 QA 벤치마크 문서를 다듬는 기술문서 편집자이자 RAG/GraphRAG 평가셋 설계자다.
아래 QA Pair를 수정하라. 목표는 자동 생성 템플릿 느낌을 줄이고, 교수/부트캠프 평가자가 보기에 자연스럽고 설계 의도가 분명한 평가셋으로 만드는 것이다.

수정 원칙:
1. answerability는 아래 라벨 중 하나로 세분화한다.
- executable-with-data: 원자료와 파라미터만 있으면 바로 실행 가능한 단순 질의
- needs-parameter: 특정 날짜, 시간, 대여소 ID, 기간 등 입력값이 필요한 질의
- needs-metric-definition: 수요 유지, 급회복, 비어감, 부족, 과잉 등 파생 지표 정의가 필요한 질의
- needs-schema-confirmation: 컬럼 의미, 단위, 시작/반납 역할, 좌표계 등 스키마 확인이 필요한 질의
- needs-provenance: 직접 근거와 추론 근거, source priority, confidence가 필요한 질의
- inferential-only: 직접 수치 산출보다 추론적 설명 또는 운영 가설 생성이 중심인 질의
- needs-human-review: 자동 산출은 가능하지만 기준 확정 또는 오탐 검토가 필요한 질의

2. requires_review 판단:
- 단순 COUNT, GROUP BY, SUM, AVG, ORDER BY LIMIT 질의는 review=False 가능.
- 날짜/대여소/기간 같은 입력값만 필요한 경우는 needs-parameter이고 review=False 가능.
- 컬럼 의미, 단위, 타임존, 시작/반납 역할, 개인정보, baseline/임계치, 추론 조인, provenance/confidence가 필요한 경우 review=True.
- review=False면 review_reason은 "not required" 또는 빈 문자열.
- review=True면 한 문장으로 구체적 이유를 쓴다.

3. 문체:
- QP는 2~4문장, 실행형 질의 설명 중심. 짧고 단정하게.
- QO는 4~6문장, 파생 개념·조인·baseline·임계치·provenance 중 질문별 핵심을 설명.
- 실제 값/순위/대여소명을 지어내지 않는다.
- "현재 근거만으로 수치 확정 불가" 같은 표현을 반복하지 않는다. 문맥에 맞게 변주한다.
- evidence_sources는 실제 필요한 파일만 남긴다. ontology-lite는 class/relation/provenance/confidence/metric definition이 필요한 QO에만 포함한다.

반드시 JSON object만 반환한다. markdown code fence 금지.
반환 schema:
{"items":[{"qid":"...","question":"...","answer":"...","answerability":"...","evidence_sources":["..."],"requires_review":false,"review_reason":"..."}]}
""".strip()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_no}")
        rows.append(value)
    return rows


def chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def build_prompt(batch: list[dict[str, Any]]) -> str:
    compact: list[dict[str, Any]] = []
    for row in batch:
        compact.append(
            {
                "qid": row.get("qid"),
                "question_group": row.get("question_group"),
                "question": row.get("question"),
                "original_answer": row.get("answer"),
                "original_answerability": row.get("answerability"),
                "original_evidence_sources": row.get("evidence_sources") or row.get("expected_sources") or [],
                "expected_sources": row.get("expected_sources") or [],
                "expected_data_fields": row.get("expected_data_fields") or [],
                "review_hint": row.get("review_reason") or "",
            }
        )
    return EDITOR_INSTRUCTIONS + "\n\n수정할 QA batch:\n" + json.dumps(compact, ensure_ascii=False)


def call_llm(prompt: str, *, key_file: Path, model_override: str | None = None, timeout: int = 240) -> dict[str, Any]:
    if requests is None:
        raise RuntimeError("requests is not installed")
    settings = load_openai_settings(key_file)
    api_key = settings.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is empty")
    model = model_override or settings.get("OPENAI_MODEL", "gpt-5.2") or "gpt-5.2"
    base_url = settings.get("OPENAI_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You revise Korean QA benchmark documents. Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "max_completion_tokens": 10000,
        "response_format": {"type": "json_object"},
    }
    started = time.perf_counter()
    response = requests.post(
        chat_url(base_url),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=timeout,
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    response.raise_for_status()
    data = response.json()
    parsed = json.loads(data["choices"][0]["message"]["content"])
    parsed["_llm"] = {"model": model, "latency_ms": latency_ms, "usage": data.get("usage", {})}
    return parsed


def validate_items(source_batch: list[dict[str, Any]], items: list[dict[str, Any]], batch_index: int) -> None:
    if len(items) != len(source_batch):
        raise RuntimeError(f"Batch {batch_index}: expected {len(source_batch)} items, got {len(items)}")
    source_qids = [str(row.get("qid")) for row in source_batch]
    item_qids = [str(row.get("qid")) for row in items]
    if source_qids != item_qids:
        raise RuntimeError(f"Batch {batch_index}: qid mismatch: {source_qids} != {item_qids}")
    for item in items:
        label = str(item.get("answerability") or "")
        if label not in ALLOWED_LABELS:
            raise RuntimeError(f"Batch {batch_index}: invalid answerability {label!r} for {item.get('qid')}")
        if item.get("requires_review") is False and str(item.get("review_reason") or "").strip() not in {"", "not required"}:
            raise RuntimeError(f"Batch {batch_index}: review false but reason not concise for {item.get('qid')}")
        if item.get("requires_review") is True and not str(item.get("review_reason") or "").strip():
            raise RuntimeError(f"Batch {batch_index}: review true but empty reason for {item.get('qid')}")


def write_outputs(rows: list[dict[str, Any]], output_dir: Path, *, source_path: Path, batch_log: Path) -> None:
    jsonl_path = output_dir / "llm_qa_pairs_100_revised.jsonl"
    md_path = output_dir / "llm_qa_pairs_100_revised.md"
    csv_path = output_dir / "llm_qa_pairs_100_revised.csv"
    catalog_path = output_dir / "llm_qa_pairs_100_revised_catalog.md"
    report_path = output_dir / "llm_qa_pairs_100_revised_report.md"

    jsonl_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    md_lines = [
        "# OBYBK 100 LLM QA Pairs — Revised Benchmark Edition",
        "",
        f"- revised_at: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- qa_count: `{len(rows)}`",
        "- editing goal: 자동 생성 템플릿 문체를 줄이고, 실행 가능성/검토 필요성을 세분화",
        "",
    ]
    for idx, row in enumerate(rows, start=1):
        md_lines.extend(
            [
                f"## {idx:03d}. {row['qid']} · {row['question']}",
                "",
                row["answer"].strip(),
                "",
                f"- answerability: `{row['answerability']}`",
                f"- evidence_sources: `{', '.join(row.get('evidence_sources') or [])}`",
                f"- requires_review: `{row['requires_review']}`",
                f"- review_reason: {row.get('review_reason') or ''}",
                "",
            ]
        )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["qid", "question_group", "question", "answer", "answerability", "evidence_sources", "requires_review", "review_reason"])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "qid": row["qid"],
                "question_group": row.get("question_group", ""),
                "question": row["question"],
                "answer": row["answer"],
                "answerability": row["answerability"],
                "evidence_sources": ", ".join(row.get("evidence_sources") or []),
                "requires_review": row["requires_review"],
                "review_reason": row.get("review_reason") or "",
            })

    catalog_lines = [
        "# OBYBK 100 QA Revised Catalog",
        "",
        "| # | QID | Group | Answerability | Review | Question |",
        "|---:|---|---|---|---|---|",
    ]
    for i, row in enumerate(rows, start=1):
        q = str(row["question"]).replace("|", "/")
        catalog_lines.append(f"| {i} | {row['qid']} | {row.get('question_group','')} | {row['answerability']} | {row['requires_review']} | {q} |")
    catalog_path.write_text("\n".join(catalog_lines) + "\n", encoding="utf-8")

    label_counts = Counter(row["answerability"] for row in rows)
    group_counts = Counter(row.get("question_group", "") for row in rows)
    review_count = sum(1 for row in rows if row.get("requires_review"))
    report = {
        "revised_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(source_path),
        "qa_count": len(rows),
        "group_counts": dict(group_counts),
        "answerability_counts": dict(label_counts),
        "requires_review_count": review_count,
        "outputs": {
            "jsonl": str(jsonl_path),
            "markdown": str(md_path),
            "csv": str(csv_path),
            "catalog": str(catalog_path),
            "batch_log": str(batch_log),
        },
    }
    (output_dir / "llm_qa_pairs_100_revised_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_lines = [
        "# 100 QA Pair Revision Report",
        "",
        f"- qa_count: `{len(rows)}`",
        f"- source: `{source_path}`",
        f"- requires_review_count: `{review_count}`",
        "",
        "## Answerability Distribution",
        "",
        "| Label | Count |",
        "|---|---:|",
        *[f"| {label} | {count} |" for label, count in sorted(label_counts.items())],
        "",
        "## Outputs",
        "",
        f"- `{jsonl_path}`",
        f"- `{md_path}`",
        f"- `{csv_path}`",
        f"- `{catalog_path}`",
        f"- `{output_dir / 'llm_qa_pairs_100_revised_summary.json'}`",
    ]
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Revise generated 100 QA pairs into a cleaner benchmark document.")
    parser.add_argument("--input-jsonl", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--model")
    args = parser.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_rows = read_jsonl(args.input_jsonl)
    revised: list[dict[str, Any]] = []
    batch_log = args.output_dir / "revision_batch_log.jsonl"
    batch_log.write_text("", encoding="utf-8")

    for batch_index, batch in enumerate(chunks(source_rows, args.batch_size), start=1):
        prompt = build_prompt(batch)
        parsed = call_llm(prompt, key_file=args.key_file, model_override=args.model)
        items = parsed.get("items") or []
        validate_items(batch, items, batch_index)
        llm_meta = parsed.get("_llm", {})
        for source, item in zip(batch, items):
            revised.append(
                {
                    "revised_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "qid": item["qid"],
                    "question": item["question"],
                    "answer": item["answer"],
                    "answerability": item["answerability"],
                    "evidence_sources": item.get("evidence_sources") or [],
                    "requires_review": bool(item.get("requires_review")),
                    "review_reason": item.get("review_reason") or "",
                    "question_group": source.get("question_group") or "",
                    "expected_sources": source.get("expected_sources") or [],
                    "expected_data_fields": source.get("expected_data_fields") or [],
                    "llm": llm_meta,
                    "mode": "live_llm_qa_revision",
                }
            )
        with batch_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"batch": batch_index, "count": len(items), "llm": llm_meta}, ensure_ascii=False) + "\n")
        print(json.dumps({"batch": batch_index, "revised": len(revised), "latency_ms": llm_meta.get("latency_ms")}, ensure_ascii=False), flush=True)

    write_outputs(revised, args.output_dir, source_path=args.input_jsonl, batch_log=batch_log)
    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
