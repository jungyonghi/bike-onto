# Timestamp: 2026-04-21 23:21:00
# Timestamp: 2026-04-21 23:44:00
# Timestamp: 2026-04-21 23:55:00
# Timestamp: 2026-04-21 23:47:20
# Timestamp: 2026-04-21 23:51:43
# Timestamp: 2026-04-21 23:56:00
# Timestamp: 2026-04-27 17:46:00
# Timestamp: 2026-04-27 18:40:00
# Timestamp: 2026-04-27 19:00:00
# Timestamp: 2026-04-27 19:10:00
# Timestamp: 2026-05-11 12:09:05
# Timestamp: 2026-05-11 12:56:21

from pathlib import Path
import json
import sys
import zipfile


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

import rag.ttareungi_rag as rag_module  # noqa: E402
from rag.ttareungi_rag import (  # noqa: E402
    FactSnippet,
    HashingEmbedder,
    DEFAULT_LLM_URL,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_QWEN_MODEL,
    LLM_PROVIDER_OPENAI,
    RagDocument,
    SearchResult,
    SentenceTransformerEmbedder,
    _is_complete_sentence_transformer_path,
    answer_question,
    build_corpus_documents,
    build_prompt,
    build_faiss_index,
    build_pandas_aggregate_documents,
    build_parquet_catalog_documents,
    build_parquet_dataset_profiles,
    build_rag_index,
    build_rag_eval_questions,
    build_project_documents,
    create_embedder_for_index,
    collect_pandas_fact_snippets,
    call_qwen_chat,
    default_index_dir,
    inspect_data,
    load_llm_api_key_file,
    resolve_llm_runtime_settings,
    search_faiss_index,
)


def test_default_sentence_transformer_model_candidates_prefer_complete_qwen(monkeypatch, tmp_path):
    qwen_model = tmp_path / "Qwen3-Embedding-0.6B"
    qwen_model.mkdir()
    (qwen_model / "modules.json").write_text("[]", encoding="utf-8")
    (qwen_model / "config_sentence_transformers.json").write_text("{}", encoding="utf-8")
    (qwen_model / "model.safetensors").write_text("stub", encoding="utf-8")
    kanana_model = tmp_path / "kanana-nano-2.1b-embedding"
    kanana_model.mkdir()
    (kanana_model / "modules.json").write_text("[]", encoding="utf-8")
    (kanana_model / "config_sentence_transformers.json").write_text("{}", encoding="utf-8")
    (kanana_model / "model.safetensors").write_text("stub", encoding="utf-8")

    monkeypatch.setattr(rag_module, "DEFAULT_QWEN3_EMBEDDING_LOCAL_PATH", qwen_model)
    monkeypatch.setattr(rag_module, "LEGACY_KANANA_EMBEDDING_MODEL_PATH", kanana_model)
    monkeypatch.setattr(rag_module, "DEFAULT_SENTENCE_TRANSFORMER_CACHE_CANDIDATES", ())
    monkeypatch.delenv(rag_module.DEFAULT_SENTENCE_TRANSFORMER_MODEL_ENV, raising=False)

    candidates = rag_module._default_sentence_transformer_model_candidates()

    assert candidates[0] == qwen_model
    assert rag_module.DEFAULT_LIGHTWEIGHT_SENTENCE_TRANSFORMER_MODEL_ID in candidates
    assert kanana_model not in candidates


def test_sentence_transformer_embedder_uses_small_indexing_batch():
    class FakeModel:
        def encode(self, texts, **kwargs):
            assert kwargs["batch_size"] == 1
            assert kwargs["normalize_embeddings"] is True
            return [[1.0, 0.0] for _ in texts]

    embedder = SentenceTransformerEmbedder.__new__(SentenceTransformerEmbedder)
    embedder.model = FakeModel()

    embeddings = embedder.encode(["고장 데이터", "날씨 데이터"])

    assert embeddings.shape == (2, 2)


def test_sentence_transformer_path_requires_model_weights(tmp_path):
    incomplete_model = tmp_path / "incomplete-model"
    incomplete_model.mkdir()
    (incomplete_model / "modules.json").write_text("[]", encoding="utf-8")
    (incomplete_model / "config_sentence_transformers.json").write_text("{}", encoding="utf-8")

    assert not _is_complete_sentence_transformer_path(incomplete_model)

    (incomplete_model / "model.safetensors").write_text("stub", encoding="utf-8")

    assert _is_complete_sentence_transformer_path(incomplete_model)


def test_faiss_manifest_records_sentence_transformer_model_path(tmp_path):
    class FakeSentenceTransformerEmbedder:
        name = "sentence-transformers"
        model_path = "fake-model"
        device = "cpu"

        def encode(self, texts):
            return [[1.0, 0.0] for _ in texts]

    documents = [RagDocument(doc_id="doc:1", text="따릉이 고장 데이터", metadata={})]
    index_dir = tmp_path / "rag_index"

    build_faiss_index(documents, index_dir, FakeSentenceTransformerEmbedder())

    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["embedding_model"] == "fake-model"
    assert manifest["embedding_device"] == "cpu"


