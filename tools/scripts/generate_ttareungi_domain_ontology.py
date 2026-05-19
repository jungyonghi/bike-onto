# Timestamp: 2026-05-11 11:24:00
# Timestamp: 2026-05-11 15:55:50

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Iterable


CORE_DOMAIN_CLASSES = [
    "Station",
    "Bike",
    "TripEvent",
    "StationHourlyCount",
    "BrokenEvent",
    "WeatherObservation",
    "DateBucket",
    "EvidenceEdge",
]
V2_DOMAIN_CLASSES = [
    "DemandEpisode",
    "RecoveryEpisode",
    "ShortageEpisode",
    "StationRoleProfile",
    "ImbalanceCorridor",
    "BikeLifecyclePath",
    "MaintenanceSinkStation",
    "StationLifecycleEvent",
    "MetricSemantics",
    "SourceArtifact",
    "ConfidenceAssessment",
    "NightReallocationShift",
    "DispatchAgent",
    "ReallocationAction",
    "ReallocationRoute",
    "MarkovTransitionPolicy",
    "MorningShortageRisk",
    "ReallocationRecommendation",
    "WorkforceCapacityConstraint",
]
DOMAIN_RELATIONS = [
    "rental_station",
    "return_station",
    "same_bike",
    "observed_under_weather",
    "in_time_bucket",
    "supported_by",
    "derived_from",
    "precedes",
    "followed_by",
    "has_role_in_time_band",
    "has_confidence",
    "has_upper_parent",
    "explains_anomaly",
    "assigned_to_agent",
    "pickup_station",
    "dropoff_station",
    "occurs_during_shift",
    "uses_transition_policy",
    "mitigates_shortage",
    "has_route_cost",
    "constrained_by_capacity",
]
EVIDENCE_KINDS = ["direct", "derived", "inferred", "weak-context"]
NIGHT_REALLOCATION_ONTOLOGY_NAME = "NightReallocationOperationsOntology"
NIGHT_REALLOCATION_PARENT_ONTOLOGY = "Ttareungi Domain Ontology-lite v2.1"
NIGHT_REALLOCATION_PURPOSE = "야간 200명 현장 인력 기반 Markov 재배치 실험과 KPI 판정을 위한 운영 의사결정 ontology slice"
NIGHT_REALLOCATION_STATUS = "domain_extension"
NIGHT_REALLOCATION_FORMALIZATION_LEVEL = "ontology-lite"
QUESTION_BANK_RELATIVE_PATH = Path("docs/project/obybk_ontology_necessity_performance_question_bank.md")
UPPER_RUNS_RELATIVE_DIR = Path("data/processed/exports/ontology_term_runs")
DOMAIN_RUNS_RELATIVE_DIR = Path("data/processed/exports/ttareungi_domain_ontology_runs")


@dataclass(frozen=True)
class QuestionRecord:
    qid: str
    question: str
    expected_query: str
    physical_query: str
    verdict: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class DomainOntologyCandidate:
    domain_term: str
    canonical_name: str
    upper_parent: str
    candidate_type: str
    source_refs: list[str]
    cq_ids: list[str]
    physical_sources: list[str]
    evidence_kind: str
    confidence: float
    promotion_decision: str
    relations: list[str]
    short_definition: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UpperAlignmentEdge:
    upper_concept: str
    relation: str
    domain_concept: str
    mapping_kind: str
    confidence: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DomainConceptSpec:
    canonical_name: str
    upper_parent: str
    candidate_type: str
    physical_sources: list[str]
    evidence_kind: str
    confidence: float
    promotion_decision: str
    relations: list[str]
    short_definition: str


