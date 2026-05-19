# Timestamp: 2026-05-11 10:57:52

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


TARGET_COUNT = 1000
GENERAL_CATEGORIES = [
    "actor/person",
    "organization",
    "place/location",
    "time/schedule",
    "object/asset",
    "event",
    "process/capability",
    "information/document",
    "contract/policy/right",
    "value/cost/revenue",
    "risk/compliance",
    "channel/interface/touchpoint",
]
FACETS = [
    ("Identity", "attribute_candidate"),
    ("Boundary", "attribute_candidate"),
    ("Role", "role_candidate"),
    ("State", "state_candidate"),
    ("Relation", "relation_candidate"),
    ("Lifecycle", "process_candidate"),
    ("Evidence", "class_candidate"),
]
CATEGORY_SUBJECTS = {
    "actor/person": [
        "Agent",
        "Person",
        "Role Bearer",
        "Participant",
        "Observer",
        "Decision Maker",
        "Beneficiary",
        "Contributor",
        "Custodian",
        "Accountable Party",
        "Stakeholder",
        "Community Member",
    ],
    "organization": [
        "Organization",
        "Organizational Unit",
        "Governance Body",
        "Legal Entity",
        "Team",
        "Department",
        "Operating Group",
        "Partner Network",
        "Authority",
        "Committee",
        "Institution",
        "Service Provider",
    ],
    "place/location": [
        "Place",
        "Location",
        "Region",
        "Site",
        "Facility",
        "Zone",
        "Route",
        "Boundary Area",
        "Address",
        "Access Point",
        "Spatial Cluster",
        "Jurisdiction",
    ],
    "time/schedule": [
        "Time Instant",
        "Time Interval",
        "Duration",
        "Schedule",
        "Calendar Period",
        "Recurrence",
        "Deadline",
        "Sequence",
        "Temporal Window",
        "Cycle",
        "Milestone",
        "Time Horizon",
    ],
    "object/asset": [
        "Physical Object",
        "Asset",
        "Resource",
        "Equipment",
        "Device",
        "Container",
        "Material",
        "Inventory Item",
        "Component",
        "Product",
        "Tool",
        "Infrastructure Element",
    ],
    "event": [
        "Event",
        "Incident",
        "Transaction",
        "Interaction",
        "Trigger",
        "Transition",
        "Change Event",
        "Failure Event",
        "Completion Event",
        "Observation Event",
        "Exception Event",
        "Notification Event",
    ],
    "process/capability": [
        "Process",
        "Activity",
        "Capability",
        "Operation",
        "Workflow",
        "Procedure",
        "Function",
        "Transformation",
        "Assessment",
        "Decision Process",
        "Control Process",
        "Coordination Process",
    ],
    "information/document": [
        "Information Object",
        "Document",
        "Record",
        "Dataset",
        "Assertion",
        "Measurement",
        "Identifier",
        "Classification",
        "Evidence Item",
        "Report",
        "Message",
        "Metadata",
    ],
    "contract/policy/right": [
        "Policy",
        "Rule",
        "Contract",
        "Agreement",
        "Right",
        "Obligation",
        "Permission",
        "Prohibition",
        "Entitlement",
        "Commitment",
        "Constraint",
        "Norm",
    ],
    "value/cost/revenue": [
        "Value",
        "Cost",
        "Revenue",
        "Price",
        "Fee",
        "Budget",
        "Benefit",
        "Loss",
        "Incentive",
        "Resource Allocation",
        "Economic Exchange",
        "Valuation",
    ],
    "risk/compliance": [
        "Risk",
        "Hazard",
        "Threat",
        "Vulnerability",
        "Control",
        "Requirement",
        "Compliance Obligation",
        "Violation",
        "Exception",
        "Mitigation",
        "Audit Finding",
        "Assurance",
    ],
    "channel/interface/touchpoint": [
        "Channel",
        "Interface",
        "Touchpoint",
        "Endpoint",
        "Portal",
        "Form",
        "Message Flow",
        "Interaction Surface",
        "Access Mechanism",
        "Notification Channel",
        "Service Window",
        "Integration Point",
    ],
}
ANTONYM_AXES = {
    "Boundary": ["unboundedness"],
    "State": ["transition"],
    "Lifecycle": ["stasis"],
    "Permission": ["prohibition"],
    "Prohibition": ["permission"],
    "Obligation": ["exemption"],
    "Risk": ["assurance"],
    "Loss": ["benefit"],
    "Cost": ["benefit"],
    "Revenue": ["expense"],
}


