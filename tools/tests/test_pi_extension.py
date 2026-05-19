# Timestamp: 2026-05-19 14:47:00

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_PATH = REPO_ROOT / ".pi" / "extensions" / "bike-onto" / "index.ts"


def test_bike_onto_pi_extension_registers_commands_and_tools() -> None:
    source = EXTENSION_PATH.read_text(encoding="utf-8")

    for command in ["bike-setup", "bike-status", "bike-tools"]:
        assert f'pi.registerCommand("{command}"' in source

    for tool in ["bike_rag_answer", "bike_visual_inspect", "bike_ontology_map", "bike_wiki_export"]:
        assert f'name: "{tool}"' in source

    assert "ctx.ui.confirm" in source
    assert "ctx.ui.select" in source
    assert "runBike" in source
    assert "tools/scripts/rag/general_rag_cli.py" in source


def test_bike_onto_pi_extension_keeps_secret_handling_outside_repo() -> None:
    source = EXTENSION_PATH.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY" in source
    assert "~/.bike-onto" in source
    assert "apiKey" not in source
    assert "sk-" not in source
