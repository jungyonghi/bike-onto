# Timestamp: 2026-05-19 14:06:00

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
from typing import Any

CATEGORY_TAGS = {
    "운영 모니터링": "operation-monitoring",
    "장애/품질": "fault-quality",
    "수요/이용량 분석": "demand-usage",
    "추천/재배치/우선순위": "reallocation-priority",
    "데이터/스키마/근거": "data-schema-evidence",
    "평가/검증": "evaluation-validation",
    "보안/권한/운영통제": "security-governance",
    "서비스/PM/보고": "service-pm-reporting",
    "API/DB/성능": "api-db-performance",
    "API/성능": "api-db-performance",
    "ML/예측/확장": "ml-prediction-extension",
}
RELATION_TAGS = {
    "hasEvidence": "has-evidence",
    "forStation": "for-station",
    "inTimeBucket": "in-time-bucket",
    "affectedByWeather": "affected-by-weather",
    "requiresReview": "requires-review",
    "approvedBy": "approved-by",
    "usesDataset": "uses-dataset",
}
DOMAIN_TO_UPPER = {
    "Station": ["Place"],
    "Place": ["Place"],
    "UsageMetric": ["Metric"],
    "Metric": ["Metric"],
    "WeatherObservation": ["Event"],
    "TimeBucket": ["Time"],
    "Dataset": ["Evidence"],
    "EvidenceDocument": ["Evidence"],
    "ReallocationRecommendation": ["Event", "ReviewGate"],
    "ReviewGate": ["ReviewGate"],
    "Question": ["Event"],
}


@dataclass(frozen=True)
class WikiExportResult:
    vault: Path
    run_note: Path
    index_note: Path
    review_queue_note: Path
    question_notes: list[Path]
    entity_notes: list[Path]
    concept_notes: list[Path]
    relation_notes: list[Path]
    asset_paths: list[Path]
    obsidian_uri: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "vault": str(self.vault),
            "run_note": str(self.run_note),
            "index_note": str(self.index_note),
            "review_queue_note": str(self.review_queue_note),
            "question_notes": len(self.question_notes),
            "entity_notes": len(self.entity_notes),
            "concept_notes": len(self.concept_notes),
            "relation_notes": len(self.relation_notes),
            "asset_count": len(self.asset_paths),
            "obsidian_uri": self.obsidian_uri,
        }


def _short(value: Any, limit: int = 110) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def _slug(value: Any, *, separator: str = "_") -> str:
    text = str(value or "note").strip()
    text = re.sub(r"[\\/:*?\"<>|]+", separator, text)
    text = re.sub(r"\s+", separator, text)
    text = re.sub(rf"{re.escape(separator)}+", separator, text)
    return text.strip(separator) or "note"


def _note_title(value: Any) -> str:
    text = str(value or "Untitled").strip()
    text = re.sub(r"[\\/:*?\"<>|]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip() or "Untitled"


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value or "")
    if not text:
        return '""'
    if re.match(r"^[A-Za-z0-9_.:-]+$", text) and text.lower() not in {"true", "false", "null"}:
        return text
    escaped = text.replace('"', '\\"')
    return f'"{escaped}"'