@dataclass(frozen=True)
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
    antonyms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionRecord:
    promotion_decision: str
    canonical_name: str
    short_definition: str
    rationale: str
    possible_parent_classes: list[str]
    possible_related_classes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _targets_by_category(total: int) -> dict[str, int]:
    base = total // len(GENERAL_CATEGORIES)
    remainder = total % len(GENERAL_CATEGORIES)
    return {
        category: base + (1 if index < remainder else 0)
        for index, category in enumerate(GENERAL_CATEGORIES)
    }


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())


def _promotion_decision(subject_index: int, facet: str) -> str:
    if subject_index < 4 or facet in {"Identity", "State", "Relation"}:
        return "core_upper"
    return "general_reference"


def _antonyms(surface_form: str, facet: str) -> list[str]:
    for key, values in ANTONYM_AXES.items():
        if key.lower() in surface_form.lower() or key == facet:
            return values
    return []


def _scores(decision: str) -> dict[str, int]:
    if decision == "core_upper":
        return {
            "business_relevance": 2,
            "general_reusability": 5,
            "cross_domain_applicability": 5,
            "relational_centrality": 5,
            "abstraction_fitness": 5,
            "ontological_clarity": 4,
            "composability": 5,
            "compression_survival_likelihood": 5,
        }
    return {
        "business_relevance": 2,
        "general_reusability": 5,
        "cross_domain_applicability": 5,
        "relational_centrality": 4,
        "abstraction_fitness": 4,
        "ontological_clarity": 4,
        "composability": 4,
        "compression_survival_likelihood": 4,
    }


def _make_candidate(
    category: str,
    subject: str,
    subject_index: int,
    facet: str,
    candidate_type: str,
    timestamp: str,
) -> CandidateRecord:
    surface_form = f"{subject} {facet}"
    canonical = _normalize(surface_form)
    decision = _promotion_decision(subject_index, facet)
    scores = _scores(decision)
    notes = (
        "codex_upper_ontology_seed | "
        f"general_category={category} | concept_family={subject} | facet={facet} | "
        "knowledge_source=codex_agent | protocol=step_01_candidate_record | "
        f"# Timestamp: {timestamp}"
    )
    return CandidateRecord(
        surface_form=surface_form,
        normalized_form=canonical,
        canonical_candidate=canonical,
        candidate_type=candidate_type,
        business_relevance=scores["business_relevance"],
        general_reusability=scores["general_reusability"],
        cross_domain_applicability=scores["cross_domain_applicability"],
        relational_centrality=scores["relational_centrality"],
        abstraction_fitness=scores["abstraction_fitness"],
        ontological_clarity=scores["ontological_clarity"],
        composability=scores["composability"],
        compression_survival_likelihood=scores["compression_survival_likelihood"],
        is_domain_specific=False,
        generalizable=False,
        suggested_generalization=subject,
        promotion_decision=decision,
        notes=notes,
        antonyms=_antonyms(surface_form, facet),
    )


def _make_promotion(candidate: CandidateRecord, category: str, timestamp: str) -> PromotionRecord:
    canonical_name = candidate.surface_form
    return PromotionRecord(
        promotion_decision=candidate.promotion_decision,
        canonical_name=canonical_name,
        short_definition=(
            f"A reusable upper-ontology concept for modeling {canonical_name.lower()} "
            "across domains and application ontologies."
        ),
        rationale=(
            f"Selected as {candidate.promotion_decision} because it is domain-neutral, "
            f"composable, and belongs to the balanced upper category {category}. "
            f"# Timestamp: {timestamp}"
        ),
        possible_parent_classes=["Upper Ontology Concept", category],
        possible_related_classes=[
            candidate.suggested_generalization,
            "Identity" if "Identity" not in canonical_name else "Relation",
            "Evidence" if "Evidence" not in canonical_name else "State",
        ],
    )