def test_create_embedder_for_index_uses_manifest_model(monkeypatch, tmp_path):
    index_dir = tmp_path / "rag_index"
    index_dir.mkdir()
    (index_dir / "documents.jsonl").write_text("", encoding="utf-8")
    (index_dir / "manifest.json").write_text(
        json.dumps(
            {
                "embedding_backend": "sentence-transformers",
                "embedding_model": "manifest-model",
                "index_file": "index.faiss",
                "documents_file": "documents.jsonl",
            }
        ),
        encoding="utf-8",
    )
    calls = []

    class FakeEmbedder:
        name = "sentence-transformers"

        def __init__(self, model_path):
            calls.append(model_path)

    monkeypatch.setattr(rag_module, "SentenceTransformerEmbedder", FakeEmbedder)

    embedder = create_embedder_for_index(index_dir, backend="auto")

    assert isinstance(embedder, FakeEmbedder)
    assert calls == ["manifest-model"]


def test_faiss_index_returns_relevant_ttareungi_station_doc(tmp_path):
    documents = [
        RagDocument(
            doc_id="station:102",
            text="대여소 102 망원역 1번출구 앞. 자치구 마포구. 주소 마포구 월드컵로 72.",
            metadata={"source": "branch_data", "station_id": "102", "district": "마포구"},
        ),
        RagDocument(
            doc_id="station:540",
            text="대여소 540 군자역 7번출구 베스트샵 앞. 자치구 광진구.",
            metadata={"source": "branch_data", "station_id": "540", "district": "광진구"},
        ),
        RagDocument(
            doc_id="guide:fault",
            text="고장 급증은 최근 7일 기준선과 비교해 점검 우선순위를 산정한다.",
            metadata={"source": "ops_guide"},
        ),
    ]

    index_dir = tmp_path / "rag_index"
    embedder = HashingEmbedder(dim=128)

    build_faiss_index(documents, index_dir, embedder)
    results = search_faiss_index("망원역 대여소 위치와 자치구 알려줘", index_dir, embedder, top_k=2)

    assert results[0].document.doc_id == "station:102"
    assert results[0].score > 0


def test_prompt_preserves_facts_sources_and_grounding_rules():
    document = RagDocument(
        doc_id="doc:aiplan:1",
        text="GraphRAG는 구조화 데이터와 GeneratedBrief를 함께 검색한다.",
        metadata={"source": "docs/project/aiplan.md"},
    )
    result = SearchResult(document=document, score=0.88, rank=1)
    fact = FactSnippet(
        title="데이터셋 branch_data.parquet",
        text="행 수 65,648건, 컬럼 branchnum, branchname, location1",
        source="data/processed/parquet/bike_cloud/branch_data.parquet",
    )

    prompt = build_prompt("따릉이 데이터셋으로 무엇을 답할 수 있어?", [result], [fact])

    assert "branch_data.parquet" in prompt
    assert "docs/project/aiplan.md" in prompt
    assert "근거 없는 숫자나 원인을 만들지 않는다" in prompt


