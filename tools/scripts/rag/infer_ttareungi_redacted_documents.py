# Timestamp: 2026-05-18 11:05:50

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Sequence


PROJECT_DOC_RELATIVE = Path("docs/project/ttareungi_service_overview.md")
DEFAULT_MANIFEST_GLOB = "data/raw/opengov_seoul_ttareungi_pdfs/run_*_all_period/manifest.json"
DEFAULT_OUTPUT_ROOT = Path("data/processed/exports/opengov_redaction_inference_runs")
RAG_DOCUMENTS_RELATIVE = Path("data/processed/rag/ttareungi_rag_index/documents.jsonl")
DOMAIN_ONTOLOGY_GLOB = (
    "data/processed/exports/ttareungi_domain_ontology_runs/*/ttareungi_domain_ontology_lite.json"
)

OPERATION_KEYWORDS = {
    "maintenance": ["유지관리", "유지보수", "정비", "정비용역", "민간협업정비", "따릉이포"],
    "delivery": ["배송", "재배치", "집중관리", "배송업무", "배송인력"],
    "station": ["대여소", "거치대", "캐노피", "안내간판", "LED"],
    "device": ["단말기", "QR", "LCD", "배터리", "충전기"],
    "disposal": ["폐기", "노후"],
    "budget": ["예산", "추경", "전용", "사고이월", "대행사업"],
    "safety": ["안전관리", "안전보건", "위험성평가", "재발방지"],
    "operation": ["운영계획", "인력", "조직", "운영"],
}
SENSITIVE_KEYWORDS = [
    "개인정보",
    "유출",
    "보안",
    "취약점",
    "외부강의",
    "채용",
    "면접",
    "서류전형",
    "응시원서",
    "비위",
    "조사결과",
    "사건대리인",
    "전화번호",
]
SENSITIVE_PATTERNS = [
    re.compile(r"\b\d{2,3}-\d{3,4}-\d{4}\b"),
    re.compile(r"\b\d{6}-\d{7}\b"),
    re.compile(r"sk-[A-Za-z0-9_-]+"),
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+"),
]

CATEGORY_CONCEPTS = {
    "maintenance": ["Bike", "BrokenEvent", "MaintenanceSinkStation", "EvidenceEdge", "SourceArtifact"],
    "delivery": [
        "Station",
        "TripEvent",
        "NightReallocationOperationsOntology",
        "ReallocationAction",
        "ReallocationRoute",
        "WorkforceCapacityConstraint",
    ],
    "station": ["Station", "StationLifecycleEvent", "SourceArtifact", "EvidenceEdge"],
    "device": ["Bike", "StationLifecycleEvent", "SourceArtifact", "EvidenceEdge"],
    "disposal": ["BikeLifecyclePath", "BrokenEvent", "SourceArtifact", "ConfidenceAssessment"],
    "budget": ["MetricSemantics", "SourceArtifact", "ConfidenceAssessment"],
    "safety": ["BrokenEvent", "Risk State", "EvidenceEdge", "ConfidenceAssessment"],
    "operation": ["StationRoleProfile", "SourceArtifact", "ConfidenceAssessment", "EvidenceEdge"],
}
CATEGORY_RELATIONS = {
    "maintenance": ["supported_by", "derived_from", "same_bike"],
    "delivery": ["pickup_station", "dropoff_station", "has_route_cost", "constrained_by_capacity"],
    "station": ["supported_by", "derived_from", "in_time_bucket"],
    "device": ["supported_by", "derived_from"],
    "disposal": ["precedes", "followed_by", "supported_by"],
    "budget": ["supported_by", "derived_from"],
    "safety": ["supported_by", "has_confidence"],
    "operation": ["supported_by", "derived_from", "has_confidence"],
}
CATEGORY_LABELS = {
    "maintenance": "정비·유지관리",
    "delivery": "배송·재배치",
    "station": "대여소·거치대",
    "device": "단말기·장비",
    "disposal": "폐기·자산 처리",
    "budget": "예산·사업비",
    "safety": "안전관리",
    "operation": "운영계획",
}


@dataclass(frozen=True)
class RedactedDocumentTarget:
    nid: str
    title: str
    date: str
    department: str
    disclosure_status: str
    reason: str
    target_category: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceLink:
    source_type: str
    source_id: str
    source_title: str
    relation: str
    snippet_summary: str
    evidence_kind: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InferredRestoration:
    target_nid: str
    target_title: str
    inferred_sections: list[str]
    ontology_concepts: list[str]
    evidence_links: list[EvidenceLink]
    confidence: float
    not_reconstructed: list[str]
    sensitivity_guard: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_links"] = [link.to_dict() for link in self.evidence_links]
        return payload


