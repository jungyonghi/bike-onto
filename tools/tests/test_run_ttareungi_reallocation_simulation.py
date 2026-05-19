# Timestamp: 2026-05-11 16:36:00

from __future__ import annotations

import csv
from datetime import date
import json
from pathlib import Path
import sys

import pandas as pd


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.run_ttareungi_reallocation_simulation import (  # noqa: E402
    DEFAULT_TOTAL_CAPACITY,
    POLICY_ONTOLOGY,
    POLICY_SEMANTIC_FLOW,
    SimulationConfig,
    _simulate_policy,
    build_ontology_markov_simulation_payload,
    haversine_km,
    run_simulation,
)


def _make_simulation_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    data_dir = project_root / "data" / "processed" / "parquet" / "bike_cloud"
    data_dir.mkdir(parents=True, exist_ok=True)
    (project_root / ".obybk-root").write_text("", encoding="utf-8")

    pd.DataFrame(
        [
            {
                "date": "2026-05-10",
                "branchnum": 101,
                "branchname": "잉여A",
                "location1": "마포구",
                "location2": "서울 마포구",
                "branch_x": 37.5550,
                "branch_y": 126.9100,
                "ilcd": 0,
                "iqr": 0,
                "sy": "QR",
            },
            {
                "date": "2026-05-10",
                "branchnum": 102,
                "branchname": "부족B",
                "location1": "마포구",
                "location2": "서울 마포구",
                "branch_x": 37.5560,
                "branch_y": 126.9150,
                "ilcd": 0,
                "iqr": 0,
                "sy": "QR",
            },
            {
                "date": "2026-05-10",
                "branchnum": 201,
                "branchname": "잉여C",
                "location1": "강남구",
                "location2": "서울 강남구",
                "branch_x": 37.5000,
                "branch_y": 127.0300,
                "ilcd": 0,
                "iqr": 0,
                "sy": "QR",
            },
        ]
    ).to_parquet(data_dir / "branch_data.parquet", index=False)

    pd.DataFrame(
        [
            {"date_rt": "2026-05-09", "branchnum": 101, "hour_cnt": 18, "cnt_rack": 30},
            {"date_rt": "2026-05-09", "branchnum": 101, "hour_cnt": 23, "cnt_rack": 25},
            {"date_rt": "2026-05-10", "branchnum": 201, "hour_cnt": 1, "cnt_rack": 20},
            {"date_rt": "2026-05-10", "branchnum": 102, "hour_cnt": 8, "cnt_rack": 4},
        ]
    ).to_parquet(data_dir / "count_data.parquet", index=False)

    pd.DataFrame(
        [
            {
                "date_rt": "2026-05-09 18:10:00",
                "rentt": "2026-05-09 18:10:00",
                "bikenum": 1,
                "branchnum_r": 102,
                "branchnum_b": 101,
                "hour_cnt": 18,
                "cnt_rack": 0,
                "cnt_rack_b": 0,
                "dist": 1000.0,
            },
            {
                "date_rt": "2026-05-10 08:10:00",
                "rentt": "2026-05-10 08:10:00",
                "bikenum": 2,
                "branchnum_r": 102,
                "branchnum_b": 101,
                "hour_cnt": 8,
                "cnt_rack": 0,
                "cnt_rack_b": 0,
                "dist": 1000.0,
            },
            {
                "date_rt": "2026-05-10 08:20:00",
                "rentt": "2026-05-10 08:20:00",
                "bikenum": 3,
                "branchnum_r": 102,
                "branchnum_b": 201,
                "hour_cnt": 8,
                "cnt_rack": 0,
                "cnt_rack_b": 0,
                "dist": 8000.0,
            },
        ]
    ).to_parquet(data_dir / "rent_data.parquet", index=False)

    pd.DataFrame(
        [
            {"date_ym": "2026-05-01", "branchnum": 101, "cnt_r": 1, "cnt_b": 9},
            {"date_ym": "2026-05-01", "branchnum": 102, "cnt_r": 9, "cnt_b": 1},
        ]
    ).to_parquet(data_dir / "uselate_data.parquet", index=False)

    pd.DataFrame(
        [
            {
                "datetime": "2026-05-10 08:00:00",
                "temperature": 18.0,
                "precipitation": 0.0,
                "windspeed": 1.0,
                "snowfall": 0.0,
                "holiday": 0,
            }
        ]
    ).to_parquet(data_dir / "weather_data.parquet", index=False)
    return project_root


