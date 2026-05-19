# Timestamp: 2026-05-11 10:43:10
# Timestamp: 2026-05-11 13:24:00

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, Sequence


if TYPE_CHECKING:
    from rag.ttareungi_rag import FactSnippet, RagDocument


ONTOLOGY_LITE_CLASSES = [
    "Station",
    "Bike",
    "TripEvent",
    "StationHourlyCount",
    "BrokenEvent",
    "WeatherObservation",
    "DateBucket",
    "EvidenceEdge",
]
ONTOLOGY_LITE_RELATIONS = [
    "rental_station",
    "return_station",
    "same_bike",
    "observed_under_weather",
    "in_time_bucket",
    "supported_by",
    "derived_from",
]
EVIDENCE_KINDS = ["direct", "derived", "inferred", "weak-context"]


@dataclass(frozen=True)
class SemanticQueryPlan:
    intent: str
    target_entities: list[str]
    required_sources: list[str]
    answerability: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceEdge:
    source_entity: str
    relation: str
    target_entity: str
    evidence_kind: str
    confidence: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_text(self) -> str:
        return (
            f"EvidenceEdge {self.source_entity} {self.relation} {self.target_entity} "
            f"evidence_kind={self.evidence_kind} confidence={self.confidence:.2f} source={self.source}"
        )


def _current_question_text(question: str) -> str:
    marker = "현재 질문:"
    if marker not in question:
        return question
    return question.rsplit(marker, 1)[-1].strip()


def _terms(question: str) -> list[str]:
    return re.findall(r"[0-9a-zA-Z가-힣]+", _current_question_text(question))