@dataclass(frozen=True)
class EvidenceDocument:
    source_type: str
    source_id: str
    source_title: str
    text: str
    evidence_kind: str
    base_confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _run_stamp(timestamp: str) -> str:
    return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d_%H%M%S")


def _jsonl_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(_jsonl_line(record) + "\n")


def _sanitize_text(text: str, *, max_len: int | None = None) -> str:
    sanitized = text
    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if max_len is not None and len(sanitized) > max_len:
        sanitized = sanitized[: max_len - 3].rstrip() + "..."
    return sanitized


def _contains_any(text: str, keywords: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _category_for_title(title: str) -> str:
    scores: list[tuple[int, str]] = []
    for category, keywords in OPERATION_KEYWORDS.items():
        scores.append((sum(1 for keyword in keywords if keyword in title), category))
    score, category = max(scores)
    return category if score > 0 else "operation"


def _tokens(text: str) -> set[str]:
    tokens = set(re.findall(r"[0-9A-Za-z가-힣]{2,}", text.lower()))
    return {token for token in tokens if token not in {"공공자전거", "따릉이", "계획", "보고", "관련"}}


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "tools" / "scripts" / "rag" / "ttareungi_rag.py").exists():
            return candidate
    raise FileNotFoundError("Could not find OBYBK project root.")


def find_latest_manifest(project_root: Path) -> Path:
    manifests = sorted(project_root.glob(DEFAULT_MANIFEST_GLOB))
    if not manifests:
        raise FileNotFoundError(f"No all-period OpenGov manifest found under {project_root}.")
    return manifests[-1]


