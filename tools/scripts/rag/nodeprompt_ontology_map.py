# Timestamp: 2026-05-19 18:15:00

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import math
import re
import textwrap
from typing import Any, Iterable

from rag.answer_composer import entity_display_name, relation_label


@dataclass(frozen=True)
class OntologyMapNode:
    id: str
    label: str
    type: str
    weight: float
    description: str
    parent_id: str | None = None
    depth: int = 0


@dataclass(frozen=True)
class OntologyMapEdge:
    source: str
    target: str
    relation: str = "parent-child"
    strength: float = 0.75


TYPE_STYLES: dict[str, dict[str, str]] = {
    "framework": {"fill": "#111111", "outline": "#111111"},
    "claim": {"fill": "#111111", "outline": "#111111"},
    "evidence": {"fill": "#737373", "outline": "#111111"},
    "entity": {"fill": "#262626", "outline": "#111111"},
    "relation": {"fill": "#ffffff", "outline": "#111111"},
    "review": {"fill": "#fca5a5", "outline": "#b91c1c"},
    "store": {"fill": "#d4d4d4", "outline": "#404040"},
    "projection": {"fill": "#e5e7eb", "outline": "#111111"},
    "domain": {"fill": "#a3a3a3", "outline": "#111111"},
}


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^0-9a-z가-힣_-]+", "-", text)
    return text.strip("-") or "item"


def _payload_entity_id(raw: dict[str, Any]) -> str:
    return str(raw.get("id") or raw.get("candidate_id") or raw.get("label") or raw.get("display_name") or "").strip()


def _payload_entity_label(raw: dict[str, Any]) -> str:
    if raw.get("candidate_id") and not raw.get("id"):
        return str(raw.get("candidate_id"))
    try:
        return entity_display_name(raw)
    except Exception:
        return str(raw.get("display_name") or raw.get("label") or raw.get("id") or raw.get("candidate_id") or "Entity")


