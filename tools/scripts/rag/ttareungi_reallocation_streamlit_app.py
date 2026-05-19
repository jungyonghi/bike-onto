# Timestamp: 2026-05-11 16:45:00

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Sequence

import pandas as pd


TOOLS_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_SCRIPTS_DIR))

from rag.run_ttareungi_reallocation_simulation import (  # noqa: E402
    DEFAULT_CANDIDATE_LIMIT,
    POLICY_SEMANTIC_FLOW,
    build_ontology_markov_simulation_payload,
)
from rag.ttareungi_rag import find_project_root  # noqa: E402


DEFAULT_MAP_ROUTE_LIMIT = 80


def _require_streamlit():
    try:
        import streamlit as st
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise SystemExit(
            "streamlit이 설치되어 있지 않습니다. "
            "다음 명령으로 설치하세요: venv/bin/pip install -r tools/scripts/rag/requirements-streamlit.txt"
        ) from exc
    return st


def build_concept_rows() -> list[dict[str, str]]:
    return [
        {
            "concept": "NightReallocationOperationsOntology",
            "role": "야간 재배치 운영 slice",
            "source": "ontology-lite registry",
        },
        {
            "concept": "MarkovTransitionPolicy",
            "role": "station OD 전이 확률로 재배치 방향을 보정",
            "source": "rent_data.parquet",
        },
        {
            "concept": "MorningShortageRisk",
            "role": "다음날 07:00~10:00 부족 위험",
            "source": "count_data.parquet|rent_data.parquet",
        },
        {
            "concept": "ReallocationRoute",
            "role": "Haversine distance 기반 route cost",
            "source": "branch_data.parquet",
        },
        {
            "concept": "WorkforceCapacityConstraint",
            "role": "200명, 600 bikes/night scenario constraint",
            "source": "weak-context",
        },
        {
            "concept": "ReallocationRecommendation",
            "role": "pickup/dropoff, 이동 대수, confidence 추천 결과",
            "source": "simulation payload",
        },
        {
            "concept": "EvidenceEdge",
            "role": "source_refs, evidence_kind, confidence 연결",
            "source": "ontology-lite registry",
        },
    ]


def build_route_table(payload: dict[str, Any], limit: int = DEFAULT_MAP_ROUTE_LIMIT) -> list[dict[str, Any]]:
    rows = [row for row in payload.get("routes", []) if row.get("policy") == POLICY_SEMANTIC_FLOW]
    rows = sorted(
        rows,
        key=lambda row: (
            -float(row.get("morning_shortage_risk", 0.0)),
            float(row.get("distance_km", 0.0)),
            -float(row.get("confidence", 0.0)),
        ),
    )
    selected: list[dict[str, Any]] = []
    for row in rows[:limit]:
        selected.append(
            {
                "pickup_station": row.get("pickup_station"),
                "pickup_name": row.get("pickup_name"),
                "pickup_district": row.get("pickup_district"),
                "pickup_lat": row.get("pickup_lat"),
                "pickup_lon": row.get("pickup_lon"),
                "dropoff_station": row.get("dropoff_station"),
                "dropoff_name": row.get("dropoff_name"),
                "dropoff_district": row.get("dropoff_district"),
                "dropoff_lat": row.get("dropoff_lat"),
                "dropoff_lon": row.get("dropoff_lon"),
                "distance_km": row.get("distance_km"),
                "recommended_bike_count": row.get("recommended_bike_count"),
                "surplus_risk": row.get("surplus_risk"),
                "morning_shortage_risk": row.get("morning_shortage_risk"),
                "corridor_imbalance": row.get("corridor_imbalance"),
                "semantic_flow_score": row.get("semantic_flow_score"),
                "semantic_reward": row.get("semantic_reward"),
                "semantic_cost": row.get("semantic_cost"),
                "confidence_penalty": row.get("confidence_penalty"),
                "evidence_gate": row.get("evidence_gate"),
                "ontology_constraints_applied": row.get("ontology_constraints_applied"),
                "explanation": row.get("explanation"),
                "evidence_kind": row.get("evidence_kind"),
                "confidence": row.get("confidence"),
                "source_refs": row.get("source_refs"),
            }
        )
    return selected