DOMAIN_CONCEPT_SPECS = [
    DomainConceptSpec(
        "Station",
        "Location Identity",
        "class_candidate",
        ["branch_data.parquet"],
        "direct",
        0.96,
        "domain_core",
        ["rental_station", "return_station", "has_upper_parent"],
        "따릉이 대여소 운영 개체와 위치 프로필을 나타내는 핵심 domain class.",
    ),
    DomainConceptSpec(
        "Bike",
        "Asset Identity",
        "class_candidate",
        ["rent_data.parquet", "broken_data.parquet"],
        "direct",
        0.94,
        "domain_core",
        ["same_bike", "has_upper_parent"],
        "대여 및 고장 이벤트를 관통하는 자전거 개체.",
    ),
    DomainConceptSpec(
        "TripEvent",
        "Transaction Identity",
        "class_candidate",
        ["rent_data.parquet"],
        "direct",
        0.95,
        "domain_core",
        ["rental_station", "return_station", "same_bike", "in_time_bucket"],
        "대여 시작, 반납, 거리, 자전거 식별자를 포함하는 이동 이벤트.",
    ),
    DomainConceptSpec(
        "StationHourlyCount",
        "Measurement Identity",
        "class_candidate",
        ["count_data.parquet"],
        "direct",
        0.91,
        "domain_core",
        ["in_time_bucket", "derived_from"],
        "대여소-시간 단위 이용량 또는 가용성 측정 fact.",
    ),
    DomainConceptSpec(
        "BrokenEvent",
        "Failure Event Identity",
        "class_candidate",
        ["broken_data.parquet"],
        "direct",
        0.93,
        "domain_core",
        ["same_bike", "in_time_bucket"],
        "자전거 번호와 고장 유형을 기준으로 기록되는 고장 이벤트.",
    ),
    DomainConceptSpec(
        "WeatherObservation",
        "Observation Event Identity",
        "class_candidate",
        ["weather_data.parquet"],
        "direct",
        0.92,
        "domain_core",
        ["observed_under_weather", "in_time_bucket"],
        "시간별 기온, 강수, 풍속 등 외생 날씨 관측 fact.",
    ),
    DomainConceptSpec(
        "DateBucket",
        "Time Interval Identity",
        "class_candidate",
        [
            "branch_data.parquet",
            "rent_data.parquet",
            "count_data.parquet",
            "broken_data.parquet",
            "weather_data.parquet",
        ],
        "derived",
        0.88,
        "domain_core",
        ["in_time_bucket", "derived_from"],
        "서로 다른 grain의 fact를 맞추기 위한 파생 시간 버킷.",
    ),
    DomainConceptSpec(
        "EvidenceEdge",
        "Evidence Item Relation",
        "relation_candidate",
        [
            "branch_data.parquet",
            "rent_data.parquet",
            "count_data.parquet",
            "broken_data.parquet",
            "weather_data.parquet",
        ],
        "weak-context",
        0.86,
        "domain_core",
        ["supported_by", "derived_from", "has_confidence"],
        "source, relation, evidence kind, confidence를 같이 운반하는 근거 edge.",
    ),
    DomainConceptSpec(
        "DemandEpisode",
        "Event Identity",
        "class_candidate",
        ["weather_data.parquet", "count_data.parquet", "branch_data.parquet"],
        "derived",
        0.82,
        "domain_extension",
        ["observed_under_weather", "in_time_bucket", "derived_from"],
        "날씨나 시간대 조건 아래 수요 변화가 의미 있게 나타나는 episode.",
    ),
    DomainConceptSpec(
        "RecoveryEpisode",
        "Process Lifecycle",
        "class_candidate",
        ["weather_data.parquet", "count_data.parquet"],
        "derived",
        0.80,
        "domain_extension",
        ["precedes", "followed_by", "derived_from"],
        "강수 종료나 충격 이후 수요가 기준선으로 회복되는 시간 window.",
    ),
    DomainConceptSpec(
        "ShortageEpisode",
        "Incident State",
        "class_candidate",
        ["count_data.parquet", "rent_data.parquet"],
        "derived",
        0.79,
        "domain_extension",
        ["in_time_bucket", "derived_from", "explains_anomaly"],
        "대여소 수요 급증, 공급 부족, 비어감 현상을 표현하는 운영 episode.",
    ),
    DomainConceptSpec(
        "StationRoleProfile",
        "Role Bearer State",
        "class_candidate",
        ["rent_data.parquet", "branch_data.parquet"],
        "direct",
        0.90,
        "domain_extension",
        ["rental_station", "return_station", "has_role_in_time_band"],
        "동일 대여소가 시간대별 시작점/반납점 역할을 바꾸는 profile.",
    ),
    DomainConceptSpec(
        "ImbalanceCorridor",
        "Route Relation",
        "relation_candidate",
        ["rent_data.parquet", "count_data.parquet"],
        "derived",
        0.78,
        "domain_extension",
        ["rental_station", "return_station", "precedes", "explains_anomaly"],
        "대여소 쌍 또는 구간에서 반복되는 편도 쏠림 관계.",
    ),
    DomainConceptSpec(
        "BikeLifecyclePath",
        "Sequence Lifecycle",
        "class_candidate",
        ["rent_data.parquet", "broken_data.parquet"],
        "inferred",
        0.74,
        "domain_extension",
        ["same_bike", "precedes", "followed_by"],
        "자전거의 대여, 반납, 장거리 이동, 고장 상태 전이를 시간순으로 잇는 path.",
    ),
    DomainConceptSpec(
        "MaintenanceSinkStation",
        "Site Role",
        "class_candidate",
        ["broken_data.parquet", "rent_data.parquet", "branch_data.parquet"],
        "inferred",
        0.70,
        "domain_extension",
        ["same_bike", "return_station", "precedes"],
        "고장 자전거가 반복적으로 수렴하거나 배출되는 정비 취약 대여소 후보.",
    ),
    DomainConceptSpec(
        "StationLifecycleEvent",
        "Change Event Lifecycle",
        "class_candidate",
        ["branch_data.parquet"],
        "derived",
        0.81,
        "domain_extension",
        ["derived_from", "has_upper_parent"],
        "대여소명 변경, 좌표 이동, 신설, 운영 연속성을 다루는 lifecycle event.",
    ),
    DomainConceptSpec(
        "MetricSemantics",
        "Metadata Identity",
        "class_candidate",
        ["branch_data.parquet", "count_data.parquet", "rent_data.parquet", "uselate_data.parquet"],
        "weak-context",
        0.76,
        "domain_extension",
        ["supported_by", "derived_from", "has_confidence"],
        "cnt_rack, ilcd, iqr 같은 물리 컬럼의 의미와 해석 위험을 담는 catalog concept.",
    ),
    DomainConceptSpec(
        "SourceArtifact",
        "Dataset Evidence",
        "class_candidate",
        [
            "branch_data.parquet",
            "rent_data.parquet",
            "count_data.parquet",
            "broken_data.parquet",
            "weather_data.parquet",
            "newmeta.parquet",
        ],
        "weak-context",
        0.84,
        "domain_extension",
        ["supported_by", "derived_from"],
        "Parquet, 공식 문서, 질문셋을 provenance 단위로 묶는 source concept.",
    ),
    DomainConceptSpec(
        "ConfidenceAssessment",
        "Assessment Evidence",
        "class_candidate",
        [
            "branch_data.parquet",
            "rent_data.parquet",
            "count_data.parquet",
            "broken_data.parquet",
            "weather_data.parquet",
        ],
        "weak-context",
        0.83,
        "domain_extension",
        ["supported_by", "has_confidence", "explains_anomaly"],
        "직접/파생/추론/약한 문맥 근거를 답변 신뢰도와 함께 설명하는 assessment.",
    ),
    DomainConceptSpec(
        "NightReallocationShift",
        "Operation Process",
        "class_candidate",
        ["count_data.parquet", "rent_data.parquet", "weather_data.parquet"],
        "weak-context",
        0.68,
        "domain_extension",
        ["occurs_during_shift", "in_time_bucket", "supported_by"],
        "23:00~05:00 야간 자전거 재배치 작업 window를 표현하는 운영 process.",
    ),
    DomainConceptSpec(
        "DispatchAgent",
        "Agent Role",
        "class_candidate",
        ["EXPERIMENT:night_200_dispatch_agents"],
        "weak-context",
        0.62,
        "domain_extension",
        ["assigned_to_agent", "constrained_by_capacity", "supported_by"],
        "약 200명의 야간 현장 재배치 인력 또는 작업자 agent 역할.",
    ),
    DomainConceptSpec(
        "ReallocationAction",
        "Resource Transfer Event",
        "class_candidate",
        ["rent_data.parquet", "count_data.parquet", "branch_data.parquet"],
        "derived",
        0.73,
        "domain_extension",
        ["pickup_station", "dropoff_station", "assigned_to_agent", "mitigates_shortage"],
        "특정 대여소에서 자전거를 회수해 다른 대여소로 이동시키는 재배치 행위.",
    ),
    DomainConceptSpec(
        "ReallocationRoute",
        "Route Relation",
        "class_candidate",
        ["branch_data.parquet", "rent_data.parquet"],
        "derived",
        0.71,
        "domain_extension",
        ["pickup_station", "dropoff_station", "has_route_cost"],
        "재배치 agent가 이동하는 station sequence와 거리/시간 비용 relation.",
    ),
    DomainConceptSpec(
        "MarkovTransitionPolicy",
        "Predictive Policy",
        "class_candidate",
        ["rent_data.parquet", "count_data.parquet"],
        "derived",
        0.77,
        "domain_extension",
        ["uses_transition_policy", "derived_from", "has_confidence"],
        "station 간 이동 확률과 shortage 예측을 만드는 Markov 기반 재배치 정책.",
    ),
    DomainConceptSpec(
        "MorningShortageRisk",
        "Risk State",
        "class_candidate",
        ["count_data.parquet", "rent_data.parquet", "weather_data.parquet"],
        "derived",
        0.76,
        "domain_extension",
        ["in_time_bucket", "observed_under_weather", "mitigates_shortage"],
        "다음날 07:00~10:00 출근 피크 shortage 가능성을 나타내는 risk state.",
    ),
    DomainConceptSpec(
        "ReallocationRecommendation",
        "Decision Artifact",
        "class_candidate",
        ["rent_data.parquet", "count_data.parquet", "branch_data.parquet", "weather_data.parquet"],
        "inferred",
        0.72,
        "domain_extension",
        ["uses_transition_policy", "constrained_by_capacity", "supported_by", "has_confidence"],
        "ontology-base Markov가 제안한 station pair, 수량, 근거, confidence 포함 재배치 추천.",
    ),
    DomainConceptSpec(
        "WorkforceCapacityConstraint",
        "Operational Constraint",
        "class_candidate",
        ["EXPERIMENT:night_shift_200_agents"],
        "weak-context",
        0.61,
        "domain_extension",
        ["constrained_by_capacity", "supported_by"],
        "200명 인력, agent당 작업량, 야간 이동 가능 시간 같은 실험 capacity 제약.",
    ),
]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _run_stamp(timestamp: str) -> str:
    return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d_%H%M%S")


