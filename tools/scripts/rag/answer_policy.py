# Timestamp: 2026-05-19 22:22:00

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import re
from typing import Any


class AnswerabilityLabel(str, Enum):
    EXECUTABLE_WITH_DATA = "executable-with-data"
    NEEDS_PARAMETER = "needs-parameter"
    NEEDS_METRIC_DEFINITION = "needs-metric-definition"
    NEEDS_SCHEMA_CONFIRMATION = "needs-schema-confirmation"
    NEEDS_PROVENANCE = "needs-provenance"
    INFERENTIAL_ONLY = "inferential-only"
    NEEDS_HUMAN_REVIEW = "needs-human-review"


@dataclass(frozen=True)
class QuestionPlan:
    task_type: str
    required_parameters: list[str]
    schema_risks: list[str]
    metric_terms: list[str]
    provenance_required: bool
    inferential_terms: list[str]
    human_review_risks: list[str]


@dataclass(frozen=True)
class AnswerPolicyDecision:
    answerability: AnswerabilityLabel
    requires_review: bool
    review_reason: str
    task_type: str
    risk_signals: list[str]
    required_parameters: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["answerability"] = self.answerability.value
        return payload


_PARAMETER_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("date", ("특정 날짜", "날짜", "일자", ":d", "date")),
    ("time", ("특정 시간", "시간대", ":h", "hour", "datetime", "시각")),
    ("period", ("기간", "between", ":t1", ":t2", ":d1", ":d2", "from", "to")),
    ("entity_id", ("특정 대여소", "특정 id", "id", ":id", "식별자", "branchnum")),
    ("month", ("특정 월", "월", "month", "date_ym")),
    ("top_n", ("상위 n", "top n", "limit", "몇 개", "상위")),
)

_SCHEMA_TERMS = (
    "좌표", "좌표계", "단위", "타임존", "timezone", "dst", "시작", "반납", "출발", "도착",
    "역할", "컬럼 의미", "스키마", "결측", "누락", "코드 체계", "성별", "연령", "cnt_rack",
    "branchnum_r", "branchnum_b", "date_bk", "datetime", "hour_cnt", "dist", "iqr", "ilcd",
)

_METRIC_TERMS = (
    "비어감", "급회복", "수요 유지", "유지", "회복력", "민감도", "부족", "과잉", "정비 취약",
    "신뢰도", "급감", "급증", "지연 반응", "lag", "baseline", "임계치", "threshold", "피크",
    "포화", "견딤", "부담", "회전율", "상위 이용", "역할 전환", "편도 쏠림", "불균형",
)

_PROVENANCE_TERMS = (
    "provenance", "confidence", "source priority", "근거 신뢰도", "직접 근거", "추론 근거",
    "direct", "inferred", "rule_id", "same_as", "동일 개체", "alias", "별칭", "온톨로지",
    "ontology", "class", "relation", "edge", "증거 그래프", "evidencegraph",
)

_INFERENTIAL_TERMS = (
    "설명", "가설", "군집", "패턴", "판단 기준", "설계", "커버", "slice", "분류 기준", "어떤 것들",
)

_HUMAN_REVIEW_TERMS = (
    "개인정보", "민감정보", "오탐", "승인", "사람", "운영자", "수동", "검토", "기준 확정", "예외",
)

_AGGREGATION_TERMS = (
    "count", "count(*)", "sum", "avg", "average", "group by", "order by", "limit", "집계", "평균", "합계", "총", "상위", "목록",
)


