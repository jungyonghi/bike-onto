# Timestamp: 2026-04-21 23:24:00
# Timestamp: 2026-04-21 23:26:00
# Timestamp: 2026-04-21 23:29:00
# Timestamp: 2026-04-21 23:33:00
# Timestamp: 2026-04-21 23:46:00
# Timestamp: 2026-04-21 23:58:00
# Timestamp: 2026-04-21 23:47:20
# Timestamp: 2026-04-21 23:47:20
# Timestamp: 2026-04-21 23:51:43
# Timestamp: 2026-04-21 23:56:00
# Timestamp: 2026-04-27 17:46:00
# Timestamp: 2026-04-27 18:40:00
# Timestamp: 2026-04-27 19:00:00
# Timestamp: 2026-05-11 10:43:10
# Timestamp: 2026-05-11 11:24:00
# Timestamp: 2026-05-11 12:09:05
# Timestamp: 2026-05-11 12:56:21
# Timestamp: 2026-05-11 13:43:00
# Timestamp: 2026-05-18 15:15:06

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Sequence
import zipfile

import numpy as np


try:
    import faiss
except Exception:  # pragma: no cover - exercised only when faiss is unavailable.
    faiss = None


PROFILE_ONTOLOGY_HYBRID = "ontology-hybrid"
PROFILE_DB_ONLY = "db-only"
PROFILE_CHOICES = (PROFILE_ONTOLOGY_HYBRID, PROFILE_DB_ONLY)
DEFAULT_RAG_PROFILE = PROFILE_ONTOLOGY_HYBRID

DEFAULT_INDEX_DIR_NAME = "ttareungi_rag_index"
DB_ONLY_INDEX_DIR_NAME = "ttareungi_rag_index_db_only"
DEFAULT_EMBEDDING_DIM = 384
SENTENCE_TRANSFORMER_INDEX_BATCH_SIZE = 1
DEFAULT_LIGHTWEIGHT_SENTENCE_TRANSFORMER_MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_SENTENCE_TRANSFORMER_MODEL_ENV = "TTAREUNGI_EMBEDDING_MODEL_PATH"
DEFAULT_QWEN3_EMBEDDING_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_QWEN3_EMBEDDING_LOCAL_PATH = Path("/home/user/Documents/11_Models/Qwen3-Embedding-0.6B")
DEFAULT_SENTENCE_TRANSFORMER_CACHE_CANDIDATES = (
    Path.home() / ".cache" / "huggingface" / "hub" / "models--Qwen--Qwen3-Embedding-0.6B",
)
LEGACY_KANANA_EMBEDDING_MODEL_PATH = Path("/home/user/Documents/11_Models/kanana-nano-2.1b-embedding")
SENTENCE_TRANSFORMER_WEIGHT_FILENAMES = ("model.safetensors", "pytorch_model.bin")
DEFAULT_LLM_URL = "http://127.0.0.1:18080/v1/chat/completions"
DEFAULT_QWEN_MODEL = "qwen3-lightweight"
LLM_PROVIDER_LOCAL = "local"
LLM_PROVIDER_OPENAI = "openai"
LLM_PROVIDER_CHOICES = (LLM_PROVIDER_LOCAL, LLM_PROVIDER_OPENAI)
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.2"
DEFAULT_OPENAI_API_KEY_FILE = Path("config/openai_api_key.local")
DEFAULT_OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
REPOSITORY_ONTOLOGY_ARTIFACT_DIR_ENV = "TTAREUNGI_REPOSITORY_ONTOLOGY_ARTIFACT_DIR"
REPOSITORY_ONTOLOGY_ARTIFACT_FILENAMES = ("ontology_seed.json", "reviewed_ontology_blueprint.md")

DATASET_FILENAMES = [
    "branch_data.parquet",
    "broken_data.parquet",
    "count_data.parquet",
    "rent_data.parquet",
    "uselate_data.parquet",
    "weather_data.parquet",
    "newmeta.parquet",
]

PARQUET_CATALOG_FILENAMES = [
    *DATASET_FILENAMES,
    "master_branch_data.parquet",
    "meta.parquet",
]
PANDAS_AGGREGATE_MAX_ROWS = 200_000
PANDAS_AGGREGATE_SCAN_SIZE_LIMIT_BYTES = 64 * 1024 * 1024

REFERENCE_DOCS = [
    "README.md",
    "docs/project/aiplan.md",
    "docs/project/[데이터 수집 및 저장]수집 데이터.md",
    "docs/project/skn23_4_requirements.md",
    "docs/architecture/architecture.mmd",
]

ONTOLOGY_BUNDLE_GLOB = "_download_ontology_bundle_*.json"
ONTOLOGY_STRUCTURED_DATASET_IDS = {
    "OA-15182",
    "OA-22382",
    "OA-22300",
    "OA-22657",
    "OA-21222",
    "OA-21226",
    "OA-21228",
    "OA-15493",
    "OA-714",
    "OA-12849",
}
ONTOLOGY_DOCUMENT_CATEGORIES = {"service", "policy", "sanction", "press", "procurement", "api_specs"}
BLOCKED_NOTE_TOKENS = ("blocked_or_unavailable", "exception=")
HWP_EXTENSIONS = {".hwp", ".hwpx"}

ONTOLOGY_DATASET_PURPOSES = {
    "OA-15182": "연도별 대여/반납 흐름과 시계열 이용 패턴을 확인한다.",
    "OA-22382": "대여소 가용 수량과 재배치 수요를 추적한다.",
    "OA-22300": "수도권 행정동 간 생활이동 원천을 확인한다.",
    "OA-22657": "수단별 수도권 생활이동과 환승 연계 패턴을 본다.",
    "OA-21222": "정류장/역사 단위 대중교통 출도착과 거점 연결 구조를 본다.",
    "OA-21226": "행정동 단위 대중교통 유입/유출을 본다.",
    "OA-21228": "행정동 단위 목적 기반 출도착 패턴을 본다.",
    "OA-15493": "실시간 대여 가능 자전거와 API 접근 방식을 확인한다.",
    "OA-714": "자전거도로 인프라 현황과 접근 방식을 확인한다.",
    "OA-12849": "자전거 사고·안전 관련 공개 통계 접근 방식을 확인한다.",
}
ONTOLOGY_QUERY_AXES = {
    "OA-15182": "연도, 대여소, 대여/반납 시간, 자전거별 이동 이력",
    "OA-22382": "대여소, 분기, 시간 단위 가용 수량, 운영 가용성",
    "OA-22300": "출발 행정동, 도착 행정동, 이동 목적, 일자",
    "OA-22657": "출발/도착 행정동, 교통수단, 일자",
    "OA-21222": "정류장/역사, 수단, 출발지/도착지, 일자",
    "OA-21226": "행정동, 출도착 승객수, 일자",
    "OA-21228": "행정동, 이동 목적, 출도착 승객수, 일자",
    "OA-15493": "실시간 API, 대여소, 가용 대수, 거치율",
    "OA-714": "연도, 자전거도로 유형, 통계 시트",
    "OA-12849": "사고 통계, 안전, 자전거, 시트/통계 접근",
}

PARQUET_DATASET_PURPOSES = {
    "branch_data.parquet": "대여소 번호, 이름, 자치구, 주소, 좌표, 운영방식 기준의 대여소 프로필을 확인한다.",
    "broken_data.parquet": "자전거 고장 유형과 점검/수리 우선순위 후보를 확인한다.",
    "count_data.parquet": "대여소/일자 단위 이용량 집계와 대여/반납 수요를 확인한다.",
    "rent_data.parquet": "대여/반납 이벤트 흐름과 이동 이용 패턴을 집계 단위로 확인한다.",
    "uselate_data.parquet": "지연 또는 연체 이용 패턴을 확인한다.",
    "weather_data.parquet": "기온, 강수량, 풍속 등 날씨 조건과 이용 맥락을 확인한다.",
    "newmeta.parquet": "신규가입자 성별/연령/기간 메타 정보를 확인한다.",
    "master_branch_data.parquet": "대여소 master 기준의 전체 대여소 속성을 확인한다.",
    "meta.parquet": "운영 데이터 메타/보조 정보를 확인한다.",
}
PARQUET_QUERY_AXES = {
    "branch_data.parquet": "대여소 번호, 대여소명, 자치구, 주소, 좌표, 최신 기준일",
    "broken_data.parquet": "고장일, 자전거 번호, 고장 유형, 유형별 건수",
    "count_data.parquet": "일자, 대여소, 대여 건수, 반납 건수, 이용량",
    "rent_data.parquet": "대여일시, 대여 대여소, 반납 대여소, 거리, 이용 흐름",
    "uselate_data.parquet": "일자, 대여소, 지연/연체 건수",
    "weather_data.parquet": "시간, 기온, 강수량, 풍속",
    "newmeta.parquet": "가입 기준월, 연령, 성별, 신규가입자 수",
    "master_branch_data.parquet": "대여소 번호, 대여소명, 위치, 운영 속성",
    "meta.parquet": "메타 기준일, source, row 수, 보조 속성",
}
PARQUET_GRANULARITIES = {
    "branch_data.parquet": "station",
    "broken_data.parquet": "fault_event",
    "count_data.parquet": "station_daily_count",
    "rent_data.parquet": "trip_event_aggregate",
    "uselate_data.parquet": "late_usage",
    "weather_data.parquet": "hourly_weather",
    "newmeta.parquet": "signup_monthly",
    "master_branch_data.parquet": "station_master",
    "meta.parquet": "metadata",
}

DB_ONLY_SOURCE_ALIASES = {
    "newmeta.parquet": [
        "신규가입자",
        "신규 가입자",
        "가입자",
        "연령",
        "성별",
        "age",
        "gender",
        "signup",
    ],
    "pricing_info": [
        "요금",
        "이용요금",
        "이용권",
        "정기권",
        "1시간권",
        "결제",
        "가격",
        "pricing",
    ],
    "g2b_r26bk01319050_file1": [
        "정비용역",
        "정비 용역",
        "공공자전거 정비",
        "조달",
        "입찰",
        "나라장터",
        "procurement",
    ],
    "g2b_r26bk01319050_file3": [
        "정비용역",
        "정비 용역",
        "공공자전거 정비",
        "조달",
        "입찰",
        "나라장터",
        "procurement",
    ],
}

DB_ONLY_CATEGORY_ALIASES = {
    "procurement": ["정비용역", "공공자전거 정비", "조달", "입찰", "나라장터"],
    "service": ["서비스", "이용요금", "요금", "이용권", "정기권", "약관"],
    "policy": ["정책", "계획", "공시", "활성화"],
    "api_specs": ["실시간", "API", "대여정보"],
}

DB_ONLY_QUESTION_TYPE_BY_SOURCE = {
    "branch_data.parquet": "station_lookup",
    "broken_data.parquet": "fault",
    "count_data.parquet": "usage",
    "rent_data.parquet": "usage",
    "uselate_data.parquet": "late_usage",
    "weather_data.parquet": "weather",
    "newmeta.parquet": "signup",
    "master_branch_data.parquet": "station_master",
    "meta.parquet": "metadata",
    "pricing_info": "service_doc",
    "g2b_r26bk01319050_file1": "procurement_doc",
    "g2b_r26bk01319050_file3": "procurement_doc",
}
TIME_COLUMN_HINTS = (
    "date",
    "datetime",
    "time",
    "dt",
    "month",
    "year",
    "일자",
    "일시",
    "시간",
    "월",
    "년",
)


@dataclass(frozen=True)
class RagDocument:
    doc_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    document: RagDocument
    score: float
    rank: int


@dataclass(frozen=True)
class FactSnippet:
    title: str
    text: str
    source: str


@dataclass(frozen=True)
class LlmRuntimeSettings:
    llm_url: str
    model: str
    api_key: str


@dataclass(frozen=True)
class ParquetDatasetProfile:
    dataset_name: str
    source: str
    row_count: int
    columns: list[str]
    schema: str
    row_group_count: int
    size_bytes: int
    time_columns: list[str]
    query_axes: str
    granularity: str
    read_error: str = ""


@dataclass(frozen=True)
class StructuredFactQuery:
    question: str
    terms: list[str]
    dataset_hints: list[str]
    column_hints: list[str]
    time_hints: list[str]
    station_terms: list[str]


class HashingEmbedder:
    """Small deterministic embedder for zero-setup local retrieval."""

    name = "hashing"

    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row_index, text in enumerate(texts):
            for feature, weight in _text_features(text):
                digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
                bucket = int.from_bytes(digest[:4], "little") % self.dim
                matrix[row_index, bucket] += weight
        return _normalize_rows(matrix)


class SentenceTransformerEmbedder:
    name = "sentence-transformers"

    def __init__(self, model_path: Path | str, device: str = "cpu") -> None:
        from sentence_transformers import SentenceTransformer

        self.model_path = model_path
        self.device = device
        self.model = SentenceTransformer(str(model_path), trust_remote_code=True, device=device)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        embeddings = self.model.encode(
            list(texts),
            normalize_embeddings=True,
            batch_size=SENTENCE_TRANSFORMER_INDEX_BATCH_SIZE,
        )
        return np.asarray(embeddings, dtype=np.float32)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _text_features(text: str) -> list[tuple[str, float]]:
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    tokens = re.findall(r"[0-9a-zA-Z가-힣]+", normalized)
    features: list[tuple[str, float]] = []
    for token in tokens:
        features.append((token, 3.0))
        if len(token) >= 3:
            features.extend((token[i : i + 2], 0.7) for i in range(len(token) - 1))
            features.extend((token[i : i + 3], 1.0) for i in range(len(token) - 2))
    return features


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_profile(profile: str | None = None) -> str:
    resolved = (profile or DEFAULT_RAG_PROFILE).strip().lower()
    if resolved not in PROFILE_CHOICES:
        raise ValueError(f"profile must be one of: {', '.join(PROFILE_CHOICES)}")
    return resolved


def _doc_to_json(document: RagDocument) -> str:
    payload = asdict(document)
    payload["# Timestamp"] = _now()
    return json.dumps(payload, ensure_ascii=False)


def _json_to_doc(line: str) -> RagDocument:
    payload = json.loads(line)
    return RagDocument(
        doc_id=payload["doc_id"],
        text=payload["text"],
        metadata=payload.get("metadata", {}),
    )


