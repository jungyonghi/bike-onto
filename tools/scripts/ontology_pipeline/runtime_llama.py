# Timestamp: 2026-04-20 18:24:07

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

from .config import DEFAULT_HOST, DEFAULT_PORT
from .config import build_server_command
from .schemas import LlamaServerConfig


def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _build_env(config: LlamaServerConfig) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("LD_LIBRARY_PATH", "")
    lib_path = str(config.llama_server_lib_dir)
    env["LD_LIBRARY_PATH"] = lib_path if not existing else f"{lib_path}:{existing}"
    return env


def _server_ready(host: str, port: int) -> bool:
    for path in ("/health", "/"):
        try:
            request = urllib.request.Request(_base_url(host, port) + path, method="GET")
            with urllib.request.urlopen(request, timeout=2) as response:
                if response.status < 500:
                    return True
        except Exception:
            continue
    return False


def start_server(config: LlamaServerConfig) -> subprocess.Popen[str] | None:
    if _server_ready(config.host, config.port):
        return None

    process = subprocess.Popen(
        build_server_command(config),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=_build_env(config),
    )

    deadline = time.time() + 120
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("llama-server terminated before becoming ready")
        if _server_ready(config.host, config.port):
            return process
        time.sleep(1)

    process.terminate()
    raise RuntimeError("Timed out while waiting for llama-server to become ready")


def stop_server(handle: subprocess.Popen[str] | None) -> None:
    if handle is None or handle.poll() is not None:
        return
    handle.terminate()
    try:
        handle.wait(timeout=10)
    except subprocess.TimeoutExpired:
        handle.kill()


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def _format_completion_prompt(prompt: str, system_prompt: str) -> str:
    return (
        "<|im_start|>system\n"
        f"{system_prompt}\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"{prompt}\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def generate(
    prompt: str,
    system_prompt: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    max_tokens: int = 2048,
    temperature: float = 0.1,
) -> str:
    chat_payload = {
        "model": "local-qwen",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        response = _post_json(_base_url(host, port) + "/v1/chat/completions", chat_payload)
        return response["choices"][0]["message"]["content"]
    except Exception:
        completion_payload = {
            "prompt": _format_completion_prompt(prompt, system_prompt),
            "temperature": temperature,
            "n_predict": max_tokens,
            "cache_prompt": True,
        }
        response = _post_json(_base_url(host, port) + "/completion", completion_payload)
        if "content" in response:
            return response["content"]
        return response.get("completion", "")
