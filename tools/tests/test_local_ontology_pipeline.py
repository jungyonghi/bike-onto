# Timestamp: 2026-04-20 18:24:07

# Timestamp: 2026-04-20 20:12:00
# Timestamp: 2026-04-20 20:52:00
# Timestamp: 2026-04-20 21:08:00
# Timestamp: 2026-04-20 21:22:00
# Timestamp: 2026-04-20 21:31:00
# Timestamp: 2026-04-20 21:34:00

import json
from pathlib import Path
import sys

import pytest


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from project_paths import DOCS_DIR, PROJECT_ROOT, TOOLS_SCRIPTS_DIR  # noqa: E402

from ontology_pipeline.chunking import chunk_markdown_by_heading  # noqa: E402
from ontology_pipeline.config import (  # noqa: E402
    DEFAULT_CTX_SIZE,
    DEFAULT_LLAMA_SERVER_BIN,
    DEFAULT_LLAMA_SERVER_LIB_DIR,
    DEFAULT_MODEL_PATH,
    LlamaServerConfig,
    build_server_command,
)
from ontology_pipeline.io_utils import persist_phase_outputs  # noqa: E402
import ontology_pipeline.phase_a_candidate_extraction as phase_a_module  # noqa: E402
import ontology_pipeline.phase_c_type_classification as phase_c_module  # noqa: E402
import ontology_pipeline.phase_d_generalization_assessment as phase_d_module  # noqa: E402
import ontology_pipeline.phase_e_ontology_fitness_evaluation as phase_e_module  # noqa: E402
import ontology_pipeline.phase_g_sealed_promotion as phase_g_module  # noqa: E402
from ontology_pipeline.phase_a_candidate_extraction import run_phase_a, run_phase_a_with_artifacts  # noqa: E402
from ontology_pipeline.phase_b_normalization import normalize_candidates  # noqa: E402
from ontology_pipeline.phase_f_merge_duplicate_handling import cluster_candidates_for_merge  # noqa: E402
from ontology_pipeline.phase_c_type_classification import run_phase_c  # noqa: E402
from ontology_pipeline.phase_d_generalization_assessment import run_phase_d  # noqa: E402
from ontology_pipeline.phase_e_ontology_fitness_evaluation import run_phase_e  # noqa: E402
from ontology_pipeline.phase_g_sealed_promotion import build_run_summary, run_phase_g  # noqa: E402
from ontology_pipeline.protocol_loader import load_protocol_bundle  # noqa: E402
from ontology_pipeline.schemas import CandidateRecord, MergeRecord, PhaseContext, PromotionRecord, RawCandidateRecord  # noqa: E402
from ontology_pipeline.validators import parse_json_payload  # noqa: E402


STEPS_DIR = DOCS_DIR / "steps"


def _make_candidate(
    surface_form: str,
    normalized_form: str | None = None,
    canonical_candidate: str | None = None,
    promotion_decision: str = "",
    notes: str = "",
    candidate_type: str = "class_candidate",
    antonyms: list[str] | None = None,
) -> CandidateRecord:
    normalized = normalized_form or surface_form.lower()
    canonical = canonical_candidate or normalized
    return CandidateRecord(
        surface_form=surface_form,
        normalized_form=normalized,
        canonical_candidate=canonical,
        candidate_type=candidate_type,
        business_relevance=3,
        general_reusability=3,
        cross_domain_applicability=3,
        relational_centrality=3,
        abstraction_fitness=3,
        ontological_clarity=3,
        composability=3,
        compression_survival_likelihood=3,
        is_domain_specific=False,
        generalizable=False,
        suggested_generalization="",
        promotion_decision=promotion_decision,
        notes=notes,
        antonyms=antonyms or [],
    )


def _write_protocol_steps(root: Path) -> None:
    (root / "step_01_llm_sealed_business_archetype_ontology_protocol.md").write_text(
        "\n".join(
            [
                "# Timestamp: 2026-04-20 20:05:00",
                "",
                "# Protocol",
                "",
                "## System Prompt",
                "```text",
                "system role",
                "```",
                "",
                "## Template 1",
                "phase a",
            ]
        ),
        encoding="utf-8",
    )
    contents = {
        "step_01a_phase_a_candidate_extraction.md": "generate concept candidates",
        "step_01b_phase_b_normalization.md": "normalize candidates",
        "step_01c_phase_c_type_classification.md": "classify candidates",
        "step_01d_phase_d_generalization_assessment.md": "generalize candidates",
        "step_01e_phase_e_ontology_fitness_evaluation.md": "score candidates",
        "step_01f_phase_f_merge_duplicate_handling.md": "merge candidates",
        "step_01g_phase_g_sealed_promotion.md": "promote candidates",
    }
    for filename, prompt_body in contents.items():
        (root / filename).write_text(
            "\n".join(
                [
                    "# Timestamp: 2026-04-20 20:05:00",
                    "",
                    "# Prompt Template",
                    "```text",
                    prompt_body,
                    "```",
                ]
            ),
            encoding="utf-8",
        )


