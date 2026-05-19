# Timestamp: 2026-05-11 16:36:00

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd


TOOLS_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_SCRIPTS_DIR))

from rag.ttareungi_rag import find_project_root, processed_bike_cloud_dir  # noqa: E402


DEFAULT_OUTPUT_ROOT = Path("data/processed/exports/reallocation_simulation_runs")
DEFAULT_AGENT_COUNT = 200
DEFAULT_TRIPS_PER_AGENT = 3
DEFAULT_BIKES_PER_TRIP = 1
DEFAULT_TOTAL_CAPACITY = DEFAULT_AGENT_COUNT * DEFAULT_TRIPS_PER_AGENT * DEFAULT_BIKES_PER_TRIP
DEFAULT_PRIMARY_DISTANCE_KM = 5.0
DEFAULT_FALLBACK_DISTANCE_KM = 10.0
DEFAULT_CANDIDATE_LIMIT = 80
POLICY_NATIVE = "native baseline"
POLICY_ONTOLOGY = "ontology-base simulation"
POLICY_SEMANTIC_FLOW = "ontology-semantic-flow"
ONTOLOGY_POLICIES = (POLICY_ONTOLOGY, POLICY_SEMANTIC_FLOW)


@dataclass(frozen=True)
class SimulationConfig:
    plan_date: date
    timestamp: str
    agent_count: int = DEFAULT_AGENT_COUNT
    trips_per_agent_per_night: int = DEFAULT_TRIPS_PER_AGENT
    bikes_per_trip: int = DEFAULT_BIKES_PER_TRIP
    total_capacity: int = DEFAULT_TOTAL_CAPACITY
    primary_distance_km: float = DEFAULT_PRIMARY_DISTANCE_KM
    fallback_distance_km: float = DEFAULT_FALLBACK_DISTANCE_KM
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _run_stamp(timestamp: str) -> str:
    return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d_%H%M%S")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _parse_date(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if not value:
        raise ValueError("plan_date is required")
    return datetime.strptime(value, "%Y-%m-%d").date()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def _normalize(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0).astype(float)
    max_value = float(numeric.max()) if not numeric.empty else 0.0
    if max_value <= 0:
        return pd.Series([0.0] * len(numeric), index=numeric.index)
    return numeric / max_value


def _safe_columns(path: Path, columns: Sequence[str]) -> list[str]:
    try:
        import pyarrow.parquet as pq

        available = set(pq.ParquetFile(path).schema_arrow.names)
        return [column for column in columns if column in available]
    except Exception:
        return list(columns)


def _read_parquet(path: Path, columns: Sequence[str], filters: list[tuple[str, str, Any]] | None = None) -> pd.DataFrame:
    selected_columns = _safe_columns(path, columns)
    if not path.exists():
        return pd.DataFrame(columns=selected_columns)
    try:
        import pyarrow.parquet as pq

        table = pq.read_table(path, columns=selected_columns or None, filters=filters)
        return table.to_pandas()
    except Exception:
        frame = pd.read_parquet(path, columns=selected_columns or None)
        return frame


def _infer_latest_plan_date(data_dir: Path) -> date:
    count_path = data_dir / "count_data.parquet"
    try:
        import pyarrow.parquet as pq

        parquet_file = pq.ParquetFile(count_path)
        date_index = parquet_file.schema_arrow.names.index("date_rt")
        max_dates: list[date] = []
        for index in range(parquet_file.metadata.num_row_groups):
            stats = parquet_file.metadata.row_group(index).column(date_index).statistics
            if stats and stats.max:
                max_value = stats.max
                if isinstance(max_value, datetime):
                    max_dates.append(max_value.date())
                elif isinstance(max_value, date):
                    max_dates.append(max_value)
        if max_dates:
            return max(max_dates)
    except Exception:
        pass
    frame = pd.read_parquet(count_path, columns=["date_rt"])
    values = pd.to_datetime(frame["date_rt"], errors="coerce").dropna()
    if values.empty:
        raise ValueError("Could not infer plan_date from count_data.parquet")
    return values.max().date()


def _date_filters_for_count(plan_date: date) -> list[tuple[str, str, Any]]:
    previous = plan_date - timedelta(days=1)
    return [("date_rt", ">=", previous), ("date_rt", "<=", plan_date)]


def _timestamp_filters_for_rent(plan_date: date) -> list[tuple[str, str, Any]]:
    previous = plan_date - timedelta(days=1)
    start = datetime.combine(previous, time(0, 0, 0))
    end = datetime.combine(plan_date, time(23, 59, 59))
    return [("date_rt", ">=", start), ("date_rt", "<=", end)]


def _latest_branch_frame(data_dir: Path) -> pd.DataFrame:
    frame = _read_parquet(
        data_dir / "branch_data.parquet",
        ["date", "branchnum", "branchname", "location1", "location2", "branch_x", "branch_y"],
    )
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame.get("date"), errors="coerce")
    frame = frame.sort_values(["branchnum", "date"]).drop_duplicates("branchnum", keep="last")
    frame["branchnum"] = pd.to_numeric(frame["branchnum"], errors="coerce").astype("Int64")
    frame["branch_x"] = pd.to_numeric(frame["branch_x"], errors="coerce")
    frame["branch_y"] = pd.to_numeric(frame["branch_y"], errors="coerce")
    return frame.dropna(subset=["branchnum", "branch_x", "branch_y"]).copy()


