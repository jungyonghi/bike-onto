# Timestamp: 2026-05-19 17:30:00

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote
import unicodedata

from rag.answer_composer import entity_display_name, relation_label


@dataclass(frozen=True)
class InspectorEntity:
    index: int
    entity_id: str
    label: str
    entity_type: str
    source: str
    raw: dict[str, Any]


def _short(value: Any, width: int = 96) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    if len(text) <= width:
        return text
    return text[: max(0, width - 3)].rstrip() + "..."


def _entity_id(value: dict[str, Any]) -> str:
    return str(value.get("id") or value.get("candidate_id") or value.get("label") or value.get("display_name") or "").strip()


def _entity_label(value: dict[str, Any]) -> str:
    if value.get("candidate_id") and not value.get("id"):
        return str(value.get("candidate_id"))
    try:
        return entity_display_name(value)
    except Exception:
        return str(value.get("display_name") or value.get("label") or value.get("id") or value.get("candidate_id") or "명칭 미확인")


def collect_inspector_entities(payload: dict[str, Any]) -> list[InspectorEntity]:
    entities: list[InspectorEntity] = []
    seen: set[str] = set()

    def add(raw: dict[str, Any], source: str) -> None:
        entity_id = _entity_id(raw)
        if not entity_id or entity_id in seen:
            return
        seen.add(entity_id)
        entities.append(
            InspectorEntity(
                index=len(entities) + 1,
                entity_id=entity_id,
                label=_entity_label(raw),
                entity_type=str(raw.get("type") or raw.get("source_id") or source or "Entity"),
                source=source,
                raw=raw,
            )
        )

    for item in payload.get("related_objects") or []:
        if isinstance(item, dict):
            add(item, "related_objects")
    for item in payload.get("entity_cards") or []:
        if isinstance(item, dict):
            add(item, "entity_cards")
    for item in payload.get("candidate_set") or []:
        if isinstance(item, dict):
            add(item, "candidate_set")
    return entities


def _select_entity(entities: list[InspectorEntity], selector: str | None) -> InspectorEntity | None:
    if not entities:
        return None
    if not selector:
        return entities[0]
    cleaned = selector.strip()
    if cleaned.isdigit():
        index = int(cleaned)
        if 1 <= index <= len(entities):
            return entities[index - 1]
    lowered = cleaned.lower()
    for entity in entities:
        if lowered in {entity.entity_id.lower(), entity.label.lower()} or lowered in entity.label.lower() or lowered in entity.entity_id.lower():
            return entity
    return entities[0]


def _entity_uri(entity: InspectorEntity) -> str:
    return "obybk://entity/" + quote(entity.entity_id, safe="")


def _osc8(label: str, uri: str, enabled: bool) -> str:
    if not enabled:
        return label
    return f"\033]8;;{uri}\033\\{label}\033]8;;\033\\"


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\][^\x1b]*(?:\x1b\\|\x07)", "", text)


def _cell_width(char: str) -> int:
    if not char:
        return 0
    if unicodedata.combining(char):
        return 0
    category = unicodedata.category(char)
    if category.startswith("C"):
        return 0
    return 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1


def _display_width(text: str) -> int:
    return sum(_cell_width(char) for char in _strip_ansi(text))


def _wrap_plain_display(text: str, width: int) -> list[str]:
    lines: list[str] = []
    current: list[str] = []
    current_width = 0
    last_space_index = -1
    last_space_width = 0
    for char in text:
        char_width = _cell_width(char)
        if current_width + char_width > width and current:
            if last_space_index > 0:
                lines.append("".join(current[:last_space_index]).rstrip())
                remainder = "".join(current[last_space_index + 1 :]).lstrip()
                current = list(remainder)
                current_width = _display_width(remainder)
            else:
                lines.append("".join(current).rstrip())
                current = []
                current_width = 0
            last_space_index = -1
            last_space_width = 0
        current.append(char)
        current_width += char_width
        if char.isspace():
            last_space_index = len(current) - 1
            last_space_width = current_width
    if current:
        lines.append("".join(current).rstrip())
    return lines or [""]