def _make_raw_candidate(
    raw_term: str,
    generation_stratum: str = "business",
    general_category: str = "",
    source_field: str = "name",
    description: str = "",
    notes: str = "",
) -> RawCandidateRecord:
    return RawCandidateRecord(
        raw_term=raw_term,
        source_field=source_field,
        generation_stratum=generation_stratum,
        general_category=general_category,
        description=description,
        notes=notes,
        raw_payload_json=json.dumps({"name": raw_term}, ensure_ascii=False),
    )


def test_protocol_loader_reads_overview_and_phase_templates():
    bundle = load_protocol_bundle(STEPS_DIR)

    assert "LLM Sealed Business Archetype Ontology Distillation Protocol" in bundle.overview_text
    assert "Template 1" in bundle.overview_text
    assert "phase_a" in bundle.phase_docs
    assert "phase_g" in bundle.phase_docs
    assert "Prompt Template" in bundle.phase_docs["phase_a"].raw_text
    assert "Prompt Template" in bundle.phase_docs["phase_g"].raw_text


def test_protocol_loader_fails_when_required_phase_doc_is_missing(tmp_path):
    root = tmp_path / "steps"
    root.mkdir()
    (root / "step_01_llm_sealed_business_archetype_ontology_protocol.md").write_text(
        "# Timestamp: 2026-04-20 18:24:07\n\n# Overview\n",
        encoding="utf-8",
    )

    try:
        load_protocol_bundle(root)
    except FileNotFoundError as exc:
        assert "step_01a_phase_a_candidate_extraction.md" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError for missing phase docs")


def test_server_command_contains_required_gpu_and_ram_flags():
    config = LlamaServerConfig(
        llama_server_bin=DEFAULT_LLAMA_SERVER_BIN,
        llama_server_lib_dir=DEFAULT_LLAMA_SERVER_LIB_DIR,
        model_path=DEFAULT_MODEL_PATH,
        host="127.0.0.1",
        port=18080,
        ctx_size=DEFAULT_CTX_SIZE,
        parallel=1,
        ngl=999,
        no_kv_offload=True,
    )

    command = build_server_command(config)

    assert str(DEFAULT_MODEL_PATH) in command
    assert "-ngl" in command and "999" in command
    assert "-nkvo" in command
    assert "-c" in command and str(DEFAULT_CTX_SIZE) in command
    assert "--parallel" in command and "1" in command


def test_chunk_markdown_by_heading_preserves_heading_paths():
    text = """# Title

## Alpha
First paragraph.

### Alpha Child
Child paragraph.

## Beta
Second paragraph.
"""

    chunks = chunk_markdown_by_heading(text, max_chunk_chars=120)

    assert len(chunks) >= 3
    assert chunks[0].heading_path[0] == "Title"
    assert any(chunk.heading_path[-1] == "Alpha" for chunk in chunks)
    assert any(chunk.heading_path[-1] == "Alpha Child" for chunk in chunks)
    assert any(chunk.heading_path[-1] == "Beta" for chunk in chunks)


def test_normalize_candidates_lowercases_and_deduplicates():
    raw = [
        _make_candidate("Customers", normalized_form="Customers", canonical_candidate="Customers"),
        _make_candidate("customer", normalized_form="customer", canonical_candidate="customer"),
        _make_candidate("Service-Point", normalized_form="Service-Point", canonical_candidate="Service-Point"),
    ]

    normalized = normalize_candidates(raw)

    assert len(normalized) == 2
    assert any(item.normalized_form == "customer" for item in normalized)
    assert any(item.normalized_form == "service point" for item in normalized)


def test_cluster_candidates_for_merge_groups_only_same_normalized_form():
    candidates = [
        _make_candidate("customer"),
        _make_candidate("Customer"),
        _make_candidate("client"),
    ]

    clusters = cluster_candidates_for_merge(candidates)

    assert len(clusters) == 2
    assert any(len(cluster) == 2 for cluster in clusters)
    assert any(cluster[0].normalized_form == "client" for cluster in clusters if len(cluster) == 1)


