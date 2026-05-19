# Timestamp: 2026-05-11 11:24:00

from pathlib import Path
import json
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TOOLS_DIR.parents[0]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from generate_ttareungi_domain_ontology import (  # noqa: E402
    CORE_DOMAIN_CLASSES,
    V2_DOMAIN_CLASSES,
    build_domain_ontology_documents,
    build_ttareungi_domain_ontology,
    write_ttareungi_domain_ontology_run,
)
from rag.ttareungi_rag import build_corpus_documents  # noqa: E402


def _make_minimal_hybrid_project(tmp_path: Path) -> Path:
    import pandas as pd

    project_root = tmp_path / "project"
    data_dir = project_root / "data" / "processed" / "parquet" / "bike_cloud"
    data_dir.mkdir(parents=True)
    docs_dir = project_root / "docs" / "project"
    docs_dir.mkdir(parents=True)
    docs_dir.joinpath("obybk_ontology_necessity_performance_question_bank.md").write_text(
        (PROJECT_ROOT / "docs" / "project" / "obybk_ontology_necessity_performance_question_bank.md").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    raw_dir = project_root / "data" / "raw"
    raw_dir.mkdir(parents=True)
    raw_dir.joinpath("_download_ontology_bundle_2026-04-27.json").write_text(
        '{"timestamp":"2026-04-27 15:17:14","summary":{},"structured_downloads":[],"document_downloads":[]}',
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "date": "2026-04-01",
                "branchnum": 101,
                "branchname": "테스트 대여소",
                "location1": "마포구",
                "branch_x": 37.55,
                "branch_y": 126.91,
                "sy": "QR",
            }
        ]
    ).to_parquet(data_dir / "branch_data.parquet", index=False)
    pd.DataFrame([{"date_rt": "2026-04-01", "branchnum": 101, "hour_cnt": 8, "cnt_rack": 10}]).to_parquet(
        data_dir / "count_data.parquet", index=False
    )
    pd.DataFrame(
        [
            {
                "rentt": "2026-04-01 08:00:00",
                "bikenum": 5001,
                "branchnum_r": 101,
                "branchnum_b": 101,
                "dist": 1000.0,
            }
        ]
    ).to_parquet(data_dir / "rent_data.parquet", index=False)
    pd.DataFrame([{"date_bk": "2026-04-01 09:00:00", "bikenum": 5001, "type_bk": "타이어"}]).to_parquet(
        data_dir / "broken_data.parquet", index=False
    )
    pd.DataFrame([{"datetime": "2026-04-01 08:00:00", "temperature": 11.0, "precipitation": 0.0}]).to_parquet(
        data_dir / "weather_data.parquet", index=False
    )
    pd.DataFrame([{"date_ym": "2026-04", "branchnum": 101, "cnt_r": 1, "cnt_b": 1}]).to_parquet(
        data_dir / "uselate_data.parquet", index=False
    )
    pd.DataFrame([{"new_dt": "2026-04", "age": "20대", "gender": "F", "new": 1}]).to_parquet(
        data_dir / "newmeta.parquet", index=False
    )
    return project_root


def test_build_domain_ontology_covers_qo_and_keeps_qp_as_baseline():
    payload = build_ttareungi_domain_ontology(
        PROJECT_ROOT,
        timestamp="2026-05-11 11:24:00",
    )

    candidates = payload["domain_candidate_records"]
    alignments = payload["upper_alignment_edges"]
    coverage = payload["coverage"]

    assert coverage["qo_total"] == 50
    assert coverage["qo_mapped"] == 50
    assert coverage["qp_total"] == 50
    assert coverage["qp_baseline_only"] == 50
    assert coverage["qo_unmapped"] == []

    candidate_names = {candidate["canonical_name"] for candidate in candidates}
    assert set(CORE_DOMAIN_CLASSES).issubset(candidate_names)
    assert set(V2_DOMAIN_CLASSES).issubset(candidate_names)
    assert all(candidate["upper_parent"] for candidate in candidates)
    assert all(candidate["source_refs"] for candidate in candidates)
    assert all(candidate["evidence_kind"] in {"direct", "derived", "inferred", "weak-context"} for candidate in candidates)
    assert all(0.0 <= candidate["confidence"] <= 1.0 for candidate in candidates)
    assert not any(ref.startswith("CQ:QP") for candidate in candidates for ref in candidate["source_refs"])

    assert len(alignments) >= len(candidates)
    assert all(edge["relation"] == "has_upper_parent" for edge in alignments)
    assert all(edge["upper_concept"] and edge["domain_concept"] for edge in alignments)


def test_domain_ontology_acceptance_slices_are_present():
    payload = build_ttareungi_domain_ontology(
        PROJECT_ROOT,
        timestamp="2026-05-11 11:24:00",
    )
    candidates = {candidate["canonical_name"]: candidate for candidate in payload["domain_candidate_records"]}

    assert {"DemandEpisode", "StationRoleProfile", "BikeLifecyclePath", "ConfidenceAssessment"}.issubset(candidates)
    assert "QO01" in " ".join(candidates["DemandEpisode"]["cq_ids"])
    assert "QO11" in " ".join(candidates["StationRoleProfile"]["cq_ids"])
    assert "QO21" in " ".join(candidates["BikeLifecyclePath"]["cq_ids"])
    assert "QO44" in " ".join(candidates["ConfidenceAssessment"]["cq_ids"])
    assert candidates["DemandEpisode"]["evidence_kind"] == "derived"
    assert candidates["BikeLifecyclePath"]["evidence_kind"] == "inferred"
    assert candidates["ConfidenceAssessment"]["evidence_kind"] == "weak-context"