def _split_markdown_table_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def parse_question_bank(question_bank_path: Path) -> tuple[list[QuestionRecord], list[QuestionRecord]]:
    text = question_bank_path.read_text(encoding="utf-8")
    qo_records: list[QuestionRecord] = []
    qp_records: list[QuestionRecord] = []
    for line in text.splitlines():
        if not line.startswith("| Q"):
            continue
        parts = _split_markdown_table_row(line)
        if len(parts) < 5 or not re.fullmatch(r"Q[OP]\d{2}", parts[0]):
            continue
        record = QuestionRecord(
            qid=parts[0],
            question=parts[1],
            expected_query=parts[2],
            physical_query=parts[3],
            verdict=parts[4],
        )
        if record.qid.startswith("QO"):
            qo_records.append(record)
        else:
            qp_records.append(record)
    return qo_records, qp_records


def _latest_run_dir(parent_dir: Path, required_filename: str) -> Path | None:
    if not parent_dir.exists():
        return None
    candidates = [path for path in parent_dir.iterdir() if path.is_dir() and (path / required_filename).exists()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.name)[-1]


def _latest_upper_ontology_run(project_root: Path) -> Path | None:
    return _latest_run_dir(project_root / UPPER_RUNS_RELATIVE_DIR, "final_result.json")