_DEFAULT_REVIEW_REASONS: dict[AnswerabilityLabel, str] = {
    AnswerabilityLabel.NEEDS_METRIC_DEFINITION: "파생 지표의 산식, baseline, 임계치가 고정되어야 결과가 재현된다.",
    AnswerabilityLabel.NEEDS_SCHEMA_CONFIRMATION: "컬럼 의미, 단위, 역할 또는 시간 경계가 확정되어야 해석이 일관된다.",
    AnswerabilityLabel.NEEDS_PROVENANCE: "직접 근거와 추론 근거를 분리하고 source priority/confidence를 표기해야 한다.",
    AnswerabilityLabel.NEEDS_HUMAN_REVIEW: "자동 산출 후 기준 확정 또는 오탐 검토가 필요하다.",
    AnswerabilityLabel.INFERENTIAL_ONLY: "정확한 단일 수치보다 추론적 설명 또는 설계 판단이 중심이므로 해석 기준을 문서화해야 한다.",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _hits(text: str, terms: tuple[str, ...]) -> list[str]:
    normalized = _norm(text)
    found: list[str] = []
    for term in terms:
        if term.lower() in normalized:
            found.append(term)
    return found


def _parameter_hits(text: str) -> list[str]:
    normalized = _norm(text)
    values: list[str] = []
    for name, patterns in _PARAMETER_PATTERNS:
        if any(pattern.lower() in normalized for pattern in patterns):
            values.append(name)
    return [value for index, value in enumerate(values) if value not in values[:index]]


def _task_type(question: str, category: str | None = None) -> str:
    text = _norm(" ".join([question, category or ""]))
    if any(term in text for term in ("provenance", "confidence", "source priority", "근거 신뢰도", "직접 근거", "추론 근거")):
        return "provenance"
    if any(term in text for term in ("조인", "join", "연결", "관계", "relation")):
        return "join_relation"
    if any(term in text for term in _METRIC_TERMS):
        return "metric_definition"
    if "group by" in text or "별" in text or "매트릭스" in text:
        return "groupby"
    if "상위" in text or "top" in text or "limit" in text:
        return "topk"
    if "평균" in text or "avg" in text:
        return "avg"
    if "합" in text or "sum" in text or "총" in text:
        return "sum"
    if "수" in text or "count" in text or "몇" in text:
        return "count"
    if any(term in text for term in ("목록", "프로필", "보여줘", "lookup")):
        return "lookup"
    return "general"


def plan_question(question: str, category: str | None = None, fields: list[str] | None = None) -> QuestionPlan:
    field_text = " ".join(fields or [])
    full_text = " ".join([question, category or "", field_text])
    return QuestionPlan(
        task_type=_task_type(question, category),
        required_parameters=_parameter_hits(full_text),
        schema_risks=_hits(full_text, _SCHEMA_TERMS),
        metric_terms=_hits(full_text, _METRIC_TERMS),
        provenance_required=bool(_hits(full_text, _PROVENANCE_TERMS)),
        inferential_terms=_hits(full_text, _INFERENTIAL_TERMS),
        human_review_risks=_hits(full_text, _HUMAN_REVIEW_TERMS),
    )


def decide_answer_policy(question: str, category: str | None = None, fields: list[str] | None = None) -> AnswerPolicyDecision:
    plan = plan_question(question, category, fields)
    risk_signals: list[str] = []

    if plan.human_review_risks and not (plan.metric_terms or plan.schema_risks or plan.provenance_required):
        label = AnswerabilityLabel.NEEDS_HUMAN_REVIEW
        risk_signals = plan.human_review_risks
    elif plan.provenance_required:
        label = AnswerabilityLabel.NEEDS_PROVENANCE
        risk_signals = _hits(" ".join([question, category or ""]), _PROVENANCE_TERMS) or ["provenance/confidence"]
    elif plan.schema_risks and plan.task_type in {"lookup", "sum", "avg", "count", "groupby", "topk", "join_relation", "general"}:
        label = AnswerabilityLabel.NEEDS_SCHEMA_CONFIRMATION
        risk_signals = plan.schema_risks
    elif plan.metric_terms or plan.task_type == "metric_definition":
        label = AnswerabilityLabel.NEEDS_METRIC_DEFINITION
        risk_signals = plan.metric_terms or ["metric definition"]
    elif plan.inferential_terms and plan.task_type == "general":
        label = AnswerabilityLabel.INFERENTIAL_ONLY
        risk_signals = plan.inferential_terms
    elif plan.required_parameters:
        label = AnswerabilityLabel.NEEDS_PARAMETER
        risk_signals = plan.required_parameters
    elif plan.task_type in {"count", "sum", "avg", "groupby", "topk", "lookup"} or _hits(question, _AGGREGATION_TERMS):
        label = AnswerabilityLabel.EXECUTABLE_WITH_DATA
    else:
        label = AnswerabilityLabel.EXECUTABLE_WITH_DATA

    requires_review = label in {
        AnswerabilityLabel.NEEDS_METRIC_DEFINITION,
        AnswerabilityLabel.NEEDS_SCHEMA_CONFIRMATION,
        AnswerabilityLabel.NEEDS_PROVENANCE,
        AnswerabilityLabel.NEEDS_HUMAN_REVIEW,
        AnswerabilityLabel.INFERENTIAL_ONLY,
    }
    review_reason = _DEFAULT_REVIEW_REASONS.get(label, "") if requires_review else ""
    return AnswerPolicyDecision(
        answerability=label,
        requires_review=requires_review,
        review_reason=review_reason,
        task_type=plan.task_type,
        risk_signals=risk_signals[:8],
        required_parameters=plan.required_parameters,
    )
