# Timestamp: 2026-05-19 22:58:00

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

PROMPT = """
너는 RAG/GraphRAG 분석 도구의 사용자-facing 답변을 다듬는 기술문서 편집자다.
아래 QA 항목을 '실사용 질의-답변 리스트'로 다시 쓴다.

핵심 목표:
- 평가셋 내부 산식 설명처럼 보이지 말고, 실제 분석 도구가 사용자에게 답하는 문장처럼 쓴다.
- 하지만 실제 원자료를 실행하지 않았으면 숫자, 순위, 고유 대상을 지어내지 않는다.
- 파일명/컬럼명은 필요할 때만 근거 또는 입력 조건으로 짧게 언급한다. 첫 문장을 파일명으로 시작하지 않는다.
- gender=1.0, age=20, holiday=0 같은 내부 코드값은 그대로 노출하지 말고 가능한 자연어 label(남성(M), 여성(F), 20대, 공휴일/비공휴일)을 우선한다.
- QP는 "바로 산출 가능 / 어떤 입력값이 필요 / 어떤 형태로 반환"이 드러나야 한다.
- QO는 "정의가 필요한 이유 / 기본 정의 제안 / 확정되면 어떤 결과를 반환"이 드러나야 한다.
- 같은 표현을 반복하지 않는다.
- 답변은 2~4문장으로 쓴다.

라벨별 사용자-facing 문체:
- executable-with-data: "바로 계산 가능한 항목"으로 말한다. 현재 값이 없으면 실행 결과를 지어내지 말고, 결과 형태를 자연스럽게 말한다.
- needs-parameter: 필요한 날짜/기간/ID/월 등을 먼저 요청한다. "값을 주면 바로 계산해 반환"한다고 말한다.
- needs-metric-definition: 지표 정의가 먼저 필요하다고 말하고, 사용 가능한 기본 정의 후보를 제안한다.
- needs-schema-confirmation: 컬럼 의미/단위/역할 확인 전에는 단정하면 안 된다고 말한다.
- needs-provenance: 직접 근거와 추론 근거, confidence/source priority를 분리해야 한다고 말한다.
- inferential-only: 숫자 하나보다 설계/해석 기준을 정하는 질문이라고 말한다.
- needs-human-review: 자동 후보는 만들 수 있지만 최종 기준/오탐은 사람이 확인해야 한다고 말한다.

반드시 JSON object만 반환한다.
반환 schema:
{"items":[{"qid":"QP01","question":"...","user_answer":"..."}]}
""".strip()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def build_prompt(batch: list[dict[str, Any]]) -> str:
    compact = [
        {
            "qid": row.get("qid"),
            "question": row.get("question"),
            "answerability": row.get("answerability"),
            "evidence_sources": row.get("evidence_sources") or [],
            "requires_review": row.get("requires_review"),
            "review_reason": row.get("review_reason") or "",
            "current_benchmark_answer": row.get("answer") or "",
        }
        for row in batch
    ]
    return PROMPT + "\n\nQA batch:\n" + json.dumps(compact, ensure_ascii=False)


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
                {"role": "system", "content": "You rewrite benchmark QA into user-facing Korean answer list items. Return JSON only."},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": 8000,
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


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "user_facing_qa_list_100.jsonl"
    md_path = output_dir / "user_facing_qa_list_100.md"
    jsonl_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    lines = [
        "# OBYBK User-facing QA List 100",
        "",
        f"- generated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "- note: 실제 원자료 실행 결과가 없는 항목은 숫자/순위를 만들지 않고 필요한 입력·정의·검토 조건을 사용자-facing으로 설명한다.",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"{index:03d}. {row['qid']}",
                f"- 질의: {row['question']}",
                f"- 답변: {row['user_answer']}",
                "",
            ]
        )
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate user-facing Q/A list from final benchmark QA JSONL.")
    parser.add_argument("--input-jsonl", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--model")
    args = parser.parse_args(argv)

    source_rows = read_jsonl(args.input_jsonl)
    output_rows: list[dict[str, Any]] = []
    log_path = args.output_dir / "user_facing_batch_log.jsonl"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")
    for batch_index, batch in enumerate(chunks(source_rows, args.batch_size), start=1):
        parsed = call_llm(build_prompt(batch), key_file=args.key_file, model_override=args.model)
        items = parsed.get("items") or []
        if len(items) != len(batch):
            raise RuntimeError(f"batch {batch_index}: expected {len(batch)}, got {len(items)}")
        for source, item in zip(batch, items):
            if str(source.get("qid")) != str(item.get("qid")):
                raise RuntimeError(f"batch {batch_index}: qid mismatch {source.get('qid')} != {item.get('qid')}")
            output_rows.append(
                {
                    "qid": source.get("qid"),
                    "question": source.get("question"),
                    "user_answer": str(item.get("user_answer") or "").strip(),
                    "answerability": source.get("answerability"),
                    "requires_review": source.get("requires_review"),
                }
            )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"batch": batch_index, "count": len(items), "llm": parsed.get("_llm", {})}, ensure_ascii=False) + "\n")
        print(json.dumps({"batch": batch_index, "generated": len(output_rows), "latency_ms": parsed.get("_llm", {}).get("latency_ms")}, ensure_ascii=False), flush=True)
    write_outputs(output_rows, args.output_dir)
    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