def _payload_entities(answer_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not answer_payload:
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in ("related_objects", "entity_cards", "candidate_set"):
        for raw in answer_payload.get(key) or []:
            if not isinstance(raw, dict):
                continue
            entity_id = _payload_entity_id(raw)
            if not entity_id or entity_id in seen:
                continue
            seen.add(entity_id)
            rows.append(raw)
    return rows


def _append_answer_payload_map(
    nodes: list[OntologyMapNode],
    edges: list[OntologyMapEdge],
    answer_payload: dict[str, Any] | None,
) -> dict[str, str]:
    id_to_node: dict[str, str] = {}
    entities = _payload_entities(answer_payload)
    if not entities:
        return id_to_node
    max_entities = 10
    for index, raw in enumerate(entities[:max_entities], start=1):
        entity_id = _payload_entity_id(raw)
        node_id = f"payload_entity_{_slug(entity_id)}"
        id_to_node[entity_id] = node_id
        label = _payload_entity_label(raw)
        description_bits = [str(raw.get("type") or raw.get("source_id") or "RAG entity")]
        if raw.get("district"):
            description_bits.append(f"district={raw.get('district')}")
        if raw.get("score") is not None:
            description_bits.append(f"score={raw.get('score')}")
        nodes.append(
            OntologyMapNode(
                node_id,
                label,
                "domain",
                max(0.40, 0.70 - index * 0.035),
                ", ".join(description_bits),
                "domain_entity",
                3,
            )
        )
        edges.append(OntologyMapEdge("candidate_set", node_id, "retrieves", 0.72))
        edges.append(OntologyMapEdge(node_id, "relation_type", "participatesIn", 0.58))
    relation_rows = answer_payload.get("related_relations") if answer_payload else []
    for index, relation in enumerate((relation_rows or [])[:8], start=1):
        if not isinstance(relation, dict):
            continue
        source = str(relation.get("source") or relation.get("from") or relation.get("subject") or "").strip()
        target = str(relation.get("target") or relation.get("to") or relation.get("object") or "").strip()
        raw_relation = str(relation.get("relation") or relation.get("type") or "relation")
        rel_node = f"payload_relation_{index}_{_slug(raw_relation)}"
        nodes.append(
            OntologyMapNode(
                rel_node,
                relation_label(raw_relation),
                "relation",
                0.48,
                raw_relation,
                "relation_type",
                3,
            )
        )
        if source in id_to_node:
            edges.append(OntologyMapEdge(id_to_node[source], rel_node, raw_relation, 0.70))
        if target in id_to_node:
            edges.append(OntologyMapEdge(rel_node, id_to_node[target], raw_relation, 0.70))
    return id_to_node


def build_obybk_ontology_map(answer_payload: dict[str, Any] | None = None) -> tuple[list[OntologyMapNode], list[OntologyMapEdge], dict[str, str]]:
    nodes = [
        OntologyMapNode("root", "OBYBK RAG Inspection", "framework", 1.00, "RAG answers decomposed into claim, evidence, entity, relation, and review gates.", None, 0),
        OntologyMapNode("claim", "Claim Graph", "claim", 0.92, "답변을 검증 가능한 주장 단위로 분해합니다.", "root", 1),
        OntologyMapNode("evidence", "Evidence Graph", "evidence", 0.96, "검색 근거, 문서 출처, 후보군, provenance를 연결합니다.", "root", 1),
        OntologyMapNode("ontology", "Ontology Anchors", "entity", 0.88, "Business Model Ontology와 domain slice를 anchor로 사용합니다.", "root", 1),
        OntologyMapNode("review", "Review Gates", "review", 0.86, "사람 검토, 품질 guard, data gap을 명시합니다.", "root", 1),
        OntologyMapNode("store", "RAG Store", "store", 0.82, "Local JSONL/SQLite/PostgreSQL-pgvector 검색 저장소입니다.", "root", 1),
        OntologyMapNode("projection", "Reviewer Projection", "projection", 0.80, "Visual Inspector와 Obsidian wiki로 검토 화면을 만듭니다.", "root", 1),
        OntologyMapNode("answer_claim", "Answer Claim", "claim", 0.76, "사용자 질문에 대한 핵심 답변 주장", "claim", 2),
        OntologyMapNode("data_gap_claim", "Data Gap Claim", "claim", 0.64, "근거 부족/미확정 조건을 숨기지 않는 주장", "claim", 2),
        OntologyMapNode("answerability", "Answerability State", "claim", 0.66, "answered / insufficient-but-grounded 상태", "claim", 2),
        OntologyMapNode("indicator", "Quantitative Indicator", "claim", 0.58, "latency, score, count 등 측정값", "claim", 2),
        OntologyMapNode("excerpt", "Evidence Excerpt", "evidence", 0.82, "답변을 지지하는 짧은 근거 excerpt", "evidence", 2),
        OntologyMapNode("source_doc", "Source Document", "evidence", 0.78, "문서/데이터 파일/DB row 출처", "evidence", 2),
        OntologyMapNode("candidate_set", "Candidate Set", "evidence", 0.72, "검색된 후보 객체와 ranking", "evidence", 2),
        OntologyMapNode("provenance", "Provenance Trace", "evidence", 0.70, "어떤 근거가 어떤 claim을 지지했는지 추적", "evidence", 2),
        OntologyMapNode("bmo", "Business Model Ontology", "entity", 0.72, "Osterwalder BMO 기반 upper ontology anchor", "ontology", 2),
        OntologyMapNode("owl_blueprint", "OWL 2 DL Blueprint", "entity", 0.62, "문서화된 형식화 청사진; runtime reasoner는 아님", "ontology", 2),
        OntologyMapNode("domain_entity", "Domain Entity", "entity", 0.80, "Station, dataset, episode 같은 domain object", "ontology", 2),
        OntologyMapNode("relation_type", "Relation Type", "relation", 0.72, "supports, forStation, requiresReview 등 관계", "ontology", 2),
        OntologyMapNode("name_resolver", "Name Resolver", "entity", 0.54, "ST-152 같은 technical id를 사람이 읽는 이름으로 변환", "ontology", 2),
        OntologyMapNode("contract", "Contract Check", "review", 0.70, "응답 payload가 검사 계약을 통과했는지 확인", "review", 2),
        OntologyMapNode("human_review", "Human Review", "review", 0.78, "운영자가 판단해야 하는 항목을 분리", "review", 2),
        OntologyMapNode("quality_guard", "Quality Guard", "review", 0.68, "profile-specific guard와 failure reason", "review", 2),
        OntologyMapNode("action", "Recommended Action", "review", 0.66, "검토자가 다음에 할 수 있는 action", "review", 2),
        OntologyMapNode("jsonl", "Runtime JSONL", "store", 0.54, "local seed/runtime answer store", "store", 2),
        OntologyMapNode("sqlite", "SQLite RAG Store", "store", 0.58, "evaluation/snippet/review queue local DB", "store", 2),
        OntologyMapNode("pgvector", "PostgreSQL + pgvector", "store", 0.76, "live vector search adapter", "store", 2),
        OntologyMapNode("hybrid_profile", "DB-only vs Hybrid", "store", 0.66, "retrieval profile comparison", "store", 2),
        OntologyMapNode("visual", "Visual Inspector", "projection", 0.76, "single-answer evidence workspace", "projection", 2),
        OntologyMapNode("eval_overview", "Evaluation Overview", "projection", 0.72, "100-question coverage artifact", "projection", 2),
        OntologyMapNode("obsidian", "Obsidian Wiki", "projection", 0.74, "ontology-like markdown knowledge projection", "projection", 2),
        OntologyMapNode("review_queue", "Review Queue", "projection", 0.62, "review-required items for human inspection", "projection", 2),
        OntologyMapNode("station_152", "충무로역 3.4호선 ST-152", "domain", 0.62, "Seoul Bike case-study entity", "domain_entity", 3),
        OntologyMapNode("station_150", "종로3가역 2번출구 뒤 ST-150", "domain", 0.56, "candidate entity", "domain_entity", 3),
        OntologyMapNode("shortage", "Shortage Episode", "domain", 0.58, "운영 이상 징후 episode", "relation_type", 3),
        OntologyMapNode("weather", "Weather Context", "domain", 0.48, "날씨/시간 맥락 근거", "source_doc", 3),
        OntologyMapNode("rel_supports", "supportsEvidence", "relation", 0.50, "evidence가 claim을 지지", "relation_type", 3),
        OntologyMapNode("rel_review", "requiresReview", "relation", 0.54, "검토 gate와 연결", "relation_type", 3),
        OntologyMapNode("entity_note", "Entity Note", "projection", 0.52, "Obsidian entity page/backlink", "obsidian", 3),
        OntologyMapNode("run_note", "Run Note", "projection", 0.48, "평가 실행 단위 markdown note", "obsidian", 3),
    ]
    edges: list[OntologyMapEdge] = []
    for node in nodes:
        if node.parent_id:
            edges.append(OntologyMapEdge(node.parent_id, node.id, "parent-child", 0.72))
    edges.extend(
        [
            OntologyMapEdge("answer_claim", "excerpt", "supportedBy", 0.88),
            OntologyMapEdge("excerpt", "source_doc", "cites", 0.82),
            OntologyMapEdge("candidate_set", "domain_entity", "retrieves", 0.78),
            OntologyMapEdge("domain_entity", "relation_type", "participatesIn", 0.78),
            OntologyMapEdge("human_review", "data_gap_claim", "checks", 0.75),
            OntologyMapEdge("contract", "answer_claim", "validates", 0.75),
            OntologyMapEdge("quality_guard", "answerability", "guards", 0.72),
            OntologyMapEdge("pgvector", "candidate_set", "searches", 0.82),
            OntologyMapEdge("hybrid_profile", "eval_overview", "compares", 0.70),
            OntologyMapEdge("visual", "provenance", "renders", 0.74),
            OntologyMapEdge("obsidian", "entity_note", "projects", 0.76),
            OntologyMapEdge("review_queue", "human_review", "routes", 0.80),
            OntologyMapEdge("station_152", "shortage", "forEpisode", 0.66),
            OntologyMapEdge("weather", "data_gap_claim", "contextFor", 0.55),
            OntologyMapEdge("rel_supports", "excerpt", "labels", 0.62),
            OntologyMapEdge("rel_review", "human_review", "labels", 0.62),
        ]
    )
    payload_entity_nodes = _append_answer_payload_map(nodes, edges, answer_payload)
    return nodes, edges, payload_entity_nodes


def write_ontology_map_json(output: Path, nodes: list[OntologyMapNode], edges: list[OntologyMapEdge]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "kind": "nodeprompt_inspired_ontology_map",
                "title": "OBYBK Ontology-Hybrid Evidence Graph",
                "nodes": [asdict(node) for node in nodes],
                "edges": [asdict(edge) for edge in edges],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _load_font(size: int, *, mono: bool = False):
    from PIL import ImageFont

    candidates = [
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 6 if mono else 1),
        ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
    ]
    path, index = next((item for item in candidates if Path(item[0]).exists()), candidates[-1])
    try:
        return ImageFont.truetype(path, size, index=index)
    except TypeError:  # pragma: no cover
        return ImageFont.truetype(path, size)


def _wrap_text(draw: Any, text: str, font: Any, max_width: int) -> list[str]:
    lines: list[str] = []
    for raw_line in str(text).splitlines() or [""]:
        words = raw_line.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = current + " " + word
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    wrapped: list[str] = []
    for line in lines:
        if draw.textlength(line, font=font) <= max_width:
            wrapped.append(line)
        else:
            # CJK/no-space fallback.
            current = ""
            for ch in line:
                if draw.textlength(current + ch, font=font) <= max_width:
                    current += ch
                else:
                    wrapped.append(current)
                    current = ch
            if current:
                wrapped.append(current)
    return wrapped


def _draw_text_box(draw: Any, xy: tuple[int, int, int, int], title: str, body: Iterable[str], fonts: dict[str, Any]) -> None:
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=14, outline="#d6d6d6", width=2, fill="#ffffff")
    draw.text((x0 + 20, y0 + 18), title, font=fonts["panel_title"], fill="#111111")
    y = y0 + 58
    for line in body:
        if not line:
            y += 10
            continue
        for wrapped in _wrap_text(draw, line, fonts["panel"], x1 - x0 - 40):
            draw.text((x0 + 20, y), wrapped, font=fonts["panel"], fill="#3f3f46")
            y += 26
            if y > y1 - 28:
                return