def test_haversine_km_returns_reasonable_seoul_distance():
    distance = haversine_km(37.5550, 126.9100, 37.5560, 126.9150)

    assert 0.3 < distance < 0.7


def test_run_simulation_writes_recommendations_metrics_and_reports(tmp_path):
    project_root = _make_simulation_project(tmp_path)

    run_dir = run_simulation(
        project_root=project_root,
        plan_date="2026-05-10",
        output_root=tmp_path / "runs",
        timestamp="2026-05-11 16:36:00",
        candidate_limit=3,
    )

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    metrics = json.loads((run_dir / "simulation_metrics.json").read_text(encoding="utf-8"))
    routes = list(csv.DictReader((run_dir / "recommended_routes.csv").open(encoding="utf-8")))
    states = list(csv.DictReader((run_dir / "station_state_before_after.csv").open(encoding="utf-8")))
    summary = (run_dir / "simulation_summary.md").read_text(encoding="utf-8")

    assert manifest["plan_date"] == "2026-05-10"
    assert manifest["total_capacity"] == DEFAULT_TOTAL_CAPACITY
    assert {row["policy"] for row in routes} == {"native baseline", "ontology-base simulation", POLICY_SEMANTIC_FLOW}
    assert all(row["pickup_station"] != row["dropoff_station"] for row in routes)
    assert all(float(row["distance_km"]) <= 10.0 for row in routes)
    assert sum(int(row["recommended_bike_count"]) for row in routes if row["policy"] == "ontology-base simulation") <= 600
    assert {"distance_km", "recommended_bike_count", "evidence_kind", "confidence", "source_refs"} <= set(routes[0])
    assert all(row["evidence_kind"] in {"derived", "inferred", "weak-context"} for row in routes)
    assert metrics["policies"]["ontology-base simulation"]["recommendation_coverage"] == 1.0
    assert metrics["policies"]["ontology-base simulation"]["weak_context_guard"] == 1.0
    assert metrics["policies"][POLICY_SEMANTIC_FLOW]["recommendation_coverage"] == 1.0
    assert states
    assert "# Timestamp: 2026-05-11 16:36:00" in summary
    assert "NightReallocationOperationsOntology" in summary


def test_ontology_markov_payload_is_not_a_profile_comparison(tmp_path):
    project_root = _make_simulation_project(tmp_path)

    payload = build_ontology_markov_simulation_payload(
        project_root=project_root,
        plan_date="2026-05-10",
        timestamp="2026-05-11 16:45:00",
        candidate_limit=3,
    )

    assert payload["policy"] == POLICY_SEMANTIC_FLOW
    assert payload["manifest"]["ontology"] == "NightReallocationOperationsOntology"
    assert payload["metrics"]["route_count"] >= 1
    assert {row["policy"] for row in payload["routes"]} == {POLICY_SEMANTIC_FLOW}
    assert all(row["source_refs"] for row in payload["routes"])
    assert "native baseline" not in json.dumps(payload, ensure_ascii=False)