def test_load_llm_api_key_file_keeps_blank_openai_key_template(tmp_path):
    key_file = tmp_path / "config" / "openai_api_key.local"
    key_file.parent.mkdir()
    key_file.write_text(
        "\n".join(
            [
                "# Timestamp: 2026-05-11 12:12:00",
                "OPENAI_API_KEY=",
                "OPENAI_BASE_URL=https://api.openai.com/v1",
                "OPENAI_MODEL=gpt-5.2",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_llm_api_key_file(tmp_path)

    assert settings["OPENAI_API_KEY"] == ""
    assert settings["OPENAI_BASE_URL"] == DEFAULT_OPENAI_BASE_URL
    assert settings["OPENAI_MODEL"] == DEFAULT_OPENAI_MODEL


def test_default_openai_model_is_gpt_5_2_for_mvp():
    assert DEFAULT_OPENAI_MODEL == "gpt-5.2"


def test_resolve_openai_runtime_settings_uses_key_file_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    key_file = tmp_path / "config" / "openai_api_key.local"
    key_file.parent.mkdir()
    key_file.write_text(
        "\n".join(
            [
                "# Timestamp: 2026-05-11 12:12:00",
                "OPENAI_API_KEY=sk-test",
                "OPENAI_BASE_URL=https://api.openai.com/v1",
                "OPENAI_MODEL=gpt-5.2",
            ]
        ),
        encoding="utf-8",
    )

    settings = resolve_llm_runtime_settings(
        project_root=tmp_path,
        provider=LLM_PROVIDER_OPENAI,
        llm_url=DEFAULT_LLM_URL,
        model=DEFAULT_QWEN_MODEL,
    )

    assert settings.llm_url == DEFAULT_OPENAI_BASE_URL
    assert settings.model == DEFAULT_OPENAI_MODEL
    assert settings.api_key == "sk-test"


def test_call_qwen_chat_sends_authorization_header_for_openai(monkeypatch):
    import requests

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    answer = call_qwen_chat(
        prompt="테스트",
        llm_url=DEFAULT_OPENAI_BASE_URL,
        model=DEFAULT_OPENAI_MODEL,
        api_key="sk-test",
    )

    assert answer == "ok"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == DEFAULT_OPENAI_MODEL
    assert "max_completion_tokens" in captured["json"]
    assert "max_tokens" not in captured["json"]
    assert "temperature" not in captured["json"]


def test_inspect_data_reports_project_dataset_inventory():
    project_root = Path(__file__).resolve().parents[2]

    report = inspect_data(project_root)

    assert "# Timestamp:" in report
    assert "branch_data.parquet" in report
    assert "weather_data.parquet" in report


def test_project_documents_are_db_only_by_default():
    project_root = Path(__file__).resolve().parents[2]

    documents = build_project_documents(project_root, max_station_docs=5)
    sources = [str(document.metadata.get("source", "")) for document in documents]

    assert documents
    assert any(source.endswith(".parquet") for source in sources)
    assert not any(source.endswith(".md") or source.endswith(".mmd") for source in sources)


def test_no_llm_output_hides_internal_answer_rules(tmp_path):
    documents = [
        RagDocument(
            doc_id="dataset:1",
            text="데이터셋 branch_data.parquet 행 수 65,648건 컬럼 branchnum branchname location1",
            metadata={"source": "data/processed/parquet/bike_cloud/branch_data.parquet"},
        )
    ]
    index_dir = tmp_path / "rag_index"
    embedder = HashingEmbedder(dim=128)
    build_faiss_index(documents, index_dir, embedder)

    output = answer_question(
        question="따릉이 데이터셋 근거 보여줘",
        project_root=Path(__file__).resolve().parents[2],
        index_dir=index_dir,
        embedder=embedder,
        use_llm=False,
    )

    assert "답변 규칙" not in output
    assert "근거 없는 숫자" not in output
    assert "RAG 검색 근거" in output


def test_capability_question_returns_stable_guidance_without_random_station(tmp_path):
    documents = [
        RagDocument(
            doc_id="station:553",
            text="따릉이 대여소 프로필. 대여소 번호 553. 대여소명 중곡 성원아파트 앞.",
            metadata={"source": "branch_data.parquet"},
        )
    ]
    index_dir = tmp_path / "rag_index"
    embedder = HashingEmbedder(dim=128)
    build_faiss_index(documents, index_dir, embedder)

    output = answer_question(
        question="뭘 할 수 있지?",
        project_root=Path(__file__).resolve().parents[2],
        index_dir=index_dir,
        embedder=embedder,
        use_llm=False,
    )

    assert "제가 할 수 있는 일" in output
    assert "대여소 위치" in output
    assert "station:553" not in output
    assert "답변 규칙" not in output


def test_followup_after_capability_question_uses_current_question(tmp_path):
    documents = [
        RagDocument(
            doc_id="station:102",
            text="따릉이 대여소 프로필. 대여소 번호 102. 대여소명 망원역 1번출구 앞. 자치구 마포구.",
            metadata={"source": "branch_data.parquet"},
        )
    ]
    index_dir = tmp_path / "rag_index"
    embedder = HashingEmbedder(dim=128)
    build_faiss_index(documents, index_dir, embedder)
    contextual_question = (
        "이전 대화 맥락을 참고해 현재 질문에 답한다.\n"
        "이전 질문: 뭘 할 수 있지?\n"
        "이전 답변 요약: 제가 할 수 있는 일은 따릉이 운영 데이터 + 공식 원천/문서 코퍼스 기반 질의입니다.\n"
        "현재 질문: 망원역 대여소 위치 알려줘"
    )

    output = answer_question(
        question=contextual_question,
        project_root=Path(__file__).resolve().parents[2],
        index_dir=index_dir,
        embedder=embedder,
        use_llm=False,
    )

    assert "제가 할 수 있는 일" not in output
    assert "station:102" in output
    assert "망원역 1번출구" in output


def test_general_chat_does_not_trigger_db_retrieval(tmp_path):
    documents = [
        RagDocument(
            doc_id="station:102",
            text="따릉이 대여소 프로필. 대여소 번호 102. 대여소명 망원역 1번출구 앞.",
            metadata={"source": "branch_data.parquet"},
        )
    ]
    index_dir = tmp_path / "rag_index"
    embedder = HashingEmbedder(dim=128)
    build_faiss_index(documents, index_dir, embedder)

    output = answer_question(
        question="안녕 오늘 기분 어때?",
        project_root=Path(__file__).resolve().parents[2],
        index_dir=index_dir,
        embedder=embedder,
        use_llm=False,
    )

    assert "안녕하세요" in output
    assert "따릉이 관련 질문" in output
    assert "RAG 검색 근거" not in output
    assert "station:102" not in output


def test_ttareungi_related_question_still_triggers_db_retrieval(tmp_path):
    documents = [
        RagDocument(
            doc_id="station:102",
            text="따릉이 대여소 프로필. 대여소 번호 102. 대여소명 망원역 1번출구 앞.",
            metadata={"source": "branch_data.parquet"},
        )
    ]
    index_dir = tmp_path / "rag_index"
    embedder = HashingEmbedder(dim=128)
    build_faiss_index(documents, index_dir, embedder)

    output = answer_question(
        question="따릉이 망원역 대여소 알려줘",
        project_root=Path(__file__).resolve().parents[2],
        index_dir=index_dir,
        embedder=embedder,
        use_llm=False,
    )

    assert "RAG 검색 근거" in output
    assert "station:102" in output


def test_fault_question_prioritizes_broken_dataset_doc(tmp_path):
    documents = [
        RagDocument(
            doc_id="dataset:newmeta",
            text="데이터셋 newmeta.parquet 행 수 1,390건 컬럼 new_dt age gender new",
            metadata={"source": "data/processed/parquet/bike_cloud/newmeta.parquet"},
        ),
        RagDocument(
            doc_id="dataset:broken",
            text="데이터셋 broken_data.parquet 행 수 515,233건 컬럼 date_bk bikenum type_bk",
            metadata={"source": "data/processed/parquet/bike_cloud/broken_data.parquet"},
        ),
    ]
    index_dir = tmp_path / "rag_index"
    embedder = HashingEmbedder(dim=128)
    build_faiss_index(documents, index_dir, embedder)

    results = search_faiss_index("고장 데이터로 뭘 볼 수 있어?", index_dir, embedder, top_k=2)

    assert results[0].document.doc_id == "dataset:broken"


def _make_parquet_project(tmp_path: Path) -> Path:
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
                "date": "2026-04-02",
                "branchnum": 102,
                "branchname": "망원역 1번출구 앞",
                "location1": "마포구",
                "location2": "서울특별시 마포구 월드컵로 72",
                "branch_x": 37.555,
                "branch_y": 126.91,
                "sy": "QR",
            },
        ]
    ).to_parquet(processed_dir / "branch_data.parquet", index=False)
    pd.DataFrame(
        [
            {"date_bk": "2026-04-01", "bikenum": "B1", "type_bk": "체인"},
            {"date_bk": "2026-04-01", "bikenum": "B2", "type_bk": "체인"},
            {"date_bk": "2026-04-02", "bikenum": "B3", "type_bk": "타이어"},
        ]
    ).to_parquet(processed_dir / "broken_data.parquet", index=False)
    pd.DataFrame(
        [
            {"datetime": "2026-04-01 00:00:00", "temperature": 12.0, "precipitation": 0.0, "windspeed": 2.0},
            {"datetime": "2026-04-01 01:00:00", "temperature": 14.0, "precipitation": 3.0, "windspeed": 4.0},
        ]
    ).to_parquet(processed_dir / "weather_data.parquet", index=False)
    pd.DataFrame(
        [
            {"date": "2026-04-01", "branchnum": 102, "rent_count": 10, "return_count": 8},
            {"date": "2026-04-02", "branchnum": 102, "rent_count": 12, "return_count": 11},
        ]
    ).to_parquet(processed_dir / "count_data.parquet", index=False)
    pd.DataFrame(
        [
            {"rentdate": "2026-04-01", "rentstation": 102, "returnstation": 103, "distance": 1200},
            {"rentdate": "2026-04-02", "rentstation": 102, "returnstation": 104, "distance": 2300},
        ]
    ).to_parquet(processed_dir / "rent_data.parquet", index=False)
    pd.DataFrame(
        [{"date": "2026-04-01", "branchnum": 102, "uselate_count": 2}]
    ).to_parquet(processed_dir / "uselate_data.parquet", index=False)
    pd.DataFrame(
        [{"new_dt": "2026-04", "age": "20대", "gender": "F", "new": 7}]
    ).to_parquet(processed_dir / "newmeta.parquet", index=False)
    pd.DataFrame(
        [{"date": "2026-04-01", "branchnum": 102, "branchname": "망원역 1번출구 앞"}]
    ).to_parquet(processed_dir / "master_branch_data.parquet", index=False)
    pd.DataFrame(
        [{"date": "2026-04-01", "source": "fixture", "rows": 1}]
    ).to_parquet(processed_dir / "meta.parquet", index=False)
    return project_root


