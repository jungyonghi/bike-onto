# Timestamp: 2026-05-19 14:06:00

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


TOOLS_DIR = Path(__file__).resolve().parents[1]
CLI_PATH = TOOLS_DIR / "scripts" / "rag" / "general_rag_cli.py"
sys.path.insert(0, str(TOOLS_DIR / "scripts"))

from rag.obsidian_wiki_export import export_ontology_wiki  # noqa: E402
from rag.pgvector_integration_pack import build_pgvector_integration_pack  # noqa: E402


def _write_evaluation_results(path: Path) -> None:
    rows = [
        {
            "id": "Q-001",
            "question": "운영 이상 징후는?",
            "answer": "충무로역 3.4호선 (ST-152)를 우선 확인합니다.",
            "category": "운영 모니터링",
            "status": "ok",
            "contract_pass": True,
            "requires_review": False,
            "llm_mode": "live",
            "data_gap_count": 1,
            "quality_guard_notes": [],
            "first_candidates": [{"candidate_id": "station:152", "rank": 1}],
            "top_ids": ["ST-152"],
        },
        {
            "id": "Q-002",
            "question": "API 지연 상태는?",
            "category": "API/성능",
            "status": "error",
            "contract_pass": False,
            "requires_review": True,
            "llm_mode": "fallback_parse_error",
            "data_gap_count": 2,
            "quality_guard_notes": ["profile_specific_guard"],
        },
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _write_visual_graph(path: Path) -> None:
    graph = {
        "kind": "evaluation_overview",
        "title": "RAG Evaluation Overview",
        "summary": {"questionCount": 2},
        "nodes": [
            {"id": "entity:station-152", "type": "entity", "label": "충무로역 3.4호선 (ST-152)", "metadata": {"id": "station:152", "type": "Station"}},
            {"id": "relation:1", "type": "relation", "label": "대상 대여소", "metadata": {"relation": "forStation"}},
            {"id": "category:operation", "type": "category_cluster", "label": "운영 모니터링 (1)", "metadata": {"category": "운영 모니터링"}},
        ],
        "edges": [{"source": "relation:1", "target": "entity:station-152", "label": "대상 대여소", "relationType": "uses"}],
    }
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_runtime_answers(path: Path) -> None:
    rows = [
        {
            "question_id": "Q-001",
            "question": "어떤 후보를 먼저 검토해야 하는가?",
            "answer": "entity:alpha와 entity:beta를 후보로 검토한다.",
            "evidence_documents": ["docs/source.md"],
            "related_objects": [
                {"type": "Entity", "id": "entity:alpha", "label": "Alpha"},
                {"type": "Entity", "id": "entity:beta", "label": "Beta"},
            ],
            "related_relations": [{"source": "Metric", "relation": "FOR_ENTITY", "target": "Entity"}],
            "recommended_actions": [{"type": "ReviewAction", "summary": "후보 검토"}],
            "requires_review": True,
            "contract_pass": True,
            "graph_metrics": {"entity_sample_preview": ["entity:alpha", "entity:beta"], "metric_count": 2},
        }
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _run_cli(args: list[str], *, input_text: str | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(CLI_PATH), *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
        cwd=TOOLS_DIR.parents[0],
        env=merged_env,
    )


def test_general_rag_cli_inspect_dir_resolves_cli_targetable_artifacts(tmp_path: Path) -> None:
    results_path = tmp_path / "eval_results.jsonl"
    graph_path = tmp_path / "overview_graph.json"
    manifest_path = tmp_path / "domain_manifest.json"
    _write_evaluation_results(results_path)
    _write_visual_graph(graph_path)
    (tmp_path / "raw_table.csv").write_text("id,value\n1,alpha\n", encoding="utf-8")

    result = _run_cli(
        [
            "inspect-dir",
            "--domain-dir",
            str(tmp_path),
            "--output",
            str(manifest_path),
            "--json",
        ]
    )

    payload = json.loads(result.stdout)
    assert payload["total_files"] >= 3
    assert payload["resolved_artifacts"]["evaluation_results"] == "eval_results.jsonl"
    assert payload["resolved_artifacts"]["visual_graph"] == "overview_graph.json"
    assert payload["artifact_counts"]["jsonl"] == 1
    assert "multiple_file_formats_detected" in payload["fragmentation_signals"]
    assert manifest_path.exists()


def test_general_rag_cli_demo_wizard_prompts_and_creates_artifacts(tmp_path: Path) -> None:
    results_path = tmp_path / "eval_results.jsonl"
    graph_path = tmp_path / "overview_graph.json"
    output_dir = tmp_path / "demo_output"
    _write_evaluation_results(results_path)
    _write_visual_graph(graph_path)

    result = _run_cli(
        ["demo-wizard", "--run-id", "demo_run"],
        input_text=f"{tmp_path}\n{output_dir}\ny\ny\n",
    )

    assert "? Domain artifact directory" in result.stdout
    assert "[Step 1] Directory 검사" in result.stdout
    assert "[Step 2] Evaluation Overview 생성" in result.stdout
    assert "[Step 3] Obsidian ontology wiki export" in result.stdout
    assert (output_dir / "domain_manifest.json").exists()
    assert (output_dir / "evaluation_overview.html").exists()
    assert (output_dir / "OBYBK_RAG_Wiki" / "00_Index.md").exists()


def test_general_rag_cli_cli_examples_exports_markdown_csv_and_screenshot(tmp_path: Path) -> None:
    md_path = tmp_path / "cli_examples.md"
    csv_path = tmp_path / "cli_examples.csv"
    png_path = tmp_path / "cli_examples.png"

    result = _run_cli(
        [
            "cli-examples",
            "--format",
            "md",
            "--output",
            str(md_path),
            "--csv-output",
            str(csv_path),
            "--screenshot",
            str(png_path),
            "--json-summary",
        ]
    )

    payload = json.loads(result.stdout)
    assert payload["count"] >= 5
    assert md_path.exists()
    assert csv_path.exists()
    assert png_path.exists()
    assert "Benchmark polish" in md_path.read_text(encoding="utf-8")
    assert "workflow,command,purpose,save_as" in csv_path.read_text(encoding="utf-8").splitlines()[0]


def test_general_rag_cli_agent_catalog_and_print_only_runner() -> None:
    catalog_result = _run_cli(["agent-catalog", "--compact"])
    catalog = json.loads(catalog_result.stdout)
    assert "demo-wizard" in catalog["native"]
    assert "ontology-map" in catalog["native"]
    assert "inspect-answer" in catalog["native"]
    assert "benchmark-polish" in catalog["native"]
    assert "pgpack" in catalog["tools"]

    run_result = _run_cli(["agent-run", "--print-only", "pgpack", "--", "--help"])
    run_payload = json.loads(run_result.stdout)
    assert run_payload["tool"] == "pgpack"
    assert "pgvector_integration_pack.py" in " ".join(run_payload["command"])


def test_general_rag_cli_benchmark_polish_no_llm_writes_final_outputs(tmp_path: Path) -> None:
    input_jsonl = tmp_path / "revised_qa.jsonl"
    output_dir = tmp_path / "benchmark"
    rows = []
    for index in range(1, 51):
        rows.append(
            {
                "qid": f"QP{index:02d}",
                "question_group": "QP",
                "question": f"실행형 질의 {index}",
                "answer": "COUNT(*) 또는 GROUP BY로 산출 방식을 설명한다.",
                "answerability": "executable-with-data",
                "evidence_sources": ["fact.parquet"],
                "requires_review": False,
                "review_reason": "not required",
            }
        )
    for index in range(1, 51):
        rows.append(
            {
                "qid": f"QO{index:02d}",
                "question_group": "QO",
                "question": f"검토형 질의 {index}",
                "answer": "파생 지표와 baseline, 임계치를 정의한 뒤 근거를 분리해 산출한다.",
                "answerability": "needs-metric-definition",
                "evidence_sources": ["fact.parquet", "ontology-lite"],
                "requires_review": True,
                "review_reason": "파생 지표의 산식과 임계치가 고정되어야 결과가 재현된다.",
            }
        )
    input_jsonl.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    result = _run_cli(
        [
            "benchmark-polish",
            "--input-jsonl",
            str(input_jsonl),
            "--output-dir",
            str(output_dir),
            "--no-llm",
        ]
    )

    assert result.returncode == 0
    markdown = output_dir / "llm_qa_pairs_100_final.md"
    assert markdown.exists()
    text = markdown.read_text(encoding="utf-8")
    assert "## 001. QP01" in text
    assert "## 100. QO50" in text
    assert "- answerability: executable-with-data" in text
    assert "- review_reason: not required" not in text


def test_general_rag_cli_sqlite_store_loads_evaluation_results(tmp_path: Path) -> None:
    results_path = tmp_path / "eval_results.jsonl"
    db_path = tmp_path / "rag_store.sqlite"
    _write_evaluation_results(results_path)

    init_result = _run_cli(["db-init", "--backend", "sqlite", "--db", str(db_path), "--json"])
    init_payload = json.loads(init_result.stdout)
    assert init_payload["backend"] == "sqlite"
    assert db_path.exists()

    load_result = _run_cli(
        [
            "db-load-eval",
            "--backend",
            "sqlite",
            "--db",
            str(db_path),
            "--results-jsonl",
            str(results_path),
            "--run-id",
            "test_run",
            "--json",
        ]
    )
    load_payload = json.loads(load_result.stdout)
    assert load_payload["loaded_questions"] == 2
    assert load_payload["review_items"] == 1

    status_result = _run_cli(["db-status", "--backend", "sqlite", "--db", str(db_path), "--json"])
    status_payload = json.loads(status_result.stdout)
    assert status_payload["tables"]["rag_evaluation_questions"] == 2
    assert status_payload["tables"]["review_queue"] == 1


def test_general_rag_cli_postgres_schema_handoff(tmp_path: Path) -> None:
    schema_path = tmp_path / "rag_store_postgres.sql"
    result = _run_cli(["db-init", "--backend", "postgres", "--schema-out", str(schema_path), "--json"])
    payload = json.loads(result.stdout)
    assert payload["backend"] == "postgres"
    assert schema_path.exists()
    assert "JSONB" in schema_path.read_text(encoding="utf-8")





def test_general_rag_cli_snippet_store_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "rag_store.sqlite"
    put_result = _run_cli(
        [
            "snippet-put",
            "--db",
            str(db_path),
            "--key",
            "rag.snippet.template",
            "--title",
            "RAG Snippet Template",
            "--tags",
            "rag,powershell",
            "--text",
            "PowerShell RAG CLI reusable template",
            "--json",
        ]
    )
    put_payload = json.loads(put_result.stdout)
    assert put_payload["key"] == "rag.snippet.template"

    get_result = _run_cli(["snippet-get", "--db", str(db_path), "--key", "rag.snippet.template", "--compact"])
    get_payload = json.loads(get_result.stdout)
    assert get_payload["k"] == "rag.snippet.template"
    assert "PowerShell RAG" in get_payload["c"]

    list_result = _run_cli(["snippet-list", "--db", str(db_path), "--tag", "rag", "--compact"])
    list_payload = json.loads(list_result.stdout)
    assert list_payload["snippets"][0][0] == "rag.snippet.template"


def test_general_rag_cli_setup_status_and_zero_arg_chat(tmp_path: Path) -> None:
    env = {"BIKE_ONTO_HOME": str(tmp_path / ".bike-onto")}

    setup_result = _run_cli(["setup", "--yes", "--offline", "--json"], env=env)
    setup_payload = json.loads(setup_result.stdout)
    assert setup_payload["configured"] is True
    assert setup_payload["llm_mode"] == "offline"
    assert Path(setup_payload["config_path"]).exists()

    status_result = _run_cli(["status", "--json"], env=env)
    status_payload = json.loads(status_result.stdout)
    assert status_payload["configured"] is True
    assert status_payload["llm_mode"] == "offline"

    chat_result = _run_cli([], input_text="오늘 먼저 확인해야 할 대상은?\nq\n", env=env)
    assert "Bike Onto chat" in chat_result.stdout
    assert "[답변]" in chat_result.stdout
    assert "충무로역" in chat_result.stdout


def test_general_rag_cli_ask_positional_question_uses_demo_fixture_without_long_flags() -> None:
    result = _run_cli(["ask", "오늘 먼저 확인해야 할 대상은?", "--offline"])

    assert "[질의]" in result.stdout
    assert "[답변]" in result.stdout
    assert "충무로역" in result.stdout
    assert "[정량 지표]" not in result.stdout


def test_general_rag_cli_ask_outputs_grounded_answer_json(tmp_path: Path) -> None:
    runtime_answers = tmp_path / "runtime.jsonl"
    _write_runtime_answers(runtime_answers)
    pg_pack = build_pgvector_integration_pack(runtime_answers, tmp_path / "pgvector", vector_dim=8)

    result = _run_cli(
        [
            "ask",
            "--runtime-answers",
            str(runtime_answers),
            "--pgvector-seed",
            str(pg_pack.seed_jsonl_path),
            "--question",
            "어떤 후보를 먼저 검토해야 하는가?",
            "--offline",
            "--json",
        ]
    )

    payload = json.loads(result.stdout)
    assert payload["mode"] == "rag_llm"
    assert payload["llm"]["mode"] == "offline_cli"
    assert "답변" in payload["answer"] or "RAG" in payload["answer"]
    assert payload["candidate_set"]
    assert payload["evidence_excerpt_list"]


def test_general_rag_cli_nodeprompt_ontology_map_creates_png_and_json(tmp_path: Path) -> None:
    output = tmp_path / "ontology_map.png"
    graph_json = tmp_path / "ontology_map.json"
    preview = tmp_path / "ontology_map_preview.jpg"

    result = _run_cli(
        [
            "ontology-map",
            "--output",
            str(output),
            "--graph-json",
            str(graph_json),
            "--preview",
            str(preview),
            "--json",
        ]
    )

    payload = json.loads(result.stdout)
    assert payload["kind"] == "nodeprompt_inspired_ontology_map"
    assert payload["node_count"] >= 30
    assert payload["edge_count"] >= 40
    assert output.exists() and output.stat().st_size > 1000
    assert graph_json.exists()
    assert preview.exists() and preview.stat().st_size > 1000


def test_general_rag_cli_ask_visual_click_creates_clickable_ontology_artifacts(tmp_path: Path) -> None:
    runtime_answers = tmp_path / "runtime.jsonl"
    _write_runtime_answers(runtime_answers)
    pg_pack = build_pgvector_integration_pack(runtime_answers, tmp_path / "pgvector", vector_dim=8)
    click_dir = tmp_path / "visual_click"

    result = _run_cli(
        [
            "ask",
            "--runtime-answers",
            str(runtime_answers),
            "--pgvector-seed",
            str(pg_pack.seed_jsonl_path),
            "--question",
            "어떤 후보를 먼저 검토해야 하는가?",
            "--offline",
            "--visual-click",
            "--visual-click-dir",
            str(click_dir),
        ]
    )

    assert "[클릭 시각화]" in result.stdout
    assert "Open NODEPROMPT-style ontology map" in result.stdout
    assert (click_dir / "index.html").exists()
    index_html = (click_dir / "index.html").read_text(encoding="utf-8")
    assert "data-view=\"tree\"" in index_html
    assert "data-view=\"radial\"" in index_html
    assert "activateVisual" in index_html
    assert (click_dir / "nodeprompt_ontology_tree.png").exists()
    assert (click_dir / "nodeprompt_ontology_map.png").exists()
    assert (click_dir / "answer_visual_inspector.html").exists()
    assert "Entity click targets" in result.stdout


def test_general_rag_cli_terminal_entity_inspector_from_answer_payload(tmp_path: Path) -> None:
    runtime_answers = tmp_path / "runtime.jsonl"
    _write_runtime_answers(runtime_answers)
    pg_pack = build_pgvector_integration_pack(runtime_answers, tmp_path / "pgvector", vector_dim=8)
    answer_path = tmp_path / "answer.json"
    inspector_path = tmp_path / "inspector.txt"
    screenshot_path = tmp_path / "inspector.png"

    ask_result = _run_cli(
        [
            "ask",
            "--runtime-answers",
            str(runtime_answers),
            "--pgvector-seed",
            str(pg_pack.seed_jsonl_path),
            "--question",
            "어떤 후보를 먼저 검토해야 하는가?",
            "--offline",
            "--json",
        ]
    )
    answer_path.write_text(ask_result.stdout, encoding="utf-8")

    result = _run_cli(
        [
            "inspect-answer",
            "--answer-json",
            str(answer_path),
            "--entity",
            "1",
            "--output",
            str(inspector_path),
            "--screenshot",
            str(screenshot_path),
        ]
    )

    text = inspector_path.read_text(encoding="utf-8")
    assert "Terminal Entity Inspector" in result.stdout
    assert "Entity Popup" in text
    assert "Evidence" in text
    assert screenshot_path.exists()


def test_general_rag_cli_report_creates_markdown_and_screenshots(tmp_path: Path) -> None:
    runtime_answers = tmp_path / "runtime.jsonl"
    _write_runtime_answers(runtime_answers)
    pg_pack = build_pgvector_integration_pack(runtime_answers, tmp_path / "pgvector", vector_dim=8)
    output_dir = tmp_path / "report"

    result = _run_cli(
        [
            "report",
            "--runtime-answers",
            str(runtime_answers),
            "--pgvector-seed",
            str(pg_pack.seed_jsonl_path),
            "--output-dir",
            str(output_dir),
            "--offline",
            "--json",
        ]
    )

    payload = json.loads(result.stdout)
    assert payload["question_count"] == 1
    assert Path(payload["report_path"]).exists()
    assert len(list((output_dir / "screenshots").glob("*.png"))) == 1
    markdown = Path(payload["report_path"]).read_text(encoding="utf-8")
    assert "General RAG" in markdown
    assert "후보 목록" in markdown


def test_general_rag_cli_visual_creates_html_inspector(tmp_path: Path) -> None:
    runtime_answers = tmp_path / "runtime.jsonl"
    _write_runtime_answers(runtime_answers)
    pg_pack = build_pgvector_integration_pack(runtime_answers, tmp_path / "pgvector", vector_dim=8)
    output_path = tmp_path / "visual" / "inspector.html"

    result = _run_cli(
        [
            "visual",
            "--runtime-answers",
            str(runtime_answers),
            "--pgvector-seed",
            str(pg_pack.seed_jsonl_path),
            "--question",
            "어떤 후보를 먼저 검토해야 하는가?",
            "--output",
            str(output_path),
            "--offline",
            "--json",
        ]
    )

    payload = json.loads(result.stdout)
    assert Path(payload["html_path"]).exists()
    assert payload["node_count"] >= 5
    html = output_path.read_text(encoding="utf-8")
    assert "Answer Evidence Radial Graph" in html
    assert "<svg" in html
    assert "Operator Debug" not in html


def test_general_rag_cli_visual_eval_creates_evaluation_overview(tmp_path: Path) -> None:
    results_path = tmp_path / "eval_results.jsonl"
    _write_evaluation_results(results_path)
    output_path = tmp_path / "visual" / "evaluation_overview.html"

    result = _run_cli(
        [
            "visual-eval",
            "--results-jsonl",
            str(results_path),
            "--output",
            str(output_path),
            "--json",
        ]
    )

    payload = json.loads(result.stdout)
    assert Path(payload["html_path"]).exists()
    assert Path(payload["graph_json_path"]).exists()
    assert payload["question_count"] == 2
    assert payload["contract_pass_count"] == 1
    html = output_path.read_text(encoding="utf-8")
    assert "RAG Evaluation Overview" in html
    assert "Category Clusters" in html
    assert "운영 모니터링 (1)" in html
    assert "fallback_parse_error=1" in html


def test_general_rag_cli_wiki_export_creates_ontology_tagged_obsidian_vault(tmp_path: Path) -> None:
    results_path = tmp_path / "eval_results.jsonl"
    graph_path = tmp_path / "overview_graph.json"
    vault_path = tmp_path / "OBYBK_RAG_Wiki"
    _write_evaluation_results(results_path)
    _write_visual_graph(graph_path)

    result = _run_cli(
        [
            "wiki-export",
            "--results-jsonl",
            str(results_path),
            "--graph-json",
            str(graph_path),
            "--vault",
            str(vault_path),
            "--run-id",
            "test_run_live_100",
            "--json",
        ]
    )

    payload = json.loads(result.stdout)
    assert Path(payload["run_note"]).exists()
    assert payload["question_notes"] == 2
    assert payload["entity_notes"] >= 1
    assert payload["relation_notes"] >= 1
    assert (vault_path / "00_Index.md").exists()
    assert (vault_path / "03_Review_Queue" / "review_queue_test_run_live_100.md").exists()

    run_note = Path(payload["run_note"]).read_text(encoding="utf-8")
    assert "type: rag_run" in run_note
    assert "#rag/run/live" in run_note
    assert "[[review_queue_test_run_live_100]]" in run_note

    question_note = next((vault_path / "02_Evaluation" / "questions").glob("Q-001*.md")).read_text(encoding="utf-8")
    assert "ontology_type: Question" in question_note
    assert "#ontology/domain/station" in question_note
    assert "#relation/for-station" in question_note
    assert "#sim/question/monitoring" in question_note
    assert "[[충무로역 3.4호선 ST-152]]" in question_note

    entity_note_path = next((vault_path / "04_Entities" / "stations").glob("*ST-152*.md"))
    assert "충무로역 3.4호선" in entity_note_path.name
    entity_note = entity_note_path.read_text(encoding="utf-8")
    assert "type: entity" in entity_note
    assert "#entity/station/ST-152" in entity_note
    assert "station:152" in entity_note
    assert "[[Q-001" in entity_note


def test_wiki_export_prefers_human_title_from_answer_when_graph_has_only_id(tmp_path: Path) -> None:
    result = export_ontology_wiki(
        rows=[
            {
                "id": "Q-ROW-TITLE",
                "question": "자연어 엔티티 타이틀 확인",
                "answer": "후보는 충무로역 3.4호선 (ST-152)와 종로3가역 2번출구 뒤 (ST-150)입니다.",
                "category": "추천/재배치/우선순위",
                "contract_pass": True,
                "requires_review": False,
                "data_gap_count": 0,
                "llm_mode": "live",
                "first_candidates": [
                    {"candidate_id": "station:152"},
                    {"candidate_id": "station:150"},
                    {"candidate_id": "station:999", "display_name": "강남역 2번출구 대여소"},
                ],
                "top_ids": ["ST-152", "ST-150", "ST-999"],
            }
        ],
        vault=tmp_path / "wiki",
        run_id="human_title_run",
        graph={},
    )

    entity_names = sorted(path.name for path in result.entity_notes)
    assert "충무로역 3.4호선 ST-152.md" in entity_names
    assert "종로3가역 2번출구 뒤 ST-150.md" in entity_names
    assert "강남역 2번출구 대여소 ST-999.md" in entity_names
    question_note = result.question_notes[0].read_text(encoding="utf-8")
    assert "[[충무로역 3.4호선 ST-152]]" in question_note
    assert "[[종로3가역 2번출구 뒤 ST-150]]" in question_note



def test_general_rag_cli_chat_accepts_stdin_question(tmp_path: Path) -> None:
    runtime_answers = tmp_path / "runtime.jsonl"
    _write_runtime_answers(runtime_answers)
    pg_pack = build_pgvector_integration_pack(runtime_answers, tmp_path / "pgvector", vector_dim=8)

    result = _run_cli(
        [
            "chat",
            "--runtime-answers",
            str(runtime_answers),
            "--pgvector-seed",
            str(pg_pack.seed_jsonl_path),
            "--offline",
        ],
        input_text="어떤 후보를 먼저 검토해야 하는가?\nq\n",
    )

    assert "질문>" in result.stdout
    assert "[답변]" in result.stdout
    assert "[검토 필요]" in result.stdout
