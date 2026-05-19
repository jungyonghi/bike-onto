# Timestamp: 2026-04-20 16:40:01

"""Project wrapper for the shared LLM site backup tool.

This wrapper stays inside the project so local tests and project-specific defaults keep working,
but the reusable implementation lives in `07_Skills/llm-site-backup-tool/scripts`.

AI editing guide:
- Update project-local defaults here only if this project needs custom values.
- Update shared crawling logic in the 07_Skills module, not in this wrapper.
- If the project moves, set `LLM_SITE_BACKUP_SKILL_DIR` to the shared skill scripts path,
  or keep the repo somewhere under the same Documents tree so the auto-discovery still works.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys

from project_paths import CRAWL_RESULTS_DIR, PROJECT_ROOT, find_project_root


def find_shared_skill_scripts_dir(script_path: Path) -> Path:
    override = os.environ.get("LLM_SITE_BACKUP_SKILL_DIR")
    if override:
        path = Path(override).expanduser().resolve()
        if (path / "site_backup_tool.py").exists():
            return path

    for candidate in [script_path.resolve().parent, *script_path.resolve().parents]:
        maybe = candidate / "07_Skills" / "llm-site-backup-tool" / "scripts"
        if (maybe / "site_backup_tool.py").exists():
            return maybe

    raise FileNotFoundError(
        "Could not locate shared skill module. "
        "Set LLM_SITE_BACKUP_SKILL_DIR to 07_Skills/llm-site-backup-tool/scripts."
    )

SHARED_SKILL_SCRIPTS_DIR = find_shared_skill_scripts_dir(Path(__file__))
SHARED_MODULE_PATH = SHARED_SKILL_SCRIPTS_DIR / "site_backup_tool.py"

_spec = importlib.util.spec_from_file_location("site_backup_tool", SHARED_MODULE_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Failed to load shared module from {SHARED_MODULE_PATH}")
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

DEFAULT_PROJECT_OUTPUT_DIR = str(CRAWL_RESULTS_DIR)

# Re-export shared API for tests and local usage.
CrawlConfig = _module.CrawlConfig
normalize_url = _module.normalize_url
summarize_by_prefix = _module.summarize_by_prefix
resolve_scope = _module.resolve_scope
should_queue_url = _module.should_queue_url
has_page_budget = _module.has_page_budget
build_httrack_filters = _module.build_httrack_filters
detect_dynamic_signals = _module.detect_dynamic_signals
collect_dynamic_candidates_from_pages = _module.collect_dynamic_candidates_from_pages
run_httrack_capture = _module.run_httrack_capture
run_playwright_dynamic_capture = _module.run_playwright_dynamic_capture
crawl_with_httrack_first = _module.crawl_with_httrack_first
save_results = _module.save_results
build_tool_response = _module.build_tool_response
infer_allowed_domain = _module.infer_allowed_domain
run_backup_tool = _module.run_backup_tool
parse_args = _module.parse_args
main = _module.main


# Project-local default override:
_module.DEFAULT_CONFIG["output_dir"] = DEFAULT_PROJECT_OUTPUT_DIR


if __name__ == "__main__":
    main()
