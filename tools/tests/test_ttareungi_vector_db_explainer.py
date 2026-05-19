# Timestamp: 2026-04-22 19:11:44

from pathlib import Path
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.explain_ttareungi_vector_db import build_explanation_report  # noqa: E402


def test_vector_db_explainer_report_names_faiss_and_parquet_sources():
    project_root = Path(__file__).resolve().parents[2]

    report = build_explanation_report(project_root=project_root, sample_station_docs=3)

    assert "FAISS IndexFlatIP" in report
    assert "branch_data.parquet" in report
    assert "broken_data.parquet" in report
    assert "documents.jsonl" in report
    assert "index.faiss" in report
    assert "include_reference_docs=False" in report