def test_parquet_dataset_profiles_include_pyarrow_schema_and_catalog_files(tmp_path):
    project_root = _make_parquet_project(tmp_path)

    profiles = build_parquet_dataset_profiles(project_root)
    by_name = {profile.dataset_name: profile for profile in profiles}

    assert set(by_name) >= {"branch_data.parquet", "rent_data.parquet", "master_branch_data.parquet", "meta.parquet"}
    assert by_name["branch_data.parquet"].row_count == 2
    assert by_name["branch_data.parquet"].row_group_count >= 1
    assert "branchnum" in by_name["branch_data.parquet"].columns
    assert "date" in by_name["branch_data.parquet"].time_columns
    assert "branchnum" in by_name["branch_data.parquet"].schema


def test_parquet_catalog_and_pandas_aggregate_documents_are_grounded(tmp_path):
    project_root = _make_parquet_project(tmp_path)

    catalog_docs = build_parquet_catalog_documents(project_root, profile="db-only")
    aggregate_docs = build_pandas_aggregate_documents(project_root, profile="db-only")

    assert any(doc.metadata.get("brief_type") == "dataset_inventory_brief" for doc in catalog_docs)
    assert any(doc.metadata.get("brief_type") == "query_axis_brief" for doc in catalog_docs)
    assert any("row_count" in doc.metadata for doc in catalog_docs)
    assert any("고장 유형" in doc.text for doc in aggregate_docs)
    assert any("날씨 데이터" in doc.text for doc in aggregate_docs)
    assert any("대여/반납 이용" in doc.text for doc in aggregate_docs)
    assert all(not doc.doc_id.startswith("rent-row:") for doc in aggregate_docs)


