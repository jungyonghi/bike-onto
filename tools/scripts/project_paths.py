# Timestamp: 2026-04-20 16:40:01

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT_MARKER = ".obybk-root"


def find_project_root(start_path: Path) -> Path:
    resolved = start_path.expanduser().resolve()
    current = resolved if resolved.is_dir() else resolved.parent

    for candidate in [current, *current.parents]:
        if (candidate / PROJECT_ROOT_MARKER).exists():
            return candidate

    raise FileNotFoundError(
        f"Could not locate project root marker '{PROJECT_ROOT_MARKER}' from {start_path}."
    )


PROJECT_ROOT = find_project_root(Path(__file__))
TOOLS_DIR = PROJECT_ROOT / "tools"
TOOLS_SCRIPTS_DIR = TOOLS_DIR / "scripts"
TOOLS_TESTS_DIR = TOOLS_DIR / "tests"
DOCS_DIR = PROJECT_ROOT / "docs"
DOCS_PROJECT_DIR = DOCS_DIR / "project"
TERMINOLOGY_DIR = DOCS_DIR / "terminology"
DATA_DIR = PROJECT_ROOT / "data"
RAW_PUBLIC_DIR = DATA_DIR / "raw" / "public"
PROCESSED_DIR = DATA_DIR / "processed"
CAPTURES_DIR = DATA_DIR / "captures"
CRAWL_RESULTS_DIR = CAPTURES_DIR / "crawl_results"
WEB_MIRRORS_DIR = CAPTURES_DIR / "web_mirrors"
REFERENCES_DIR = PROJECT_ROOT / "references"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
ARCHIVE_DIR = PROJECT_ROOT / "archive"
MARKER_PROJECT_DIR = Path(
    os.environ.get(
        "OBYBK_MARKER_PROJECT_DIR",
        "/home/user/Documents/01_Projects/01_Active/marker",
    )
).expanduser()