def test_parse_json_payload_requires_fields_and_repairs_wrapped_payload():
    payload = """
    Here is the result:
    {
      "items": [
        {
          "surface_form": "customer",
          "normalized_form": "customer",
          "canonical_candidate": "customer",
          "candidate_type": "class_candidate",
          "business_relevance": 5,
          "general_reusability": 5,
          "cross_domain_applicability": 5,
          "relational_centrality": 5,
          "abstraction_fitness": 5,
          "ontological_clarity": 5,
          "composability": 5,
          "compression_survival_likelihood": 5,
          "is_domain_specific": false,
          "generalizable": false,
          "suggested_generalization": "",
          "promotion_decision": "business_archetype",
          "notes": ""
        }
      ]
    }
    """

    parsed = parse_json_payload(payload, required_top_level="items")

    assert "items" in parsed
    assert parsed["items"][0]["surface_form"] == "customer"


def test_candidate_record_round_trip_preserves_antonyms_array():
    record = _make_candidate("customer", antonyms=["provider", "supplier"])

    payload = record.to_dict()
    round_tripped = CandidateRecord.from_dict(payload)

    assert payload["antonyms"] == ["provider", "supplier"]
    assert round_tripped.antonyms == ["provider", "supplier"]


# Timestamp: 2026-04-20 20:36:00
def test_build_default_server_config_accepts_registered_model_alias():
    import ontology_pipeline.config as config_module

    server_config = config_module.build_default_server_config(
        model_alias="opus47_godsghost_codex_4b_q4_k_m"
    )

    assert server_config.model_path == Path(
        "/home/user/Documents/11_Models/Opus4.7-GODsGhost-Codex-4B-Q4_K_M.gguf"
    )