def test_collect_pandas_fact_snippets_returns_question_specific_grounding(tmp_path):
    project_root = _make_parquet_project(tmp_path)

    station_facts = collect_pandas_fact_snippets(project_root, "망원역 대여소 위치 알려줘")
    fault_facts = collect_pandas_fact_snippets(project_root, "고장 데이터 유형 상위 알려줘")
    weather_facts = collect_pandas_fact_snippets(project_root, "날씨 평균 기온과 강수량 알려줘")

    assert any("망원역" in fact.text for fact in station_facts)
    assert any("체인" in fact.text for fact in fault_facts)
    assert any("평균 기온" in fact.text for fact in weather_facts)


def test_search_reranking_uses_column_and_granularity_metadata(tmp_path):
    documents = [
        RagDocument(
            doc_id="dataset:weather",
            text="날씨 데이터 요약. 평균 기온과 강수량을 제공한다.",
            metadata={
                "source": "weather_data.parquet",
                "dataset_name": "weather_data.parquet",
                "columns": ["datetime", "temperature", "precipitation", "windspeed"],
                "granularity": "hourly_weather",
            },
        ),
        RagDocument(
            doc_id="dataset:station",
            text="대여소 프로필. 주소와 자치구를 제공한다.",
            metadata={
                "source": "branch_data.parquet",
                "dataset_name": "branch_data.parquet",
                "columns": ["branchnum", "branchname", "location1"],
                "granularity": "station",
            },
        ),
    ]
    index_dir = tmp_path / "rag_index"
    embedder = HashingEmbedder(dim=128)
    build_faiss_index(documents, index_dir, embedder)

    results = search_faiss_index("temperature precipitation 컬럼 있는 날씨 데이터", index_dir, embedder, top_k=2)

    assert results[0].document.doc_id == "dataset:weather"


def test_build_rag_eval_questions_writes_100_grounded_rows(tmp_path):
    project_root = _make_parquet_project(tmp_path)
    output_path = tmp_path / "eval" / "rag_eval_questions.jsonl"

    rows = build_rag_eval_questions(project_root, output_path, count=100)
    parsed_rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 100
    assert len(parsed_rows) == 100
    required_fields = {
        "id",
        "question",
        "question_type",
        "expected_sources",
        "expected_data_fields",
        "expected_answer",
        "actual_answer",
        "judge_rule",
    }
    assert required_fields <= set(parsed_rows[0])
    assert any("broken_data.parquet" in row["expected_sources"] for row in parsed_rows)


