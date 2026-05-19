# Timestamp: 2026-05-19 01:08:25

from __future__ import annotations

import csv
from functools import lru_cache
import io
from pathlib import Path
import re
from textwrap import shorten
from typing import Any

try:
    from .answer_renderer import append_debug_if_enabled, render_answer_draft
    from .natural_language_labels import humanize_mapping_values
    from .intent_classifier import classify_question_intent
    from .schemas import AnswerDraft, AnswerProfile, EvidenceBundle, RecommendedAction
except ImportError:  # Allow direct script execution.
    from answer_renderer import append_debug_if_enabled, render_answer_draft
    from natural_language_labels import humanize_mapping_values
    from intent_classifier import classify_question_intent
    from schemas import AnswerDraft, AnswerProfile, EvidenceBundle, RecommendedAction


PROFILE_CHECKS: dict[AnswerProfile, list[str]] = {
    AnswerProfile.OPERATIONS_MONITORING: [
        "우선 확인 대상의 최근 상태와 이상 징후 후보",
        "장애 신고, 정비 이력, 데이터 누락 여부",
        "운영자가 즉시 조치할 수 있는 범위와 승인 필요 범위",
    ],
    AnswerProfile.INCIDENT_QUALITY: [
        "증상 발생 시각과 영향 범위",
        "최근 배포, 장애 신고, 에러 로그",
        "복구 가능 조건과 에스컬레이션 기준",
    ],
    AnswerProfile.DEMAND_USAGE_ANALYSIS: [
        "전일 대비 증감률",
        "최근 7일 평균 대비 편차",
        "동일 요일 평균 대비 편차",
        "시간대별 변화량",
        "날씨",
        "이벤트",
        "정비 이력",
        "데이터 누락 여부",
    ],
    AnswerProfile.RECOMMENDATION_REBALANCING: [
        "추천 대상의 현재 상태와 우선순위 근거",
        "기대 효과와 위험 요소",
        "자동 실행 금지 조건과 운영자 승인 절차",
    ],
    AnswerProfile.DATA_SCHEMA: [
        "필요한 테이블 또는 필드",
        "조인 기준과 grain 일치 여부",
        "데이터 품질, null, 중복, 누락 상태",
    ],
    AnswerProfile.EVALUATION_VALIDATION: [
        "평가 목적과 정답 기준",
        "성공/실패 사례와 주요 평가 지표",
        "회귀 테스트와 개선 방법",
    ],
    AnswerProfile.SECURITY_GOVERNANCE: [
        "접근 주체와 허용 범위",
        "제한 조건, 감사 로그, 승인 기준",
        "권한 변경 이력과 운영 통제 정책",
    ],
    AnswerProfile.PM_REPORTING: [
        "핵심 요약과 현재 상태",
        "리스크와 의사결정 필요 사항",
        "다음 액션과 담당자/기한",
    ],
    AnswerProfile.API_DB_PERFORMANCE: [
        "API 처리 시간",
        "DB query time",
        "vector search time",
        "reranking time",
        "LLM generation time",
        "network latency",
        "serialization time",
        "p50/p95/p99 latency",
        "index 사용 여부",
        "top-k 설정",
        "filter 조건",
        "embedding dimension",
        "row count",
    ],
    AnswerProfile.ML_FORECASTING: [
        "예측 대상",
        "입력 feature",
        "평가 지표",
        "모델 한계",
        "운영 적용 조건",
    ],
    AnswerProfile.GENERAL: [
        "판단에 필요한 핵심 데이터",
        "근거가 부족한 지표",
        "추가 조회 대상과 검증 조건",
    ],
}

FALLBACK_MISSING: dict[AnswerProfile, list[str]] = {
    AnswerProfile.API_DB_PERFORMANCE: [
        "API endpoint별 p95 latency",
        "DB query time",
        "vector search time",
        "LLM generation time",
        "reranking time",
        "network/serialization time",
    ],
    AnswerProfile.DEMAND_USAGE_ANALYSIS: [
        "전일 대비 증감률",
        "최근 7일 평균 대비 편차",
        "동일 요일 평균 대비 편차",
        "시간대별 변화량",
        "날씨 또는 이벤트 영향",
        "정비 이력과 데이터 누락 여부",
    ],
    AnswerProfile.RECOMMENDATION_REBALANCING: [
        "추천 대상",
        "추천 이유와 기대 효과",
        "위험 요소와 승인 조건",
    ],
}