def test_main_restarts_llama_server_between_llm_phases(monkeypatch, tmp_path):
    import run_local_ontology_pipeline as pipeline

    root = tmp_path / "steps"
    root.mkdir()
    _write_protocol_steps(root)

    started: list[str] = []
    stopped: list[str] = []
    persisted_payloads: list[dict[str, object]] = []

    monkeypatch.setattr(
        pipeline,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "protocol_root_dir": str(root),
                "output_dir": str(tmp_path / "out"),
                "ctx_size": 4096,
                "port": 18080,
                "phase_a_max_candidates": 4,
                "phase_a_raw_target": 4,
                "model_alias": None,
                "model_path": None,
            },
        )(),
    )
    monkeypatch.setattr(pipeline, "load_protocol_bundle", lambda _: load_protocol_bundle(root))
    monkeypatch.setattr(pipeline, "create_run_output_dir", lambda _: tmp_path / "run")
    monkeypatch.setattr(
        pipeline,
        "build_default_server_config",
        lambda **kwargs: LlamaServerConfig(
            llama_server_bin=DEFAULT_LLAMA_SERVER_BIN,
            llama_server_lib_dir=DEFAULT_LLAMA_SERVER_LIB_DIR,
            model_path=DEFAULT_MODEL_PATH,
            host="127.0.0.1",
            port=18080,
            ctx_size=4096,
            parallel=1,
            ngl=999,
            no_kv_offload=True,
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "start_server",
        lambda config: started.append(str(config.model_path)) or f"handle-{len(started)}",
    )
    monkeypatch.setattr(pipeline, "stop_server", lambda handle: stopped.append(str(handle)))
    monkeypatch.setattr(
        pipeline,
        "run_phase_a_with_artifacts",
        lambda context, progress_callback=None: (
            [_make_raw_candidate("raw customer")],
            [_make_candidate("customer")],
            [{"name": "raw customer"}],
        ),
    )
    monkeypatch.setattr(pipeline, "run_phase_b", lambda context, candidates: candidates)
    monkeypatch.setattr(
        pipeline,
        "run_phase_c",
        lambda context, candidates: [_make_candidate("customer", candidate_type="role_candidate")],
    )
    monkeypatch.setattr(
        pipeline,
        "run_phase_d",
        lambda context, candidates: [_make_candidate("customer", notes="generalized")],
    )
    monkeypatch.setattr(
        pipeline,
        "run_phase_e",
        lambda context, candidates: [_make_candidate("customer", notes="scored")],
    )
    monkeypatch.setattr(
        pipeline,
        "run_phase_f",
        lambda context, candidates: [
            MergeRecord(
                canonical_candidate="customer",
                duplicate_group=["customer"],
                relation_among_candidates="same",
                merge_recommendation="keep",
                notes="",
            )
        ],
    )
    monkeypatch.setattr(
        pipeline,
        "run_phase_g",
        lambda context, candidates: (
            [_make_candidate("customer", promotion_decision="business_archetype", antonyms=["provider"])],
            [
                PromotionRecord(
                    promotion_decision="business_archetype",
                    canonical_name="customer",
                    short_definition="customer",
                    rationale="core",
                    possible_parent_classes=[],
                    possible_related_classes=[],
                )
            ],
            build_run_summary(
                promoted_candidates=[_make_candidate("customer", promotion_decision="business_archetype")],
                review_count=0,
                rejected_count=0,
            ),
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "persist_phase_outputs",
        lambda output_dir, payload: persisted_payloads.append(payload) or {"ok": str(output_dir)},
    )

    result = pipeline.main()

    assert result == 0
    assert len(started) == 5
    assert len(stopped) == 5
    assert any("phase_a_candidates.json" in payload for payload in persisted_payloads)
    assert any("phase_g_promotion_records.json" in payload for payload in persisted_payloads)


def test_main_persists_true_raw_csv_and_phase_ordered_candidate_csvs(monkeypatch, tmp_path):
    import run_local_ontology_pipeline as pipeline

    root = tmp_path / "steps"
    root.mkdir()
    _write_protocol_steps(root)

    raw_csv_calls: list[tuple[Path, str, list[RawCandidateRecord]]] = []
    candidate_csv_calls: list[tuple[Path, str, list[CandidateRecord]]] = []

    monkeypatch.setattr(
        pipeline,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "protocol_root_dir": str(root),
                "output_dir": str(tmp_path / "out"),
                "ctx_size": 4096,
                "port": 18080,
                "phase_a_max_candidates": 2,
                "phase_a_raw_target": 2,
                "model_alias": None,
                "model_path": None,
            },
        )(),
    )
    monkeypatch.setattr(pipeline, "load_protocol_bundle", lambda _: load_protocol_bundle(root))
    monkeypatch.setattr(pipeline, "create_run_output_dir", lambda _: tmp_path / "run")
    monkeypatch.setattr(
        pipeline,
        "build_default_server_config",
        lambda **kwargs: LlamaServerConfig(
            llama_server_bin=DEFAULT_LLAMA_SERVER_BIN,
            llama_server_lib_dir=DEFAULT_LLAMA_SERVER_LIB_DIR,
            model_path=DEFAULT_MODEL_PATH,
            host="127.0.0.1",
            port=18080,
            ctx_size=4096,
            parallel=1,
            ngl=999,
            no_kv_offload=True,
        ),
    )
    monkeypatch.setattr(pipeline, "start_server", lambda config: "handle")
    monkeypatch.setattr(pipeline, "stop_server", lambda handle: None)
    monkeypatch.setattr(
        pipeline,
        "persist_phase_outputs",
        lambda output_dir, payload: {"ok": str(output_dir / next(iter(payload)))},
    )
    monkeypatch.setattr(
        pipeline,
        "persist_raw_candidate_records_csv",
        lambda output_dir, filename, records: raw_csv_calls.append((output_dir, filename, records))
        or str(output_dir / filename),
        raising=False,
    )
    monkeypatch.setattr(
        pipeline,
        "persist_candidate_records_csv",
        lambda output_dir, filename, records: candidate_csv_calls.append((output_dir, filename, records))
        or str(output_dir / filename),
        raising=False,
    )
    monkeypatch.setattr(
        pipeline,
        "run_phase_a_with_artifacts",
        lambda context, progress_callback=None: (
            [_make_raw_candidate("raw customer", notes="llm raw")],
            [_make_candidate("customer")],
            [{"name": "raw customer", "notes": "llm raw"}],
        ),
    )
    monkeypatch.setattr(pipeline, "run_phase_b", lambda context, candidates: candidates)
    monkeypatch.setattr(pipeline, "run_phase_c", lambda context, candidates: candidates)
    monkeypatch.setattr(pipeline, "run_phase_d", lambda context, candidates: candidates)
    monkeypatch.setattr(pipeline, "run_phase_e", lambda context, candidates: candidates)
    monkeypatch.setattr(pipeline, "run_phase_f", lambda context, candidates: [])
    monkeypatch.setattr(
        pipeline,
        "run_phase_g",
        lambda context, candidates: (
            [_make_candidate("customer", promotion_decision="business_archetype")],
            [],
            build_run_summary(
                promoted_candidates=[_make_candidate("customer", promotion_decision="business_archetype")],
                review_count=0,
                rejected_count=0,
            ),
        ),
    )

    pipeline.main()

    assert len(raw_csv_calls) == 1
    assert raw_csv_calls[0][1] == "raw.csv"
    assert raw_csv_calls[0][2][0].raw_term == "raw customer"
    assert [call[1] for call in candidate_csv_calls] == [
        "phase_a_candidates.csv",
        "phase_b_normalized_candidates.csv",
        "phase_c_typed_candidates.csv",
        "phase_d_generalized_candidates.csv",
        "phase_e_scored_candidates.csv",
    ]
    assert candidate_csv_calls[0][2][0].surface_form == "customer"


