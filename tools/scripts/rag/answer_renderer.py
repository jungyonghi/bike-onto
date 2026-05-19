# Timestamp: 2026-05-18 22:42:00

from __future__ import annotations

from typing import Any

try:
    from .schemas import AnswerDraft, RecommendedAction
except ImportError:  # Allow direct script execution.
    from schemas import AnswerDraft, RecommendedAction


_DEBUG_KEYS = [
    "retrieved_context_count",
    "evidence_document_count",
    "related_object_count",
    "related_relation_count",
    "top1_retrieval_score",
    "top1_token_overlap",
]


def _approval_text(action: RecommendedAction) -> str:
    if action.requires_human_approval:
        return "사람 검토 필요"
    if action.auto_executable:
        return "자동 실행 가능"
    return "자동 실행 금지"


def _render_action(action: RecommendedAction) -> list[str]:
    lines = [
        f"- 대상: {action.target or '현재 근거에서 특정 대상 미확정'}",
        f"- 조치: {action.action}",
        f"- 이유: {action.reason}",
        f"- 승인 필요 여부: {_approval_text(action)}",
    ]
    if action.risk:
        lines.append(f"- 위험 요소: {action.risk}")
    return lines


def render_debug_section(debug: dict[str, Any] | None) -> str:
    if not debug:
        debug = {}
    lines = ["## 디버깅 정보"]
    for key in _DEBUG_KEYS:
        lines.append(f"- {key}: {debug.get(key)}")
    return "\n".join(lines)


def render_answer_draft(draft: AnswerDraft, *, debug_mode: bool = False) -> str:
    lines: list[str] = ["## 답변", draft.answer.strip() or "현재 근거를 바탕으로 우선 확인이 필요합니다.", "", "## 근거 기반 판단"]
    if draft.evidence_based_judgment:
        lines.extend(f"- {item}" for item in draft.evidence_based_judgment)
    else:
        lines.append("- 현재 검색 근거에서 판단에 필요한 핵심 사실이 충분히 구조화되지 않았습니다.")

    lines.extend(["", "## 권장 조치"])
    if draft.recommended_actions:
        for index, action in enumerate(draft.recommended_actions):
            if index:
                lines.append("")
            lines.extend(_render_action(action))
    else:
        lines.extend(
            [
                "- 대상: 현재 근거에서 특정 조치 대상 미확정",
                "- 조치: 추가 근거를 확인한 뒤 운영자가 조치 여부를 결정합니다.",
                "- 이유: 자동 실행에 필요한 대상·조건·위험 정보가 충분하지 않습니다.",
                "- 승인 필요 여부: 사람 검토 필요",
            ]
        )

    lines.extend(["", "## 추가 확인 필요"])
    if draft.additional_checks:
        lines.extend(f"- {item}" for item in draft.additional_checks)
    else:
        lines.append("- 판단 확정을 위한 기간, 대상, 지표, 데이터 품질 상태를 추가 확인해야 합니다.")

    lines.extend(["", "## 답변 한계", draft.limitations.strip() or "현재 context만으로는 원인과 실행 결과를 확정할 수 없습니다."])

    if debug_mode:
        lines.extend(["", render_debug_section(draft.debug)])
    return "\n".join(lines).rstrip() + "\n"


def append_debug_if_enabled(markdown: str, debug: dict[str, Any] | None, *, debug_mode: bool = False) -> str:
    if not debug_mode:
        return markdown.rstrip() + "\n"
    return markdown.rstrip() + "\n\n" + render_debug_section(debug) + "\n"