def _load_upper_anchor_names(project_root: Path) -> tuple[set[str], str]:
    run_dir = _latest_upper_ontology_run(project_root)
    if run_dir is None:
        return set(), "upper_ontology_source=missing"
    payload = json.loads((run_dir / "final_result.json").read_text(encoding="utf-8"))
    names: set[str] = set()
    for item in payload.get("candidate_records", []):
        if item.get("surface_form"):
            names.add(str(item["surface_form"]))
        if item.get("canonical_candidate"):
            names.add(str(item["canonical_candidate"]))
    for item in payload.get("promotion_records", []):
        if item.get("canonical_name"):
            names.add(str(item["canonical_name"]))
        for parent in item.get("possible_parent_classes", []):
            names.add(str(parent))
        for related in item.get("possible_related_classes", []):
            names.add(str(related))
    source = str((run_dir / "final_result.json").relative_to(project_root))
    return names, source


def _qid_number(qid: str) -> int:
    return int(qid[2:])


def _concepts_for_qo(record: QuestionRecord) -> list[str]:
    number = _qid_number(record.qid)
    question = record.question
    concepts: set[str] = set()

    if 1 <= number <= 10:
        concepts.update({"DemandEpisode", "WeatherObservation", "StationHourlyCount", "DateBucket"})
    if any(token in question for token in ["회복", "회복력", "회복 속도"]):
        concepts.add("RecoveryEpisode")
    if any(token in question for token in ["비어", "부족", "급감", "급증", "수요", "유지"]):
        concepts.add("ShortageEpisode")
    if 11 <= number <= 20:
        concepts.update({"Station", "TripEvent", "StationRoleProfile"})
    if any(token in question for token in ["쏠림", "방향", "쌍", "순유출입", "corridor", "군집", "swap"]):
        concepts.add("ImbalanceCorridor")
    if any(token in question for token in ["스냅샷", "이름", "좌표", "별칭", "lifecycle", "신설", "이동"]):
        concepts.add("StationLifecycleEvent")
    if 21 <= number <= 30:
        concepts.update({"Bike", "TripEvent", "BrokenEvent", "BikeLifecyclePath", "DateBucket"})
    if any(token in question for token in ["정비", "고장 유형", "고장 자전거", "고장 배출", "취약"]):
        concepts.add("MaintenanceSinkStation")
    if any(token in question for token in ["metric", "ilcd", "iqr", "cnt_rack", "컬럼"]):
        concepts.add("MetricSemantics")
    if 31 <= number <= 50:
        concepts.update({"EvidenceEdge", "SourceArtifact", "ConfidenceAssessment"})
    if any(token in question for token in ["가입자", "newmeta", "월별", "성별", "연령"]):
        concepts.add("SourceArtifact")
        concepts.add("ConfidenceAssessment")
    if any(token in question for token in ["이상", "모순", "정합성", "근거", "신뢰도", "source", "provenance"]):
        concepts.add("ConfidenceAssessment")
    if number in {41, 44, 47, 48, 49, 50}:
        concepts.update({"EvidenceEdge", "SourceArtifact", "ConfidenceAssessment"})
    if not concepts:
        concepts.add("SourceArtifact")
    return sorted(concepts)