def test_main_reports_progress_to_stderr(monkeypatch, tmp_path, capsys):
    import run_local_ontology_pipeline as pipeline

    root = tmp_path / "steps"
    root.mkdir()
    _write_protocol_steps(root)

    monkeypatch.setattr(
        pipeline,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "protocol_root_dir": str(root),
                "output_dir": str(tmp_path / "out"),
                "ctx_size": 4096,
                "port": 18080,
                "phase_a_max_candidates": 2,
                "phase_a_raw_target": 5,
                "model_alias": None,
                "model_path": None,
            },
        )(),
    )
    monkeypatch.setattr(pipeline, "load_protocol_bundle", lambda _: load_protocol_bundle(root))
    monkeypatch.setattr(pipeline, "create_run_output_dir", lambda _: tmp_path / "run")
    monkeypatch.setattr(
        pipeline,
        "build_default_server_config",
        lambda **kwargs: LlamaServerConfig(
            llama_server_bin=DEFAULT_LLAMA_SERVER_BIN,
            llama_server_lib_dir=DEFAULT_LLAMA_SERVER_LIB_DIR,
            model_path=DEFAULT_MODEL_PATH,
            host="127.0.0.1",
            port=18080,
            ctx_size=4096,
            parallel=1,
            ngl=999,
            no_kv_offload=True,
        ),
    )
    monkeypatch.setattr(pipeline, "start_server", lambda config: "handle")
    monkeypatch.setattr(pipeline, "stop_server", lambda handle: None)
    monkeypatch.setattr(pipeline, "persist_phase_outputs", lambda output_dir, payload: {})
    monkeypatch.setattr(pipeline, "persist_raw_candidate_records_csv", lambda *args, **kwargs: "raw.csv")
    monkeypatch.setattr(pipeline, "persist_candidate_records_csv", lambda *args, **kwargs: "phase.csv")

    def fake_phase_a(context, progress_callback):
        progress_callback(
            {
                "phase": "phase_a",
                "event": "batch_completed",
                "batch_index": 1,
                "batch_total": 3,
                "raw_count": 2,
                "raw_target": 5,
                "candidate_count": 2,
                "candidate_target": 2,
                "generation_stratum": "business",
                "general_category": "",
            }
        )
        return (
            [_make_raw_candidate("raw customer"), _make_raw_candidate("raw org", generation_stratum="non_business")],
            [_make_candidate("customer"), _make_candidate("organization")],
            [{"name": "raw customer"}, {"name": "raw org"}],
        )

    monkeypatch.setattr(pipeline, "run_phase_a_with_artifacts", fake_phase_a)
    monkeypatch.setattr(pipeline, "run_phase_b", lambda context, candidates: candidates)
    monkeypatch.setattr(pipeline, "run_phase_c", lambda context, candidates: candidates)
    monkeypatch.setattr(pipeline, "run_phase_d", lambda context, candidates: candidates)
    monkeypatch.setattr(pipeline, "run_phase_e", lambda context, candidates: candidates)
    monkeypatch.setattr(pipeline, "run_phase_f", lambda context, candidates: [])
    monkeypatch.setattr(
        pipeline,
        "run_phase_g",
        lambda context, candidates: (
            candidates,
            [],
            build_run_summary(promoted_candidates=candidates, review_count=0, rejected_count=0),
        ),
    )

    pipeline.main()
    captured = capsys.readouterr()

    assert "phase_a:start" in captured.err
    assert "phase_a:batch 1/3 raw=2/5 candidates=2/2" in captured.err
    assert "phase_g:done" in captured.err


def test_llm_phase_batch_sizes_are_capped_at_30():
    plan = phase_a_module._build_generation_plan(100)

    assert phase_a_module.PHASE_A_BATCH_SIZE == 30
    assert max(request.target_count for request in plan) == 30
    assert phase_c_module.BATCH_SIZE == 30
    assert phase_d_module.BATCH_SIZE == 30
    assert phase_e_module.BATCH_SIZE == 30
    assert phase_g_module.BATCH_SIZE == 30


