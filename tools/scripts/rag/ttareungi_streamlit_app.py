# Timestamp: 2026-04-27 18:02:00
# Timestamp: 2026-05-11 12:09:05

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Sequence


TOOLS_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_SCRIPTS_DIR))

from rag.ttareungi_interactive import ChatTurn, build_contextual_question
from rag.ttareungi_rag import (
    DEFAULT_RAG_PROFILE,
    DEFAULT_LLM_URL,
    DEFAULT_OPENAI_API_KEY_ENV,
    DEFAULT_OPENAI_API_KEY_FILE,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_QWEN_MODEL,
    FactSnippet,
    HashingEmbedder,
    LLM_PROVIDER_CHOICES,
    LLM_PROVIDER_LOCAL,
    LLM_PROVIDER_OPENAI,
    PROFILE_CHOICES,
    SearchResult,
    SentenceTransformerEmbedder,
    build_capability_answer,
    build_context_report,
    build_general_chat_answer,
    build_prompt,
    build_rag_index,
    call_qwen_chat,
    collect_fact_snippets,
    create_embedder_for_index,
    current_question_text,
    default_index_dir,
    find_project_root,
    index_is_ready,
    is_capability_question,
    is_ttareungi_related_question,
    resolve_llm_runtime_settings,
    search_faiss_index,
)


DEFAULT_STREAMLIT_LLM_URL = "http://127.0.0.1:11434/v1/chat/completions"
DEFAULT_STREAMLIT_MODEL = "qwen3:0.6b"
DEFAULT_STREAMLIT_EMBEDDING_BACKEND = "auto"
STREAMLIT_EMBEDDING_BACKEND_CHOICES = ("auto", "sentence-transformers", "hashing")


@dataclass(frozen=True)
class GroundedResponse:
    question: str
    answer: str
    mode: str
    search_results: list[SearchResult]
    facts: list[FactSnippet]
    context_report: str
    error: str | None = None


def build_grounded_response(
    question: str,
    project_root: Path,
    index_dir: Path,
    embedder: HashingEmbedder | SentenceTransformerEmbedder,
    top_k: int = 5,
    use_llm: bool = True,
    llm_url: str = DEFAULT_STREAMLIT_LLM_URL,
    model: str = DEFAULT_STREAMLIT_MODEL,
    profile: str = DEFAULT_RAG_PROFILE,
    llm_provider: str = LLM_PROVIDER_LOCAL,
    api_key_file: Path | str | None = DEFAULT_OPENAI_API_KEY_FILE,
    api_key_env: str = DEFAULT_OPENAI_API_KEY_ENV,
) -> GroundedResponse:
    current_question = current_question_text(question)

    if is_capability_question(current_question):
        return GroundedResponse(
            question=current_question,
            answer=build_capability_answer(),
            mode="capability",
            search_results=[],
            facts=[],
            context_report="",
        )

    if not is_ttareungi_related_question(current_question):
        return GroundedResponse(
            question=current_question,
            answer=build_general_chat_answer(current_question),
            mode="general",
            search_results=[],
            facts=[],
            context_report="",
        )

    search_results = search_faiss_index(current_question, index_dir, embedder, top_k=top_k)
    facts = collect_fact_snippets(project_root, current_question, profile=profile)
    context_report = build_context_report(question, search_results, facts)

    if not use_llm:
        return GroundedResponse(
            question=current_question,
            answer="LLM 호출 없이 검색 컨텍스트만 반환합니다.\n\n" + context_report,
            mode="rag",
            search_results=search_results,
            facts=facts,
            context_report=context_report,
        )

    prompt = build_prompt(question, search_results, facts)
    try:
        runtime = resolve_llm_runtime_settings(
            project_root=project_root,
            provider=llm_provider,
            llm_url=llm_url,
            model=model,
            api_key_file=api_key_file,
            api_key_env=api_key_env,
        )
        answer = call_qwen_chat(
            prompt=prompt,
            llm_url=runtime.llm_url,
            model=runtime.model,
            api_key=runtime.api_key,
        ).strip()
        if not answer:
            raise ValueError("LLM returned an empty answer")
        return GroundedResponse(
            question=current_question,
            answer=answer,
            mode="rag",
            search_results=search_results,
            facts=facts,
            context_report=context_report,
        )
    except Exception as exc:
        return GroundedResponse(
            question=current_question,
            answer=(
                "LLM 서버 호출에 실패해 검색 컨텍스트를 반환합니다.\n"
                f"오류: {type(exc).__name__}: {exc}\n\n"
                + context_report
            ),
            mode="rag",
            search_results=search_results,
            facts=facts,
            context_report=context_report,
            error=f"{type(exc).__name__}: {exc}",
        )


def _require_streamlit():
    try:
        import streamlit as st
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised by local CLI usage.
        raise SystemExit(
            "streamlit이 설치되어 있지 않습니다. "
            "다음 명령으로 설치하세요: .venv/bin/pip install streamlit"
        ) from exc
    return st


def _result_rows(search_results: Sequence[SearchResult]) -> list[dict[str, str | float | int]]:
    rows: list[dict[str, str | float | int]] = []
    for result in search_results:
        rows.append(
            {
                "rank": result.rank,
                "score": round(result.score, 3),
                "doc_id": result.document.doc_id,
                "source": str(result.document.metadata.get("source", "unknown")),
                "text": result.document.text[:260],
            }
        )
    return rows


def _render_grounding(st, payload: GroundedResponse) -> None:
    if payload.mode in {"general", "capability"}:
        return

    with st.expander("Retrieval / Grounding", expanded=False):
        if payload.error:
            st.warning(payload.error)

        st.caption("구조화 데이터 근거")
        if payload.facts:
            for fact in payload.facts:
                st.markdown(f"- **{fact.title}**: {fact.text}  \n  source: `{fact.source}`")
        else:
            st.write("직접 조회된 구조화 근거 없음")

        st.caption("RAG 검색 근거")
        rows = _result_rows(payload.search_results)
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.write("RAG 검색 근거 없음")

        st.caption("Grounded Context")
        st.code(payload.context_report, language="text")