def _curve_points(p0: tuple[float, float], p1: tuple[float, float], center: tuple[float, float], bend: float = 0.32) -> list[tuple[float, float]]:
    x0, y0 = p0
    x1, y1 = p1
    cx, cy = center
    c0 = (x0 + (cx - x0) * bend, y0 + (cy - y0) * bend)
    c1 = (x1 + (cx - x1) * bend, y1 + (cy - y1) * bend)
    pts = []
    for i in range(24):
        t = i / 23
        x = (1 - t) ** 3 * x0 + 3 * (1 - t) ** 2 * t * c0[0] + 3 * (1 - t) * t**2 * c1[0] + t**3 * x1
        y = (1 - t) ** 3 * y0 + 3 * (1 - t) ** 2 * t * c0[1] + 3 * (1 - t) * t**2 * c1[1] + t**3 * y1
        pts.append((x, y))
    return pts


def _node_positions(nodes: list[OntologyMapNode], size: tuple[int, int]) -> dict[str, tuple[float, float]]:
    width, height = size
    center = (width * 0.52, height * 0.50)
    first_order = [node for node in nodes if node.parent_id == "root"]
    angle_map = {
        "claim": -95,
        "evidence": -35,
        "ontology": 28,
        "review": 92,
        "store": 158,
        "projection": 220,
    }
    positions: dict[str, tuple[float, float]] = {"root": center}
    for node in first_order:
        angle = math.radians(angle_map.get(node.id, 0))
        radius = 168
        positions[node.id] = (center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius)
    children_by_parent: dict[str, list[OntologyMapNode]] = {}
    for node in nodes:
        if node.parent_id:
            children_by_parent.setdefault(node.parent_id, []).append(node)
    for parent in first_order:
        kids = [kid for kid in children_by_parent.get(parent.id, []) if kid.depth == 2]
        base = angle_map.get(parent.id, 0)
        spread = 46 if len(kids) > 3 else 32
        for index, kid in enumerate(kids):
            offset = 0 if len(kids) == 1 else -spread / 2 + spread * index / (len(kids) - 1)
            angle = math.radians(base + offset)
            radius = 355
            positions[kid.id] = (center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius)
    for parent_id, kids in children_by_parent.items():
        kids3 = [kid for kid in kids if kid.depth >= 3]
        if not kids3 or parent_id not in positions:
            continue
        px, py = positions[parent_id]
        base = math.degrees(math.atan2(py - center[1], px - center[0]))
        spread = 26 + len(kids3) * 4
        for index, kid in enumerate(kids3):
            offset = 0 if len(kids3) == 1 else -spread / 2 + spread * index / (len(kids3) - 1)
            angle = math.radians(base + offset)
            radius = 520
            positions[kid.id] = (center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius)
    return positions


