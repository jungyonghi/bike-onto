# Timestamp: 2026-05-19 23:28:00

from __future__ import annotations

import math
import re
from typing import Any


_FIELD_ALIASES: dict[str, str] = {
    "gender": "gender",
    "sex": "gender",
    "성별": "gender",
    "gender_code": "gender",
    "age": "age_band",
    "age_band": "age_band",
    "age_code": "age_band",
    "연령대코드": "age_band",
    "연령대": "age_band",
    "holiday": "holiday",
    "is_holiday": "holiday",
    "공휴일": "holiday",
    "weekday": "weekday",
    "day_of_week": "weekday",
    "요일": "weekday",
    "sy": "station_type",
    "station_type": "station_type",
    "type_sy": "station_type",
}

_GENDER_LABELS = {
    "0": "여성(F)",
    "0.0": "여성(F)",
    "f": "여성(F)",
    "female": "여성(F)",
    "여": "여성(F)",
    "여성": "여성(F)",
    "1": "남성(M)",
    "1.0": "남성(M)",
    "m": "남성(M)",
    "male": "남성(M)",
    "남": "남성(M)",
    "남성": "남성(M)",
}

_AGE_BAND_LABELS = {
    "10": "~10대",
    "10.0": "~10대",
    "20": "20대",
    "20.0": "20대",
    "30": "30대",
    "30.0": "30대",
    "40": "40대",
    "40.0": "40대",
    "50": "50대",
    "50.0": "50대",
    "60": "60대",
    "60.0": "60대",
    "70": "70대 이상",
    "70.0": "70대 이상",
    "70대~": "70대 이상",
    "70대이상": "70대 이상",
    "기타": "기타/미상",
}

_HOLIDAY_LABELS = {
    "0": "비공휴일",
    "0.0": "비공휴일",
    "false": "비공휴일",
    "n": "비공휴일",
    "1": "공휴일",
    "1.0": "공휴일",
    "true": "공휴일",
    "y": "공휴일",
}

_WEEKDAY_LABELS = {
    "monday": "월요일",
    "mon": "월요일",
    "tuesday": "화요일",
    "tue": "화요일",
    "wednesday": "수요일",
    "wed": "수요일",
    "thursday": "목요일",
    "thu": "목요일",
    "friday": "금요일",
    "fri": "금요일",
    "saturday": "토요일",
    "sat": "토요일",
    "sunday": "일요일",
    "sun": "일요일",
}

_STATION_TYPE_LABELS = {
    "qr": "QR형",
    "lcd": "LCD형",
}

_VALUE_LABELS: dict[str, dict[str, str]] = {
    "gender": _GENDER_LABELS,
    "age_band": _AGE_BAND_LABELS,
    "holiday": _HOLIDAY_LABELS,
    "weekday": _WEEKDAY_LABELS,
    "station_type": _STATION_TYPE_LABELS,
}


def _field_key(field_name: Any) -> str:
    raw = str(field_name or "").strip().strip("'").strip('"')
    raw = raw.replace(" ", "_").lower()
    return _FIELD_ALIASES.get(raw, raw)


def _value_key(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip().strip("'").strip('"').strip()
    text = text.replace(",", "")
    if re.fullmatch(r"[-+]?\d+\.0+", text):
        return str(int(float(text))) if text not in {"0.0", "1.0", "10.0", "20.0", "30.0", "40.0", "50.0", "60.0", "70.0"} else text
    return text.lower()


def display_value(field_name: Any, value: Any, *, fallback: str | None = None) -> str:
    """Return a human-readable label for a coded categorical value.

    The resolver is field-aware: numeric values are translated only when the
    field name is known (for example gender=1.0 -> 남성(M)). Unknown fields keep
    the original value so quantitative metrics are not accidentally relabeled.
    """
    field = _field_key(field_name)
    raw_text = str(value).strip() if value is not None else ""
    if not raw_text or raw_text.lower() == "nan":
        return fallback or "미상"
    labels = _VALUE_LABELS.get(field)
    if not labels:
        return raw_text
    key = _value_key(value)
    return labels.get(key) or labels.get(raw_text.lower()) or raw_text


def humanize_mapping_values(mapping: dict[str, Any], *, suffix: str = "_label") -> dict[str, Any]:
    """Add human-readable companion fields for known coded values.

    Raw values are preserved for traceability; display fields are added so UI,
    LLM prompts, reports, and Obsidian exports can prefer natural language.
    """
    result = dict(mapping)
    for key, value in mapping.items():
        label = display_value(key, value, fallback="")
        if label and label != str(value).strip():
            result[f"{key}{suffix}"] = label
    return result


def naturalize_code_mentions(text: str) -> str:
    """Replace common leaked categorical codes in user-facing text."""
    result = text
    replacements = [
        (r"\bgender\s*(?:=|:)?\s*1(?:\.0)?\b", "남성(M)"),
        (r"\bgender\s*(?:=|:)?\s*0(?:\.0)?\b", "여성(F)"),
        (r"\b성별\s*(?:=|:)?\s*1(?:\.0)?\b", "성별 남성(M)"),
        (r"\b성별\s*(?:=|:)?\s*0(?:\.0)?\b", "성별 여성(F)"),
        (r"\bholiday\s*(?:=|:)?\s*1(?:\.0)?\b", "공휴일"),
        (r"\bholiday\s*(?:=|:)?\s*0(?:\.0)?\b", "비공휴일"),
    ]
    for pattern, label in replacements:
        result = re.sub(pattern, label, result, flags=re.I)
    return result