RELATION_LABELS: dict[str, str] = {
    "hasEvidence": "근거",
    "hasevidence": "근거",
    "forStation": "대상 대여소",
    "forstation": "대상 대여소",
    "inTimeBucket": "시간대",
    "intimebucket": "시간대",
    "affectedByWeather": "날씨 영향",
    "affectedbyweather": "날씨 영향",
    "requiresReview": "검토 필요",
    "requiresreview": "검토 필요",
    "approvedBy": "승인 주체",
    "approvedby": "승인 주체",
    "createsTask": "작업 생성",
    "createstask": "작업 생성",
    "generatesRecommendation": "추천 생성",
    "generatesrecommendation": "추천 생성",
    "usesDataset": "사용 데이터셋",
    "usesdataset": "사용 데이터셋",
    "servesUser": "지원 사용자",
    "servesuser": "지원 사용자",
    "helpsOperation": "운영 지원",
    "helpsoperation": "운영 지원",
    "measuresAnswer": "답변 평가",
    "measuresanswer": "답변 평가",
    "faultAtStation": "장애 발생 대여소",
    "faultatstation": "장애 발생 대여소",
}

DISPLAY_NAME_KEYS = ("display_name", "name", "place_name", "station_name", "label", "title")
PLACE_NAME_KEYS = (
    "place_name",
    "station_name",
    "address2",
    "주소2",
    "display_name",
    "name",
    "label",
    "title",
    "address",
    "address1",
    "주소",
    "주소1",
    "location",
    "위치",
)
ADDRESS_KEYS = ("address2", "주소2", "address", "address1", "주소", "주소1", "location", "위치")
PLACE_ENTITY_TYPE_HINTS = ("station", "place", "location", "site", "facility", "venue", "address", "branch")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
TTAREUNGI_STATION_MASTER_PATH = PROJECT_ROOT / "data" / "raw" / "public" / "서울시 공공자전거 따릉이 대여소 마스터 정보.csv"
MASTER_DATA_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "path": TTAREUNGI_STATION_MASTER_PATH,
        "id_columns": ("대여소_ID", "id", "station_id", "stationId"),
        "name_columns": ("대여소명", "branchname", "place_name", "station_name", "주소2", "address2", "name", "label", "title"),
        "address_columns": ("주소1", "address1", "주소", "address"),
        "numeric_alias_prefixes": ("station",),
    },
)


def _has_evidence(evidence: EvidenceBundle) -> bool:
    return any(
        [
            evidence.contexts,
            evidence.evidence_documents,
            evidence.related_objects,
            evidence.related_relations,
            evidence.recommended_actions,
        ]
    )


def _short(text: Any, width: int = 150) -> str:
    return shorten(str(text).replace("\n", " ").strip(), width=width, placeholder="...")


def relation_label(relation_id: Any) -> str:
    raw = str(relation_id or "").strip()
    if not raw:
        return "관계"
    return RELATION_LABELS.get(raw) or RELATION_LABELS.get(raw.lower()) or "기타 관계"


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _normalize_space(value: Any) -> str:
    return " ".join(str(value or "").split())