def _draw_node(draw: Any, node: OntologyMapNode, position: tuple[float, float], center: tuple[float, float], fonts: dict[str, Any], selected_id: str) -> None:
    x, y = position
    style = TYPE_STYLES.get(node.type, TYPE_STYLES["entity"])
    radius = int(7 + node.weight * 16 - node.depth * 1.6)
    if node.id == "root":
        radius = 25
    if node.id == selected_id:
        draw.ellipse((x - radius - 8, y - radius - 8, x + radius + 8, y + radius + 8), outline="#111111", width=3, fill="#f5f5f5")
    if node.type == "relation":
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=style["outline"], width=3, fill="#ffffff")
        draw.line((x - radius * 0.6, y, x + radius * 0.6, y), fill="#111111", width=2)
    else:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=style["outline"], width=2, fill=style["fill"])
    if node.type == "evidence":
        for dx in range(-radius, radius + 1, 7):
            draw.line((x + dx - radius, y + radius, x + dx + radius, y - radius), fill="#e5e7eb", width=1)
    if node.type == "review":
        draw.line((x - radius * 0.55, y - radius * 0.55, x + radius * 0.55, y + radius * 0.55), fill="#7f1d1d", width=2)
        draw.line((x - radius * 0.55, y + radius * 0.55, x + radius * 0.55, y - radius * 0.55), fill="#7f1d1d", width=2)
    label_font = fonts["label_big"] if node.depth <= 1 else fonts["label"]
    label = node.label
    tw = draw.textlength(label, font=label_font)
    if node.id == "root":
        tx, ty = x - tw / 2, y + radius + 8
    else:
        tx = x + radius + 7 if x >= center[0] else x - radius - 7 - tw
        ty = y - 10
    # Soft white backing for labels.
    draw.rounded_rectangle((tx - 4, ty - 2, tx + tw + 4, ty + 22), radius=5, fill="#ffffff")
    draw.text((tx, ty), label, font=label_font, fill="#111111")