def _contains_any(text: str, keywords: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _target_entities(question: str) -> list[str]:
    stopwords = {"따릉이", "대여소", "어디", "무엇", "어떤", "알려줘", "근거", "신뢰도"}
    generic_entity_terms = {"대여소", "자전거"}
    entities: list[str] = []
    for term in _terms(question):
        if len(term) < 2 or term in stopwords:
            continue
        if any(generic in term for generic in generic_entity_terms):
            continue
        if term.isdigit() or any(hint in term for hint in ["역", "구", "ST", "st", "자전거", "B"]):
            entities.append(term)
    return entities[:8]


def plan_semantic_query(question: str) -> SemanticQueryPlan:
    current_question = _current_question_text(question)
    lifecycle_keywords = ["직후", "직전", "재대여", "장거리", "lifecycle", "경로", "24시간"]
    weather_keywords = ["날씨", "비", "강수", "눈", "적설", "기온", "풍속", "폭염", "가시거리"]
    role_keywords = ["출근", "퇴근", "시작점", "반납", "목적지", "쏠림", "유입", "유출", "대여 시작"]
    provenance_keywords = ["근거", "신뢰도", "source", "출처", "온톨로지 필요", "provenance", "confidence", "evidence"]

    if "고장" in current_question and _contains_any(current_question, lifecycle_keywords):
        return SemanticQueryPlan(
            intent="bike_fault_lifecycle",
            target_entities=_target_entities(current_question),
            required_sources=["broken_data.parquet", "rent_data.parquet"],
            answerability="inferred",
        )
    if _contains_any(current_question, weather_keywords):
        return SemanticQueryPlan(
            intent="weather_demand_episode",
            target_entities=_target_entities(current_question),
            required_sources=["weather_data.parquet", "count_data.parquet", "branch_data.parquet"],
            answerability="derived",
        )
    if _contains_any(current_question, role_keywords):
        return SemanticQueryPlan(
            intent="station_role_flow",
            target_entities=_target_entities(current_question),
            required_sources=["rent_data.parquet", "branch_data.parquet"],
            answerability="direct",
        )
    if _contains_any(current_question, provenance_keywords):
        return SemanticQueryPlan(
            intent="provenance_confidence",
            target_entities=_target_entities(current_question),
            required_sources=[
                "branch_data.parquet",
                "rent_data.parquet",
                "count_data.parquet",
                "broken_data.parquet",
                "weather_data.parquet",
            ],
            answerability="weak-context",
        )
    return SemanticQueryPlan(
        intent="unsupported",
        target_entities=_target_entities(current_question),
        required_sources=[],
        answerability="unanswerable",
    )


def _processed_bike_cloud_dir(project_root: Path) -> Path:
    return project_root / "data" / "processed" / "parquet" / "bike_cloud"


def _relative_source(project_root: Path, *filenames: str) -> str:
    data_dir = _processed_bike_cloud_dir(project_root)
    return "+".join(str((data_dir / filename).relative_to(project_root)) for filename in filenames)


def _existing_columns(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        import pyarrow.parquet as pq

        return [str(column) for column in pq.ParquetFile(path).schema_arrow.names]
    except Exception:
        try:
            import pandas as pd

            return [str(column) for column in pd.read_parquet(path).columns]
        except Exception:
            return []


def _read_parquet(path: Path, preferred_columns: Sequence[str], max_rows: int | None = 200_000):
    import pandas as pd

    if not path.exists():
        return pd.DataFrame()
    available = set(_existing_columns(path))
    columns = [column for column in preferred_columns if column in available]
    if not columns:
        return pd.DataFrame()
    try:
        import pyarrow.parquet as pq

        parquet_file = pq.ParquetFile(path)
        if max_rows is None:
            return pd.read_parquet(path, columns=columns)
        frames = []
        rows_read = 0
        for batch in parquet_file.iter_batches(batch_size=min(max_rows, 50_000), columns=columns):
            frame = batch.to_pandas()
            remaining = max_rows - rows_read
            if len(frame) > remaining:
                frame = frame.head(remaining)
            frames.append(frame)
            rows_read += len(frame)
            if rows_read >= max_rows:
                break
        if not frames:
            return pd.DataFrame(columns=columns)
        return pd.concat(frames, ignore_index=True)
    except Exception:
        frame = pd.read_parquet(path, columns=columns)
        return frame.head(max_rows) if max_rows is not None else frame


def _large_unbounded_guard(project_root: Path, plan: SemanticQueryPlan, question: str) -> str:
    bounded_tokens = [r"20\d{2}", r"\d{1,2}월", r"\d{1,2}일", r"\d{2,5}\s*번", r"st-\d+", r"ST-\d+"]
    if any(re.search(pattern, question) for pattern in bounded_tokens) or plan.target_entities:
        return ""
    data_dir = _processed_bike_cloud_dir(project_root)
    large_sources = []
    for source in plan.required_sources:
        path = data_dir / source
        if path.exists() and path.stat().st_size > 64 * 1024 * 1024 and source in {"count_data.parquet", "rent_data.parquet"}:
            large_sources.append(source)
    if not large_sources:
        return ""
    if plan.intent == "weather_demand_episode":
        required_next_filter = "date_or_station_or_time_band"
        executable_slice = "WeatherObservation.datetime -> StationHourlyCount.date_rt/hour_cnt"
        relation_hint = "observed_under_weather"
    elif plan.intent == "station_role_flow":
        required_next_filter = "date_or_station_or_time_band"
        executable_slice = "branchnum_r:rental_station,branchnum_b:return_station"
        relation_hint = "rental_station,return_station"
    elif plan.intent == "bike_fault_lifecycle":
        required_next_filter = "bike_id_or_date_window_or_distance_threshold"
        executable_slice = "rent_data.bikenum -> broken_data.bikenum within_24h"
        relation_hint = "same_bike,in_time_bucket"
    else:
        required_next_filter = "date_or_entity_scope"
        executable_slice = "bounded_source_slice"
        relation_hint = "supported_by"
    return (
        f"intent={plan.intent} answerability=weak-context evidence_kind=weak-context confidence=0.35. "
        f"required_sources={','.join(plan.required_sources)}. "
        f"required_next_filter={required_next_filter}. executable_slice={executable_slice}. relations={relation_hint}. "
        f"대용량 source {', '.join(large_sources)}는 날짜/대여소/자전거 범위 없는 전역 row scan을 생략했습니다. "
        "범위를 좁히면 column pruning 기반 실측 evidence를 만들 수 있습니다."
    )


def _normalize_date_hour(frame: Any, date_column: str, hour_column: str | None = None):
    import pandas as pd

    normalized = frame.copy()
    normalized["_dt"] = pd.to_datetime(normalized[date_column], errors="coerce")
    normalized["_date_key"] = normalized["_dt"].dt.date.astype(str)
    if hour_column and hour_column in normalized.columns:
        normalized["_hour"] = pd.to_numeric(normalized[hour_column], errors="coerce").fillna(-1).astype(int)
    else:
        normalized["_hour"] = normalized["_dt"].dt.hour.fillna(-1).astype(int)
    return normalized


def _station_labels(project_root: Path) -> dict[str, str]:
    branch_path = _processed_bike_cloud_dir(project_root) / "branch_data.parquet"
    frame = _read_parquet(branch_path, ["date", "branchnum", "branchname", "location1"], max_rows=None)
    if frame.empty or "branchnum" not in frame.columns:
        return {}
    if "date" in frame.columns:
        frame = frame.sort_values(["branchnum", "date"]).drop_duplicates("branchnum", keep="last")
    labels = {}
    for row in frame.to_dict(orient="records"):
        station_id = str(row.get("branchnum", ""))
        labels[station_id] = f"{row.get('branchname', '')}({row.get('location1', '')})"
    return labels


def _metric_column(frame: Any, candidates: Sequence[str]) -> str:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return ""


def _weather_demand_facts(project_root: Path, question: str, plan: SemanticQueryPlan, limit: int) -> list[FactSnippet]:
    from rag.ttareungi_rag import FactSnippet

    guard = _large_unbounded_guard(project_root, plan, question)
    if guard:
        return [FactSnippet(title="Ontology-lite 성능 가드", text=guard, source="ontology-lite")]

    data_dir = _processed_bike_cloud_dir(project_root)
    weather = _read_parquet(
        data_dir / "weather_data.parquet",
        ["datetime", "temperature", "precipitation", "snowfall", "windspeed", "visibility"],
    )
    counts = _read_parquet(
        data_dir / "count_data.parquet",
        ["date_rt", "date", "branchnum", "hour_cnt", "cnt_rack", "rent_count", "return_count", "count"],
    )
    if weather.empty or counts.empty:
        return []

    weather_time = "datetime" if "datetime" in weather.columns else weather.columns[0]
    count_time = "date_rt" if "date_rt" in counts.columns else "date" if "date" in counts.columns else ""
    if not count_time or "branchnum" not in counts.columns:
        return []
    weather = _normalize_date_hour(weather, weather_time)
    counts = _normalize_date_hour(counts, count_time, "hour_cnt" if "hour_cnt" in counts.columns else None)

    if _contains_any(question, ["출근", "아침"]):
        weather = weather[weather["_hour"].isin([7, 8, 9])]
        counts = counts[counts["_hour"].isin([7, 8, 9])]
    event_mask = False
    for column in ["precipitation", "snowfall"]:
        if column in weather.columns:
            column_mask = weather[column].fillna(0).astype(float) > 0
            event_mask = column_mask if isinstance(event_mask, bool) else (event_mask | column_mask)
    if "windspeed" in weather.columns and _contains_any(question, ["풍속", "바람"]):
        wind_mask = weather["windspeed"].fillna(0).astype(float) >= 4
        event_mask = wind_mask if isinstance(event_mask, bool) else (event_mask | wind_mask)
    if not isinstance(event_mask, bool):
        weather = weather[event_mask]
    if weather.empty:
        return []

    metric = _metric_column(counts, ["cnt_rack", "rent_count", "return_count", "count"])
    if not metric:
        return []
    counts = counts.sort_values(["branchnum", "_date_key", "_hour"])
    counts["_previous_metric"] = counts.groupby("branchnum")[metric].shift(1)
    counts["_drop"] = counts["_previous_metric"].fillna(counts[metric]) - counts[metric]
    merged = counts.merge(
        weather,
        on=["_date_key", "_hour"],
        how="inner",
        suffixes=("_count", "_weather"),
    )
    if merged.empty:
        return []
    merged = merged.sort_values("_drop", ascending=False).head(limit)
    labels = _station_labels(project_root)
    snippets = []
    for row in merged.to_dict(orient="records"):
        station_id = str(row.get("branchnum", ""))
        station_label = labels.get(station_id, station_id)
        date_key = row.get("_date_key", "")
        hour = row.get("_hour", "")
        edge = EvidenceEdge(
            source_entity=f"StationHourlyCount:{station_id}@{date_key}T{hour}",
            relation="observed_under_weather",
            target_entity=f"WeatherObservation:{date_key}T{hour}",
            evidence_kind="derived",
            confidence=0.72,
            source=_relative_source(project_root, "count_data.parquet", "weather_data.parquet"),
        )
        snippets.append(
            FactSnippet(
                title="Ontology-lite 날씨-수요 episode",
                text=(
                    f"intent={plan.intent} answerability={plan.answerability}. "
                    f"{edge.to_text()}. supported_by Station:{station_id} {station_label}. "
                    f"metric={metric} observed={row.get(metric)} previous={row.get('_previous_metric')} drop={row.get('_drop')}."
                ),
                source=edge.source,
            )
        )
    return snippets


def _role_flow_facts(project_root: Path, question: str, plan: SemanticQueryPlan, limit: int) -> list[FactSnippet]:
    from rag.ttareungi_rag import FactSnippet

    guard = _large_unbounded_guard(project_root, plan, question)
    if guard:
        return [FactSnippet(title="Ontology-lite 성능 가드", text=guard, source="ontology-lite")]

    rent_path = _processed_bike_cloud_dir(project_root) / "rent_data.parquet"
    frame = _read_parquet(
        rent_path,
        ["date_rt", "rentt", "rentdate", "hour_cnt", "branchnum_r", "branchnum_b", "rentstation", "returnstation", "bikenum", "dist", "distance"],
    )
    if frame.empty:
        return []
    start_col = _metric_column(frame, ["branchnum_r", "rentstation"])
    return_col = _metric_column(frame, ["branchnum_b", "returnstation"])
    if not start_col or not return_col:
        return []
    start_counts = frame[start_col].astype(str).value_counts().head(limit)
    return_counts = frame[return_col].astype(str).value_counts().head(limit)
    top_ids = list(dict.fromkeys([*start_counts.index.astype(str), *return_counts.index.astype(str)]))[:limit]
    labels = _station_labels(project_root)
    parts = []
    for station_id in top_ids:
        start_count = int(start_counts.get(station_id, 0))
        return_count = int(return_counts.get(station_id, 0))
        parts.append(f"Station:{station_id} {labels.get(station_id, station_id)} start={start_count} return={return_count}")
    rental_edge = EvidenceEdge(
        source_entity=f"TripEvent.{start_col}",
        relation="rental_station",
        target_entity="Station",
        evidence_kind="direct",
        confidence=0.90,
        source=_relative_source(project_root, "rent_data.parquet"),
    )
    return_edge = EvidenceEdge(
        source_entity=f"TripEvent.{return_col}",
        relation="return_station",
        target_entity="Station",
        evidence_kind="direct",
        confidence=0.90,
        source=_relative_source(project_root, "rent_data.parquet"),
    )
    return [
        FactSnippet(
            title="Ontology-lite 대여/반납 role 구분",
            text=(
                f"intent={plan.intent} answerability={plan.answerability}. "
                f"{rental_edge.to_text()}. {return_edge.to_text()}. "
                f"role_summary {'; '.join(parts)}."
            ),
            source=rental_edge.source,
        )
    ]


def _bike_fault_lifecycle_facts(project_root: Path, question: str, plan: SemanticQueryPlan, limit: int) -> list[FactSnippet]:
    from rag.ttareungi_rag import FactSnippet

    guard = _large_unbounded_guard(project_root, plan, question)
    if guard:
        return [FactSnippet(title="Ontology-lite 성능 가드", text=guard, source="ontology-lite")]

    data_dir = _processed_bike_cloud_dir(project_root)
    broken = _read_parquet(data_dir / "broken_data.parquet", ["date_bk", "bikenum", "type_bk"])
    rent = _read_parquet(
        data_dir / "rent_data.parquet",
        ["date_rt", "rentt", "rentdate", "bikenum", "branchnum_r", "branchnum_b", "rentstation", "returnstation", "dist", "distance"],
    )
    if broken.empty or rent.empty or "bikenum" not in broken.columns or "bikenum" not in rent.columns:
        return []
    import pandas as pd

    broken = broken.copy()
    rent = rent.copy()
    broken["_broken_at"] = pd.to_datetime(broken["date_bk"], errors="coerce")
    time_col = _metric_column(rent, ["rentt", "date_rt", "rentdate"])
    rent["_rent_at"] = pd.to_datetime(rent[time_col], errors="coerce")
    distance_col = _metric_column(rent, ["dist", "distance"])
    merged = rent.merge(broken, on="bikenum", how="inner", suffixes=("_rent", "_broken"))
    merged["_hours_to_fault"] = (merged["_broken_at"] - merged["_rent_at"]).dt.total_seconds() / 3600
    merged = merged[(merged["_hours_to_fault"] >= 0) & (merged["_hours_to_fault"] <= 24)]
    if distance_col and _contains_any(question, ["장거리"]):
        merged = merged[pd.to_numeric(merged[distance_col], errors="coerce").fillna(0) >= 5000]
    if merged.empty:
        return []
    merged = merged.sort_values("_hours_to_fault").head(limit)
    snippets = []
    for row in merged.to_dict(orient="records"):
        bike_id = str(row.get("bikenum", ""))
        edge = EvidenceEdge(
            source_entity=f"TripEvent:bike:{bike_id}",
            relation="same_bike",
            target_entity=f"BrokenEvent:bike:{bike_id}",
            evidence_kind="inferred",
            confidence=0.64,
            source=_relative_source(project_root, "rent_data.parquet", "broken_data.parquet"),
        )
        snippets.append(
            FactSnippet(
                title="Ontology-lite 자전거 고장 lifecycle",
                text=(
                    f"intent={plan.intent} answerability={plan.answerability}. "
                    f"{edge.to_text()}. in_time_bucket within_24h hours_to_fault={round(float(row.get('_hours_to_fault', 0)), 2)}. "
                    f"distance={row.get(distance_col, '') if distance_col else ''} fault_type={row.get('type_bk', '')}."
                ),
                source=edge.source,
            )
        )
    return snippets


def _provenance_facts(project_root: Path, plan: SemanticQueryPlan) -> list[FactSnippet]:
    from rag.ttareungi_rag import FactSnippet

    source = "ontology-lite"
    return [
        FactSnippet(
            title="Ontology-lite provenance/confidence 모델",
            text=(
                f"intent={plan.intent} answerability={plan.answerability}. "
                f"classes={', '.join(ONTOLOGY_LITE_CLASSES)}. "
                f"relations={', '.join(ONTOLOGY_LITE_RELATIONS)}. "
                f"evidence_kinds={', '.join(EVIDENCE_KINDS)}. "
                "direct는 같은 row/key 근거, derived는 시간 bucket/episode 계산 근거, "
                "inferred는 window join 같은 추론 근거, weak-context는 보조 문맥 근거로 표기합니다."
            ),
            source=source,
        )
    ]


def collect_ontology_lite_facts(project_root: Path, question: str, limit: int = 6) -> list[FactSnippet]:
    plan = plan_semantic_query(question)
    if plan.intent == "weather_demand_episode":
        return _weather_demand_facts(project_root, question, plan, limit)
    if plan.intent == "station_role_flow":
        return _role_flow_facts(project_root, question, plan, limit)
    if plan.intent == "bike_fault_lifecycle":
        return _bike_fault_lifecycle_facts(project_root, question, plan, limit)
    if plan.intent == "provenance_confidence":
        return _provenance_facts(project_root, plan)
    return []


def build_ontology_lite_documents(project_root: Path, profile: str) -> list[RagDocument]:
    from rag.ttareungi_rag import RagDocument

    source = "ontology-lite"
    metadata = {
        "profile": profile,
        "source": source,
        "brief_type": "ontology_lite_brief",
        "source_kind": "ontology_lite",
        "dataset_name": "",
        "dataset_id": "",
        "category": "semantic_model",
        "local_path": "",
        "time_token": "",
        "availability": "available",
        "columns": [],
        "granularity": "semantic_query_plan",
        "time_range": "",
        "row_count": None,
    }
    return [
        RagDocument(
            doc_id="ontology-lite:model",
            text=(
                "Ontology-lite MVP semantic model. "
                f"Classes: {', '.join(ONTOLOGY_LITE_CLASSES)}. "
                f"Relations: {', '.join(ONTOLOGY_LITE_RELATIONS)}. "
                f"Evidence kinds: {', '.join(EVIDENCE_KINDS)}. "
                "EvidenceEdge carries source_entity, relation, target_entity, evidence_kind, confidence, source."
            ),
            metadata=metadata,
        ),
        RagDocument(
            doc_id="ontology-lite:routing",
            text=(
                "Ontology-lite semantic query routing. "
                "weather_demand_episode uses weather_data.parquet, count_data.parquet, branch_data.parquet. "
                "station_role_flow separates rent_data.parquet branchnum_r/rental_station from branchnum_b/return_station. "
                "bike_fault_lifecycle links broken_data.parquet and rent_data.parquet by same_bike within a time window. "
                "provenance_confidence explains answerability, source, confidence, direct, derived, inferred, weak-context."
            ),
            metadata=metadata | {"category": "semantic_routing"},
        ),
    ]
