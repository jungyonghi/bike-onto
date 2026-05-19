# Timestamp: 2026-05-18 17:10:00

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import statistics
import textwrap
import time
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont

try:
    from .ontology_rag_fastapi_app import create_app
except ImportError:  # Allow direct script execution.
    from ontology_rag_fastapi_app import create_app


@dataclass(frozen=True)
class QuestionEvaluationResult:
    id: str
    question: str
    contract_pass: bool
    requires_review: bool
    top1_id: str | None
    topk_ids: list[str]
    top1_hit: bool
    topk_hit: bool
    api_status_code: int
    latency_ms: float
    feedback: str
    screenshot_path: Path


@dataclass(frozen=True)
class PerQuestionEvaluationReportResult:
    output_dir: Path
    report_path: Path
    results_jsonl_path: Path
    summary_json_path: Path
    screenshot_dir: Path
    screenshot_paths: list[Path]
    question_count: int
    screenshot_count: int


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_no}")
        rows.append(payload)
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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


def _wrap_text(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for raw_line in str(text).splitlines() or [""]:
        if not raw_line:
            lines.append("")
            continue
        # textwrap counts Korean as one char; acceptable for fixed screenshot cards.
        lines.extend(textwrap.wrap(raw_line, width=width, replace_whitespace=False, drop_whitespace=True) or [raw_line])
    return lines


def _draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], *, font: ImageFont.ImageFont, fill: str, wrap: int, line_gap: int = 8, max_lines: int | None = None) -> int:
    x, y = xy
    lines = _wrap_text(text, wrap)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [lines[max_lines - 1][: max(0, wrap - 3)] + "..."]
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line or "A", font=font)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


def _feedback(row: dict[str, Any], top1_id: str | None, topk_ids: list[str], status_code: int) -> str:
    question_id = str(row.get("id") or row.get("question_id") or "")
    contract_pass = bool(row.get("contract_pass"))
    requires_review = bool(row.get("requires_review"))
    if status_code != 200:
        return "API 호출 실패: FastAPI route와 입력 payload를 먼저 확인해야 한다."
    if not topk_ids:
        return "검색 결과 없음: pgvector seed와 query embedding 생성 경로를 점검해야 한다."
    if top1_id == question_id and contract_pass:
        base = "유지: top-1 검색과 answer contract가 모두 통과했다."
    elif question_id in topk_ids and contract_pass:
        base = "개선 필요: expected question은 top-k에 있으나 top-1은 아니므로 ranking 보정이 필요하다."
    elif contract_pass:
        base = "검색 개선 필요: answer contract는 통과했지만 expected question이 top-k에 없어 retrieval 품질 보강이 필요하다."
    else:
        base = "계약 개선 필요: answer contract 또는 필수 근거 필드가 부족하다."
    if requires_review:
        base += " 사람 검토·승인 플래그는 유지한다."
    else:
        base += " 자동 응답 후보로 유지 가능하다."
    return base


