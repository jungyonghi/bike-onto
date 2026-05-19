# Timestamp: 2026-04-20 16:40:01

import json
from pathlib import Path
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from project_paths import PROJECT_ROOT, TOOLS_SCRIPTS_DIR  # noqa: E402

import sisul_domain_crawler as crawler  # noqa: E402
from sisul_domain_crawler import (  # noqa: E402
    CrawlConfig,
    build_httrack_filters,
    build_tool_response,
    crawl_with_httrack_first,
    detect_dynamic_signals,
    find_project_root,
    find_shared_skill_scripts_dir,
    has_page_budget,
    normalize_url,
    resolve_scope,
    save_results,
    should_queue_url,
    summarize_by_prefix,
)


def test_normalize_url_keeps_same_domain_and_strips_fragments():
    config = CrawlConfig()

    normalized = normalize_url(
        "https://www.sisul.or.kr/open_content/main/#section1",
        config,
    )

    assert normalized == "https://www.sisul.or.kr/open_content/main/"


def test_normalize_url_rejects_blocked_extensions_and_external_domains():
    config = CrawlConfig()

    assert normalize_url("https://www.sisul.or.kr/file.pdf", config) is None
    assert normalize_url("https://example.com/page", config) is None


def test_summarize_by_prefix_counts_expected_sections():
    urls = [
        "https://www.sisul.or.kr/open_content/main/",
        "https://www.sisul.or.kr/open_content/main/community/faq_category.jsp",
        "https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
        "https://www.sisul.or.kr/open_content/parking/",
        "https://www.sisul.or.kr/gha/index.do",
    ]

    summary = summarize_by_prefix(urls)

    assert summary["/open_content/main/"] == 2
    assert summary["/open_content/traffic/"] == 1
    assert summary["/open_content/parking/"] == 1
    assert summary["other"] == 1


def test_resolve_scope_auto_uses_page_for_detail_url():
    resolved = resolve_scope(
        "https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
        "auto",
    )

    assert resolved["resolved_scope"] == "page"
    assert resolved["needs_user_confirmation"] is False


def test_resolve_scope_auto_uses_domain_for_root_url():
    resolved = resolve_scope("https://www.sisul.or.kr/", "auto")

    assert resolved["resolved_scope"] == "domain"
    assert resolved["needs_user_confirmation"] is False


def test_page_scope_does_not_expand_beyond_target_page():
    config = CrawlConfig(
        start_url="https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
        scope="page",
        page_seed_url="https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
    )

    assert (
        should_queue_url(
            "https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
            config,
        )
        is True
    )
    assert (
        should_queue_url(
            "https://www.sisul.or.kr/open_content/main/",
            config,
        )
        is False
    )


def test_save_results_emits_llm_context_files(tmp_path):
    result = {
        "timestamp": "2026-04-20 09:03:16",
        "status": "success",
        "resolved_scope": "page",
        "warnings": [],
        "next_prompt_hint": "hint",
        "config": {
            "start_url": "https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
            "allowed_domain": "www.sisul.or.kr",
            "scope": "page",
            "backup_mode": "metadata_only",
            "max_pages": 20,
            "timeout_seconds": 15,
            "output_dir": str(tmp_path),
            "respect_robots": True,
        },
        "summary": {
            "visited_html_pages": 1,
            "queued_seen_total": 1,
            "errors": 0,
            "by_prefix": {"/open_content/traffic/": 1},
        },
        "pages": [
            {
                "url": "https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
                "title": "서울시설공단 | 공공자전거",
                "status_code": 200,
                "content_type": "text/html; charset=UTF-8",
            }
        ],
        "errors": [],
    }

    saved = save_results(result, str(tmp_path), emit_llm_context=True)

    assert Path(saved["llm_context_json"]).exists()
    assert Path(saved["llm_context_md"]).exists()
    assert Path(saved["llm_prompt_templates_md"]).exists()