def test_run_phase_a_generates_candidates_without_text_input(monkeypatch, tmp_path):
    root = tmp_path / "steps"
    root.mkdir()
    _write_protocol_steps(root)
    prompts: list[dict[str, object]] = []

    def fake_generate(*, prompt: str, **kwargs: object) -> str:
        payload = json.loads(prompt)
        prompts.append(payload)
        target_count = int(payload["target_count"])
        prefix = str(payload["generation_stratum"])
        items = [
            {
                "surface_form": f"{prefix} candidate {index}",
                "normalized_form": f"{prefix} candidate {index}",
                "canonical_candidate": f"{prefix} candidate {index}",
                "candidate_type": "class_candidate",
                "business_relevance": 4 if prefix == "business" else 2,
                "general_reusability": 4,
                "cross_domain_applicability": 4,
                "relational_centrality": 3,
                "abstraction_fitness": 3,
                "ontological_clarity": 3,
                "composability": 3,
                "compression_survival_likelihood": 3,
                "is_domain_specific": prefix == "business",
                "generalizable": prefix != "business",
                "suggested_generalization": "",
                "promotion_decision": "",
                "notes": prefix,
            }
            for index in range(target_count)
        ]
        return json.dumps({"items": items}, ensure_ascii=False)

    monkeypatch.setattr("ontology_pipeline.phase_a_candidate_extraction.generate", fake_generate)

    context = PhaseContext(
        protocol_root_dir=root,
        run_output_dir=tmp_path / "run",
        protocol_bundle=load_protocol_bundle(root),
        host="127.0.0.1",
        port=18080,
        phase_a_max_candidates=12,
        phase_a_raw_target=12,
    )

    records = run_phase_a(context)

    assert len(records) == 12
    assert all(item.antonyms == [] for item in records)
    assert {payload["generation_stratum"] for payload in prompts} == {"business", "non_business"}
    assert all("text" not in payload for payload in prompts)
    assert any("general_category" in payload for payload in prompts if payload["generation_stratum"] == "non_business")


def test_run_phase_a_with_artifacts_collects_true_raw_items_before_coercion(monkeypatch, tmp_path):
    root = tmp_path / "steps"
    root.mkdir()
    _write_protocol_steps(root)

    def fake_generate(*, prompt: str, **kwargs: object) -> str:
        payload = json.loads(prompt)
        prefix = str(payload["generation_stratum"])
        target_count = int(payload["target_count"])
        items = [
            {
                "id": f"{prefix}_{index}",
                "name": f"{prefix} raw term {index}",
                "description": f"{prefix} raw description {index}",
                "stratum": prefix,
                "notes": "minimal-shape",
            }
            for index in range(target_count)
        ]
        return json.dumps({"items": items}, ensure_ascii=False)

    monkeypatch.setattr("ontology_pipeline.phase_a_candidate_extraction.generate", fake_generate)

    context = PhaseContext(
        protocol_root_dir=root,
        run_output_dir=tmp_path / "run",
        protocol_bundle=load_protocol_bundle(root),
        host="127.0.0.1",
        port=18080,
        phase_a_max_candidates=4,
        phase_a_raw_target=4,
    )

    raw_records, candidate_records, raw_items = run_phase_a_with_artifacts(context)

    assert len(raw_records) == 4
    assert len(candidate_records) == 4
    assert len(raw_items) == 4
    assert raw_records[0].raw_term == "business raw term 0"
    assert raw_records[0].source_field == "name"
    assert candidate_records[0].surface_form == "business raw term 0"
    assert candidate_records[0].normalized_form == "business raw term 0"


def test_run_phase_a_with_artifacts_loops_until_raw_target_even_when_candidate_target_is_smaller(
    monkeypatch,
    tmp_path,
):
    root = tmp_path / "steps"
    root.mkdir()
    _write_protocol_steps(root)

    def fake_generate(*, prompt: str, **kwargs: object) -> str:
        payload = json.loads(prompt)
        prefix = str(payload["generation_stratum"])
        target_count = int(payload["target_count"])
        items = [
            {
                "id": f"{prefix}_{index}",
                "name": f"{prefix} raw term {index}",
                "description": f"{prefix} raw description {index}",
                "stratum": prefix,
                "notes": "minimal-shape",
            }
            for index in range(target_count)
        ]
        return json.dumps({"items": items}, ensure_ascii=False)

    monkeypatch.setattr("ontology_pipeline.phase_a_candidate_extraction.generate", fake_generate)

    context = PhaseContext(
        protocol_root_dir=root,
        run_output_dir=tmp_path / "run",
        protocol_bundle=load_protocol_bundle(root),
        host="127.0.0.1",
        port=18080,
        phase_a_max_candidates=2,
        phase_a_raw_target=5,
    )

    raw_records, candidate_records, raw_items = run_phase_a_with_artifacts(context)

    assert len(raw_records) == 5
    assert len(raw_items) == 5
    assert len(candidate_records) == 2