def test_run_simulation_adds_semantic_flow_policy_with_ontology_fields(tmp_path):
    project_root = _make_simulation_project(tmp_path)

    run_dir = run_simulation(
        project_root=project_root,
        plan_date="2026-05-10",
        output_root=tmp_path / "runs",
        timestamp="2026-05-11 17:24:00",
        candidate_limit=3,
    )

    metrics = json.loads((run_dir / "simulation_metrics.json").read_text(encoding="utf-8"))
    routes = list(csv.DictReader((run_dir / "recommended_routes.csv").open(encoding="utf-8")))
    semantic_routes = [row for row in routes if row["policy"] == POLICY_SEMANTIC_FLOW]

    assert POLICY_SEMANTIC_FLOW in metrics["policies"]
    assert semantic_routes
    assert sum(int(row["recommended_bike_count"]) for row in semantic_routes) <= DEFAULT_TOTAL_CAPACITY
    assert all(row["pickup_station"] != row["dropoff_station"] for row in semantic_routes)
    assert all(float(row["distance_km"]) <= 10.0 for row in semantic_routes)
    assert {
        "semantic_flow_score",
        "semantic_reward",
        "semantic_cost",
        "confidence_penalty",
        "evidence_gate",
        "ontology_constraints_applied",
        "explanation",
    } <= set(semantic_routes[0])
    assert all(row["evidence_gate"] in {"pass", "limited"} for row in semantic_routes)
    assert all("NightReallocationOperationsOntology" in row["source_refs"] for row in semantic_routes)
    assert metrics["policies"][POLICY_SEMANTIC_FLOW]["recommendation_coverage"] == 1.0
    assert metrics["policies"][POLICY_SEMANTIC_FLOW]["weak_context_guard"] == 1.0


def test_semantic_flow_payload_is_the_gui_default_policy(tmp_path):
    project_root = _make_simulation_project(tmp_path)

    payload = build_ontology_markov_simulation_payload(
        project_root=project_root,
        plan_date="2026-05-10",
        timestamp="2026-05-11 17:24:00",
        candidate_limit=3,
    )

    assert payload["policy"] == POLICY_SEMANTIC_FLOW
    assert payload["manifest"]["policy"] == POLICY_SEMANTIC_FLOW
    assert {row["policy"] for row in payload["routes"]} == {POLICY_SEMANTIC_FLOW}


def test_semantic_flow_prefers_higher_ontology_score_inside_same_distance_band():
    pairs = pd.DataFrame(
        [
            {
                "pickup_station": 101,
                "pickup_name": "높은근거",
                "pickup_district": "마포구",
                "pickup_lat": 37.55,
                "pickup_lon": 126.91,
                "dropoff_station": 201,
                "dropoff_name": "부족",
                "dropoff_district": "마포구",
                "dropoff_lat": 37.56,
                "dropoff_lon": 126.92,
                "distance_km": 1.0,
                "surplus_risk": 0.9,
                "morning_shortage_risk": 0.9,
                "corridor_imbalance": 0.5,
                "route_cost_score": 0.1,
                "role_stability": 1.0,
                "estimated_surplus_bikes": 1,
                "estimated_shortage_bikes": 1,
                "ontology_reallocation_score": 0.8,
                "distance_priority_band": 0,
            },
            {
                "pickup_station": 102,
                "pickup_name": "낮은근거",
                "pickup_district": "마포구",
                "pickup_lat": 37.55,
                "pickup_lon": 126.91,
                "dropoff_station": 201,
                "dropoff_name": "부족",
                "dropoff_district": "마포구",
                "dropoff_lat": 37.56,
                "dropoff_lon": 126.92,
                "distance_km": 1.0,
                "surplus_risk": 0.2,
                "morning_shortage_risk": 0.9,
                "corridor_imbalance": 0.0,
                "route_cost_score": 0.1,
                "role_stability": 1.0,
                "estimated_surplus_bikes": 1,
                "estimated_shortage_bikes": 1,
                "ontology_reallocation_score": 0.3,
                "distance_priority_band": 0,
            },
        ]
    )
    config = SimulationConfig(plan_date=date(2026, 5, 10), timestamp="2026-05-11 17:44:00")

    routes = _simulate_policy(pairs, config, POLICY_SEMANTIC_FLOW)

    assert routes[0]["pickup_station"] == 101
    assert float(routes[0]["semantic_flow_score"]) > 0
    assert routes[0]["evidence_gate"] == "pass"
