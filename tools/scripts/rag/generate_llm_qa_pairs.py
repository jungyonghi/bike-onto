# Timestamp: 2026-05-19 20:08:00

from __future__ import annotations

import argparse
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


def _question_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "qid": row.get("qid") or row.get("id") or row.get("question_id"),
        "question": row.get("question"),
        "question_group": row.get("question_group") or row.get("group") or row.get("question_type"),
        "expected_sources": row.get("expected_sources") or [],
        "expected_data_fields": row.get("expected_data_fields") or [],
        "expected_query": row.get("expected_query") or "",
        "physical_query": row.get("physical_query") or "",
        "verdict": row.get("verdict") or "",
    }


def build_prompt(batch: list[dict[str, Any]]) -> str:
    compact = [_question_payload(row) for row in batch]
    return "\n".join(
        [
            "너는 OBYBK RAG inspection QA 생성기다.",
            "아래 질문들에 대해 한국어 질의-답변(QA) 데이터를 만든다.",
            "중요 규칙:",
            "- 실제 DB를 실행한 척하지 않는다.",
            "- expected_sources와 expected_data_fields를 근거로, 어떤 데이터/관계/검토가 필요한지 답한다.",
            "- 정확한 수치가 context에 없으면 '현재 근거만으로 수치 확정 불가'라고 명시한다.",
            "- 질문이 단순 조회(QP)이면 필요한 source/table/field와 조회 기준을 간결히 답한다.",
            "- 질문이 ontology/relation(QO)이면 claim, evidence, entity, relation, review gate 관점이 드러나게 답한다.",
            "- 각 답변은 4~7문장, 과장 금지, 제출용으로 담백하게 작성한다.",
            "- 반드시 JSON object만 반환한다. markdown code fence 금지.",
            "반환 schema:",
            '{"items":[{"qid":"...","question":"...","answer":"...","answerability":"answered|insufficient-but-grounded","evidence_sources":["..."],"requires_review":true,"review_reason":"..."}]}',
            "질문 batch:",
            json.dumps(compact, ensure_ascii=False),
        ]
    )


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
            {"role": "system", "content": "You generate grounded Korean QA pairs. Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "max_completion_tokens": 9000,
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
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    parsed["_llm"] = {
        "model": model,
        "latency_ms": latency_ms,
        "usage": data.get("usage", {}),
    }
    return parsed


def write_markdown(rows: list[dict[str, Any]], output: Path, *, title: str) -> None:
    lines = [
        f"# {title}",
        "",
        f"- generated_at: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- qa_count: `{len(rows)}`",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"## {index:03d}. {row.get('qid')} · {row.get('question')}",
                "",
                str(row.get("answer") or "").strip(),
                "",
                f"- answerability: `{row.get('answerability')}`",
                f"- evidence_sources: `{', '.join(row.get('evidence_sources') or [])}`",
                f"- requires_review: `{row.get('requires_review')}`",
                f"- review_reason: {row.get('review_reason') or ''}",
                "",
            ]
        )
    output.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate about 100 LLM-backed Korean QA pairs from a question JSONL.")
    parser.add_argument("--questions-jsonl", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--model")
    args = parser.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_rows = read_jsonl(args.questions_jsonl)[: args.limit]
    output_jsonl = args.output_dir / "llm_qa_pairs_100.jsonl"
    output_md = args.output_dir / "llm_qa_pairs_100.md"
    batch_log = args.output_dir / "batch_log.jsonl"
    output_jsonl.write_text("", encoding="utf-8")
    batch_log.write_text("", encoding="utf-8")

    generated: list[dict[str, Any]] = []
    for batch_index, batch in enumerate(chunks(source_rows, args.batch_size), start=1):
        prompt = build_prompt(batch)
        started = time.perf_counter()
        parsed = call_llm(prompt, key_file=args.key_file, model_override=args.model)
        items = parsed.get("items") or []
        if len(items) != len(batch):
            raise RuntimeError(f"Batch {batch_index}: expected {len(batch)} items, got {len(items)}")
        llm_meta = parsed.get("_llm", {})
        for source, item in zip(batch, items):
            row = {
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "qid": item.get("qid") or source.get("qid") or source.get("id"),
                "question": item.get("question") or source.get("question"),
                "answer": item.get("answer") or "",
                "answerability": item.get("answerability") or "answered",
                "evidence_sources": item.get("evidence_sources") or source.get("expected_sources") or [],
                "requires_review": bool(item.get("requires_review")),
                "review_reason": item.get("review_reason") or "",
                "question_group": source.get("question_group") or source.get("question_type") or "",
                "expected_sources": source.get("expected_sources") or [],
                "expected_data_fields": source.get("expected_data_fields") or [],
                "llm": llm_meta,
                "mode": "live_llm_batch_qa",
            }
            generated.append(row)
            with output_jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        with batch_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"batch": batch_index, "count": len(batch), "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "llm": llm_meta}, ensure_ascii=False) + "\n")
        print(json.dumps({"batch": batch_index, "generated": len(generated), "latency_ms": llm_meta.get("latency_ms")}, ensure_ascii=False), flush=True)

    write_markdown(generated, output_md, title="OBYBK 100 LLM QA Pairs")
    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "questions_jsonl": str(args.questions_jsonl),
        "qa_count": len(generated),
        "output_jsonl": str(output_jsonl),
        "output_md": str(output_md),
        "batch_log": str(batch_log),
        "model": generated[0].get("llm", {}).get("model") if generated else args.model,
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