def test_run_phase_a_with_artifacts_emits_progress_events(monkeypatch, tmp_path):
    root = tmp_path / "steps"
    root.mkdir()
    _write_protocol_steps(root)
    events: list[dict[str, object]] = []

    def fake_generate(*, prompt: str, **kwargs: object) -> str:
        payload = json.loads(prompt)
        prefix = str(payload["generation_stratum"])
        target_count = int(payload["target_count"])
        items = [
            {
                "id": f"{prefix}_{index}",
                "name": f"{prefix} raw term {index}",
                "description": f"{prefix} raw description {index}",
                "stratum": prefix,
                "notes": "minimal-shape",
            }
            for index in range(target_count)
        ]
        return json.dumps({"items": items}, ensure_ascii=False)

    monkeypatch.setattr("ontology_pipeline.phase_a_candidate_extraction.generate", fake_generate)

    context = PhaseContext(
        protocol_root_dir=root,
        run_output_dir=tmp_path / "run",
        protocol_bundle=load_protocol_bundle(root),
        host="127.0.0.1",
        port=18080,
        phase_a_max_candidates=2,
        phase_a_raw_target=5,
    )

    run_phase_a_with_artifacts(context, progress_callback=events.append)

    assert events
    assert events[-1]["raw_count"] == 5
    assert events[-1]["candidate_count"] == 2
    assert events[-1]["batch_total"] == 4


def test_run_phase_a_accepts_minimal_llm_candidate_shape(monkeypatch, tmp_path):
    root = tmp_path / "steps"
    root.mkdir()
    _write_protocol_steps(root)

    def fake_generate(*, prompt: str, **kwargs: object) -> str:
        payload = json.loads(prompt)
        prefix = str(payload["generation_stratum"])
        target_count = int(payload["target_count"])
        items = [
            {
                "id": f"{prefix}_{index}",
                "name": f"{prefix} concept {index}",
                "description": f"{prefix} concept description {index}",
                "stratum": prefix,
                "notes": "model-minimal-shape",
            }
            for index in range(target_count)
        ]
        return json.dumps({"items": items}, ensure_ascii=False)

    monkeypatch.setattr("ontology_pipeline.phase_a_candidate_extraction.generate", fake_generate)

    context = PhaseContext(
        protocol_root_dir=root,
        run_output_dir=tmp_path / "run",
        protocol_bundle=load_protocol_bundle(root),
        host="127.0.0.1",
        port=18080,
        phase_a_max_candidates=4,
        phase_a_raw_target=4,
    )

    records = run_phase_a(context)

    assert len(records) == 4
    assert records[0].surface_form
    assert records[0].canonical_candidate
    assert records[0].candidate_type == "class_candidate"
    assert "model-minimal-shape" in records[0].notes


def test_run_phase_a_raises_when_llm_generation_fails(monkeypatch, tmp_path):
    root = tmp_path / "steps"
    root.mkdir()
    _write_protocol_steps(root)

    monkeypatch.setattr(
        "ontology_pipeline.phase_a_candidate_extraction.generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("llm down")),
    )

    context = PhaseContext(
        protocol_root_dir=root,
        run_output_dir=tmp_path / "run",
        protocol_bundle=load_protocol_bundle(root),
        host="127.0.0.1",
        port=18080,
        phase_a_max_candidates=8,
        phase_a_raw_target=8,
    )

    with pytest.raises(RuntimeError, match="llm down"):
        run_phase_a(context)


def test_run_local_pipeline_no_longer_requires_input_path_arg():
    script_path = TOOLS_SCRIPTS_DIR / "run_local_ontology_pipeline.py"
    source = script_path.read_text(encoding="utf-8")

    assert "--input-path" not in source
    assert "--max-chunk-chars" not in source


def test_build_run_summary_tracks_target_ratio_and_category_balance():
    promoted = [
        _make_candidate("customer", promotion_decision="business_archetype"),
        _make_candidate("service point", promotion_decision="business_archetype"),
        _make_candidate("time interval", promotion_decision="general_reference"),
        _make_candidate("actor", promotion_decision="core_upper"),
    ]

    summary = build_run_summary(
        promoted_candidates=promoted,
        review_count=1,
        rejected_count=2,
    )

    assert summary.target_ratio["business_archetype"] == 0.7
    assert summary.review_count == 1
    assert summary.rejected_count == 2
    assert "actor/person" in summary.general_category_balance
    assert summary.observed_ratio["business_archetype"] == 0.5


