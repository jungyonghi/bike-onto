# Timestamp: 2026-04-20 20:12:00
# Timestamp: 2026-04-20 21:10:00
# Timestamp: 2026-04-20 21:22:00

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CandidateRecord:
    surface_form: str
    normalized_form: str
    canonical_candidate: str
    candidate_type: str
    business_relevance: int
    general_reusability: int
    cross_domain_applicability: int
    relational_centrality: int
    abstraction_fitness: int
    ontological_clarity: int
    composability: int
    compression_survival_likelihood: int
    is_domain_specific: bool
    generalizable: bool
    suggested_generalization: str
    promotion_decision: str
    notes: str
    antonyms: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CandidateRecord":
        normalized_payload = dict(payload)
        antonyms = normalized_payload.get("antonyms", [])
        normalized_payload["antonyms"] = antonyms if isinstance(antonyms, list) else []
        return cls(**normalized_payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RawCandidateRecord:
    raw_term: str
    source_field: str
    generation_stratum: str
    general_category: str
    description: str
    notes: str
    raw_payload_json: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RawCandidateRecord":
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MergeRecord:
    canonical_candidate: str
    duplicate_group: list[str]
    relation_among_candidates: str
    merge_recommendation: str
    notes: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MergeRecord":
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PromotionRecord:
    promotion_decision: str
    canonical_name: str
    short_definition: str
    rationale: str
    possible_parent_classes: list[str]
    possible_related_classes: list[str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PromotionRecord":
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunSummary:
    target_ratio: dict[str, float]
    observed_ratio: dict[str, float]
    general_category_balance: dict[str, int]
    review_count: int
    rejected_count: int
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ChunkRecord:
    chunk_id: str
    heading_path: list[str]
    text: str
    source_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PhaseDocument:
    phase_key: str
    path: Path
    raw_text: str
    prompt_template: str


@dataclass(slots=True)
class ProtocolBundle:
    overview_path: Path
    overview_text: str
    system_prompt: str
    phase_docs: dict[str, PhaseDocument]


@dataclass(slots=True)
class LlamaServerConfig:
    llama_server_bin: Path
    llama_server_lib_dir: Path
    model_path: Path
    host: str
    port: int
    ctx_size: int
    parallel: int
    ngl: int
    no_kv_offload: bool = True
    extra_args: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PhaseContext:
    protocol_root_dir: Path
    run_output_dir: Path
    protocol_bundle: ProtocolBundle
    host: str
    port: int
    phase_a_max_candidates: int = 10000
    phase_a_raw_target: int | None = None