def _question_coverage(qo_records: Iterable[QuestionRecord]) -> dict[str, list[str]]:
    return {record.qid: _concepts_for_qo(record) for record in qo_records}


def _source_refs(cq_ids: list[str], fallback_refs: list[str]) -> list[str]:
    refs = [f"CQ:{qid}" for qid in cq_ids]
    refs.extend(fallback_refs)
    deduped: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if ref not in seen:
            deduped.append(ref)
            seen.add(ref)
    return deduped


def _build_candidates(
    qo_records: list[QuestionRecord],
    timestamp: str,
) -> tuple[list[DomainOntologyCandidate], dict[str, list[str]]]:
    coverage_map = _question_coverage(qo_records)
    cq_by_concept: dict[str, list[str]] = {spec.canonical_name: [] for spec in DOMAIN_CONCEPT_SPECS}
    for qid, concepts in coverage_map.items():
        for concept in concepts:
            cq_by_concept.setdefault(concept, []).append(qid)

    candidates = []
    for spec in DOMAIN_CONCEPT_SPECS:
        cq_ids = sorted(cq_by_concept.get(spec.canonical_name, []))
        fallback = [
            f"DOC:{QUESTION_BANK_RELATIVE_PATH.as_posix()}",
            "MODEL:ontology-lite-mvp",
        ]
        candidates.append(
            DomainOntologyCandidate(
                domain_term=spec.canonical_name,
                canonical_name=spec.canonical_name,
                upper_parent=spec.upper_parent,
                candidate_type=spec.candidate_type,
                source_refs=_source_refs(cq_ids, fallback),
                cq_ids=cq_ids,
                physical_sources=spec.physical_sources,
                evidence_kind=spec.evidence_kind,
                confidence=spec.confidence,
                promotion_decision=spec.promotion_decision,
                relations=spec.relations,
                short_definition=spec.short_definition,
                notes=(
                    "strategy=hybrid_anchored_extraction | "
                    f"upper_parent={spec.upper_parent} | "
                    f"# Timestamp: {timestamp}"
                ),
            )
        )
    return candidates, coverage_map


