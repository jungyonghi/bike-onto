# Timestamp: 2026-05-18 17:30:00

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import statistics
import textwrap
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont

try:
    from .rag_llm_answer_endpoint import create_rag_llm_answer_app, read_jsonl
except ImportError:  # Allow direct script execution.
    from rag_llm_answer_endpoint import create_rag_llm_answer_app, read_jsonl


LlmCallable = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class RagLlmAnswerReportResult:
    output_dir: Path
    report_path: Path
    responses_jsonl_path: Path
    summary_json_path: Path
    screenshot_dir: Path
    screenshot_paths: list[Path]
    question_count: int
    screenshot_count: int


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    if bold:
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            *candidates,
        ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrap_text(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for raw_line in str(text).splitlines() or [""]:
        if not raw_line:
            lines.append("")
        else:
            lines.extend(textwrap.wrap(raw_line, width=width, replace_whitespace=False, drop_whitespace=True) or [raw_line])
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    *,
    font_obj: ImageFont.ImageFont,
    fill: str,
    wrap: int,
    max_lines: int | None = None,
    line_gap: int = 7,
) -> int:
    x, y = xy
    lines = wrap_text(text, wrap)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [lines[max_lines - 1][: max(0, wrap - 3)] + "..."]
    for line in lines:
        draw.text((x, y), line, font=font_obj, fill=fill)
        bbox = draw.textbbox((x, y), line or "A", font=font_obj)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


def feedback(payload: dict[str, Any]) -> str:
    if payload.get("llm", {}).get("mode") != "live":
        return "LLM live 호출이 아니므로 API key/모델 설정을 확인한 뒤 live mode로 재측정한다."
    if payload.get("contract_pass") and payload.get("requires_review"):
        return "RAG 답변과 계약은 통과했다. 추천/조치가 포함되어 사람 검토·승인 경계를 유지한다."
    if payload.get("contract_pass"):
        return "RAG 답변과 계약은 통과했다. 자동 응답 후보로 유지 가능하지만 근거 citation은 계속 표시한다."
    return "계약 미통과 항목이 있어 prompt schema, relation context, review boundary를 보강해야 한다."