def _prepare_count_frame(data_dir: Path, config: SimulationConfig) -> pd.DataFrame:
    frame = _read_parquet(
        data_dir / "count_data.parquet",
        ["date_rt", "branchnum", "hour_cnt", "cnt_rack"],
        filters=_date_filters_for_count(config.plan_date),
    )
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date_rt"], errors="coerce").dt.date
    frame["hour_cnt"] = pd.to_numeric(frame["hour_cnt"], errors="coerce").fillna(-1).astype(int)
    frame["cnt_rack"] = pd.to_numeric(frame["cnt_rack"], errors="coerce").fillna(0)
    frame["branchnum"] = pd.to_numeric(frame["branchnum"], errors="coerce").astype("Int64")
    return frame.dropna(subset=["branchnum", "date"])


def _prepare_rent_frame(data_dir: Path, config: SimulationConfig) -> pd.DataFrame:
    frame = _read_parquet(
        data_dir / "rent_data.parquet",
        ["date_rt", "branchnum_r", "branchnum_b", "hour_cnt", "dist"],
        filters=_timestamp_filters_for_rent(config.plan_date),
    )
    if frame.empty:
        return frame
    frame["date_time"] = pd.to_datetime(frame["date_rt"], errors="coerce")
    frame["date"] = frame["date_time"].dt.date
    frame["hour_cnt"] = pd.to_numeric(frame["hour_cnt"], errors="coerce").fillna(frame["date_time"].dt.hour).astype(int)
    for column in ["branchnum_r", "branchnum_b"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Int64")
    return frame.dropna(subset=["branchnum_r", "branchnum_b", "date"])


def _prepare_monthly_frame(data_dir: Path, plan_date: date) -> pd.DataFrame:
    path = data_dir / "uselate_data.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["branchnum", "cnt_r", "cnt_b"])
    frame = _read_parquet(path, ["date_ym", "branchnum", "cnt_r", "cnt_b"])
    if frame.empty:
        return frame
    frame["month"] = pd.to_datetime(frame["date_ym"], errors="coerce").dt.to_period("M")
    target_month = pd.Period(plan_date, freq="M")
    frame = frame[frame["month"] == target_month]
    if frame.empty:
        return pd.DataFrame(columns=["branchnum", "cnt_r", "cnt_b"])
    frame["branchnum"] = pd.to_numeric(frame["branchnum"], errors="coerce").astype("Int64")
    frame["cnt_r"] = pd.to_numeric(frame["cnt_r"], errors="coerce").fillna(0)
    frame["cnt_b"] = pd.to_numeric(frame["cnt_b"], errors="coerce").fillna(0)
    return frame.groupby("branchnum", as_index=False)[["cnt_r", "cnt_b"]].sum()


def _count_by_station(frame: pd.DataFrame, station_column: str) -> pd.Series:
    if frame.empty or station_column not in frame.columns:
        return pd.Series(dtype=float)
    return frame.groupby(station_column).size().astype(float)


def build_station_states(data_dir: Path, config: SimulationConfig) -> pd.DataFrame:
    previous = config.plan_date - timedelta(days=1)
    branch = _latest_branch_frame(data_dir)
    count = _prepare_count_frame(data_dir, config)
    rent = _prepare_rent_frame(data_dir, config)
    monthly = _prepare_monthly_frame(data_dir, config.plan_date)

    evening_or_night_count = count[
        ((count["date"] == previous) & count["hour_cnt"].between(17, 23))
        | ((count["date"] == config.plan_date) & count["hour_cnt"].between(0, 5))
    ]
    morning_count = count[(count["date"] == config.plan_date) & count["hour_cnt"].between(7, 10)]
    evening_or_night_rent = rent[
        ((rent["date"] == previous) & rent["hour_cnt"].between(17, 23))
        | ((rent["date"] == config.plan_date) & rent["hour_cnt"].between(0, 5))
    ]
    morning_rent = rent[(rent["date"] == config.plan_date) & rent["hour_cnt"].between(7, 10)]

    surplus_count = evening_or_night_count.groupby("branchnum")["cnt_rack"].sum() if not evening_or_night_count.empty else pd.Series(dtype=float)
    morning_mean = morning_count.groupby("branchnum")["cnt_rack"].mean() if not morning_count.empty else pd.Series(dtype=float)
    low_morning_stock = (morning_mean.max() - morning_mean).clip(lower=0) if not morning_mean.empty else pd.Series(dtype=float)
    return_counts = _count_by_station(evening_or_night_rent, "branchnum_b")
    start_counts = _count_by_station(morning_rent, "branchnum_r")

    states = branch[["branchnum", "branchname", "location1", "location2", "branch_x", "branch_y"]].copy()
    states = states.rename(columns={"branch_x": "lat", "branch_y": "lon", "location1": "district"})
    states["branchnum"] = states["branchnum"].astype(int)
    states = states.set_index("branchnum", drop=False)

    states["surplus_count_signal"] = states.index.map(surplus_count).fillna(0).astype(float)
    states["return_count_signal"] = states.index.map(return_counts).fillna(0).astype(float)
    states["low_morning_stock_signal"] = states.index.map(low_morning_stock).fillna(0).astype(float)
    states["start_count_signal"] = states.index.map(start_counts).fillna(0).astype(float)

    if not monthly.empty:
        monthly = monthly.set_index("branchnum")
        states["monthly_cnt_r"] = states.index.map(monthly["cnt_r"]).fillna(0).astype(float)
        states["monthly_cnt_b"] = states.index.map(monthly["cnt_b"]).fillna(0).astype(float)
    else:
        states["monthly_cnt_r"] = 0.0
        states["monthly_cnt_b"] = 0.0

    states["surplus_risk"] = (
        0.45 * _normalize(states["return_count_signal"])
        + 0.35 * _normalize(states["surplus_count_signal"])
        + 0.20 * _normalize(states["monthly_cnt_b"])
    ).round(4)
    states["morning_shortage_risk"] = (
        0.55 * _normalize(states["start_count_signal"])
        + 0.25 * _normalize(states["low_morning_stock_signal"])
        + 0.20 * _normalize(states["monthly_cnt_r"])
    ).round(4)
    states["estimated_surplus_bikes"] = np.ceil(states["surplus_risk"] * 8).astype(int)
    states["estimated_shortage_bikes"] = np.ceil(states["morning_shortage_risk"] * 8).astype(int)
    return states.reset_index(drop=True)


def build_markov_edges(data_dir: Path, config: SimulationConfig) -> pd.DataFrame:
    rent = _prepare_rent_frame(data_dir, config)
    if rent.empty:
        return pd.DataFrame(columns=["dropoff_station", "pickup_station", "transition_count", "transition_probability"])
    grouped = rent.groupby(["branchnum_r", "branchnum_b"]).size().reset_index(name="transition_count")
    grouped = grouped.rename(columns={"branchnum_r": "dropoff_station", "branchnum_b": "pickup_station"})
    totals = grouped.groupby("dropoff_station")["transition_count"].transform("sum")
    grouped["transition_probability"] = grouped["transition_count"] / totals.replace(0, np.nan)
    return grouped


def _candidate_pairs(states: pd.DataFrame, markov_edges: pd.DataFrame, config: SimulationConfig) -> pd.DataFrame:
    pickups = states[states["estimated_surplus_bikes"] > 0].sort_values("surplus_risk", ascending=False).head(config.candidate_limit)
    dropoffs = states[states["estimated_shortage_bikes"] > 0].sort_values("morning_shortage_risk", ascending=False).head(config.candidate_limit)
    rows: list[dict[str, Any]] = []
    transition_lookup = {
        (int(row.dropoff_station), int(row.pickup_station)): float(row.transition_probability)
        for row in markov_edges.itertuples(index=False)
    }
    for pickup in pickups.itertuples(index=False):
        for dropoff in dropoffs.itertuples(index=False):
            if int(pickup.branchnum) == int(dropoff.branchnum):
                continue
            distance = haversine_km(float(pickup.lat), float(pickup.lon), float(dropoff.lat), float(dropoff.lon))
            if distance > config.fallback_distance_km:
                continue
            corridor = transition_lookup.get((int(dropoff.branchnum), int(pickup.branchnum)), 0.0)
            route_cost_score = min(distance / config.fallback_distance_km, 1.0)
            role_stability = 1.0 if float(pickup.surplus_risk) > 0 and float(dropoff.morning_shortage_risk) > 0 else 0.0
            ontology_score = (
                0.35 * float(dropoff.morning_shortage_risk)
                + 0.25 * float(pickup.surplus_risk)
                + 0.20 * corridor
                + 0.10 * role_stability
                - 0.10 * route_cost_score
            )
            rows.append(
                {
                    "pickup_station": int(pickup.branchnum),
                    "pickup_name": pickup.branchname,
                    "pickup_district": pickup.district,
                    "pickup_lat": round(float(pickup.lat), 7),
                    "pickup_lon": round(float(pickup.lon), 7),
                    "dropoff_station": int(dropoff.branchnum),
                    "dropoff_name": dropoff.branchname,
                    "dropoff_district": dropoff.district,
                    "dropoff_lat": round(float(dropoff.lat), 7),
                    "dropoff_lon": round(float(dropoff.lon), 7),
                    "distance_km": round(distance, 4),
                    "surplus_risk": round(float(pickup.surplus_risk), 4),
                    "morning_shortage_risk": round(float(dropoff.morning_shortage_risk), 4),
                    "corridor_imbalance": round(float(corridor), 4),
                    "route_cost_score": round(route_cost_score, 4),
                    "role_stability": round(role_stability, 4),
                    "estimated_surplus_bikes": int(pickup.estimated_surplus_bikes),
                    "estimated_shortage_bikes": int(dropoff.estimated_shortage_bikes),
                    "ontology_reallocation_score": round(ontology_score, 4),
                    "distance_priority_band": 0 if distance <= config.primary_distance_km else 1,
                }
            )
    return pd.DataFrame(rows)


def _confidence_for_pair(row: pd.Series, policy: str) -> float:
    if policy == POLICY_NATIVE:
        confidence = 0.5
    elif policy == POLICY_SEMANTIC_FLOW:
        confidence = 0.62
    else:
        confidence = 0.58
    if float(row["distance_km"]) <= DEFAULT_PRIMARY_DISTANCE_KM:
        confidence += 0.05
    if float(row["corridor_imbalance"]) > 0:
        confidence += 0.05
    if float(row["surplus_risk"]) > 0.4 and float(row["morning_shortage_risk"]) > 0.4:
        confidence += 0.08
    confidence -= 0.10  # worker/route log 부재
    if float(row["distance_km"]) > DEFAULT_FALLBACK_DISTANCE_KM:
        confidence -= 0.15
    return round(max(0.0, min(confidence, 0.95)), 4)


def _semantic_flow_components(row: pd.Series, config: SimulationConfig) -> dict[str, Any]:
    confidence = _confidence_for_pair(row, POLICY_SEMANTIC_FLOW)
    confidence_penalty = round(max(0.0, 0.62 - confidence), 4)
    evidence_gate = "pass" if confidence >= 0.57 and float(row["distance_km"]) <= config.primary_distance_km else "limited"
    fallback_penalty = 0.30 if float(row["distance_km"]) > config.primary_distance_km else 0.0
    semantic_reward = round(
        0.48 * float(row["morning_shortage_risk"])
        + 0.24 * float(row["surplus_risk"])
        + 0.18 * float(row["corridor_imbalance"])
        + 0.08 * float(row.get("role_stability", 0.0)),
        4,
    )
    semantic_cost = round(0.55 * float(row["route_cost_score"]) + confidence_penalty + fallback_penalty, 4)
    semantic_flow_score = round(semantic_reward - semantic_cost, 4)
    constraints = [
        "SurplusRisk",
        "MorningShortageRisk",
        "MarkovTransitionPolicy",
        "ReallocationRoute",
        "EvidenceEdge",
        "WorkforceCapacityConstraint",
    ]
    explanation = (
        f"shortage={float(row['morning_shortage_risk']):.4f}, surplus={float(row['surplus_risk']):.4f}, "
        f"markov={float(row['corridor_imbalance']):.4f}, distance={float(row['distance_km']):.2f}km, "
        f"confidence={confidence:.4f}, gate={evidence_gate}"
    )
    return {
        "semantic_flow_score": semantic_flow_score,
        "semantic_reward": semantic_reward,
        "semantic_cost": semantic_cost,
        "confidence_penalty": confidence_penalty,
        "evidence_gate": evidence_gate,
        "ontology_constraints_applied": "|".join(constraints),
        "explanation": explanation,
        "confidence": confidence,
    }


def _base_recommendation(
    row: pd.Series,
    policy: str,
    move_count: int,
    capacity_remaining: int,
    confidence: float,
    evidence_kind: str,
    source_refs: str,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "policy": policy,
        "shift_window": "23:00~05:00",
        "pickup_station": int(row["pickup_station"]),
        "pickup_name": row["pickup_name"],
        "pickup_district": row["pickup_district"],
        "pickup_lat": row["pickup_lat"],
        "pickup_lon": row["pickup_lon"],
        "dropoff_station": int(row["dropoff_station"]),
        "dropoff_name": row["dropoff_name"],
        "dropoff_district": row["dropoff_district"],
        "dropoff_lat": row["dropoff_lat"],
        "dropoff_lon": row["dropoff_lon"],
        "distance_km": row["distance_km"],
        "recommended_bike_count": move_count,
        "surplus_risk": row["surplus_risk"],
        "morning_shortage_risk": row["morning_shortage_risk"],
        "corridor_imbalance": row["corridor_imbalance"],
        "route_cost_score": row["route_cost_score"],
        "ontology_reallocation_score": row["ontology_reallocation_score"],
        "capacity_remaining_after": capacity_remaining,
        "evidence_kind": evidence_kind,
        "worker_route_evidence_kind": "weak-context",
        "confidence": confidence,
        "source_refs": source_refs,
        "semantic_flow_score": "",
        "semantic_reward": "",
        "semantic_cost": "",
        "confidence_penalty": "",
        "evidence_gate": "",
        "ontology_constraints_applied": "",
        "explanation": "",
    }
    if extra_fields:
        payload.update(extra_fields)
    return payload


def _simulate_semantic_flow(pairs: pd.DataFrame, config: SimulationConfig) -> list[dict[str, Any]]:
    if pairs.empty:
        return []
    eligible = pairs[
        (pairs["surplus_risk"] > 0)
        & (pairs["morning_shortage_risk"] > 0)
        & (pairs["distance_km"] <= config.fallback_distance_km)
    ].copy()
    if eligible.empty:
        return []
    component_rows = eligible.apply(lambda row: pd.Series(_semantic_flow_components(row, config)), axis=1)
    eligible = pd.concat([eligible.reset_index(drop=True), component_rows.reset_index(drop=True)], axis=1)
    eligible["distance_micro_band"] = np.floor(eligible["distance_km"].astype(float) / 0.5).astype(int)
    eligible["evidence_gate_rank"] = np.where(eligible["evidence_gate"] == "pass", 0, 1)
    eligible = eligible.sort_values(
        ["distance_priority_band", "distance_km", "semantic_flow_score", "morning_shortage_risk"],
        ascending=[True, True, False, False],
    )

    remaining_surplus = {
        int(row.pickup_station): int(row.estimated_surplus_bikes)
        for row in eligible.drop_duplicates("pickup_station").itertuples(index=False)
    }
    remaining_shortage = {
        int(row.dropoff_station): int(row.estimated_shortage_bikes)
        for row in eligible.drop_duplicates("dropoff_station").itertuples(index=False)
    }
    capacity_remaining = config.total_capacity
    recommendations: list[dict[str, Any]] = []

    for _, row in eligible.iterrows():
        if capacity_remaining <= 0:
            break
        pickup_station = int(row["pickup_station"])
        dropoff_station = int(row["dropoff_station"])
        surplus_left = int(remaining_surplus.get(pickup_station, 0))
        shortage_left = int(remaining_shortage.get(dropoff_station, 0))
        if surplus_left <= 0 or shortage_left <= 0:
            continue
        gate_cap = 2 if row["evidence_gate"] == "limited" else surplus_left
        move_count = min(surplus_left, shortage_left, int(capacity_remaining), gate_cap)
        if move_count <= 0:
            continue
        remaining_surplus[pickup_station] -= move_count
        remaining_shortage[dropoff_station] -= move_count
        capacity_remaining -= move_count
        evidence_kind = "derived" if row["evidence_gate"] == "pass" else "inferred"
        recommendations.append(
            _base_recommendation(
                row=row,
                policy=POLICY_SEMANTIC_FLOW,
                move_count=move_count,
                capacity_remaining=capacity_remaining,
                confidence=float(row["confidence"]),
                evidence_kind=evidence_kind,
                source_refs=(
                    "branch_data.parquet|count_data.parquet|rent_data.parquet|uselate_data.parquet|"
                    "NightReallocationOperationsOntology|MarkovTransitionPolicy|EvidenceEdge"
                ),
                extra_fields={
                    "semantic_flow_score": row["semantic_flow_score"],
                    "semantic_reward": row["semantic_reward"],
                    "semantic_cost": row["semantic_cost"],
                    "confidence_penalty": row["confidence_penalty"],
                    "evidence_gate": row["evidence_gate"],
                    "ontology_constraints_applied": row["ontology_constraints_applied"],
                    "explanation": row["explanation"],
                },
            )
        )
    return recommendations


def _simulate_policy(pairs: pd.DataFrame, config: SimulationConfig, policy: str) -> list[dict[str, Any]]:
    if policy == POLICY_SEMANTIC_FLOW:
        return _simulate_semantic_flow(pairs, config)
    if pairs.empty:
        return []
    if policy == POLICY_NATIVE:
        ordered = pairs.sort_values(
            ["distance_priority_band", "distance_km", "morning_shortage_risk", "surplus_risk"],
            ascending=[True, True, False, False],
        )
    else:
        ordered = pairs.sort_values(
            ["distance_priority_band", "ontology_reallocation_score", "distance_km"],
            ascending=[True, False, True],
        )

    remaining_surplus = {
        int(row.pickup_station): int(row.estimated_surplus_bikes)
        for row in ordered.drop_duplicates("pickup_station").itertuples(index=False)
    }
    remaining_shortage = {
        int(row.dropoff_station): int(row.estimated_shortage_bikes)
        for row in ordered.drop_duplicates("dropoff_station").itertuples(index=False)
    }
    capacity_remaining = config.total_capacity
    recommendations: list[dict[str, Any]] = []

    for _, row in ordered.iterrows():
        if capacity_remaining <= 0:
            break
        pickup_station = int(row["pickup_station"])
        dropoff_station = int(row["dropoff_station"])
        move_count = min(
            int(remaining_surplus.get(pickup_station, 0)),
            int(remaining_shortage.get(dropoff_station, 0)),
            int(capacity_remaining),
        )
        if move_count <= 0:
            continue
        remaining_surplus[pickup_station] -= move_count
        remaining_shortage[dropoff_station] -= move_count
        capacity_remaining -= move_count
        confidence = _confidence_for_pair(row, policy)
        evidence_kind = "derived" if policy in ONTOLOGY_POLICIES and float(row["distance_km"]) <= config.primary_distance_km else "inferred"
        source_refs = (
            "branch_data.parquet|count_data.parquet|rent_data.parquet"
            if policy == POLICY_NATIVE
            else "branch_data.parquet|count_data.parquet|rent_data.parquet|uselate_data.parquet|NightReallocationOperationsOntology"
        )
        recommendations.append(
            _base_recommendation(
                row=row,
                policy=policy,
                move_count=move_count,
                capacity_remaining=capacity_remaining,
                confidence=confidence,
                evidence_kind=evidence_kind,
                source_refs=source_refs,
            )
        )
    return recommendations


def _after_state_rows(states: pd.DataFrame, recommendations: Sequence[dict[str, Any]], policy: str) -> list[dict[str, Any]]:
    moved_in: dict[int, int] = {}
    moved_out: dict[int, int] = {}
    for row in recommendations:
        if row["policy"] != policy:
            continue
        moved_in[int(row["dropoff_station"])] = moved_in.get(int(row["dropoff_station"]), 0) + int(row["recommended_bike_count"])
        moved_out[int(row["pickup_station"])] = moved_out.get(int(row["pickup_station"]), 0) + int(row["recommended_bike_count"])

    rows: list[dict[str, Any]] = []
    for state in states.itertuples(index=False):
        shortage_before = float(state.morning_shortage_risk)
        estimated_shortage = max(int(state.estimated_shortage_bikes), 1)
        inbound = moved_in.get(int(state.branchnum), 0)
        reduction = min(shortage_before, shortage_before * inbound / estimated_shortage)
        rows.append(
            {
                "policy": policy,
                "station": int(state.branchnum),
                "station_name": state.branchname,
                "district": state.district,
                "surplus_risk_before": round(float(state.surplus_risk), 4),
                "morning_shortage_risk_before": round(shortage_before, 4),
                "moved_in_bikes": inbound,
                "moved_out_bikes": moved_out.get(int(state.branchnum), 0),
                "morning_shortage_risk_after": round(max(0.0, shortage_before - reduction), 4),
            }
        )
    return rows


def _policy_metrics(
    policy: str,
    recommendations: Sequence[dict[str, Any]],
    state_rows: Sequence[dict[str, Any]],
    total_capacity: int,
) -> dict[str, Any]:
    routes = [row for row in recommendations if row["policy"] == policy]
    before = sum(float(row["morning_shortage_risk_before"]) for row in state_rows if row["policy"] == policy)
    after = sum(float(row["morning_shortage_risk_after"]) for row in state_rows if row["policy"] == policy)
    total_bikes = sum(int(row["recommended_bike_count"]) for row in routes)
    distances = [float(row["distance_km"]) for row in routes]
    weighted_distance = sum(float(row["distance_km"]) * int(row["recommended_bike_count"]) for row in routes)
    coverage_fields = ["distance_km", "recommended_bike_count", "evidence_kind", "confidence", "source_refs"]
    if routes:
        recommendation_coverage = sum(
            1 for row in routes if all(str(row.get(field, "")).strip() for field in coverage_fields)
        ) / len(routes)
        weak_context_guard = sum(
            1 for row in routes if row.get("worker_route_evidence_kind") in {"weak-context", "inferred"}
        ) / len(routes)
    else:
        recommendation_coverage = 1.0
        weak_context_guard = 1.0
    return {
        "route_count": len(routes),
        "total_recommended_bike_count": total_bikes,
        "morning_shortage_reduction": round((before - after) / before, 4) if before > 0 else 0.0,
        "avg_distance_km": round(float(np.mean(distances)), 4) if distances else 0.0,
        "p95_distance_km": round(float(np.percentile(distances, 95)), 4) if distances else 0.0,
        "bike_moves_per_km": round(total_bikes / weighted_distance, 4) if weighted_distance > 0 else 0.0,
        "capacity_utilization": round(total_bikes / total_capacity, 4) if total_capacity else 0.0,
        "recommendation_coverage": round(recommendation_coverage, 4),
        "weak_context_guard": round(weak_context_guard, 4),
    }


def _summary_markdown(
    config: SimulationConfig,
    run_dir: Path,
    metrics: dict[str, Any],
    recommendations: Sequence[dict[str, Any]],
) -> str:
    ontology_metrics = metrics["policies"][POLICY_ONTOLOGY]
    semantic_metrics = metrics["policies"][POLICY_SEMANTIC_FLOW]
    native_metrics = metrics["policies"][POLICY_NATIVE]
    lines = [
        f"# Timestamp: {config.timestamp}",
        "",
        "# 온톨로지 기반 야간 재배치 시뮬레이션 요약",
        "",
        "- ontology: `NightReallocationOperationsOntology`",
        "- parent ontology: `Ttareungi Domain Ontology-lite v2.1`",
        f"- run_dir: `{run_dir}`",
        f"- plan_date: `{config.plan_date.isoformat()}`",
        "- shift_window: `23:00~05:00`",
        "- evaluation_window: `07:00~10:00`",
        f"- capacity: `{config.total_capacity} bikes/night`",
        "",
        "## KPI 비교",
        "",
        "| policy | routes | bikes | shortage_reduction | avg_distance_km | p95_distance_km | capacity_utilization | recommendation_coverage | weak_context_guard |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for policy in [POLICY_NATIVE, POLICY_ONTOLOGY, POLICY_SEMANTIC_FLOW]:
        item = metrics["policies"][policy]
        lines.append(
            f"| `{policy}` | {item['route_count']} | {item['total_recommended_bike_count']} | "
            f"{item['morning_shortage_reduction']} | {item['avg_distance_km']} | {item['p95_distance_km']} | "
            f"{item['capacity_utilization']} | {item['recommendation_coverage']} | {item['weak_context_guard']} |"
        )
    lines.extend(
        [
            "",
            "## 해석",
            "",
            (
                f"- ontology-base shortage reduction은 native 대비 "
                f"`{round(ontology_metrics['morning_shortage_reduction'] - native_metrics['morning_shortage_reduction'], 4)}`p 차이다."
            ),
            (
                f"- ontology-semantic-flow shortage reduction은 native 대비 "
                f"`{round(semantic_metrics['morning_shortage_reduction'] - native_metrics['morning_shortage_reduction'], 4)}`p 차이다."
            ),
            "- 실제 worker route log가 없으므로 `DispatchAgent`와 `WorkforceCapacityConstraint`는 `weak-context`로 유지한다.",
            "- `cnt_rack`은 실시간 재고 확정값이 아니라 shortage/surplus rank 신호로만 해석한다.",
            "",
            "## 추천 route preview",
            "",
            "| policy | pickup | dropoff | distance_km | bikes | confidence | evidence_kind |",
            "| :--- | :--- | :--- | ---: | ---: | ---: | :--- |",
        ]
    )
    for row in list(recommendations)[:10]:
        lines.append(
            f"| `{row['policy']}` | {row['pickup_station']} {row['pickup_name']} | "
            f"{row['dropoff_station']} {row['dropoff_name']} | {row['distance_km']} | "
            f"{row['recommended_bike_count']} | {row['confidence']} | `{row['evidence_kind']}` |"
        )
    return "\n".join(lines) + "\n"


def _comparison_rows(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for policy, values in metrics["policies"].items():
        row = {"policy": policy}
        row.update(values)
        rows.append(row)
    return rows


def build_ontology_markov_simulation_payload(
    project_root: Path,
    plan_date: str | date | None = None,
    timestamp: str | None = None,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    """Build an in-memory ontology-only Markov simulation payload for GUI use."""
    data_dir = processed_bike_cloud_dir(project_root)
    run_timestamp = timestamp or _now()
    resolved_plan_date = _parse_date(plan_date) if plan_date else _infer_latest_plan_date(data_dir)
    config = SimulationConfig(plan_date=resolved_plan_date, timestamp=run_timestamp, candidate_limit=candidate_limit)
    states = build_station_states(data_dir, config)
    markov_edges = build_markov_edges(data_dir, config)
    pairs = _candidate_pairs(states, markov_edges, config)
    recommendations = _simulate_policy(pairs, config, POLICY_SEMANTIC_FLOW)
    state_rows = _after_state_rows(states, recommendations, POLICY_SEMANTIC_FLOW)
    metrics = _policy_metrics(POLICY_SEMANTIC_FLOW, recommendations, state_rows, config.total_capacity)
    manifest = {
        "timestamp": run_timestamp,
        "plan_date": config.plan_date.isoformat(),
        "policy": POLICY_SEMANTIC_FLOW,
        "shift_window": "23:00~05:00",
        "evaluation_window": "07:00~10:00",
        "agent_count": config.agent_count,
        "trips_per_agent_per_night": config.trips_per_agent_per_night,
        "bikes_per_trip": config.bikes_per_trip,
        "total_capacity": config.total_capacity,
        "primary_distance_km": config.primary_distance_km,
        "fallback_distance_km": config.fallback_distance_km,
        "candidate_limit": config.candidate_limit,
        "ontology": "NightReallocationOperationsOntology",
        "parent_ontology": "Ttareungi Domain Ontology-lite v2.1",
    }
    top_markov_edges = (
        markov_edges.sort_values(["transition_probability", "transition_count"], ascending=[False, False])
        .head(50)
        .to_dict(orient="records")
        if not markov_edges.empty
        else []
    )
    return {
        "timestamp": run_timestamp,
        "policy": POLICY_SEMANTIC_FLOW,
        "manifest": manifest,
        "metrics": metrics,
        "routes": recommendations,
        "station_states": state_rows,
        "markov_edges": top_markov_edges,
    }


def run_simulation(
    project_root: Path,
    plan_date: str | date | None = None,
    output_root: Path | None = None,
    timestamp: str | None = None,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> Path:
    data_dir = processed_bike_cloud_dir(project_root)
    run_timestamp = timestamp or _now()
    resolved_plan_date = _parse_date(plan_date) if plan_date else _infer_latest_plan_date(data_dir)
    config = SimulationConfig(plan_date=resolved_plan_date, timestamp=run_timestamp, candidate_limit=candidate_limit)
    resolved_output_root = output_root or project_root / DEFAULT_OUTPUT_ROOT
    run_dir = resolved_output_root / f"run_{_run_stamp(run_timestamp)}_ontology_night_reallocation"
    run_dir.mkdir(parents=True, exist_ok=True)

    states = build_station_states(data_dir, config)
    markov_edges = build_markov_edges(data_dir, config)
    pairs = _candidate_pairs(states, markov_edges, config)
    recommendations = (
        _simulate_policy(pairs, config, POLICY_NATIVE)
        + _simulate_policy(pairs, config, POLICY_ONTOLOGY)
        + _simulate_policy(pairs, config, POLICY_SEMANTIC_FLOW)
    )
    state_rows = (
        _after_state_rows(states, recommendations, POLICY_NATIVE)
        + _after_state_rows(states, recommendations, POLICY_ONTOLOGY)
        + _after_state_rows(states, recommendations, POLICY_SEMANTIC_FLOW)
    )

    metrics = {
        "timestamp": run_timestamp,
        "plan_date": config.plan_date.isoformat(),
        "policies": {
            POLICY_NATIVE: _policy_metrics(POLICY_NATIVE, recommendations, state_rows, config.total_capacity),
            POLICY_ONTOLOGY: _policy_metrics(POLICY_ONTOLOGY, recommendations, state_rows, config.total_capacity),
            POLICY_SEMANTIC_FLOW: _policy_metrics(POLICY_SEMANTIC_FLOW, recommendations, state_rows, config.total_capacity),
        },
    }
    native_reduction = metrics["policies"][POLICY_NATIVE]["morning_shortage_reduction"]
    ontology_reduction = metrics["policies"][POLICY_ONTOLOGY]["morning_shortage_reduction"]
    semantic_reduction = metrics["policies"][POLICY_SEMANTIC_FLOW]["morning_shortage_reduction"]
    metrics["ontology_value_uplift"] = {
        "morning_shortage_reduction_delta": round(ontology_reduction - native_reduction, 4),
        "recommendation_coverage_delta": round(
            metrics["policies"][POLICY_ONTOLOGY]["recommendation_coverage"]
            - metrics["policies"][POLICY_NATIVE]["recommendation_coverage"],
            4,
        ),
    }
    metrics["semantic_flow_uplift"] = {
        "morning_shortage_reduction_delta": round(semantic_reduction - native_reduction, 4),
        "recommendation_coverage_delta": round(
            metrics["policies"][POLICY_SEMANTIC_FLOW]["recommendation_coverage"]
            - metrics["policies"][POLICY_NATIVE]["recommendation_coverage"],
            4,
        ),
        "avg_distance_delta_km": round(
            metrics["policies"][POLICY_SEMANTIC_FLOW]["avg_distance_km"]
            - metrics["policies"][POLICY_NATIVE]["avg_distance_km"],
            4,
        ),
    }

    manifest = {
        "timestamp": run_timestamp,
        "plan_date": config.plan_date.isoformat(),
        "shift_window": "23:00~05:00",
        "evaluation_window": "07:00~10:00",
        "agent_count": config.agent_count,
        "trips_per_agent_per_night": config.trips_per_agent_per_night,
        "bikes_per_trip": config.bikes_per_trip,
        "total_capacity": config.total_capacity,
        "primary_distance_km": config.primary_distance_km,
        "fallback_distance_km": config.fallback_distance_km,
        "candidate_limit": config.candidate_limit,
        "ontology": "NightReallocationOperationsOntology",
        "parent_ontology": "Ttareungi Domain Ontology-lite v2.1",
        "source_refs": [
            "branch_data.parquet",
            "count_data.parquet",
            "rent_data.parquet",
            "uselate_data.parquet",
            "weather_data.parquet",
        ],
    }

    route_fields = [
        "plan_date",
        "policy",
        "shift_window",
        "pickup_station",
        "pickup_name",
        "pickup_district",
        "pickup_lat",
        "pickup_lon",
        "dropoff_station",
        "dropoff_name",
        "dropoff_district",
        "dropoff_lat",
        "dropoff_lon",
        "distance_km",
        "recommended_bike_count",
        "surplus_risk",
        "morning_shortage_risk",
        "corridor_imbalance",
        "route_cost_score",
        "ontology_reallocation_score",
        "semantic_flow_score",
        "semantic_reward",
        "semantic_cost",
        "confidence_penalty",
        "evidence_gate",
        "ontology_constraints_applied",
        "explanation",
        "capacity_remaining_after",
        "evidence_kind",
        "worker_route_evidence_kind",
        "confidence",
        "source_refs",
    ]
    route_rows = [{"plan_date": config.plan_date.isoformat(), **row} for row in recommendations]
    state_fields = [
        "policy",
        "station",
        "station_name",
        "district",
        "surplus_risk_before",
        "morning_shortage_risk_before",
        "moved_in_bikes",
        "moved_out_bikes",
        "morning_shortage_risk_after",
    ]
    comparison_fields = [
        "policy",
        "route_count",
        "total_recommended_bike_count",
        "morning_shortage_reduction",
        "avg_distance_km",
        "p95_distance_km",
        "bike_moves_per_km",
        "capacity_utilization",
        "recommendation_coverage",
        "weak_context_guard",
    ]

    _write_json(run_dir / "run_manifest.json", manifest)
    _write_csv(run_dir / "recommended_routes.csv", route_rows, route_fields)
    _write_csv(run_dir / "station_state_before_after.csv", state_rows, state_fields)
    _write_json(run_dir / "simulation_metrics.json", metrics)
    _write_csv(run_dir / "policy_comparison.csv", _comparison_rows(metrics), comparison_fields)
    (run_dir / "simulation_summary.md").write_text(
        _summary_markdown(config, run_dir, metrics, recommendations),
        encoding="utf-8",
    )
    return run_dir


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Ttareungi ontology-based night reallocation simulation.")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--plan-date", default=None, help="YYYY-MM-DD. Defaults to latest count_data date.")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--candidate-limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
    parser.add_argument("--timestamp", default=None)
    args = parser.parse_args(argv)

    project_root = args.project_root or find_project_root(Path.cwd())
    output_root = args.output_root if args.output_root is None or args.output_root.is_absolute() else project_root / args.output_root
    run_dir = run_simulation(
        project_root=project_root,
        plan_date=args.plan_date,
        output_root=output_root,
        timestamp=args.timestamp,
        candidate_limit=args.candidate_limit,
    )
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
