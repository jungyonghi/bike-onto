# Timestamp: 2026-04-21 23:34:00
# Timestamp: 2026-05-11 12:09:05

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from rag.ttareungi_rag import (
    DEFAULT_RAG_PROFILE,
    DEFAULT_LLM_URL,
    DEFAULT_OPENAI_API_KEY_ENV,
    DEFAULT_OPENAI_API_KEY_FILE,
    DEFAULT_QWEN_MODEL,
    LLM_PROVIDER_CHOICES,
    LLM_PROVIDER_LOCAL,
    PROFILE_CHOICES,
    answer_question,
    create_embedder,
    default_index_dir,
    find_project_root,
)


EXIT_COMMANDS = {"exit", "quit", "q", "종료", "나가기"}


@dataclass(frozen=True)
class ChatTurn:
    question: str
    answer: str


def build_contextual_question(raw_question: str, history: Sequence[ChatTurn]) -> str:
    if not history:
        return raw_question

    previous = history[-1]
    return (
        "이전 대화 맥락을 참고해 현재 질문에 답한다.\n"
        f"이전 질문: {previous.question}\n"
        f"이전 답변 요약: {previous.answer[:500]}\n"
        f"현재 질문: {raw_question}"
    )


def interactive_chat_loop(
    answer_fn: Callable[[str], str],
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
    max_history_turns: int = 3,
) -> int:
    history: list[ChatTurn] = []
    turn_count = 0

    print_fn("따릉이 RAG 챗봇입니다. 종료하려면 exit 또는 종료를 입력하세요.")
    while True:
        try:
            raw_question = input_fn("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print_fn("\n종료합니다.")
            return turn_count

        if not raw_question:
            continue
        if raw_question.lower() in EXIT_COMMANDS:
            print_fn("종료합니다.")
            return turn_count

        contextual_question = build_contextual_question(raw_question, history[-max_history_turns:])
        answer = answer_fn(contextual_question)
        print_fn(answer)
        history.append(ChatTurn(question=raw_question, answer=answer))
        history = history[-max_history_turns:]
        turn_count += 1


def run_interactive_chat(
    project_root: Path,
    index_dir: Path,
    top_k: int,
    use_llm: bool,
    llm_url: str,
    model: str,
    embedding_backend: str,
    max_history_turns: int,
    profile: str,
    llm_provider: str,
    api_key_file: Path,
    api_key_env: str,
) -> int:
    embedder = create_embedder(backend=embedding_backend)

    def answer_fn(question: str) -> str:
        return answer_question(
            question=question,
            project_root=project_root,
            index_dir=index_dir,
            embedder=embedder,
            top_k=top_k,
            use_llm=use_llm,
            llm_url=llm_url,
            model=model,
            profile=profile,
            llm_provider=llm_provider,
            api_key_file=api_key_file,
            api_key_env=api_key_env,
        )

    return interactive_chat_loop(answer_fn=answer_fn, max_history_turns=max_history_turns)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive OBYBK Ttareung-i RAG chatbot")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--index-dir", type=Path, default=None)
    parser.add_argument("--profile", choices=PROFILE_CHOICES, default=DEFAULT_RAG_PROFILE)
    parser.add_argument("--llm-provider", choices=LLM_PROVIDER_CHOICES, default=LLM_PROVIDER_LOCAL)
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_OPENAI_API_KEY_FILE)
    parser.add_argument("--api-key-env", default=DEFAULT_OPENAI_API_KEY_ENV)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--llm-url", default=DEFAULT_LLM_URL)
    parser.add_argument("--model", default=DEFAULT_QWEN_MODEL)
    parser.add_argument(
        "--embedding-backend",
        choices=["hashing", "auto", "sentence-transformers"],
        default="hashing",
    )
    parser.add_argument("--max-history-turns", type=int, default=3)

    args = parser.parse_args(argv)
    project_root = args.project_root or find_project_root(Path(__file__))
    index_dir = args.index_dir or default_index_dir(project_root, profile=args.profile)

    return run_interactive_chat(
        project_root=project_root,
        index_dir=index_dir,
        top_k=args.top_k,
        use_llm=not args.no_llm,
        llm_url=args.llm_url,
        model=args.model,
        embedding_backend=args.embedding_backend,
        max_history_turns=args.max_history_turns,
        profile=args.profile,
        llm_provider=args.llm_provider,
        api_key_file=args.api_key_file,
        api_key_env=args.api_key_env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
