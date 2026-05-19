# Timestamp: 2026-05-19 22:28:00

from __future__ import annotations

from pathlib import Path
import sys

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.answer_policy import AnswerabilityLabel, decide_answer_policy  # noqa: E402


def test_answer_policy_separates_simple_execution_from_review() -> None:
    decision = decide_answer_policy("특정 기간 총 대여 건수는 몇 건인가? rentt BETWEEN :t1 AND :t2 후 COUNT(*)")

    assert decision.answerability == AnswerabilityLabel.NEEDS_PARAMETER
    assert decision.requires_review is False
    assert decision.review_reason == ""
    assert "period" in decision.required_parameters


def test_answer_policy_marks_metric_definition_without_data_execution_confusion() -> None:
    decision = decide_answer_policy("비가 그친 뒤 수요가 급회복되는 지점을 찾고 baseline 대비 회복률을 계산하라")

    assert decision.answerability == AnswerabilityLabel.NEEDS_METRIC_DEFINITION
    assert decision.requires_review is True
    assert "baseline" in " ".join(decision.risk_signals).lower() or decision.risk_signals
    assert "지표" in decision.review_reason or "baseline" in decision.review_reason


def test_answer_policy_marks_schema_confirmation_for_role_and_unit_risks() -> None:
    decision = decide_answer_policy("branchnum_r와 branchnum_b를 이용해 시작/반납 역할별 집계를 비교하라")

    assert decision.answerability == AnswerabilityLabel.NEEDS_SCHEMA_CONFIRMATION
    assert decision.requires_review is True
    assert "역할" in decision.review_reason or "컬럼" in decision.review_reason


def test_answer_policy_marks_provenance_when_direct_and_inferred_evidence_are_required() -> None:
    decision = decide_answer_policy("직접 근거와 추론 근거를 분리해 confidence와 source priority를 표시해야 하는 질문은 무엇인가?")

    assert decision.answerability == AnswerabilityLabel.NEEDS_PROVENANCE
    assert decision.requires_review is True
    assert "confidence" in decision.review_reason