def _make_screenshot(path: Path, row: dict[str, Any], result_payload: dict[str, Any], eval_result: dict[str, Any]) -> None:
    width = 1280
    height = 760
    image = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(image)
    title_font = _font(34, bold=True)
    h_font = _font(22, bold=True)
    body_font = _font(19)
    small_font = _font(16)

    draw.rectangle((0, 0, width, 86), fill="#0f172a")
    draw.text((36, 24), f"OBYBK Question Evaluation - {eval_result['id']}", font=title_font, fill="white")

    badge_color = "#16a34a" if eval_result["contract_pass"] else "#dc2626"
    draw.rounded_rectangle((1010, 22, 1235, 62), radius=12, fill=badge_color)
    draw.text((1030, 31), f"contract={eval_result['contract_pass']}", font=small_font, fill="white")

    y = 112
    draw.text((42, y), "질문", font=h_font, fill="#111827")
    y = _draw_wrapped(draw, str(row.get("question") or ""), (42, y + 34), font=body_font, fill="#111827", wrap=58, max_lines=3)

    y += 12
    draw.text((42, y), "실험 결과", font=h_font, fill="#111827")
    y += 36
    metrics = [
        f"API status: {eval_result['api_status_code']}",
        f"latency_ms: {eval_result['latency_ms']:.2f}",
        f"top1_id: {eval_result['top1_id']}",
        f"topk_ids: {', '.join(eval_result['topk_ids'])}",
        f"top1_hit: {eval_result['top1_hit']} / topk_hit: {eval_result['topk_hit']}",
        f"requires_review: {eval_result['requires_review']}",
    ]
    for metric in metrics:
        draw.text((64, y), f"• {metric}", font=body_font, fill="#1f2937")
        y += 32

    y += 8
    draw.text((42, y), "답변 요약", font=h_font, fill="#111827")
    y = _draw_wrapped(draw, str(row.get("answer") or ""), (42, y + 34), font=body_font, fill="#111827", wrap=72, max_lines=4)

    y += 10
    draw.text((42, y), "피드백", font=h_font, fill="#111827")
    y = _draw_wrapped(draw, eval_result["feedback"], (42, y + 34), font=body_font, fill="#7c2d12", wrap=76, max_lines=4)

    # Right panel with top matches.
    draw.rounded_rectangle((760, 112, 1238, 690), radius=16, fill="white", outline="#cbd5e1", width=2)
    draw.text((786, 136), "Top-k Matches", font=h_font, fill="#111827")
    match_y = 178
    for index, match in enumerate((result_payload.get("matches") or [])[:5], start=1):
        match_text = f"{index}. {match.get('id')} score={match.get('score')} review={match.get('requires_review')}"
        draw.text((786, match_y), match_text, font=small_font, fill="#0f172a")
        match_y += 28
        content = str(match.get("content") or "")
        match_y = _draw_wrapped(draw, content, (806, match_y), font=small_font, fill="#475569", wrap=38, line_gap=5, max_lines=3)
        match_y += 14

    draw.text((42, 718), "# Timestamp: 2026-05-18 17:10:00", font=small_font, fill="#64748b")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _empty_ml_features(output_dir: Path) -> Path:
    path = output_dir / "_empty_ml_features.jsonl"
    path.write_text("", encoding="utf-8")
    return path