def test_build_tool_response_contains_required_contract_fields():
    result = {
        "timestamp": "2026-04-20 09:03:16",
        "status": "success",
        "resolved_scope": "domain",
        "warnings": ["warn"],
        "next_prompt_hint": "hint",
        "summary": {
            "visited_html_pages": 5,
            "queued_seen_total": 5,
            "errors": 0,
            "by_prefix": {"/open_content/main/": 5},
        },
    }

    response = build_tool_response(
        result=result,
        saved_files={"json": "/tmp/a.json"},
        root_artifact_dir="/tmp/artifacts",
    )

    assert response["status"] == "success"
    assert response["resolved_scope"] == "domain"
    assert response["visited_html_pages"] == 5
    assert response["saved_files"]["json"] == "/tmp/a.json"
    assert response["root_artifact_dir"] == "/tmp/artifacts"
    assert "warnings" in response
    assert "next_prompt_hint" in response


def test_build_tool_response_marks_empty_result_as_partial():
    result = {
        "timestamp": "2026-04-20 09:03:16",
        "status": "partial",
        "resolved_scope": "page",
        "warnings": ["No HTML pages were saved."],
        "next_prompt_hint": "질문을 통해 scope를 다시 확인하세요.",
        "summary": {
            "visited_html_pages": 0,
            "queued_seen_total": 0,
            "errors": 0,
            "by_prefix": {},
        },
    }

    response = build_tool_response(
        result=result,
        saved_files={},
        root_artifact_dir="/tmp/artifacts",
    )

    assert response["status"] == "partial"
    assert response["visited_html_pages"] == 0
    assert response["warnings"]


def test_find_project_root_uses_environment_independent_marker():
    script_path = TOOLS_SCRIPTS_DIR / "sisul_domain_crawler.py"
    project_root = find_project_root(script_path)

    assert project_root == PROJECT_ROOT


def test_find_shared_skill_scripts_dir_finds_07_skills_location():
    script_path = TOOLS_SCRIPTS_DIR / "sisul_domain_crawler.py"
    shared_dir = find_shared_skill_scripts_dir(script_path)

    assert shared_dir.name == "scripts"
    assert shared_dir.parent.name == "llm-site-backup-tool"
    assert "07_Skills" in str(shared_dir)


def test_max_pages_zero_means_unlimited_budget():
    config = CrawlConfig(max_pages=0)

    assert has_page_budget(visited_count=0, config=config) is True
    assert has_page_budget(visited_count=10_000, config=config) is True


def test_positive_max_pages_still_limits_budget():
    config = CrawlConfig(max_pages=3)

    assert has_page_budget(visited_count=2, config=config) is True
    assert has_page_budget(visited_count=3, config=config) is False


def test_build_httrack_filters_page_scope_keeps_target_and_shared_assets():
    config = CrawlConfig(
        start_url="https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
        allowed_domain="www.sisul.or.kr",
        scope="page",
        page_seed_url="https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
    )

    filters = build_httrack_filters(config)

    assert "+www.sisul.or.kr/open_content/traffic/bikeseoul.jsp*" in filters
    assert "+www.sisul.or.kr/open_content/share/*" in filters
    assert "+www.sisul.or.kr/open_content/images/*" in filters
    assert "+www.sisul.or.kr/seoulgnb/*" in filters
    assert filters[-1] == "-*"


def test_detect_dynamic_signals_finds_expected_markers():
    html = """
    <html>
      <body>
        <button>더보기</button>
        <div class="infinite-scroll"></div>
        <script>
          fetch('/api/list');
          window.history.pushState({}, '', '/app');
          const observer = new IntersectionObserver(() => {});
        </script>
      </body>
    </html>
    """

    signals = detect_dynamic_signals(html)

    assert "load_more_control" in signals
    assert "scripted_network_call" in signals
    assert "infinite_scroll_hint" in signals
    assert "js_routing_hint" in signals


