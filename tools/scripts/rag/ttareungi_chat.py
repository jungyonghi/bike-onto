# Timestamp: 2026-04-21 23:24:00

from __future__ import annotations

from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from rag.ttareungi_rag import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["ask", *sys.argv[1:]]))
