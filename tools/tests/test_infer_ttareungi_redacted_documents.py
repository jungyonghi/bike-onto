# Timestamp: 2026-05-18 11:05:50

from __future__ import annotations

import json
from pathlib import Path
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TOOLS_DIR.parents[0]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

import rag.infer_ttareungi_redacted_documents as infer  # noqa: E402


def _jsonl(path: Path) -> list[dict]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_manifest(path: Path) -> None:
    payload = {
        "timestamp": "2026-05-18 10:58:00",
        "documents": [
            {
                "nid": "private-ops",
                "title": "2024년 공공자전거 유지관리 계획",
                "생산일자": "2023-12-27",
                "department": "공공자전거운영처",
                "공개구분": "비공개",
                "download_status": "no_pdf_attachment",
                "downloaded_files": [],
            },
            {
                "nid": "private-sensitive",
                "title": "따릉이 개인정보 유출 대응 보고",
                "생산일자": "2026-04-28",
                "department": "기획조정실",
                "공개구분": "비공개",
                "download_status": "no_pdf_attachment",
                "downloaded_files": [],
            },
            {
                "nid": "public-evidence",
                "title": "2025년 공공자전거 유지관리 계획",
                "생산일자": "2024-12-31",
                "department": "공공자전거운영처",
                "공개구분": "부분공개",
                "download_status": "downloaded",
                "downloaded_files": [],
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_select_redacted_targets_excludes_sensitive_and_keeps_operations(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)

    documents = infer.load_manifest_documents(manifest_path)
    targets, excluded = infer.select_redacted_targets(documents)

    assert [target.nid for target in targets] == ["private-ops"]
    assert targets[0].target_category == "maintenance"
    assert excluded[0]["nid"] == "private-sensitive"
    assert excluded[0]["handling"] == "meta_only"


def test_inferred_restoration_never_uses_direct_for_private_document(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)
    documents = infer.load_manifest_documents(manifest_path)
    targets, _ = infer.select_redacted_targets(documents)
    service_overview = infer.build_service_overview_text()
    evidence_docs = infer.build_evidence_corpus(
        project_root=PROJECT_ROOT,
        manifest_documents=documents,
        service_overview=service_overview,
        max_pdf_chars=0,
    )

    restoration = infer.infer_restoration(targets[0], evidence_docs)

    assert restoration.target_nid == "private-ops"
    assert restoration.inferred_sections
    assert restoration.ontology_concepts
    assert restoration.not_reconstructed
    assert restoration.sensitivity_guard == "passed"
    assert all(link.evidence_kind != "direct" for link in restoration.evidence_links)
    assert all("문서번호" not in link.snippet_summary for link in restoration.evidence_links)
    assert all("결재일자" not in link.snippet_summary for link in restoration.evidence_links)
    assert all("보존기간" not in link.snippet_summary for link in restoration.evidence_links)


def test_build_evidence_corpus_handles_public_pdf_paths(tmp_path):
    project_root = tmp_path / "project"
    pdf_path = project_root / "data" / "raw" / "sample.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-1.4\n% minimal fixture\n")
    documents = [
        {
            "nid": "public-pdf",
            "title": "공공자전거 정비 공개 문서",
            "download_status": "downloaded",
            "downloaded_files": [str(pdf_path.relative_to(project_root))],
        }
    ]

    evidence = infer.build_evidence_corpus(
        project_root=project_root,
        manifest_documents=documents,
        service_overview=infer.build_service_overview_text(),
        max_pdf_chars=20,
    )

    assert any(item.source_type == "public_pdf" and item.source_id == "public-pdf" for item in evidence)


def test_run_inference_writes_report_and_contract_outputs(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path)

    run_dir = infer.run_inference(
        project_root=PROJECT_ROOT,
        manifest_path=manifest_path,
        output_root=tmp_path / "runs",
        timestamp="2026-05-18 10:58:00",
        max_pdf_chars=0,
        publish_project_report=False,
    )

    expected = {
        "candidate_documents.jsonl",
        "evidence_links.jsonl",
        "inferred_restorations.jsonl",
        "summary_report.md",
        "not_reconstructed.csv",
    }
    assert expected.issubset({path.name for path in run_dir.iterdir()})
    restorations = _jsonl(run_dir / "inferred_restorations.jsonl")
    report = (run_dir / "summary_report.md").read_text(encoding="utf-8")
    overview = PROJECT_ROOT / "docs" / "project" / "ttareungi_service_overview.md"

    assert restorations
    assert "원문 복원이 아니라 근거 기반 추정" in report
    assert "private-ops" in report
    assert "private-sensitive" in (run_dir / "not_reconstructed.csv").read_text(encoding="utf-8")
    assert overview.exists()
