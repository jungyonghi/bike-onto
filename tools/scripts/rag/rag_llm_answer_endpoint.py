# Timestamp: 2026-05-19 12:44:00

import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable

try:
    import requests
except Exception:  # pragma: no cover - requests exists in the project venv.
    requests = None

try:
    from .answer_composer import build_answer_prompt, compose_answer, display_entity_reference, entity_display_name, relation_label
    from .answer_policy import decide_answer_policy
    from .natural_language_labels import humanize_mapping_values, naturalize_code_mentions
    from .evidence_builder import build_evidence_bundle
    from .intent_classifier import classify_question_intent
    from .pgvector_integration_pack import hash_text_to_vector
    from .schemas import AnswerProfile
except ImportError:  # Allow direct script execution.
    from answer_composer import build_answer_prompt, compose_answer, display_entity_reference, entity_display_name, relation_label
    from answer_policy import decide_answer_policy
    from natural_language_labels import humanize_mapping_values, naturalize_code_mentions
    from evidence_builder import build_evidence_bundle
    from intent_classifier import classify_question_intent
    from pgvector_integration_pack import hash_text_to_vector
    from schemas import AnswerProfile


PROJECT_ROOT = Path("/home/user/Documents/01_Projects/01_Active/obybk")
DEFAULT_KEY_FILE = PROJECT_ROOT / "config" / "openai_api_key.local"