def _build_alignments(
    candidates: list[DomainOntologyCandidate],
    upper_anchor_names: set[str],
    upper_source: str,
) -> list[UpperAlignmentEdge]:
    edges = []
    for candidate in candidates:
        mapping_kind = "exact_anchor" if candidate.upper_parent in upper_anchor_names else "proposed_anchor"
        confidence = min(candidate.confidence + 0.04, 0.99) if mapping_kind == "exact_anchor" else candidate.confidence
        edges.append(
            UpperAlignmentEdge(
                upper_concept=candidate.upper_parent,
                relation="has_upper_parent",
                domain_concept=candidate.canonical_name,
                mapping_kind=mapping_kind,
                confidence=round(confidence, 2),
                source=upper_source,
            )
        )
    return edges


def _build_promotions(candidates: list[DomainOntologyCandidate], timestamp: str) -> list[dict[str, Any]]:
    promotions = []
    for candidate in candidates:
        promotions.append(
            {
                "promotion_decision": candidate.promotion_decision,
                "canonical_name": candidate.canonical_name,
                "upper_parent": candidate.upper_parent,
                "short_definition": candidate.short_definition,
                "rationale": (
                    f"{candidate.canonical_name} is retained for 따릉이 ontology-lite v2 because it "
                    f"covers {len(candidate.cq_ids)} ontology necessity questions and maps to "
                    f"upper parent {candidate.upper_parent}. # Timestamp: {timestamp}"
                ),
                "possible_parent_classes": [candidate.upper_parent, "TtareungiDomainOntologyConcept"],
                "possible_related_classes": sorted(
                    {
                        related.canonical_name
                        for related in candidates
                        if related.canonical_name != candidate.canonical_name
                        and set(related.physical_sources).intersection(candidate.physical_sources)
                    }
                )[:8],
                "cq_ids": candidate.cq_ids,
                "physical_sources": candidate.physical_sources,
                "evidence_kind": candidate.evidence_kind,
                "confidence": candidate.confidence,
            }
        )
    return promotions


def _coverage_summary(
    qo_records: list[QuestionRecord],
    qp_records: list[QuestionRecord],
    coverage_map: dict[str, list[str]],
) -> dict[str, Any]:
    qo_ids = [record.qid for record in qo_records]
    mapped = [qid for qid in qo_ids if coverage_map.get(qid)]
    unmapped = [qid for qid in qo_ids if not coverage_map.get(qid)]
    return {
        "qo_total": len(qo_records),
        "qo_mapped": len(mapped),
        "qo_unmapped": unmapped,
        "qp_total": len(qp_records),
        "qp_baseline_only": len(qp_records),
        "qp_promoted": 0,
    }


def build_ttareungi_domain_ontology(project_root: Path, timestamp: str | None = None) -> dict[str, Any]:
    timestamp = timestamp or _now()
    question_bank_path = project_root / QUESTION_BANK_RELATIVE_PATH
    qo_records, qp_records = parse_question_bank(question_bank_path)
    upper_anchor_names, upper_source = _load_upper_anchor_names(project_root)
    candidates, coverage_map = _build_candidates(qo_records, timestamp)
    alignments = _build_alignments(candidates, upper_anchor_names, upper_source)
    promotions = _build_promotions(candidates, timestamp)
    coverage = _coverage_summary(qo_records, qp_records, coverage_map)

    return {
        "timestamp": timestamp,
        "generation_source": "codex_agent",
        "strategy": "hybrid_anchored_extraction",
        "ontology_name": NIGHT_REALLOCATION_ONTOLOGY_NAME,
        "parent_ontology": NIGHT_REALLOCATION_PARENT_ONTOLOGY,
        "purpose": NIGHT_REALLOCATION_PURPOSE,
        "status": NIGHT_REALLOCATION_STATUS,
        "formalization_level": NIGHT_REALLOCATION_FORMALIZATION_LEVEL,
        "upper_ontology_source": upper_source,
        "core_domain_classes": CORE_DOMAIN_CLASSES,
        "v2_domain_classes": V2_DOMAIN_CLASSES,
        "relations": DOMAIN_RELATIONS,
        "evidence_kinds": EVIDENCE_KINDS,
        "domain_candidate_records": [candidate.to_dict() for candidate in candidates],
        "domain_promotion_records": promotions,
        "upper_alignment_edges": [edge.to_dict() for edge in alignments],
        "question_coverage": coverage_map,
        "baseline_question_ids": [record.qid for record in qp_records],
        "coverage": coverage,
        "notes": (
            "Option D Hybrid Anchored Extraction. QO questions are mapped to domain ontology "
            "concepts; QP questions remain DB-only baseline unless explicitly promoted later. "
            "NightReallocationOperationsOntology is a domain_extension slice for 야간 재배치, "
            "200명 인력, Markov transition, worker dispatch, morning shortage risk, "
            "reallocation recommendation, route cost, capacity constraint. "
            f"# Timestamp: {timestamp}"
        ),
    }