def test_phase_c_d_e_raise_when_llm_fails(monkeypatch, tmp_path):
    root = tmp_path / "steps"
    root.mkdir()
    _write_protocol_steps(root)
    context = PhaseContext(
        protocol_root_dir=root,
        run_output_dir=tmp_path / "run",
        protocol_bundle=load_protocol_bundle(root),
        host="127.0.0.1",
        port=18080,
        phase_a_max_candidates=8,
        phase_a_raw_target=8,
    )
    candidates = [_make_candidate("customer")]

    monkeypatch.setattr(
        "ontology_pipeline.phase_c_type_classification.generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("phase c failed")),
    )
    with pytest.raises(RuntimeError, match="phase c failed"):
        run_phase_c(context, candidates)

    monkeypatch.setattr(
        "ontology_pipeline.phase_d_generalization_assessment.generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("phase d failed")),
    )
    with pytest.raises(RuntimeError, match="phase d failed"):
        run_phase_d(context, candidates)

    monkeypatch.setattr(
        "ontology_pipeline.phase_e_ontology_fitness_evaluation.generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("phase e failed")),
    )
    with pytest.raises(RuntimeError, match="phase e failed"):
        run_phase_e(context, candidates)


def test_run_phase_g_populates_antonyms_only_for_retained_candidates(monkeypatch, tmp_path):
    root = tmp_path / "steps"
    root.mkdir()
    _write_protocol_steps(root)
    context = PhaseContext(
        protocol_root_dir=root,
        run_output_dir=tmp_path / "run",
        protocol_bundle=load_protocol_bundle(root),
        host="127.0.0.1",
        port=18080,
        phase_a_max_candidates=8,
        phase_a_raw_target=8,
    )
    candidates = [
        _make_candidate("customer"),
        _make_candidate("status", candidate_type="noise"),
    ]

    def fake_generate(*, prompt: str, **kwargs: object) -> str:
        payload = json.loads(prompt)
        assert "candidates" in payload
        return json.dumps(
            {
                "candidate_records": [
                    {
                        **payload["candidates"][0],
                        "promotion_decision": "business_archetype",
                        "antonyms": ["provider", "supplier"],
                    },
                    {
                        **payload["candidates"][1],
                        "promotion_decision": "reject",
                        "antonyms": [],
                    },
                ],
                "promotion_records": [
                    {
                        "promotion_decision": "business_archetype",
                        "canonical_name": "customer",
                        "short_definition": "commercial actor",
                        "rationale": "central business actor",
                        "possible_parent_classes": ["actor"],
                        "possible_related_classes": ["subscriber"],
                    },
                    {
                        "promotion_decision": "reject",
                        "canonical_name": "status",
                        "short_definition": "status",
                        "rationale": "noise",
                        "possible_parent_classes": [],
                        "possible_related_classes": [],
                    },
                ],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("ontology_pipeline.phase_g_sealed_promotion.generate", fake_generate)

    promoted, promotion_records, summary = run_phase_g(context, candidates)

    assert promoted[0].antonyms == ["provider", "supplier"]
    assert promoted[1].antonyms == []
    assert promotion_records[0].promotion_decision == "business_archetype"
    assert summary.rejected_count == 1


def test_persist_phase_outputs_writes_all_expected_json_files(tmp_path):
    phase_outputs = {
        "phase_a_candidates.json": [
            _make_candidate("customer").to_dict(),
        ],
        "phase_f_merge_records.json": [
            MergeRecord(
                canonical_candidate="customer",
                duplicate_group=["customer", "Customer"],
                relation_among_candidates="duplicate",
                merge_recommendation="merge",
                notes="",
            ).to_dict()
        ],
        "phase_g_promotion_records.json": [
            PromotionRecord(
                promotion_decision="business_archetype",
                canonical_name="customer",
                short_definition="commercial actor",
                rationale="core business actor",
                possible_parent_classes=["actor"],
                possible_related_classes=["subscriber"],
            ).to_dict()
        ],
        "run_summary.json": build_run_summary(
            promoted_candidates=[_make_candidate("customer", promotion_decision="business_archetype")],
            review_count=0,
            rejected_count=0,
        ).to_dict(),
    }

    persisted = persist_phase_outputs(tmp_path, phase_outputs)

    for path in persisted.values():
        assert Path(path).exists()
        json.loads(Path(path).read_text(encoding="utf-8"))
