# Timestamp: 2026-05-11 16:45:00

from __future__ import annotations

from pathlib import Path
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.ttareungi_reallocation_streamlit_app import (  # noqa: E402
    build_concept_rows,
    build_route_points,
    build_route_table,
)
from rag.run_ttareungi_reallocation_simulation import POLICY_SEMANTIC_FLOW  # noqa: E402


def _payload() -> dict:
    return {
        "routes": [
            {
                "policy": POLICY_SEMANTIC_FLOW,
                "pickup_station": 101,
                "pickup_name": "잉여A",
                "pickup_district": "마포구",
                "pickup_lat": 37.555,
                "pickup_lon": 126.91,
                "dropoff_station": 102,
                "dropoff_name": "부족B",
                "dropoff_district": "마포구",
                "dropoff_lat": 37.556,
                "dropoff_lon": 126.915,
                "distance_km": 0.45,
                "recommended_bike_count": 3,
                "surplus_risk": 0.8,
                "morning_shortage_risk": 0.9,
                "corridor_imbalance": 0.2,
                "evidence_kind": "derived",
                "confidence": 0.73,
                "semantic_flow_score": 0.91,
                "semantic_reward": 1.3,
                "semantic_cost": 0.39,
                "confidence_penalty": 0.1,
                "evidence_gate": "pass",
                "ontology_constraints_applied": "SurplusRisk|MorningShortageRisk|WorkforceCapacityConstraint",
                "explanation": "부족 위험과 Markov 근거가 높아 선택됨",
                "source_refs": "branch_data.parquet|count_data.parquet|rent_data.parquet|NightReallocationOperationsOntology",
            },
            {
                "policy": "native baseline",
                "pickup_station": 201,
                "pickup_name": "비교군",
                "dropoff_station": 202,
                "dropoff_name": "비교군",
                "pickup_lat": 37.5,
                "pickup_lon": 127.0,
                "dropoff_lat": 37.51,
                "dropoff_lon": 127.01,
                "distance_km": 1.0,
                "recommended_bike_count": 1,
            },
        ]
    }


def test_build_route_table_filters_to_ontology_markov_rows_only():
    rows = build_route_table(_payload(), limit=20)

    assert len(rows) == 1
    assert rows[0]["pickup_station"] == 101
    assert rows[0]["dropoff_station"] == 102
    assert "native baseline" not in str(rows)
    assert {
        "distance_km",
        "recommended_bike_count",
        "evidence_kind",
        "confidence",
        "semantic_flow_score",
        "evidence_gate",
        "source_refs",
    } <= set(rows[0])


def test_build_route_points_creates_pickup_and_dropoff_points():
    points = build_route_points(build_route_table(_payload()))

    assert len(points) == 2
    assert {point["role"] for point in points} == {"pickup", "dropoff"}
    assert all("lat" in point and "lon" in point for point in points)


def test_build_concept_rows_explains_markov_ontology_management():
    rows = build_concept_rows()
    names = {row["concept"] for row in rows}

    assert "NightReallocationOperationsOntology" in names
    assert "MarkovTransitionPolicy" in names
    assert "ReallocationRecommendation" in names
