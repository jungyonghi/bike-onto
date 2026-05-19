# Timestamp: 2026-05-19 23:34:00

from __future__ import annotations

from pathlib import Path
import sys

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.natural_language_labels import display_value, humanize_mapping_values, naturalize_code_mentions  # noqa: E402
from rag.rag_llm_answer_endpoint import apply_answer_quality_guards, build_entity_cards  # noqa: E402


def test_display_value_prefers_human_labels_for_known_codes() -> None:
    assert display_value("gender", 1.0) == "남성(M)"
    assert display_value("gender", 0.0) == "여성(F)"
    assert display_value("age", 20) == "20대"
    assert display_value("age", 70) == "70대 이상"
    assert display_value("holiday", 1) == "공휴일"
    assert display_value("weekday", "Saturday") == "토요일"
    assert display_value("sy", "QR") == "QR형"


def test_unknown_numeric_values_are_not_relabelled_without_field_context() -> None:
    assert display_value("cnt_rack", 1.0) == "1.0"
    assert display_value("score", 0.0) == "0.0"


def test_humanize_mapping_values_preserves_raw_and_adds_display_labels() -> None:
    row = humanize_mapping_values({"gender": 1.0, "age": 20, "cnt_rack": 88})

    assert row["gender"] == 1.0
    assert row["gender_label"] == "남성(M)"
    assert row["age_label"] == "20대"
    assert "cnt_rack_label" not in row


def test_naturalize_code_mentions_rewrites_leaked_user_facing_codes() -> None:
    text = naturalize_code_mentions("gender 1.0은 100명이고 gender=0.0은 90명입니다. holiday=1 조건입니다.")

    assert "남성(M)" in text
    assert "여성(F)" in text
    assert "공휴일" in text
    assert "gender 1.0" not in text


def test_answer_quality_guard_naturalizes_code_labels() -> None:
    answer, notes = apply_answer_quality_guards("성별별 가입자 수", "gender 1.0은 10명, gender 0.0은 9명입니다.", {})

    assert "남성(M)" in answer
    assert "여성(F)" in answer
    assert "naturalized_code_labels" in notes


def test_entity_cards_include_display_attributes_for_known_codes() -> None:
    cards = build_entity_cards([{"type": "Cohort", "id": "cohort:1", "label": "cohort", "gender": 1.0, "age": 20}])

    assert cards[0]["attributes"]["gender"] == 1.0
    assert cards[0]["display_attributes"]["gender_label"] == "남성(M)"
    assert cards[0]["display_attributes"]["age_label"] == "20대"
