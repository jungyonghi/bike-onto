# Timestamp: 2026-04-27 18:02:00

from pathlib import Path
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.ttareungi_rag import HashingEmbedder, RagDocument, build_faiss_index  # noqa: E402
from rag.ttareungi_streamlit_app import DEFAULT_STREAMLIT_EMBEDDING_BACKEND, build_grounded_response  # noqa: E402


def test_streamlit_default_embedding_backend_uses_auto():
    assert DEFAULT_STREAMLIT_EMBEDDING_BACKEND == "auto"


def test_streamlit_payload_skips_retrieval_for_general_chat(tmp_path):
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

    payload = build_grounded_response(
        question="안녕 오늘 뭐해?",
        project_root=Path(__file__).resolve().parents[2],
        index_dir=index_dir,
        embedder=embedder,
        use_llm=False,
    )

    assert "안녕하세요" in payload.answer
    assert payload.search_results == []
    assert payload.facts == []
    assert payload.mode == "general"


def test_streamlit_payload_includes_retrieval_and_grounding_for_ttareungi_question(tmp_path):
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

    payload = build_grounded_response(
        question="따릉이 망원역 대여소 위치 알려줘",
        project_root=Path(__file__).resolve().parents[2],
        index_dir=index_dir,
        embedder=embedder,
        top_k=1,
        use_llm=False,
    )

    assert payload.mode == "rag"
    assert "LLM 호출 없이 검색 컨텍스트만 반환합니다" in payload.answer
    assert payload.search_results[0].document.doc_id == "station:102"
    assert "station:102" in payload.context_report
    assert "구조화 데이터 근거" in payload.context_report
