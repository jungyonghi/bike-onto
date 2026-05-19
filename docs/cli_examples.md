# CLI Examples

These examples are portfolio-friendly commands for the core OBYBK / Bike Onto workflow.

| Workflow | Command | Purpose | Save as |
|---|---|---|---|
| Ask like a chatbot | `python tools/scripts/rag/general_rag_cli.py ask "오늘 먼저 확인해야 할 대상은?" --offline` | Ask one question with the built-in demo fixture; no DB or long flags required. | Terminal answer |
| Inspect domain directory | `python tools/scripts/rag/general_rag_cli.py inspect-dir --domain-dir sample_data/rag_visual_inspector --output artifacts/domain_manifest.json --json` | Resolve runnable artifact paths from a fragmented domain folder. | JSON manifest |
| Evaluation overview | `python tools/scripts/rag/general_rag_cli.py visual-eval --results-jsonl sample_data/rag_visual_inspector/sample_eval_results.jsonl --output artifacts/evaluation_overview.html --graph-json artifacts/evaluation_overview.visual_graph.json --json` | Render the 100-QA inspection overview as a local HTML visual graph. | HTML + JSON |
| Obsidian wiki export | `python tools/scripts/rag/general_rag_cli.py wiki-export --results-jsonl sample_data/rag_visual_inspector/sample_eval_results.jsonl --graph-json sample_data/rag_visual_inspector/sample_visual_graph.json --vault artifacts/OBYBK_RAG_Wiki --run-id demo_run --json` | Project questions, entities, relations, and review queue into an Obsidian vault. | Markdown vault |
| Ontology map | `python tools/scripts/rag/general_rag_cli.py ontology-map --output artifacts/ontology_map.png --preview artifacts/ontology_map_preview.jpg --graph-json artifacts/ontology_map.json --json` | Create the NODEPROMPT-inspired ontology/evidence graph image. | PNG + JPG + JSON |
| Benchmark polish | `python tools/scripts/rag/general_rag_cli.py benchmark-polish --input-jsonl docs/benchmarks/obybk_rag_graphrag_inspection_benchmark_100.jsonl --output-dir artifacts/benchmark_check --no-llm` | Normalize/lint a domain QA snapshot with answerability and review policy. | MD + JSONL + CSV |
| CLI examples export | `python tools/scripts/rag/general_rag_cli.py cli-examples --format md --output docs/cli_examples.md --csv-output docs/cli_examples.csv --screenshot docs/assets/screenshots/cli_examples/cli_examples_export_screenshot.png` | Export this command catalog for README, submission notes, or reviewers. | MD + CSV + PNG |