def create_embedder(
    backend: str = "auto",
    model_path: str | Path | None = None,
    dim: int = DEFAULT_EMBEDDING_DIM,
) -> HashingEmbedder | SentenceTransformerEmbedder:
    if backend == "hashing":
        return HashingEmbedder(dim=dim)

    if backend == "sentence-transformers":
        candidates = (
            [Path(model_path).expanduser()] if model_path is not None else _default_sentence_transformer_model_candidates()
        )
        resolved_model = candidates[0] if candidates else DEFAULT_QWEN3_EMBEDDING_MODEL_ID
        return SentenceTransformerEmbedder(resolved_model)

    if backend != "auto":
        raise ValueError("backend must be one of: auto, hashing, sentence-transformers")

    model_candidates: list[Path | str] = (
        [Path(model_path).expanduser()] if model_path is not None else _default_sentence_transformer_model_candidates()
    )
    for candidate in model_candidates:
        if isinstance(candidate, Path) and not _is_complete_sentence_transformer_path(candidate):
            continue
        try:
            return SentenceTransformerEmbedder(candidate)
        except Exception:
            continue
    return HashingEmbedder(dim=dim)


def create_embedder_for_index(
    index_dir: Path,
    backend: str = "auto",
    dim: int = DEFAULT_EMBEDDING_DIM,
) -> HashingEmbedder | SentenceTransformerEmbedder:
    if backend != "auto":
        return create_embedder(backend=backend, dim=dim)

    manifest = _load_index_manifest(index_dir)
    manifest_backend = str(manifest.get("embedding_backend", ""))
    manifest_model = manifest.get("embedding_model")
    if manifest_backend == "sentence-transformers" and manifest_model:
        return SentenceTransformerEmbedder(str(manifest_model))
    if manifest_backend == "hashing":
        return HashingEmbedder(dim=int(manifest.get("embedding_dim", dim)))
    return create_embedder(backend=backend, dim=dim)


def _default_sentence_transformer_model_candidates() -> list[Path | str]:
    candidates: list[Path | str] = []
    env_model_path = os.environ.get(DEFAULT_SENTENCE_TRANSFORMER_MODEL_ENV)
    if env_model_path:
        candidate = Path(env_model_path).expanduser()
        if _is_complete_sentence_transformer_path(candidate):
            candidates.append(candidate)
    if _is_complete_sentence_transformer_path(DEFAULT_QWEN3_EMBEDDING_LOCAL_PATH):
        candidates.append(DEFAULT_QWEN3_EMBEDDING_LOCAL_PATH)
    for cache_root in DEFAULT_SENTENCE_TRANSFORMER_CACHE_CANDIDATES:
        snapshot_path = _latest_hf_snapshot(cache_root)
        if snapshot_path is not None and _is_complete_sentence_transformer_path(snapshot_path):
            candidates.append(snapshot_path)
    candidates.append(DEFAULT_QWEN3_EMBEDDING_MODEL_ID)
    candidates.append(DEFAULT_LIGHTWEIGHT_SENTENCE_TRANSFORMER_MODEL_ID)
    return candidates


def _is_complete_sentence_transformer_path(path: Path) -> bool:
    return (
        path.exists()
        and (path / "modules.json").exists()
        and (path / "config_sentence_transformers.json").exists()
        and any((path / filename).exists() for filename in SENTENCE_TRANSFORMER_WEIGHT_FILENAMES)
    )


def _latest_hf_snapshot(cache_root: Path) -> Path | None:
    snapshots_dir = cache_root / "snapshots"
    ref_path = cache_root / "refs" / "main"
    if ref_path.exists():
        revision = ref_path.read_text(encoding="utf-8").strip()
        snapshot = snapshots_dir / revision
        if snapshot.exists():
            return snapshot
    if not snapshots_dir.exists():
        return None
    candidates = [path for path in snapshots_dir.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_index_manifest(index_dir: Path) -> dict[str, Any]:
    manifest_path = index_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    return _read_json(manifest_path)


def index_is_ready(index_dir: Path) -> bool:
    manifest = _load_index_manifest(index_dir)
    documents_file = manifest.get("documents_file", "documents.jsonl")
    index_file = manifest.get("index_file")
    if not (index_dir / documents_file).exists():
        return False
    if index_file and (index_dir / index_file).exists():
        return True
    return (index_dir / "index.faiss").exists() or (index_dir / "embeddings.npy").exists()


def build_faiss_index(
    documents: Sequence[RagDocument],
    index_dir: Path,
    embedder: HashingEmbedder | SentenceTransformerEmbedder,
    extra_manifest: dict[str, Any] | None = None,
) -> None:
    if not documents:
        raise ValueError("documents must not be empty")

    index_dir.mkdir(parents=True, exist_ok=True)
    embeddings = np.asarray(embedder.encode([doc.text for doc in documents]), dtype=np.float32)
    embeddings = _normalize_rows(embeddings)

    if faiss is not None:
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)
        index_file = "index.faiss"
        index_backend = "faiss.IndexFlatIP"
        faiss.write_index(index, str(index_dir / index_file))
    else:
        index_file = "embeddings.npy"
        index_backend = "numpy-dot-product"
        np.save(index_dir / index_file, embeddings)

    (index_dir / "documents.jsonl").write_text(
        "\n".join(_doc_to_json(document) for document in documents) + "\n",
        encoding="utf-8",
    )
    manifest_payload = {
        "# Timestamp": _now(),
        "doc_count": len(documents),
        "embedding_backend": getattr(embedder, "name", type(embedder).__name__),
        "embedding_model": str(getattr(embedder, "model_path", "")),
        "embedding_device": str(getattr(embedder, "device", "")),
        "embedding_dim": int(embeddings.shape[1]),
        "index_backend": index_backend,
        "index_file": index_file,
        "documents_file": "documents.jsonl",
    }
    if extra_manifest:
        manifest_payload.update(extra_manifest)
    _write_json(index_dir / "manifest.json", manifest_payload)