def test_night_reallocation_operations_slice_is_promoted_and_aligned():
    payload = build_ttareungi_domain_ontology(
        PROJECT_ROOT,
        timestamp="2026-05-11 11:24:00",
    )
    candidates = {candidate["canonical_name"]: candidate for candidate in payload["domain_candidate_records"]}
    alignments = {edge["domain_concept"]: edge for edge in payload["upper_alignment_edges"]}

    expected = {
        "NightReallocationShift",
        "DispatchAgent",
        "ReallocationAction",
        "ReallocationRoute",
        "MarkovTransitionPolicy",
        "MorningShortageRisk",
        "ReallocationRecommendation",
        "WorkforceCapacityConstraint",
    }
    assert expected.issubset(candidates)
    assert expected.issubset(set(payload["v2_domain_classes"]))
    assert payload["ontology_name"] == "NightReallocationOperationsOntology"
    assert payload["parent_ontology"] == "Ttareungi Domain Ontology-lite v2.1"
    assert payload["formalization_level"] == "ontology-lite"
    assert "assigned_to_agent" in payload["relations"]
    assert "mitigates_shortage" in payload["relations"]

    for name in expected:
        candidate = candidates[name]
        assert candidate["upper_parent"]
        assert candidate["source_refs"]
        assert candidate["physical_sources"]
        assert candidate["evidence_kind"] in {"direct", "derived", "inferred", "weak-context"}
        assert 0.0 <= candidate["confidence"] <= 1.0
        assert alignments[name]["relation"] == "has_upper_parent"

    assert candidates["DispatchAgent"]["upper_parent"] == "Agent Role"
    assert candidates["WorkforceCapacityConstraint"]["upper_parent"] == "Operational Constraint"
    assert candidates["DispatchAgent"]["evidence_kind"] == "weak-context"
    assert candidates["WorkforceCapacityConstraint"]["evidence_kind"] == "weak-context"
    assert {"rent_data.parquet", "count_data.parquet"}.issubset(
        set(candidates["MarkovTransitionPolicy"]["physical_sources"])
    )


def test_write_domain_ontology_run_persists_required_outputs(tmp_path):
    run_dir = write_ttareungi_domain_ontology_run(
        PROJECT_ROOT,
        output_dir=tmp_path,
        timestamp="2026-05-11 11:24:00",
    )

    expected_files = {
        "domain_candidate_records.json",
        "domain_promotion_records.json",
        "upper_alignment_edges.json",
        "ttareungi_domain_ontology_lite.json",
        "coverage_report.md",
        "human_review.csv",
    }
    assert expected_files.issubset({path.name for path in run_dir.iterdir()})

    registry = json.loads((run_dir / "ttareungi_domain_ontology_lite.json").read_text(encoding="utf-8"))
    report = (run_dir / "coverage_report.md").read_text(encoding="utf-8")
    csv_text = (run_dir / "human_review.csv").read_text(encoding="utf-8")

    assert registry["timestamp"] == "2026-05-11 11:24:00"
    assert registry["ontology_name"] == "NightReallocationOperationsOntology"
    assert registry["coverage"]["qo_mapped"] == 50
    assert "# Timestamp: 2026-05-11 11:24:00" in report
    assert "night reallocation operations" in report
    assert csv_text.startswith("# Timestamp: 2026-05-11 11:24:00")


def test_domain_ontology_documents_are_hybrid_only(tmp_path):
    run_dir = write_ttareungi_domain_ontology_run(
        PROJECT_ROOT,
        output_dir=tmp_path,
        timestamp="2026-05-11 11:24:00",
    )
    project_root = tmp_path / "project"
    target = project_root / "data" / "processed" / "exports" / "ttareungi_domain_ontology_runs" / run_dir.name
    target.parent.mkdir(parents=True)
    target.symlink_to(run_dir, target_is_directory=True)

    docs = build_domain_ontology_documents(project_root, profile="ontology-hybrid")
    db_only_docs = build_domain_ontology_documents(project_root, profile="db-only")

    assert any(doc.metadata.get("brief_type") == "domain_ontology_lite_brief" for doc in docs)
    assert any("DemandEpisode" in doc.text and "upper_parent" in doc.text for doc in docs)
    assert any("NightReallocationOperationsOntology" in doc.text for doc in docs)
    assert any("야간 재배치" in doc.text and "200명 인력" in doc.text for doc in docs)
    assert db_only_docs == []


def test_hybrid_corpus_includes_domain_ontology_brief_after_run_exists(tmp_path):
    project_root = _make_minimal_hybrid_project(tmp_path)
    docs = build_corpus_documents(project_root, profile="ontology-hybrid", max_station_docs=1)

    assert any(doc.metadata.get("brief_type") == "domain_ontology_lite_brief" for doc in docs)
    assert any("NightReallocationOperationsOntology" in doc.text for doc in docs)