def build_upper_ontology_seed(timestamp: str | None = None, total: int = TARGET_COUNT) -> dict[str, Any]:
    resolved_timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    targets = _targets_by_category(total)
    candidates: list[CandidateRecord] = []
    promotions: list[PromotionRecord] = []
    balance = {category: 0 for category in GENERAL_CATEGORIES}

    for category in GENERAL_CATEGORIES:
        target = targets[category]
        category_candidates: list[CandidateRecord] = []
        for subject_index, subject in enumerate(CATEGORY_SUBJECTS[category]):
            for facet, candidate_type in FACETS:
                category_candidates.append(
                    _make_candidate(
                        category=category,
                        subject=subject,
                        subject_index=subject_index,
                        facet=facet,
                        candidate_type=candidate_type,
                        timestamp=resolved_timestamp,
                    )
                )
        selected = category_candidates[:target]
        candidates.extend(selected)
        promotions.extend(_make_promotion(candidate, category, resolved_timestamp) for candidate in selected)
        balance[category] = len(selected)

    core_upper_count = sum(1 for item in candidates if item.promotion_decision == "core_upper")
    general_reference_count = len(candidates) - core_upper_count
    run_summary = {
        "target_ratio": {
            "business_archetype": 0.0,
            "general_reference_plus_core_upper": 1.0,
        },
        "observed_ratio": {
            "business_archetype": 0.0,
            "core_upper": round(core_upper_count / len(candidates), 4),
            "general_reference": round(general_reference_count / len(candidates), 4),
            "general_reference_plus_core_upper": 1.0,
        },
        "general_category_balance": balance,
        "review_count": 0,
        "rejected_count": 0,
        "notes": (
            "knowledge_source=codex_agent | mode=upper_ontology_only | "
            "shape=candidate_record+promotion_record | "
            f"# Timestamp: {resolved_timestamp}"
        ),
    }
    return {
        "timestamp": resolved_timestamp,
        "generation_source": "codex_agent",
        "execution_mode": "codex_upper_ontology_seed",
        "input_mode": "protocol_native_upper_only",
        "target_count": total,
        "candidate_records": [candidate.to_dict() for candidate in candidates],
        "merge_records": [],
        "promotion_records": [promotion.to_dict() for promotion in promotions],
        "run_summary": run_summary,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_candidate_csv(path: Path, payload: dict[str, Any]) -> None:
    fieldnames = list(CandidateRecord.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# Timestamp: {payload['timestamp']}\n")
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in payload["candidate_records"]:
            row = dict(record)
            row["antonyms"] = "|".join(row["antonyms"])
            writer.writerow(row)


def _write_readme(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["run_summary"]
    path.write_text(
        "\n".join(
            [
                f"# Timestamp: {payload['timestamp']}",
                "",
                "# Codex Upper Ontology 1000 Seed Run",
                "",
                "## Summary",
                "",
                f"- generation_source: `{payload['generation_source']}`",
                f"- execution_mode: `{payload['execution_mode']}`",
                f"- target_count: `{payload['target_count']}`",
                f"- retained candidates: `{len(payload['candidate_records'])}`",
                f"- core_upper ratio: `{summary['observed_ratio']['core_upper']}`",
                f"- general_reference ratio: `{summary['observed_ratio']['general_reference']}`",
                "",
                "## Files",
                "",
                "- `final_result.json`: protocol-compatible object with candidate_records and promotion_records",
                "- `phase_g_candidate_records.json`: candidate_record array only",
                "- `phase_g_promotion_records.json`: promotion_record array only",
                "- `codex_upper_ontology_1000.csv`: human-review CSV",
                "- `run_summary.json`: balance and ratio summary",
                "",
                "## Notes",
                "",
                "- This is an upper-ontology-only run, so business_archetype target is intentionally 0.0.",
                "- The shape follows the existing step_01 candidate_record and promotion_record contracts.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_upper_ontology_run(output_dir: Path, timestamp: str | None = None) -> Path:
    payload = build_upper_ontology_seed(timestamp=timestamp)
    compact_timestamp = payload["timestamp"].replace("-", "").replace(":", "").replace(" ", "_")
    run_dir = output_dir / f"run_{compact_timestamp}_codex_upper_ontology_1000"
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_json(run_dir / "final_result.json", payload)
    _write_json(run_dir / "phase_g_candidate_records.json", payload["candidate_records"])
    _write_json(run_dir / "phase_g_promotion_records.json", payload["promotion_records"])
    _write_json(run_dir / "run_summary.json", payload["run_summary"])
    _write_candidate_csv(run_dir / "codex_upper_ontology_1000.csv", payload)
    _write_readme(run_dir / "README.md", payload)
    return run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Codex-authored 1000-item upper ontology seed run.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/exports/ontology_term_runs"),
    )
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = write_upper_ontology_run(
        output_dir=args.output_dir.expanduser().resolve(),
        timestamp=args.timestamp,
    )
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
