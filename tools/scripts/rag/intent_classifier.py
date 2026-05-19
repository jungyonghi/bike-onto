# Timestamp: 2026-05-18 22:42:00

from __future__ import annotations

import re

try:
    from .schemas import AnswerProfile
except ImportError:  # Allow direct script execution.
    from schemas import AnswerProfile


_CATEGORY_PATTERNS: list[tuple[AnswerProfile, tuple[str, ...]]] = [
    (AnswerProfile.OPERATIONS_MONITORING, ("운영모니터링", "operations_monitoring")),
    (AnswerProfile.INCIDENT_QUALITY, ("장애/품질", "장애품질", "incident_quality")),
    (AnswerProfile.DEMAND_USAGE_ANALYSIS, ("수요/이용량분석", "수요이용량분석", "demand_usage_analysis")),
    (AnswerProfile.RECOMMENDATION_REBALANCING, ("추천/재배치/우선순위", "추천재배치우선순위", "recommendation_rebalancing")),
    (AnswerProfile.DATA_SCHEMA, ("데이터/스키마/근거", "데이터스키마근거", "data_schema")),
    (AnswerProfile.EVALUATION_VALIDATION, ("평가/검증", "평가검증", "evaluation_validation")),
    (AnswerProfile.SECURITY_GOVERNANCE, ("보안/권한/운영통제", "보안권한운영통제", "security_governance")),
    (AnswerProfile.PM_REPORTING, ("서비스/pm/보고", "서비스pm보고", "pm_reporting")),
    (AnswerProfile.API_DB_PERFORMANCE, ("api/db/성능", "apidb성능", "api_db_performance")),
    (AnswerProfile.ML_FORECASTING, ("ml/예측/확장", "ml예측확장", "ml_forecasting")),
]

_KEYWORD_PATTERNS: list[tuple[AnswerProfile, tuple[str, ...]]] = [
    (AnswerProfile.API_DB_PERFORMANCE, ("latency", "response time", "p95", "p99", "p50", "api", "endpoint", "db", "database", "query", "vector search", "reranking", "serialization", "검색 지연", "응답 시간", "처리 시간", "성능", "느려")),
    (AnswerProfile.SECURITY_GOVERNANCE, ("권한", "보안", "접근", "로그", "감사", "승인", "운영통제", "security", "permission", "audit", "access")),
    (AnswerProfile.ML_FORECASTING, ("예측", "feature", "모델", "ml", "machine learning", "forecast", "baseline", "이상탐지")),
    (AnswerProfile.EVALUATION_VALIDATION, ("평가", "검증", "지표", "정답률", "테스트", "회귀", "validation", "evaluation", "metric", "accuracy")),
    (AnswerProfile.DATA_SCHEMA, ("테이블", "필드", "컬럼", "스키마", "조인", "데이터셋", "근거 파일", "schema", "table", "column", "join")),
    (AnswerProfile.DEMAND_USAGE_ANALYSIS, ("이용량", "수요", "전일 대비", "증감률", "평균 대비", "동일 요일", "시간대별", "usage", "demand", "delta")),
    (AnswerProfile.RECOMMENDATION_REBALANCING, ("재배치", "추천", "우선순위", "조치", "후보", "recommend", "rebalance", "priority", "action")),
    (AnswerProfile.INCIDENT_QUALITY, ("장애", "오류", "실패", "품질", "incident", "failure", "error", "quality", "복구", "에스컬레이션")),
    (AnswerProfile.PM_REPORTING, ("보고", "요약", "pm", "의사결정", "리스크", "상태", "report", "decision", "risk")),
    (AnswerProfile.OPERATIONS_MONITORING, ("운영", "모니터링", "이상 징후", "먼저 확인", "점검", "monitoring", "operation")),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def classify_question_intent(question: str, category: str | None = None) -> AnswerProfile:
    """
    질문과 기존 카테고리를 기반으로 답변 프로필을 결정한다.
    category가 있으면 category를 우선 사용하고,
    없으면 question text 기반 keyword fallback을 사용한다.
    """
    if category:
        normalized_category = _normalize(category).replace(" ", "")
        for profile, patterns in _CATEGORY_PATTERNS:
            if any(pattern.lower().replace(" ", "") in normalized_category for pattern in patterns):
                return profile

    normalized_question = _normalize(question)
    for profile, keywords in _KEYWORD_PATTERNS:
        if _has_keyword(normalized_question, keywords):
            return profile
    return AnswerProfile.GENERAL
