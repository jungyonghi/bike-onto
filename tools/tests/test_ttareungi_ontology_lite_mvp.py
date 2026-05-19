# Timestamp: 2026-05-11 00:00:00
# Timestamp: 2026-05-11 13:24:00

from pathlib import Path
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.ttareungi_ontology_lite import (  # noqa: E402
    build_ontology_lite_documents,
    collect_ontology_lite_facts,
    plan_semantic_query,
)
from rag.ttareungi_rag import (  # noqa: E402
    collect_fact_snippets,
    build_corpus_documents,
)


def _make_ontology_lite_project(tmp_path: Path) -> Path:
    import pandas as pd

    project_root = tmp_path / "project"
    processed_dir = project_root / "data" / "processed" / "parquet" / "bike_cloud"
    processed_dir.mkdir(parents=True, exist_ok=True)
    (project_root / ".obybk-root").write_text("", encoding="utf-8")

    pd.DataFrame(
        [
            {
                "date": "2026-04-01",
                "branchnum": 102,
                "branchname": "망원역 1번출구 앞",
                "location1": "마포구",
                "location2": "서울특별시 마포구 월드컵로 72",
                "branch_x": 37.555,
                "branch_y": 126.91,
                "sy": "QR",
            },
            {
                "date": "2026-04-01",
                "branchnum": 103,
                "branchname": "합정역 2번출구 앞",
                "location1": "마포구",
                "location2": "서울특별시 마포구 양화로 45",
                "branch_x": 37.549,
                "branch_y": 126.914,
                "sy": "QR",
            },
        ]
    ).to_parquet(processed_dir / "branch_data.parquet", index=False)
    pd.DataFrame(
        [
            {"date_rt": "2026-04-01", "branchnum": 102, "hour_cnt": 7, "cnt_rack": 24},
            {"date_rt": "2026-04-01", "branchnum": 102, "hour_cnt": 8, "cnt_rack": 11},
            {"date_rt": "2026-04-01", "branchnum": 103, "hour_cnt": 8, "cnt_rack": 18},
        ]
    ).to_parquet(processed_dir / "count_data.parquet", index=False)
    pd.DataFrame(
        [
            {"datetime": "2026-04-01 08:00:00", "temperature": 9.5, "precipitation": 4.0, "windspeed": 5.2},
            {"datetime": "2026-04-01 09:00:00", "temperature": 10.0, "precipitation": 0.0, "windspeed": 2.1},
        ]
    ).to_parquet(processed_dir / "weather_data.parquet", index=False)
    pd.DataFrame(
        [
            {
                "date_rt": "2026-04-01 08:00:00",
                "rentt": "2026-04-01 08:05:00",
                "bikenum": 5001,
                "branchnum_r": 102,
                "branchnum_b": 103,
                "hour_cnt": 8,
                "dist": 2300.0,
            },
            {
                "date_rt": "2026-04-01 18:00:00",
                "rentt": "2026-04-01 18:10:00",
                "bikenum": 5001,
                "branchnum_r": 103,
                "branchnum_b": 102,
                "hour_cnt": 18,
                "dist": 6100.0,
            },
        ]
    ).to_parquet(processed_dir / "rent_data.parquet", index=False)
    pd.DataFrame(
        [
            {"date_bk": "2026-04-01 19:00:00", "bikenum": 5001, "type_bk": "타이어"},
        ]
    ).to_parquet(processed_dir / "broken_data.parquet", index=False)
    return project_root


def test_plan_semantic_query_routes_mvp_intents():
    weather_plan = plan_semantic_query("비 오는 출근시간에 빨리 비어가는 대여소는?")
    role_plan = plan_semantic_query("출근시간 시작점이고 퇴근시간 반납 목적지가 되는 대여소는?")
    lifecycle_plan = plan_semantic_query("장거리 이동 직후 고장 난 자전거가 있나?")
    provenance_plan = plan_semantic_query("이 답변의 근거와 신뢰도 source를 알려줘")

    assert weather_plan.intent == "weather_demand_episode"
    assert weather_plan.required_sources == ["weather_data.parquet", "count_data.parquet", "branch_data.parquet"]
    assert role_plan.intent == "station_role_flow"
    assert "rent_data.parquet" in role_plan.required_sources
    assert lifecycle_plan.intent == "bike_fault_lifecycle"
    assert lifecycle_plan.required_sources == ["broken_data.parquet", "rent_data.parquet"]
    assert provenance_plan.intent == "provenance_confidence"
    assert provenance_plan.answerability == "weak-context"


