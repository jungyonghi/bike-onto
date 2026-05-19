# Timestamp: 2026-05-11 17:04:42

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "ttareungi_ontology_reallocation_yearly_kpi_comparison.ipynb"


def _notebook_text() -> str:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook.get("cells", [])
    )


def test_yearly_reallocation_notebook_exists_with_timestamp() -> None:
    assert NOTEBOOK_PATH.exists()
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    first_cell = "".join(notebook["cells"][0]["source"])
    assert first_cell.startswith("# Timestamp:")


def test_yearly_reallocation_notebook_compares_native_and_ontology_kpis() -> None:
    text = _notebook_text()
    assert "POLICY_NATIVE" in text
    assert "POLICY_SEMANTIC_FLOW" in text
    assert "run_yearly_kpi_comparison" in text
    assert "yearly_summary" in text
    assert "morning_shortage_reduction_delta" in text
    assert "semantic_flow_uplift" in text


def test_yearly_reallocation_notebook_documents_one_year_sampling_controls() -> None:
    text = _notebook_text()
    assert "analysis_year" in text
    assert "max_days" in text
    assert "candidate_limit" in text
    assert "23:00~05:00" in text
    assert "07:00~10:00" in text
