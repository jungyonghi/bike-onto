# Timestamp: 2026-04-20 20:05:00

from __future__ import annotations

import re
from dataclasses import replace

from .schemas import CandidateRecord, PhaseContext


def normalize_text(value: str) -> str:
    normalized = value.strip().lower().replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized.endswith("ies") and len(normalized) > 4:
        normalized = normalized[:-3] + "y"
    elif normalized.endswith("ses") and len(normalized) > 4:
        normalized = normalized[:-2]
    elif normalized.endswith("s") and not normalized.endswith("ss") and len(normalized) > 3:
        normalized = normalized[:-1]
    return normalized.strip()


def normalize_candidates(candidates: list[CandidateRecord]) -> list[CandidateRecord]:
    deduped: dict[str, CandidateRecord] = {}
    for candidate in candidates:
        normalized_form = normalize_text(candidate.normalized_form or candidate.surface_form)
        canonical_candidate = normalize_text(candidate.canonical_candidate or normalized_form)
        notes = candidate.notes
        if normalized_form in deduped:
            existing = deduped[normalized_form]
            alias_note = f"aliases: {candidate.surface_form}"
            merged_notes = " | ".join(part for part in [existing.notes, alias_note] if part)
            deduped[normalized_form] = replace(
                existing,
                normalized_form=normalized_form,
                business_relevance=max(existing.business_relevance, candidate.business_relevance),
                general_reusability=max(existing.general_reusability, candidate.general_reusability),
                cross_domain_applicability=max(existing.cross_domain_applicability, candidate.cross_domain_applicability),
                relational_centrality=max(existing.relational_centrality, candidate.relational_centrality),
                abstraction_fitness=max(existing.abstraction_fitness, candidate.abstraction_fitness),
                ontological_clarity=max(existing.ontological_clarity, candidate.ontological_clarity),
                composability=max(existing.composability, candidate.composability),
                compression_survival_likelihood=max(
                    existing.compression_survival_likelihood,
                    candidate.compression_survival_likelihood,
                ),
                is_domain_specific=existing.is_domain_specific and candidate.is_domain_specific,
                generalizable=existing.generalizable or candidate.generalizable,
                suggested_generalization=existing.suggested_generalization or candidate.suggested_generalization,
                promotion_decision=existing.promotion_decision or candidate.promotion_decision,
                notes=merged_notes,
                antonyms=existing.antonyms or candidate.antonyms,
            )
            continue

        deduped[normalized_form] = replace(
            candidate,
            normalized_form=normalized_form,
            canonical_candidate=canonical_candidate,
            notes=notes,
        )

    return list(deduped.values())


def run_phase_b(context: PhaseContext, candidates: list[CandidateRecord]) -> list[CandidateRecord]:
    del context
    return normalize_candidates(candidates)