def test_collect_ontology_lite_facts_returns_evidence_confidence_and_sources(tmp_path):
    project_root = _make_ontology_lite_project(tmp_path)

    weather_facts = collect_ontology_lite_facts(project_root, "비 오는 출근시간에 빨리 비어가는 대여소는?")
    role_facts = collect_ontology_lite_facts(project_root, "시작점과 반납 목적지 역할 구분 근거 알려줘")
    lifecycle_facts = collect_ontology_lite_facts(project_root, "장거리 이동 직후 고장 난 자전거가 있나?")
    provenance_facts = collect_ontology_lite_facts(project_root, "근거 신뢰도 source 설명해줘")

    assert any("intent=weather_demand_episode" in fact.text for fact in weather_facts)
    assert any("observed_under_weather" in fact.text for fact in weather_facts)
    assert any("evidence_kind=derived" in fact.text for fact in weather_facts)
    assert any("confidence=" in fact.text for fact in weather_facts)
    assert any("rental_station" in fact.text and "return_station" in fact.text for fact in role_facts)
    assert any("same_bike" in fact.text and "evidence_kind=inferred" in fact.text for fact in lifecycle_facts)
    assert any("answerability=weak-context" in fact.text for fact in provenance_facts)


def test_ontology_lite_facts_are_hybrid_only(tmp_path):
    project_root = _make_ontology_lite_project(tmp_path)
    question = "비 오는 출근시간에 빨리 비어가는 대여소와 근거 신뢰도 알려줘"

    hybrid_facts = collect_fact_snippets(project_root, question, profile="ontology-hybrid")
    db_only_facts = collect_fact_snippets(project_root, question, profile="db-only")

    assert any("Ontology-lite" in fact.title for fact in hybrid_facts)
    assert any("answerability=" in fact.text for fact in hybrid_facts)
    assert not any("Ontology-lite" in fact.title for fact in db_only_facts)


def test_build_ontology_lite_documents_and_hybrid_corpus_include_brief(tmp_path):
    project_root = _make_ontology_lite_project(tmp_path)
    bundle_path = project_root / "data" / "raw" / "_download_ontology_bundle_2026-04-27.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(
        '{"timestamp":"2026-04-27 15:17:14","summary":{},"structured_downloads":[],"document_downloads":[]}',
        encoding="utf-8",
    )

    docs = build_ontology_lite_documents(project_root, profile="ontology-hybrid")
    corpus_docs = build_corpus_documents(project_root, profile="ontology-hybrid", max_station_docs=2)

    assert any(doc.metadata.get("brief_type") == "ontology_lite_brief" for doc in docs)
    assert any("EvidenceEdge" in doc.text for doc in docs)
    assert any(doc.metadata.get("brief_type") == "ontology_lite_brief" for doc in corpus_docs)


def test_ontology_lite_large_query_guards_expose_actionable_evidence_metadata(tmp_path):
    project_root = tmp_path / "project"
    data_dir = project_root / "data" / "processed" / "parquet" / "bike_cloud"
    data_dir.mkdir(parents=True, exist_ok=True)
    (project_root / ".obybk-root").write_text("", encoding="utf-8")
    for filename in ["count_data.parquet", "rent_data.parquet"]:
        path = data_dir / filename
        with path.open("wb") as file:
            file.truncate(65 * 1024 * 1024)

    weather_facts = collect_ontology_lite_facts(project_root, "비 오는 출근시간에 빨리 비어가는 대여소는?", limit=1)
    role_facts = collect_ontology_lite_facts(project_root, "출근시간 시작점이고 퇴근시간 반납 종착점으로 바뀌는 대여소는?", limit=1)
    lifecycle_facts = collect_ontology_lite_facts(project_root, "장거리 이동 직후 24시간 내 고장 난 자전거는?", limit=1)

    assert any("weather_data.parquet" in fact.text and "count_data.parquet" in fact.text for fact in weather_facts)
    assert any("evidence_kind=weak-context" in fact.text and "confidence=0.35" in fact.text for fact in weather_facts)
    assert any("required_next_filter=" in fact.text for fact in weather_facts)
    assert any("branchnum_r:rental_station" in fact.text and "branchnum_b:return_station" in fact.text for fact in role_facts)
    assert any("rent_data.bikenum -> broken_data.bikenum" in fact.text for fact in lifecycle_facts)