def _make_ontology_hybrid_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / ".obybk-root").write_text("", encoding="utf-8")

    processed_dir = project_root / "data" / "processed" / "parquet" / "bike_cloud"
    processed_dir.mkdir(parents=True, exist_ok=True)
    (processed_dir / "branch_data.parquet").write_bytes(b"PAR1")
    (processed_dir / "weather_data.parquet").write_bytes(b"PAR1")

    bundle_path = project_root / "data" / "raw" / "_download_ontology_bundle_2026-04-27.json"
    structured_root = project_root / "data" / "raw" / "public" / "official_ontology"
    docs_root = project_root / "data" / "raw" / "docs" / "ttareungi"
    dataset_dir = structured_root / "OA-22300_capital_mobility_od"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "dataset_page.html").write_text(
        "<html><body><h1>수도권 생활이동 (출발-도착지 기준)</h1><p>출도착 행정동 기준 이동 원천</p></body></html>",
        encoding="utf-8",
    )
    zip_path = dataset_dir / "seoul_purpose_admdong3_20260331.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(
            "seoul_purpose_admdong3_20260331.csv",
            "start_dong,end_dong,purpose,count\n마포구,광진구,출근,120\n마포구,종로구,쇼핑,45\n",
        )

    page_only_dir = structured_root / "OA-714_bike_road_stats"
    page_only_dir.mkdir(parents=True, exist_ok=True)
    (page_only_dir / "dataset_page.html").write_text(
        "<html><body><h1>서울시 자전거도로 현황</h1><p>자전거도로 통계와 현황</p></body></html>",
        encoding="utf-8",
    )
    (page_only_dir / "sheet_view.html").write_text(
        "<html><body><table><tr><th>연도</th><th>길이</th></tr><tr><td>2025</td><td>100</td></tr></table></body></html>",
        encoding="utf-8",
    )

    pricing_dir = docs_root / "service" / "pricing_info"
    pricing_dir.mkdir(parents=True, exist_ok=True)
    (pricing_dir / "source.html").write_text(
        "<html><body><h1>이용요금 안내</h1><p>1시간권과 정기권 요금을 안내합니다.</p></body></html>",
        encoding="utf-8",
    )

    terms_dir = docs_root / "service" / "terms_pdf_2024_04_23"
    terms_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "timestamp": "2026-04-27 15:17:14",
        "summary": {
            "structured_file_artifact_count": 1,
            "structured_total_bytes": zip_path.stat().st_size,
            "document_file_artifact_count": 1,
            "document_total_bytes": (pricing_dir / "source.html").stat().st_size,
            "manifest_path": "data/raw/_download_ontology_bundle_2026-04-27.json",
        },
        "structured_downloads": [
            {
                "dataset_id": "OA-22300",
                "title": "수도권 생활이동 (출발-도착지 기준)",
                "page_url": "https://data.seoul.go.kr/dataList/OA-22300/F/1/datasetView.do",
                "storage_dir": "data/raw/public/official_ontology/OA-22300_capital_mobility_od",
                "download_mode": "latest_30",
                "selected_file_count": 1,
                "available_file_count": 1,
                "files": [
                    {
                        "seq": "260331",
                        "filename": zip_path.name,
                        "size_mb": "0.01",
                        "modified_date": "2026.04.26.",
                        "path": "data/raw/public/official_ontology/OA-22300_capital_mobility_od/seoul_purpose_admdong3_20260331.zip",
                        "status": "downloaded",
                        "size_bytes": zip_path.stat().st_size,
                    }
                ],
                "notes": [],
            },
            {
                "dataset_id": "OA-714",
                "title": "서울시 자전거도로 현황(2013년 이후) 통계",
                "page_url": "https://data.seoul.go.kr/dataList/OA-714/S/1/datasetView.do",
                "storage_dir": "data/raw/public/official_ontology/OA-714_bike_road_stats",
                "download_mode": "page_and_sheet_view",
                "page_status": 200,
                "files": [],
                "notes": ["sheetView HTML 저장 완료."],
            },
        ],
        "document_downloads": [
            {
                "category": "service",
                "key": "pricing_info",
                "title": "따릉이 이용요금 안내",
                "url": "https://www.bikeseoul.com/info/infoCoupon.do",
                "type": "html",
                "storage_dir": "data/raw/docs/ttareungi/service/pricing_info",
                "saved_files": [
                    {
                        "path": "data/raw/docs/ttareungi/service/pricing_info/source.html",
                        "status": "downloaded",
                        "size_bytes": (pricing_dir / "source.html").stat().st_size,
                    }
                ],
                "notes": [],
            },
            {
                "category": "service",
                "key": "terms_pdf_2024_04_23",
                "title": "따릉이 이용약관 PDF 2024-04-23",
                "url": "https://www.bikeseoul.com/upload/TermsofUse/TermsofUse%284.23.~%29.pdf",
                "type": "binary",
                "storage_dir": "data/raw/docs/ttareungi/service/terms_pdf_2024_04_23",
                "saved_files": [],
                "notes": [
                    "blocked_or_unavailable status=403 ctype=text/html; charset=iso-8859-1",
                    "Forbidden",
                ],
            },
        ],
    }
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return project_root


def test_default_index_dir_uses_ontology_hybrid_by_default(tmp_path):
    project_root = tmp_path / "project"

    assert default_index_dir(project_root) == project_root / "data" / "processed" / "rag" / "ttareungi_rag_index"
    assert default_index_dir(project_root, profile="db-only") == (
        project_root / "data" / "processed" / "rag" / "ttareungi_rag_index_db_only"
    )


def test_hybrid_corpus_documents_include_structured_and_blocked_briefs(tmp_path):
    project_root = _make_ontology_hybrid_project(tmp_path)

    documents = build_corpus_documents(project_root, profile="ontology-hybrid", max_station_docs=5)

    assert any(doc.metadata.get("brief_type") == "dataset_overview_brief" for doc in documents)
    assert any(doc.metadata.get("brief_type") == "file_window_brief" for doc in documents)
    assert any(doc.metadata.get("brief_type") == "page_only_brief" for doc in documents)
    assert any(doc.metadata.get("brief_type") == "document_overview_brief" for doc in documents)
    assert any(doc.metadata.get("brief_type") == "blocked_artifact_brief" for doc in documents)
    assert any(doc.metadata.get("dataset_id") == "OA-22300" for doc in documents)
    assert any(doc.metadata.get("availability") == "blocked" for doc in documents)


def test_build_rag_index_defaults_to_hybrid_and_writes_profile_manifest(tmp_path):
    project_root = _make_ontology_hybrid_project(tmp_path)
    index_dir = default_index_dir(project_root)

    build_rag_index(project_root=project_root, index_dir=index_dir, embedding_backend="hashing")

    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["profile"] == "ontology-hybrid"
    assert manifest["source_manifest"].endswith("_download_ontology_bundle_2026-04-27.json")
    assert manifest["blocked_artifact_count"] == 1
    assert manifest["corpus_counts"]["document_overview_brief"] >= 1
    assert manifest["dataset_profile_count"] >= 2