def _load_index_documents(index_dir: Path) -> list[RagDocument]:
    docs_path = index_dir / "documents.jsonl"
    if not docs_path.exists():
        raise FileNotFoundError(f"Missing index documents file: {docs_path}")
    return [_json_to_doc(line) for line in docs_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def search_faiss_index(
    query: str,
    index_dir: Path,
    embedder: HashingEmbedder | SentenceTransformerEmbedder,
    top_k: int = 5,
) -> list[SearchResult]:
    if top_k <= 0:
        return []

    documents = _load_index_documents(index_dir)
    query_embedding = np.asarray(embedder.encode([query]), dtype=np.float32)
    query_embedding = _normalize_rows(query_embedding)
    candidate_k = min(max(top_k * 20, 50), len(documents))
    manifest = _load_index_manifest(index_dir)
    index_file = manifest.get("index_file", "index.faiss")
    index_path = index_dir / index_file
    if not index_path.exists():
        raise FileNotFoundError(f"Missing vector index: {index_path}")

    if index_path.suffix == ".faiss" and faiss is not None:
        index = faiss.read_index(str(index_path))
        scores, indices = index.search(query_embedding, candidate_k)
    else:
        embeddings = np.load(index_path)
        similarities = embeddings @ query_embedding[0]
        ordered_indices = np.argsort(similarities)[::-1][:candidate_k]
        scores = np.asarray([similarities[ordered_indices]], dtype=np.float32)
        indices = np.asarray([ordered_indices], dtype=np.int64)

    scored: dict[int, float] = {}
    for score, doc_index in zip(scores[0], indices[0]):
        if doc_index < 0:
            continue
        scored[int(doc_index)] = float(score)

    for doc_index, document in enumerate(documents):
        lexical_score = _lexical_overlap_score(query, document.text)
        source_score = _source_hint_score(query, document)
        metadata_score = _metadata_match_score(query, document)
        if lexical_score > 0 or source_score > 0 or metadata_score > 0:
            scored[doc_index] = (
                scored.get(doc_index, 0.0)
                + min(lexical_score, 1.5)
                + source_score
                + metadata_score
            )

    ordered = _apply_source_diversity(
        sorted(scored.items(), key=lambda item: item[1], reverse=True),
        documents,
        top_k,
    )
    return [
        SearchResult(document=documents[doc_index], score=float(score), rank=rank)
        for rank, (doc_index, score) in enumerate(ordered, start=1)
    ]


def _lexical_overlap_score(query: str, text: str) -> float:
    query_terms = _question_terms(query)
    if not query_terms:
        return 0.0
    normalized_text = text.lower()
    score = 0.0
    for term in query_terms:
        term_lower = term.lower()
        if term_lower in normalized_text:
            score += 0.35 if len(term_lower) <= 2 else 0.75
    return score


def _metadata_match_score(query: str, document: RagDocument) -> float:
    text = current_question_text(query).lower()
    terms = [term.lower() for term in _question_terms(text)]
    metadata = document.metadata
    dataset_name = str(metadata.get("dataset_name") or metadata.get("source", "")).lower()
    granularity = str(metadata.get("granularity", "")).lower()
    query_axes = str(metadata.get("query_axes", "")).lower()
    columns = [str(column).lower() for column in metadata.get("columns", [])]
    alias_text = _flatten_metadata_value(metadata.get("aliases", "")).lower()
    authority_text = _flatten_metadata_value(metadata.get("source_authority", "")).lower()
    question_type = _flatten_metadata_value(metadata.get("question_type", "")).lower()
    doc_key = _flatten_metadata_value(metadata.get("doc_key", "")).lower()
    category = _flatten_metadata_value(metadata.get("category", "")).lower()
    metadata_text = " ".join([alias_text, authority_text, question_type, doc_key, category])
    score = 0.0

    for term in terms:
        if term and term in dataset_name:
            score += 0.8
        if term and term in granularity:
            score += 0.5
        if term and term in query_axes:
            score += 0.4
        if term in columns:
            score += 1.0
        if term and term in metadata_text:
            score += 0.9

    for column in columns:
        if column and column in text:
            score += 0.8
    for alias in [alias.strip().lower() for alias in _flatten_metadata_value(metadata.get("aliases", "")).split()]:
        if alias and alias in text:
            score += 1.1

    granularity_hints = [
        (["날씨", "기온", "강수", "풍속", "temperature", "precipitation"], "weather", 0.9),
        (["고장", "장애", "수리", "점검"], "fault", 0.9),
        (["대여소", "주소", "자치구", "위치"], "station", 0.7),
        (["대여", "반납", "이용량", "거리"], "trip", 0.7),
        (["가입", "신규", "연령", "성별"], "signup", 0.7),
        (["요금", "이용권", "정기권", "결제"], "service_doc", 1.0),
        (["정비용역", "조달", "입찰", "공공자전거 정비"], "procurement_doc", 1.0),
    ]
    for keywords, target, weight in granularity_hints:
        if any(keyword in text for keyword in keywords) and target in f"{granularity} {question_type} {metadata_text}":
            score += weight
    return min(score, 4.0)


def _source_hint_score(query: str, document: RagDocument) -> float:
    text = current_question_text(query).lower()
    source = str(document.metadata.get("source", "")).lower()
    doc_id = document.doc_id.lower()
    category = str(document.metadata.get("category", "")).lower()
    dataset_id = str(document.metadata.get("dataset_id", "")).lower()
    brief_type = str(document.metadata.get("brief_type", "")).lower()
    availability = str(document.metadata.get("availability", "")).lower()
    doc_key = _flatten_metadata_value(document.metadata.get("doc_key", "")).lower()
    local_path = _flatten_metadata_value(document.metadata.get("local_path", "")).lower()
    source_authority = _flatten_metadata_value(document.metadata.get("source_authority", "")).lower()
    question_type = _flatten_metadata_value(document.metadata.get("question_type", "")).lower()
    aliases = _flatten_metadata_value(document.metadata.get("aliases", "")).lower()
    haystack = (
        f"{source} {doc_id} {category} {dataset_id} {brief_type} {availability} "
        f"{doc_key} {local_path} {source_authority} {question_type} {aliases}"
    )
    hints = [
        (["고장", "장애", "점검", "수리"], ["broken_data"], 1.2),
        (["날씨", "기온", "강수", "비", "풍속"], ["weather_data"], 1.2),
        (["대여", "반납", "이용", "거리"], ["rent_data", "count_data", "uselate_data"], 0.8),
        (["데이터셋", "데이터", "컬럼", "스키마", "규모", "행 수"], ["dataset:"], 0.5),
        (["대여소", "위치", "주소", "자치구"], ["branch_data.parquet", "station:"], 0.7),
        (["신규가입", "신규 가입", "가입자", "연령", "성별", "age", "gender"], ["newmeta", "signup"], 1.6),
        (["요금", "약관", "공지"], ["service", "pricing_info", "terms_pdf", "blocked_artifact"], 1.1),
        (["이용요금", "이용권", "정기권", "1시간권", "결제"], ["pricing_info", "service_doc"], 1.8),
        (["정비용역", "정비 용역", "공공자전거 정비", "조달", "입찰", "나라장터"], ["g2b_r26bk01319050", "procurement_doc"], 1.9),
        (["정책", "공시", "보도자료"], ["policy", "sanction", "press"], 1.0),
        (["생활이동", "출도착", "od", "수도권", "수단"], ["oa-22300", "oa-22657", "oa-21222", "oa-21226", "oa-21228"], 1.15),
        (["사고", "안전", "자전거도로"], ["oa-12849", "oa-714"], 1.0),
        (["실시간", "api"], ["oa-15493", "api_specs", "page_only_brief"], 0.9),
        (["근거", "신뢰도", "출처", "provenance", "confidence", "ontology", "온톨로지"], ["ontology-lite", "ontology_lite_brief"], 1.2),
        (["받았", "다운로드", "차단"], ["blocked", "blocked_artifact"], 1.3),
    ]
    score = 0.0
    for keywords, targets, weight in hints:
        if any(keyword in text for keyword in keywords) and any(_hint_target_matches(target, haystack) for target in targets):
            score += weight
    return score


def _hint_target_matches(target: str, haystack: str) -> bool:
    if target.endswith(".parquet"):
        pattern = rf"(?<![0-9a-zA-Z가-힣_]){re.escape(target)}(?![0-9a-zA-Z가-힣_])"
        return re.search(pattern, haystack) is not None
    return target in haystack


def find_project_root(start_path: Path | None = None) -> Path:
    try:
        from project_paths import PROJECT_ROOT

        return PROJECT_ROOT
    except Exception:
        start = (start_path or Path.cwd()).resolve()
        current = start if start.is_dir() else start.parent
        for candidate in [current, *current.parents]:
            if (candidate / ".obybk-root").exists():
                return candidate
        raise FileNotFoundError("Could not find .obybk-root")


def processed_bike_cloud_dir(project_root: Path) -> Path:
    return project_root / "data" / "processed" / "parquet" / "bike_cloud"


def default_index_dir(project_root: Path, profile: str = DEFAULT_RAG_PROFILE) -> Path:
    resolved_profile = normalize_profile(profile)
    index_name = DEFAULT_INDEX_DIR_NAME if resolved_profile == PROFILE_ONTOLOGY_HYBRID else DB_ONLY_INDEX_DIR_NAME
    return project_root / "data" / "processed" / "rag" / index_name


def find_latest_ontology_bundle_manifest(project_root: Path) -> Path:
    candidates = list((project_root / "data" / "raw").glob(ONTOLOGY_BUNDLE_GLOB))
    if not candidates:
        raise FileNotFoundError("Could not find ontology bundle manifest in data/raw")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def load_ontology_bundle_manifest(project_root: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = find_latest_ontology_bundle_manifest(project_root)
    return manifest_path, _read_json(manifest_path)


def _common_metadata(
    *,
    profile: str,
    source: str,
    brief_type: str,
    source_kind: str,
    dataset_name: str = "",
    dataset_id: str = "",
    category: str = "",
    local_path: str = "",
    time_token: str = "",
    availability: str = "available",
    columns: Sequence[str] | None = None,
    granularity: str = "",
    time_range: str = "",
    row_count: int | None = None,
) -> dict[str, Any]:
    return {
        "profile": profile,
        "source": source,
        "brief_type": brief_type,
        "source_kind": source_kind,
        "dataset_name": dataset_name,
        "dataset_id": dataset_id,
        "category": category,
        "local_path": local_path,
        "time_token": time_token,
        "availability": availability,
        "columns": list(columns or []),
        "granularity": granularity,
        "time_range": time_range,
        "row_count": row_count,
    }


def _source_aliases(*parts: str) -> list[str]:
    haystack = " ".join(str(part).lower() for part in parts if part)
    aliases: list[str] = []
    for key, key_aliases in DB_ONLY_SOURCE_ALIASES.items():
        if key.lower() in haystack:
            aliases.extend(key_aliases)
    for category, category_aliases in DB_ONLY_CATEGORY_ALIASES.items():
        if category.lower() in haystack:
            aliases.extend(category_aliases)
    return sorted(dict.fromkeys(alias for alias in aliases if alias))


def _question_type_for_source(*parts: str) -> str:
    haystack = " ".join(str(part).lower() for part in parts if part)
    for key, question_type in DB_ONLY_QUESTION_TYPE_BY_SOURCE.items():
        if key.lower() in haystack:
            return question_type
    if "procurement" in haystack:
        return "procurement_doc"
    if "service" in haystack:
        return "service_doc"
    if "policy" in haystack:
        return "policy_doc"
    return ""


def _flatten_metadata_value(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key} {nested}" for key, nested in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value)
    return str(value or "")


def _source_diversity_key(document: RagDocument) -> str:
    metadata = document.metadata
    for key in ("dataset_name", "doc_key", "dataset_id"):
        value = str(metadata.get(key, "")).strip()
        if value:
            return f"{key}:{value.lower()}"
    source = str(metadata.get("source", "")).strip()
    if source:
        return f"source:{source.lower()}"
    return f"doc_id:{document.doc_id.lower()}"


def _apply_source_diversity(
    ordered: Sequence[tuple[int, float]],
    documents: Sequence[RagDocument],
    top_k: int,
) -> list[tuple[int, float]]:
    if top_k <= 2 or len(ordered) <= top_k:
        return list(ordered[:top_k])

    max_per_source = max(2, top_k // 3)
    selected: list[tuple[int, float]] = []
    source_counts: dict[str, int] = {}
    for doc_index, score in ordered:
        source_key = _source_diversity_key(documents[doc_index])
        if source_counts.get(source_key, 0) >= max_per_source:
            continue
        selected.append((doc_index, score))
        source_counts[source_key] = source_counts.get(source_key, 0) + 1
        if len(selected) >= top_k:
            break
    return selected


def _parquet_catalog_paths(project_root: Path) -> list[Path]:
    data_dir = processed_bike_cloud_dir(project_root)
    ordered = [data_dir / filename for filename in PARQUET_CATALOG_FILENAMES]
    extras = sorted(path for path in data_dir.glob("*.parquet") if path.name not in PARQUET_CATALOG_FILENAMES)
    return [path for path in [*ordered, *extras] if path.exists()]


def _detect_time_columns(columns: Sequence[str]) -> list[str]:
    detected: list[str] = []
    for column in columns:
        lowered = column.lower()
        if any(hint in lowered for hint in TIME_COLUMN_HINTS):
            detected.append(column)
    return detected


def _schema_to_text(schema: Any) -> str:
    try:
        return ", ".join(f"{field.name}: {field.type}" for field in schema)
    except Exception:
        return str(schema)


def _build_pandas_dataset_profile(project_root: Path, path: Path) -> ParquetDatasetProfile | None:
    try:
        import pandas as pd

        frame = pd.read_parquet(path)
    except Exception:
        return None

    columns = [str(column) for column in frame.columns]
    schema = ", ".join(f"{column}: {dtype}" for column, dtype in frame.dtypes.items())
    dataset_name = path.name
    return ParquetDatasetProfile(
        dataset_name=dataset_name,
        source=str(path.relative_to(project_root)),
        row_count=int(len(frame)),
        columns=columns,
        schema=schema,
        row_group_count=1,
        size_bytes=path.stat().st_size,
        time_columns=_detect_time_columns(columns),
        query_axes=PARQUET_QUERY_AXES.get(dataset_name, "컬럼, 기간, 주요 집계 축"),
        granularity=PARQUET_GRANULARITIES.get(dataset_name, "dataset"),
    )


def _build_unreadable_dataset_profile(project_root: Path, path: Path, exc: Exception) -> ParquetDatasetProfile:
    dataset_name = path.name
    return ParquetDatasetProfile(
        dataset_name=dataset_name,
        source=str(path.relative_to(project_root)),
        row_count=0,
        columns=[],
        schema=f"unreadable: {type(exc).__name__}: {exc}",
        row_group_count=0,
        size_bytes=path.stat().st_size,
        time_columns=[],
        query_axes=PARQUET_QUERY_AXES.get(dataset_name, "컬럼, 기간, 주요 집계 축"),
        granularity=PARQUET_GRANULARITIES.get(dataset_name, "dataset"),
        read_error=f"{type(exc).__name__}: {exc}",
    )


def build_parquet_dataset_profiles(project_root: Path) -> list[ParquetDatasetProfile]:
    profiles: list[ParquetDatasetProfile] = []
    try:
        import pyarrow.parquet as pq
    except Exception:
        pq = None

    for path in _parquet_catalog_paths(project_root):
        dataset_name = path.name
        if pq is None:
            profile = _build_pandas_dataset_profile(project_root, path)
            if profile:
                profiles.append(profile)
            else:
                profiles.append(
                    ParquetDatasetProfile(
                        dataset_name=dataset_name,
                        source=str(path.relative_to(project_root)),
                        row_count=0,
                        columns=[],
                        schema="unreadable: pyarrow unavailable and pandas read failed",
                        row_group_count=0,
                        size_bytes=path.stat().st_size,
                        time_columns=[],
                        query_axes=PARQUET_QUERY_AXES.get(dataset_name, "컬럼, 기간, 주요 집계 축"),
                        granularity=PARQUET_GRANULARITIES.get(dataset_name, "dataset"),
                        read_error="pyarrow unavailable and pandas read failed",
                    )
                )
            continue
        try:
            parquet_file = pq.ParquetFile(path)
            schema_arrow = parquet_file.schema_arrow
            columns = [str(column) for column in schema_arrow.names]
            metadata = parquet_file.metadata
            profiles.append(
                ParquetDatasetProfile(
                    dataset_name=dataset_name,
                    source=str(path.relative_to(project_root)),
                    row_count=int(metadata.num_rows),
                    columns=columns,
                    schema=_schema_to_text(schema_arrow),
                    row_group_count=int(metadata.num_row_groups),
                    size_bytes=path.stat().st_size,
                    time_columns=_detect_time_columns(columns),
                    query_axes=PARQUET_QUERY_AXES.get(dataset_name, "컬럼, 기간, 주요 집계 축"),
                    granularity=PARQUET_GRANULARITIES.get(dataset_name, "dataset"),
                )
            )
        except Exception as exc:
            profile = _build_pandas_dataset_profile(project_root, path)
            if profile:
                profiles.append(profile)
            else:
                profiles.append(_build_unreadable_dataset_profile(project_root, path, exc))
    return profiles


def _read_parquet_frame(
    path: Path,
    columns: Sequence[str] | None = None,
    max_rows: int | None = PANDAS_AGGREGATE_MAX_ROWS,
):
    import pandas as pd

    selected_columns = list(columns or [])
    try:
        import pyarrow.parquet as pq

        parquet_file = pq.ParquetFile(path)
        available_columns = set(parquet_file.schema_arrow.names)
        if selected_columns:
            selected_columns = [column for column in selected_columns if column in available_columns]
        if max_rows is None:
            return pd.read_parquet(path, columns=selected_columns or None)

        frames = []
        rows_read = 0
        for batch in parquet_file.iter_batches(batch_size=min(max_rows, 50_000), columns=selected_columns or None):
            batch_frame = batch.to_pandas()
            remaining = max_rows - rows_read
            if len(batch_frame) > remaining:
                batch_frame = batch_frame.head(remaining)
            frames.append(batch_frame)
            rows_read += len(batch_frame)
            if rows_read >= max_rows:
                break
        if not frames:
            return pd.DataFrame(columns=selected_columns)
        return pd.concat(frames, ignore_index=True)
    except Exception:
        frame = pd.read_parquet(path, columns=selected_columns or None)
        return frame.head(max_rows) if max_rows is not None else frame


def _frame_time_range(frame: Any, time_columns: Sequence[str]) -> str:
    for column in time_columns:
        if column not in frame.columns or frame.empty:
            continue
        values = frame[column].dropna()
        if values.empty:
            continue
        return f"{values.min()}~{values.max()}"
    return ""


def _top_value_summary(frame: Any, columns: Sequence[str], limit: int = 5) -> str:
    parts: list[str] = []
    for column in columns:
        if column not in frame.columns:
            continue
        counts = frame[column].dropna().astype(str).value_counts().head(limit)
        if counts.empty:
            continue
        summary = ", ".join(f"{value}: {count:,}건" for value, count in counts.items())
        parts.append(f"{column} 상위값 {summary}")
    return " / ".join(parts)


def _numeric_summary(frame: Any, limit: int = 5) -> str:
    try:
        numeric_frame = frame.select_dtypes(include=["number"])
    except Exception:
        return ""
    if numeric_frame.empty:
        return ""
    parts: list[str] = []
    for column in list(numeric_frame.columns)[:limit]:
        series = numeric_frame[column].dropna()
        if series.empty:
            continue
        parts.append(
            f"{column} 평균 {round(float(series.mean()), 2)}, 최대 {round(float(series.max()), 2)}"
        )
    return " / ".join(parts)


def _aggregate_columns(profile: ParquetDatasetProfile) -> list[str]:
    preferred = [
        *profile.time_columns,
        "branchnum",
        "branchname",
        "location1",
        "location2",
        "rentstation",
        "returnstation",
        "type_bk",
        "bikenum",
        "temperature",
        "precipitation",
        "windspeed",
        "rent_count",
        "return_count",
        "uselate_count",
        "distance",
        "new",
        "age",
        "gender",
    ]
    selected: list[str] = []
    for column in preferred:
        if column in profile.columns and column not in selected:
            selected.append(column)
    for column in profile.columns:
        if len(selected) >= 12:
            break
        if column not in selected:
            selected.append(column)
    return selected


def build_parquet_catalog_documents(project_root: Path, profile: str = PROFILE_DB_ONLY) -> list[RagDocument]:
    documents: list[RagDocument] = []
    for dataset_profile in build_parquet_dataset_profiles(project_root):
        purpose = PARQUET_DATASET_PURPOSES.get(dataset_profile.dataset_name, "따릉이 운영 Parquet 데이터셋")
        aliases = _source_aliases(dataset_profile.dataset_name, dataset_profile.source, dataset_profile.granularity)
        common_metadata = _common_metadata(
            profile=profile,
            source=dataset_profile.source,
            brief_type="dataset_inventory_brief",
            source_kind="processed_parquet",
            dataset_name=dataset_profile.dataset_name,
            category="dataset_inventory",
            local_path=dataset_profile.source,
            columns=dataset_profile.columns,
            granularity=dataset_profile.granularity,
            row_count=dataset_profile.row_count,
        ) | {
            "aliases": aliases,
            "source_authority": "processed_parquet_catalog",
            "question_type": _question_type_for_source(dataset_profile.dataset_name, dataset_profile.source),
        }
        alias_text = f" source aliases: {', '.join(aliases)}." if aliases else ""
        documents.append(
            RagDocument(
                doc_id=f"parquet-catalog:{dataset_profile.dataset_name}",
                text=(
                    f"Parquet 데이터셋 카탈로그. 데이터셋 {dataset_profile.dataset_name}. "
                    f"행 수 {dataset_profile.row_count:,}건. row group {dataset_profile.row_group_count}개. "
                    f"파일 크기 {dataset_profile.size_bytes} bytes. 컬럼 {', '.join(dataset_profile.columns)}. "
                    f"시간 컬럼 {', '.join(dataset_profile.time_columns) or '없음'}. "
                    f"granularity {dataset_profile.granularity}. 활용 목적: {purpose}. "
                    f"읽기 상태 {'실패: ' + dataset_profile.read_error if dataset_profile.read_error else 'available'}."
                    f"{alias_text}"
                ),
                metadata=common_metadata,
            )
        )
        documents.append(
            RagDocument(
                doc_id=f"parquet-axis:{dataset_profile.dataset_name}",
                text=(
                    f"Parquet 질의 축 브리프. 데이터셋 {dataset_profile.dataset_name}. "
                    f"추천 질의 축: {dataset_profile.query_axes}. "
                    f"스키마 {dataset_profile.schema}.{alias_text}"
                ),
                metadata=common_metadata
                | {
                    "brief_type": "query_axis_brief",
                    "query_axes": dataset_profile.query_axes,
                    "schema": dataset_profile.schema,
                },
            )
        )
    return documents


def build_pandas_aggregate_documents(project_root: Path, profile: str = PROFILE_DB_ONLY) -> list[RagDocument]:
    documents: list[RagDocument] = []
    data_dir = processed_bike_cloud_dir(project_root)
    for dataset_profile in build_parquet_dataset_profiles(project_root):
        path = data_dir / dataset_profile.dataset_name
        if not path.exists():
            continue
        aliases = _source_aliases(dataset_profile.dataset_name, dataset_profile.source, dataset_profile.granularity)
        source_profile_metadata = {
            "aliases": aliases,
            "source_authority": "processed_parquet_aggregate",
            "question_type": _question_type_for_source(dataset_profile.dataset_name, dataset_profile.source),
        }
        alias_text = f" source aliases: {', '.join(aliases)}." if aliases else ""
        if dataset_profile.read_error:
            documents.append(
                RagDocument(
                    doc_id=f"parquet-aggregate:{dataset_profile.dataset_name}",
                    text=(
                        f"Parquet 읽기 실패 브리프. 데이터셋 {dataset_profile.dataset_name}. "
                        f"파일은 catalog에 존재하지만 PyArrow/Pandas로 row scan을 수행하지 못했습니다. "
                        f"실패 사유 {dataset_profile.read_error}. 추천 질의 축: {dataset_profile.query_axes}.{alias_text}"
                    ),
                    metadata=_common_metadata(
                        profile=profile,
                        source=dataset_profile.source,
                        brief_type="dataset_aggregate_brief",
                        source_kind="processed_parquet",
                        dataset_name=dataset_profile.dataset_name,
                        category="dataset_aggregate",
                        local_path=dataset_profile.source,
                        columns=dataset_profile.columns,
                        granularity=dataset_profile.granularity,
                        row_count=dataset_profile.row_count,
                    )
                    | source_profile_metadata
                    | {"sample_row_count": 0, "scan_skipped_reason": "read_error", "read_error": dataset_profile.read_error},
                )
            )
            continue
        if dataset_profile.size_bytes > PANDAS_AGGREGATE_SCAN_SIZE_LIMIT_BYTES:
            documents.append(
                RagDocument(
                    doc_id=f"parquet-aggregate:{dataset_profile.dataset_name}",
                    text=(
                        f"대용량 Parquet 집계 브리프. 데이터셋 {dataset_profile.dataset_name}. "
                        f"전체 행 수 {dataset_profile.row_count:,}건, 파일 크기 {dataset_profile.size_bytes} bytes. "
                        f"원천 row 전체는 벡터화하지 않고 컬럼/질의 축 기반으로 검색한다. "
                        f"추천 질의 축: {dataset_profile.query_axes}. 컬럼 {', '.join(dataset_profile.columns)}.{alias_text}"
                    ),
                    metadata=_common_metadata(
                        profile=profile,
                        source=dataset_profile.source,
                        brief_type="dataset_aggregate_brief",
                        source_kind="processed_parquet",
                        dataset_name=dataset_profile.dataset_name,
                        category="dataset_aggregate",
                        local_path=dataset_profile.source,
                        columns=dataset_profile.columns,
                        granularity=dataset_profile.granularity,
                        row_count=dataset_profile.row_count,
                    )
                    | source_profile_metadata
                    | {"sample_row_count": 0, "scan_skipped_reason": "large_parquet"},
                )
            )
            continue
        try:
            frame = _read_parquet_frame(path, columns=_aggregate_columns(dataset_profile))
        except Exception:
            continue
        if frame.empty:
            continue

        sample_count = len(frame)
        time_range = _frame_time_range(frame, dataset_profile.time_columns)
        top_summary = _top_value_summary(frame, ["type_bk", "branchname", "location1", "rentstation", "returnstation", "age", "gender"])
        numeric_summary = _numeric_summary(frame)
        if dataset_profile.dataset_name == "broken_data.parquet":
            title = "고장 유형 집계 브리프"
            lead = "고장 유형 상위 분포와 자전거 점검 우선순위 후보를 제공한다."
        elif dataset_profile.dataset_name == "weather_data.parquet":
            title = "날씨 데이터 집계 브리프"
            lead = "날씨 데이터 평균 기온, 강수량, 풍속과 기간 요약을 제공한다."
        elif dataset_profile.dataset_name in {"count_data.parquet", "rent_data.parquet", "uselate_data.parquet"}:
            title = "대여/반납 이용 집계 브리프"
            lead = "대여/반납 이용량, 이동 흐름, 지연/연체 관련 집계 단서를 제공한다."
        elif dataset_profile.dataset_name in {"branch_data.parquet", "master_branch_data.parquet"}:
            title = "대여소 프로필 집계 브리프"
            lead = "대여소 위치, 자치구, 주소, master 속성의 분포를 제공한다."
        else:
            title = "운영 데이터 집계 브리프"
            lead = "운영 데이터의 주요 컬럼과 값 분포를 제공한다."

        documents.append(
            RagDocument(
                doc_id=f"parquet-aggregate:{dataset_profile.dataset_name}",
                text=(
                    f"{title}. 데이터셋 {dataset_profile.dataset_name}. {lead} "
                    f"전체 행 수 {dataset_profile.row_count:,}건 중 샘플/스캔 행 수 {sample_count:,}건. "
                    f"기간 {time_range or '확인 불가'}. "
                    f"{top_summary or '범주형 상위값 없음'}. "
                    f"{numeric_summary or '수치 요약 없음'}.{alias_text}"
                ),
                metadata=_common_metadata(
                    profile=profile,
                    source=dataset_profile.source,
                    brief_type="dataset_aggregate_brief",
                    source_kind="processed_parquet",
                    dataset_name=dataset_profile.dataset_name,
                    category="dataset_aggregate",
                    local_path=dataset_profile.source,
                    columns=dataset_profile.columns,
                    granularity=dataset_profile.granularity,
                    time_range=time_range,
                    row_count=dataset_profile.row_count,
                )
                | source_profile_metadata
                | {"sample_row_count": sample_count},
            )
        )
    return documents


def _parse_structured_fact_query(project_root: Path, question: str) -> StructuredFactQuery:
    current_question = current_question_text(question)
    terms = _question_terms(current_question)
    lowered = current_question.lower()
    profiles = build_parquet_dataset_profiles(project_root)
    dataset_hints: list[str] = []
    column_hints: list[str] = []
    for profile in profiles:
        haystack = f"{profile.dataset_name} {PARQUET_DATASET_PURPOSES.get(profile.dataset_name, '')}".lower()
        if any(term.lower() in haystack for term in terms):
            dataset_hints.append(profile.dataset_name)
        for column in profile.columns:
            if column.lower() in lowered:
                column_hints.append(column)
    time_hints = [term for term in terms if re.search(r"20\d{2}|[0-9]{1,2}월|[0-9]{1,2}일", term)]
    station_terms = [
        term
        for term in terms
        if term.isdigit() or any(keyword in term for keyword in ["역", "구", "대여소", "망원", "합정", "군자"])
    ]
    return StructuredFactQuery(
        question=current_question,
        terms=terms,
        dataset_hints=dataset_hints,
        column_hints=sorted(set(column_hints)),
        time_hints=time_hints,
        station_terms=station_terms,
    )


def _collect_station_pandas_facts(project_root: Path, parsed: StructuredFactQuery, limit: int = 5) -> list[FactSnippet]:
    branch_path = processed_bike_cloud_dir(project_root) / "branch_data.parquet"
    if not branch_path.exists() or not parsed.terms:
        return []
    columns = ["date", "branchnum", "branchname", "location1", "location2", "branch_x", "branch_y", "sy"]
    try:
        frame = _read_parquet_frame(branch_path, columns=columns, max_rows=None)
    except Exception:
        return []
    if frame.empty:
        return []
    if "date" in frame.columns:
        frame = frame.sort_values(["branchnum", "date"]).drop_duplicates("branchnum", keep="last")
    matches = []
    for term in parsed.terms:
        mask = False
        for column in ["branchnum", "branchname", "location1", "location2"]:
            if column in frame.columns:
                column_mask = frame[column].astype(str).str.contains(term, case=False, na=False)
                mask = column_mask if isinstance(mask, bool) else (mask | column_mask)
        if not isinstance(mask, bool):
            matches = frame[mask].head(limit).to_dict(orient="records")
            if matches:
                break
    snippets: list[FactSnippet] = []
    for row in matches:
        snippets.append(
            FactSnippet(
                title=f"대여소 {row.get('branchnum', '')} {row.get('branchname', '')}",
                text=(
                    f"대여소명 {row.get('branchname', '')}, 자치구 {row.get('location1', '')}, 주소 {row.get('location2', '')}, "
                    f"위도 {row.get('branch_x', '')}, 경도 {row.get('branch_y', '')}, 최신 기준일 {row.get('date', '')}"
                ),
                source=str(branch_path.relative_to(project_root)),
            )
        )
    return snippets


def _collect_fault_pandas_facts(project_root: Path) -> list[FactSnippet]:
    path = processed_bike_cloud_dir(project_root) / "broken_data.parquet"
    if not path.exists():
        return []
    try:
        frame = _read_parquet_frame(path, columns=["date_bk", "bikenum", "type_bk"])
    except Exception:
        return []
    if frame.empty or "type_bk" not in frame.columns:
        return []
    counts = frame["type_bk"].dropna().astype(str).value_counts().head(8)
    summary = ", ".join(f"{fault_type}: {count:,}건" for fault_type, count in counts.items())
    time_range = _frame_time_range(frame, ["date_bk"])
    return [
        FactSnippet(
            title="고장 유형 상위 집계",
            text=f"기간 {time_range or '확인 불가'}, {summary}",
            source=str(path.relative_to(project_root)),
        )
    ]


def _collect_weather_pandas_facts(project_root: Path) -> list[FactSnippet]:
    path = processed_bike_cloud_dir(project_root) / "weather_data.parquet"
    if not path.exists():
        return []
    try:
        frame = _read_parquet_frame(path, columns=["datetime", "temperature", "precipitation", "windspeed"])
    except Exception:
        return []
    if frame.empty:
        return []
    time_range = _frame_time_range(frame, ["datetime"])
    parts: list[str] = [f"기간 {time_range or '확인 불가'}", f"행 수 {len(frame):,}건"]
    for column, label in [
        ("temperature", "평균 기온"),
        ("precipitation", "평균 강수량"),
        ("windspeed", "평균 풍속"),
    ]:
        if column in frame.columns:
            series = frame[column].dropna()
            if not series.empty:
                parts.append(f"{label} {round(float(series.mean()), 2)}, 최대 {round(float(series.max()), 2)}")
    return [
        FactSnippet(
            title="날씨 데이터 요약",
            text=", ".join(parts),
            source=str(path.relative_to(project_root)),
        )
    ]


def _collect_usage_pandas_facts(project_root: Path) -> list[FactSnippet]:
    snippets: list[FactSnippet] = []
    data_dir = processed_bike_cloud_dir(project_root)
    for filename in ["count_data.parquet", "rent_data.parquet", "uselate_data.parquet"]:
        path = data_dir / filename
        if not path.exists():
            continue
        profile = next((item for item in build_parquet_dataset_profiles(project_root) if item.dataset_name == filename), None)
        if not profile:
            continue
        if profile.size_bytes > PANDAS_AGGREGATE_SCAN_SIZE_LIMIT_BYTES:
            snippets.append(
                FactSnippet(
                    title=f"{filename} 이용 집계",
                    text=(
                        f"대용량 파일이라 row scan은 생략했습니다. 행 수 {profile.row_count:,}건, "
                        f"추천 질의 축 {profile.query_axes}, 컬럼 {', '.join(profile.columns)}"
                    ),
                    source=str(path.relative_to(project_root)),
                )
            )
            continue
        try:
            frame = _read_parquet_frame(path, columns=_aggregate_columns(profile))
        except Exception:
            continue
        if frame.empty:
            continue
        snippets.append(
            FactSnippet(
                title=f"{filename} 이용 집계",
                text=(
                    f"행 수 {profile.row_count:,}건 중 {len(frame):,}건 스캔. "
                    f"기간 {_frame_time_range(frame, profile.time_columns) or '확인 불가'}. "
                    f"{_numeric_summary(frame) or _top_value_summary(frame, profile.columns[:3]) or '요약 없음'}"
                ),
                source=str(path.relative_to(project_root)),
            )
        )
    return snippets[:3]


def collect_pandas_fact_snippets(project_root: Path, question: str) -> list[FactSnippet]:
    parsed = _parse_structured_fact_query(project_root, question)
    lowered = parsed.question.lower()
    snippets: list[FactSnippet] = []
    snippets.extend(_collect_station_pandas_facts(project_root, parsed))
    if any(keyword in parsed.question for keyword in ["고장", "장애", "점검", "수리"]):
        snippets.extend(_collect_fault_pandas_facts(project_root))
    if any(keyword in parsed.question for keyword in ["날씨", "기온", "강수", "비", "풍속"]):
        snippets.extend(_collect_weather_pandas_facts(project_root))
    if any(keyword in parsed.question for keyword in ["대여", "반납", "이용량", "거리", "지연", "연체"]):
        snippets.extend(_collect_usage_pandas_facts(project_root))
    if any(keyword in lowered for keyword in ["dataset", "schema", "데이터", "컬럼", "행 수", "규모", "스키마"]):
        snippets.extend(collect_dataset_inventory(project_root))
    return snippets[:12]


def build_station_profile_documents(
    project_root: Path,
    max_station_docs: int | None = None,
    profile: str = PROFILE_DB_ONLY,
) -> list[RagDocument]:
    branch_path = processed_bike_cloud_dir(project_root) / "branch_data.parquet"
    if not branch_path.exists():
        return []

    try:
        import pandas as pd
    except Exception:
        return []

    columns = ["date", "branchnum", "branchname", "location1", "location2", "branch_x", "branch_y", "sy"]
    try:
        frame = _read_parquet_frame(branch_path, columns=columns, max_rows=None)
    except Exception:
        return []
    frame = frame.sort_values(["branchnum", "date"]).drop_duplicates("branchnum", keep="last")
    if max_station_docs is not None:
        frame = frame.head(max_station_docs)

    documents: list[RagDocument] = []
    for row in frame.to_dict(orient="records"):
        station_id = str(row.get("branchnum", "")).strip()
        station_name = str(row.get("branchname", "")).strip()
        district = str(row.get("location1", "")).strip()
        address = str(row.get("location2", "")).strip()
        text = (
            f"따릉이 대여소 프로필. 대여소 번호 {station_id}. "
            f"대여소명 {station_name}. 자치구 {district}. 주소 {address}. "
            f"위도 {row.get('branch_x')}. 경도 {row.get('branch_y')}. 운영방식 {row.get('sy')}."
        )
        documents.append(
            RagDocument(
                doc_id=f"station:{station_id}",
                text=text,
                metadata=_common_metadata(
                    profile=profile,
                    source="branch_data.parquet",
                    brief_type="station_profile",
                    source_kind="processed_parquet",
                    dataset_name="branch_data.parquet",
                    category="station",
                    local_path=str(branch_path.relative_to(project_root)),
                    time_token=str(row.get("date", "")),
                    columns=columns,
                    granularity="station",
                    row_count=len(frame),
                )
                | {
                    "station_id": station_id,
                    "station_name": station_name,
                    "district": district,
                },
            )
        )
    return documents


def _chunk_text(text: str, max_chars: int = 1400) -> Iterable[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    buffer = ""
    for paragraph in paragraphs:
        if len(buffer) + len(paragraph) + 2 <= max_chars:
            buffer = f"{buffer}\n\n{paragraph}".strip()
            continue
        if buffer:
            yield buffer
        buffer = paragraph[:max_chars]
    if buffer:
        yield buffer


def build_reference_documents(project_root: Path, profile: str = PROFILE_DB_ONLY) -> list[RagDocument]:
    documents: list[RagDocument] = []
    for relative_path in REFERENCE_DOCS:
        path = project_root / relative_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for chunk_index, chunk in enumerate(_chunk_text(text), start=1):
            documents.append(
                RagDocument(
                    doc_id=f"doc:{relative_path}:{chunk_index}",
                    text=chunk,
                    metadata=_common_metadata(
                        profile=profile,
                        source=relative_path,
                        brief_type="reference_doc_chunk",
                        source_kind="reference_doc",
                        category="reference",
                        local_path=relative_path,
                    )
                    | {"chunk": chunk_index},
                )
            )
    return documents


def _resolve_repository_ontology_artifact_dir(artifact_dir: Path | None = None) -> Path | None:
    if artifact_dir is not None:
        return artifact_dir.expanduser().resolve()
    env_value = os.getenv(REPOSITORY_ONTOLOGY_ARTIFACT_DIR_ENV, "").strip()
    if not env_value:
        return None
    return Path(env_value).expanduser().resolve()


def _ontology_seed_summary_text(path: Path) -> str:
    try:
        seed = _read_json(path)
    except Exception:
        return _safe_read_text(path)

    project = seed.get("project", {}) if isinstance(seed, dict) else {}
    classes = seed.get("classes", []) if isinstance(seed, dict) else []
    relations = seed.get("relations", []) if isinstance(seed, dict) else []
    metrics = seed.get("evaluation_metrics", []) if isinstance(seed, dict) else []
    held_items = seed.get("held_items", []) if isinstance(seed, dict) else []
    canonical_evidence = seed.get("canonical_evidence", []) if isinstance(seed, dict) else []
    class_ids = [str(item.get("id", "")) for item in classes if isinstance(item, dict) and item.get("id")]
    relation_lines = [
        f"{item.get('id')} {item.get('domain')} -> {item.get('range')}"
        for item in relations
        if isinstance(item, dict) and item.get("id")
    ]
    held_lines = [
        f"{item.get('question_id')}: {item.get('next_action')}"
        for item in held_items
        if isinstance(item, dict)
    ]
    evidence_lines = [
        f"{item.get('path')}: {item.get('role')}"
        for item in canonical_evidence
        if isinstance(item, dict) and item.get("path")
    ]
    return "\n".join(
        [
            "OBYBK repository ontology seed artifact.",
            f"project: {project.get('name', '')} domain_id: {project.get('domain_id', '')}",
            f"core_problem: {seed.get('core_problem', '')}",
            f"automation_boundary: {seed.get('automation_boundary', '')}",
            f"classes: {', '.join(class_ids)}",
            f"relations: {'; '.join(relation_lines)}",
            f"evaluation_metrics: {', '.join(str(metric) for metric in metrics)}",
            f"held_items: {'; '.join(held_lines)}",
            f"canonical_evidence: {'; '.join(evidence_lines)}",
            "answer_contract: 추천 답변 필수 항목은 답변, 근거 문서, 관련 객체, 관련 관계, 추천 조치, 검토 필요 여부.",
        ]
    )


def build_repository_ontology_artifact_documents(
    artifact_dir: Path | None = None,
    profile: str = DEFAULT_RAG_PROFILE,
) -> list[RagDocument]:
    resolved_dir = _resolve_repository_ontology_artifact_dir(artifact_dir)
    if resolved_dir is None or not resolved_dir.exists():
        return []

    documents: list[RagDocument] = []
    for filename in REPOSITORY_ONTOLOGY_ARTIFACT_FILENAMES:
        path = resolved_dir / filename
        if not path.exists():
            continue
        text = _ontology_seed_summary_text(path) if filename == "ontology_seed.json" else _safe_read_text(path)
        for chunk_index, chunk in enumerate(_chunk_text(text), start=1):
            stem = Path(filename).stem.replace("_", "-")
            documents.append(
                RagDocument(
                    doc_id=f"repository-ontology:{stem}:{chunk_index}",
                    text=chunk,
                    metadata=_common_metadata(
                        profile=profile,
                        source=filename,
                        brief_type="repository_ontology_artifact",
                        source_kind="repository_ontology_discovery",
                        category="ontology_review",
                        local_path=str(path),
                        availability="available",
                    )
                    | {"chunk": chunk_index},
                )
            )
    return documents


def _repository_ontology_artifact_dir_from_index(index_dir: Path) -> Path | None:
    manifest = _load_index_manifest(index_dir)
    raw_path = str(manifest.get("repository_ontology_artifact_dir", "")).strip()
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else (index_dir / path).resolve()


def _camel_to_graph_relation(relation_id: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", relation_id).upper()


FALLBACK_ONTOLOGY_RELATIONS: dict[str, tuple[str, str]] = {
    "servesUser": ("Service", "User"),
    "helpsOperation": ("Service", "Operator"),
    "usesDataset": ("Service", "Dataset"),
    "hasEvidence": ("Recommendation", "Evidence"),
    "forStation": ("UsageMetric", "Station"),
    "inTimeBucket": ("UsageMetric", "TimeBucket"),
    "faultAtStation": ("FaultEvent", "Station"),
    "faultForBike": ("FaultEvent", "Bike"),
    "affectedByWeather": ("UsageMetric", "WeatherObservation"),
    "generatesRecommendation": ("Service", "Recommendation"),
    "createsTask": ("Recommendation", "ReallocationAction"),
    "requiresReview": ("Recommendation", "ReviewDecision"),
    "approvedBy": ("ReviewDecision", "Operator"),
    "measuresAnswer": ("EvaluationMetric", "Recommendation"),
}


RELATION_INTENT_MAP: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("이용량", "시간대", "시간 구간", "대여", "반납", "줄어든", "감소", "usage"), ("forStation", "inTimeBucket")),
    (("날씨", "기온", "강수", "비", "풍속", "이유", "원인"), ("affectedByWeather", "inTimeBucket")),
    (("고장", "장애", "점검", "수리", "fault"), ("faultAtStation", "faultForBike")),
    (("추천", "조치", "재배치", "recommendation"), ("hasEvidence", "requiresReview", "createsTask")),
    (("근거", "문서", "source", "evidence"), ("hasEvidence",)),
    (("검토", "승인", "review", "approved"), ("requiresReview", "approvedBy")),
    (("기준 데이터", "데이터셋", "dataset", "bike_cloud"), ("usesDataset",)),
    (("사용자", "운영 담당자", "주로 사용", "user"), ("servesUser", "helpsOperation")),
    (("품질", "평가", "답변", "metric", "quality"), ("measuresAnswer", "hasEvidence")),
    (("보류", "pdf", "ocr", "held"), ("hasEvidence", "requiresReview")),
)


def _load_repository_ontology_seed(index_dir: Path) -> dict[str, Any]:
    artifact_dir = _repository_ontology_artifact_dir_from_index(index_dir)
    if artifact_dir is None:
        return {}
    seed_path = artifact_dir / "ontology_seed.json"
    if not seed_path.exists():
        return {}
    try:
        return _read_json(seed_path)
    except Exception:
        return {}


def collect_repository_ontology_relation_facts(index_dir: Path, question: str) -> list[FactSnippet]:
    text = current_question_text(question).lower()
    requested_relation_ids: list[str] = []
    for keywords, relation_ids in RELATION_INTENT_MAP:
        if any(keyword.lower() in text for keyword in keywords):
            requested_relation_ids.extend(relation_ids)
    if not requested_relation_ids:
        return []

    seed = _load_repository_ontology_seed(index_dir)
    seed_relations = {
        str(item.get("id")): (str(item.get("domain", "")), str(item.get("range", "")))
        for item in seed.get("relations", [])
        if isinstance(item, dict) and item.get("id")
    }
    relation_lines: list[str] = []
    seen: set[str] = set()
    for relation_id in requested_relation_ids:
        if relation_id in seen:
            continue
        seen.add(relation_id)
        domain, range_ = seed_relations.get(relation_id, FALLBACK_ONTOLOGY_RELATIONS.get(relation_id, ("", "")))
        if not domain and not range_:
            continue
        relation_lines.append(f"{relation_id} ({_camel_to_graph_relation(relation_id)}): {domain} -> {range_}")
    if not relation_lines:
        return []
    return [
        FactSnippet(
            title="Ontology relation contract",
            text=(
                "ontology_seed.json relation contract: "
                + "; ".join(relation_lines)
                + ". 답변에는 관련 객체와 관련 관계를 함께 표시해야 합니다."
            ),
            source="ontology_seed.json",
        )
    ]


def collect_repository_ontology_artifact_facts(index_dir: Path, question: str) -> list[FactSnippet]:
    artifact_dir = _repository_ontology_artifact_dir_from_index(index_dir)
    if artifact_dir is None or not artifact_dir.exists():
        return []

    seed_path = artifact_dir / "ontology_seed.json"
    blueprint_path = artifact_dir / "reviewed_ontology_blueprint.md"
    if not seed_path.exists() and not blueprint_path.exists():
        return []

    text = current_question_text(question).lower()
    snippets: list[FactSnippet] = []
    seed: dict[str, Any] = {}
    if seed_path.exists():
        try:
            seed = _read_json(seed_path)
        except Exception:
            seed = {}

    wants_evidence = any(keyword in text for keyword in ["근거", "문서", "source", "evidence"])
    wants_review = any(keyword in text for keyword in ["추천", "검토", "승인", "review", "recommendation"])
    wants_held = any(keyword in text for keyword in ["보류", "pdf", "ocr", "held"])
    wants_quality = any(keyword in text for keyword in ["답변", "품질", "평가", "항목", "contract"])
    wants_user = any(keyword in text for keyword in ["사용자", "운영 담당자", "주로 사용"])

    if seed and (wants_evidence or wants_review or wants_quality or wants_user or wants_held):
        canonical_evidence = seed.get("canonical_evidence", [])
        evidence_text = "; ".join(
            f"{item.get('path')}: {item.get('role')}"
            for item in canonical_evidence
            if isinstance(item, dict) and item.get("path")
        )
        primary_users = ", ".join(str(user) for user in seed.get("primary_users", []))
        snippets.append(
            FactSnippet(
                title="Repository ontology seed 요약",
                text=(
                    f"ontology_seed.json 기준 자동화 경계: {seed.get('automation_boundary', '')}. "
                    f"canonical evidence: {evidence_text or '없음'}. "
                    f"primary users: {primary_users or '없음'}. "
                    "추천 답변 필수 항목은 답변, 근거 문서, 관련 객체, 관련 관계, 추천 조치, 검토 필요 여부입니다."
                ),
                source="ontology_seed.json",
            )
        )

    if seed and wants_held:
        held_text = "; ".join(
            f"{item.get('question_id')}: {item.get('reason', '')} {item.get('next_action', '')}".strip()
            for item in seed.get("held_items", [])
            if isinstance(item, dict)
        )
        snippets.append(
            FactSnippet(
                title="보류 문서 재평가 정책",
                text=f"ontology_seed.json held_items: {held_text or '보류 항목 없음'}. reviewed_ontology_blueprint.md도 함께 확인해야 합니다.",
                source="reviewed_ontology_blueprint.md",
            )
        )

    if blueprint_path.exists() and (wants_evidence or wants_review or wants_quality or wants_held):
        blueprint_text = _safe_read_text(blueprint_path)[:1200]
        snippets.append(
            FactSnippet(
                title="Reviewed ontology blueprint 근거",
                text=f"reviewed_ontology_blueprint.md: {blueprint_text}",
                source="reviewed_ontology_blueprint.md",
            )
        )

    return snippets[:5]


def build_dataset_inventory_documents(
    project_root: Path,
    profile: str = PROFILE_DB_ONLY,
) -> list[RagDocument]:
    documents = build_parquet_catalog_documents(project_root, profile=profile)
    if documents:
        return documents

    snippets = collect_dataset_inventory(project_root)
    return [
        RagDocument(
            doc_id=f"dataset:{index}",
            text=f"{snippet.title}\n{snippet.text}",
            metadata=_common_metadata(
                profile=profile,
                source=snippet.source,
                brief_type="dataset_inventory_brief",
                source_kind="processed_parquet",
                dataset_name=Path(snippet.source).name,
                category="dataset_inventory",
                local_path=snippet.source,
            ),
        )
        for index, snippet in enumerate(snippets, start=1)
    ]


def _safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _squash_text(text: str, max_chars: int = 900) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:max_chars]


def _time_token_from_filename(filename: str) -> str:
    quarter_match = re.search(r"(20\d{2})[^\d]{0,4}([1-4])\s*분기", filename)
    if quarter_match:
        return f"{quarter_match.group(1)}Q{quarter_match.group(2)}"
    for pattern in [r"(20\d{6})", r"(20\d{4})", r"(20\d{2})"]:
        match = re.search(pattern, filename)
        if match:
            return match.group(1)
    return ""


def _inspect_csv_bytes(payload: bytes) -> tuple[list[str], list[list[str]]]:
    text = payload.decode("utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], []
    return rows[0], rows[1:4]


def _inspect_csv_file(path: Path) -> tuple[str, list[str], list[list[str]]]:
    payload = path.read_bytes()
    headers, rows = _inspect_csv_bytes(payload)
    return path.name, headers, rows


def _inspect_zip_file(path: Path) -> tuple[str, list[str], list[list[str]]]:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if not name.endswith("/")]
        if not members:
            return "", [], []
        preferred = next((name for name in members if Path(name).suffix.lower() in {".csv", ".txt"}), members[0])
        suffix = Path(preferred).suffix.lower()
        if suffix in {".csv", ".txt"}:
            with archive.open(preferred) as member:
                headers, rows = _inspect_csv_bytes(member.read())
            return preferred, headers, rows
        return preferred, [], []


def _inspect_structured_file(path: Path) -> tuple[str, list[str], list[list[str]]]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return _inspect_zip_file(path)
    if suffix in {".csv", ".txt"}:
        return _inspect_csv_file(path)
    if suffix in {".xlsx", ".xls"}:
        return path.name, [], []
    return path.name, [], []


def _extract_html_text(path: Path) -> str:
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return _squash_text(_safe_read_text(path))
    soup = BeautifulSoup(_safe_read_text(path), "html.parser")
    return _squash_text(soup.get_text("\n"))


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    try:
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages[:3])
    except Exception:
        return ""
    return _squash_text(text)


def _count_blocked_artifacts(bundle_manifest: dict[str, Any]) -> int:
    count = 0
    for entry in bundle_manifest.get("document_downloads", []):
        notes = [str(note) for note in entry.get("notes", [])]
        if not entry.get("saved_files") or any(token in note for token in BLOCKED_NOTE_TOKENS for note in notes):
            count += 1
    return count


def _build_dataset_overview_text(entry: dict[str, Any], total_bytes: int) -> str:
    dataset_id = str(entry.get("dataset_id", ""))
    title = str(entry.get("title", dataset_id))
    purpose = ONTOLOGY_DATASET_PURPOSES.get(dataset_id, "온톨로지용 공식 원천 범위를 확인한다.")
    query_axes = ONTOLOGY_QUERY_AXES.get(dataset_id, "데이터셋별 주요 질의 축")
    return (
        f"공식 원천 데이터셋 개요. dataset_id {dataset_id}. 제목 {title}. "
        f"다운로드 모드 {entry.get('download_mode', '')}. 선택 파일 수 {entry.get('selected_file_count', 0)}개. "
        f"총 바이트 {total_bytes}. 페이지 URL {entry.get('page_url', '')}. "
        f"온톨로지 활용 목적: {purpose} 추천 질의 축: {query_axes}."
    )


def build_official_ontology_documents(
    project_root: Path,
    bundle_manifest: dict[str, Any],
    profile: str,
) -> list[RagDocument]:
    documents: list[RagDocument] = []
    for entry in bundle_manifest.get("structured_downloads", []):
        dataset_id = str(entry.get("dataset_id", ""))
        if dataset_id not in ONTOLOGY_STRUCTURED_DATASET_IDS:
            continue
        storage_dir = str(entry.get("storage_dir", ""))
        aliases = _source_aliases(dataset_id, str(entry.get("title", "")), storage_dir)
        source_metadata = {
            "aliases": aliases,
            "source_authority": "official_public_data",
            "question_type": "ontology_source" if dataset_id != "OA-15493" else "realtime_api",
        }
        total_bytes = sum(int(file_entry.get("size_bytes", 0) or 0) for file_entry in entry.get("files", []))
        documents.append(
            RagDocument(
                doc_id=f"ontology-dataset:{dataset_id}",
                text=_build_dataset_overview_text(entry, total_bytes)
                + (f" source aliases: {', '.join(aliases)}." if aliases else ""),
                metadata=_common_metadata(
                    profile=profile,
                    source=str(entry.get("page_url", "")),
                    brief_type="dataset_overview_brief",
                    source_kind="official_ontology",
                    dataset_id=dataset_id,
                    category="structured",
                    local_path=storage_dir,
                )
                | source_metadata,
            )
        )

        if entry.get("download_mode") in {"page_only", "page_and_sheet_view"}:
            dataset_dir = project_root / storage_dir
            page_parts: list[str] = []
            for filename in ["dataset_page.html", "sheet_view.html"]:
                candidate = dataset_dir / filename
                if candidate.exists():
                    page_parts.append(_extract_html_text(candidate))
            page_text = " ".join(part for part in page_parts if part).strip()
            documents.append(
                RagDocument(
                    doc_id=f"ontology-page:{dataset_id}",
                    text=(
                        f"공식 페이지 전용 데이터셋 브리프. dataset_id {dataset_id}. 제목 {entry.get('title', dataset_id)}. "
                        f"접근 방식 {entry.get('download_mode', '')}. 저장 상태 {entry.get('page_status', '')}. "
                        f"페이지 요약 {page_text or '페이지 텍스트 없음'}."
                    ),
                    metadata=_common_metadata(
                        profile=profile,
                        source=str(entry.get("page_url", "")),
                        brief_type="page_only_brief",
                        source_kind="official_ontology",
                        dataset_id=dataset_id,
                        category="structured",
                        local_path=storage_dir,
                    )
                    | source_metadata,
                )
            )
            continue

        for index, file_entry in enumerate(entry.get("files", []), start=1):
            status = str(file_entry.get("status", ""))
            if status not in {"downloaded", "skipped_existing"}:
                continue
            relative_path = str(file_entry.get("path", ""))
            file_path = project_root / relative_path
            member_name = ""
            headers: list[str] = []
            sample_rows: list[list[str]] = []
            if profile == PROFILE_DB_ONLY:
                member_name = file_path.name
            elif file_path.exists():
                member_name, headers, sample_rows = _inspect_structured_file(file_path)
            filename = str(file_entry.get("filename", file_path.name))
            time_token = _time_token_from_filename(filename)
            sample_text = " / ".join(", ".join(row) for row in sample_rows if row)
            documents.append(
                RagDocument(
                    doc_id=f"ontology-file:{dataset_id}:{index}",
                    text=(
                        f"공식 원천 파일 윈도우 브리프. dataset_id {dataset_id}. 파일명 {filename}. "
                        f"시계열 토큰 {time_token or '없음'}. 바이트 {file_entry.get('size_bytes', 0)}. "
                        f"수정일 {file_entry.get('modified_date', '')}. 내부 멤버 {member_name or '없음'}. "
                        f"헤더 컬럼 {', '.join(headers) or '추출 실패 또는 없음'}. "
                        f"샘플 행 {sample_text or '없음'}."
                    ),
                    metadata=_common_metadata(
                        profile=profile,
                        source=relative_path,
                        brief_type="file_window_brief",
                        source_kind="official_ontology",
                        dataset_id=dataset_id,
                        category="structured",
                        local_path=relative_path,
                        time_token=time_token,
                    )
                    | source_metadata
                    | {"internal_member": member_name, "headers": headers},
                )
            )
    return documents


def build_operations_document_documents(
    project_root: Path,
    bundle_manifest: dict[str, Any],
    profile: str,
) -> list[RagDocument]:
    documents: list[RagDocument] = []
    for entry in bundle_manifest.get("document_downloads", []):
        category = str(entry.get("category", ""))
        if category not in ONTOLOGY_DOCUMENT_CATEGORIES:
            continue
        key = str(entry.get("key", ""))
        source_url = str(entry.get("url", ""))
        title = str(entry.get("title", key))
        storage_dir = str(entry.get("storage_dir", ""))
        aliases = _source_aliases(key, category, title, storage_dir)
        alias_text = f" source aliases: {', '.join(aliases)}." if aliases else ""
        source_metadata = {
            "doc_key": key,
            "aliases": aliases,
            "source_authority": "official_operations_document",
            "question_type": _question_type_for_source(key, category, title),
        }
        notes = [str(note) for note in entry.get("notes", [])]
        saved_files = entry.get("saved_files", [])
        is_blocked = (not saved_files) or any(
            token in note for token in BLOCKED_NOTE_TOKENS for note in notes
        )

        if is_blocked:
            documents.append(
                RagDocument(
                    doc_id=f"ops-blocked:{key}",
                    text=(
                        f"차단 또는 미수집 아티팩트 브리프. 문서 키 {key}. 제목 {title}. 카테고리 {category}. "
                        f"가용성 blocked. 원본 URL {source_url}. 기대 문서 역할 {category} 문서 코퍼스 근거. "
                        f"실패 사유 {' / '.join(notes) or '기록 없음'}.{alias_text}"
                    ),
                    metadata=_common_metadata(
                        profile=profile,
                        source=source_url,
                        brief_type="blocked_artifact_brief",
                        source_kind="operations_doc",
                        category=category,
                        local_path=storage_dir,
                        availability="blocked",
                    )
                    | source_metadata,
                )
            )
            continue

        text_parts: list[str] = []
        for saved_file in saved_files:
            relative_path = str(saved_file.get("path", ""))
            path = project_root / relative_path
            if not path.exists():
                continue
            suffix = path.suffix.lower()
            if suffix == ".html":
                text_parts.append(_extract_html_text(path))
            elif profile == PROFILE_DB_ONLY:
                text_parts.append(f"Attachment metadata only for db-only source routing: {path.name}")
            elif suffix == ".pdf":
                pdf_text = _extract_pdf_text(path)
                if pdf_text:
                    text_parts.append(pdf_text)
            elif suffix in HWP_EXTENSIONS:
                text_parts.append(f"HWP/HWPX attachment metadata only: {path.name}")
        excerpt = _squash_text(" ".join(part for part in text_parts if part))
        documents.append(
            RagDocument(
                doc_id=f"ops-doc:{category}:{key}",
                text=(
                    f"운영/공시 문서 브리프. 문서 키 {key}. 제목 {title}. 카테고리 {category}. "
                    f"가용성 available. 첨부 수 {max(len(saved_files) - 1, 0)}개. "
                    f"원본 URL {source_url}. 핵심 텍스트 {excerpt or '본문 추출 없음'}.{alias_text}"
                ),
                metadata=_common_metadata(
                    profile=profile,
                    source=source_url,
                    brief_type="document_overview_brief",
                    source_kind="operations_doc",
                    category=category,
                    local_path=storage_dir,
                    availability="available",
                )
                | source_metadata,
            )
        )
    return documents


def _db_only_source_document(document: RagDocument) -> RagDocument:
    metadata = dict(document.metadata)
    metadata["profile"] = PROFILE_DB_ONLY
    if metadata.get("source_kind") == "official_ontology":
        metadata["source_kind"] = "official_public_source"
    text = document.text.replace("온톨로지 활용 목적", "공식 원천 활용 목적")
    doc_id = document.doc_id
    if doc_id.startswith("ontology-"):
        doc_id = doc_id.replace("ontology-", "official-source-", 1)
    return RagDocument(doc_id=doc_id, text=text, metadata=metadata)


def build_project_documents(
    project_root: Path,
    max_station_docs: int | None = None,
    include_reference_docs: bool = False,
    include_source_documents: bool = False,
) -> list[RagDocument]:
    documents: list[RagDocument] = []
    documents.extend(
        build_station_profile_documents(
            project_root,
            max_station_docs=max_station_docs,
            profile=PROFILE_DB_ONLY,
        )
    )
    documents.extend(build_dataset_inventory_documents(project_root, profile=PROFILE_DB_ONLY))
    documents.extend(build_pandas_aggregate_documents(project_root, profile=PROFILE_DB_ONLY))
    if include_source_documents:
        try:
            _, bundle_manifest = load_ontology_bundle_manifest(project_root)
        except FileNotFoundError:
            bundle_manifest = {}
        if bundle_manifest:
            official_source_documents = [
                _db_only_source_document(document)
                for document in build_official_ontology_documents(project_root, bundle_manifest, PROFILE_DB_ONLY)
            ]
            documents.extend(official_source_documents)
            documents.extend(build_operations_document_documents(project_root, bundle_manifest, PROFILE_DB_ONLY))
    if include_reference_docs:
        documents.extend(build_reference_documents(project_root, profile=PROFILE_DB_ONLY))
    if not documents:
        raise FileNotFoundError("No RAG documents could be built from the project data")
    return documents


def build_corpus_documents(
    project_root: Path,
    profile: str = DEFAULT_RAG_PROFILE,
    max_station_docs: int | None = None,
    include_reference_docs: bool = False,
    repository_ontology_artifact_dir: Path | None = None,
) -> list[RagDocument]:
    resolved_profile = normalize_profile(profile)
    if resolved_profile == PROFILE_DB_ONLY:
        return build_project_documents(
            project_root=project_root,
            max_station_docs=max_station_docs,
            include_reference_docs=include_reference_docs,
            include_source_documents=True,
        )

    _, bundle_manifest = load_ontology_bundle_manifest(project_root)
    documents: list[RagDocument] = []
    documents.extend(
        build_station_profile_documents(
            project_root,
            max_station_docs=max_station_docs,
            profile=resolved_profile,
        )
    )
    documents.extend(build_dataset_inventory_documents(project_root, profile=resolved_profile))
    documents.extend(build_pandas_aggregate_documents(project_root, profile=resolved_profile))
    from rag.ttareungi_ontology_lite import build_ontology_lite_documents
    from generate_ttareungi_domain_ontology import build_domain_ontology_documents

    documents.extend(build_ontology_lite_documents(project_root, profile=resolved_profile))
    documents.extend(build_domain_ontology_documents(project_root, profile=resolved_profile))
    documents.extend(build_official_ontology_documents(project_root, bundle_manifest, resolved_profile))
    documents.extend(build_operations_document_documents(project_root, bundle_manifest, resolved_profile))
    documents.extend(
        build_repository_ontology_artifact_documents(
            artifact_dir=repository_ontology_artifact_dir,
            profile=resolved_profile,
        )
    )
    if include_reference_docs:
        documents.extend(build_reference_documents(project_root, profile=resolved_profile))
    if not documents:
        raise FileNotFoundError("No RAG documents could be built from the ontology-hybrid corpus")
    return documents


def collect_dataset_inventory(project_root: Path) -> list[FactSnippet]:
    snippets: list[FactSnippet] = []
    profiles_by_name = {profile.dataset_name: profile for profile in build_parquet_dataset_profiles(project_root)}
    data_dir = processed_bike_cloud_dir(project_root)
    for filename in PARQUET_CATALOG_FILENAMES:
        path = data_dir / filename
        if not path.exists():
            continue
        profile = profiles_by_name.get(filename)
        if profile:
            read_status = f", 읽기 실패 {profile.read_error}" if profile.read_error else ""
            snippets.append(
                FactSnippet(
                    title=f"데이터셋 {filename}",
                    text=(
                        f"행 수 {profile.row_count:,}건, row group {profile.row_group_count}개, "
                        f"컬럼 {', '.join(profile.columns) or '확인 불가'}, "
                        f"시간 컬럼 {', '.join(profile.time_columns) or '없음'}{read_status}"
                    ),
                    source=profile.source,
                )
            )
            continue
        snippets.append(
            FactSnippet(
                title=f"데이터셋 {filename}",
                text="Parquet 메타데이터 읽기 실패 또는 지원되지 않는 파일",
                source=str(path.relative_to(project_root)),
            )
        )
    return snippets


def _question_terms(question: str) -> list[str]:
    terms = re.findall(r"[0-9a-zA-Z가-힣]+", current_question_text(question))
    stopwords = {"대여소", "따릉이", "알려줘", "어디", "무엇", "어떤", "분석", "현황"}
    return [term for term in terms if len(term) >= 2 and term not in stopwords][:8]


def collect_station_lookup_facts(project_root: Path, question: str, limit: int = 5) -> list[FactSnippet]:
    try:
        import duckdb
    except Exception:
        return []

    branch_path = processed_bike_cloud_dir(project_root) / "branch_data.parquet"
    if not branch_path.exists():
        return []

    terms = _question_terms(question)
    if not terms:
        return []

    snippets: list[FactSnippet] = []
    with duckdb.connect(database=":memory:") as connection:
        for term in terms:
            rows = connection.execute(
                """
                SELECT
                    branchnum,
                    any_value(branchname) AS branchname,
                    any_value(location1) AS location1,
                    any_value(location2) AS location2,
                    max(date) AS latest_date
                FROM read_parquet(?)
                WHERE branchname ILIKE ? OR location1 ILIKE ? OR CAST(branchnum AS VARCHAR) = ?
                GROUP BY branchnum
                ORDER BY branchnum
                LIMIT ?
                """,
                [str(branch_path), f"%{term}%", f"%{term}%", term, limit],
            ).fetchall()
            for row in rows:
                station_id, name, district, address, latest_date = row
                snippets.append(
                    FactSnippet(
                        title=f"대여소 {station_id} {name}",
                        text=f"자치구 {district}, 주소 {address}, 최신 기준일 {latest_date}",
                        source=str(branch_path.relative_to(project_root)),
                    )
                )
            if snippets:
                break
    return snippets


def collect_fault_summary(project_root: Path) -> list[FactSnippet]:
    try:
        import duckdb
    except Exception:
        return []

    broken_path = processed_bike_cloud_dir(project_root) / "broken_data.parquet"
    if not broken_path.exists():
        return []

    with duckdb.connect(database=":memory:") as connection:
        rows = connection.execute(
            """
            SELECT type_bk, count(*) AS fault_count
            FROM read_parquet(?)
            GROUP BY type_bk
            ORDER BY fault_count DESC
            LIMIT 8
            """,
            [str(broken_path)],
        ).fetchall()
    summary = ", ".join(f"{fault_type}: {count:,}건" for fault_type, count in rows)
    return [
        FactSnippet(
            title="고장 유형 상위 집계",
            text=summary,
            source=str(broken_path.relative_to(project_root)),
        )
    ]


def collect_weather_summary(project_root: Path) -> list[FactSnippet]:
    try:
        import duckdb
    except Exception:
        return []

    weather_path = processed_bike_cloud_dir(project_root) / "weather_data.parquet"
    if not weather_path.exists():
        return []

    with duckdb.connect(database=":memory:") as connection:
        row = connection.execute(
            """
            SELECT
                min(datetime) AS start_at,
                max(datetime) AS end_at,
                round(avg(temperature), 2) AS avg_temp,
                round(avg(precipitation), 2) AS avg_precipitation,
                round(avg(windspeed), 2) AS avg_windspeed,
                count(*) AS row_count
            FROM read_parquet(?)
            """,
            [str(weather_path)],
        ).fetchone()
    return [
        FactSnippet(
            title="날씨 데이터 요약",
            text=(
                f"기간 {row[0]}~{row[1]}, 행 수 {row[5]:,}건, "
                f"평균 기온 {row[2]}, 평균 강수량 {row[3]}, 평균 풍속 {row[4]}"
            ),
            source=str(weather_path.relative_to(project_root)),
        )
    ]


def collect_ontology_bundle_inventory(project_root: Path) -> tuple[Path, dict[str, Any]] | None:
    try:
        return load_ontology_bundle_manifest(project_root)
    except FileNotFoundError:
        return None


def collect_ontology_bundle_inventory_facts(project_root: Path, question: str) -> list[FactSnippet]:
    bundle = collect_ontology_bundle_inventory(project_root)
    if not bundle:
        return []

    manifest_path, bundle_manifest = bundle
    lowered = current_question_text(question).lower()
    snippets: list[FactSnippet] = []
    summary = bundle_manifest.get("summary", {})
    structured_entries = bundle_manifest.get("structured_downloads", [])
    document_entries = bundle_manifest.get("document_downloads", [])
    source = str(manifest_path.relative_to(project_root))

    if any(
        keyword in lowered
        for keyword in ["원천", "공식", "생활이동", "수도권", "출도착", "od", "수단", "데이터셋", "다운로드"]
    ):
        dataset_ids = [
            str(entry.get("dataset_id", ""))
            for entry in structured_entries
            if str(entry.get("dataset_id", "")) in ONTOLOGY_STRUCTURED_DATASET_IDS
        ]
        snippets.append(
            FactSnippet(
                title="온톨로지 원천 데이터셋 인벤토리",
                text=(
                    f"공식 원천 데이터셋 {len(dataset_ids)}건. "
                    f"dataset_id: {', '.join(dataset_ids[:10]) or '없음'}"
                ),
                source=source,
            )
        )

    if any(keyword in lowered for keyword in ["문서", "요금", "약관", "공지", "정책", "공시", "보도자료"]):
        categories = sorted({str(entry.get("category", "")) for entry in document_entries if entry.get("category")})
        snippets.append(
            FactSnippet(
                title="운영/공시 문서 코퍼스 인벤토리",
                text=(
                    f"문서 엔트리 {len(document_entries)}건. "
                    f"카테고리 {', '.join(categories) or '없음'}."
                ),
                source=source,
            )
        )

    if any(keyword in lowered for keyword in ["약관", "차단", "blocked", "받았", "다운로드", "공지"]):
        blocked_count = _count_blocked_artifacts(bundle_manifest)
        snippets.append(
            FactSnippet(
                title="차단/미수집 문서 현황",
                text=f"blocked_artifact_count {blocked_count}. 공식 번들 요약 기준으로 추적 중입니다.",
                source=source,
            )
        )

    if not snippets and any(keyword in lowered for keyword in ["api", "실시간", "사고", "안전", "자전거도로"]):
        snippets.append(
            FactSnippet(
                title="온톨로지 번들 요약",
                text=(
                    f"구조화 파일 {summary.get('structured_file_artifact_count', 0)}개, "
                    f"문서 파일 {summary.get('document_file_artifact_count', 0)}개."
                ),
                source=source,
            )
        )

    return snippets


def collect_fact_snippets(
    project_root: Path,
    question: str,
    profile: str = DEFAULT_RAG_PROFILE,
) -> list[FactSnippet]:
    snippets = collect_pandas_fact_snippets(project_root, question)
    if normalize_profile(profile) == PROFILE_ONTOLOGY_HYBRID:
        from rag.ttareungi_ontology_lite import collect_ontology_lite_facts

        snippets.extend(collect_ontology_lite_facts(project_root, question))
        snippets.extend(collect_ontology_bundle_inventory_facts(project_root, question))
    return snippets[:12]


def current_question_text(question: str) -> str:
    marker = "현재 질문:"
    if marker not in question:
        return question
    return question.rsplit(marker, 1)[-1].strip()


def is_capability_question(question: str) -> bool:
    normalized = re.sub(r"\s+", "", current_question_text(question).lower())
    capability_patterns = [
        "뭘할수있",
        "뭐할수있",
        "무엇을할수있",
        "어떤걸할수있",
        "어떤것을할수있",
        "기능",
        "사용법",
        "도움말",
        "help",
        "whatcanyoudo",
        "capabilities",
    ]
    return any(pattern in normalized for pattern in capability_patterns)


def is_ttareungi_related_question(question: str) -> bool:
    text = current_question_text(question).lower()
    compact = re.sub(r"\s+", "", text)
    related_keywords = [
        "따릉이",
        "공공자전거",
        "서울자전거",
        "대여소",
        "망원역",
        "자치구",
        "마포구",
        "광진구",
        "동대문구",
        "branch_data",
        "broken_data",
        "count_data",
        "rent_data",
        "uselate_data",
        "weather_data",
        "parquet",
        "데이터셋",
        "데이터",
        "컬럼",
        "고장",
        "장애",
        "점검",
        "수리",
        "날씨",
        "기온",
        "강수",
        "풍속",
        "대여",
        "반납",
        "거치",
        "운영",
        "생활이동",
        "수도권",
        "출도착",
        "od",
        "수단",
        "요금",
        "약관",
        "공지",
        "정책",
        "공시",
        "보도자료",
        "api",
        "실시간",
        "자전거도로",
        "사고",
        "이용량",
        "시간대",
        "사용자",
        "obybk",
        "추천",
        "승인",
        "검토",
        "근거",
        "보류",
        "답변 품질",
        "평가 기준",
        "온톨로지",
        "ontology",
        "ontology_seed",
        "reviewed_ontology_blueprint",
        "recommendation",
        "reviewdecision",
        "evidence",
    ]
    if any(keyword in text for keyword in related_keywords):
        return True
    station_pattern = re.search(r"(st-\d+|\b\d{2,5}\s*번?\s*대여소)", compact)
    return station_pattern is not None


def build_capability_answer() -> str:
    return """제가 할 수 있는 일은 따릉이 운영 데이터 + 공식 원천/문서 코퍼스 기반 질의입니다.

- 대여소 위치/주소/자치구 조회: 예) "망원역 대여소 위치 알려줘"
- 데이터셋 규모와 컬럼 확인: 예) "따릉이 데이터셋 컬럼 보여줘"
- 고장 유형 상위 집계 확인: 예) "고장 데이터로 뭘 볼 수 있어?"
- 날씨 데이터 요약 확인: 예) "날씨 데이터 기간과 평균값 알려줘"
- 수도권 생활이동/출도착 원천 확인: 예) "수도권 생활이동 원천 어떤 게 있어?"
- 요금/약관/공지/정책 문서 확인: 예) "따릉이 요금 관련 문서 보여줘"
- 후속 질문 이어가기: 예) "그 대여소 고장 데이터도 같이 봐줘"

현재 기본 검색 범위는 운영 Parquet + 공식 원천 다운로드 번들 + 운영/공시 문서 브리프입니다.
주요 source: branch_data.parquet, broken_data.parquet, count_data.parquet, rent_data.parquet, uselate_data.parquet, weather_data.parquet, newmeta.parquet, OA-15182, OA-22300, OA-22657, service/policy/sanction/press/procurement/api_specs"""


def build_general_chat_answer(question: str) -> str:
    text = current_question_text(question).strip()
    if any(greeting in text for greeting in ["안녕", "하이", "hello", "hi"]):
        return "안녕하세요. 편하게 대화하다가 따릉이 관련 질문이 나오면 운영 데이터와 공식 원천/문서 근거로 찾아드릴게요."
    return "일반 대화로 이해했어요. 따릉이 관련 질문을 하시면 대여소, 고장, 날씨, 생활이동, 요금/약관 문서를 운영 데이터와 공식 원천/문서에서 찾아드릴게요."


def _format_doc_context(search_results: Sequence[SearchResult]) -> str:
    return "\n\n".join(
        [
            f"[문서 {result.rank} | score={result.score:.3f} | id={result.document.doc_id} | "
            f"source={result.document.metadata.get('source', 'unknown')}]\n{result.document.text}"
            for result in search_results
        ]
    )


def _format_fact_context(facts: Sequence[FactSnippet]) -> str:
    return "\n".join(
        f"- {fact.title}: {fact.text} (source: {fact.source})" for fact in facts
    )


def build_prompt(question: str, search_results: Sequence[SearchResult], facts: Sequence[FactSnippet]) -> str:
    doc_context = _format_doc_context(search_results)
    fact_context = _format_fact_context(facts)
    return f"""질문:
{question}

구조화 데이터 근거:
{fact_context or "- 직접 조회된 구조화 근거 없음"}

RAG 검색 근거:
{doc_context or "- RAG 검색 근거 없음"}

답변 규칙:
- 한국어로 답변한다.
- 근거 없는 숫자나 원인을 만들지 않는다.
- 데이터 근거가 부족하면 부족하다고 말한다.
- 마지막에 사용한 source를 짧게 적는다.
"""


def build_context_report(question: str, search_results: Sequence[SearchResult], facts: Sequence[FactSnippet]) -> str:
    doc_context = _format_doc_context(search_results)
    fact_context = _format_fact_context(facts)
    return f"""질문:
{current_question_text(question)}

구조화 데이터 근거:
{fact_context or "- 직접 조회된 구조화 근거 없음"}

RAG 검색 근거:
{doc_context or "- RAG 검색 근거 없음"}
"""


def _chat_url(base_url: str) -> str:
    stripped = base_url.rstrip("/")
    if stripped.endswith("/chat/completions"):
        return stripped
    if stripped.endswith("/v1"):
        return f"{stripped}/chat/completions"
    return f"{stripped}/v1/chat/completions"


def _resolve_project_file(project_root: Path, path: Path | str | None) -> Path:
    if path is None:
        return project_root / DEFAULT_OPENAI_API_KEY_FILE
    resolved = Path(path).expanduser()
    return resolved if resolved.is_absolute() else project_root / resolved


def _clean_setting_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def load_llm_api_key_file(
    project_root: Path,
    key_file: Path | str | None = DEFAULT_OPENAI_API_KEY_FILE,
) -> dict[str, str]:
    path = _resolve_project_file(project_root, key_file)
    if not path.exists():
        return {}

    settings: dict[str, str] = {}
    raw_key_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, value = stripped.split("=", 1)
            settings[key.strip()] = _clean_setting_value(value)
        else:
            raw_key_lines.append(stripped)
    if raw_key_lines and "OPENAI_API_KEY" not in settings:
        settings["OPENAI_API_KEY"] = raw_key_lines[0]
    return settings


def resolve_llm_runtime_settings(
    project_root: Path,
    provider: str = LLM_PROVIDER_LOCAL,
    llm_url: str = DEFAULT_LLM_URL,
    model: str = DEFAULT_QWEN_MODEL,
    api_key_file: Path | str | None = DEFAULT_OPENAI_API_KEY_FILE,
    api_key_env: str = DEFAULT_OPENAI_API_KEY_ENV,
) -> LlmRuntimeSettings:
    normalized_provider = provider if provider in LLM_PROVIDER_CHOICES else LLM_PROVIDER_LOCAL
    file_settings = load_llm_api_key_file(project_root, api_key_file)
    env_key = os.getenv(api_key_env, "").strip() if api_key_env else ""
    file_key = file_settings.get("OPENAI_API_KEY", "").strip()
    api_key = env_key or file_key

    if normalized_provider == LLM_PROVIDER_OPENAI:
        file_base_url = file_settings.get("OPENAI_BASE_URL", "").strip()
        file_model = file_settings.get("OPENAI_MODEL", "").strip()
        resolved_url = file_base_url or DEFAULT_OPENAI_BASE_URL
        resolved_model = file_model or DEFAULT_OPENAI_MODEL
        if llm_url and llm_url != DEFAULT_LLM_URL:
            resolved_url = llm_url
        if model and model != DEFAULT_QWEN_MODEL:
            resolved_model = model
        return LlmRuntimeSettings(llm_url=resolved_url, model=resolved_model, api_key=api_key)

    return LlmRuntimeSettings(llm_url=llm_url or DEFAULT_LLM_URL, model=model or DEFAULT_QWEN_MODEL, api_key="")


def call_qwen_chat(
    prompt: str,
    llm_url: str = DEFAULT_LLM_URL,
    model: str = DEFAULT_QWEN_MODEL,
    max_tokens: int = 900,
    temperature: float = 0.1,
    api_key: str = "",
) -> str:
    import requests

    system_prompt = (
        "너는 따릉이 운영 AS-IS 분석용 RAG 챗봇이다. /no_think\n"
        "반드시 제공된 구조화 데이터와 RAG 검색 근거 안에서만 답한다."
    )
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    if "api.openai.com" in llm_url:
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["temperature"] = temperature
        payload["max_tokens"] = max_tokens
    response = requests.post(
        _chat_url(llm_url),
        headers=headers,
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["choices"][0]["message"]["content"]


def answer_question(
    question: str,
    project_root: Path,
    index_dir: Path,
    embedder: HashingEmbedder | SentenceTransformerEmbedder,
    top_k: int = 5,
    use_llm: bool = True,
    llm_url: str = DEFAULT_LLM_URL,
    model: str = DEFAULT_QWEN_MODEL,
    profile: str = DEFAULT_RAG_PROFILE,
    llm_provider: str = LLM_PROVIDER_LOCAL,
    api_key_file: Path | str | None = DEFAULT_OPENAI_API_KEY_FILE,
    api_key_env: str = DEFAULT_OPENAI_API_KEY_ENV,
) -> str:
    if is_capability_question(question):
        return build_capability_answer()

    retrieval_question = current_question_text(question)
    if not is_ttareungi_related_question(retrieval_question):
        return build_general_chat_answer(retrieval_question)

    results = search_faiss_index(retrieval_question, index_dir, embedder, top_k=top_k)
    facts = [
        *collect_repository_ontology_relation_facts(index_dir, retrieval_question),
        *collect_repository_ontology_artifact_facts(index_dir, retrieval_question),
        *collect_fact_snippets(project_root, retrieval_question, profile=profile),
    ]
    prompt = build_prompt(question, results, facts)
    context_report = build_context_report(question, results, facts)

    if not use_llm:
        return "LLM 호출 없이 검색 컨텍스트만 반환합니다.\n\n" + context_report

    try:
        runtime = resolve_llm_runtime_settings(
            project_root=project_root,
            provider=llm_provider,
            llm_url=llm_url,
            model=model,
            api_key_file=api_key_file,
            api_key_env=api_key_env,
        )
        return call_qwen_chat(
            prompt=prompt,
            llm_url=runtime.llm_url,
            model=runtime.model,
            api_key=runtime.api_key,
        )
    except Exception as exc:
        return (
            "LLM 서버 호출에 실패해 검색 컨텍스트를 반환합니다.\n"
            f"오류: {type(exc).__name__}: {exc}\n\n"
            + context_report
        )


def build_rag_index(
    project_root: Path,
    index_dir: Path,
    max_station_docs: int = 500,
    embedding_backend: str = "auto",
    profile: str = DEFAULT_RAG_PROFILE,
    repository_ontology_artifact_dir: Path | None = None,
) -> None:
    resolved_profile = normalize_profile(profile)
    documents = build_corpus_documents(
        project_root,
        profile=resolved_profile,
        max_station_docs=max_station_docs,
        repository_ontology_artifact_dir=repository_ontology_artifact_dir,
    )
    embedder = create_embedder(backend=embedding_backend)
    corpus_counts: dict[str, int] = {}
    for document in documents:
        brief_type = str(document.metadata.get("brief_type", "unknown"))
        corpus_counts[brief_type] = corpus_counts.get(brief_type, 0) + 1

    extra_manifest: dict[str, Any] = {
        "profile": resolved_profile,
        "source_manifest": None,
        "corpus_counts": corpus_counts,
        "blocked_artifact_count": 0,
        "dataset_profile_count": len(build_parquet_dataset_profiles(project_root)),
        "repository_ontology_artifact_dir": str(_resolve_repository_ontology_artifact_dir(repository_ontology_artifact_dir) or ""),
        "db_only_scope": (
            "processed_parquet_plus_official_source_briefs_no_generated_ontology"
            if resolved_profile == PROFILE_DB_ONLY
            else ""
        ),
    }
    if resolved_profile == PROFILE_ONTOLOGY_HYBRID:
        manifest_path, bundle_manifest = load_ontology_bundle_manifest(project_root)
        extra_manifest["source_manifest"] = str(manifest_path.relative_to(project_root))
        extra_manifest["blocked_artifact_count"] = _count_blocked_artifacts(bundle_manifest)
    elif resolved_profile == PROFILE_DB_ONLY:
        try:
            manifest_path, bundle_manifest = load_ontology_bundle_manifest(project_root)
            extra_manifest["source_manifest"] = str(manifest_path.relative_to(project_root))
            extra_manifest["blocked_artifact_count"] = _count_blocked_artifacts(bundle_manifest)
        except FileNotFoundError:
            pass

    build_faiss_index(documents, index_dir, embedder, extra_manifest=extra_manifest)


def build_rag_eval_questions(project_root: Path, output_path: Path, count: int = 100) -> list[dict[str, Any]]:
    timestamp = _now()
    dataset_sources = {profile.dataset_name for profile in build_parquet_dataset_profiles(project_root)}
    ontology_sources = sorted(ONTOLOGY_STRUCTURED_DATASET_IDS)
    base_questions = [
        ("dataset_identification", "따릉이 대여소 위치와 주소는 어떤 데이터셋을 봐야 해?", ["branch_data.parquet"], ["branchnum", "branchname", "location1", "location2"], "branch_data.parquet의 대여소 번호, 이름, 자치구, 주소 컬럼을 사용한다."),
        ("schema", "따릉이 운영 Parquet 데이터셋들의 컬럼과 행 수를 알려줘.", sorted(dataset_sources), ["columns", "row_count"], "Parquet catalog의 row_count와 columns를 근거로 답한다."),
        ("station_lookup", "망원역 1번출구 앞 대여소의 자치구와 주소는?", ["branch_data.parquet"], ["branchname", "location1", "location2"], "branch_data.parquet 최신 대여소 프로필에서 자치구와 주소를 답한다."),
        ("fault", "고장 유형 상위 분포는 어떤 데이터로 확인해?", ["broken_data.parquet"], ["date_bk", "type_bk", "bikenum"], "broken_data.parquet의 type_bk 집계를 사용한다."),
        ("weather", "평균 기온과 강수량은 어떤 근거로 답해야 해?", ["weather_data.parquet"], ["datetime", "temperature", "precipitation"], "weather_data.parquet의 날씨 집계를 사용한다."),
        ("usage", "대여와 반납 이용량 추세는 어떤 데이터셋을 봐야 해?", ["count_data.parquet", "rent_data.parquet"], ["rent_count", "return_count", "rentstation", "returnstation"], "count_data 또는 rent_data 집계 브리프를 사용한다."),
        ("late_usage", "지연 또는 연체 이용은 어떤 데이터로 확인할 수 있어?", ["uselate_data.parquet"], ["date", "branchnum", "uselate_count"], "uselate_data.parquet의 지연/연체 집계를 사용한다."),
        ("signup", "신규가입자의 연령과 성별 정보는 어디에 있어?", ["newmeta.parquet"], ["new_dt", "age", "gender", "new"], "newmeta.parquet의 가입자 메타 컬럼을 사용한다."),
        ("station_master", "대여소 master 속성은 어떤 파일에서 확인해?", ["master_branch_data.parquet"], ["branchnum", "branchname"], "master_branch_data.parquet를 대여소 master 근거로 사용한다."),
        ("metadata", "운영 데이터 메타 정보는 어떤 파일에 있어?", ["meta.parquet"], ["date", "source", "rows"], "meta.parquet를 보조 메타 근거로 사용한다."),
        ("ontology_source", "수도권 생활이동 출발-도착지 기준 원천은 어떤 dataset_id야?", ["OA-22300"], ["dataset_id", "page_url"], "OA-22300 공식 원천 브리프를 사용한다."),
        ("ontology_source", "수단별 수도권 생활이동은 어떤 공식 원천을 봐야 해?", ["OA-22657"], ["dataset_id", "transport_mode"], "OA-22657 공식 원천 브리프를 사용한다."),
        ("ontology_source", "정류장/역사 단위 출도착은 어떤 원천이야?", ["OA-21222"], ["dataset_id", "station"], "OA-21222 공식 원천 브리프를 사용한다."),
        ("realtime_api", "따릉이 실시간 대여정보 API는 어떤 원천으로 확인해?", ["OA-15493"], ["dataset_id", "api"], "OA-15493 page-only/API 브리프를 사용한다."),
        ("bike_road", "자전거도로 현황 통계는 어떤 공식 원천이야?", ["OA-714"], ["dataset_id", "sheet_view"], "OA-714 page/sheet 브리프를 사용한다."),
        ("accident", "자전거 사고 통계는 어떤 공식 원천이야?", ["OA-12849"], ["dataset_id", "accident"], "OA-12849 page/sheet 브리프를 사용한다."),
        ("service_doc", "따릉이 이용요금은 어떤 문서 근거로 답해야 해?", ["pricing_info"], ["category", "doc_key"], "service/pricing_info 운영 문서 브리프를 사용한다."),
        ("policy_doc", "자전거 이용 활성화 계획은 어떤 정책 문서에서 찾아?", ["research_27078570", "sanction_34844148"], ["category", "doc_key"], "policy 문서 브리프를 사용한다."),
        ("procurement_doc", "2026년 공공자전거 정비용역 정보는 어디에 있어?", ["g2b_r26bk01319050_file1", "g2b_r26bk01319050_file3"], ["category", "doc_key"], "procurement 문서 브리프를 사용한다."),
        ("blocked_doc", "따릉이 이용약관 PDF 2024-04-23은 수집됐어?", ["terms_pdf_2024_04_23"], ["availability", "notes"], "blocked_artifact_brief에서 차단 또는 미수집 상태를 답한다."),
    ]
    paraphrases = [
        "{question}",
        "{question} 사용해야 할 source도 같이 알려줘.",
        "{question} 기대되는 데이터 필드까지 말해줘.",
        "{question} 근거 부족하면 부족하다고 표시해줘.",
        "{question} RAG 평가용 정답 기준으로 짧게 답해줘.",
    ]

    rows: list[dict[str, Any]] = []
    for base_index, (question_type, question, sources, fields, answer) in enumerate(base_questions, start=1):
        for variant_index, template in enumerate(paraphrases, start=1):
            rows.append(
                {
                    "timestamp": timestamp,
                    "id": f"ttareungi-rag-{base_index:02d}-{variant_index:02d}",
                    "question": template.format(question=question),
                    "question_type": question_type,
                    "expected_sources": sources,
                    "expected_data_fields": fields,
                    "expected_answer": answer,
                    "actual_answer": "",
                    "judge_rule": "expected_sources 중 하나 이상을 근거로 사용하고, expected_answer와 모순되지 않아야 한다.",
                }
            )
    rows = rows[:count]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return rows


def inspect_data(project_root: Path) -> str:
    snippets = collect_dataset_inventory(project_root)
    lines = ["# Timestamp: " + _now(), "# 따릉이 RAG 데이터 인벤토리", ""]
    for snippet in snippets:
        lines.append(f"- {snippet.title}: {snippet.text} ({snippet.source})")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OBYBK Ttareung-i Qwen3 RAG chatbot MVP")
    parser.add_argument("--project-root", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build-index", help="Build the local FAISS RAG index")
    build_parser.add_argument("--index-dir", type=Path, default=None)
    build_parser.add_argument("--profile", choices=PROFILE_CHOICES, default=DEFAULT_RAG_PROFILE)
    build_parser.add_argument("--max-station-docs", type=int, default=500)
    build_parser.add_argument("--repository-ontology-artifact-dir", type=Path, default=None)
    build_parser.add_argument(
        "--embedding-backend",
        choices=["hashing", "auto", "sentence-transformers"],
        default="auto",
    )

    ask_parser = subparsers.add_parser("ask", help="Ask the RAG chatbot")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--index-dir", type=Path, default=None)
    ask_parser.add_argument("--profile", choices=PROFILE_CHOICES, default=DEFAULT_RAG_PROFILE)
    ask_parser.add_argument("--llm-provider", choices=LLM_PROVIDER_CHOICES, default=LLM_PROVIDER_LOCAL)
    ask_parser.add_argument("--api-key-file", type=Path, default=DEFAULT_OPENAI_API_KEY_FILE)
    ask_parser.add_argument("--api-key-env", default=DEFAULT_OPENAI_API_KEY_ENV)
    ask_parser.add_argument("--top-k", type=int, default=5)
    ask_parser.add_argument("--no-llm", action="store_true")
    ask_parser.add_argument("--llm-url", default=DEFAULT_LLM_URL)
    ask_parser.add_argument("--model", default=DEFAULT_QWEN_MODEL)
    ask_parser.add_argument(
        "--embedding-backend",
        choices=["hashing", "auto", "sentence-transformers"],
        default="auto",
    )

    eval_parser = subparsers.add_parser("build-eval-questions", help="Build the RAG evaluation question set")
    eval_parser.add_argument("--output-path", type=Path, default=None)
    eval_parser.add_argument("--count", type=int, default=100)

    subparsers.add_parser("inspect-data", help="Print dataset inventory")

    args = parser.parse_args(argv)
    project_root = args.project_root or find_project_root(Path(__file__))

    if args.command == "build-index":
        index_dir = args.index_dir or default_index_dir(project_root, profile=args.profile)
        build_rag_index(
            project_root=project_root,
            index_dir=index_dir,
            max_station_docs=args.max_station_docs,
            embedding_backend=args.embedding_backend,
            profile=args.profile,
            repository_ontology_artifact_dir=args.repository_ontology_artifact_dir,
        )
        print(f"# Timestamp: {_now()}")
        print(f"Built RAG index: {index_dir}")
        return 0

    if args.command == "ask":
        index_dir = args.index_dir or default_index_dir(project_root, profile=args.profile)
        embedder = create_embedder_for_index(index_dir=index_dir, backend=args.embedding_backend)
        print(
            answer_question(
                question=args.question,
                project_root=project_root,
                index_dir=index_dir,
                embedder=embedder,
                top_k=args.top_k,
                use_llm=not args.no_llm,
                llm_url=args.llm_url,
                model=args.model,
                profile=args.profile,
                llm_provider=args.llm_provider,
                api_key_file=args.api_key_file,
                api_key_env=args.api_key_env,
            )
        )
        return 0

    if args.command == "build-eval-questions":
        output_path = args.output_path or (
            project_root / "data" / "processed" / "rag" / "ttareungi_rag_eval_questions.jsonl"
        )
        rows = build_rag_eval_questions(project_root=project_root, output_path=output_path, count=args.count)
        print(f"# Timestamp: {_now()}")
        print(f"Built RAG eval questions: {output_path} ({len(rows)} rows)")
        return 0

    if args.command == "inspect-data":
        print(inspect_data(project_root))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