def load_manifest_documents(manifest_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return list(payload.get("documents", []))


def select_redacted_targets(
    manifest_documents: Sequence[dict[str, Any]],
) -> tuple[list[RedactedDocumentTarget], list[dict[str, str]]]:
    targets: list[RedactedDocumentTarget] = []
    excluded: list[dict[str, str]] = []
    for document in manifest_documents:
        if document.get("download_status") == "downloaded":
            continue
        title = str(document.get("title", ""))
        disclosure_status = str(document.get("공개구분") or document.get("list_disclosure") or "")
        reason = str(document.get("download_status") or "unknown")
        date = str(document.get("생산일자") or document.get("registered_date") or "")
        department = str(document.get("department") or document.get("부서명") or "")
        if _contains_any(title, SENSITIVE_KEYWORDS):
            excluded.append(
                {
                    "nid": str(document.get("nid", "")),
                    "title": title,
                    "date": date,
                    "department": department,
                    "disclosure_status": disclosure_status,
                    "reason": reason,
                    "handling": "meta_only",
                    "not_reconstructed": "민감정보/개인정보/보안/인사·조사 세부사항은 추정 복원하지 않는다.",
                }
            )
            continue
        if not any(keyword in title for keywords in OPERATION_KEYWORDS.values() for keyword in keywords):
            continue
        targets.append(
            RedactedDocumentTarget(
                nid=str(document.get("nid", "")),
                title=title,
                date=date,
                department=department,
                disclosure_status=disclosure_status,
                reason=reason,
                target_category=_category_for_title(title),
            )
        )
    return targets, excluded


def build_service_overview_text() -> str:
    return "\n".join(
        [
            "# Timestamp: 2026-05-18 10:58:00",
            "",
            "# 따릉이 서비스 운영 개요",
            "",
            "이 문서는 공개 결재문서와 OBYBK RAG/온톨로지 자산을 근거로 만든 derived reference다.",
            "따릉이는 대여소, 자전거, 단말기, 거치대, 운영 인력, 정비, 배송/재배치, 안전관리, 예산, 정보시스템으로 구성된 공공자전거 서비스다.",
            "운영 문서는 보통 추진 배경, 현황, 세부 추진계획, 예산/계약, 일정, 기대효과, 협조사항, 붙임 자료 구조를 가진다.",
            "정비 문서는 고장·노후 자전거, 부품 구매, 민간협업정비, 정비용역, 안전관리와 연결된다.",
            "배송/재배치 문서는 대여소별 부족·잉여, 운영 대수, 배송 차량 또는 인력, 야간/시간대별 이동, 집중관리 대여소와 연결된다.",
            "대여소/거치대/단말기 문서는 설치, 구매, 유지보수, 폐기, 교체, 운영 시스템과 연결된다.",
            "이 개요는 비공개 원문을 대체하지 않으며, 삭제/비공개 처리된 내용은 공개 근거 기반 추정으로만 다룬다.",
        ]
    ) + "\n"


def ensure_service_overview(project_root: Path, timestamp: str) -> Path:
    path = project_root / PROJECT_DOC_RELATIVE
    if path.exists():
        return path
    text = build_service_overview_text().replace("2026-05-18 10:58:00", timestamp)
    path.write_text(text, encoding="utf-8")
    return path


def _extract_pdf_text(project_root: Path, relative_path: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    path = project_root / relative_path
    if not path.exists():
        return ""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=20,
        )
        if result.returncode == 0:
            return _sanitize_text(result.stdout, max_len=max_chars)
    except Exception:
        return ""
    return ""


def _iter_rag_documents(project_root: Path, limit: int = 160) -> Iterable[EvidenceDocument]:
    path = project_root / RAG_DOCUMENTS_RELATIVE
    if not path.exists():
        return []
    selected: list[EvidenceDocument] = []
    keywords = ["운영", "정비", "배송", "대여소", "단말기", "거치대", "예산", "안전", "공공자전거", "따릉이"]
    for line in path.read_text(encoding="utf-8").splitlines():
        if len(selected) >= limit:
            break
        if not line.strip():
            continue
        record = json.loads(line)
        text = str(record.get("text", ""))
        metadata = record.get("metadata", {})
        source = metadata.get("source") or record.get("doc_id", "")
        if not _contains_any(text, keywords) and not _contains_any(str(source), keywords):
            continue
        selected.append(
            EvidenceDocument(
                source_type="rag_index",
                source_id=str(record.get("doc_id", "")),
                source_title=str(source),
                text=_sanitize_text(text, max_len=1400),
                evidence_kind="inferred",
                base_confidence=0.55,
                metadata=metadata if isinstance(metadata, dict) else {},
            )
        )
    return selected


def _load_latest_domain_ontology(project_root: Path) -> EvidenceDocument | None:
    paths = sorted(project_root.glob(DOMAIN_ONTOLOGY_GLOB))
    if not paths:
        return None
    payload = json.loads(paths[-1].read_text(encoding="utf-8"))
    text = " ".join(
        [
            str(payload.get("ontology_name", "")),
            str(payload.get("parent_ontology", "")),
            " ".join(payload.get("core_domain_classes", [])),
            " ".join(payload.get("v2_domain_classes", [])),
            " ".join(payload.get("relations", [])),
        ]
    )
    return EvidenceDocument(
        source_type="ontology_registry",
        source_id=str(paths[-1].relative_to(project_root)),
        source_title=str(payload.get("ontology_name", "domain ontology")),
        text=_sanitize_text(text, max_len=2200),
        evidence_kind="inferred",
        base_confidence=0.62,
        metadata={"path": str(paths[-1].relative_to(project_root))},
    )


def build_evidence_corpus(
    project_root: Path,
    manifest_documents: Sequence[dict[str, Any]],
    service_overview: str,
    max_pdf_chars: int = 4000,
) -> list[EvidenceDocument]:
    evidence: list[EvidenceDocument] = [
        EvidenceDocument(
            source_type="service_overview",
            source_id=str(PROJECT_DOC_RELATIVE),
            source_title="따릉이 서비스 운영 개요",
            text=_sanitize_text(service_overview, max_len=2400),
            evidence_kind="weak-context",
            base_confidence=0.45,
        )
    ]
    ontology_doc = _load_latest_domain_ontology(project_root)
    if ontology_doc:
        evidence.append(ontology_doc)
    for document in manifest_documents:
        if document.get("download_status") != "downloaded":
            continue
        title = str(document.get("title", ""))
        document_text_parts = [title]
        for relative in document.get("downloaded_files", [])[:3]:
            document_text_parts.append(_extract_pdf_text(project_root, str(relative), max_chars=max_pdf_chars))
        combined = _sanitize_text(" ".join(part for part in document_text_parts if part), max_len=max_pdf_chars + 600)
        if not combined:
            continue
        evidence.append(
            EvidenceDocument(
                source_type="public_pdf",
                source_id=str(document.get("nid", "")),
                source_title=title,
                text=combined,
                evidence_kind="derived",
                base_confidence=0.72,
                metadata={
                    "date": document.get("생산일자") or document.get("registered_date") or "",
                    "files": document.get("downloaded_files", []),
                },
            )
        )
    evidence.extend(_iter_rag_documents(project_root))
    return evidence


def _evidence_score(target: RedactedDocumentTarget, evidence: EvidenceDocument) -> float:
    target_tokens = _tokens(f"{target.title} {target.target_category}")
    evidence_tokens = _tokens(f"{evidence.source_title} {evidence.text}")
    overlap = len(target_tokens & evidence_tokens)
    category_hits = sum(
        1 for keyword in OPERATION_KEYWORDS.get(target.target_category, []) if keyword in evidence.text
    )
    year_bonus = 0.0
    if target.date[:4] and target.date[:4] in str(evidence.metadata.get("date", "")):
        year_bonus = 1.5
    source_bonus = {"public_pdf": 2.0, "ontology_registry": 1.4, "rag_index": 1.0, "service_overview": 0.8}.get(
        evidence.source_type, 0.5
    )
    return overlap * 1.8 + category_hits * 2.2 + year_bonus + source_bonus


def _summarize_evidence(doc: EvidenceDocument, category: str) -> str:
    category_label = CATEGORY_LABELS.get(category, "운영")
    title = _sanitize_text(doc.source_title, max_len=90)
    if doc.source_type == "public_pdf":
        summary = f"공개 PDF `{title}`에서 {category_label} 유형의 문서 구조와 운영 항목이 확인됨."
    elif doc.source_type == "ontology_registry":
        summary = f"온톨로지 registry `{title}`가 {category_label} 문서를 SourceArtifact와 EvidenceEdge 관계로 분류하는 근거를 제공함."
    elif doc.source_type == "rag_index":
        summary = f"기존 RAG 문서 `{title}`가 {category_label} 관련 source routing 및 운영 맥락 근거를 제공함."
    elif doc.source_type == "service_overview":
        summary = f"`{title}`가 따릉이 서비스의 {category_label} 운영 구성요소를 derived reference로 설명함."
    else:
        summary = f"`{title}`가 {category_label} 관련 공개 근거로 사용됨."
    return _sanitize_text(summary, max_len=220)


def _build_sections(target: RedactedDocumentTarget, links: Sequence[EvidenceLink]) -> list[str]:
    category = target.target_category
    common = {
        "maintenance": "정비·유지관리 문서로서 운영 현황, 정비 대상, 용역 또는 민간협업 방식, 일정, 기대효과가 포함되었을 가능성이 높다.",
        "delivery": "배송·재배치 운영 문서로서 대여소별 부족/잉여 대응, 배송 인력 또는 차량 운용, 시간대별 우선순위가 포함되었을 가능성이 높다.",
        "station": "대여소·거치대 운영 문서로서 설치/구매/유지보수 대상, 위치 또는 수량 관리, 현장 적용 일정이 포함되었을 가능성이 높다.",
        "device": "단말기 운영 문서로서 구매, 교체, 유지보수, 폐기 또는 운영 방식 변경이 포함되었을 가능성이 높다.",
        "disposal": "노후 자전거·단말기 폐기 문서로서 대상 선정, 폐기 절차, 자산 처리, 후속 보충 계획이 포함되었을 가능성이 높다.",
        "budget": "예산 문서로서 대행사업비, 낙찰차액, 예산 전용/이월, 사업 항목별 재원 배분이 포함되었을 가능성이 높다.",
        "safety": "안전관리 문서로서 위험성 평가, 사고 예방, 작업 안전, 재발방지 또는 안전보건 이행 항목이 포함되었을 가능성이 높다.",
        "operation": "운영계획 문서로서 추진 배경, 현황, 실행 절차, 담당 조직, 일정, 협조사항이 포함되었을 가능성이 높다.",
    }
    sections = [
        common.get(category, common["operation"]),
        "공개 근거 문서들의 반복 구조상 `추진 배경 -> 현황 -> 세부계획 -> 일정/예산 -> 기대효과/협조사항` 형태였을 가능성이 높다.",
    ]
    if any(link.source_type == "ontology_registry" for link in links):
        sections.append(
            "온톨로지 관점에서는 해당 문서를 SourceArtifact로 보고, 운영 대상 Station/Bike/TripEvent 및 EvidenceEdge 관계로 근거를 연결한다."
        )
    if category == "delivery":
        sections.append(
            "NightReallocationOperationsOntology 관점에서는 ReallocationAction, ReallocationRoute, WorkforceCapacityConstraint와 연결되는 운영 지시 또는 계획 문서로 해석한다."
        )
    return sections


def infer_restoration(target: RedactedDocumentTarget, evidence_docs: Sequence[EvidenceDocument]) -> InferredRestoration:
    ranked = sorted(
        ((doc, _evidence_score(target, doc)) for doc in evidence_docs),
        key=lambda item: item[1],
        reverse=True,
    )
    links: list[EvidenceLink] = []
    for doc, score in ranked[:5]:
        if score <= 0:
            continue
        confidence = min(0.92, doc.base_confidence + min(score, 12.0) / 60.0)
        evidence_kind = doc.evidence_kind if doc.evidence_kind != "direct" else "derived"
        links.append(
            EvidenceLink(
                source_type=doc.source_type,
                source_id=doc.source_id,
                source_title=_sanitize_text(doc.source_title, max_len=120),
                relation=CATEGORY_RELATIONS.get(target.target_category, ["supported_by"])[0],
                snippet_summary=_summarize_evidence(doc, target.target_category),
                evidence_kind=evidence_kind,
                confidence=round(confidence, 2),
            )
        )
    if not links:
        links.append(
            EvidenceLink(
                source_type="service_overview",
                source_id=str(PROJECT_DOC_RELATIVE),
                source_title="따릉이 서비스 운영 개요",
                relation="weak-context",
                snippet_summary="공개 근거가 부족해 제목과 서비스 운영 개요 수준에서만 추정한다.",
                evidence_kind="weak-context",
                confidence=0.35,
            )
        )
    concepts = sorted(set(CATEGORY_CONCEPTS.get(target.target_category, CATEGORY_CONCEPTS["operation"])))
    avg_confidence = round(sum(link.confidence for link in links) / len(links), 2)
    not_reconstructed = [
        "비공개 원문의 문장, 표, 금액, 담당자명, 전화번호, 결재선은 복원하지 않는다.",
        "개인정보, 보안 취약점, 인사/채용/조사 세부사항은 추정하지 않는다.",
        "공개 근거로 확인되지 않는 정확 수량과 일정은 단정하지 않는다.",
    ]
    return InferredRestoration(
        target_nid=target.nid,
        target_title=_sanitize_text(target.title, max_len=160),
        inferred_sections=_build_sections(target, links),
        ontology_concepts=concepts,
        evidence_links=links,
        confidence=avg_confidence,
        not_reconstructed=not_reconstructed,
        sensitivity_guard="passed",
    )


def _report(
    timestamp: str,
    targets: Sequence[RedactedDocumentTarget],
    restorations: Sequence[InferredRestoration],
    excluded: Sequence[dict[str, str]],
    manifest_path: Path,
) -> str:
    lines = [
        f"# Timestamp: {timestamp}",
        "",
        "# 따릉이 비공개/삭제 처리 문서 근거 기반 추정 복원 보고서",
        "",
        "이 보고서는 **원문 복원이 아니라 근거 기반 추정**이다. 비공개 원문을 우회하거나 숨겨진 내용을 추출하지 않았고, 공개 자료·RAG·온톨로지 관계로 설명 가능한 범위만 요약한다.",
        "",
        "## 실행 요약",
        "",
        f"- manifest: `{manifest_path}`",
        f"- candidate_targets: `{len(targets)}`",
        f"- inferred_restorations: `{len(restorations)}`",
        f"- meta_only_exclusions: `{len(excluded)}`",
        "",
        "## 복원 제외 원칙",
        "",
        "- 개인정보, 보안 취약점, 인사/채용, 비위/조사, 개인 연락처는 복원하지 않는다.",
        "- 비공개 원문 자체에는 `direct` evidence를 부여하지 않는다.",
        "- 금액, 담당자, 결재선, 세부 일정은 공개 근거가 명확하지 않으면 단정하지 않는다.",
        "",
        "## 대상별 추정",
        "",
    ]
    for restoration in restorations:
        lines.extend(
            [
                f"### {restoration.target_nid} {restoration.target_title}",
                "",
                f"- confidence: `{restoration.confidence}`",
                f"- ontology_concepts: `{', '.join(restoration.ontology_concepts)}`",
                "- 추정 복원 내용:",
            ]
        )
        for section in restoration.inferred_sections:
            lines.append(f"  - {section}")
        lines.append("- 근거:")
        for link in restoration.evidence_links:
            lines.append(
                f"  - `{link.evidence_kind}` confidence=`{link.confidence}` source=`{link.source_type}:{link.source_id}` "
                f"relation=`{link.relation}` summary={link.snippet_summary}"
            )
        lines.append("- 복원 제외:")
        for item in restoration.not_reconstructed:
            lines.append(f"  - {item}")
        lines.append("")
    if excluded:
        lines.extend(["## Meta-only 제외 문서", ""])
        for item in excluded[:120]:
            lines.append(f"- `{item['nid']}` {item['title']} reason={item['not_reconstructed']}")
    return "\n".join(lines) + "\n"


def _write_outputs(
    run_dir: Path,
    timestamp: str,
    targets: Sequence[RedactedDocumentTarget],
    restorations: Sequence[InferredRestoration],
    excluded: Sequence[dict[str, str]],
    manifest_path: Path,
) -> None:
    _write_jsonl(run_dir / "candidate_documents.jsonl", [target.to_dict() for target in targets])
    _write_jsonl(run_dir / "inferred_restorations.jsonl", [restoration.to_dict() for restoration in restorations])
    links: list[dict[str, Any]] = []
    for restoration in restorations:
        for link in restoration.evidence_links:
            payload = link.to_dict()
            payload["target_nid"] = restoration.target_nid
            links.append(payload)
    _write_jsonl(run_dir / "evidence_links.jsonl", links)
    with (run_dir / "not_reconstructed.csv").open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["nid", "title", "date", "department", "disclosure_status", "reason", "handling", "not_reconstructed"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in excluded:
            writer.writerow(item)
        for restoration in restorations:
            writer.writerow(
                {
                    "nid": restoration.target_nid,
                    "title": restoration.target_title,
                    "date": "",
                    "department": "",
                    "disclosure_status": "",
                    "reason": "guarded_fields",
                    "handling": "excluded_fields",
                    "not_reconstructed": " | ".join(restoration.not_reconstructed),
                }
            )
    (run_dir / "summary_report.md").write_text(
        _report(timestamp, targets, restorations, excluded, manifest_path),
        encoding="utf-8",
    )


def run_inference(
    project_root: Path,
    manifest_path: Path | None = None,
    output_root: Path | None = None,
    timestamp: str | None = None,
    max_pdf_chars: int = 4000,
    max_targets: int | None = None,
    publish_project_report: bool = True,
) -> Path:
    timestamp = timestamp or _now()
    manifest_path = manifest_path or find_latest_manifest(project_root)
    if not manifest_path.is_absolute():
        manifest_path = project_root / manifest_path
    output_root = output_root or project_root / DEFAULT_OUTPUT_ROOT
    run_dir = output_root / f"run_{_run_stamp(timestamp)}_ttareungi_redaction_inference"
    run_dir.mkdir(parents=True, exist_ok=True)

    overview_path = ensure_service_overview(project_root, timestamp)
    service_overview = overview_path.read_text(encoding="utf-8")
    documents = load_manifest_documents(manifest_path)
    targets, excluded = select_redacted_targets(documents)
    if max_targets is not None:
        targets = targets[:max_targets]
    evidence_docs = build_evidence_corpus(project_root, documents, service_overview, max_pdf_chars=max_pdf_chars)
    restorations = [infer_restoration(target, evidence_docs) for target in targets]
    _write_outputs(run_dir, timestamp, targets, restorations, excluded, manifest_path)

    if publish_project_report:
        docs_report = project_root / "docs" / "project" / "ttareungi_deleted_content_inference_report.md"
        docs_report.write_text((run_dir / "summary_report.md").read_text(encoding="utf-8"), encoding="utf-8")
    return run_dir


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Infer guarded summaries for redacted Ttareungi OpenGov documents.")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--max-pdf-chars", type=int, default=4000)
    parser.add_argument("--max-targets", type=int, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    project_root = args.project_root.resolve() if args.project_root else find_project_root()
    run_dir = run_inference(
        project_root=project_root,
        manifest_path=args.manifest,
        output_root=args.output_root,
        timestamp=args.timestamp,
        max_pdf_chars=args.max_pdf_chars,
        max_targets=args.max_targets,
    )
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