def _json_dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _coverage_report(payload: dict[str, Any]) -> str:
    coverage = payload["coverage"]
    candidates = payload["domain_candidate_records"]
    return "\n".join(
        [
            f"# Timestamp: {payload['timestamp']}",
            "",
            "# Ttareungi Domain Ontology Lite v2 Coverage Report",
            "",
            "## Summary",
            "",
            f"- strategy: `{payload['strategy']}`",
            f"- ontology_name: `{payload['ontology_name']}`",
            f"- parent_ontology: `{payload['parent_ontology']}`",
            f"- purpose: {payload['purpose']}",
            f"- status: `{payload['status']}`",
            f"- formalization_level: `{payload['formalization_level']}`",
            f"- upper_ontology_source: `{payload['upper_ontology_source']}`",
            f"- QO coverage: `{coverage['qo_mapped']}/{coverage['qo_total']}`",
            f"- QP baseline-only: `{coverage['qp_baseline_only']}/{coverage['qp_total']}`",
            f"- domain candidates: `{len(candidates)}`",
            f"- upper alignment edges: `{len(payload['upper_alignment_edges'])}`",
            "",
            "## Acceptance Slices",
            "",
            "- weather-demand episode: `DemandEpisode`, `RecoveryEpisode`, `ShortageEpisode`",
            "- role-aware flow: `StationRoleProfile`, `ImbalanceCorridor`",
            "- bike fault lifecycle: `BikeLifecyclePath`, `MaintenanceSinkStation`",
            "- provenance/confidence: `EvidenceEdge`, `SourceArtifact`, `ConfidenceAssessment`",
            "- night reallocation operations: `NightReallocationShift`, `DispatchAgent`, `ReallocationAction`, `ReallocationRoute`, `MarkovTransitionPolicy`, `MorningShortageRisk`, `ReallocationRecommendation`, `WorkforceCapacityConstraint`",
        ]
    )