def _wrap_line(line: str, width: int) -> list[str]:
    if _display_width(line) <= width:
        return [line]
    return _wrap_plain_display(_strip_ansi(line), width)


def _box(title: str, lines: list[str], *, width: int = 112, style: str = "single") -> list[str]:
    if width < 40:
        width = 40
    if style == "double":
        tl, tr, bl, br, hz, vt = "╔", "╗", "╚", "╝", "═", "║"
    else:
        tl, tr, bl, br, hz, vt = "┌", "┐", "└", "┘", "─", "│"
    inner = width - 2
    title_text = f" {title} "
    top = tl + title_text + hz * max(0, inner - _display_width(title_text)) + tr
    rendered = [top]
    for line in lines:
        for wrapped in _wrap_line(line, inner - 2):
            plain_width = _display_width(wrapped)
            rendered.append(vt + " " + wrapped + " " * max(0, inner - 2 - plain_width) + " " + vt)
    rendered.append(bl + hz * inner + br)
    return rendered


def _relation_lines(payload: dict[str, Any], focused: InspectorEntity | None, limit: int = 8) -> list[str]:
    rows = payload.get("related_relations") or []
    lines: list[str] = []
    focused_id = focused.entity_id.lower() if focused else ""
    for relation in rows:
        if not isinstance(relation, dict):
            continue
        source = str(relation.get("source") or relation.get("from") or relation.get("subject") or "?")
        rel = str(relation.get("relation") or relation.get("type") or "relation")
        target = str(relation.get("target") or relation.get("to") or relation.get("object") or "?")
        raw = f"{source} --{relation_label(rel)} / {rel}--> {target}"
        if focused_id and focused_id not in raw.lower():
            # Keep a few general relation lines even when exact ids differ.
            if len(lines) >= 3:
                continue
        lines.append("- " + raw)
        if len(lines) >= limit:
            break
    return lines or ["- 현재 payload에서 명시 relation 없음"]


def _evidence_lines(payload: dict[str, Any], limit: int = 7) -> list[str]:
    excerpts = payload.get("evidence_excerpt_list") or []
    lines: list[str] = []
    for item in excerpts:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        kind = item.get("kind")
        score = item.get("score")
        excerpt = _short(item.get("excerpt"), 120)
        lines.append(f"- {source} [{kind}, score={score}] {excerpt}")
        if len(lines) >= limit:
            break
    return lines or ["- 현재 payload에서 evidence excerpt 없음"]


def _gap_lines(payload: dict[str, Any], limit: int = 5) -> list[str]:
    gaps = payload.get("data_gaps") or []
    if not gaps:
        return ["- data gap 없음"]
    return ["- " + _short(gap, 125) for gap in gaps[:limit]]


def _action_lines(payload: dict[str, Any], limit: int = 5) -> list[str]:
    actions = payload.get("recommended_actions") or []
    lines: list[str] = []
    for action in actions:
        if isinstance(action, dict):
            summary = action.get("summary") or action.get("label") or action.get("type") or action
            lines.append("- " + _short(summary, 125))
        else:
            lines.append("- " + _short(action, 125))
        if len(lines) >= limit:
            break
    return lines or ["- recommended action 없음"]