LlmCallable = Callable[[str, dict[str, Any]], dict[str, Any]]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^0-9A-Za-z가-힣]+", text.lower()) if len(token) >= 2}


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def retrieve_contexts(seed_rows: list[dict[str, Any]], question: str, top_k: int) -> list[dict[str, Any]]:
    if not seed_rows:
        return []
    query_tokens = tokens(question)
    vector_dim = len(seed_rows[0].get("embedding") or []) or 16
    query_vector = hash_text_to_vector(question, vector_dim)
    scored: list[dict[str, Any]] = []
    for row in seed_rows:
        content = str(row.get("content") or "")
        embedding = [float(value) for value in (row.get("embedding") or [])]
        token_overlap = len(query_tokens & tokens(content))
        vector_score = cosine(query_vector, embedding)
        score = token_overlap + vector_score
        scored.append(
            {
                "id": row.get("id"),
                "content": content,
                "metadata": row.get("metadata") or {},
                "score": round(float(score), 6),
                "token_overlap": token_overlap,
                "vector_score": round(float(vector_score), 6),
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[: max(1, min(top_k, 10))]


def merge_runtime_contexts(matches: list[dict[str, Any]], runtime_rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    evidence_documents: list[str] = []
    related_objects: list[dict[str, Any]] = []
    related_relations: list[dict[str, Any]] = []
    recommended_actions: list[dict[str, Any]] = []
    graph_metrics: list[dict[str, Any]] = []
    primary_match = matches[0] if matches else {}
    primary_row = runtime_rows.get(str(primary_match.get("id")), {})
    primary_metadata = primary_match.get("metadata") or {}
    requires_review = bool(primary_row.get("requires_review")) or bool(primary_metadata.get("requires_review"))

    # Aggregate evidence/relation context from top-k, but keep review/action boundary anchored
    # to the primary retrieved item to avoid unrelated top-k review actions contaminating
    # non-actionable questions.
    for value in primary_row.get("recommended_actions") or []:
        if value not in recommended_actions:
            recommended_actions.append(value)
    for match in matches:
        row = runtime_rows.get(str(match.get("id")), {})
        metadata = match.get("metadata") or {}
        if isinstance(row.get("graph_metrics"), dict):
            graph_metrics.append({"source_id": match.get("id"), "metrics": row.get("graph_metrics")})
        for value in row.get("evidence_documents") or metadata.get("evidence_documents") or []:
            if value not in evidence_documents:
                evidence_documents.append(value)
        for value in row.get("related_objects") or []:
            if value not in related_objects:
                related_objects.append(value)
        for value in row.get("related_relations") or []:
            if value not in related_relations:
                related_relations.append(value)
    return {
        "evidence_documents": evidence_documents,
        "related_objects": related_objects,
        "related_relations": related_relations,
        "recommended_actions": recommended_actions,
        "requires_review": requires_review,
        "graph_metrics": graph_metrics,
    }


def _object_detail_status(obj: dict[str, Any]) -> str:
    attributes = {key: value for key, value in obj.items() if key not in {"type", "id", "label"} and value not in (None, "", [])}
    label = str(obj.get("label") or "").strip()
    obj_id = str(obj.get("id") or "").strip()
    if attributes:
        return "resolved"
    if label and label != obj_id:
        return "minimal"
    return "insufficient_context"


def build_entity_cards(related_objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for obj in related_objects:
        obj_id = str(obj.get("id") or obj.get("label") or "")
        if not obj_id or obj_id in seen:
            continue
        seen.add(obj_id)
        attributes = {key: value for key, value in obj.items() if key not in {"type", "id", "label"} and value not in (None, "", [])}
        display_attributes = humanize_mapping_values(attributes)
        status = _object_detail_status(obj)
        missing = [] if status == "resolved" else ["location/address/detail attributes not present in current RAG context"]
        cards.append(
            {
                "type": obj.get("type"),
                "id": obj.get("id"),
                "label": obj.get("label"),
                "attributes": attributes,
                "display_attributes": display_attributes,
                "detail_status": status,
                "missing_detail_notes": missing,
            }
        )
    return cards


def build_quantitative_indicators(
    *,
    matches: list[dict[str, Any]],
    related_objects: list[dict[str, Any]],
    related_relations: list[dict[str, Any]],
    evidence_documents: list[str],
    recommended_actions: list[dict[str, Any]],
    graph_metrics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    indicators: list[dict[str, Any]] = [
        {"metric": "retrieved_context_count", "value": len(matches), "source": "retrieval"},
        {"metric": "evidence_document_count", "value": len(evidence_documents), "source": "runtime_context"},
        {"metric": "related_object_count", "value": len(related_objects), "source": "runtime_context"},
        {"metric": "related_relation_count", "value": len(related_relations), "source": "runtime_context"},
        {"metric": "recommended_action_count", "value": len(recommended_actions), "source": "primary_context"},
    ]
    for index, match in enumerate(matches, start=1):
        indicators.append({"metric": f"top{index}_retrieval_score", "value": match.get("score"), "source": match.get("id")})
        indicators.append({"metric": f"top{index}_token_overlap", "value": match.get("token_overlap"), "source": match.get("id")})
    relation_counts: dict[str, int] = {}
    for relation in related_relations:
        name = str(relation.get("relation") or "unknown")
        relation_counts[name] = relation_counts.get(name, 0) + 1
    for name, count in sorted(relation_counts.items()):
        indicators.append({"metric": f"relation_count:{name}", "value": count, "source": "related_relations"})
    for metric_group in graph_metrics:
        source_id = metric_group.get("source_id")
        metrics = metric_group.get("metrics") or {}
        if not isinstance(metrics, dict):
            continue
        for key, value in metrics.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                indicators.append({"metric": key, "value": value, "source": source_id})
    return indicators


def build_candidate_set(graph_metrics: list[dict[str, Any]], related_objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for metric_group in graph_metrics:
        source_id = metric_group.get("source_id")
        metrics = metric_group.get("metrics") or {}
        if not isinstance(metrics, dict):
            continue
        for key, value in metrics.items():
            if "preview" not in str(key).lower() or not isinstance(value, list):
                continue
            for rank, candidate_id in enumerate(value, start=1):
                candidate_key = str(candidate_id)
                if candidate_key in seen:
                    continue
                seen.add(candidate_key)
                candidates.append(
                    {
                        "candidate_id": candidate_key,
                        "rank": rank,
                        "source_metric": key,
                        "source_id": source_id,
                        "score": None,
                        "note": "preview candidate from graph/runtime metrics; score is not available in current context",
                    }
                )
    if not candidates:
        for obj in related_objects:
            obj_id = str(obj.get("id") or "")
            if obj_id and obj_id not in seen:
                seen.add(obj_id)
                candidates.append(
                    {
                        "candidate_id": obj_id,
                        "rank": len(candidates) + 1,
                        "source_metric": "related_objects",
                        "source_id": obj.get("type"),
                        "score": None,
                        "note": "object candidate; explicit ranking score is not available",
                    }
                )
    return candidates


def build_evidence_excerpt_list(matches: list[dict[str, Any]], evidence_documents: list[str]) -> list[dict[str, Any]]:
    excerpts: list[dict[str, Any]] = []
    for match in matches:
        content = str(match.get("content") or "")
        excerpts.append(
            {
                "source": match.get("id"),
                "kind": "retrieved_context",
                "score": match.get("score"),
                "excerpt": content[:500],
            }
        )
    for path in evidence_documents[:10]:
        excerpts.append({"source": path, "kind": "evidence_document", "score": None, "excerpt": "file path only; quote extraction not available in current context"})
    return excerpts


def build_data_gaps(question: str, entity_cards: list[dict[str, Any]], candidate_set: list[dict[str, Any]], quantitative_indicators: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    for card in entity_cards:
        if card.get("detail_status") != "resolved":
            gaps.append(f"{card.get('id') or card.get('label')} has no detailed location/address attributes in current context.")
    if candidate_set and all(candidate.get("score") is None for candidate in candidate_set):
        gaps.append("Candidate identifiers are available, but explicit ranking/score values are not available in current context.")
    q = question.lower()
    if any(token in q for token in ["이유", "왜", "줄어", "감소", "원인", "reason", "why"]):
        gaps.append("Causal explanation needs statistical comparison: target period vs baseline period, delta, and confidence interval/effect size.")
    if any(token in q for token in ["연결", "관련", "상관", "관계", "connected", "relation"]):
        if not any(str(item.get("metric", "")).startswith("relation_count") for item in quantitative_indicators):
            gaps.append("Relation strength needs quantified counts or weights, not just relation labels.")
    return gaps[:8]


def load_openai_settings(key_file: Path = DEFAULT_KEY_FILE) -> dict[str, str]:
    settings: dict[str, str] = {}
    if key_file.exists():
        for line in key_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            settings[key.strip()] = value.strip().strip("'\"")
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
        if os.environ.get(key):
            settings[key] = os.environ[key]
    settings.setdefault("OPENAI_BASE_URL", "https://api.openai.com/v1")
    settings.setdefault("OPENAI_MODEL", "gpt-5.2")
    return settings


def chat_url(base_url: str) -> str:
    stripped = base_url.rstrip("/")
    if stripped.endswith("/chat/completions"):
        return stripped
    if stripped.endswith("/v1"):
        return f"{stripped}/chat/completions"
    return f"{stripped}/v1/chat/completions"


def build_llm_prompt(context: dict[str, Any]) -> str:
    evidence = build_evidence_bundle(context)
    answer_policy = context.get("answer_policy") or decide_answer_policy(context["question"], context.get("category")).to_dict()
    compact_context = {
        "question": context["question"],
        "answer_policy": answer_policy,
        "retrieved_contexts": context["retrieved_contexts"][:3],
        "entity_cards": context.get("entity_cards", [])[:5],
        "candidate_set": context.get("candidate_set", [])[:5],
        "quantitative_indicators": context.get("quantitative_indicators", [])[:12],
        "data_gaps": context.get("data_gaps", [])[:5],
        "evidence_documents": context["evidence_documents"][:5],
        "evidence_excerpt_list": context.get("evidence_excerpt_list", [])[:5],
        "related_objects": [{**obj, "display_name": entity_display_name(obj)} for obj in context["related_objects"][:5]],
        "related_relations": [{**relation, "relation_label_ko": relation_label(relation.get("relation") or relation.get("type"))} for relation in context["related_relations"][:5]],
        "recommended_actions": context["recommended_actions"][:3],
        "requires_review": context["requires_review"],
    }
    profile = classify_question_intent(context["question"], context.get("category"))
    composer_prompt = build_answer_prompt(
        context["question"],
        profile,
        evidence,
        debug_mode=bool(context.get("debug_mode", False)),
    )
    return "\n".join(
        [
            composer_prompt,
            "",
            "추가 규칙:",
            "- answer_policy.answerability, requires_review, review_reason은 판단 기준으로 고정하고 임의로 더 엄격하게 만들지 마라.",
            "- review=False인 경우 review_reason은 빈 문자열로 둔다.",
            "- 단순 실행형 질문은 장황한 운영 해석 대신 산출 방식, 필요한 파라미터, 반환 형태를 짧게 설명하라.",
            "- metric/provenance형 질문은 필요한 조인, 파생 지표, baseline/임계치, 직접/추론 근거 분리를 질문별 핵심만 남겨 설명하라.",
            "- '현재 근거만으로 수치 확정 불가', '현재 근거만으로 제시할 수 없다', '리뷰 게이트가 필요하다'를 반복하지 마라.",
            "- 이유/감소/원인 질문에서 원인을 모르면 모른다고 끝내지 말고, 가능한 통계 비교(기준 기간, 대상 기간, delta, 비율, 효과크기)와 필요한 추가 집계를 능동적으로 제안하라.",
            "- 후보 질문에서는 candidate_set이 있으면 1개만 단정하지 말고 여러 후보와 score/순위 부재 여부를 표 형태로 설명하라.",
            "- 연결/관계 질문에서는 related_relations의 relation_label_ko와 quantitative_indicators를 사용해 얼마나 연결되는지 count/score 등 정량 지표를 언급하라.",
            "- relation은 한국어 명사형 label로 표시하고 영어 relation id는 사용자 본문에 그대로 노출하지 마라.",
            "- gender=1.0, holiday=0 같은 코드값은 사용자 본문에 그대로 노출하지 말고 가능한 자연어 label(예: 남성(M), 여성(F), 공휴일/비공휴일)을 우선 표시하라.",
            "- 엔티티는 id보다 display_name/name/label/station_name/title/place_name/address2/address를 우선 표시하고, 주소 문장에서는 역이름·지명 suffix를 우선 추출하라.",
            "- 추정과 근거를 구분하고, 추천/조치가 있으면 자동 실행하지 말고 사람 검토·승인이 필요하다고 명시하라.",
            "- 반드시 JSON만 반환하고 markdown code fence는 쓰지 마라.",
            "- JSON의 answer 필드 안에는 위 Markdown 섹션 구조를 넣어라.",
            "반환 JSON schema:",
            '{"answer":"## 답변\\n...","key_findings":[{"claim":"...","basis":"...","confidence":"..."}],"answerability":"needs-parameter","requires_review":true,"review_reason":"...","uncertainty":"..."}',
            "RAG context:",
            json.dumps(compact_context, ensure_ascii=False),
        ]
    )


def extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else None
    except Exception:
        pass
    match = re.search(r"\{.*\}", stripped, flags=re.S)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def call_openai_compatible_llm(prompt: str, context: dict[str, Any], *, key_file: Path = DEFAULT_KEY_FILE) -> dict[str, Any]:
    settings = load_openai_settings(key_file)
    api_key = settings.get("OPENAI_API_KEY", "").strip()
    model = settings.get("OPENAI_MODEL", "gpt-5.2").strip() or "gpt-5.2"
    base_url = settings.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip() or "https://api.openai.com/v1"
    if not api_key:
        return fallback_grounded_answer(context, mode="fallback_no_api_key", model=model)
    if requests is None:
        return fallback_grounded_answer(context, mode="fallback_requests_missing", model=model)
    started = time.perf_counter()
    request_payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a grounded RAG answer generator. Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "max_completion_tokens": 2400,
        "response_format": {"type": "json_object"},
    }
    try:
        response = requests.post(
            chat_url(base_url),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            json=request_payload,
            timeout=180,
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        response.raise_for_status()
        response_payload = response.json()
    except Exception as error:
        fallback = fallback_grounded_answer(context, mode="fallback_llm_error", model=model)
        fallback["_meta"]["error_type"] = type(error).__name__
        fallback["_meta"]["error"] = str(error)[:500]
        return fallback
    raw_text = response_payload["choices"][0]["message"].get("content", "")
    parsed = extract_json_object(raw_text)
    if parsed is None:
        parsed = fallback_grounded_answer(context, mode="fallback_parse_error", model=model)
        parsed["_raw_text"] = raw_text
        parsed["_meta"]["latency_ms"] = latency_ms
        parsed["_meta"]["usage"] = response_payload.get("usage", {})
        return parsed
    parsed["_meta"] = {"mode": "live", "model": model, "latency_ms": latency_ms, "usage": response_payload.get("usage", {})}
    parsed.setdefault("_raw_text", raw_text)
    return parsed


def fallback_grounded_answer(context: dict[str, Any], *, mode: str = "fallback", model: str = "fallback") -> dict[str, Any]:
    evidence_documents = context.get("evidence_documents", [])[:5]
    policy = context.get("answer_policy") or decide_answer_policy(str(context.get("question") or ""), context.get("category")).to_dict()
    review = bool(context.get("requires_review")) or bool(policy.get("requires_review"))
    evidence_bundle = build_evidence_bundle(context)
    answer = compose_answer(
        str(context.get("question") or ""),
        evidence_bundle,
        category=context.get("category"),
        debug_mode=bool(context.get("debug_mode", False)),
    )
    return {
        "answer": answer,
        "key_findings": [{"claim": "검색 근거를 사용자 조치 중심 답변으로 변환했습니다.", "basis": "answer_composer", "confidence": "medium"}],
        "answerability": policy.get("answerability"),
        "answer_policy": policy,
        "candidate_set": context.get("candidate_set", [])[:10],
        "quantitative_indicators": context.get("quantitative_indicators", [])[:30],
        "entity_cards": context.get("entity_cards", [])[:10],
        "data_gaps": context.get("data_gaps", [])[:8],
        "evidence_excerpt_list": context.get("evidence_excerpt_list", [])[:12],
        "evidence_documents": evidence_documents,
        "related_objects": context.get("related_objects", [])[:5],
        "related_relations": context.get("related_relations", [])[:5],
        "recommended_actions": context.get("recommended_actions", [])[:3],
        "requires_review": review,
        "review_reason": (policy.get("review_reason") or "추천/조치 또는 검토 플래그가 포함되어 사람 검토가 필요합니다.") if review else "",
        "uncertainty": "LLM live 호출 대신 Answer Composer fallback을 사용했습니다.",
        "_raw_text": "",
        "_meta": {"mode": mode, "model": model, "latency_ms": 0.0},
    }


def normalize_llm_payload(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("_meta") or {}
    policy = context.get("answer_policy") or decide_answer_policy(str(context.get("question") or ""), context.get("category")).to_dict()
    policy_requires_review = bool(policy.get("requires_review"))
    requires_review = bool(context.get("requires_review")) or policy_requires_review
    if requires_review:
        review_reason = str(payload.get("review_reason") or policy.get("review_reason") or "추천/조치 또는 검토 플래그가 포함되어 사람 검토가 필요합니다.")
    else:
        review_reason = ""
    evidence = payload.get("evidence_documents") if isinstance(payload.get("evidence_documents"), list) else context.get("evidence_documents", [])[:5]
    related_objects = payload.get("related_objects") if isinstance(payload.get("related_objects"), list) else context.get("related_objects", [])[:5]
    related_relations = payload.get("related_relations") if isinstance(payload.get("related_relations"), list) else context.get("related_relations", [])[:5]
    recommended_actions = payload.get("recommended_actions") if isinstance(payload.get("recommended_actions"), list) else context.get("recommended_actions", [])[:3]
    return {
        "answer": str(payload.get("answer") or "").strip(),
        "key_findings": payload.get("key_findings") if isinstance(payload.get("key_findings"), list) else [],
        "answerability": str(policy.get("answerability") or payload.get("answerability") or "executable-with-data"),
        "answer_policy": policy,
        "candidate_set": context.get("candidate_set", []),
        "quantitative_indicators": context.get("quantitative_indicators", []),
        "entity_cards": context.get("entity_cards", []),
        "data_gaps": context.get("data_gaps", []),
        "evidence_excerpt_list": context.get("evidence_excerpt_list", []),
        "evidence_documents": evidence,
        "related_objects": related_objects,
        "related_relations": related_relations,
        "recommended_actions": recommended_actions,
        "requires_review": requires_review,
        "review_reason": review_reason,
        "uncertainty": str(payload.get("uncertainty") or ""),
        "raw_text": payload.get("_raw_text", ""),
        "llm": {
            "mode": meta.get("mode", "unknown"),
            "model": meta.get("model", "unknown"),
            "latency_ms": meta.get("latency_ms", 0.0),
            "usage": meta.get("usage", {}),
        },
    }


def _indicator_display_text(item: dict[str, Any]) -> str:
    metric = str(item.get("metric") or "")
    value = item.get("value")
    if metric.startswith("relation_count:"):
        return f"{relation_label(metric.split(':', 1)[1])}={value}"
    return f"{metric}={value}"


def _entity_reference_ids(context: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for obj in context.get("related_objects", []) or []:
        obj_id = str(obj.get("id") or "").strip()
        if obj_id:
            values.append(obj_id)
    for candidate in context.get("candidate_set", []) or []:
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        if candidate_id:
            values.append(candidate_id)
    for action in context.get("recommended_actions", []) or []:
        target = str(action.get("target") or action.get("station") or "").strip()
        if target:
            values.append(target)
    return [value for index, value in enumerate(values) if value and value not in values[:index]]


def _normalize_answer_entity_references(answer: str, context: dict[str, Any]) -> str:
    evidence_bundle = build_evidence_bundle(context)
    normalized = answer
    for reference in _entity_reference_ids(context):
        display = display_entity_reference(reference, evidence_bundle)
        if not display or display == reference or "명칭 미확인" in display:
            continue
        normalized = re.sub(re.escape(reference), display, normalized, flags=re.I)
        station_match = re.match(r"station:0*(\d+)$", reference, flags=re.I)
        st_match = re.match(r"st-0*(\d+)$", reference, flags=re.I)
        station_number = station_match.group(1) if station_match else st_match.group(1) if st_match else ""
        if station_number:
            normalized = re.sub(rf"\b대여소\s*0*{re.escape(station_number)}\b", display, normalized)
            normalized = re.sub(rf"\bstation\s*:?\s*0*{re.escape(station_number)}\b", display, normalized, flags=re.I)
            normalized = re.sub(rf"(?<!\()\bST-0*{re.escape(station_number)}\b", display, normalized, flags=re.I)
    return normalized


def apply_answer_quality_guards(question: str, answer: str, context: dict[str, Any]) -> tuple[str, list[str]]:
    notes: list[str] = []
    additions: list[str] = []
    original_answer = answer
    answer = _normalize_answer_entity_references(answer, context)
    answer = naturalize_code_mentions(answer)
    if answer != original_answer and "naturalized_code_labels" not in notes:
        notes.append("naturalized_code_labels")
    q = question.lower()
    answer_lower = answer.lower()
    if any(token in q for token in ["이유", "왜", "줄어", "감소", "원인", "reason", "why"]):
        profile = classify_question_intent(question, context.get("category"))
        if profile == AnswerProfile.API_DB_PERFORMANCE:
            if not any(token in answer for token in ["API 처리 시간", "DB query time", "vector search time", "p95 latency", "LLM generation time"]):
                additions.append(
                    "성능 병목 분석 제안: 검색 latency 원인을 확정하려면 API 처리 시간, DB query time, "
                    "vector search time, reranking time, LLM generation time, network/serialization time을 trace 단위로 분리하고 "
                    "p50 latency, p95 latency, p99 latency, index 사용 여부, top-k 설정, filter 조건, embedding dimension, row count 변화를 함께 확인해야 합니다."
                )
                notes.append("added_performance_diagnostic_for_latency_reason_question")
        elif profile == AnswerProfile.DEMAND_USAGE_ANALYSIS and not any(token in answer for token in ["기준 기간", "대상 기간", "delta", "증감", "평균 대비"]):
            debug_metric_names = {"retrieved_context_count", "evidence_document_count", "related_object_count", "related_relation_count", "recommended_action_count"}
            metric_text = ", ".join(
                _indicator_display_text(item)
                for item in context.get("quantitative_indicators", [])[:12]
                if item.get("value") is not None
                and str(item.get("metric") or "") not in debug_metric_names
                and not str(item.get("metric") or "").startswith("top")
            )
            additions.append(
                "능동 분석 제안: 원인을 확정할 수 없을 때는 대상 시간대와 기준 기간(예: 전일/지난 7일 평균)을 나누어 "
                "이용량 delta, 증감률, 시간대별 평균 대비 편차, 관련 외부 변수별 차이를 계산해야 합니다. "
                f"현재 원인 판단용 정량 단서: {metric_text or '원인 판단 지표 부족'}."
            )
            notes.append("added_active_statistical_diagnostic_for_reason_question")
        elif profile == AnswerProfile.RECOMMENDATION_REBALANCING and not any(token in answer for token in ["후보 다양성", "명시적 score", "승인 조건", "위험 요소"]):
            additions.append(
                "추천 위험 분석 제안: 추천 후보가 적을 때는 후보 다양성, 명시적 score/순위, 기대 효과, 위험 요소, "
                "자동 실행 금지 조건, 운영자 승인 조건을 함께 확인해야 합니다."
            )
            notes.append("added_recommendation_risk_diagnostic_for_reason_question")
        elif profile not in {AnswerProfile.DEMAND_USAGE_ANALYSIS, AnswerProfile.API_DB_PERFORMANCE} and not any(token in answer for token in ["영향 범위", "최근 변경", "로그", "데이터 누락"]):
            additions.append(
                "원인 분석 제안: 현재 근거만으로 원인을 확정할 수 없으면 증상 발생 시각, 영향 범위, 최근 변경 이력, "
                "관련 로그, 데이터 누락 여부를 분리해 확인해야 합니다."
            )
            notes.append("added_general_cause_diagnostic_for_reason_question")
    if context.get("candidate_set") and any(token in q for token in ["후보", "추천", "candidate"]):
        candidate_ids = [str(item.get("candidate_id")) for item in context.get("candidate_set", [])[:5] if item.get("candidate_id")]
        if candidate_ids and sum(1 for candidate_id in candidate_ids if candidate_id in answer) < min(2, len(candidate_ids)):
            evidence_bundle = build_evidence_bundle(context)
            candidate_labels = [display_entity_reference(candidate_id, evidence_bundle) for candidate_id in candidate_ids]
            additions.append(
                "후보는 단일 항목으로 단정하지 않습니다. 현재 context의 후보 목록은 "
                f"{', '.join(candidate_labels)}이며, 명시적 score가 없으면 순위는 preview 순서일 뿐 확정 점수가 아닙니다."
            )
            notes.append("added_multi_candidate_guard")
    if any(token in q for token in ["어디", "위치", "주소", "where"]):
        missing_cards = [card for card in context.get("entity_cards", []) if card.get("detail_status") != "resolved"]
        if missing_cards and not any(token in answer for token in ["위치", "주소", "상세 속성", "detail_status"]):
            additions.append(
                "엔티티 위치/주소 주의: 현재 RAG context에는 "
                + ", ".join(str(card.get("id") or card.get("label")) for card in missing_cards[:5])
                + "의 상세 위치·주소 속성이 없어 ID/라벨 이상으로 위치를 단정할 수 없습니다."
            )
            notes.append("added_entity_detail_gap_guard")
    if any(token in q for token in ["연결", "관련", "관계", "상관", "connected", "relation"]):
        if not any(token in answer for token in ["count", "score", "개", "정량", "지표"]):
            relation_metrics = [item for item in context.get("quantitative_indicators", []) if str(item.get("metric", "")).startswith("relation_count")]
            relation_text = ", ".join(_indicator_display_text(item) for item in relation_metrics[:8])
            additions.append(f"연결 강도는 라벨만으로 판단하지 않고 정량 지표를 함께 봐야 합니다. 현재 관계 지표: {relation_text or '관계 count 부족'}.")
            notes.append("added_relation_quantification_guard")
    if additions:
        return answer.rstrip() + "\n\n" + "\n".join(additions), notes
    return answer, notes


def generate_rag_llm_answer(
    *,
    question: str,
    runtime_rows: dict[str, dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    top_k: int = 3,
    llm_callable: LlmCallable | None = None,
    key_file: Path = DEFAULT_KEY_FILE,
    debug_mode: bool = False,
    category: str | None = None,
    retrieved_contexts: list[dict[str, Any]] | None = None,
    retrieval_backend: str = "local",
    retrieval_latency_ms_override: float | None = None,
) -> dict[str, Any]:
    retrieval_started = time.perf_counter()
    if retrieved_contexts is None:
        matches = retrieve_contexts(seed_rows, question, top_k)
    else:
        matches = retrieved_contexts
    measured_retrieval_latency_ms = round((time.perf_counter() - retrieval_started) * 1000, 3)
    retrieval_latency_ms = retrieval_latency_ms_override if retrieval_latency_ms_override is not None else measured_retrieval_latency_ms
    merged = merge_runtime_contexts(matches, runtime_rows)
    entity_cards = build_entity_cards(merged["related_objects"])
    candidate_set = build_candidate_set(merged.get("graph_metrics", []), merged["related_objects"])
    quantitative_indicators = build_quantitative_indicators(
        matches=matches,
        related_objects=merged["related_objects"],
        related_relations=merged["related_relations"],
        evidence_documents=merged["evidence_documents"],
        recommended_actions=merged["recommended_actions"],
        graph_metrics=merged.get("graph_metrics", []),
    )
    evidence_excerpt_list = build_evidence_excerpt_list(matches, merged["evidence_documents"])
    data_gaps = build_data_gaps(question, entity_cards, candidate_set, quantitative_indicators)
    answer_policy = decide_answer_policy(question, category)
    context = {
        "question": question,
        "answer_policy": answer_policy.to_dict(),
        "retrieved_contexts": matches,
        **merged,
        "entity_cards": entity_cards,
        "candidate_set": candidate_set,
        "quantitative_indicators": quantitative_indicators,
        "evidence_excerpt_list": evidence_excerpt_list,
        "data_gaps": data_gaps,
        "debug_mode": debug_mode,
        "category": category,
    }
    prompt = build_llm_prompt(context)
    if llm_callable is None:
        llm_payload = call_openai_compatible_llm(prompt, context, key_file=key_file)
    else:
        llm_payload = llm_callable(prompt, context)
    normalized = normalize_llm_payload(llm_payload, context)
    guarded_answer, quality_guard_notes = apply_answer_quality_guards(question, normalized["answer"], context)
    normalized["answer"] = guarded_answer
    contract_checks = {
        "has_answer": bool(normalized["answer"]),
        "has_evidence_documents": bool(normalized["evidence_documents"]),
        "has_related_objects": bool(normalized["related_objects"]),
        "has_related_relations": bool(normalized["related_relations"]),
        "has_review_boundary": (not normalized["requires_review"]) or bool(normalized["review_reason"]),
    }
    return {
        "mode": "rag_llm",
        "question": question,
        "answer": normalized["answer"],
        "key_findings": normalized["key_findings"],
        "answerability": normalized["answerability"],
        "answer_policy": normalized["answer_policy"],
        "candidate_set": normalized["candidate_set"],
        "quantitative_indicators": normalized["quantitative_indicators"],
        "entity_cards": normalized["entity_cards"],
        "data_gaps": normalized["data_gaps"],
        "evidence_excerpt_list": normalized["evidence_excerpt_list"],
        "evidence_documents": normalized["evidence_documents"],
        "related_objects": normalized["related_objects"],
        "related_relations": normalized["related_relations"],
        "recommended_actions": normalized["recommended_actions"],
        "requires_review": normalized["requires_review"],
        "review_reason": normalized["review_reason"],
        "uncertainty": normalized["uncertainty"],
        "llm": normalized["llm"],
        "retrieval": {"top_k": top_k, "latency_ms": retrieval_latency_ms, "matches": matches, "backend": retrieval_backend},
        "contract_checks": contract_checks,
        "contract_pass": all(contract_checks.values()),
        "quality_guard_notes": quality_guard_notes,
        "raw_text": normalized["raw_text"],
    }


def create_rag_llm_answer_app(
    *,
    runtime_answers_path: Path | str,
    pgvector_seed_path: Path | str,
    llm_callable: LlmCallable | None = None,
    key_file: Path | str = DEFAULT_KEY_FILE,
):
    from fastapi import FastAPI
    from pydantic import BaseModel, Field

    runtime_answers_path = Path(runtime_answers_path)
    pgvector_seed_path = Path(pgvector_seed_path)
    key_file = Path(key_file)
    runtime_list = read_jsonl(runtime_answers_path)
    runtime_rows = {str(row.get("id") or row.get("question_id")): row for row in runtime_list}
    seed_rows = read_jsonl(pgvector_seed_path)

    class RagAnswerRequest(BaseModel):
        question: str = Field(min_length=1)
        top_k: int = Field(default=3, ge=1, le=10)
        debug_mode: bool = False
        category: str | None = None

    app = FastAPI(
        title="OBYBK RAG LLM Answer API",
        version="0.1.0",
        description="RAG retrieval + LLM grounded answer generation endpoint for OBYBK.",
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "runtime_answer_count": len(runtime_list),
            "seed_count": len(seed_rows),
            "llm_mode": "custom" if llm_callable else "openai_compatible_or_fallback",
        }

    @app.post("/rag-answer")
    def rag_answer(request: RagAnswerRequest) -> dict[str, Any]:
        return generate_rag_llm_answer(
            question=request.question,
            runtime_rows=runtime_rows,
            seed_rows=seed_rows,
            top_k=request.top_k,
            llm_callable=llm_callable,
            key_file=key_file,
            debug_mode=request.debug_mode,
            category=request.category,
        )

    return app
