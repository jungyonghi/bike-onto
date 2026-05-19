# Timestamp: 2026-05-11 10:57:52

from pathlib import Path
import json
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from generate_codex_upper_ontology_seed import (  # noqa: E402
    GENERAL_CATEGORIES,
    TARGET_COUNT,
    build_upper_ontology_seed,
    write_upper_ontology_run,
)


def test_build_upper_ontology_seed_returns_1000_balanced_records():
    payload = build_upper_ontology_seed(timestamp="2026-05-11 10:57:52")
    candidates = payload["candidate_records"]
    promotions = payload["promotion_records"]
    summary = payload["run_summary"]

    assert len(candidates) == TARGET_COUNT == 1000
    assert len(promotions) == TARGET_COUNT
    assert set(summary["general_category_balance"]) == set(GENERAL_CATEGORIES)
    assert sum(summary["general_category_balance"].values()) == TARGET_COUNT
    assert min(summary["general_category_balance"].values()) >= 83
    assert max(summary["general_category_balance"].values()) <= 84

    canonical_names = [item["canonical_candidate"] for item in candidates]
    assert len(canonical_names) == len(set(canonical_names))
    assert all(item["is_domain_specific"] is False for item in candidates)
    assert all(item["promotion_decision"] in {"core_upper", "general_reference"} for item in candidates)
    assert all("general_category=" in item["notes"] for item in candidates)
    assert all("# Timestamp: 2026-05-11 10:57:52" in item["notes"] for item in candidates)
    assert all("# Timestamp: 2026-05-11 10:57:52" in item["rationale"] for item in promotions)


def test_write_upper_ontology_run_persists_timestamped_outputs(tmp_path):
    run_dir = write_upper_ontology_run(
        output_dir=tmp_path,
        timestamp="2026-05-11 10:57:52",
    )

    final_result = json.loads((run_dir / "final_result.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    csv_text = (run_dir / "codex_upper_ontology_1000.csv").read_text(encoding="utf-8")
    readme_text = (run_dir / "README.md").read_text(encoding="utf-8")

    assert final_result["timestamp"] == "2026-05-11 10:57:52"
    assert final_result["generation_source"] == "codex_agent"
    assert len(final_result["candidate_records"]) == 1000
    assert summary["observed_ratio"]["general_reference_plus_core_upper"] == 1.0
    assert csv_text.startswith("# Timestamp: 2026-05-11 10:57:52")
    assert "# Timestamp: 2026-05-11 10:57:52" in readme_text