def build_route_points(routes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in routes:
        points.append(
            {
                "lat": float(row["pickup_lat"]),
                "lon": float(row["pickup_lon"]),
                "role": "pickup",
                "station": row["pickup_station"],
                "name": row["pickup_name"],
                "recommended_bike_count": row["recommended_bike_count"],
            }
        )
        points.append(
            {
                "lat": float(row["dropoff_lat"]),
                "lon": float(row["dropoff_lon"]),
                "role": "dropoff",
                "station": row["dropoff_station"],
                "name": row["dropoff_name"],
                "recommended_bike_count": row["recommended_bike_count"],
            }
        )
    return points


def _build_line_rows(routes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in routes:
        rows.append(
            {
                "from": [float(row["pickup_lon"]), float(row["pickup_lat"])],
                "to": [float(row["dropoff_lon"]), float(row["dropoff_lat"])],
                "recommended_bike_count": int(row["recommended_bike_count"]),
                "tooltip": (
                    f"{row['pickup_station']} -> {row['dropoff_station']} / "
                    f"{row['recommended_bike_count']}대 / confidence={row['confidence']}"
                ),
            }
        )
    return rows


def _render_map(st, routes: Sequence[dict[str, Any]]) -> None:
    points = build_route_points(routes)
    if not points:
        st.info("표시할 추천 route가 없습니다.")
        return
    point_frame = pd.DataFrame(points)
    try:
        import pydeck as pdk

        line_frame = pd.DataFrame(_build_line_rows(routes))
        layers = [
            pdk.Layer(
                "ScatterplotLayer",
                point_frame,
                get_position="[lon, lat]",
                get_fill_color="[40, 110, 220, 180]",
                get_radius=70,
                pickable=True,
            ),
            pdk.Layer(
                "LineLayer",
                line_frame,
                get_source_position="from",
                get_target_position="to",
                get_color="[220, 80, 60, 160]",
                get_width=3,
                pickable=True,
            ),
        ]
        view_state = pdk.ViewState(
            latitude=float(point_frame["lat"].mean()),
            longitude=float(point_frame["lon"].mean()),
            zoom=10,
            pitch=0,
        )
        st.pydeck_chart(
            pdk.Deck(
                map_style=None,
                initial_view_state=view_state,
                layers=layers,
                tooltip={"text": "{tooltip}{name}\n{role} {station}"},
            ),
            use_container_width=True,
        )
    except Exception:
        st.map(point_frame[["lat", "lon"]], use_container_width=True)


def _metric_value(metrics: dict[str, Any], key: str) -> str:
    value = metrics.get(key, 0)
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def run_app() -> None:
    st = _require_streamlit()
    st.set_page_config(page_title="따릉이 Markov 재배치 시뮬레이터", layout="wide")
    st.title("따릉이 Markov 재배치 시뮬레이터")

    project_root = find_project_root(Path(__file__))
    with st.sidebar:
        st.header("시뮬레이션 조건")
        project_root_input = st.text_input("Project root", value=str(project_root))
        plan_date = st.text_input("Plan date", value="2024-12-31")
        candidate_limit = st.slider("Candidate station limit", min_value=10, max_value=200, value=DEFAULT_CANDIDATE_LIMIT)
        route_limit = st.slider("Visible routes", min_value=10, max_value=200, value=DEFAULT_MAP_ROUTE_LIMIT)
        st.caption("운영 window `23:00~05:00`, 평가 window `07:00~10:00`, capacity `600 bikes/night`")
        run_clicked = st.button("Markov ontology simulation 실행", type="primary")

    resolved_root = Path(project_root_input)
    if "reallocation_payload" not in st.session_state or run_clicked:
        with st.spinner("Markov 전이와 ontology 추천 route를 계산하는 중..."):
            st.session_state["reallocation_payload"] = build_ontology_markov_simulation_payload(
                project_root=resolved_root,
                plan_date=plan_date,
                candidate_limit=candidate_limit,
            )

    payload = st.session_state["reallocation_payload"]
    manifest = payload["manifest"]
    metrics = payload["metrics"]
    routes = build_route_table(payload, limit=route_limit)

    st.subheader("Ontology Policy")
    st.write(
        "`NightReallocationOperationsOntology` 기반 `ontology-semantic-flow`로 "
        "`MarkovTransitionPolicy`, "
        "`MorningShortageRisk`, `ReallocationRoute`, `WorkforceCapacityConstraint`, "
        "`EvidenceEdge`를 연결해 야간 재배치 추천을 계산합니다."
    )

    cols = st.columns(5)
    cols[0].metric("추천 route", _metric_value(metrics, "route_count"))
    cols[1].metric("이동 대수", _metric_value(metrics, "total_recommended_bike_count"))
    cols[2].metric("부족 완화", _metric_value(metrics, "morning_shortage_reduction"))
    cols[3].metric("평균 거리 km", _metric_value(metrics, "avg_distance_km"))
    cols[4].metric("capacity 사용률", _metric_value(metrics, "capacity_utilization"))

    st.caption(
        f"plan_date `{manifest['plan_date']}` / shift `{manifest['shift_window']}` / "
        f"evaluation `{manifest['evaluation_window']}` / policy `{manifest['policy']}`"
    )

    tab_map, tab_routes, tab_markov, tab_ontology = st.tabs(["지도", "추천 route", "Markov 흐름", "Ontology 근거"])
    with tab_map:
        _render_map(st, routes)

    with tab_routes:
        route_frame = pd.DataFrame(routes)
        st.dataframe(route_frame, use_container_width=True, hide_index=True)

    with tab_markov:
        edge_frame = pd.DataFrame(payload.get("markov_edges", []))
        if edge_frame.empty:
            st.info("Markov transition edge가 없습니다.")
        else:
            st.dataframe(edge_frame.head(50), use_container_width=True, hide_index=True)

    with tab_ontology:
        st.dataframe(pd.DataFrame(build_concept_rows()), use_container_width=True, hide_index=True)
        st.markdown("#### Evidence / Confidence")
        if route_frame.empty:
            st.write("추천 route가 없습니다.")
        else:
            st.dataframe(
                route_frame[
                    [
                        "pickup_station",
                        "dropoff_station",
                        "recommended_bike_count",
                        "semantic_flow_score",
                        "evidence_gate",
                        "evidence_kind",
                        "confidence",
                        "source_refs",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )


if __name__ == "__main__":
    run_app()
