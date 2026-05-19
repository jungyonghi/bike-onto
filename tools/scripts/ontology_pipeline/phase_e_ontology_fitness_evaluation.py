# Timestamp: 2026-04-20 20:12:00
# Timestamp: 2026-04-20 20:55:00

from __future__ import annotations

import json
from dataclasses import replace

from .runtime_llama import generate
from .schemas import CandidateRecord, PhaseContext
from .validators import coerce_candidate_records, parse_json_payload

BATCH_SIZE = 30


def _build_prompt(template: str, candidates: list[CandidateRecord]) -> str:
    payload = {
        "instruction": template,
        "output_contract": "Return JSON only. Use {'items': candidate_record[]} as top-level object.",
        "candidates": [candidate.to_dict() for candidate in candidates],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def run_phase_e(context: PhaseContext, candidates: list[CandidateRecord]) -> list[CandidateRecord]:
    phase_doc = context.protocol_bundle.phase_docs["phase_e"]
    scored_records: list[CandidateRecord] = []
    for index in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[index : index + BATCH_SIZE]
        response = generate(
            prompt=_build_prompt(phase_doc.prompt_template, batch),
            system_prompt=context.protocol_bundle.system_prompt,
            host=context.host,
            port=context.port,
            max_tokens=4096,
        )
        parsed = parse_json_payload(response, required_top_level="items")
        scored_records.extend(coerce_candidate_records(parsed))
    return [
        replace(
            candidate,
            business_relevance=scored.business_relevance,
            general_reusability=scored.general_reusability,
            cross_domain_applicability=scored.cross_domain_applicability,
            relational_centrality=scored.relational_centrality,
            abstraction_fitness=scored.abstraction_fitness,
            ontological_clarity=scored.ontological_clarity,
            composability=scored.composability,
            compression_survival_likelihood=scored.compression_survival_likelihood,
            notes=scored.notes,
            antonyms=scored.antonyms,
        )
        for candidate, scored in zip(candidates, scored_records, strict=True)
    ]