def _history_turns(messages: Sequence[dict[str, object]], max_turns: int) -> list[ChatTurn]:
    turns: list[ChatTurn] = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        question = str(message.get("question", ""))
        answer = str(message.get("content", ""))
        if question and answer:
            turns.append(ChatTurn(question=question, answer=answer))
    return turns[-max_turns:]


def run_app() -> None:
    st = _require_streamlit()

    st.set_page_config(page_title="따릉이 RAG 챗봇", layout="wide")
    st.title("따릉이 RAG 챗봇")

    project_root = find_project_root(Path(__file__))

    with st.sidebar:
        st.header("설정")
        if "rag_index_profile" not in st.session_state:
            st.session_state["rag_index_profile"] = DEFAULT_RAG_PROFILE
        selected_profile = st.selectbox("Index profile", list(PROFILE_CHOICES), key="rag_index_profile")
        default_index = default_index_dir(project_root, profile=selected_profile)
        if st.session_state.get("_last_rag_index_profile") != selected_profile:
            st.session_state["rag_index_dir_input"] = str(default_index)
            st.session_state["_last_rag_index_profile"] = selected_profile
        project_root_input = st.text_input("Project root", value=str(project_root), key="rag_project_root_input")
        index_dir_input = st.text_input("Index dir", key="rag_index_dir_input")
        top_k = st.slider("Top K", min_value=1, max_value=10, value=5)
        max_history_turns = st.slider("History turns", min_value=0, max_value=5, value=3)
        embedding_backend = st.selectbox(
            "Embedding",
            list(STREAMLIT_EMBEDDING_BACKEND_CHOICES),
            index=list(STREAMLIT_EMBEDDING_BACKEND_CHOICES).index(DEFAULT_STREAMLIT_EMBEDDING_BACKEND),
        )
        use_llm = st.checkbox("LLM 사용", value=True)
        llm_provider = st.selectbox(
            "LLM provider",
            list(LLM_PROVIDER_CHOICES),
            index=list(LLM_PROVIDER_CHOICES).index(LLM_PROVIDER_LOCAL),
        )
        provider_default_url = DEFAULT_OPENAI_BASE_URL if llm_provider == LLM_PROVIDER_OPENAI else DEFAULT_STREAMLIT_LLM_URL
        provider_default_model = DEFAULT_OPENAI_MODEL if llm_provider == LLM_PROVIDER_OPENAI else DEFAULT_STREAMLIT_MODEL
        llm_url = st.text_input("LLM URL", value=provider_default_url or DEFAULT_LLM_URL)
        model = st.text_input("Model", value=provider_default_model or DEFAULT_QWEN_MODEL)
        api_key_file = st.text_input("OpenAI key file", value=str(DEFAULT_OPENAI_API_KEY_FILE))
        api_key_env = st.text_input("OpenAI key env", value=DEFAULT_OPENAI_API_KEY_ENV)

        resolved_project_root = Path(project_root_input).expanduser()
        resolved_index_dir = Path(index_dir_input).expanduser()
        index_ready = index_is_ready(resolved_index_dir)
        st.status("인덱스 준비됨" if index_ready else "인덱스 없음", state="complete" if index_ready else "error")

        if st.button("인덱스 다시 만들기", type="secondary"):
            with st.spinner("운영 데이터 + 공식 원천/문서 기반 RAG 인덱스를 다시 만드는 중..."):
                build_rag_index(
                    project_root=resolved_project_root,
                    index_dir=resolved_index_dir,
                    embedding_backend=embedding_backend,
                    profile=selected_profile,
                )
            st.success("인덱스 생성 완료")

        if st.button("대화 초기화"):
            st.session_state["messages"] = []
            st.rerun()

    @st.cache_resource(show_spinner=False)
    def cached_embedder(backend: str, index_dir_text: str):
        return create_embedder_for_index(Path(index_dir_text).expanduser(), backend=backend)

    embedder = cached_embedder(embedding_backend, str(resolved_index_dir))

    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    for message in st.session_state["messages"]:
        with st.chat_message(str(message["role"])):
            st.markdown(str(message["content"]))
            payload = message.get("payload")
            if isinstance(payload, GroundedResponse):
                _render_grounding(st, payload)

    raw_question = st.chat_input("일반 대화도 가능해요. 따릉이 질문은 운영 데이터 + 공식 원천/문서 근거로 답합니다.")
    if not raw_question:
        return

    st.session_state["messages"].append({"role": "user", "content": raw_question})
    with st.chat_message("user"):
        st.markdown(raw_question)

    history = _history_turns(st.session_state["messages"], max_history_turns)
    contextual_question = build_contextual_question(raw_question, history)

    with st.chat_message("assistant"):
        with st.spinner("검색하고 근거를 정리하는 중..."):
            payload = build_grounded_response(
                question=contextual_question,
                project_root=resolved_project_root,
                index_dir=resolved_index_dir,
                embedder=embedder,
                top_k=top_k,
                use_llm=use_llm,
                llm_url=llm_url,
                model=model,
                profile=selected_profile,
                llm_provider=llm_provider,
                api_key_file=api_key_file,
                api_key_env=api_key_env,
            )
        st.markdown(payload.answer)
        _render_grounding(st, payload)

    st.session_state["messages"].append(
        {
            "role": "assistant",
            "question": raw_question,
            "content": payload.answer,
            "payload": payload,
        }
    )


if __name__ == "__main__":
    run_app()