def _frontmatter(values: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in values.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
                continue
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_yaml_scalar(item)}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for child_key, child_value in value.items():
                lines.append(f"  {child_key}: {_yaml_scalar(child_value)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _category_tag(category: str) -> str:
    return CATEGORY_TAGS.get(category, _slug(category, separator="-").lower())


def _relation_tag(relation: str) -> str:
    return RELATION_TAGS.get(relation, re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", relation).replace("_", "-").lower())


def _question_id(row: dict[str, Any], index: int) -> str:
    return str(row.get("id") or row.get("question_id") or f"Q-{index:03d}")


def _station_number(value: str) -> str:
    station_match = re.search(r"station:0*(\d+)", value, flags=re.I)
    st_match = re.search(r"ST-0*(\d+)", value, flags=re.I)
    number = station_match.group(1) if station_match else st_match.group(1) if st_match else ""
    return number


def _canonical_station_id(value: str) -> str:
    number = _station_number(value)
    return f"ST-{int(number)}" if number else value


def _display_without_parenthesized_id(label: str) -> str:
    return re.sub(r"\s*\((?:ST-\d+|station:\d+)\)\s*$", "", label).strip()


def _extract_entity_from_graph_node(node: dict[str, Any]) -> dict[str, Any] | None:
    if node.get("type") != "entity":
        return None
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    raw_id = str(metadata.get("id") or node.get("id") or "").strip()
    label = str(node.get("label") or raw_id).strip()
    entity_type = str(metadata.get("type") or "Entity")
    canonical_id = _canonical_station_id(raw_id or label)
    display = _display_without_parenthesized_id(label)
    title = f"{display} {canonical_id}" if canonical_id and canonical_id not in display else display
    aliases = _unique([raw_id, canonical_id, label])
    if not title:
        return None
    if raw_id.lower().startswith("station:") or canonical_id.startswith("ST-") or entity_type.lower() == "station":
        entity_type = "Station"
    return {"id": canonical_id or raw_id or title, "raw_id": raw_id, "title": _note_title(title), "display_name": display or title, "type": entity_type, "aliases": aliases}


def _entity_map_from_graph(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for node in graph.get("nodes", []) or []:
        entity = _extract_entity_from_graph_node(node)
        if not entity:
            continue
        for alias in entity["aliases"] + [entity["id"], entity["title"]]:
            if alias:
                mapping[str(alias).lower()] = entity
    return mapping


def _register_entity(mapping: dict[str, dict[str, Any]], entity: dict[str, Any]) -> None:
    for alias in entity["aliases"] + [entity["id"], entity["title"], entity.get("display_name", "")]:
        if alias:
            mapping[str(alias).lower()] = entity


def _clean_station_display_label(value: str) -> str:
    text = " ".join(str(value or "").split()).strip(" -–—:：,;|()[]{}\"'“”‘’")
    text = re.sub(r"^(?:와|과|및|또는|그리고|/)+\s*", "", text)
    text = re.sub(r"^(?:현재\s*)?(?:context의\s*)?(?:후보\s*목록은|후보군은|후보는|대상은|예시로|예|대상|후보|대여소|점검\s*대상|\d+순위)\s*", "", text)
    text = text.strip(" -–—:：,;|()[]{}\"'“”‘’")
    return text


def _entity_map_from_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    pattern = re.compile(r"([^\n\|,;]{1,80}?)\s*\((ST-\d+)\)")
    for row in rows:
        text = "\n".join([str(row.get("question") or ""), str(row.get("answer") or "")])
        for match in pattern.finditer(text):
            display = _clean_station_display_label(match.group(1))
            canonical_id = match.group(2)
            if not display or display.upper().startswith("ST-") or canonical_id in display:
                continue
            title = _note_title(f"{display} {canonical_id}")
            entity = {
                "id": canonical_id,
                "raw_id": canonical_id,
                "title": title,
                "display_name": display,
                "type": "Station",
                "aliases": _unique([canonical_id, canonical_id.replace("ST-", "station:"), display, title]),
            }
            _register_entity(mapping, entity)
    return mapping


def _merge_entity_maps(base: dict[str, dict[str, Any]], preferred: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    merged = dict(base)
    for entity in preferred.values():
        _register_entity(merged, entity)
    return merged


def _relation_names_from_graph(graph: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for node in graph.get("nodes", []) or []:
        if node.get("type") == "relation":
            metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
            relation = str(metadata.get("relation") or node.get("label") or "").strip()
            if relation:
                names.append(relation)
    for edge in graph.get("edges", []) or []:
        relation = str(edge.get("label") or edge.get("relationType") or "").strip()
        if relation:
            names.append(relation)
    return _unique(names)


def _entities_for_row(row: dict[str, Any], entity_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[tuple[str, str]] = []
    for candidate in row.get("first_candidates") or row.get("candidate_set") or []:
        if isinstance(candidate, dict):
            candidate_id = str(candidate.get("candidate_id") or candidate.get("id") or candidate.get("entity_id") or "")
            candidate_label = str(
                candidate.get("display_name")
                or candidate.get("station_name")
                or candidate.get("place_name")
                or candidate.get("name")
                or candidate.get("label")
                or candidate.get("title")
                or ""
            )
            candidates.append((candidate_id, candidate_label))
        else:
            candidates.append((str(candidate), ""))
    for value in row.get("top_ids") or []:
        candidates.append((str(value), ""))
    text = " ".join([str(row.get("question") or ""), str(row.get("answer") or "")])
    candidates.extend((value, "") for value in re.findall(r"station:0*\d+|ST-0*\d+", text, flags=re.I))
    entities: list[dict[str, Any]] = []
    for candidate, candidate_label in candidates:
        if not candidate:
            continue
        entity = entity_map.get(candidate.lower()) or entity_map.get(_canonical_station_id(candidate).lower())
        if not entity and candidate_label and (_station_number(candidate) or candidate.upper().startswith("ST-")):
            canonical_id = _canonical_station_id(candidate)
            display = _display_without_parenthesized_id(candidate_label)
            title = _note_title(f"{display} {canonical_id}") if display and canonical_id not in display else _note_title(display or canonical_id)
            entity = {
                "id": canonical_id,
                "raw_id": candidate,
                "title": title,
                "display_name": display or title,
                "type": "Station",
                "aliases": _unique([candidate, canonical_id, candidate_label, title]),
            }
        if not entity and (_station_number(candidate) or candidate.upper().startswith("ST-")):
            canonical_id = _canonical_station_id(candidate)
            title = canonical_id
            entity = {"id": canonical_id, "raw_id": candidate, "title": title, "display_name": title, "type": "Station", "aliases": _unique([candidate, canonical_id])}
        if entity and entity["id"] not in [item["id"] for item in entities]:
            entities.append(entity)
    return entities


def _domain_concepts(row: dict[str, Any], entities: list[dict[str, Any]]) -> list[str]:
    text = " ".join([str(row.get("category") or ""), str(row.get("question") or ""), str(row.get("answer") or "")]).lower()
    concepts = ["Question"]
    if any(entity.get("type") == "Station" for entity in entities) or "대여소" in text or "station" in text:
        concepts.append("Station")
    if "이용량" in text or "usage" in text or "metric" in text:
        concepts.append("UsageMetric")
    if "재배치" in text or "추천" in text or "reallocation" in text:
        concepts.append("ReallocationRecommendation")
    if "날씨" in text or "weather" in text:
        concepts.append("WeatherObservation")
    if row.get("requires_review"):
        concepts.append("ReviewGate")
    if "api" in text or "db" in text or "성능" in text:
        concepts.append("Metric")
    return _unique(concepts)


def _upper_concepts(domain_concepts: list[str]) -> list[str]:
    values: list[str] = []
    for concept in domain_concepts:
        values.extend(DOMAIN_TO_UPPER.get(concept, []))
    return _unique(values)


def _relation_names(row: dict[str, Any], entities: list[dict[str, Any]], graph_relations: list[str]) -> list[str]:
    text = " ".join([str(row.get("question") or ""), str(row.get("answer") or ""), str(row.get("category") or "")]).lower()
    relations: list[str] = []
    if entities:
        relations.append("forStation")
    if row.get("evidence_excerpt_count") or row.get("evidence_documents") or "근거" in text:
        relations.append("hasEvidence")
    if "날씨" in text or "weather" in text:
        relations.append("affectedByWeather")
    if row.get("requires_review"):
        relations.append("requiresReview")
    relations.extend([relation for relation in graph_relations if relation in RELATION_TAGS or re.match(r"[a-z]+[A-Z]", relation)])
    return _unique(relations)


def _tags_for_row(row: dict[str, Any], entities: list[dict[str, Any]], domain_concepts: list[str], relations: list[str]) -> list[str]:
    category = str(row.get("category") or "미분류")
    tags = ["#obybk", "#rag/question", f"#rag/eval/category/{_category_tag(category)}"]
    tags.append("#rag/eval/contract-pass" if row.get("contract_pass") else "#rag/eval/contract-fail")
    if row.get("requires_review"):
        tags.extend(["#review/needed", "#sim/risk/review-needed"])
    if int(row.get("data_gap_count") or 0) > 0:
        tags.append("#sim/risk/data-gap")
    for concept in domain_concepts:
        tags.append(f"#ontology/domain/{_relation_tag(concept)}")
    for concept in _upper_concepts(domain_concepts):
        tags.append(f"#ontology/upper/{_relation_tag(concept)}")
    for entity in entities:
        if entity.get("type") == "Station":
            tags.extend(["#sim/location/station", f"#entity/station/{entity['id']}"])
    for relation in relations:
        tags.append(f"#relation/{_relation_tag(relation)}")
    text = f"{category} {row.get('question', '')} {row.get('answer', '')}"
    if "운영" in text or "모니터링" in text:
        tags.append("#sim/question/monitoring")
    if "재배치" in text or "추천" in text:
        tags.append("#sim/operation/reallocation")
    if "성능" in text or "API" in text or "DB" in text:
        tags.append("#sim/question/performance")
    return _unique(tags)


def _entity_dir(entity: dict[str, Any]) -> str:
    return "stations" if entity.get("type") == "Station" else "places" if entity.get("type") == "Place" else "datasets" if entity.get("type") == "Dataset" else "objects"


def _question_note_path(vault: Path, row: dict[str, Any], index: int) -> Path:
    qid = _question_id(row, index)
    return vault / "02_Evaluation" / "questions" / f"{_slug(qid)}_{_slug(_short(row.get('question'), 36))}.md"


def _entity_note_path(vault: Path, entity: dict[str, Any]) -> Path:
    return vault / "04_Entities" / _entity_dir(entity) / f"{_note_title(entity['title'])}.md"


def _obsidian_uri(vault: Path, note: Path) -> str:
    vault_name = vault.name
    rel = note.relative_to(vault).with_suffix("").as_posix()
    return f"obsidian://open?vault={vault_name}&file={rel}"


def export_ontology_wiki(
    *,
    rows: list[dict[str, Any]],
    vault: Path | str,
    run_id: str,
    graph: dict[str, Any] | None = None,
    screenshot_paths: list[Path | str] | None = None,
    cloud_manifest_url: str = "",
    dashboard_url: str = "",
) -> WikiExportResult:
    vault_path = Path(vault)
    graph = graph or {}
    screenshot_paths = screenshot_paths or []
    entity_map = _merge_entity_maps(_entity_map_from_graph(graph), _entity_map_from_rows(rows))
    graph_relations = _relation_names_from_graph(graph)
    run_mode_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    review_rows: list[tuple[int, dict[str, Any]]] = []
    question_notes: list[Path] = []
    entity_usage: dict[str, dict[str, Any]] = {}
    relation_usage: dict[str, list[str]] = {}
    concept_usage: dict[str, list[str]] = {}

    for index, row in enumerate(rows, start=1):
        run_mode = str(row.get("llm_mode") or "unknown")
        category = str(row.get("category") or "미분류")
        run_mode_counts[run_mode] = run_mode_counts.get(run_mode, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
        if row.get("requires_review") or not row.get("contract_pass") or row.get("quality_guard_notes") or int(row.get("data_gap_count") or 0) > 0:
            review_rows.append((index, row))

    asset_paths: list[Path] = []
    for source in screenshot_paths:
        source_path = Path(source)
        if not source_path.exists():
            continue
        target = vault_path / "99_Assets" / "screenshots" / source_path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        asset_paths.append(target)

    run_note = vault_path / "01_Runs" / f"{_slug(run_id)}.md"
    review_queue_note = vault_path / "03_Review_Queue" / f"review_queue_{_slug(run_id)}.md"
    index_note = vault_path / "00_Index.md"

    run_tags = ["#obybk", "#rag/run"]
    for mode in run_mode_counts:
        run_tags.append(f"#rag/run/{_relation_tag(mode)}")
    run_tags.append("#review/has-items" if review_rows else "#review/none")
    contract_pass_count = sum(1 for row in rows if row.get("contract_pass"))

    run_body = _frontmatter(
        {
            "type": "rag_run",
            "run_id": run_id,
            "project": "OBYBK",
            "question_count": len(rows),
            "contract_pass_count": contract_pass_count,
            "review_count": len(review_rows),
            "llm_mode_counts": json.dumps(run_mode_counts, ensure_ascii=False),
            "cloud_manifest_url": cloud_manifest_url,
            "dashboard_url": dashboard_url,
            "tags": run_tags,
        }
    )
    run_body += f"# {run_id}\n\n"
    run_body += "## Summary\n"
    run_body += f"- Question Count: `{len(rows)}`\n- Contract Pass: `{contract_pass_count}/{len(rows)}`\n- Review Queue: `[[{review_queue_note.stem}]]`\n"
    run_body += "- Tags: " + " ".join(run_tags) + "\n\n"
    if asset_paths:
        run_body += "## Screenshots\n" + "\n".join(f"- ![[{path.name}]]" for path in asset_paths) + "\n\n"
    run_body += "## Category Counts\n" + "\n".join(f"- {category}: {count}" for category, count in category_counts.items()) + "\n"
    _write(run_note, run_body)

    question_note_by_id: dict[str, Path] = {}
    question_row_by_id: dict[str, dict[str, Any]] = {}
    question_entities: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(rows, start=1):
        qid = _question_id(row, index)
        question_row_by_id[qid] = row
        entities = _entities_for_row(row, entity_map)
        question_entities[qid] = entities
        for entity in entities:
            entity_usage.setdefault(entity["id"], {**entity, "questions": []})
            entity_usage[entity["id"]]["questions"].append(qid)
        domains = _domain_concepts(row, entities)
        uppers = _upper_concepts(domains)
        relations = _relation_names(row, entities, graph_relations)
        for relation in relations:
            relation_usage.setdefault(relation, []).append(qid)
        for concept in domains + uppers:
            concept_usage.setdefault(concept, []).append(qid)
        tags = _tags_for_row(row, entities, domains, relations)
        note_path = _question_note_path(vault_path, row, index)
        question_note_by_id[qid] = note_path
        entity_links = [f"[[{entity['title']}]]" for entity in entities]
        relation_links = [f"[[{relation}]]" for relation in relations]
        concept_links = [f"[[{concept}]]" for concept in domains]
        content = _frontmatter(
            {
                "type": "evaluation_question",
                "run_id": run_id,
                "question_id": qid,
                "category": row.get("category") or "미분류",
                "contract_pass": bool(row.get("contract_pass")),
                "requires_review": bool(row.get("requires_review")),
                "llm_mode": row.get("llm_mode") or "unknown",
                "data_gap_count": int(row.get("data_gap_count") or 0),
                "quality_guard_notes": row.get("quality_guard_notes") or [],
                "ontology_type": "Question",
                "upper_concepts": uppers,
                "domain_concepts": domains,
                "entity_ids": [entity["id"] for entity in entities],
                "relations": relations,
                "tags": tags,
            }
        )
        content += f"# {qid} {_short(row.get('question'), 80)}\n\n"
        content += "Tags: " + " ".join(tags) + "\n\n"
        content += f"## Run\n- [[{run_note.stem}]]\n\n"
        content += "## Ontology Links\n"
        content += "- Concepts: " + (", ".join(concept_links) if concept_links else "(none)") + "\n"
        content += "- Entities: " + (", ".join(entity_links) if entity_links else "(none)") + "\n"
        content += "- Relations: " + (", ".join(relation_links) if relation_links else "(none)") + "\n\n"
        content += f"## Question\n{row.get('question') or ''}\n\n"
        if row.get("answer"):
            content += f"## Answer\n{row.get('answer')}\n\n"
        content += "## Review Signals\n"
        content += f"- contract_pass: `{bool(row.get('contract_pass'))}`\n- requires_review: `{bool(row.get('requires_review'))}`\n- data_gap_count: `{int(row.get('data_gap_count') or 0)}`\n- quality_guard_notes: `{row.get('quality_guard_notes') or []}`\n"
        question_notes.append(_write(note_path, content))

    review_tags = ["#obybk", "#review/queue", "#rag/eval/review-queue"]
    review_body = _frontmatter({"type": "review_queue", "run_id": run_id, "review_count": len(review_rows), "tags": review_tags})
    review_body += f"# Review Queue {run_id}\n\nTags: {' '.join(review_tags)}\n\n"
    if not review_rows:
        review_body += "검토 필요 항목이 없습니다.\n"
    for index, row in review_rows:
        qid = _question_id(row, index)
        note_path = question_note_by_id.get(qid)
        link = f"[[{note_path.stem}]]" if note_path else qid
        review_body += f"## {link}\n"
        review_body += f"- Category: `{row.get('category') or '미분류'}`\n- contract_pass: `{bool(row.get('contract_pass'))}`\n- requires_review: `{bool(row.get('requires_review'))}`\n- data_gap_count: `{int(row.get('data_gap_count') or 0)}`\n- quality_guard_notes: `{row.get('quality_guard_notes') or []}`\n\n"
    _write(review_queue_note, review_body)

    entity_notes: list[Path] = []
    for entity in entity_usage.values():
        tags = ["#obybk", f"#ontology/domain/{_relation_tag(entity.get('type') or 'Entity')}"]
        if entity.get("type") == "Station":
            tags.extend([f"#entity/station/{entity['id']}", "#ontology/upper/place", "#sim/location/station"])
        content = _frontmatter(
            {
                "type": "entity",
                "entity_id": entity["id"],
                "display_name": entity.get("display_name") or entity["title"],
                "ontology_type": entity.get("type") or "Entity",
                "upper_concepts": DOMAIN_TO_UPPER.get(entity.get("type") or "Entity", []),
                "domain_concepts": [entity.get("type") or "Entity"],
                "aliases": entity.get("aliases") or [],
                "related_runs": [run_id],
                "related_questions": entity.get("questions") or [],
                "tags": _unique(tags),
            }
        )
        content += f"# {entity['title']}\n\nTags: {' '.join(_unique(tags))}\n\n"
        content += "## Appears In\n" + "\n".join(f"- [[{question_note_by_id[qid].stem}]]" for qid in entity.get("questions", []) if qid in question_note_by_id) + "\n"
        entity_notes.append(_write(_entity_note_path(vault_path, entity), content))

    concept_notes: list[Path] = []
    for concept, qids in sorted(concept_usage.items()):
        folder = "upper" if concept in {"Place", "Time", "Event", "Metric", "Evidence", "ReviewGate"} else "domain"
        tags = ["#obybk", f"#ontology/{folder}/{_relation_tag(concept)}"]
        content = _frontmatter({"type": "ontology_concept", "concept": concept, "concept_layer": folder, "related_questions": _unique(qids), "tags": tags})
        content += f"# {concept}\n\nTags: {' '.join(tags)}\n\n## Related Questions\n"
        content += "\n".join(f"- [[{question_note_by_id[qid].stem}]]" for qid in _unique(qids) if qid in question_note_by_id) + "\n"
        concept_notes.append(_write(vault_path / "05_Ontology" / folder / f"{concept}.md", content))

    relation_notes: list[Path] = []
    for relation, qids in sorted(relation_usage.items()):
        tags = ["#obybk", f"#relation/{_relation_tag(relation)}"]
        content = _frontmatter({"type": "ontology_relation", "relation": relation, "related_questions": _unique(qids), "tags": tags})
        content += f"# {relation}\n\nTags: {' '.join(tags)}\n\n## Related Questions\n"
        content += "\n".join(f"- [[{question_note_by_id[qid].stem}]]" for qid in _unique(qids) if qid in question_note_by_id) + "\n"
        relation_notes.append(_write(vault_path / "05_Ontology" / "relations" / f"{relation}.md", content))

    data_gap_count = sum(1 for row in rows if int(row.get("data_gap_count") or 0) > 0)
    index_body = _frontmatter({"type": "wiki_index", "project": "OBYBK", "run_id": run_id, "tags": ["#obybk", "#wiki/index", "#rag/wiki"]})
    index_body += "# OBYBK RAG Wiki\n\n"
    index_body += "## Dashboard\n"
    index_body += f"- Latest Run: [[{run_note.stem}]]\n"
    index_body += f"- Review Queue: [[{review_queue_note.stem}]]\n"
    index_body += f"- Questions: `{len(rows)}`\n"
    index_body += f"- Contract Pass: `{contract_pass_count}/{len(rows)}`\n"
    index_body += f"- Review Items: `{len(review_rows)}`\n"
    index_body += f"- Data-gap Questions: `{data_gap_count}`\n"
    index_body += f"- Entities: `{len(entity_notes)}` / Concepts: `{len(concept_notes)}` / Relations: `{len(relation_notes)}`\n\n"
    if asset_paths:
        index_body += "## Visual Evidence\n" + "\n".join(f"- ![[{path.name}]]" for path in asset_paths[:3]) + "\n\n"
    index_body += "## Category Counts\n"
    index_body += "\n".join(f"- **{category}**: `{count}`" for category, count in category_counts.items()) + "\n\n"
    index_body += "## LLM Mode Counts\n"
    index_body += "\n".join(f"- `{mode}`: `{count}`" for mode, count in run_mode_counts.items()) + "\n\n"
    index_body += "## Question Samples\n"
    for qid, note_path in list(question_note_by_id.items())[:12]:
        row = question_row_by_id.get(qid, {})
        status = "✅" if row.get("contract_pass") else "⚠️"
        review = " review" if row.get("requires_review") else ""
        index_body += f"- {status} [[{note_path.stem}]] — {_short(row.get('question'), 90)}{review}\n"
    index_body += "\n"
    if review_rows:
        index_body += "## Review Hotlist\n"
        for index, row in review_rows[:12]:
            qid = _question_id(row, index)
            note_path = question_note_by_id.get(qid)
            link = f"[[{note_path.stem}]]" if note_path else qid
            index_body += f"- {link} — contract_pass=`{bool(row.get('contract_pass'))}`, data_gap_count=`{int(row.get('data_gap_count') or 0)}`\n"
        index_body += "\n"
    index_body += "## Ontology Entry Points\n"
    index_body += "- Domain concepts: [[Question]], [[Station]], [[UsageMetric]], [[ReallocationRecommendation]], [[ReviewGate]]\n"
    index_body += "- Relations: [[hasEvidence]], [[forStation]], [[requiresReview]]\n"
    if entity_notes:
        index_body += "- Entity examples: " + ", ".join(f"[[{path.stem}]]" for path in entity_notes[:6]) + "\n"
    index_body += "\n## Query Examples\n"
    index_body += "- `tag:#sim/operation/reallocation tag:#ontology/domain/station`\n"
    index_body += "- `tag:#review/needed tag:#sim/risk/data-gap`\n"
    index_body += "- `tag:#entity/station/ST-152`\n"
    index_body += "- `tag:#relation/has-evidence tag:#rag/eval/contract-fail`\n"
    _write(index_note, index_body)

    return WikiExportResult(
        vault=vault_path,
        run_note=run_note,
        index_note=index_note,
        review_queue_note=review_queue_note,
        question_notes=question_notes,
        entity_notes=entity_notes,
        concept_notes=concept_notes,
        relation_notes=relation_notes,
        asset_paths=asset_paths,
        obsidian_uri=_obsidian_uri(vault_path, index_note),
    )


__all__ = ["WikiExportResult", "export_ontology_wiki"]