def write_nodeprompt_ontology_map_png(
    output: Path,
    *,
    graph_json: Path | None = None,
    answer_payload: dict[str, Any] | None = None,
    focused_entity: str | None = None,
) -> dict[str, Any]:
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Pillow is required to render the ontology map") from exc

    nodes, edges, payload_entity_nodes = build_obybk_ontology_map(answer_payload=answer_payload)
    if graph_json:
        write_ontology_map_json(graph_json, nodes, edges)

    width, height = 2400, 1350
    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    fonts = {
        "title": _load_font(28),
        "toolbar": _load_font(18),
        "panel_title": _load_font(20),
        "panel": _load_font(17),
        "panel_small": _load_font(15),
        "label_big": _load_font(17),
        "label": _load_font(15),
        "tiny": _load_font(13),
        "mono": _load_font(15, mono=True),
    }

    # Top-left quick buttons.
    draw.ellipse((22, 18, 62, 58), outline="#d4d4d8", width=2)
    draw.text((38, 25), "?", font=fonts["toolbar"], fill="#111111", anchor="la")
    draw.rounded_rectangle((74, 18, 122, 58), radius=22, outline="#d4d4d8", width=2, fill="#ffffff")
    draw.text((91, 28), "한", font=fonts["toolbar"], fill="#111111")

    # Top toolbar.
    bar = (760, 14, 1600, 58)
    draw.rounded_rectangle(bar, radius=14, outline="#d4d4d8", width=2, fill="#ffffff")
    toolbar = "● Radial   Home   |   40n · 55e   |   A ━●━━ A   |   Aa   |   Local RAG   |   Reset   |   Demo"
    draw.text((786, 26), toolbar, font=fonts["toolbar"], fill="#111111")
    draw.rounded_rectangle((1510, 22, 1578, 50), radius=7, fill="#050505")
    draw.text((1531, 27), "Demo", font=fonts["panel_small"], fill="#ffffff")

    # Legend.
    legend_x, legend_y = 2210, 18
    draw.rounded_rectangle((legend_x - 12, legend_y - 12, 2375, 176), radius=8, outline="#dcdcdc", fill="#ffffff")
    legend = [
        ("claim", "Claim"),
        ("evidence", "Evidence"),
        ("entity", "Entity"),
        ("relation", "Relation"),
        ("review", "Review Gate"),
        ("store", "Store"),
        ("projection", "Projection"),
    ]
    for i, (kind, label) in enumerate(legend):
        y = legend_y + i * 21
        style = TYPE_STYLES[kind]
        draw.ellipse((legend_x, y, legend_x + 13, y + 13), fill=style["fill"], outline=style["outline"], width=2)
        draw.text((legend_x + 23, y - 3), label, font=fonts["tiny"], fill="#111111")

    positions = _node_positions(nodes, (width, height))
    center = positions["root"]
    by_id = {node.id: node for node in nodes}

    # Faint guide arcs.
    for radius in (168, 355, 520):
        draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), outline="#f1f1f1", width=1)

    # Edges.
    for edge in edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        p0, p1 = positions[edge.source], positions[edge.target]
        is_cross = edge.relation != "parent-child"
        color = "#2f2f2f" if is_cross else "#b8b8b8"
        width_edge = max(1, int(1 + edge.strength * (2 if is_cross else 1)))
        pts = _curve_points(p0, p1, center, bend=0.18 if is_cross else 0.36)
        draw.line(pts, fill=color, width=width_edge)

    selected_id = payload_entity_nodes.get(str(focused_entity or "")) or (next(iter(payload_entity_nodes.values()), "evidence"))
    # Nodes.
    for node in sorted(nodes, key=lambda n: n.depth, reverse=True):
        _draw_node(draw, node, positions[node.id], center, fonts, selected_id)

    # Left inspector panel.
    _draw_text_box(
        draw,
        (22, 98, 392, 462),
        "× Evidence Graph   Provenance",
        [
            "RAG 답변을 근거 단위로 분해하고 claim과 source를 연결합니다.",
            "Weight 96%",
            "Connected (6)",
            "◦ Evidence Excerpt",
            "◦ Source Document",
            "◦ Candidate Set",
            "◦ Provenance Trace",
            "◦ Visual Inspector",
            "◦ Claim Graph",
        ],
        fonts,
    )

    # Prompt panel.
    _draw_text_box(
        draw,
        (22, 936, 530, 1296),
        "PROMPT",
        [
            "질문: 오늘 운영자가 먼저 확인해야 할 이상 징후는 무엇인가?",
            "분해 기준:",
            "- claim / evidence / entity / relation / review gate",
            "- DB-only vs Ontology-Hybrid 비교",
            "- Obsidian projection까지 export",
            "",
            "Depth D:3     Nodes N:40     Branch:6",
        ],
        fonts,
    )
    draw.rounded_rectangle((44, 1241, 508, 1282), radius=8, fill="#050505")
    draw.text((214, 1252), "Analyze Ontology", font=fonts["panel"], fill="#ffffff")

    # Right inspector/editor panel.
    _draw_text_box(
        draw,
        (2038, 244, 2378, 718),
        "× Evidence Graph",
        [
            "Description",
            "검색된 문서, 후보 객체, 근거 excerpt, provenance trace를 하나의 inspection graph로 묶습니다.",
            "Weight — 96%",
            "Type",
            "● Evidence   ○ Claim",
            "○ Entity     ○ Relation",
            "○ Review Gate",
            "Actions",
            "Delete     Connect Edge",
        ],
        fonts,
    )

    # Response panel.
    _draw_text_box(
        draw,
        (1760, 1070, 2378, 1298),
        "RESPONSE",
        [
            "Generated Ontology-Hybrid Evidence Graph",
            f"Nodes: {len(nodes)} / Edges: {len(edges)} / Answer entities: {len(payload_entity_nodes)}",
            "Core path: Question → Claim → Evidence → Entity → Review Gate",
            "Public scope: ontology-like runtime inspection; full OWL reasoner is not claimed.",
        ],
        fonts,
    )
    draw.rounded_rectangle((1784, 1242, 2354, 1284), radius=8, fill="#050505")
    draw.text((2000, 1253), "Export Graph", font=fonts["panel"], fill="#ffffff")

    # Subtle attribution note, not a dependency claim.
    draw.text(
        (860, 1312),
        "NODEPROMPT-inspired radial interaction style · OBYBK-owned static ontology visualization artifact",
        font=fonts["tiny"],
        fill="#8a8a8a",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return {
        "output": str(output),
        "graph_json": str(graph_json) if graph_json else "",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "entity_node_count": len(payload_entity_nodes),
        "focused_entity": focused_entity or "",
        "kind": "nodeprompt_inspired_ontology_map",
    }


def write_preview_crop(source: Path, output: Path) -> None:
    from PIL import Image

    image = Image.open(source).convert("RGB")
    # Crop tightly around the radial graph so the clickable HTML keeps the graphic prominent
    # while the right-hand panel shows the selected entity card.
    crop = image.crop((520, 85, 2220, 1245))
    output.parent.mkdir(parents=True, exist_ok=True)
    crop.save(output, quality=92, optimize=True)


def _draw_curve(draw: Any, p0: tuple[float, float], p1: tuple[float, float], *, color: str = "#9ca3af", width: int = 2) -> None:
    cx = (p0[0] + p1[0]) / 2
    c0 = (cx, p0[1])
    c1 = (cx, p1[1])
    pts: list[tuple[float, float]] = []
    for i in range(32):
        t = i / 31
        x = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * c0[0] + 3 * (1 - t) * t**2 * c1[0] + t**3 * p1[0]
        y = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * c0[1] + 3 * (1 - t) * t**2 * c1[1] + t**3 * p1[1]
        pts.append((x, y))
    draw.line(pts, fill=color, width=width)


def _node_style_for_tree(kind: str) -> tuple[str, str]:
    style = TYPE_STYLES.get(kind, TYPE_STYLES["entity"])
    return style["fill"], style["outline"]


def _draw_tree_node(
    draw: Any,
    xy: tuple[float, float],
    label: str,
    kind: str,
    fonts: dict[str, Any],
    *,
    selected: bool = False,
    radius: int = 16,
    label_side: str = "right",
) -> None:
    x, y = xy
    fill, outline = _node_style_for_tree(kind)
    if selected:
        draw.ellipse((x - radius - 8, y - radius - 8, x + radius + 8, y + radius + 8), outline="#111111", width=4, fill="#fef08a")
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline=outline, width=3)
    if kind == "relation":
        draw.line((x - radius * 0.55, y, x + radius * 0.55, y), fill="#111111", width=2)
    if kind == "review":
        draw.line((x - radius * 0.48, y - radius * 0.48, x + radius * 0.48, y + radius * 0.48), fill="#7f1d1d", width=2)
        draw.line((x - radius * 0.48, y + radius * 0.48, x + radius * 0.48, y - radius * 0.48), fill="#7f1d1d", width=2)
    font = fonts["label_big"] if radius >= 17 else fonts["label"]
    lines = _wrap_text(draw, label, font, 270)
    if label_side == "left":
        max_w = max(draw.textlength(line, font=font) for line in lines)
        tx = x - radius - 12 - max_w
    else:
        tx = x + radius + 12
    ty = y - len(lines) * 12
    for line in lines[:2]:
        draw.text((tx, ty), line, font=font, fill="#111111")
        ty += 24