def _human_review_csv(payload: dict[str, Any]) -> str:
    buffer = StringIO()
    buffer.write(f"# Timestamp: {payload['timestamp']}\n")
    fieldnames = [
        "canonical_name",
        "upper_parent",
        "candidate_type",
        "promotion_decision",
        "evidence_kind",
        "confidence",
        "cq_ids",
        "physical_sources",
        "relations",
        "short_definition",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for candidate in payload["domain_candidate_records"]:
        writer.writerow(
            {
                "canonical_name": candidate["canonical_name"],
                "upper_parent": candidate["upper_parent"],
                "candidate_type": candidate["candidate_type"],
                "promotion_decision": candidate["promotion_decision"],
                "evidence_kind": candidate["evidence_kind"],
                "confidence": candidate["confidence"],
                "cq_ids": "|".join(candidate["cq_ids"]),
                "physical_sources": "|".join(candidate["physical_sources"]),
                "relations": "|".join(candidate["relations"]),
                "short_definition": candidate["short_definition"],
            }
        )
    return buffer.getvalue()


def write_ttareungi_domain_ontology_run(
    project_root: Path,
    output_dir: Path | None = None,
    timestamp: str | None = None,
) -> Path:
    timestamp = timestamp or _now()
    output_root = output_dir or project_root / DOMAIN_RUNS_RELATIVE_DIR
    run_dir = output_root / f"run_{_run_stamp(timestamp)}_ttareungi_domain_ontology_v2"
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = build_ttareungi_domain_ontology(project_root, timestamp=timestamp)

    _json_dump(run_dir / "domain_candidate_records.json", payload["domain_candidate_records"])
    _json_dump(run_dir / "domain_promotion_records.json", payload["domain_promotion_records"])
    _json_dump(run_dir / "upper_alignment_edges.json", payload["upper_alignment_edges"])
    _json_dump(run_dir / "ttareungi_domain_ontology_lite.json", payload)
    (run_dir / "coverage_report.md").write_text(_coverage_report(payload), encoding="utf-8")
    (run_dir / "human_review.csv").write_text(_human_review_csv(payload), encoding="utf-8")
    return run_dir


def latest_domain_ontology_run(project_root: Path) -> Path | None:
    return _latest_run_dir(project_root / DOMAIN_RUNS_RELATIVE_DIR, "ttareungi_domain_ontology_lite.json")


def load_latest_domain_ontology(project_root: Path) -> dict[str, Any] | None:
    run_dir = latest_domain_ontology_run(project_root)
    if run_dir is None:
        return None
    return json.loads((run_dir / "ttareungi_domain_ontology_lite.json").read_text(encoding="utf-8"))


def build_domain_ontology_documents(project_root: Path, profile: str) -> list[Any]:
    if profile != "ontology-hybrid":
        return []

    from rag.ttareungi_rag import RagDocument

    payload = load_latest_domain_ontology(project_root)
    if payload is None:
        question_bank_path = project_root / QUESTION_BANK_RELATIVE_PATH
        if not question_bank_path.exists():
            return []
        payload = build_ttareungi_domain_ontology(project_root)

    coverage = payload["coverage"]
    candidates = payload["domain_candidate_records"]
    metadata = {
        "profile": profile,
        "source": "ttareungi-domain-ontology-lite-v2.1",
        "brief_type": "domain_ontology_lite_brief",
        "source_kind": "domain_ontology",
        "dataset_name": "",
        "dataset_id": "",
        "category": "semantic_model",
        "local_path": "",
        "time_token": "",
        "availability": "available",
        "columns": [],
        "granularity": "domain_ontology_registry",
        "time_range": "",
        "row_count": None,
    }
    class_summary = ", ".join(
        f"{candidate['canonical_name']} upper_parent={candidate['upper_parent']} "
        f"evidence_kind={candidate['evidence_kind']} confidence={candidate['confidence']:.2f}"
        for candidate in candidates
    )
    return [
        RagDocument(
            doc_id="ttareungi-domain-ontology-lite-v2.1:model",
            text=(
                "Ttareungi domain ontology-lite v2.1 generated by hybrid anchored extraction. "
                f"Ontology name {payload.get('ontology_name', NIGHT_REALLOCATION_ONTOLOGY_NAME)}; "
                f"parent ontology {payload.get('parent_ontology', NIGHT_REALLOCATION_PARENT_ONTOLOGY)}; "
                f"purpose {payload.get('purpose', NIGHT_REALLOCATION_PURPOSE)}; "
                f"formalization level {payload.get('formalization_level', NIGHT_REALLOCATION_FORMALIZATION_LEVEL)}. "
                f"QO coverage {coverage['qo_mapped']}/{coverage['qo_total']}; "
                f"QP baseline-only {coverage['qp_baseline_only']}/{coverage['qp_total']}. "
                f"Classes and upper_parent mappings: {class_summary}. "
                f"Relations: {', '.join(payload['relations'])}."
            ),
            metadata=metadata,
        ),
        RagDocument(
            doc_id="ttareungi-domain-ontology-lite-v2.1:acceptance",
            text=(
                "Domain ontology-lite v2.1 acceptance slices. "
                "weather-demand episode uses DemandEpisode, RecoveryEpisode, ShortageEpisode. "
                "role-aware movement uses StationRoleProfile and ImbalanceCorridor. "
                "bike fault lifecycle uses BikeLifecyclePath and MaintenanceSinkStation. "
                "provenance/confidence uses EvidenceEdge, SourceArtifact, ConfidenceAssessment. "
                "night reallocation operations uses NightReallocationOperationsOntology, NightReallocationShift, "
                "DispatchAgent, ReallocationAction, ReallocationRoute, MarkovTransitionPolicy, "
                "MorningShortageRisk, ReallocationRecommendation, WorkforceCapacityConstraint. "
                "Korean retrieval aliases: 야간 재배치, 200명 인력, Markov transition, worker dispatch, "
                "morning shortage risk, reallocation recommendation, route cost, capacity constraint."
            ),
            metadata=metadata | {"category": "semantic_acceptance"},
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Ttareungi domain ontology-lite v2 from upper anchors.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timestamp")
    args = parser.parse_args()

    run_dir = write_ttareungi_domain_ontology_run(
        project_root=args.project_root,
        output_dir=args.output_dir,
        timestamp=args.timestamp,
    )
    print(run_dir)


if __name__ == "__main__":
    main()
