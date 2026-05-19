# Timestamp: 2026-04-20 20:36:00
# Timestamp: 2026-04-20 20:55:00
# Timestamp: 2026-04-20 21:10:00
# Timestamp: 2026-04-20 21:22:00
# Timestamp: 2026-04-20 21:34:00

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path
from typing import Callable, TypeVar


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ontology_pipeline.config import (  # noqa: E402
    DEFAULT_CTX_SIZE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PHASE_A_MAX_CANDIDATES,
    DEFAULT_PORT,
    DEFAULT_PROTOCOL_ROOT_DIR,
    build_default_server_config,
    list_registered_model_aliases,
)
from ontology_pipeline.io_utils import (  # noqa: E402
    create_run_output_dir,
    persist_candidate_records_csv,
    persist_raw_candidate_records_csv,
    persist_phase_outputs,
    to_serializable,
)
from ontology_pipeline.phase_a_candidate_extraction import run_phase_a_with_artifacts  # noqa: E402
from ontology_pipeline.phase_b_normalization import run_phase_b  # noqa: E402
from ontology_pipeline.phase_c_type_classification import run_phase_c  # noqa: E402
from ontology_pipeline.phase_d_generalization_assessment import run_phase_d  # noqa: E402
from ontology_pipeline.phase_e_ontology_fitness_evaluation import run_phase_e  # noqa: E402
from ontology_pipeline.phase_f_merge_duplicate_handling import run_phase_f  # noqa: E402
from ontology_pipeline.phase_g_sealed_promotion import run_phase_g  # noqa: E402
from ontology_pipeline.protocol_loader import load_protocol_bundle  # noqa: E402
from ontology_pipeline.runtime_llama import start_server, stop_server  # noqa: E402
from ontology_pipeline.schemas import LlamaServerConfig, PhaseContext  # noqa: E402


T = TypeVar("T")
LLM_PHASE_COOLDOWN_SECONDS = 1.0


def _registered_model_alias_help_text() -> str:
    aliases = ", ".join(list_registered_model_aliases())
    return f"Registered model alias. Available aliases: {aliases}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run corpus-free ontology distillation pipeline with phase-isolated llama-server restarts."
    )
    parser.add_argument(
        "--protocol-root-dir",
        default=str(DEFAULT_PROTOCOL_ROOT_DIR),
        help="Directory containing step_01 and step_01a~g documents.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where phase JSON artifacts will be written.",
    )
    parser.add_argument("--ctx-size", type=int, default=DEFAULT_CTX_SIZE)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--phase-a-max-candidates", type=int, default=DEFAULT_PHASE_A_MAX_CANDIDATES)
    parser.add_argument(
        "--phase-a-raw-target",
        type=int,
        help="True raw phase A harvest target. When omitted, defaults to --phase-a-max-candidates.",
    )
    parser.add_argument("--model-alias", help=_registered_model_alias_help_text())
    parser.add_argument(
        "--model-path",
        help="Absolute path to a GGUF file. Use instead of --model-alias for an unregistered model.",
    )
    args = parser.parse_args()
    if args.model_alias and args.model_path:
        parser.error("--model-alias and --model-path are mutually exclusive.")
    return args


def _release_phase_memory() -> None:
    gc.collect()
    time.sleep(LLM_PHASE_COOLDOWN_SECONDS)


def _run_with_fresh_llm_runtime(
    server_config: LlamaServerConfig,
    phase_label: str,
    callback: Callable[[], T],
) -> T:
    handle = start_server(server_config)
    try:
        return callback()
    except Exception as exc:
        raise RuntimeError(f"{phase_label} failed during isolated runtime execution") from exc
    finally:
        stop_server(handle)
        _release_phase_memory()


def _persist_single_payload(run_output_dir: Path, artifacts: dict[str, str], filename: str, payload: object) -> None:
    artifacts.update(persist_phase_outputs(run_output_dir, {filename: payload}))


def _emit_progress(message: str) -> None:
    print(f"[progress] {message}", file=sys.stderr, flush=True)


def _phase_a_progress_logger(event: dict[str, object]) -> None:
    if event.get("event") != "batch_completed":
        return
    category = str(event.get("general_category") or "")
    category_suffix = f" category={category}" if category else ""
    _emit_progress(
        "phase_a:batch "
        f"{event['batch_index']}/{event['batch_total']} "
        f"raw={event['raw_count']}/{event['raw_target']} "
        f"candidates={event['candidate_count']}/{event['candidate_target']} "
        f"stratum={event['generation_stratum']}{category_suffix}"
    )


def _resolved_raw_target(context: PhaseContext) -> int:
    return context.phase_a_raw_target or context.phase_a_max_candidates


