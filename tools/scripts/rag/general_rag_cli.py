# Timestamp: 2026-05-19 14:09:00

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any
from urllib.parse import quote
import webbrowser

# Allow direct execution: python tools/scripts/rag/general_rag_cli.py ...
TOOLS_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_SCRIPTS_DIR.parents[1]
if str(TOOLS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_SCRIPTS_DIR))

from rag.nodeprompt_ontology_map import write_nodeprompt_ontology_map_png, write_nodeprompt_ontology_tree_png, write_preview_crop, write_tree_focus_crop  # noqa: E402
from rag.obsidian_wiki_export import export_ontology_wiki  # noqa: E402
from rag.pgvector_store import init_pgvector_schema, load_pgvector_seed, pgvector_status, search_pgvector  # noqa: E402
from rag.rag_llm_answer_endpoint import (  # noqa: E402
    fallback_grounded_answer,
    generate_rag_llm_answer,
    read_jsonl,
)
from rag.rag_llm_answer_report import build_rag_llm_answer_report  # noqa: E402
from rag.terminal_entity_inspector import collect_inspector_entities, render_terminal_entity_inspector, write_terminal_inspector_screenshot  # noqa: E402
from rag.visual_inspector import build_evaluation_overview_payload, build_visual_graph_payload, write_visual_inspector_html  # noqa: E402


NATIVE_AGENT_COMMANDS = [
    "demo-wizard",
    "inspect-dir",
    "ask",
    "chat",
    "report",
    "visual",
    "visual-eval",
    "wiki-export",
    "ontology-map",
    "benchmark-polish",
    "inspect-answer",
    "agent-catalog",
    "agent-run",
    "db-init",
    "db-status",
    "db-load-eval",
    "pgvector-init",
    "pgvector-load",
    "pgvector-status",
    "pgvector-search",
    "snippet-put",
    "snippet-get",
    "snippet-list",
    "snippet-delete",
]