def test_build_rag_index_auto_embedding_writes_dataset_profile_manifest(tmp_path):
    project_root = _make_ontology_hybrid_project(tmp_path)
    index_dir = default_index_dir(project_root)

    build_rag_index(project_root=project_root, index_dir=index_dir, embedding_backend="auto")

    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["embedding_backend"] in {"hashing", "sentence-transformers"}
    assert manifest["dataset_profile_count"] >= 2


def test_recommendation_review_questions_are_routed_as_ttareungi_related():
    assert rag_module.is_ttareungi_related_question("추천 조치는 사람이 승인해야 하는가?")
    assert rag_module.is_ttareungi_related_question("reviewed_ontology_blueprint.md 근거를 알려줘")
    assert rag_module.is_ttareungi_related_question("ontology_seed.json 기준 답변 품질은 무엇인가?")
    assert rag_module.is_ttareungi_related_question("특정 시간대에 이용량이 줄어든 이유는 무엇인가?")
    assert rag_module.is_ttareungi_related_question("어떤 사용자들이 OBYBK를 주로 사용하는가?")


def test_held_pdf_evidence_question_is_not_capability_question():
    assert not rag_module.is_capability_question("보류된 PDF 문서는 바로 핵심 근거로 사용할 수 있는가?")


def test_repository_ontology_relation_facts_cover_core_question_types(tmp_path):
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    (artifact_dir / "ontology_seed.json").write_text(
        json.dumps(
            {
                "relations": [
                    {"id": "servesUser", "domain": "Service", "range": "User"},
                    {"id": "usesDataset", "domain": "Service", "range": "Dataset"},
                    {"id": "hasEvidence", "domain": "Recommendation", "range": "Evidence"},
                    {"id": "forStation", "domain": "UsageMetric", "range": "Station"},
                    {"id": "inTimeBucket", "domain": "UsageMetric", "range": "TimeBucket"},
                    {"id": "faultAtStation", "domain": "FaultEvent", "range": "Station"},
                    {"id": "affectedByWeather", "domain": "UsageMetric", "range": "WeatherObservation"},
                    {"id": "requiresReview", "domain": "Recommendation", "range": "ReviewDecision"},
                    {"id": "measuresAnswer", "domain": "EvaluationMetric", "range": "Recommendation"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    (index_dir / "manifest.json").write_text(
        json.dumps({"repository_ontology_artifact_dir": str(artifact_dir)}),
        encoding="utf-8",
    )

    usage = " ".join(
        fact.text for fact in rag_module.collect_repository_ontology_relation_facts(index_dir, "이용량이 줄어든 이유는?")
    )
    recommendation = " ".join(
        fact.text for fact in rag_module.collect_repository_ontology_relation_facts(index_dir, "추천 조치는 사람이 승인해야 하는가?")
    )
    quality = " ".join(
        fact.text for fact in rag_module.collect_repository_ontology_relation_facts(index_dir, "답변 품질은 어떤 기준으로 평가하는가?")
    )

    assert "forStation" in usage
    assert "inTimeBucket" in usage
    assert "affectedByWeather" in usage
    assert "hasEvidence" in recommendation
    assert "requiresReview" in recommendation
    assert "measuresAnswer" in quality


def test_answer_question_includes_relation_contract_for_usage_question(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    (artifact_dir / "ontology_seed.json").write_text(
        json.dumps(
            {
                "relations": [
                    {"id": "forStation", "domain": "UsageMetric", "range": "Station"},
                    {"id": "inTimeBucket", "domain": "UsageMetric", "range": "TimeBucket"},
                    {"id": "affectedByWeather", "domain": "UsageMetric", "range": "WeatherObservation"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    index_dir = tmp_path / "index"
    embedder = HashingEmbedder(dim=128)
    build_faiss_index(
        [RagDocument(doc_id="usage", text="따릉이 이용량 데이터", metadata={"source": "count_data.parquet"})],
        index_dir,
        embedder,
        extra_manifest={"repository_ontology_artifact_dir": str(artifact_dir)},
    )

    output = answer_question(
        question="특정 시간대에 이용량이 줄어든 이유는 무엇인가?",
        project_root=project_root,
        index_dir=index_dir,
        embedder=embedder,
        use_llm=False,
        profile="db-only",
    )

    assert "Ontology relation contract" in output
    assert "forStation" in output
    assert "inTimeBucket" in output
    assert "affectedByWeather" in output


def test_repository_ontology_artifact_facts_include_canonical_evidence_and_held_policy(tmp_path):
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    (artifact_dir / "ontology_seed.json").write_text(
        json.dumps(
            {
                "automation_boundary": "자동 실행은 하지 않고 추천 생성 후 사람이 검토·승인한다.",
                "canonical_evidence": [
                    {"path": "docs/project/aiplan.md", "role": "자동화 경계 근거"},
                    {"path": "docs/project/[데이터 수집 및 저장]수집 데이터.md", "role": "기준 데이터 근거"},
                ],
                "held_items": [
                    {"question_id": "CQ-025", "next_action": "OCR/본문 추출 후 재평가"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (artifact_dir / "reviewed_ontology_blueprint.md").write_text("보류 PDF는 재평가 필요", encoding="utf-8")
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    (index_dir / "manifest.json").write_text(
        json.dumps({"repository_ontology_artifact_dir": str(artifact_dir)}),
        encoding="utf-8",
    )

    facts = rag_module.collect_repository_ontology_artifact_facts(index_dir, "이 추천의 근거 문서는 무엇인가?")
    held_facts = rag_module.collect_repository_ontology_artifact_facts(index_dir, "보류된 PDF 문서는 바로 핵심 근거로 사용할 수 있는가?")

    joined = "\n".join(fact.text + " " + fact.source for fact in [*facts, *held_facts])
    assert "docs/project/aiplan.md" in joined
    assert "docs/project/[데이터 수집 및 저장]수집 데이터.md" in joined
    assert "ontology_seed.json" in joined
    assert "reviewed_ontology_blueprint.md" in joined
    assert "OCR/본문 추출 후 재평가" in joined


def test_answer_question_uses_repository_ontology_manifest_facts_for_evidence_questions(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    (artifact_dir / "ontology_seed.json").write_text(
        json.dumps(
            {
                "canonical_evidence": [{"path": "docs/project/aiplan.md", "role": "자동화 경계 근거"}],
                "automation_boundary": "자동 실행은 하지 않고 추천 생성 후 사람이 검토·승인한다.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (artifact_dir / "reviewed_ontology_blueprint.md").write_text("Recommendation requiresReview ReviewDecision", encoding="utf-8")
    index_dir = tmp_path / "index"
    embedder = HashingEmbedder(dim=128)
    build_faiss_index(
        [RagDocument(doc_id="irrelevant", text="운영 안내", metadata={"source": "guide"})],
        index_dir,
        embedder,
        extra_manifest={"repository_ontology_artifact_dir": str(artifact_dir)},
    )

    output = answer_question(
        question="이 추천의 근거 문서는 무엇인가?",
        project_root=project_root,
        index_dir=index_dir,
        embedder=embedder,
        use_llm=False,
        profile="db-only",
    )

    assert "docs/project/aiplan.md" in output
    assert "ontology_seed.json" in output
    assert "reviewed_ontology_blueprint.md" in output


def test_repository_ontology_artifact_documents_include_review_boundary(tmp_path):
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    (artifact_dir / "ontology_seed.json").write_text(
        json.dumps(
            {
                "project": {"name": "OBYBK", "domain_id": "public_bike_operation"},
                "core_problem": "운영 이상을 찾고 근거로 설명하며 다음 조치를 추천한다.",
                "automation_boundary": "자동 실행은 하지 않고 추천 생성 후 사람이 검토·승인한다.",
                "classes": [{"id": "Recommendation"}, {"id": "ReviewDecision"}, {"id": "Evidence"}],
                "relations": [
                    {"id": "hasEvidence", "domain": "Recommendation", "range": "Evidence"},
                    {"id": "requiresReview", "domain": "Recommendation", "range": "ReviewDecision"},
                ],
                "evaluation_metrics": ["근거 회수", "답변 가능성"],
                "canonical_evidence": [
                    {"path": "docs/project/aiplan.md", "role": "자동화 경계 근거"},
                    {"path": "docs/project/[데이터 수집 및 저장]수집 데이터.md", "role": "기준 데이터 근거"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (artifact_dir / "reviewed_ontology_blueprint.md").write_text(
        "# Reviewed Ontology Blueprint\n\nRecommendation은 Evidence와 ReviewDecision을 가져야 한다.",
        encoding="utf-8",
    )

    documents = rag_module.build_repository_ontology_artifact_documents(
        artifact_dir=artifact_dir,
        profile="ontology-hybrid",
    )

    assert {doc.metadata.get("source") for doc in documents} >= {
        "ontology_seed.json",
        "reviewed_ontology_blueprint.md",
    }
    joined = "\n".join(doc.text for doc in documents)
    assert "requiresReview" in joined
    assert "사람이 검토·승인" in joined
    assert "docs/project/aiplan.md" in joined


def test_hybrid_search_prioritizes_mobility_dataset_and_blocked_terms_doc(tmp_path):
    project_root = _make_ontology_hybrid_project(tmp_path)
    index_dir = default_index_dir(project_root)
    build_rag_index(project_root=project_root, index_dir=index_dir, embedding_backend="hashing")
    embedder = HashingEmbedder()

    mobility_output = answer_question(
        question="수도권 생활이동 원천 어떤 게 있어?",
        project_root=project_root,
        index_dir=index_dir,
        embedder=embedder,
        use_llm=False,
        profile="ontology-hybrid",
    )
    terms_output = answer_question(
        question="약관 PDF는 받았어?",
        project_root=project_root,
        index_dir=index_dir,
        embedder=embedder,
        use_llm=False,
        profile="ontology-hybrid",
    )

    assert "OA-22300" in mobility_output
    assert "blocked" in terms_output or "차단" in terms_output
    assert "terms_pdf_2024_04_23" in terms_output
