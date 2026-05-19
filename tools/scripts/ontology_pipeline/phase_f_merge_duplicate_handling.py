# Timestamp: 2026-04-20 18:24:07

from __future__ import annotations

from collections import defaultdict

from .schemas import CandidateRecord, MergeRecord, PhaseContext


def cluster_candidates_for_merge(candidates: list[CandidateRecord]) -> list[list[CandidateRecord]]:
    grouped: dict[str, list[CandidateRecord]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.normalized_form].append(candidate)
    return [group for _, group in sorted(grouped.items(), key=lambda item: item[0])]


def run_phase_f(context: PhaseContext, candidates: list[CandidateRecord]) -> list[MergeRecord]:
    del context
    merge_records: list[MergeRecord] = []
    for cluster in cluster_candidates_for_merge(candidates):
        if len(cluster) == 1:
            continue
        merge_records.append(
            MergeRecord(
                canonical_candidate=cluster[0].canonical_candidate,
                duplicate_group=[item.surface_form for item in cluster],
                relation_among_candidates="duplicate",
                merge_recommendation="merge",
                notes="same normalized form",
            )
        )
    return merge_records