def build_per_question_evaluation_report(
    *,
    runtime_answers_path: Path | str,
    pgvector_seed_path: Path | str,
    output_dir: Path | str,
    ml_feature_table_path: Path | str | None = None,
    top_k: int = 3,
) -> PerQuestionEvaluationReportResult:
    runtime_answers_path = Path(runtime_answers_path)
    pgvector_seed_path = Path(pgvector_seed_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir = output_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    if ml_feature_table_path is None:
        ml_feature_table_path = _empty_ml_features(output_dir)
    else:
        ml_feature_table_path = Path(ml_feature_table_path)

    rows = _read_jsonl(runtime_answers_path)
    app = create_app(
        runtime_answers_path=runtime_answers_path,
        ml_feature_table_path=ml_feature_table_path,
        pgvector_seed_path=pgvector_seed_path,
    )
    from fastapi.testclient import TestClient

    client = TestClient(app)
    eval_results: list[dict[str, Any]] = []
    screenshot_paths: list[Path] = []

    for row in rows:
        question_id = str(row.get("id") or row.get("question_id") or f"Q-{len(eval_results)+1:03d}")
        question = str(row.get("question") or row.get("query") or "")
        start = time.perf_counter()
        response = client.post("/query", json={"question": question, "top_k": top_k})
        latency_ms = (time.perf_counter() - start) * 1000
        payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"matches": []}
        matches = payload.get("matches") or []
        topk_ids = [str(match.get("id")) for match in matches if match.get("id") is not None]
        top1_id = topk_ids[0] if topk_ids else None
        eval_result = {
            "id": question_id,
            "question": question,
            "contract_pass": bool(row.get("contract_pass")),
            "requires_review": bool(row.get("requires_review")),
            "top1_id": top1_id,
            "topk_ids": topk_ids,
            "top1_hit": top1_id == question_id,
            "topk_hit": question_id in topk_ids,
            "api_status_code": response.status_code,
            "latency_ms": round(latency_ms, 3),
            "feedback": _feedback(row, top1_id, topk_ids, response.status_code),
        }
        screenshot_path = screenshot_dir / f"{question_id}.png"
        _make_screenshot(screenshot_path, row, payload, eval_result)
        eval_result["screenshot_path"] = str(screenshot_path)
        eval_results.append(eval_result)
        screenshot_paths.append(screenshot_path)

    results_jsonl = output_dir / "per_question_evaluation_results.jsonl"
    results_jsonl.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in eval_results), encoding="utf-8")

    latencies = [float(row["latency_ms"]) for row in eval_results]
    summary = {
        "timestamp": "2026-05-18 17:10:00",
        "question_count": len(eval_results),
        "screenshot_count": len(screenshot_paths),
        "contract_pass_count": sum(1 for row in eval_results if row["contract_pass"]),
        "top1_hit_count": sum(1 for row in eval_results if row["top1_hit"]),
        "topk_hit_count": sum(1 for row in eval_results if row["topk_hit"]),
        "review_required_count": sum(1 for row in eval_results if row["requires_review"]),
        "latency_ms": {
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
            "mean": statistics.mean(latencies) if latencies else None,
            "median": statistics.median(latencies) if latencies else None,
        },
    }
    summary_json = output_dir / "per_question_evaluation_summary.json"
    _write_json(summary_json, summary)

    report_path = output_dir / "per_question_evaluation_report.md"
    markdown: list[str] = [
        "# Timestamp: 2026-05-18 17:10:00",
        "",
        "# OBYBK 질문별 실험 및 피드백 보고서",
        "",
        "## 1. 요약",
        "",
        f"- 평가 질문 수: `{summary['question_count']}`",
        f"- 스크린샷 수: `{summary['screenshot_count']}`",
        f"- contract pass: `{summary['contract_pass_count']}/{summary['question_count']}`",
        f"- top-1 hit: `{summary['top1_hit_count']}/{summary['question_count']}`",
        f"- top-k hit: `{summary['topk_hit_count']}/{summary['question_count']}`",
        f"- review-required: `{summary['review_required_count']}/{summary['question_count']}`",
        "",
        "> 현재 평가는 smoke용 vector(16) 및 FastAPI JSONL adapter 기준이다. production embedding/DB mode 전환 후 같은 보고서 형식으로 재측정한다.",
        "",
        "## 2. 질문별 실험 결과",
        "",
    ]
    for result in eval_results:
        screenshot_rel = Path(result["screenshot_path"]).relative_to(output_dir)
        markdown.extend(
            [
                f"### {result['id']}",
                "",
                f"![{result['id']}]({screenshot_rel.as_posix()})",
                "",
                "#### 실험 결과",
                "",
                f"- 질문: {result['question']}",
                f"- API status: `{result['api_status_code']}`",
                f"- latency_ms: `{result['latency_ms']}`",
                f"- top1_id: `{result['top1_id']}`",
                f"- topk_ids: `{', '.join(result['topk_ids'])}`",
                f"- top1_hit: `{result['top1_hit']}`",
                f"- topk_hit: `{result['topk_hit']}`",
                f"- contract_pass: `{result['contract_pass']}`",
                f"- requires_review: `{result['requires_review']}`",
                "",
                "#### 피드백",
                "",
                f"- {result['feedback']}",
                "",
            ]
        )
    report_path.write_text("\n".join(markdown), encoding="utf-8")

    return PerQuestionEvaluationReportResult(
        output_dir=output_dir,
        report_path=report_path,
        results_jsonl_path=results_jsonl,
        summary_json_path=summary_json,
        screenshot_dir=screenshot_dir,
        screenshot_paths=screenshot_paths,
        question_count=len(eval_results),
        screenshot_count=len(screenshot_paths),
    )


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate per-question OBYBK evaluation screenshots and Markdown report.")
    parser.add_argument("--runtime-answers", required=True, type=Path)
    parser.add_argument("--pgvector-seed", required=True, type=Path)
    parser.add_argument("--ml-features", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = build_per_question_evaluation_report(
        runtime_answers_path=args.runtime_answers,
        pgvector_seed_path=args.pgvector_seed,
        ml_feature_table_path=args.ml_features,
        output_dir=args.output_dir,
        top_k=args.top_k,
    )
    print(
        json.dumps(
            {
                "question_count": result.question_count,
                "screenshot_count": result.screenshot_count,
                "report_path": str(result.report_path),
                "summary_json_path": str(result.summary_json_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