def _tree_relation_labels(answer_payload: dict[str, Any] | None) -> list[str]:
    if not answer_payload:
        return ["supportsEvidence", "forEntity", "requiresReview"]
    labels: list[str] = []
    for row in answer_payload.get("related_relations") or []:
        if not isinstance(row, dict):
            continue
        raw = str(row.get("relation") or row.get("type") or "relation")
        label = raw if raw else "relation"
        if label not in labels:
            labels.append(label)
    return labels[:5] or ["supportsEvidence", "forEntity", "requiresReview"]


def write_nodeprompt_ontology_tree_png(
    output: Path,
    *,
    answer_payload: dict[str, Any] | None = None,
    focused_entity: str | None = None,
) -> dict[str, Any]:
    """Render a NODEPROMPT-like ontology tree focused on one RAG answer."""
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Pillow is required to render the ontology tree") from exc

    width, height = 1800, 1060
    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    fonts = {
        "title": _load_font(30),
        "toolbar": _load_font(18),
        "panel_title": _load_font(22),
        "panel": _load_font(18),
        "label_big": _load_font(19),
        "label": _load_font(17),
        "tiny": _load_font(14),
    }

    # Minimal NODEPROMPT-style chrome.
    draw.rounded_rectangle((520, 18, 1280, 62), radius=14, outline="#d4d4d8", width=2, fill="#ffffff")
    draw.text((548, 30), "● Radial Tree   Home   |   Claim · Evidence · Entity · Review   |   Local RAG   |   Demo", font=fonts["toolbar"], fill="#111111")
    draw.text((34, 30), "?", font=fonts["toolbar"], fill="#111111")
    draw.rounded_rectangle((62, 18, 112, 58), radius=20, outline="#d4d4d8", width=2, fill="#ffffff")
    draw.text((80, 29), "한", font=fonts["toolbar"], fill="#111111")

    question = str((answer_payload or {}).get("question") or (answer_payload or {}).get("input_question") or "오늘 먼저 확인해야 할 대여소는?")
    answer = " ".join(str((answer_payload or {}).get("answer") or "").split())[:190]
    _draw_text_box(
        draw,
        (28, 112, 390, 354),
        "× RAG Answer Tree",
        [
            "질의 답변을 ontology tree로 분해합니다.",
            f"Question: {question}",
            "Connected branches:",
            "◦ Claim",
            "◦ Evidence",
            "◦ Entity",
            "◦ Relation",
            "◦ Review Gate",
        ],
        fonts,
    )
    _draw_text_box(
        draw,
        (28, 782, 470, 1018),
        "ANSWER",
        [answer or "답변 excerpt가 여기에 표시됩니다.", "", "Entity label을 클릭하면 오른쪽 card로 이동합니다."],
        fonts,
    )

    entities = _payload_entities(answer_payload)
    entity_leaves: list[tuple[str, str, str]] = []
    for raw in entities[:4]:
        entity_id = _payload_entity_id(raw)
        entity_leaves.append((entity_id, _payload_entity_label(raw), "domain"))
    if not entity_leaves:
        entity_leaves = [("station_152", "충무로역 3.4호선 ST-152", "domain"), ("station_150", "종로3가역 2번출구 뒤 ST-150", "domain")]

    relation_leaves = [(f"rel_{i}", label, "relation") for i, label in enumerate(_tree_relation_labels(answer_payload), start=1)]
    branches: list[tuple[str, str, str, list[tuple[str, str, str]]]] = [
        ("claim", "Claim", "claim", [("answer_claim", "Answer Claim", "claim"), ("gap", "Data Gap Claim", "claim"), ("answerability", "Answerability", "claim")]),
        ("evidence", "Evidence", "evidence", [("excerpt", "Evidence Excerpt", "evidence"), ("source", "Source Document", "evidence"), ("candidate", "Candidate Set", "evidence")]),
        ("entity", "Entity", "entity", entity_leaves),
        ("relation", "Relation", "relation", relation_leaves),
        ("review", "Review Gate", "review", [("human", "Human Review", "review"), ("action", "Recommended Action", "review"), ("contract", "Contract Check", "review")]),
    ]

    root = (560, 545)
    _draw_tree_node(draw, root, "RAG Answer", "framework", fonts, radius=28)
    branch_x = 880
    leaf_x = 1245
    y_positions = [205, 375, 545, 715, 885]
    focused = str(focused_entity or "").strip().lower()
    selected_label = ""
    node_count = 1
    edge_count = 0
    for (branch_id, branch_label, branch_kind, leaves), by in zip(branches, y_positions):
        branch_pos = (branch_x, by)
        _draw_curve(draw, root, branch_pos, color="#9ca3af", width=3)
        edge_count += 1
        _draw_tree_node(draw, branch_pos, branch_label, branch_kind, fonts, radius=22)
        node_count += 1
        if len(leaves) == 1:
            leaf_ys = [by]
        else:
            gap = min(58, 130 / max(1, len(leaves) - 1))
            start = by - gap * (len(leaves) - 1) / 2
            leaf_ys = [start + i * gap for i in range(len(leaves))]
        for (leaf_id, leaf_label, leaf_kind), ly in zip(leaves, leaf_ys):
            leaf_pos = (leaf_x, ly)
            _draw_curve(draw, branch_pos, leaf_pos, color="#2f2f2f" if branch_id in {"entity", "relation"} else "#c4c4c4", width=3 if branch_id == "entity" else 2)
            edge_count += 1
            is_selected = bool(focused and (focused in leaf_id.lower() or focused in leaf_label.lower()))
            if is_selected:
                selected_label = leaf_label
            _draw_tree_node(draw, leaf_pos, leaf_label, leaf_kind, fonts, selected=is_selected, radius=17)
            node_count += 1

    # Right inspector card for selected entity / tree semantics.
    selected_label = selected_label or (entity_leaves[0][1] if entity_leaves else "Entity")
    _draw_text_box(
        draw,
        (1382, 214, 1768, 612),
        "× Selected Entity",
        [
            selected_label,
            "Type: Entity / Domain object",
            "Linked from answer mention",
            "Relations are shown as branch leaves.",
            "Review gate remains explicit.",
        ],
        fonts,
    )
    _draw_text_box(
        draw,
        (1382, 678, 1768, 928),
        "TREE CONTRACT",
        [
            "Question → Claim",
            "Claim → Evidence",
            "Evidence → Entity",
            "Entity → Relation",
            "Relation → Review Gate",
        ],
        fonts,
    )

    legend_x, legend_y = 1510, 24
    draw.rounded_rectangle((legend_x - 20, legend_y - 12, 1768, 170), radius=8, outline="#dcdcdc", fill="#ffffff")
    for i, (kind, label) in enumerate([("claim", "Claim"), ("evidence", "Evidence"), ("entity", "Entity"), ("relation", "Relation"), ("review", "Review Gate")]):
        y = legend_y + i * 26
        fill, outline = _node_style_for_tree(kind)
        draw.ellipse((legend_x, y, legend_x + 15, y + 15), fill=fill, outline=outline, width=2)
        draw.text((legend_x + 24, y - 3), label, font=fonts["tiny"], fill="#111111")

    draw.text((650, 1030), "NODEPROMPT-inspired ontology tree · answer-level claim/evidence/entity/relation/review projection", font=fonts["tiny"], fill="#8a8a8a")

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return {"output": str(output), "node_count": node_count, "edge_count": edge_count, "focused_entity": focused_entity or ""}


def write_tree_focus_crop(source: Path, output: Path) -> None:
    from PIL import Image

    image = Image.open(source).convert("RGB")
    # Keep the branching ontology tree itself large in the clickable HTML.
    crop = image.crop((360, 110, 1680, 970))
    output.parent.mkdir(parents=True, exist_ok=True)
    crop.save(output, quality=94, optimize=True)