def test_save_results_emits_hybrid_manifests_when_present(tmp_path):
    result = {
        "timestamp": "2026-04-20 09:03:16",
        "status": "partial",
        "resolved_scope": "page",
        "warnings": [],
        "next_prompt_hint": "hint",
        "config": {
            "start_url": "https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
            "allowed_domain": "www.sisul.or.kr",
            "scope": "page",
            "backup_mode": "metadata_only",
            "max_pages": 20,
            "timeout_seconds": 15,
            "output_dir": str(tmp_path),
            "respect_robots": True,
            "capture_engine": "httrack_first",
            "dynamic_fallback": "auto",
        },
        "summary": {
            "visited_html_pages": 1,
            "queued_seen_total": 1,
            "errors": 0,
            "by_prefix": {"/open_content/traffic/": 1},
        },
        "pages": [
            {
                "url": "https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
                "title": "서울시설공단 | 공공자전거",
                "status_code": 200,
                "content_type": "text/html; charset=UTF-8",
            }
        ],
        "errors": [],
        "mirror": {
            "engine": "httrack",
            "mirror_dir": str(tmp_path / "mirror"),
            "hts_log_path": str(tmp_path / "mirror" / "hts-log.txt"),
        },
        "dynamic_detection": {
            "fallback_mode": "auto",
            "candidate_count": 1,
            "candidates": [
                {
                    "url": "https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
                    "signals": ["load_more_control"],
                }
            ],
        },
        "dynamic_capture": {
            "executed": True,
            "actions": [
                {
                    "url": "https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
                    "clicked_texts": ["더보기"],
                }
            ],
            "network_artifacts": [],
            "html_artifacts": [],
            "downloads": [],
            "discovered_urls": [],
            "attachment_urls": [],
            "triggered_urls": [
                "https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp"
            ],
            "errors": [],
            "warnings": [],
        },
        "merge_summary": {
            "httrack_reseed_candidates": [],
            "new_html_urls": [],
            "attachment_urls": [],
        },
    }

    saved = save_results(result, str(tmp_path), emit_llm_context=True)

    assert Path(saved["httrack_manifest_json"]).exists()
    assert Path(saved["dynamic_candidates_json"]).exists()
    assert Path(saved["merge_manifest_json"]).exists()
    assert Path(saved["dynamic_actions_json"]).exists()

    dynamic_candidates = json.loads(Path(saved["dynamic_candidates_json"]).read_text())
    assert dynamic_candidates["candidate_count"] == 1


def test_build_tool_response_includes_optional_hybrid_sections():
    result = {
        "timestamp": "2026-04-20 09:03:16",
        "status": "partial",
        "resolved_scope": "page",
        "warnings": ["warn"],
        "next_prompt_hint": "hint",
        "summary": {
            "visited_html_pages": 2,
            "queued_seen_total": 2,
            "errors": 0,
            "by_prefix": {"/open_content/traffic/": 2},
        },
        "mirror": {"engine": "httrack"},
        "dynamic_detection": {"candidate_count": 1},
        "dynamic_capture": {"executed": True},
        "merge_summary": {"httrack_reseed_candidates": ["https://www.sisul.or.kr/a"]},
    }

    response = build_tool_response(
        result=result,
        saved_files={"json": "/tmp/a.json"},
        root_artifact_dir="/tmp/artifacts",
    )

    assert response["mirror"]["engine"] == "httrack"
    assert response["dynamic_detection"]["candidate_count"] == 1
    assert response["dynamic_capture"]["executed"] is True
    assert response["merge_summary"]["httrack_reseed_candidates"] == [
        "https://www.sisul.or.kr/a"
    ]


