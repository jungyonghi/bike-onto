# Timestamp: 2026-05-11 13:43:00

from pathlib import Path
import json
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.ttareungi_rag import (  # noqa: E402
    HashingEmbedder,
    RagDocument,
    build_corpus_documents,
    build_faiss_index,
    search_faiss_index,
)
from rag.run_db_only_rag_benchmark import (  # noqa: E402
    build_latest_feature_experiment_spec,
    write_benchmark_outputs,
)


def _make_db_only_source_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / ".obybk-root").write_text("", encoding="utf-8")

    processed_dir = project_root / "data" / "processed" / "parquet" / "bike_cloud"
    processed_dir.mkdir(parents=True)
    for filename in ["branch_data.parquet", "newmeta.parquet"]:
        (processed_dir / filename).write_bytes(b"PAR1")

    docs_root = project_root / "data" / "raw" / "docs" / "ttareungi"
    pricing_dir = docs_root / "service" / "pricing_info"
    pricing_dir.mkdir(parents=True)
    (pricing_dir / "source.html").write_text(
        "<html><body><h1>이용요금 안내</h1><p>1시간권 정기권 결제 안내</p></body></html>",
        encoding="utf-8",
    )
    procurement_dir = docs_root / "procurement" / "g2b_r26bk01319050_file1"
    procurement_dir.mkdir(parents=True)
    (procurement_dir / "source.html").write_text(
        "<html><body><h1>2026년 공공자전거 정비용역</h1><p>조달 입찰 공고</p></body></html>",
        encoding="utf-8",
    )

    bundle_path = project_root / "data" / "raw" / "_download_ontology_bundle_2026-04-27.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-04-27 15:17:14",
                "structured_downloads": [],
                "document_downloads": [
                    {
                        "category": "service",
                        "key": "pricing_info",
                        "title": "따릉이 이용요금 안내",
                        "url": "https://www.bikeseoul.com/info/infoCoupon.do",
                        "storage_dir": "data/raw/docs/ttareungi/service/pricing_info",
                        "saved_files": [{"path": "data/raw/docs/ttareungi/service/pricing_info/source.html"}],
                        "notes": [],
                    },
                    {
                        "category": "procurement",
                        "key": "g2b_r26bk01319050_file1",
                        "title": "2026년 공공자전거 정비용역",
                        "url": "https://www.g2b.go.kr/example",
                        "storage_dir": "data/raw/docs/ttareungi/procurement/g2b_r26bk01319050_file1",
                        "saved_files": [
                            {"path": "data/raw/docs/ttareungi/procurement/g2b_r26bk01319050_file1/source.html"}
                        ],
                        "notes": [],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project_root


def test_db_only_corpus_includes_source_briefs_but_not_generated_ontology_layers(tmp_path):
    project_root = _make_db_only_source_project(tmp_path)

    documents = build_corpus_documents(project_root, profile="db-only", max_station_docs=5)

    assert any(doc.metadata.get("doc_key") == "pricing_info" for doc in documents)
    assert any(doc.metadata.get("doc_key") == "g2b_r26bk01319050_file1" for doc in documents)
    assert not any(doc.metadata.get("brief_type") == "ontology_lite_brief" for doc in documents)
    assert not any(str(doc.metadata.get("source_kind", "")).startswith("domain_ontology") for doc in documents)


def test_db_only_source_routing_aliases_prioritize_known_weak_sources(tmp_path):
    documents = [
        RagDocument(
            doc_id="generic:signup",
            text="가입자 안내 문서. 연령 성별 정보가 일부 언급됩니다.",
            metadata={"source": "generic_signup_note"},
        ),
        RagDocument(
            doc_id="dataset:newmeta",
            text="Parquet catalog. dataset newmeta.parquet. columns new_dt age gender new.",
            metadata={
                "source": "data/processed/parquet/bike_cloud/newmeta.parquet",
                "dataset_name": "newmeta.parquet",
                "granularity": "signup_monthly",
                "category": "dataset_inventory",
            },
        ),
        RagDocument(
            doc_id="generic:pricing",
            text="따릉이 이용요금 정기권 결제 안내가 있는 일반 문서.",
            metadata={"source": "generic_pricing_note"},
        ),
        RagDocument(
            doc_id="ops-doc:service:1",
            text="service artifact.",
            metadata={"source": "https://www.bikeseoul.com/info/infoCoupon.do", "doc_key": "pricing_info"},
        ),
        RagDocument(
            doc_id="generic:procurement",
            text="공공자전거 정비용역 조달 입찰 안내가 있는 일반 문서.",
            metadata={"source": "generic_procurement_note"},
        ),
        RagDocument(
            doc_id="ops-doc:procurement:1",
            text="procurement artifact.",
            metadata={"source": "https://www.g2b.go.kr/example", "doc_key": "g2b_r26bk01319050_file1"},
        ),
    ]
    index_dir = tmp_path / "index"
    embedder = HashingEmbedder(dim=128)
    build_faiss_index(documents, index_dir, embedder)

    signup = search_faiss_index("신규가입자의 연령과 성별 정보는 어디에 있어?", index_dir, embedder, top_k=1)
    pricing = search_faiss_index("따릉이 이용요금은 어떤 문서 근거로 답해야 해?", index_dir, embedder, top_k=1)
    procurement = search_faiss_index("2026년 공공자전거 정비용역 정보는 어디에 있어?", index_dir, embedder, top_k=1)

    assert signup[0].document.doc_id == "dataset:newmeta"
    assert pricing[0].document.metadata["doc_key"] == "pricing_info"
    assert procurement[0].document.metadata["doc_key"] == "g2b_r26bk01319050_file1"


def test_search_applies_source_diversity_after_reranking(tmp_path):
    documents = [
        RagDocument(
            doc_id=f"count:{index}",
            text="count_data 이용량 대여 반납 추세 " * 4,
            metadata={"source": "data/processed/parquet/bike_cloud/count_data.parquet"},
        )
        for index in range(5)
    ]
    documents.append(
        RagDocument(
            doc_id="pricing",
            text="따릉이 이용요금 정기권 1시간권 결제 안내",
            metadata={"source": "https://www.bikeseoul.com/info/infoCoupon.do", "doc_key": "pricing_info"},
        )
    )
    index_dir = tmp_path / "index"
    embedder = HashingEmbedder(dim=128)
    build_faiss_index(documents, index_dir, embedder)

    results = search_faiss_index("count_data 이용량 대여 반납 요금", index_dir, embedder, top_k=5)
    sources = [result.document.metadata.get("source") for result in results]

    assert sources.count("data/processed/parquet/bike_cloud/count_data.parquet") <= 2
    assert "https://www.bikeseoul.com/info/infoCoupon.do" in sources


def test_db_only_benchmark_outputs_metrics_and_latest_feature_spec(tmp_path):
    eval_path = tmp_path / "rag100.jsonl"
    rows = [
        {
            "id": "q1",
            "question": "신규가입자의 연령과 성별 정보는 어디에 있어?",
            "question_type": "signup",
            "expected_sources": ["newmeta.parquet"],
            "retrieved_sources": ["newmeta.parquet"],
            "latency_ms": 12,
            "status": "ok",
        },
        {
            "id": "q2",
            "question": "2026년 공공자전거 정비용역 정보는 어디에 있어?",
            "question_type": "procurement_doc",
            "expected_sources": ["g2b_r26bk01319050_file1"],
            "retrieved_sources": ["pricing_info"],
            "latency_ms": 14,
            "status": "ok",
        },
    ]
    eval_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")

    output_dir = tmp_path / "run"
    outputs = write_benchmark_outputs(eval_path=eval_path, output_dir=output_dir, timestamp="2026-05-11 13:43:00")
    metrics = json.loads(outputs["metrics"].read_text(encoding="utf-8"))
    report = outputs["report"].read_text(encoding="utf-8")
    feature_spec = build_latest_feature_experiment_spec()

    assert metrics["profile"] == "db-only"
    assert metrics["row_count"] == 2
    assert metrics["source_hit_count"] == 1
    assert metrics["source_hit_rate"] == 0.5
    assert metrics["is_performance_success"] is False
    assert "procurement_doc" in metrics["weak_question_types"]
    assert "Structured Outputs" in report
    assert {"structured_outputs", "graders", "prompt_caching", "file_search"} <= set(feature_spec)


def test_db_only_benchmark_does_not_count_stale_actual_answer_as_current_hit(tmp_path):
    eval_path = tmp_path / "rag100.jsonl"
    eval_path.write_text(
        json.dumps(
            {
                "id": "q1",
                "question": "신규가입자의 연령과 성별 정보는 어디에 있어?",
                "question_type": "signup",
                "expected_sources": ["newmeta.parquet"],
                "retrieved_sources": ["pricing_info"],
                "actual_answer": "과거 run 답변에는 newmeta.parquet가 포함되어 있었다.",
                "status": "ok",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    outputs = write_benchmark_outputs(
        eval_path=eval_path,
        output_dir=tmp_path / "run",
        timestamp="2026-05-11 14:18:00",
    )
    metrics = json.loads(outputs["metrics"].read_text(encoding="utf-8"))

    assert metrics["source_hit_count"] == 0
    assert metrics["source_hit_rate"] == 0.0


def test_db_only_benchmark_uses_exact_source_match_for_branch_data(tmp_path):
    eval_path = tmp_path / "rag100.jsonl"
    eval_path.write_text(
        json.dumps(
            {
                "id": "q1",
                "question": "대여소 위치 source는?",
                "question_type": "dataset_identification",
                "expected_sources": ["branch_data.parquet"],
                "retrieved_sources": ["master_branch_data.parquet"],
                "status": "ok",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    outputs = write_benchmark_outputs(
        eval_path=eval_path,
        output_dir=tmp_path / "run",
        timestamp="2026-05-11 14:20:00",
    )
    metrics = json.loads(outputs["metrics"].read_text(encoding="utf-8"))

    assert metrics["source_hit_count"] == 0
