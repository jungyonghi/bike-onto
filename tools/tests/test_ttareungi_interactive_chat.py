# Timestamp: 2026-04-21 23:31:00

from pathlib import Path
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.ttareungi_interactive import interactive_chat_loop  # noqa: E402


def test_interactive_chat_loop_reuses_previous_question_context():
    prompts = iter(["망원역 대여소 위치 알려줘", "고장 데이터도 같이 봐줘", "exit"])
    outputs: list[str] = []
    seen_questions: list[str] = []

    def fake_input(_: str) -> str:
        return next(prompts)

    def fake_print(message: str = "") -> None:
        outputs.append(message)

    def fake_answer(question: str) -> str:
        seen_questions.append(question)
        return f"답변: {question}"

    turns = interactive_chat_loop(
        answer_fn=fake_answer,
        input_fn=fake_input,
        print_fn=fake_print,
        max_history_turns=2,
    )

    assert turns == 2
    assert seen_questions[0] == "망원역 대여소 위치 알려줘"
    assert "이전 질문: 망원역 대여소 위치 알려줘" in seen_questions[1]
    assert "현재 질문: 고장 데이터도 같이 봐줘" in seen_questions[1]
    assert any("종료" in output for output in outputs)