def test_crawl_with_httrack_first_skips_playwright_when_auto_without_candidates(
    monkeypatch,
    tmp_path,
):
    def fake_httrack_capture(config, artifact_dir):
        return {
            "pages": [
                {
                    "url": config.start_url,
                    "title": "Static page",
                    "status_code": 200,
                    "content_type": "text/html; charset=UTF-8",
                    "local_path": str(tmp_path / "mirror" / "page.html"),
                }
            ],
            "warnings": [],
            "errors": [],
            "mirror": {
                "engine": "httrack",
                "mirror_dir": str(tmp_path / "mirror"),
                "hts_log_path": str(tmp_path / "mirror" / "hts-log.txt"),
            },
        }

    def fake_collect_candidates(pages):
        return {
            "checked_pages": 1,
            "candidate_count": 0,
            "candidates": [],
            "signals_by_url": {},
        }

    def fail_playwright(*args, **kwargs):
        raise AssertionError("Playwright fallback should not run")

    monkeypatch.setattr(crawler._module, "run_httrack_capture", fake_httrack_capture)
    monkeypatch.setattr(
        crawler._module,
        "collect_dynamic_candidates_from_pages",
        fake_collect_candidates,
    )
    monkeypatch.setattr(
        crawler._module,
        "run_playwright_dynamic_capture",
        fail_playwright,
    )

    config = CrawlConfig(
        start_url="https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
        allowed_domain="www.sisul.or.kr",
        scope="page",
        capture_engine="httrack_first",
        dynamic_fallback="auto",
    )

    result = crawl_with_httrack_first(config, tmp_path)

    assert result["dynamic_capture"]["executed"] is False
    assert result["dynamic_detection"]["candidate_count"] == 0


def test_crawl_with_httrack_first_runs_playwright_for_detected_candidates(
    monkeypatch,
    tmp_path,
):
    discovered_url = "https://www.sisul.or.kr/open_content/traffic/detail.jsp?id=1"

    def fake_httrack_capture(config, artifact_dir):
        return {
            "pages": [
                {
                    "url": config.start_url,
                    "title": "Dynamic list",
                    "status_code": 200,
                    "content_type": "text/html; charset=UTF-8",
                    "local_path": str(tmp_path / "mirror" / "page.html"),
                }
            ],
            "warnings": ["httrack warning"],
            "errors": [],
            "mirror": {
                "engine": "httrack",
                "mirror_dir": str(tmp_path / "mirror"),
                "hts_log_path": str(tmp_path / "mirror" / "hts-log.txt"),
            },
        }

    def fake_collect_candidates(pages):
        return {
            "checked_pages": 1,
            "candidate_count": 1,
            "candidates": [
                {
                    "url": pages[0]["url"],
                    "signals": ["load_more_control"],
                    "local_path": pages[0]["local_path"],
                }
            ],
            "signals_by_url": {
                pages[0]["url"]: ["load_more_control"],
            },
        }

    def fake_playwright_capture(triggered_urls, config, artifact_dir):
        return {
            "executed": True,
            "triggered_urls": triggered_urls,
            "actions": [
                {
                    "url": triggered_urls[0],
                    "clicked_texts": ["더보기"],
                }
            ],
            "network_artifacts": [],
            "html_artifacts": [str(tmp_path / "dynamic" / "html" / "capture_001.html")],
            "downloads": [],
            "discovered_urls": [
                discovered_url,
                "https://www.sisul.or.kr/files/manual.pdf",
            ],
            "attachment_urls": ["https://www.sisul.or.kr/files/manual.pdf"],
            "new_pages": [
                {
                    "url": discovered_url,
                    "title": "Detail page",
                    "status_code": 200,
                    "content_type": "text/html; charset=UTF-8",
                    "source": "playwright_dynamic",
                }
            ],
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(crawler._module, "run_httrack_capture", fake_httrack_capture)
    monkeypatch.setattr(
        crawler._module,
        "collect_dynamic_candidates_from_pages",
        fake_collect_candidates,
    )
    monkeypatch.setattr(
        crawler._module,
        "run_playwright_dynamic_capture",
        fake_playwright_capture,
    )

    config = CrawlConfig(
        start_url="https://www.sisul.or.kr/open_content/traffic/bikeseoul.jsp",
        allowed_domain="www.sisul.or.kr",
        scope="page",
        capture_engine="httrack_first",
        dynamic_fallback="auto",
    )

    result = crawl_with_httrack_first(config, tmp_path)

    assert result["dynamic_capture"]["executed"] is True
    assert discovered_url in result["merge_summary"]["httrack_reseed_candidates"]
    assert any(page["url"] == discovered_url for page in result["pages"])
