# Timestamp: 2026-04-20 18:24:07

from __future__ import annotations

from pathlib import Path

from project_paths import DOCS_DIR, PROCESSED_DIR

from .schemas import LlamaServerConfig


DEFAULT_MODEL_PATH = Path("/home/user/Documents/11_Models/Qwen3.5-9B.Q4_K_M.gguf")
DEFAULT_LLAMA_SERVER_BIN = Path(
    "/home/user/Documents/01_Projects/04_Discarded/llama.cpp/build-cuda/bin/llama-server"
)
DEFAULT_LLAMA_SERVER_LIB_DIR = DEFAULT_LLAMA_SERVER_BIN.parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18080
DEFAULT_CTX_SIZE = 16384
DEFAULT_PARALLEL = 1
DEFAULT_NGL = 999
DEFAULT_MAX_CHUNK_CHARS = 12000
DEFAULT_PHASE_A_MAX_CANDIDATES = 10000
DEFAULT_PROTOCOL_ROOT_DIR = DOCS_DIR / "steps"
DEFAULT_OUTPUT_DIR = PROCESSED_DIR / "exports" / "ontology_term_runs"


def build_server_command(config: LlamaServerConfig) -> list[str]:
    command = [
        str(config.llama_server_bin),
        "-m",
        str(config.model_path),
        "-ngl",
        str(config.ngl),
        "-c",
        str(config.ctx_size),
        "--host",
        config.host,
        "--port",
        str(config.port),
        "--parallel",
        str(config.parallel),
    ]
    if config.no_kv_offload:
        command.append("-nkvo")
    command.extend(config.extra_args)
    return command


def build_default_server_config(
    port: int = DEFAULT_PORT,
    ctx_size: int = DEFAULT_CTX_SIZE,
) -> LlamaServerConfig:
    return LlamaServerConfig(
        llama_server_bin=DEFAULT_LLAMA_SERVER_BIN,
        llama_server_lib_dir=DEFAULT_LLAMA_SERVER_LIB_DIR,
        model_path=DEFAULT_MODEL_PATH,
        host=DEFAULT_HOST,
        port=port,
        ctx_size=ctx_size,
        parallel=DEFAULT_PARALLEL,
        ngl=DEFAULT_NGL,
        no_kv_offload=True,
    )


# Timestamp: 2026-04-20 20:45:00
DEFAULT_MODEL_ALIAS = "qwen35_9b_q4_k_m"
REGISTERED_MODEL_PATHS = {
    DEFAULT_MODEL_ALIAS: DEFAULT_MODEL_PATH,
    "qwen35_4b_mp_q6_k_h": Path("/home/user/Documents/11_Models/Qwen3.5-4B-MP.Q6_K_H.gguf"),
    "qwen35_4b_claude_opus_46_distilled_q4_k_m": Path(
        "/home/user/Documents/11_Models/Qwen3.5-4B-Claude-Opus-4.6-Distilled.Q4_K_M.gguf"
    ),
    "opus47_godsghost_codex_4b_q4_k_m": Path(
        "/home/user/Documents/11_Models/Opus4.7-GODsGhost-Codex-4B-Q4_K_M.gguf"
    ),
}
REGISTERED_MODEL_SOURCES = {
    DEFAULT_MODEL_ALIAS: "local-default",
    "qwen35_4b_mp_q6_k_h": "local-available",
    "qwen35_4b_claude_opus_46_distilled_q4_k_m": "local-available",
    "opus47_godsghost_codex_4b_q4_k_m": (
        "https://huggingface.co/WithinUsAI/Opus4.7-GODs.Ghost.Codex-4B.GGuF"
    ),
}


def list_registered_model_aliases() -> list[str]:
    return sorted(REGISTERED_MODEL_PATHS)


def resolve_model_path(
    model_path: str | Path | None = None,
    model_alias: str | None = None,
) -> Path:
    if model_path is not None and model_alias is not None:
        raise ValueError("Provide either model_path or model_alias, not both.")

    if model_alias is not None:
        if model_alias not in REGISTERED_MODEL_PATHS:
            available = ", ".join(list_registered_model_aliases())
            raise ValueError(f"Unknown model_alias '{model_alias}'. Available aliases: {available}")
        return REGISTERED_MODEL_PATHS[model_alias]

    if model_path is not None:
        return Path(model_path).expanduser().resolve()

    return REGISTERED_MODEL_PATHS[DEFAULT_MODEL_ALIAS]


def build_default_server_config(
    port: int = DEFAULT_PORT,
    ctx_size: int = DEFAULT_CTX_SIZE,
    model_path: str | Path | None = None,
    model_alias: str | None = None,
) -> LlamaServerConfig:
    return LlamaServerConfig(
        llama_server_bin=DEFAULT_LLAMA_SERVER_BIN,
        llama_server_lib_dir=DEFAULT_LLAMA_SERVER_LIB_DIR,
        model_path=resolve_model_path(model_path=model_path, model_alias=model_alias),
        host=DEFAULT_HOST,
        port=port,
        ctx_size=ctx_size,
        parallel=DEFAULT_PARALLEL,
        ngl=DEFAULT_NGL,
        no_kv_offload=True,
    )