def _extract_place_name_from_text(value: Any) -> str:
    normalized = _normalize_space(value)
    if not normalized:
        return ""
    patterns = [
        r"^.+?(?:대로|로|길|가)\s+(?:지하\s*)?\d+(?:-\d+)?\s+(.+)$",
        r"^.+?(?:번길|로\d+길)\s*\d*(?:-\d+)?\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, normalized)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return normalized


def _first_mapping_value(mapping: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(mapping.get(key) or "").strip()
        if value:
            return value
    return ""


def _preferred_place_name_from_mapping(mapping: dict[str, Any], keys: tuple[str, ...] = PLACE_NAME_KEYS) -> str:
    for key in keys:
        value = str(mapping.get(key) or "").strip()
        if not value:
            continue
        place_name = _extract_place_name_from_text(value)
        if place_name:
            return place_name
    return ""


def _master_record_id(row: dict[str, Any], id_columns: tuple[str, ...]) -> str:
    return _first_mapping_value(row, id_columns)


def _master_record_place_name(row: dict[str, Any], source: dict[str, Any]) -> str:
    name_columns = tuple(source.get("name_columns") or ())
    address_columns = tuple(source.get("address_columns") or ())
    return _preferred_place_name_from_mapping(row, name_columns + address_columns + PLACE_NAME_KEYS)


def _master_reference_aliases(record_id: str, source: dict[str, Any]) -> list[str]:
    aliases = [record_id.lower()]
    suffix = record_id.split("-", 1)[1] if "-" in record_id else ""
    if suffix.isdigit():
        for prefix in source.get("numeric_alias_prefixes") or ():
            aliases.append(f"{prefix}:{int(suffix)}")
            aliases.append(f"{prefix}:{suffix}")
    return aliases


@lru_cache(maxsize=1)
def _master_data_display_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for source in MASTER_DATA_SOURCES:
        path = Path(source["path"])
        if not path.exists():
            continue
        text = _decode_text(path.read_bytes())
        rows = csv.DictReader(io.StringIO(text))
        id_columns = tuple(source.get("id_columns") or ("id",))
        for row in rows:
            record_id = _master_record_id(row, id_columns)
            if not record_id:
                continue
            place_name = _master_record_place_name(row, source) or record_id
            display = f"{place_name} ({record_id})"
            for alias in _master_reference_aliases(record_id, source):
                names[alias] = display
    return names


def master_data_display_name(reference: Any) -> str | None:
    value = str(reference or "").strip()
    if not value:
        return None
    names = _master_data_display_names()
    lowered = value.lower()
    if lowered in names:
        return names[lowered]
    for prefix, numeric in re.findall(r"([a-z][\w-]*):0*(\d+)", lowered):
        display = names.get(f"{prefix}:{int(numeric)}") or names.get(f"{prefix}:{numeric}")
        if display:
            return display
    st_match = re.search(r"st-0*(\d+)", lowered)
    if st_match:
        numeric = int(st_match.group(1))
        return names.get(f"st-{numeric}") or names.get(f"st-{st_match.group(1)}")
    return None


def station_master_display_name(reference: Any) -> str | None:
    """Compatibility wrapper for callers that still use the old station-specific name."""
    return master_data_display_name(reference)


def _first_display_name(obj: dict[str, Any]) -> str:
    return _preferred_place_name_from_mapping(obj)


def _looks_like_technical_id(value: str) -> bool:
    lowered = value.lower()
    return ":" in value or lowered.startswith(("st-", "station", "entity", "dataset", "recommendation", "derived", "review", "actual_"))


def entity_display_name(obj: dict[str, Any], *, include_id: bool = True) -> str:
    obj_id = str(obj.get("id") or "").strip()
    master_name = master_data_display_name(obj_id)
    if master_name:
        return master_name
    name = _first_display_name(obj)
    if name and name != obj_id:
        return f"{name} ({obj_id})" if include_id and obj_id else name
    if obj_id:
        return f"{obj_id} (명칭 미확인)" if _looks_like_technical_id(obj_id) else obj_id
    return "명칭 미확인 객체"


def _entity_display_map(evidence: EvidenceBundle) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for obj in evidence.related_objects:
        obj_id = str(obj.get("id") or "").strip()
        if obj_id and obj_id not in mapping:
            mapping[obj_id] = entity_display_name(obj)
    return mapping


def display_entity_reference(reference: Any, evidence: EvidenceBundle) -> str:
    value = str(reference or "").strip()
    if not value:
        return "현재 근거에서 특정 대상 미확정"
    master_name = master_data_display_name(value)
    if master_name:
        return master_name
    mapped = _entity_display_map(evidence).get(value)
    if mapped:
        return mapped
    return f"{value} (명칭 미확인)" if _looks_like_technical_id(value) else value


def _object_display_names(evidence: EvidenceBundle, *, limit: int = 5) -> list[str]:
    names: list[str] = []
    for obj in evidence.related_objects:
        value = entity_display_name(obj)
        if value and value not in names:
            names.append(value)
        if len(names) >= limit:
            break
    return names


def _looks_like_place_entity(obj: dict[str, Any]) -> bool:
    obj_id = str(obj.get("id") or "").strip()
    obj_type = str(obj.get("type") or "").lower()
    if master_data_display_name(obj_id):
        return True
    if any(hint in obj_type for hint in PLACE_ENTITY_TYPE_HINTS):
        return True
    return any(str(obj.get(key) or "").strip() for key in ADDRESS_KEYS)


def _place_display_names(evidence: EvidenceBundle, *, limit: int = 5) -> list[str]:
    names: list[str] = []
    for obj in evidence.related_objects:
        if not _looks_like_place_entity(obj):
            continue
        value = entity_display_name(obj)
        if value and value not in names:
            names.append(value)
        if len(names) >= limit:
            break
    return names


def _action_targets(evidence: EvidenceBundle) -> list[str]:
    targets = [display_entity_reference(action.target, evidence) for action in evidence.recommended_actions if action.target]
    return [target for index, target in enumerate(targets) if target and target not in targets[:index]]


def _candidate_targets(evidence: EvidenceBundle) -> list[str]:
    place_targets = _place_display_names(evidence)
    if place_targets:
        return place_targets
    action_targets = _action_targets(evidence)
    if action_targets:
        return action_targets
    return _object_display_names(evidence)


def _target_text(evidence: EvidenceBundle) -> str:
    targets = _candidate_targets(evidence)
    if targets:
        return ", ".join(targets[:5])
    return "현재 검색 근거에서 확인된 후보"


def _is_db_storage_question(question: str) -> bool:
    q = question.lower()
    return any(token in q for token in ["저장", "무엇", "데이터", "pgvector", "postgresql", "table", "schema"]) and not any(
        token in q for token in ["latency", "느려", "지연", "병목", "p95", "성능"]
    )


def _direct_answer(question: str, profile: AnswerProfile, evidence: EvidenceBundle) -> str:
    target_text = _target_text(evidence)
    if profile == AnswerProfile.API_DB_PERFORMANCE:
        if _is_db_storage_question(question):
            return (
                "PostgreSQL/pgvector에 저장된 내용은 문서 본문, embedding vector, metadata, review/contract 상태처럼 검색과 검증에 필요한 항목으로 분리해 확인해야 합니다. "
                "현재 context만으로 세부 row 내용을 모두 확정하지 말고 table schema, row count, metadata key, embedding dimension, index 구성을 함께 점검해야 합니다."
            )
        return (
            "검색 latency 저하 원인은 한 구간으로 단정하지 말고 API 처리 시간, DB query time, "
            "vector search time, reranking time, LLM generation time, network/serialization time을 trace 단위로 분리해 확인해야 합니다. "
            "우선 p95 latency가 어느 구간에서 증가했는지 확인한 뒤 해당 구간의 index, top-k, filter, 배포 변경을 점검합니다."
        )
    if profile == AnswerProfile.DEMAND_USAGE_ANALYSIS:
        return (
            "이용량 변화 후보는 기준 기간과 대상 기간을 나누어 전일 대비 증감률, 최근 7일 평균 대비 편차, "
            "동일 요일 평균 대비 편차, 시간대별 변화량으로 선별해야 합니다. "
            f"현재 근거에서는 {target_text}를 우선 확인 후보로 보고, 원인은 추가 지표 확인 전까지 확정하지 않습니다."
        )
    if profile == AnswerProfile.RECOMMENDATION_REBALANCING:
        return (
            f"우선 검토 대상은 {target_text}입니다. 추천이나 재배치 실행은 운영 자원 이동이 발생할 수 있으므로 "
            "근거 지표와 위험 조건을 확인한 뒤 사람 검토를 거쳐야 합니다."
        )
    if profile == AnswerProfile.OPERATIONS_MONITORING:
        return (
            f"운영자는 {target_text}를 먼저 확인해야 합니다. 이 대상들은 현재 근거에서 이상 징후 또는 운영 점검 후보로 잡히므로 "
            "장애 신고, 최근 변화, 데이터 누락 여부를 함께 확인하는 것이 적절합니다."
        )
    if profile == AnswerProfile.INCIDENT_QUALITY:
        return "장애/품질 이슈는 증상, 영향 범위, 가능 원인 후보를 분리해 점검하고 복구 조건 또는 에스컬레이션 기준을 함께 확인해야 합니다."
    if profile == AnswerProfile.DATA_SCHEMA:
        return "데이터/스키마 질문은 필요한 테이블·필드와 조인 기준을 먼저 확인하고, 누락·중복·grain 불일치가 있는지 검증해야 합니다."
    if profile == AnswerProfile.EVALUATION_VALIDATION:
        return "평가/검증 질문은 평가 목적, 정답 기준, 지표, 실패 사례를 분리해 확인한 뒤 회귀 테스트로 개선 여부를 판단해야 합니다."
    if profile == AnswerProfile.SECURITY_GOVERNANCE:
        return "보안/권한/운영통제 질문은 접근 주체, 허용 범위, 제한 조건, 감사 로그, 승인 기준을 함께 확인해야 합니다."
    if profile == AnswerProfile.PM_REPORTING:
        return "보고 관점에서는 현재 상태, 핵심 리스크, 의사결정 필요 사항, 다음 액션을 짧게 분리해 정리해야 합니다."
    if profile == AnswerProfile.ML_FORECASTING:
        return "ML/예측 적용은 예측 대상, 입력 feature, 평가 지표, 모델 한계, 운영 적용 조건을 먼저 고정한 뒤 실험해야 합니다."
    return f"현재 근거로는 {target_text}를 중심으로 판단하되, 확정 전 추가 지표와 데이터 품질 확인이 필요합니다."


def _profile_judgment(profile: AnswerProfile, question: str = "") -> str | None:
    if profile == AnswerProfile.API_DB_PERFORMANCE:
        if _is_db_storage_question(question):
            return "DB/pgvector 저장 질문이므로 table schema, embedding dimension, metadata, row count, index 구성을 기준으로 판단해야 합니다."
        return "성능 질문이므로 API, DB, vector search, reranking, LLM, network/serialization 구간을 분리해 병목을 판단해야 합니다."
    if profile == AnswerProfile.DEMAND_USAGE_ANALYSIS:
        return "수요/이용량 질문이므로 기간별 기준선, 변화량, 평균 대비 편차를 중심으로 후보를 판단해야 합니다."
    if profile == AnswerProfile.RECOMMENDATION_REBALANCING:
        return "추천/재배치 질문이므로 대상, 이유, 기대 효과, 위험 요소, 승인 필요성을 함께 판단해야 합니다."
    if profile == AnswerProfile.SECURITY_GOVERNANCE:
        return "보안/권한 질문이므로 접근 주체와 감사 가능성을 함께 확인해야 합니다."
    return None


def _context_judgment(evidence: EvidenceBundle) -> str | None:
    if not evidence.contexts:
        return None
    return "관련 운영·지표·추천 정보가 확인되지만, 원인과 우선순위는 별도 지표로 검증해야 합니다."


def _judgment_object_ids(evidence: EvidenceBundle, profile: AnswerProfile) -> list[str]:
    object_names = _candidate_targets(evidence)
    if profile == AnswerProfile.API_DB_PERFORMANCE:
        api_terms = ("api", "db", "query", "index", "vector", "table", "endpoint", "pgvector", "postgres")
        return [value for value in object_names if any(term in value.lower() for term in api_terms)]
    return object_names


def _evidence_judgments(evidence: EvidenceBundle, profile: AnswerProfile, question: str = "") -> list[str]:
    judgments: list[str] = []
    context_note = _context_judgment(evidence)
    if context_note:
        judgments.append(context_note)
    object_ids = _judgment_object_ids(evidence, profile)
    if object_ids:
        judgments.append(f"관련 객체는 {', '.join(object_ids[:5])}로 확인되며, 이 목록은 우선 검토 대상 후보입니다.")
    if evidence.related_relations:
        relation_names = []
        for relation in evidence.related_relations[:5]:
            relation_name = relation_label(relation.get("relation") or relation.get("type") or "relation")
            if relation_name not in relation_names:
                relation_names.append(relation_name)
        judgments.append(f"관련 관계 항목은 {', '.join(relation_names)}입니다. 관계의 강도나 우선순위는 별도 지표로 검증해야 합니다.")
    profile_note = _profile_judgment(profile, question)
    if profile_note:
        judgments.append(profile_note)
    if not judgments:
        judgments.append("현재 검색 근거에는 판단에 필요한 핵심 사실이 충분히 구조화되어 있지 않습니다.")
    return judgments


def _limitations(profile: AnswerProfile, evidence: EvidenceBundle, question: str = "") -> str:
    if profile == AnswerProfile.API_DB_PERFORMANCE:
        if _is_db_storage_question(question):
            return "현재 context만으로는 저장된 row별 본문, metadata 전체, index 상태를 모두 확정할 수 없습니다. schema와 실제 row sample 확인이 필요합니다."
        return "현재 context만으로는 latency 병목 구간과 원인을 확정할 수 없습니다. 구간별 측정값과 최근 변경 이력이 필요합니다."
    if profile == AnswerProfile.DEMAND_USAGE_ANALYSIS:
        return "현재 근거만으로는 이용량 변화 원인과 확정 순위를 단정할 수 없습니다. 기간별 기준선과 외부 조건 확인이 필요합니다."
    if profile == AnswerProfile.RECOMMENDATION_REBALANCING:
        return "현재 근거만으로는 실제 재배치 실행 효과와 위험을 확정할 수 없습니다. 운영자 승인 전 추가 지표 확인이 필요합니다."
    if not evidence.contexts:
        return "현재 context에는 이 질문을 판단할 핵심 근거가 부족합니다."
    return "현재 context만으로는 원인, 우선순위, 실행 결과를 확정할 수 없습니다. 위 판단은 우선 확인 후보로 제한됩니다."


def _additional_checks(profile: AnswerProfile, question: str = "") -> list[str]:
    if profile == AnswerProfile.API_DB_PERFORMANCE and _is_db_storage_question(question):
        return [
            "table name과 schema",
            "document id와 content 컬럼",
            "embedding vector dimension",
            "metadata key와 review flag",
            "row count",
            "vector index 사용 여부",
        ]
    return PROFILE_CHECKS.get(profile, PROFILE_CHECKS[AnswerProfile.GENERAL])


def _display_actions(actions: list[RecommendedAction], evidence: EvidenceBundle) -> list[RecommendedAction]:
    displayed: list[RecommendedAction] = []
    for action in actions:
        displayed.append(
            RecommendedAction(
                target=display_entity_reference(action.target, evidence) if action.target else action.target,
                action=action.action,
                reason=action.reason,
                requires_human_approval=action.requires_human_approval,
                auto_executable=action.auto_executable,
                risk=action.risk,
            )
        )
    return displayed


def _profile_actions(profile: AnswerProfile, evidence: EvidenceBundle) -> list[RecommendedAction]:
    if profile != AnswerProfile.API_DB_PERFORMANCE:
        return _display_actions(evidence.recommended_actions, evidence)
    allowed_terms = ("api", "db", "query", "index", "vector", "latency", "endpoint", "schema", "pgvector", "postgres")
    filtered: list[RecommendedAction] = []
    for action in evidence.recommended_actions:
        haystack = " ".join([str(action.target or ""), action.action, action.reason, str(action.risk or "")]).lower()
        if any(term in haystack for term in allowed_terms):
            filtered.append(action)
    return _display_actions(filtered, evidence)


def _fallback_missing(profile: AnswerProfile) -> list[str]:
    return FALLBACK_MISSING.get(profile, PROFILE_CHECKS.get(profile, PROFILE_CHECKS[AnswerProfile.GENERAL]))


def _fallback_answer(question: str, profile: AnswerProfile, evidence: EvidenceBundle, *, debug_mode: bool = False) -> str:
    if profile == AnswerProfile.API_DB_PERFORMANCE:
        answer = "현재 근거만으로는 검색 latency 저하 원인을 확정하기 어렵습니다."
        next_checks = [
            "요청 trace 단위로 API, DB, vector search, reranking, LLM 구간을 분리해야 합니다.",
            "최근 배포 이력, index 변경, top-k 설정 변경, filter 조건 변경 여부를 확인해야 합니다.",
        ]
        limitation = "현재 context에는 latency 병목을 특정할 수 있는 구간별 측정값이 부족합니다."
    else:
        answer = "현재 근거만으로는 질문에 대한 확정 답변을 내리기 어렵습니다."
        next_checks = _additional_checks(profile, question)[:6]
        limitation = "현재 검색된 context에는 이 질문을 판단할 핵심 근거가 부족합니다."

    lines = ["## 답변", answer, "", "## 부족한 근거"]
    lines.extend(f"- {item}" for item in _fallback_missing(profile))
    lines.extend(["", "## 다음 확인 필요"])
    lines.extend(f"- {item}" for item in next_checks)
    lines.extend(["", "## 답변 한계", limitation])
    return append_debug_if_enabled("\n".join(lines), evidence.debug, debug_mode=debug_mode)


def compose_answer(
    question: str,
    evidence: EvidenceBundle,
    category: str | None = None,
    debug_mode: bool = False,
) -> str:
    """
    검색된 evidence bundle을 사용자-facing 답변으로 변환한다.
    """
    profile = classify_question_intent(question, category)
    if not _has_evidence(evidence):
        return _fallback_answer(question, profile, evidence, debug_mode=debug_mode)

    draft = AnswerDraft(
        answer=_direct_answer(question, profile, evidence),
        evidence_based_judgment=_evidence_judgments(evidence, profile, question),
        recommended_actions=_profile_actions(profile, evidence),
        additional_checks=_additional_checks(profile, question),
        limitations=_limitations(profile, evidence, question),
        debug=evidence.debug,
    )
    return render_answer_draft(draft, debug_mode=debug_mode)


def build_answer_prompt(
    question: str,
    profile: AnswerProfile,
    evidence: EvidenceBundle,
    debug_mode: bool = False,
) -> str:
    """
    Answer Composer용 LLM 프롬프트를 생성한다.
    """
    compact_evidence = {
        "contexts": evidence.contexts[:3],
        "evidence_documents": evidence.evidence_documents[:5],
        "related_objects": [
            {**humanize_mapping_values(obj), "display_name": entity_display_name(obj)} for obj in evidence.related_objects[:5]
        ],
        "related_relations": [
            {**relation, "relation_label_ko": relation_label(relation.get("relation") or relation.get("type"))}
            for relation in evidence.related_relations[:5]
        ],
        "recommended_actions": [action.__dict__ for action in _display_actions(evidence.recommended_actions[:3], evidence)],
        "debug": evidence.debug if debug_mode else "debug is hidden unless debug_mode=True",
    }
    return "\n".join(
        [
            "너는 특정 도메인에 종속되지 않는 범용 RAG Answer Composer다.",
            "반드시 제공된 RAG context와 evidence만 사용해서 한국어로 답변하라.",
            "검색 결과의 존재를 설명하지 말고, 검색 결과를 해석해서 사용자의 다음 행동으로 바꿔라.",
            "답변 본문에서는 파일 경로를 나열하지 말고, 파일 경로는 본문보다 발췌 목록/evidence_excerpt_list에만 정리하라.",
            "엔티티는 id보다 display_name/name/label/station_name/title/place_name/address2/address를 우선 표시하고, 주소 문장에서는 역이름·지명 suffix를 우선 추출하라.",
            "gender=1.0, age=20, holiday=0 같은 코드값은 사용자 본문에 그대로 노출하지 말고 display label이 있으면 남성(M), 20대, 비공휴일처럼 자연어를 우선 표시하라.",
            "엔티티 ID만 있으면 위치·주소·속성을 단정하지 말고 detail_status와 data gap을 설명하라.",
            "relation은 한국어 명사형 label로 표시하고 hasEvidence/forStation 같은 영어 relation id를 사용자 본문에 그대로 노출하지 마라.",
            "구체적 판단 없이 '추가 확인이 필요합니다'로 끝내지 마라.",
            "",
            "금지:",
            "- 근거 N개를 기준으로 답변합니다",
            "- 관계 N개를 기준으로 답변합니다",
            "- 추천 조치 후보는 N개입니다",
            "- context 밖의 원천을 추가로 추정하지 않습니다",
            "- retrieved_context_count/top1_retrieval_score 같은 debug 값을 사용자 본문에 노출",
            "",
            "필수 출력 구조:",
            "## 답변",
            "## 근거 기반 판단",
            "## 권장 조치",
            "## 추가 확인 필요",
            "## 답변 한계",
            "debug_mode=True일 때만 ## 디버깅 정보 섹션을 추가하라.",
            "",
            "필수 내용:",
            "- 질문에 대한 직접 답변",
            "- 근거에서 확인되는 사실",
            "- 사실로부터 도출되는 판단",
            "- 권장 조치",
            "- 추가 확인 필요 데이터",
            "- 답변 한계",
            "",
            f"question: {question}",
            f"answer_profile: {profile.value}",
            "evidence:",
            str(compact_evidence),
        ]
    )