def main() -> int:
    args = parse_args()
    protocol_root_dir = Path(args.protocol_root_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    protocol_bundle = load_protocol_bundle(protocol_root_dir)
    run_output_dir = create_run_output_dir(output_dir)
    server_config = build_default_server_config(
        port=args.port,
        ctx_size=args.ctx_size,
        model_path=args.model_path,
        model_alias=args.model_alias,
    )

    context = PhaseContext(
        protocol_root_dir=protocol_root_dir,
        run_output_dir=run_output_dir,
        protocol_bundle=protocol_bundle,
        host=server_config.host,
        port=server_config.port,
        phase_a_max_candidates=args.phase_a_max_candidates,
        phase_a_raw_target=args.phase_a_raw_target,
    )

    artifacts: dict[str, str] = {}

    _emit_progress(
        f"phase_a:start raw_target={_resolved_raw_target(context)} candidate_target={context.phase_a_max_candidates}"
    )
    phase_a_raw_records, phase_a_candidates, phase_a_raw_items = _run_with_fresh_llm_runtime(
        server_config,
        "phase_a",
        lambda: run_phase_a_with_artifacts(context, progress_callback=_phase_a_progress_logger),
    )
    _emit_progress(
        f"phase_a:done raw={len(phase_a_raw_records)}/{_resolved_raw_target(context)} "
        f"candidates={len(phase_a_candidates)}/{context.phase_a_max_candidates}"
    )
    _persist_single_payload(
        run_output_dir,
        artifacts,
        "phase_a_raw_items.json",
        phase_a_raw_items,
    )
    artifacts["raw.csv"] = persist_raw_candidate_records_csv(run_output_dir, "raw.csv", phase_a_raw_records)
    _persist_single_payload(
        run_output_dir,
        artifacts,
        "phase_a_candidates.json",
        [item.to_dict() for item in phase_a_candidates],
    )
    artifacts["phase_a_candidates.csv"] = persist_candidate_records_csv(
        run_output_dir,
        "phase_a_candidates.csv",
        phase_a_candidates,
    )

    _emit_progress(f"phase_b:start input={len(phase_a_candidates)}")
    phase_b_candidates = run_phase_b(context, phase_a_candidates)
    _emit_progress(f"phase_b:done output={len(phase_b_candidates)}")
    _persist_single_payload(
        run_output_dir,
        artifacts,
        "phase_b_normalized_candidates.json",
        [item.to_dict() for item in phase_b_candidates],
    )
    artifacts["phase_b_normalized_candidates.csv"] = persist_candidate_records_csv(
        run_output_dir,
        "phase_b_normalized_candidates.csv",
        phase_b_candidates,
    )

    _emit_progress(f"phase_c:start input={len(phase_b_candidates)}")
    phase_c_candidates = _run_with_fresh_llm_runtime(
        server_config,
        "phase_c",
        lambda: run_phase_c(context, phase_b_candidates),
    )
    _emit_progress(f"phase_c:done output={len(phase_c_candidates)}")
    _persist_single_payload(
        run_output_dir,
        artifacts,
        "phase_c_typed_candidates.json",
        [item.to_dict() for item in phase_c_candidates],
    )
    artifacts["phase_c_typed_candidates.csv"] = persist_candidate_records_csv(
        run_output_dir,
        "phase_c_typed_candidates.csv",
        phase_c_candidates,
    )

    _emit_progress(f"phase_d:start input={len(phase_c_candidates)}")
    phase_d_candidates = _run_with_fresh_llm_runtime(
        server_config,
        "phase_d",
        lambda: run_phase_d(context, phase_c_candidates),
    )
    _emit_progress(f"phase_d:done output={len(phase_d_candidates)}")
    _persist_single_payload(
        run_output_dir,
        artifacts,
        "phase_d_generalized_candidates.json",
        [item.to_dict() for item in phase_d_candidates],
    )
    artifacts["phase_d_generalized_candidates.csv"] = persist_candidate_records_csv(
        run_output_dir,
        "phase_d_generalized_candidates.csv",
        phase_d_candidates,
    )

    _emit_progress(f"phase_e:start input={len(phase_d_candidates)}")
    phase_e_candidates = _run_with_fresh_llm_runtime(
        server_config,
        "phase_e",
        lambda: run_phase_e(context, phase_d_candidates),
    )
    _emit_progress(f"phase_e:done output={len(phase_e_candidates)}")
    _persist_single_payload(
        run_output_dir,
        artifacts,
        "phase_e_scored_candidates.json",
        [item.to_dict() for item in phase_e_candidates],
    )
    artifacts["phase_e_scored_candidates.csv"] = persist_candidate_records_csv(
        run_output_dir,
        "phase_e_scored_candidates.csv",
        phase_e_candidates,
    )

    _emit_progress(f"phase_f:start input={len(phase_e_candidates)}")
    phase_f_merge_records = run_phase_f(context, phase_e_candidates)
    _emit_progress(f"phase_f:done merges={len(phase_f_merge_records)}")
    _persist_single_payload(
        run_output_dir,
        artifacts,
        "phase_f_merge_records.json",
        [item.to_dict() for item in phase_f_merge_records],
    )

    _emit_progress(f"phase_g:start input={len(phase_e_candidates)}")
    phase_g_candidates, phase_g_promotion_records, run_summary = _run_with_fresh_llm_runtime(
        server_config,
        "phase_g",
        lambda: run_phase_g(context, phase_e_candidates),
    )
    _emit_progress(
        f"phase_g:done candidates={len(phase_g_candidates)} promotions={len(phase_g_promotion_records)}"
    )
    _persist_single_payload(
        run_output_dir,
        artifacts,
        "phase_g_promotion_records.json",
        [item.to_dict() for item in phase_g_promotion_records],
    )
    _persist_single_payload(run_output_dir, artifacts, "run_summary.json", run_summary.to_dict())

    final_result = {
        "candidate_records": [candidate.to_dict() for candidate in phase_g_candidates],
        "merge_records": [record.to_dict() for record in phase_f_merge_records],
        "promotion_records": [record.to_dict() for record in phase_g_promotion_records],
        "run_summary": run_summary.to_dict(),
        "execution_model": str(server_config.model_path),
        "execution_strategy": "phase_isolated_llm_runtime",
    }
    _persist_single_payload(run_output_dir, artifacts, "final_result.json", final_result)
    _emit_progress(f"run:done output_dir={run_output_dir}")

    print(
        json.dumps(
            {
                "run_output_dir": str(run_output_dir),
                "artifacts": artifacts,
                "run_summary": to_serializable(run_summary),
                "execution_model": str(server_config.model_path),
                "execution_strategy": "phase_isolated_llm_runtime",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