def make_screenshot(path: Path, payload: dict[str, Any], question_id: str) -> None:
    width, height = 1400, 920
    image = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(image)
    title_font = font(34, bold=True)
    h_font = font(23, bold=True)
    body_font = font(18)
    small_font = font(15)

    draw.rectangle((0, 0, width, 90), fill="#111827")
    draw.text((36, 25), f"General RAG 기반 LLM 답변 - {question_id}", font=title_font, fill="white")
    badge = "PASS" if payload.get("contract_pass") else "CHECK"
    badge_color = "#16a34a" if payload.get("contract_pass") else "#dc2626"
    draw.rounded_rectangle((1190, 24, 1345, 64), radius=14, fill=badge_color)
    draw.text((1232, 34), badge, font=small_font, fill="white")

    left_x, right_x = 42, 850
    y = 120
    draw.text((left_x, y), "질문", font=h_font, fill="#111827")
    y = draw_wrapped(draw, payload.get("question", ""), (left_x, y + 34), font_obj=body_font, fill="#111827", wrap=58, max_lines=3)

    y += 14
    draw.text((left_x, y), "RAG 최종 답변", font=h_font, fill="#111827")
    y = draw_wrapped(draw, payload.get("answer", ""), (left_x, y + 34), font_obj=body_font, fill="#0f172a", wrap=72, max_lines=8)

    y += 14
    draw.text((left_x, y), "검토/승인 경계", font=h_font, fill="#111827")
    review_text = f"requires_review={payload.get('requires_review')} | {payload.get('review_reason', '')}"
    y = draw_wrapped(draw, review_text, (left_x, y + 34), font_obj=body_font, fill="#7c2d12", wrap=74, max_lines=3)

    y += 14
    draw.text((left_x, y), "피드백", font=h_font, fill="#111827")
    draw_wrapped(draw, feedback(payload), (left_x, y + 34), font_obj=body_font, fill="#1d4ed8", wrap=74, max_lines=4)

    draw.rounded_rectangle((right_x, 120, 1354, 840), radius=16, fill="white", outline="#cbd5e1", width=2)
    draw.text((right_x + 26, 146), "검색/LLM 메타", font=h_font, fill="#111827")
    meta_lines = [
        f"llm_mode: {payload.get('llm', {}).get('mode')}",
        f"model: {payload.get('llm', {}).get('model')}",
        f"llm_latency_ms: {payload.get('llm', {}).get('latency_ms')}",
        f"retrieval_latency_ms: {payload.get('retrieval', {}).get('latency_ms')}",
        f"top_k: {payload.get('retrieval', {}).get('top_k')}",
    ]
    ry = 190
    for line in meta_lines:
        draw.text((right_x + 40, ry), f"• {line}", font=body_font, fill="#334155")
        ry += 30

    ry += 12
    draw.text((right_x + 26, ry), "근거 문서", font=h_font, fill="#111827")
    ry += 34
    for doc in (payload.get("evidence_documents") or [])[:6]:
        ry = draw_wrapped(draw, f"- {doc}", (right_x + 40, ry), font_obj=small_font, fill="#334155", wrap=48, max_lines=2, line_gap=4)

    ry += 12
    draw.text((right_x + 26, ry), "후보/정량 지표", font=h_font, fill="#111827")
    ry += 34
    for candidate in (payload.get("candidate_set") or [])[:3]:
        ry = draw_wrapped(
            draw,
            f"후보 {candidate.get('rank')}: {candidate.get('candidate_id')} score={candidate.get('score')}",
            (right_x + 40, ry),
            font_obj=small_font,
            fill="#475569",
            wrap=50,
            max_lines=2,
            line_gap=4,
        )
    for metric in (payload.get("quantitative_indicators") or [])[:4]:
        ry = draw_wrapped(
            draw,
            f"{metric.get('metric')}={metric.get('value')} ({metric.get('source')})",
            (right_x + 40, ry),
            font_obj=small_font,
            fill="#475569",
            wrap=50,
            max_lines=2,
            line_gap=4,
        )

    ry += 12
    draw.text((right_x + 26, ry), "발췌 목록", font=h_font, fill="#111827")
    ry += 34
    for excerpt in (payload.get("evidence_excerpt_list") or [])[:3]:
        ry = draw_wrapped(
            draw,
            f"{excerpt.get('source')} | {str(excerpt.get('excerpt', ''))[:100]}",
            (right_x + 40, ry),
            font_obj=small_font,
            fill="#475569",
            wrap=50,
            max_lines=2,
            line_gap=4,
        )

    draw.text((42, 880), "# Timestamp: 2026-05-18 17:30:00", font=small_font, fill="#64748b")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def build_rag_llm_answer_report(
    *,
    runtime_answers_path: Path | str,
    pgvector_seed_path: Path | str,
    output_dir: Path | str,
    llm_callable: LlmCallable | None = None,
    key_file: Path | str | None = None,
    top_k: int = 3,
    limit: int | None = None,
) -> RagLlmAnswerReportResult:
    runtime_answers_path = Path(runtime_answers_path)
    pgvector_seed_path = Path(pgvector_seed_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir = output_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(runtime_answers_path)
    if limit is not None:
        rows = rows[:limit]
    app_kwargs: dict[str, Any] = {
        "runtime_answers_path": runtime_answers_path,
        "pgvector_seed_path": pgvector_seed_path,
        "llm_callable": llm_callable,
    }
    if key_file is not None:
        app_kwargs["key_file"] = Path(key_file)
    app = create_rag_llm_answer_app(**app_kwargs)

    from fastapi.testclient import TestClient

    client = TestClient(app)
    responses: list[dict[str, Any]] = []
    screenshot_paths: list[Path] = []
    for index, row in enumerate(rows, start=1):
        question_id = str(row.get("id") or row.get("question_id") or f"Q-{index:03d}")
        question = str(row.get("question") or "")
        response = client.post("/rag-answer", json={"question": question, "top_k": top_k})
        payload = response.json()
        payload["question_id"] = question_id
        payload["http_status_code"] = response.status_code
        payload["feedback"] = feedback(payload)
        screenshot_path = screenshot_dir / f"{question_id}.png"
        make_screenshot(screenshot_path, payload, question_id)
        payload["screenshot_path"] = str(screenshot_path)
        responses.append(payload)
        screenshot_paths.append(screenshot_path)

    responses_jsonl = output_dir / "rag_llm_answer_responses.jsonl"
    responses_jsonl.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in responses), encoding="utf-8")

    llm_latencies = [float(row.get("llm", {}).get("latency_ms") or 0) for row in responses]
    summary = {
        "timestamp": "2026-05-18 17:30:00",
        "question_count": len(responses),
        "screenshot_count": len(screenshot_paths),
        "contract_pass_count": sum(1 for row in responses if row.get("contract_pass")),
        "live_llm_count": sum(1 for row in responses if row.get("llm", {}).get("mode") == "live"),
        "fallback_count": sum(1 for row in responses if row.get("llm", {}).get("mode") != "live"),
        "review_required_count": sum(1 for row in responses if row.get("requires_review")),
        "llm_latency_ms": {
            "min": min(llm_latencies) if llm_latencies else None,
            "max": max(llm_latencies) if llm_latencies else None,
            "mean": statistics.mean(llm_latencies) if llm_latencies else None,
            "median": statistics.median(llm_latencies) if llm_latencies else None,
        },
    }
    summary_json = output_dir / "rag_llm_answer_summary.json"
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_path = output_dir / "rag_llm_answer_report.md"
    lines: list[str] = [
        "# Timestamp: 2026-05-18 17:30:00",
        "",
        "# General RAG 기반 LLM 답변 보고서",
        "",
        "## 1. 요약",
        "",
        f"- 질문 수: `{summary['question_count']}`",
        f"- 스크린샷 수: `{summary['screenshot_count']}`",
        f"- live LLM 호출: `{summary['live_llm_count']}`",
        f"- fallback 응답: `{summary['fallback_count']}`",
        f"- contract pass: `{summary['contract_pass_count']}/{summary['question_count']}`",
        f"- review-required: `{summary['review_required_count']}/{summary['question_count']}`",
        "",
        "> 이 보고서는 단순 위치 확인이 아니라 `질문 → RAG 검색 → context 구성 → LLM grounded answer 생성 → 근거/피드백 기록` 흐름의 산출물이다.",
        "",
        "## 2. 질문별 RAG 기반 LLM 답변",
        "",
    ]
    for payload in responses:
        screenshot_rel = Path(payload["screenshot_path"]).relative_to(output_dir)
        lines.extend(
            [
                f"### {payload['question_id']}",
                "",
                f"![{payload['question_id']}]({screenshot_rel.as_posix()})",
                "",
                "#### 질문",
                "",
                payload.get("question", ""),
                "",
                "#### RAG 기반 LLM 답변",
                "",
                payload.get("answer", ""),
                "",
                "#### 엔티티 상세 상태",
                "",
                *(f"- `{card.get('id')}` ({card.get('type')}): label=`{card.get('label')}`, detail_status=`{card.get('detail_status')}`, missing={card.get('missing_detail_notes')}" for card in (payload.get("entity_cards") or [])[:8]),
                "",
                "#### 후보 목록",
                "",
                *(f"- rank `{candidate.get('rank')}`: `{candidate.get('candidate_id')}`, score=`{candidate.get('score')}`, source=`{candidate.get('source_metric')}`, note={candidate.get('note')}" for candidate in (payload.get("candidate_set") or [])[:10]),
                "",
                "#### 정량 지표",
                "",
                *(f"- `{metric.get('metric')}` = `{metric.get('value')}` (source=`{metric.get('source')}`)" for metric in (payload.get("quantitative_indicators") or [])[:20]),
                "",
                "#### 데이터 공백 / 다음 분석",
                "",
                *(f"- {gap}" for gap in (payload.get("data_gaps") or [])[:8]),
                "",
                "#### 발췌 목록",
                "",
                *(f"- `{item.get('source')}` ({item.get('kind')}, score=`{item.get('score')}`): {str(item.get('excerpt', ''))[:300]}" for item in (payload.get("evidence_excerpt_list") or [])[:12]),
                "",
                "#### 사용 근거 파일",
                "",
                *(f"- `{doc}`" for doc in (payload.get("evidence_documents") or [])[:8]),
                "",
                "#### 검색 Context",
                "",
                *(f"- `{match.get('id')}` score=`{match.get('score')}` content={str(match.get('content', ''))[:180]}" for match in (payload.get("retrieval", {}).get("matches") or [])[:5]),
                "",
                "#### 실행 메타",
                "",
                f"- llm_mode: `{payload.get('llm', {}).get('mode')}`",
                f"- model: `{payload.get('llm', {}).get('model')}`",
                f"- llm_latency_ms: `{payload.get('llm', {}).get('latency_ms')}`",
                f"- retrieval_latency_ms: `{payload.get('retrieval', {}).get('latency_ms')}`",
                f"- contract_pass: `{payload.get('contract_pass')}`",
                f"- requires_review: `{payload.get('requires_review')}`",
                "",
                "#### 피드백",
                "",
                f"- {payload.get('feedback')}",
                "",
            ]
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return RagLlmAnswerReportResult(
        output_dir=output_dir,
        report_path=report_path,
        responses_jsonl_path=responses_jsonl,
        summary_json_path=summary_json,
        screenshot_dir=screenshot_dir,
        screenshot_paths=screenshot_paths,
        question_count=len(responses),
        screenshot_count=len(screenshot_paths),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate RAG-based LLM answers and per-question screenshot report.")
    parser.add_argument("--runtime-answers", required=True, type=Path)
    parser.add_argument("--pgvector-seed", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    result = build_rag_llm_answer_report(
        runtime_answers_path=args.runtime_answers,
        pgvector_seed_path=args.pgvector_seed,
        output_dir=args.output_dir,
        key_file=args.key_file,
        top_k=args.top_k,
        limit=args.limit,
    )
    print(
        json.dumps(
            {
                "question_count": result.question_count,
                "screenshot_count": result.screenshot_count,
                "report_path": str(result.report_path),
                "responses_jsonl_path": str(result.responses_jsonl_path),
                "summary_json_path": str(result.summary_json_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