def render_terminal_entity_inspector(
    payload: dict[str, Any],
    *,
    focused_entity: str | None = None,
    width: int = 112,
    hyperlinks: bool = False,
) -> str:
    """Render a browserless popup-style terminal inspector for a RAG answer payload."""
    entities = collect_inspector_entities(payload)
    focused = _select_entity(entities, focused_entity)
    answer = _short(payload.get("answer"), 260)
    question = _short(payload.get("question") or payload.get("input_question") or "", 160)
    lines: list[str] = []
    header = [
        "OBYBK Terminal Entity Inspector",
        "Headless-friendly popup-style view. In supported terminals, Ctrl+Click entity labels opens an OSC-8 entity URI.",
        f"question: {question or '(question not embedded in payload)'}",
        f"answer: {answer}",
        f"contract_pass={payload.get('contract_pass')} | requires_review={payload.get('requires_review')} | llm_mode={payload.get('llm', {}).get('mode')}",
    ]
    lines.extend(_box("RAG Answer Inspection", header, width=width, style="double"))

    entity_lines: list[str] = []
    if entities:
        for entity in entities[:12]:
            label = _osc8(entity.label, _entity_uri(entity), hyperlinks)
            marker = "▶" if focused and entity.entity_id == focused.entity_id else " "
            entity_lines.append(f"{marker} [{entity.index}] {label}  id={entity.entity_id}  type={entity.entity_type}  source={entity.source}")
    else:
        entity_lines.append("- 현재 payload에서 entity/candidate 없음")
    lines.extend(_box("Entity List", entity_lines, width=width))

    if focused:
        attrs = {key: value for key, value in focused.raw.items() if key not in {"id", "label", "display_name", "type"} and value not in (None, "", [])}
        popup = [
            f"label: {focused.label}",
            f"id: {focused.entity_id}",
            f"type: {focused.entity_type}",
            f"source: {focused.source}",
            f"terminal_link: {_entity_uri(focused)}",
            "",
            "attributes:",
        ]
        if attrs:
            for key, value in list(attrs.items())[:10]:
                popup.append(f"- {key}: {_short(value, 95)}")
        else:
            popup.append("- 상세 attribute는 현재 RAG context에 없음")
        popup.append("")
        popup.append("relations:")
        popup.extend(_relation_lines(payload, focused, limit=6))
        popup.append("")
        popup.append("review/data gaps:")
        popup.extend(_gap_lines(payload, limit=4))
        lines.extend(_box("Entity Popup", popup, width=width, style="double"))

    lines.extend(_box("Evidence", _evidence_lines(payload), width=width))
    lines.extend(_box("Recommended Actions", _action_lines(payload), width=width))
    lines.append("Hint: use --entity <number-or-id> to focus another entity; use --terminal-links for Ctrl+Click links in supported terminals.")
    return "\n".join(lines) + "\n"


def write_terminal_inspector_screenshot(text: str, output: Path, *, title: str = "OBYBK Terminal Entity Inspector") -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:  # pragma: no cover - optional screenshot dependency
        raise RuntimeError("Pillow is required for inspector screenshots") from exc

    clean = _strip_ansi(text).rstrip("\n")
    raw_lines = clean.splitlines() or [""]
    max_cells = min(max(_display_width(line) for line in raw_lines), 132)
    visible_lines = raw_lines
    font_candidates = [
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 6),
        ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 0),
    ]
    font_path, font_index = next((item for item in font_candidates if Path(item[0]).exists()), font_candidates[-1])
    try:
        body_font = ImageFont.truetype(font_path, 18, index=font_index)
        title_font = ImageFont.truetype(font_path, 27, index=font_index)
    except TypeError:  # Pillow versions without TTC index support.
        body_font = ImageFont.truetype(font_path, 18)
        title_font = ImageFont.truetype(font_path, 27)
    cell_px = max(9, int(body_font.getlength("0")))
    width = max(1280, min(1920, 58 + max_cells * cell_px))
    line_height = 29
    height = 104 + len(visible_lines) * line_height + 42
    image = Image.new("RGB", (width, height), "#0f172a")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 52), fill="#111827")
    draw.text((24, 12), title, font=title_font, fill="#e5e7eb")
    y = 74
    for line in visible_lines:
        color = "#e5e7eb"
        if line.startswith(("╔", "╚", "┌", "└")):
            color = "#93c5fd"
        elif "▶" in line or "Entity Popup" in line:
            color = "#fef08a"
        elif "requires_review=True" in line or "data gap" in line.lower():
            color = "#fca5a5"
        elif "Evidence" in line or "relation" in line.lower():
            color = "#86efac"
        draw.text((24, y), line[:150], font=body_font, fill=color)
        y += line_height
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
