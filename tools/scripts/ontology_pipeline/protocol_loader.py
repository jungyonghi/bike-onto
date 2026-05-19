# Timestamp: 2026-04-20 18:24:07

from __future__ import annotations

import re
from pathlib import Path

from .schemas import PhaseDocument, ProtocolBundle


OVERVIEW_FILENAME = "step_01_llm_sealed_business_archetype_ontology_protocol.md"
PHASE_FILE_MAP = {
    "phase_a": "step_01a_phase_a_candidate_extraction.md",
    "phase_b": "step_01b_phase_b_normalization.md",
    "phase_c": "step_01c_phase_c_type_classification.md",
    "phase_d": "step_01d_phase_d_generalization_assessment.md",
    "phase_e": "step_01e_phase_e_ontology_fitness_evaluation.md",
    "phase_f": "step_01f_phase_f_merge_duplicate_handling.md",
    "phase_g": "step_01g_phase_g_sealed_promotion.md",
}


def extract_markdown_section(raw_text: str, heading: str) -> str:
    escaped_heading = re.escape(heading.strip())
    pattern = re.compile(
        rf"^#+\s+{escaped_heading}\s*$\n(.*?)(?=^#+\s+.+$|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(raw_text)
    return match.group(1).strip() if match else ""


def extract_first_fenced_block(raw_text: str) -> str:
    match = re.search(r"```(?:text|json)?\n(.*?)```", raw_text, re.DOTALL)
    return match.group(1).strip() if match else raw_text.strip()


def load_protocol_bundle(steps_dir: Path) -> ProtocolBundle:
    overview_path = steps_dir / OVERVIEW_FILENAME
    if not overview_path.exists():
        raise FileNotFoundError(overview_path)

    overview_text = overview_path.read_text(encoding="utf-8")
    system_prompt = extract_first_fenced_block(extract_markdown_section(overview_text, "System Prompt"))

    phase_docs: dict[str, PhaseDocument] = {}
    for phase_key, filename in PHASE_FILE_MAP.items():
        path = steps_dir / filename
        if not path.exists():
            raise FileNotFoundError(path)
        raw_text = path.read_text(encoding="utf-8")
        phase_docs[phase_key] = PhaseDocument(
            phase_key=phase_key,
            path=path,
            raw_text=raw_text,
            prompt_template=extract_first_fenced_block(extract_markdown_section(raw_text, "Prompt Template")),
        )

    return ProtocolBundle(
        overview_path=overview_path,
        overview_text=overview_text,
        system_prompt=system_prompt,
        phase_docs=phase_docs,
    )