AGENT_TOOL_REGISTRY: dict[str, dict[str, str]] = {
    "pgpack": {"script": "tools/scripts/rag/pgvector_integration_pack.py", "kind": "artifact", "desc": "build pgvector SQL and JSONL seed"},
    "mlpack": {"script": "tools/scripts/rag/ml_execution_pack.py", "kind": "artifact", "desc": "build ML execution feature pack"},
    "perf": {"script": "tools/scripts/rag/analyze_ontology_rag_performance.py", "kind": "analysis", "desc": "analyze ontology RAG performance"},
    "dbbench": {"script": "tools/scripts/rag/run_db_only_rag_benchmark.py", "kind": "evaluation", "desc": "run or analyze DB-only RAG benchmark"},
    "probe": {"script": "tools/scripts/rag/run_ontology_question_probe.py", "kind": "evaluation", "desc": "run ontology-fit question probes"},
    "profilecmp": {"script": "tools/scripts/rag/run_rag_profile_comparison.py", "kind": "evaluation", "desc": "compare DB-only and ontology-hybrid profiles"},
    "perq": {"script": "tools/scripts/rag/per_question_evaluation_report.py", "kind": "report", "desc": "per-question evaluation report"},
    "redact": {"script": "tools/scripts/rag/infer_ttareungi_redacted_documents.py", "kind": "inference", "desc": "infer guarded summaries for redacted docs"},
    "sim": {"script": "tools/scripts/rag/run_ttareungi_reallocation_simulation.py", "kind": "simulation", "desc": "run ontology-based reallocation simulation"},
    "rag-domain": {"script": "tools/scripts/rag/ttareungi_rag.py", "kind": "legacy", "desc": "domain case-study RAG CLI"},
    "chat-domain": {"script": "tools/scripts/rag/ttareungi_interactive.py", "kind": "legacy", "desc": "domain case-study interactive chat"},
    "vec-explain": {"script": "tools/scripts/rag/explain_ttareungi_vector_db.py", "kind": "explain", "desc": "explain vector DB loading"},
    "catboost": {"script": "tools/scripts/rag/catboost_optional_baseline.py", "kind": "baseline", "desc": "optional CatBoost baseline"},
    "llm-report": {"script": "tools/scripts/rag/rag_llm_answer_report.py", "kind": "report", "desc": "legacy RAG LLM answer report"},
    "build-index": {"script": "tools/scripts/rag/build_ttareungi_index.py", "kind": "legacy", "desc": "build case-study RAG index"},
    "rag-ask": {"script": "tools/scripts/rag/ttareungi_chat.py", "kind": "legacy", "desc": "case-study ask wrapper"},
    "interactive-chat": {"script": "tools/scripts/rag/ttareungi_interactive_chat.py", "kind": "legacy", "desc": "case-study interactive chat wrapper"},
    "fastapi": {"script": "tools/scripts/rag/ontology_rag_fastapi_app.py", "kind": "serve", "desc": "serve/smoke-test optional FastAPI app"},
    "upper-ontology": {"script": "tools/scripts/generate_codex_upper_ontology_seed.py", "kind": "ontology", "desc": "generate upper ontology seed"},
    "domain-ontology": {"script": "tools/scripts/generate_ttareungi_domain_ontology.py", "kind": "ontology", "desc": "generate domain ontology from upper anchors"},
    "local-ontology": {"script": "tools/scripts/run_local_ontology_pipeline.py", "kind": "ontology", "desc": "run local ontology pipeline"},
    "crawler": {"script": "tools/scripts/sisul_domain_crawler.py", "kind": "crawl", "desc": "run domain crawler"},
    "marker": {"script": "tools/scripts/marker_runner.py", "kind": "extract", "desc": "run marker document extraction helper"},
    "streamlit-main": {"script": "tools/scripts/rag/ttareungi_streamlit_app.py", "kind": "ui", "desc": "launch Streamlit case-study app"},
    "streamlit-realloc": {"script": "tools/scripts/rag/ttareungi_reallocation_streamlit_app.py", "kind": "ui", "desc": "launch Streamlit reallocation app"},
}

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS rag_runs (
  run_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  domain_dir TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS rag_artifacts (
  artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT,
  kind TEXT NOT NULL,
  path TEXT NOT NULL,
  meta_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES rag_runs(run_id)
);
CREATE TABLE IF NOT EXISTS rag_evaluation_questions (
  question_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  category TEXT,
  question TEXT,
  status TEXT,
  contract_pass INTEGER NOT NULL DEFAULT 0,
  requires_review INTEGER NOT NULL DEFAULT 0,
  llm_mode TEXT,
  data_gap_count INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL,
  PRIMARY KEY(question_id, run_id),
  FOREIGN KEY(run_id) REFERENCES rag_runs(run_id)
);
CREATE TABLE IF NOT EXISTS review_queue (
  review_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES rag_runs(run_id)
);
CREATE TABLE IF NOT EXISTS agent_snippets (
  key TEXT PRIMARY KEY,
  title TEXT,
  content TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '',
  hit_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rag_eval_run ON rag_evaluation_questions(run_id);
CREATE INDEX IF NOT EXISTS idx_rag_eval_category ON rag_evaluation_questions(category);
CREATE INDEX IF NOT EXISTS idx_review_queue_run ON review_queue(run_id, status);
CREATE INDEX IF NOT EXISTS idx_agent_snippets_tags ON agent_snippets(tags);
"""

POSTGRES_SCHEMA = """
-- Timestamp: 2026-05-19 11:52:00
-- OBYBK RAG store PostgreSQL schema handoff
CREATE TABLE IF NOT EXISTS rag_runs (
  run_id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL,
  domain_dir TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS rag_artifacts (
  artifact_id BIGSERIAL PRIMARY KEY,
  run_id TEXT REFERENCES rag_runs(run_id),
  kind TEXT NOT NULL,
  path TEXT NOT NULL,
  meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS rag_evaluation_questions (
  question_id TEXT NOT NULL,
  run_id TEXT NOT NULL REFERENCES rag_runs(run_id),
  category TEXT,
  question TEXT,
  status TEXT,
  contract_pass BOOLEAN NOT NULL DEFAULT FALSE,
  requires_review BOOLEAN NOT NULL DEFAULT FALSE,
  llm_mode TEXT,
  data_gap_count INTEGER NOT NULL DEFAULT 0,
  payload_json JSONB NOT NULL,
  PRIMARY KEY(question_id, run_id)
);
CREATE TABLE IF NOT EXISTS review_queue (
  review_id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES rag_runs(run_id),
  question_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_snippets (
  key TEXT PRIMARY KEY,
  title TEXT,
  content TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '',
  hit_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rag_eval_run ON rag_evaluation_questions(run_id);
CREATE INDEX IF NOT EXISTS idx_rag_eval_category ON rag_evaluation_questions(category);
CREATE INDEX IF NOT EXISTS idx_review_queue_run ON review_queue(run_id, status);
CREATE INDEX IF NOT EXISTS idx_agent_snippets_tags ON agent_snippets(tags);
"""

DB_TABLES = ["rag_runs", "rag_artifacts", "rag_evaluation_questions", "review_queue", "agent_snippets"]


def _runtime_rows(runtime_answers: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("id") or row.get("question_id")): row for row in read_jsonl(runtime_answers)}


def _load_seed_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    if getattr(args, "retriever", "local") == "pgvector":
        return []
    if not getattr(args, "pgvector_seed", None):
        raise ValueError("--pgvector-seed is required when --retriever local")
    return read_jsonl(args.pgvector_seed)


def _retrieved_contexts(args: argparse.Namespace, question: str) -> tuple[list[dict[str, Any]] | None, float | None]:
    if getattr(args, "retriever", "local") != "pgvector":
        return None, None
    dsn = args.dsn or os.environ.get("DATABASE_URL", "")
    started = time.perf_counter()
    matches = search_pgvector(dsn, question, table_name=args.pgvector_table, top_k=args.top_k)
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return matches, latency_ms


def _offline_llm(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    return fallback_grounded_answer(context, mode="offline_cli", model="offline-grounded")


def _entity_link_map(payload: dict[str, Any], index_html: Path | None) -> dict[str, str]:
    if not index_html:
        return {}
    links: dict[str, str] = {}
    for entity in collect_inspector_entities(payload):
        uri = _file_uri(index_html, fragment=_html_anchor(entity.entity_id))
        for key in {entity.entity_id, entity.label, str(entity.raw.get("label") or ""), str(entity.raw.get("station_name") or "")}:
            key = key.strip()
            if key and key not in links:
                links[key] = uri
    return links


def _decorate_answer_with_entity_links(text: str, payload: dict[str, Any], index_html: Path | None) -> str:
    links = _entity_link_map(payload, index_html)
    if not links:
        return text
    decorated = text
    # Replace longer labels first so "충무로역 3.4호선 (ST-152)" wins before "ST-152".
    for label in sorted(links, key=len, reverse=True):
        if label not in decorated:
            continue
        decorated = decorated.replace(label, _osc8_link(label, links[label], enabled=True), 1)
    return decorated


def _print_answer(payload: dict[str, Any], *, visual_index_html: Path | None = None) -> None:
    print("\n[질의]\n")
    question = payload.get("question") or payload.get("input_question") or ""
    if question:
        print(question)

    print("\n[답변 — entity 이름은 Ctrl+Click 가능]\n" if visual_index_html else "\n[답변]\n")
    print(_decorate_answer_with_entity_links(str(payload.get("answer", "")), payload, visual_index_html))

    candidates = payload.get("candidate_set") or []
    if candidates:
        entity_links = _entity_link_map(payload, visual_index_html)
        print("\n[후보 — Ctrl+Click하면 시각화 페이지의 entity card로 이동]\n" if visual_index_html else "\n[후보]\n")
        for candidate in candidates[:8]:
            candidate_id = str(candidate.get("candidate_id") or "")
            candidate_label = candidate_id
            for entity in collect_inspector_entities(payload):
                if entity.entity_id == candidate_id:
                    candidate_label = entity.label
                    break
            link_uri = entity_links.get(candidate_id) or entity_links.get(candidate_label)
            printable_candidate = _osc8_link(candidate_label, link_uri, enabled=True) if link_uri else candidate_id
            print(
                "-",
                printable_candidate,
                "rank=",
                candidate.get("rank"),
                "score=",
                candidate.get("score"),
                "source=",
                candidate.get("source_metric"),
            )

    indicators = payload.get("quantitative_indicators") or []
    if indicators:
        print("\n[정량 지표]\n")
        for metric in indicators[:10]:
            print("-", metric.get("metric"), "=", metric.get("value"), f"({metric.get('source')})")

    gaps = payload.get("data_gaps") or []
    if gaps:
        print("\n[데이터 공백 / 다음 분석]\n")
        for gap in gaps[:8]:
            print("-", gap)

    excerpts = payload.get("evidence_excerpt_list") or []
    if excerpts:
        print("\n[발췌 목록]\n")
        for item in excerpts[:8]:
            excerpt = str(item.get("excerpt") or "").replace("\n", " ")[:220]
            print(f"- {item.get('source')} ({item.get('kind')}, score={item.get('score')}): {excerpt}")

    print("\n[실행 메타]\n")
    print("- llm_mode:", payload.get("llm", {}).get("mode"))
    print("- model:", payload.get("llm", {}).get("model"))
    print("- contract_pass:", payload.get("contract_pass"))
    print("- requires_review:", payload.get("requires_review"))


def _html_anchor(value: Any) -> str:
    text = str(value or "entity").strip()
    slug = "".join(ch if ch.isalnum() else "-" for ch in text).strip("-")
    return "entity-" + (slug or "unknown")


def _relative_href(path: Path, base_dir: Path) -> str:
    try:
        return path.relative_to(base_dir).as_posix()
    except ValueError:
        return path.resolve().as_uri()


def _osc8_link(label: str, uri: str, *, enabled: bool = True) -> str:
    if not enabled:
        return f"{label} ({uri})"
    return f"\033]8;;{uri}\033\\{label}\033]8;;\033\\"


def _file_uri(path: Path, *, fragment: str = "") -> str:
    uri = path.resolve().as_uri()
    if fragment:
        uri = uri + "#" + quote(fragment, safe="-_:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
    return uri


def _write_visual_click_index(
    payload: dict[str, Any],
    *,
    index_html: Path,
    ontology_png: Path,
    preview_jpg: Path,
    visual_inspector_html: Path,
    answer_json: Path,
    ontology_tree_png: Path,
    ontology_tree_focus_png: Path,
) -> None:
    entities = collect_inspector_entities(payload)
    entity_cards: list[str] = []
    for entity in entities[:20]:
        anchor = _html_anchor(entity.entity_id)
        attrs = []
        for key, value in entity.raw.items():
            if key in {"id", "label", "display_name"} or value in (None, "", []):
                continue
            attrs.append(f"<li><code>{html.escape(str(key))}</code>: {html.escape(str(value))}</li>")
            if len(attrs) >= 6:
                break
        entity_cards.append(
            f"""
            <article class="entity-card" id="{html.escape(anchor)}">
              <div class="entity-kicker">Entity #{entity.index} · {html.escape(entity.source)}</div>
              <h3>{html.escape(entity.label)}</h3>
              <p><strong>ID</strong> <code>{html.escape(entity.entity_id)}</code> · <strong>Type</strong> {html.escape(entity.entity_type)}</p>
              <ul>{''.join(attrs) if attrs else '<li>현재 payload에 추가 attribute 없음</li>'}</ul>
            </article>
            """
        )
    if not entity_cards:
        entity_cards.append("<article class='entity-card'><h3>No entity extracted</h3><p>현재 payload에서 entity/candidate를 찾지 못했습니다.</p></article>")

    answer_excerpt = str(payload.get("answer") or "").replace("\n", " ")[:650]
    question = str(payload.get("question") or payload.get("input_question") or "")
    html_text = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OBYBK Clickable Ontology Visual</title>
  <style>
    :root {{ --ink:#111; --muted:#707070; --line:#dedede; --soft:#fafafa; --danger:#b91c1c; }}
    html, body {{ height:100%; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR','Segoe UI',sans-serif; color:var(--ink); background:#fff; overflow:hidden; }}
    header {{ position:sticky; top:0; z-index:2; display:flex; gap:16px; align-items:center; justify-content:space-between; padding:14px 22px; border-bottom:1px solid var(--line); background:rgba(255,255,255,.94); backdrop-filter:blur(8px); }}
    .brand {{ font-weight:700; }}
    .toolbar {{ display:flex; gap:10px; flex-wrap:wrap; font-size:13px; }}
    .pill {{ color:#111; text-decoration:none; border:1px solid var(--line); border-radius:999px; padding:7px 11px; background:#fff; font:inherit; cursor:pointer; }}
    .pill.active {{ background:#111; color:#fff; border-color:#111; }}
    main {{ height:calc(100vh - 62px); display:grid; grid-template-columns:minmax(440px,1fr) minmax(330px,430px); gap:20px; padding:20px; box-sizing:border-box; overflow:hidden; }}
    .stage {{ position:sticky; top:82px; height:calc(100vh - 104px); border:1px solid var(--line); border-radius:16px; padding:14px; background:#fff; box-sizing:border-box; display:flex; flex-direction:column; align-items:center; justify-content:center; overflow:hidden; }}
    .stage-title {{ align-self:flex-start; color:var(--muted); font-size:13px; margin:0 0 8px 4px; }}
    .stage img {{ max-width:100%; max-height:calc(100% - 28px); width:auto; height:auto; display:block; border-radius:12px; object-fit:contain; }}
    aside {{ height:calc(100vh - 104px); overflow-y:auto; display:flex; flex-direction:column; gap:14px; padding:4px 8px 24px 0; scroll-behavior:smooth; }}
    .panel, .entity-card {{ border:1px solid var(--line); border-radius:14px; background:#fff; padding:16px; }}
    .panel h2, .entity-card h3 {{ margin:0 0 10px; }}
    .muted, .entity-kicker {{ color:var(--muted); font-size:13px; }}
    code {{ background:#f4f4f5; border-radius:5px; padding:1px 5px; }}
    .entity-card:target {{ outline:4px solid #111; box-shadow:0 0 0 8px #f4f4f5; }}
    .entity-card ul {{ padding-left:18px; }}
    .answer {{ max-height:150px; overflow:auto; line-height:1.5; }}
    @media (max-width: 860px) {{ main {{ grid-template-columns:minmax(340px,52vw) minmax(300px,1fr); gap:12px; padding:12px; }} .toolbar {{ display:none; }} }}
  </style>
</head>
<body>
  <header>
    <div class="brand">● OBYBK Clickable Ontology Visual</div>
    <nav class="toolbar">
      <button class="pill active" type="button" data-view="tree" data-visual-label="Ontology Tree" data-visual-src="{html.escape(_relative_href(ontology_tree_focus_png, index_html.parent))}">Ontology Tree</button>
      <button class="pill" type="button" data-view="radial" data-visual-label="Radial Map" data-visual-src="{html.escape(_relative_href(preview_jpg, index_html.parent))}">Radial Map</button>
      <a class="pill" href="{html.escape(_relative_href(visual_inspector_html, index_html.parent))}">Visual Inspector HTML</a>
      <a class="pill" href="{html.escape(_relative_href(answer_json, index_html.parent))}">Answer JSON</a>
    </nav>
  </header>
  <main>
    <section class="stage">
      <div class="stage-title" id="stage-title">Ontology Tree</div>
      <img id="ontology-visual" src="{html.escape(_relative_href(ontology_tree_focus_png, index_html.parent))}" alt="NODEPROMPT-inspired answer ontology graphic">
    </section>
    <aside>
      <section class="panel">
        <p class="muted">Question</p>
        <h2>{html.escape(question or 'RAG Answer')}</h2>
        <p class="muted">Answer excerpt</p>
        <div class="answer">{html.escape(answer_excerpt)}</div>
      </section>
      <section class="panel">
        <h2>Click Targets</h2>
        <p class="muted">CLI에서 entity 링크를 Ctrl+Click하면 이 페이지의 해당 entity card로 이동합니다.</p>
      </section>
      {''.join(entity_cards)}
    </aside>
  </main>
  <script>
    const visual = document.getElementById('ontology-visual');
    const title = document.getElementById('stage-title');
    const buttons = Array.from(document.querySelectorAll('[data-visual-src]'));
    function activateVisual(view) {{
      const button = buttons.find((item) => item.dataset.view === view) || buttons[0];
      if (!button || !visual) return;
      visual.src = button.dataset.visualSrc;
      visual.alt = button.dataset.visualLabel || 'Ontology visual';
      if (title) title.textContent = button.dataset.visualLabel || 'Ontology visual';
      buttons.forEach((item) => item.classList.toggle('active', item === button));
    }}
    buttons.forEach((button) => button.addEventListener('click', () => activateVisual(button.dataset.view)));
    const initialView = new URLSearchParams(window.location.search).get('view');
    if (initialView) activateVisual(initialView);
  </script>
</body>
</html>
"""
    index_html.write_text(html_text, encoding="utf-8")


def _find_app_mode_browser() -> str | None:
    env_browser = os.environ.get("OBYBK_VISUAL_BROWSER", "").strip()
    if env_browser and Path(env_browser).exists():
        return env_browser
    playwright_chrome = Path.home() / ".cache/ms-playwright/chromium-1194/chrome-linux/chrome"
    candidates = [
        env_browser,
        "msedge",
        "microsoft-edge",
        "google-chrome",
        "chrome",
        "chromium",
        "chromium-browser",
        str(playwright_chrome),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) or (candidate if Path(candidate).exists() else "")
        if resolved:
            return resolved
    return None


def open_visual_app_window(index_html: Path) -> bool:
    """Open local visual HTML in browser app mode, hiding tabs/address bar when supported."""
    browser = _find_app_mode_browser()
    if not browser:
        webbrowser.open(index_html.resolve().as_uri())
        return False
    uri = index_html.resolve().as_uri()
    args = [
        browser,
        f"--app={uri}",
        "--new-window",
        "--test-type",
        "--disable-infobars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
    ]
    if os.name != "nt" and any(name in Path(browser).name.lower() for name in ("chrome", "chromium")):
        args.extend(["--disable-dev-shm-usage", "--no-sandbox"])
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def build_visual_click_artifacts(
    payload: dict[str, Any],
    output_dir: Path,
    *,
    focused_entity: str | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    answer_json = output_dir / "answer_payload.json"
    answer_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    visual_graph = build_visual_graph_payload(payload, debug_mode=False)
    visual_inspector_html = write_visual_inspector_html(visual_graph, output_dir / "answer_visual_inspector.html", debug_mode=False)
    visual_graph_json = output_dir / "answer_visual_graph.json"
    visual_graph_json.write_text(json.dumps(visual_graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ontology_png = output_dir / "nodeprompt_ontology_map.png"
    ontology_json = output_dir / "nodeprompt_ontology_map.json"
    ontology_payload = write_nodeprompt_ontology_map_png(
        ontology_png,
        graph_json=ontology_json,
        answer_payload=payload,
        focused_entity=focused_entity,
    )
    ontology_tree_png = output_dir / "nodeprompt_ontology_tree.png"
    tree_payload = write_nodeprompt_ontology_tree_png(
        ontology_tree_png,
        answer_payload=payload,
        focused_entity=focused_entity,
    )
    ontology_tree_focus_png = output_dir / "nodeprompt_ontology_tree_focus.png"
    write_tree_focus_crop(ontology_tree_png, ontology_tree_focus_png)
    preview_jpg = output_dir / "nodeprompt_ontology_map_preview.jpg"
    write_preview_crop(ontology_png, preview_jpg)
    index_html = output_dir / "index.html"
    _write_visual_click_index(
        payload,
        index_html=index_html,
        ontology_png=ontology_png,
        preview_jpg=preview_jpg,
        visual_inspector_html=visual_inspector_html,
        answer_json=answer_json,
        ontology_tree_png=ontology_tree_png,
        ontology_tree_focus_png=ontology_tree_focus_png,
    )
    return {
        "index_html": str(index_html),
        "ontology_png": str(ontology_png),
        "ontology_preview": str(preview_jpg),
        "ontology_tree_png": str(ontology_tree_png),
        "ontology_tree_focus_png": str(ontology_tree_focus_png),
        "ontology_json": str(ontology_json),
        "answer_visual_inspector_html": str(visual_inspector_html),
        "answer_visual_graph_json": str(visual_graph_json),
        "answer_json": str(answer_json),
        "node_count": ontology_payload.get("node_count"),
        "edge_count": ontology_payload.get("edge_count"),
        "entity_node_count": ontology_payload.get("entity_node_count"),
        "tree_node_count": tree_payload.get("node_count"),
    }


def _print_visual_click_links(payload: dict[str, Any], artifacts: dict[str, Any], *, terminal_links: bool) -> None:
    index_html = Path(str(artifacts["index_html"]))
    ontology_png = Path(str(artifacts["ontology_png"]))
    visual_html = Path(str(artifacts["answer_visual_inspector_html"]))
    print("\n[클릭 시각화]\n")
    print("-", _osc8_link("Open NODEPROMPT-style ontology map", _file_uri(index_html), enabled=terminal_links))
    print("-", _osc8_link("Open full PNG", _file_uri(ontology_png), enabled=terminal_links))
    print("-", _osc8_link("Open answer Visual Inspector", _file_uri(visual_html), enabled=terminal_links))
    entities = collect_inspector_entities(payload)
    if entities:
        print("\n[Entity click targets]")
        for entity in entities[:10]:
            anchor = _html_anchor(entity.entity_id)
            label = f"[{entity.index}] {entity.label}"
            print("-", _osc8_link(label, _file_uri(index_html, fragment=anchor), enabled=terminal_links))
    print(f"\n[artifact dir] {index_html.parent}")


def ask(args: argparse.Namespace) -> int:
    llm_callable = _offline_llm if args.offline else None
    retrieved_contexts, retrieval_latency_ms = _retrieved_contexts(args, args.question)
    payload = generate_rag_llm_answer(
        question=args.question,
        runtime_rows=_runtime_rows(args.runtime_answers),
        seed_rows=_load_seed_rows(args),
        top_k=args.top_k,
        llm_callable=llm_callable,
        key_file=args.key_file,
        debug_mode=args.debug,
        category=args.category,
        retrieved_contexts=retrieved_contexts,
        retrieval_backend=args.retriever,
        retrieval_latency_ms_override=retrieval_latency_ms,
    )
    visual_click_artifacts: dict[str, Any] | None = None
    visual_click_enabled = bool(args.visual_click or args.visual_click_dir or args.open_visual or args.open_visual_app)
    if visual_click_enabled:
        click_dir = args.visual_click_dir or Path("artifacts/visual_click") / datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
        visual_click_artifacts = build_visual_click_artifacts(payload, click_dir, focused_entity=args.inspect_entity)
        payload["visual_click_artifacts"] = visual_click_artifacts
        if args.open_visual_app:
            visual_click_artifacts["opened_app_mode"] = open_visual_app_window(Path(str(visual_click_artifacts["index_html"])))
        elif args.open_visual:
            webbrowser.open(Path(str(visual_click_artifacts["index_html"])).resolve().as_uri())
    if args.inspect_output:
        inspector_text = render_terminal_entity_inspector(
            payload,
            focused_entity=args.inspect_entity,
            hyperlinks=args.terminal_links,
        )
        args.inspect_output.parent.mkdir(parents=True, exist_ok=True)
        args.inspect_output.write_text(inspector_text, encoding="utf-8")
    if args.inspect_screenshot:
        inspector_text = render_terminal_entity_inspector(
            payload,
            focused_entity=args.inspect_entity,
            hyperlinks=False,
        )
        write_terminal_inspector_screenshot(inspector_text, args.inspect_screenshot)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        visual_index = Path(str(visual_click_artifacts["index_html"])) if visual_click_artifacts else None
        _print_answer(payload, visual_index_html=visual_index)
        if visual_click_artifacts:
            _print_visual_click_links(payload, visual_click_artifacts, terminal_links=True)
        if args.inspect:
            print()
            print(
                render_terminal_entity_inspector(
                    payload,
                    focused_entity=args.inspect_entity,
                    hyperlinks=args.terminal_links,
                )
            )
    return 0


def inspect_answer(args: argparse.Namespace) -> int:
    payload = json.loads(args.answer_json.read_text(encoding="utf-8"))
    inspector_text = render_terminal_entity_inspector(
        payload,
        focused_entity=args.entity,
        width=args.width,
        hyperlinks=args.terminal_links,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(inspector_text, encoding="utf-8")
    if args.screenshot:
        write_terminal_inspector_screenshot(inspector_text, args.screenshot)
    result = {
        "kind": "terminal_entity_inspector",
        "answer_json": str(args.answer_json),
        "output": str(args.output) if args.output else "",
        "screenshot": str(args.screenshot) if args.screenshot else "",
        "entity": args.entity or "",
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(inspector_text)
        if args.output:
            print(f"[saved] {args.output}")
        if args.screenshot:
            print(f"[screenshot] {args.screenshot}")
    return 0


def chat(args: argparse.Namespace) -> int:
    print("General RAG CLI chat. 종료: q / quit / exit")
    while True:
        try:
            question = input("\n질문> ").strip()
        except EOFError:
            print()
            break
        if question.lower() in {"q", "quit", "exit"}:
            break
        if not question:
            continue
        retrieved_contexts, retrieval_latency_ms = _retrieved_contexts(args, question)
        payload = generate_rag_llm_answer(
            question=question,
            runtime_rows=_runtime_rows(args.runtime_answers),
            seed_rows=_load_seed_rows(args),
            top_k=args.top_k,
            llm_callable=_offline_llm if args.offline else None,
            key_file=args.key_file,
            debug_mode=args.debug,
            retrieved_contexts=retrieved_contexts,
            retrieval_backend=args.retriever,
            retrieval_latency_ms_override=retrieval_latency_ms,
        )
        _print_answer(payload)
    return 0


def report(args: argparse.Namespace) -> int:
    if not args.pgvector_seed:
        raise ValueError("--pgvector-seed is required for report")
    result = build_rag_llm_answer_report(
        runtime_answers_path=args.runtime_answers,
        pgvector_seed_path=args.pgvector_seed,
        output_dir=args.output_dir,
        llm_callable=_offline_llm if args.offline else None,
        key_file=args.key_file,
        top_k=args.top_k,
        limit=args.limit,
    )
    payload = {
        "question_count": result.question_count,
        "screenshot_count": result.screenshot_count,
        "report_path": str(result.report_path),
        "responses_jsonl_path": str(result.responses_jsonl_path),
        "summary_json_path": str(result.summary_json_path),
        "screenshot_dir": str(result.screenshot_dir),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[보고서 생성 완료]")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def visual(args: argparse.Namespace) -> int:
    llm_callable = _offline_llm if args.offline else None
    retrieved_contexts, retrieval_latency_ms = _retrieved_contexts(args, args.question)
    answer_payload = generate_rag_llm_answer(
        question=args.question,
        runtime_rows=_runtime_rows(args.runtime_answers),
        seed_rows=_load_seed_rows(args),
        top_k=args.top_k,
        llm_callable=llm_callable,
        key_file=args.key_file,
        debug_mode=args.debug,
        category=args.category,
        retrieved_contexts=retrieved_contexts,
        retrieval_backend=args.retriever,
        retrieval_latency_ms_override=retrieval_latency_ms,
    )
    graph = build_visual_graph_payload(answer_payload, debug_mode=args.debug)
    html_path = write_visual_inspector_html(graph, args.output, debug_mode=args.debug)
    graph_path = args.graph_json or html_path.with_suffix(".visual_graph.json")
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload = {
        "html_path": str(html_path),
        "graph_json_path": str(graph_path),
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
        "contract_pass": answer_payload.get("contract_pass"),
        "requires_review": answer_payload.get("requires_review"),
        "llm_mode": answer_payload.get("llm", {}).get("mode"),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[RAG Visual Inspector 생성 완료]")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def visual_eval(args: argparse.Namespace) -> int:
    rows = read_jsonl(args.results_jsonl)
    graph = build_evaluation_overview_payload(rows, debug_mode=args.debug, max_questions=args.max_questions)
    html_path = write_visual_inspector_html(graph, args.output, debug_mode=args.debug)
    graph_path = args.graph_json or html_path.with_suffix(".visual_graph.json")
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = graph.get("summary", {})
    payload = {
        "html_path": str(html_path),
        "graph_json_path": str(graph_path),
        "question_count": summary.get("questionCount"),
        "contract_pass_count": summary.get("contractPassCount"),
        "failure_count": summary.get("failureCount"),
        "review_count": summary.get("reviewCount"),
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[RAG Evaluation Overview 생성 완료]")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def ontology_map(args: argparse.Namespace) -> int:
    payload = write_nodeprompt_ontology_map_png(args.output, graph_json=args.graph_json)
    if args.preview:
        write_preview_crop(args.output, args.preview)
        payload["preview"] = str(args.preview)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[NODEPROMPT-inspired Ontology Map 생성 완료]")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def wiki_export(args: argparse.Namespace) -> int:
    rows = read_jsonl(args.results_jsonl)
    graph = json.loads(args.graph_json.read_text(encoding="utf-8")) if args.graph_json else {}
    result = export_ontology_wiki(
        rows=rows,
        vault=args.vault,
        run_id=args.run_id,
        graph=graph,
        screenshot_paths=args.screenshot or [],
        cloud_manifest_url=args.cloud_manifest_url or "",
        dashboard_url=args.dashboard_url or "",
    )
    payload = result.to_payload()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[Ontology Obsidian Wiki Export 완료]")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _first_matching(files: list[Path], root: Path, predicate: Any) -> str | None:
    matches = sorted(path for path in files if predicate(path))
    if not matches:
        return None
    return _relative_to_root(matches[0], root)


def inspect_domain_directory(domain_dir: Path) -> dict[str, Any]:
    """Inspect a domain artifact directory and resolve CLI-targetable RAG files."""
    root = domain_dir.expanduser().resolve()
    display_root = domain_dir.expanduser().as_posix()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"domain directory not found: {domain_dir}")

    files = [path for path in root.rglob("*") if path.is_file()]
    suffix_counts: dict[str, int] = {}
    for path in files:
        suffix = path.suffix.lower().lstrip(".") or "no_suffix"
        suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1

    def name(path: Path) -> str:
        return path.name.lower()

    resolved = {
        "runtime_answers": _first_matching(
            files,
            root,
            lambda p: p.suffix.lower() == ".jsonl" and ("runtime" in name(p) or "answer" in name(p)),
        ),
        "pgvector_seed": _first_matching(
            files,
            root,
            lambda p: p.suffix.lower() == ".jsonl" and ("pgvector" in name(p) or "seed" in name(p)),
        ),
        "evaluation_results": _first_matching(
            files,
            root,
            lambda p: p.suffix.lower() == ".jsonl" and ("eval" in name(p) or "result" in name(p)),
        ),
        "visual_graph": _first_matching(
            files,
            root,
            lambda p: p.suffix.lower() == ".json" and ("visual" in name(p) or "graph" in name(p)),
        ),
        "domain_manifest": _first_matching(files, root, lambda p: p.name == "domain_manifest.json"),
    }

    image_files = [p for p in files if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    raw_table_files = [p for p in files if p.suffix.lower() in {".csv", ".parquet", ".xlsx"}]
    doc_files = [p for p in files if p.suffix.lower() in {".md", ".pdf", ".docx"}]

    fragmentation_signals: list[str] = []
    if len(suffix_counts) >= 2:
        fragmentation_signals.append("multiple_file_formats_detected")
    if raw_table_files:
        fragmentation_signals.append("raw_or_structured_tables_detected")
    if doc_files:
        fragmentation_signals.append("document_sources_detected")
    if resolved.get("evaluation_results"):
        fragmentation_signals.append("evaluation_results_cli_target_detected")
    if resolved.get("visual_graph"):
        fragmentation_signals.append("visual_graph_cli_target_detected")
    if resolved.get("runtime_answers") and resolved.get("pgvector_seed"):
        fragmentation_signals.append("ask_visual_cli_targets_detected")

    cli_targets = {
        "visual_eval": resolved.get("evaluation_results"),
        "wiki_export_results": resolved.get("evaluation_results"),
        "wiki_export_graph": resolved.get("visual_graph"),
        "ask_runtime_answers": resolved.get("runtime_answers"),
        "ask_pgvector_seed": resolved.get("pgvector_seed"),
    }

    return {
        "domain_dir": display_root,
        "total_files": len(files),
        "artifact_counts": dict(sorted(suffix_counts.items())),
        "resolved_artifacts": {key: value for key, value in resolved.items() if value},
        "sample_files": [_relative_to_root(path, root) for path in sorted(files)[:12]],
        "fragmentation_signals": fragmentation_signals,
        "cli_targets": {key: value for key, value in cli_targets.items() if value},
    }


def inspect_dir(args: argparse.Namespace) -> int:
    manifest = inspect_domain_directory(args.domain_dir)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print("[Domain Artifact Directory 검사 완료]")
        print(f"- domain_dir: {manifest['domain_dir']}")
        print(f"- total_files: {manifest['total_files']}")
        print("- artifact_counts:")
        for key, value in manifest["artifact_counts"].items():
            print(f"  - {key}: {value}")
        print("- resolved_artifacts:")
        for key, value in manifest["resolved_artifacts"].items():
            print(f"  - {key}: {value}")
        if args.output:
            print(f"- manifest_path: {args.output}")
    return 0


def _prompt_path(label: str, default: Path) -> Path:
    raw = input(f"? {label} [{default}]: ").strip()
    return Path(raw) if raw else default


def _prompt_yes_no(label: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    raw = input(f"? {label} ({suffix}): ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "예", "ㅇ", "네"}


def _artifact_path(domain_dir: Path, relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    return domain_dir.expanduser().resolve() / relative_path


def demo_wizard(args: argparse.Namespace) -> int:
    """Run a presentation-friendly interactive CLI workflow."""
    print("General-Purpose Ontology-Hybrid RAG CLI Demo")
    print("파편화된 DB/문서 디렉토리를 지정하면, CLI가 실행 가능한 artifact를 찾고 산출물을 생성합니다.\n")

    domain_dir = args.domain_dir
    output_dir = args.output_dir
    run_eval = True
    run_wiki = True
    if not args.yes:
        domain_dir = _prompt_path("Domain artifact directory", domain_dir)
        output_dir = _prompt_path("Output directory", output_dir)
        run_eval = _prompt_yes_no("Evaluation Overview HTML을 생성할까요?", True)
        run_wiki = _prompt_yes_no("Obsidian ontology wiki를 export할까요?", True)
        print()

    output_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"output_dir": output_dir.as_posix()}

    print("[Step 1] Directory 검사 및 CLI target 특정")
    manifest = inspect_domain_directory(domain_dir)
    manifest_path = output_dir / "domain_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload["domain_manifest"] = manifest_path.as_posix()
    print(f"- domain_dir: {manifest['domain_dir']}")
    print(f"- total_files: {manifest['total_files']}")
    print(f"- fragmentation_signals: {', '.join(manifest['fragmentation_signals']) or 'none'}")
    print("- resolved_artifacts:")
    for key, value in manifest["resolved_artifacts"].items():
        print(f"  - {key}: {value}")
    print(f"- manifest_path: {manifest_path}\n")

    results_path = _artifact_path(domain_dir, manifest.get("cli_targets", {}).get("visual_eval"))
    graph_path = _artifact_path(domain_dir, manifest.get("cli_targets", {}).get("wiki_export_graph"))

    generated_graph_path: Path | None = None
    if run_eval:
        print("[Step 2] Evaluation Overview 생성")
        if not results_path or not results_path.exists():
            print("- skip: evaluation_results artifact를 찾지 못했습니다.\n")
        else:
            rows = read_jsonl(results_path)
            graph = build_evaluation_overview_payload(rows, debug_mode=args.debug, max_questions=args.max_questions)
            html_path = output_dir / "evaluation_overview.html"
            write_visual_inspector_html(graph, html_path, debug_mode=args.debug)
            generated_graph_path = output_dir / "evaluation_overview.visual_graph.json"
            generated_graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            summary = graph.get("summary", {})
            payload["evaluation_overview"] = {
                "html_path": html_path.as_posix(),
                "graph_json_path": generated_graph_path.as_posix(),
                "question_count": summary.get("questionCount"),
                "contract_pass_count": summary.get("contractPassCount"),
                "review_count": summary.get("reviewCount"),
            }
            print(f"- html_path: {html_path}")
            print(f"- graph_json_path: {generated_graph_path}")
            print(f"- question_count: {summary.get('questionCount')}")
            print(f"- contract_pass_count: {summary.get('contractPassCount')}")
            print(f"- review_count: {summary.get('reviewCount')}\n")

    if run_wiki:
        print("[Step 3] Obsidian ontology wiki export")
        if not results_path or not results_path.exists():
            print("- skip: evaluation_results artifact를 찾지 못했습니다.\n")
        else:
            rows = read_jsonl(results_path)
            graph: dict[str, Any] = {}
            if graph_path and graph_path.exists():
                graph = json.loads(graph_path.read_text(encoding="utf-8"))
            elif generated_graph_path and generated_graph_path.exists():
                graph = json.loads(generated_graph_path.read_text(encoding="utf-8"))
            vault_path = output_dir / "OBYBK_RAG_Wiki"
            result = export_ontology_wiki(rows=rows, vault=vault_path, run_id=args.run_id, graph=graph)
            wiki_payload = result.to_payload()
            payload["wiki_export"] = wiki_payload
            print(f"- vault: {wiki_payload['vault']}")
            print(f"- index_note: {wiki_payload['index_note']}")
            print(f"- question_notes: {wiki_payload['question_notes']}")
            print(f"- entity_notes: {wiki_payload['entity_notes']}")
            print(f"- relation_notes: {wiki_payload['relation_notes']}\n")

    print("[완료] 다음에 확인할 파일")
    print(f"- {manifest_path}")
    if "evaluation_overview" in payload:
        print(f"- {payload['evaluation_overview']['html_path']}")
    if "wiki_export" in payload:
        print(f"- {payload['wiki_export']['index_note']}")

    if args.json:
        print("\n[JSON Summary]")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def agent_catalog(args: argparse.Namespace) -> int:
    payload = {
        "cmd": "python tools/scripts/rag/general_rag_cli.py",
        "run": "agent-run <tool> -- <args>",
        "native": NATIVE_AGENT_COMMANDS,
        "tools": {
            key: {"s": value["script"], "k": value["kind"], "d": value["desc"]}
            for key, value in sorted(AGENT_TOOL_REGISTRY.items())
        },
    }
    if args.compact:
        compact = {
            "cmd": payload["cmd"],
            "native": payload["native"],
            "run": payload["run"],
            "tools": {key: value["s"] for key, value in payload["tools"].items()},
        }
        print(json.dumps(compact, ensure_ascii=False, separators=(",", ":")))
    elif args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[Agent CLI Catalog]")
        print(f"- entry: {payload['cmd']}")
        print(f"- run external tool: {payload['run']}")
        print("- native:", ", ".join(NATIVE_AGENT_COMMANDS))
        print("- tools:")
        for key, value in payload["tools"].items():
            print(f"  - {key}: {value['d']} ({value['s']})")
    return 0


def agent_run(args: argparse.Namespace) -> int:
    tool = AGENT_TOOL_REGISTRY.get(args.tool)
    if not tool:
        print(json.dumps({"error": "unknown_tool", "tool": args.tool, "available": sorted(AGENT_TOOL_REGISTRY)}, ensure_ascii=False), file=sys.stderr)
        return 2
    passthrough = list(args.tool_args or [])
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    script = REPO_ROOT / tool["script"]
    if tool["kind"] == "ui":
        command = ["streamlit", "run", str(script), "--", *passthrough]
    else:
        command = [sys.executable, str(script), *passthrough]
    if args.print_only:
        print(json.dumps({"tool": args.tool, "command": command, "cwd": str(REPO_ROOT)}, ensure_ascii=False, indent=2))
        return 0
    completed = subprocess.run(command, cwd=REPO_ROOT)
    return int(completed.returncode)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect_sqlite(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def db_init(args: argparse.Namespace) -> int:
    if args.backend == "sqlite":
        conn = _connect_sqlite(args.db)
        conn.executescript(SQLITE_SCHEMA)
        conn.commit()
        conn.close()
        payload = {"backend": "sqlite", "db": str(args.db), "tables": DB_TABLES}
    else:
        schema_out = args.schema_out or Path("docs/sql/rag_store_postgres.sql")
        schema_out.parent.mkdir(parents=True, exist_ok=True)
        schema_out.write_text(POSTGRES_SCHEMA.strip() + "\n", encoding="utf-8")
        payload = {"backend": "postgres", "mode": "schema_only", "schema_out": str(schema_out), "dsn": args.dsn or ""}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[RAG Store 초기화 완료]")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def db_status(args: argparse.Namespace) -> int:
    if args.backend != "sqlite":
        payload = {"backend": "postgres", "status": "schema_only", "message": "live PostgreSQL connection is not required; use db-init --backend postgres --schema-out"}
    elif not args.db.exists():
        payload = {"backend": "sqlite", "db": str(args.db), "exists": False, "tables": {}}
    else:
        conn = _connect_sqlite(args.db)
        tables: dict[str, int] = {}
        for table in DB_TABLES:
            try:
                row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
                tables[table] = int(row["n"] if row else 0)
            except sqlite3.OperationalError:
                tables[table] = -1
        conn.close()
        payload = {"backend": "sqlite", "db": str(args.db), "exists": True, "tables": tables}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[RAG Store 상태]")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def _review_reason(row: dict[str, Any]) -> str:
    reasons: list[str] = []
    if not bool(row.get("contract_pass")):
        reasons.append("contract_failed")
    if bool(row.get("requires_review")):
        reasons.append("requires_review")
    gap_count = int(row.get("data_gap_count") or len(row.get("data_gaps") or []))
    if gap_count:
        reasons.append(f"data_gap_count={gap_count}")
    return ";".join(reasons) or "manual_review"


def db_load_eval(args: argparse.Namespace) -> int:
    if args.backend != "sqlite":
        print(json.dumps({"error": "postgres_load_not_implemented", "hint": "use db-init --backend postgres --schema-out for schema handoff"}, ensure_ascii=False), file=sys.stderr)
        return 2
    rows = read_jsonl(args.results_jsonl)
    conn = _connect_sqlite(args.db)
    conn.executescript(SQLITE_SCHEMA)
    now = _utc_now()
    conn.execute(
        "INSERT OR REPLACE INTO rag_runs(run_id, created_at, domain_dir, metadata_json) VALUES (?, COALESCE((SELECT created_at FROM rag_runs WHERE run_id=?), ?), ?, ?)",
        (args.run_id, args.run_id, now, args.domain_dir or "", json.dumps({"source": str(args.results_jsonl)}, ensure_ascii=False)),
    )
    conn.execute(
        "INSERT INTO rag_artifacts(run_id, kind, path, meta_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (args.run_id, "evaluation_results", str(args.results_jsonl), "{}", now),
    )
    review_count = 0
    for index, row in enumerate(rows, start=1):
        question_id = str(row.get("id") or row.get("question_id") or f"Q-{index:04d}")
        gap_count = int(row.get("data_gap_count") or len(row.get("data_gaps") or []))
        conn.execute(
            """
            INSERT OR REPLACE INTO rag_evaluation_questions(
              question_id, run_id, category, question, status, contract_pass, requires_review, llm_mode, data_gap_count, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question_id,
                args.run_id,
                str(row.get("category") or ""),
                str(row.get("question") or ""),
                str(row.get("status") or ""),
                1 if bool(row.get("contract_pass")) else 0,
                1 if bool(row.get("requires_review")) else 0,
                str(row.get("llm_mode") or row.get("llm", {}).get("mode") or ""),
                gap_count,
                json.dumps(row, ensure_ascii=False),
            ),
        )
        if bool(row.get("requires_review")) or not bool(row.get("contract_pass")):
            review_count += 1
            conn.execute(
                "INSERT INTO review_queue(run_id, question_id, reason, status, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (args.run_id, question_id, _review_reason(row), "open", json.dumps(row, ensure_ascii=False), now),
            )
    conn.commit()
    conn.close()
    payload = {"backend": "sqlite", "db": str(args.db), "run_id": args.run_id, "loaded_questions": len(rows), "review_items": review_count}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[Evaluation 결과 적재 완료]")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0



def pgvector_init(args: argparse.Namespace) -> int:
    payload = init_pgvector_schema(args.dsn or os.environ.get("DATABASE_URL", ""), table_name=args.table_name, vector_dim=args.vector_dim)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[pgvector schema initialized]")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def pgvector_load(args: argparse.Namespace) -> int:
    payload = load_pgvector_seed(
        args.dsn or os.environ.get("DATABASE_URL", ""),
        args.seed_jsonl,
        table_name=args.table_name,
        vector_dim=args.vector_dim,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[pgvector seed loaded]")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def pgvector_status_cmd(args: argparse.Namespace) -> int:
    payload = pgvector_status(args.dsn or os.environ.get("DATABASE_URL", ""), table_name=args.table_name).to_payload()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[pgvector status]")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def pgvector_search_cmd(args: argparse.Namespace) -> int:
    matches = search_pgvector(
        args.dsn or os.environ.get("DATABASE_URL", ""),
        args.question,
        table_name=args.table_name,
        top_k=args.top_k,
        vector_dim=args.vector_dim,
    )
    payload = {"backend": "pgvector", "table_name": args.table_name, "top_k": args.top_k, "matches": matches}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[pgvector search]")
        for match in matches:
            print(f"- {match.get('id')} score={match.get('score')} {str(match.get('content') or '')[:100]}")
    return 0



def _snippet_content(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text
    if args.file:
        return args.file.read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise ValueError("snippet content required: use --text, --file, or stdin")


def snippet_put(args: argparse.Namespace) -> int:
    content = _snippet_content(args)
    now = _utc_now()
    conn = _connect_sqlite(args.db)
    conn.executescript(SQLITE_SCHEMA)
    existing = conn.execute("SELECT created_at FROM agent_snippets WHERE key=?", (args.key,)).fetchone()
    created_at = str(existing["created_at"]) if existing else now
    conn.execute(
        """
        INSERT OR REPLACE INTO agent_snippets(key, title, content, tags, hit_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, COALESCE((SELECT hit_count FROM agent_snippets WHERE key=?), 0), ?, ?)
        """,
        (args.key, args.title or args.key, content, args.tags or "", args.key, created_at, now),
    )
    conn.commit()
    conn.close()
    payload = {"db": str(args.db), "key": args.key, "chars": len(content), "updated_at": now}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[snippet saved] {args.key} ({len(content)} chars)")
    return 0


def snippet_get(args: argparse.Namespace) -> int:
    conn = _connect_sqlite(args.db)
    conn.executescript(SQLITE_SCHEMA)
    row = conn.execute("SELECT * FROM agent_snippets WHERE key=?", (args.key,)).fetchone()
    if not row:
        conn.close()
        print(json.dumps({"error": "snippet_not_found", "key": args.key}, ensure_ascii=False), file=sys.stderr)
        return 2
    if not args.no_touch:
        conn.execute("UPDATE agent_snippets SET hit_count=hit_count+1 WHERE key=?", (args.key,))
        conn.commit()
    payload = dict(row)
    content = str(payload.get("content") or "")
    if args.max_chars and len(content) > args.max_chars:
        content = content[: args.max_chars] + "…"
    payload["content"] = content
    conn.close()
    if args.raw:
        print(content)
    elif args.compact:
        print(json.dumps({"k": args.key, "t": payload.get("title"), "c": content}, ensure_ascii=False, separators=(",", ":")))
    elif args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{args.key}] {payload.get('title')}")
        print(content)
    return 0


def snippet_list(args: argparse.Namespace) -> int:
    conn = _connect_sqlite(args.db)
    conn.executescript(SQLITE_SCHEMA)
    like = f"%{args.tag}%" if args.tag else "%"
    rows = [dict(row) for row in conn.execute("SELECT key, title, tags, hit_count, updated_at FROM agent_snippets WHERE tags LIKE ? ORDER BY key LIMIT ?", (like, args.limit)).fetchall()]
    conn.close()
    if args.compact:
        print(json.dumps({"snippets": [[row["key"], row["title"], row["tags"], row["hit_count"]] for row in rows]}, ensure_ascii=False, separators=(",", ":")))
    elif args.json:
        print(json.dumps({"db": str(args.db), "snippets": rows}, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(f"- {row['key']}: {row['title']} tags={row['tags']} hits={row['hit_count']}")
    return 0


def benchmark_polish(args: argparse.Namespace) -> int:
    script = TOOLS_SCRIPTS_DIR / "rag" / "finalize_benchmark_qa_pairs.py"
    command = [
        sys.executable,
        str(script),
        "--input-jsonl",
        str(args.input_jsonl),
        "--output-dir",
        str(args.output_dir),
        "--batch-size",
        str(args.batch_size),
    ]
    if args.key_file:
        command.extend(["--key-file", str(args.key_file)])
    if args.model:
        command.extend(["--model", args.model])
    if args.no_llm:
        command.append("--no-llm")
    if args.print_only:
        print(json.dumps({"command": command}, ensure_ascii=False, indent=2))
        return 0
    completed = subprocess.run(command, cwd=REPO_ROOT)
    return int(completed.returncode)


def snippet_delete(args: argparse.Namespace) -> int:
    conn = _connect_sqlite(args.db)
    conn.executescript(SQLITE_SCHEMA)
    cursor = conn.execute("DELETE FROM agent_snippets WHERE key=?", (args.key,))
    conn.commit()
    conn.close()
    payload = {"db": str(args.db), "key": args.key, "deleted": cursor.rowcount}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[snippet deleted] {args.key}: {cursor.rowcount}")
    return 0


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runtime-answers", required=True, type=Path, help="GraphRAG/runtime answer JSONL path")
    parser.add_argument("--pgvector-seed", type=Path, help="pgvector seed JSONL path. Required for --retriever local and report.")
    parser.add_argument("--retriever", choices=["local", "pgvector"], default="local", help="Retrieval backend for ask/chat/visual")
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""), help="PostgreSQL DSN for --retriever pgvector")
    parser.add_argument("--pgvector-table", default="obybk_rag_documents", help="PostgreSQL pgvector table name")
    parser.add_argument("--key-file", type=Path, default=Path("config/openai_api_key.local"), help="OpenAI-compatible key file. Ignored when --offline is set.")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--offline", action="store_true", help="Do not call a live LLM; use deterministic grounded fallback.")
    parser.add_argument("--debug", action="store_true", help="Include Answer Composer debug section inside generated answers when supported.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="General-purpose RAG CLI: ask questions, chat interactively, or create screenshot/Markdown reports.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect-dir",
        help="Inspect a domain artifact directory and resolve CLI-targetable RAG files.",
    )
    inspect_parser.add_argument("--domain-dir", required=True, type=Path, help="Domain artifact directory to inspect")
    inspect_parser.add_argument("--output", type=Path, help="Optional JSON manifest output path")
    inspect_parser.add_argument("--json", action="store_true")
    inspect_parser.set_defaults(func=inspect_dir)

    demo_parser = subparsers.add_parser(
        "demo-wizard",
        help="Run an interactive presentation demo: inspect directory, build overview, export wiki.",
    )
    demo_parser.add_argument("--domain-dir", type=Path, default=Path("sample_data/rag_visual_inspector"), help="Default domain artifact directory")
    demo_parser.add_argument("--output-dir", type=Path, default=Path("/tmp/obybk_cli_demo"), help="Default output directory")
    demo_parser.add_argument("--run-id", default="demo_run", help="Run identifier for wiki export")
    demo_parser.add_argument("--max-questions", type=int, default=120, help="Maximum per-question nodes to render")
    demo_parser.add_argument("--debug", action="store_true", help="Include debug-only overview metrics")
    demo_parser.add_argument("--yes", action="store_true", help="Skip prompts and accept defaults")
    demo_parser.add_argument("--json", action="store_true", help="Print JSON summary after the human-readable demo output")
    demo_parser.set_defaults(func=demo_wizard)

    catalog_parser = subparsers.add_parser("agent-catalog", help="Print a compact command catalog for LLM agents.")
    catalog_parser.add_argument("--compact", action="store_true", help="Print minimal JSON without whitespace")
    catalog_parser.add_argument("--json", action="store_true", help="Print detailed JSON catalog")
    catalog_parser.set_defaults(func=agent_catalog)

    agent_run_parser = subparsers.add_parser("agent-run", help="Run a registered helper script by compact tool id.")
    agent_run_parser.add_argument("tool", help="Tool id from agent-catalog")
    agent_run_parser.add_argument("tool_args", nargs=argparse.REMAINDER, help="Arguments passed after -- to the tool")
    agent_run_parser.add_argument("--print-only", action="store_true", help="Print command instead of executing")
    agent_run_parser.set_defaults(func=agent_run)

    db_init_parser = subparsers.add_parser("db-init", help="Initialize SQLite RAG store or write PostgreSQL schema handoff SQL.")
    db_init_parser.add_argument("--backend", choices=["sqlite", "postgres"], default="sqlite")
    db_init_parser.add_argument("--db", type=Path, default=Path("artifacts/obybk_rag.sqlite"), help="SQLite DB path")
    db_init_parser.add_argument("--schema-out", type=Path, help="PostgreSQL schema SQL output path")
    db_init_parser.add_argument("--dsn", help="Optional PostgreSQL DSN recorded in output only")
    db_init_parser.add_argument("--json", action="store_true")
    db_init_parser.set_defaults(func=db_init)

    db_status_parser = subparsers.add_parser("db-status", help="Show SQLite RAG store table counts or PostgreSQL schema handoff status.")
    db_status_parser.add_argument("--backend", choices=["sqlite", "postgres"], default="sqlite")
    db_status_parser.add_argument("--db", type=Path, default=Path("artifacts/obybk_rag.sqlite"), help="SQLite DB path")
    db_status_parser.add_argument("--json", action="store_true")
    db_status_parser.set_defaults(func=db_status)

    db_load_eval_parser = subparsers.add_parser("db-load-eval", help="Load evaluation JSONL into the SQLite RAG store.")
    db_load_eval_parser.add_argument("--backend", choices=["sqlite", "postgres"], default="sqlite")
    db_load_eval_parser.add_argument("--db", type=Path, default=Path("artifacts/obybk_rag.sqlite"), help="SQLite DB path")
    db_load_eval_parser.add_argument("--results-jsonl", required=True, type=Path, help="Evaluation result JSONL path")
    db_load_eval_parser.add_argument("--run-id", required=True, help="Run id for imported evaluation rows")
    db_load_eval_parser.add_argument("--domain-dir", help="Optional source domain directory label")
    db_load_eval_parser.add_argument("--json", action="store_true")
    db_load_eval_parser.set_defaults(func=db_load_eval)

    pgvector_init_parser = subparsers.add_parser("pgvector-init", help="Initialize live PostgreSQL/pgvector schema.")
    pgvector_init_parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""), help="PostgreSQL DSN")
    pgvector_init_parser.add_argument("--table-name", default="obybk_rag_documents")
    pgvector_init_parser.add_argument("--vector-dim", type=int, default=16)
    pgvector_init_parser.add_argument("--json", action="store_true")
    pgvector_init_parser.set_defaults(func=pgvector_init)

    pgvector_load_parser = subparsers.add_parser("pgvector-load", help="Load pgvector seed JSONL into live PostgreSQL/pgvector.")
    pgvector_load_parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""), help="PostgreSQL DSN")
    pgvector_load_parser.add_argument("--seed-jsonl", required=True, type=Path)
    pgvector_load_parser.add_argument("--table-name", default="obybk_rag_documents")
    pgvector_load_parser.add_argument("--vector-dim", type=int)
    pgvector_load_parser.add_argument("--json", action="store_true")
    pgvector_load_parser.set_defaults(func=pgvector_load)

    pgvector_status_parser = subparsers.add_parser("pgvector-status", help="Show live PostgreSQL/pgvector extension/table status.")
    pgvector_status_parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""), help="PostgreSQL DSN")
    pgvector_status_parser.add_argument("--table-name", default="obybk_rag_documents")
    pgvector_status_parser.add_argument("--json", action="store_true")
    pgvector_status_parser.set_defaults(func=pgvector_status_cmd)

    pgvector_search_parser = subparsers.add_parser("pgvector-search", help="Search live PostgreSQL/pgvector table with hash-vector query.")
    pgvector_search_parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""), help="PostgreSQL DSN")
    pgvector_search_parser.add_argument("--question", required=True)
    pgvector_search_parser.add_argument("--table-name", default="obybk_rag_documents")
    pgvector_search_parser.add_argument("--top-k", type=int, default=3)
    pgvector_search_parser.add_argument("--vector-dim", type=int)
    pgvector_search_parser.add_argument("--json", action="store_true")
    pgvector_search_parser.set_defaults(func=pgvector_search_cmd)

    snippet_put_parser = subparsers.add_parser("snippet-put", help="Store reusable prompt/context text in the SQLite RAG store.")
    snippet_put_parser.add_argument("--db", type=Path, default=Path("artifacts/obybk_rag.sqlite"))
    snippet_put_parser.add_argument("--key", required=True)
    snippet_put_parser.add_argument("--title")
    snippet_put_parser.add_argument("--tags", default="")
    snippet_put_parser.add_argument("--text")
    snippet_put_parser.add_argument("--file", type=Path)
    snippet_put_parser.add_argument("--json", action="store_true")
    snippet_put_parser.set_defaults(func=snippet_put)

    snippet_get_parser = subparsers.add_parser("snippet-get", help="Fetch reusable prompt/context text by key.")
    snippet_get_parser.add_argument("--db", type=Path, default=Path("artifacts/obybk_rag.sqlite"))
    snippet_get_parser.add_argument("--key", required=True)
    snippet_get_parser.add_argument("--max-chars", type=int, default=0)
    snippet_get_parser.add_argument("--raw", action="store_true")
    snippet_get_parser.add_argument("--compact", action="store_true")
    snippet_get_parser.add_argument("--no-touch", action="store_true", help="Do not increment hit_count")
    snippet_get_parser.add_argument("--json", action="store_true")
    snippet_get_parser.set_defaults(func=snippet_get)

    snippet_list_parser = subparsers.add_parser("snippet-list", help="List reusable prompt/context snippets.")
    snippet_list_parser.add_argument("--db", type=Path, default=Path("artifacts/obybk_rag.sqlite"))
    snippet_list_parser.add_argument("--tag")
    snippet_list_parser.add_argument("--limit", type=int, default=50)
    snippet_list_parser.add_argument("--compact", action="store_true")
    snippet_list_parser.add_argument("--json", action="store_true")
    snippet_list_parser.set_defaults(func=snippet_list)

    snippet_delete_parser = subparsers.add_parser("snippet-delete", help="Delete a reusable prompt/context snippet.")
    snippet_delete_parser.add_argument("--db", type=Path, default=Path("artifacts/obybk_rag.sqlite"))
    snippet_delete_parser.add_argument("--key", required=True)
    snippet_delete_parser.add_argument("--json", action="store_true")
    snippet_delete_parser.set_defaults(func=snippet_delete)

    ask_parser = subparsers.add_parser("ask", help="Ask one question and print a grounded RAG answer.")
    add_common(ask_parser)
    ask_parser.add_argument("--question", required=True)
    ask_parser.add_argument("--category", help="Optional question category used by AnswerProfile intent routing.")
    ask_parser.add_argument("--inspect", action="store_true", help="Print a browserless terminal entity inspector after the answer")
    ask_parser.add_argument("--inspect-entity", help="Entity number/id to focus in the terminal inspector popup")
    ask_parser.add_argument("--inspect-output", type=Path, help="Optional text output path for terminal inspector")
    ask_parser.add_argument("--inspect-screenshot", type=Path, help="Optional PNG screenshot path for terminal inspector")
    ask_parser.add_argument("--visual-click", action="store_true", help="Generate clickable NODEPROMPT-style ontology visual artifacts and print terminal links")
    ask_parser.add_argument("--visual-click-dir", type=Path, help="Output directory for clickable ontology visual artifacts")
    ask_parser.add_argument("--open-visual", action="store_true", help="Open the clickable ontology visual index in the default browser")
    ask_parser.add_argument("--open-visual-app", action="store_true", help="Open the visual index in app/window mode without tabs or address bar when supported")
    ask_parser.add_argument("--terminal-links", action="store_true", help="Render OSC-8 terminal hyperlinks for entity labels")
    ask_parser.add_argument("--json", action="store_true")
    ask_parser.set_defaults(func=ask)

    chat_parser = subparsers.add_parser("chat", help="Interactive terminal RAG Q&A.")
    add_common(chat_parser)
    chat_parser.set_defaults(func=chat)

    report_parser = subparsers.add_parser("report", help="Generate per-question RAG answer Markdown report and screenshots.")
    add_common(report_parser)
    report_parser.add_argument("--output-dir", required=True, type=Path)
    report_parser.add_argument("--limit", type=int)
    report_parser.add_argument("--json", action="store_true")
    report_parser.set_defaults(func=report)

    visual_parser = subparsers.add_parser("visual", help="Generate a single-answer RAG Visual Inspector HTML/SVG artifact.")
    add_common(visual_parser)
    visual_parser.add_argument("--question", required=True)
    visual_parser.add_argument("--category", help="Optional question category used by AnswerProfile intent routing.")
    visual_parser.add_argument("--output", required=True, type=Path, help="Output HTML path")
    visual_parser.add_argument("--graph-json", type=Path, help="Optional output JSON path for VisualGraphPayload")
    visual_parser.add_argument("--json", action="store_true")
    visual_parser.set_defaults(func=visual)

    visual_eval_parser = subparsers.add_parser("visual-eval", help="Generate a RAG 100-QA Evaluation Overview HTML/SVG artifact.")
    visual_eval_parser.add_argument("--results-jsonl", required=True, type=Path, help="Evaluation result JSONL path")
    visual_eval_parser.add_argument("--output", required=True, type=Path, help="Output HTML path")
    visual_eval_parser.add_argument("--graph-json", type=Path, help="Optional output JSON path for evaluation VisualGraphPayload")
    visual_eval_parser.add_argument("--max-questions", type=int, default=120, help="Maximum per-question nodes to render")
    visual_eval_parser.add_argument("--debug", action="store_true", help="Include debug-only overview metrics")
    visual_eval_parser.add_argument("--json", action="store_true")
    visual_eval_parser.set_defaults(func=visual_eval)

    ontology_map_parser = subparsers.add_parser("ontology-map", help="Generate a NODEPROMPT-inspired radial ontology/evidence graph PNG artifact.")
    ontology_map_parser.add_argument("--output", required=True, type=Path, help="Output PNG path")
    ontology_map_parser.add_argument("--graph-json", type=Path, help="Optional ontology map JSON output path")
    ontology_map_parser.add_argument("--preview", type=Path, help="Optional mobile-friendly preview crop path")
    ontology_map_parser.add_argument("--json", action="store_true")
    ontology_map_parser.set_defaults(func=ontology_map)

    benchmark_polish_parser = subparsers.add_parser("benchmark-polish", help="Polish 100 QA pairs into the general RAG/GraphRAG inspection benchmark format.")
    benchmark_polish_parser.add_argument("--input-jsonl", required=True, type=Path, help="Input QA JSONL path")
    benchmark_polish_parser.add_argument("--output-dir", required=True, type=Path, help="Output directory for final md/jsonl/csv/report")
    benchmark_polish_parser.add_argument("--batch-size", type=int, default=10)
    benchmark_polish_parser.add_argument("--key-file", type=Path, default=Path("config/openai_api_key.local"), help="OpenAI-compatible key file for live polish")
    benchmark_polish_parser.add_argument("--model")
    benchmark_polish_parser.add_argument("--no-llm", action="store_true", help="Normalize/lint already revised rows without a live LLM call")
    benchmark_polish_parser.add_argument("--print-only", action="store_true", help="Print the delegated command instead of executing")
    benchmark_polish_parser.set_defaults(func=benchmark_polish)

    wiki_export_parser = subparsers.add_parser("wiki-export", help="Export ontology-tagged Obsidian wiki notes from RAG evaluation results.")
    wiki_export_parser.add_argument("--results-jsonl", required=True, type=Path, help="Evaluation result JSONL path")
    wiki_export_parser.add_argument("--graph-json", type=Path, help="Optional VisualGraphPayload JSON for entity/relation extraction")
    wiki_export_parser.add_argument("--vault", required=True, type=Path, help="Output Obsidian vault path")
    wiki_export_parser.add_argument("--run-id", required=True, help="Run identifier used in notes and backlinks")
    wiki_export_parser.add_argument("--screenshot", action="append", type=Path, help="Optional screenshot asset path. Can be provided multiple times.")
    wiki_export_parser.add_argument("--cloud-manifest-url", help="Optional GCS/Cloud manifest URL recorded in run note frontmatter")
    wiki_export_parser.add_argument("--dashboard-url", help="Optional Cloud dashboard URL recorded in run note frontmatter")
    wiki_export_parser.add_argument("--json", action="store_true")
    wiki_export_parser.set_defaults(func=wiki_export)

    inspect_answer_parser = subparsers.add_parser("inspect-answer", help="Render a browserless terminal entity inspector from an answer payload JSON.")
    inspect_answer_parser.add_argument("--answer-json", required=True, type=Path, help="RAG answer payload JSON path")
    inspect_answer_parser.add_argument("--entity", help="Entity number/id to focus in the popup panel")
    inspect_answer_parser.add_argument("--output", type=Path, help="Optional inspector text output path")
    inspect_answer_parser.add_argument("--screenshot", type=Path, help="Optional PNG screenshot output path")
    inspect_answer_parser.add_argument("--width", type=int, default=112, help="Terminal render width")
    inspect_answer_parser.add_argument("--terminal-links", action="store_true", help="Render OSC-8 terminal hyperlinks for entity labels")
    inspect_answer_parser.add_argument("--json", action="store_true")
    inspect_answer_parser.set_defaults(func=inspect_answer)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
