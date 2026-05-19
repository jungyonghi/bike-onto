# Timestamp: 2026-04-22 19:11:44
# Timestamp: 2026-04-27 17:46:00

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


TOOLS_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_SCRIPTS_DIR))

from rag.ttareungi_rag import (  # noqa: E402
    DEFAULT_RAG_PROFILE,
    DATASET_FILENAMES,
    build_parquet_catalog_documents,
    build_station_profile_documents,
    default_index_dir,
    find_project_root,
)


def build_explanation_report(project_root: Path, sample_station_docs: int = 5) -> str:
    index_dir = default_index_dir(project_root, profile=DEFAULT_RAG_PROFILE)
    documents = build_station_profile_documents(
        project_root=project_root,
        max_station_docs=sample_station_docs,
        profile=DEFAULT_RAG_PROFILE,
    )
    documents.extend(build_parquet_catalog_documents(project_root=project_root, profile=DEFAULT_RAG_PROFILE))
    sample_lines = [
        f"- `{document.doc_id}` from `{document.metadata.get('source', 'unknown')}`: "
        f"{document.text[:180]}"
        for document in documents[: min(len(documents), sample_station_docs + len(DATASET_FILENAMES))]
    ]

    return "\n".join(
        [
            "# Timestamp: 2026-04-22 19:11:44",
            "# 따릉이 RAG 벡터 DB 적재 설명 리포트",
            "",
            "## 핵심 요약",
            "- 벡터 DB 구현체는 로컬 `FAISS IndexFlatIP`입니다.",
            "- 벡터화 대상은 `RagDocument.text`입니다.",
            "- 현재 기본 범위는 `include_reference_docs=False`라서 Markdown/Mermaid 문서는 제외합니다.",
            "- 기본 프로필은 `ontology-hybrid`이며 운영 Parquet catalog/aggregate + 공식 원천 브리프 + 운영/공시 문서 브리프를 함께 색인합니다.",
            "- `db-only` 프로필은 운영 Parquet 기반 대여소 프로필, 데이터셋 인벤토리, 집계 브리프를 유지합니다.",
            "",
            "## 적재 대상 Parquet",
            *[f"- `{filename}`" for filename in DATASET_FILENAMES],
            "",
            "## 저장 산출물",
            f"- `{index_dir / 'index.faiss'}`: FAISS 벡터 인덱스",
            f"- `{index_dir / 'documents.jsonl'}`: 벡터 row와 매칭되는 원문 문서",
            f"- `{index_dir / 'manifest.json'}`: 인덱스 문서 수, 임베딩 차원, backend 메타정보",
            "",
            "## 코드상 적재 흐름",
            "```text",
            "build_corpus_documents(profile='ontology-hybrid')",
            "→ build_station_profile_documents()",
            "→ build_dataset_inventory_documents()",
            "→ build_pandas_aggregate_documents()",
            "→ build_official_ontology_documents()",
            "→ build_operations_document_documents()",
            "→ create_embedder(backend='auto').encode(doc.text)",
            "→ faiss.IndexFlatIP(embedding_dim)",
            "→ index.add(embeddings)",
            "→ faiss.write_index(index, index.faiss)",
            "```",
            "",
            "## 샘플 RagDocument",
            *sample_lines,
            "",
            "## 실행 명령",
            "```bash",
            ".venv/bin/python 01_Projects/01_Active/obybk/tools/scripts/rag/ttareungi_rag.py build-index",
            "```",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explain how Ttareung-i RAG documents are loaded into FAISS")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--sample-station-docs", type=int, default=5)
    args = parser.parse_args(argv)

    project_root = args.project_root or find_project_root(Path(__file__))
    print(build_explanation_report(project_root=project_root, sample_station_docs=args.sample_station_docs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
