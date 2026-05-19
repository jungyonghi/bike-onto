# Timestamp: 2026-05-18 22:42:00

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AnswerProfile(str, Enum):
    OPERATIONS_MONITORING = "operations_monitoring"
    INCIDENT_QUALITY = "incident_quality"
    DEMAND_USAGE_ANALYSIS = "demand_usage_analysis"
    RECOMMENDATION_REBALANCING = "recommendation_rebalancing"
    DATA_SCHEMA = "data_schema"
    EVALUATION_VALIDATION = "evaluation_validation"
    SECURITY_GOVERNANCE = "security_governance"
    PM_REPORTING = "pm_reporting"
    API_DB_PERFORMANCE = "api_db_performance"
    ML_FORECASTING = "ml_forecasting"
    GENERAL = "general"


@dataclass
class RecommendedAction:
    target: str | None
    action: str
    reason: str
    requires_human_approval: bool
    auto_executable: bool = False
    risk: str | None = None


@dataclass
class EvidenceBundle:
    contexts: list[str]
    evidence_documents: list[dict[str, Any]]
    related_objects: list[dict[str, Any]]
    related_relations: list[dict[str, Any]]
    recommended_actions: list[RecommendedAction]
    debug: dict[str, Any]


@dataclass
class AnswerDraft:
    answer: str
    evidence_based_judgment: list[str]
    recommended_actions: list[RecommendedAction]
    additional_checks: list[str]
    limitations: str
    debug: dict[str, Any] | None = None
