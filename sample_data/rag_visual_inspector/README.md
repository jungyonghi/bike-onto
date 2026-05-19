# Timestamp: 2026-05-19 12:06:00

# RAG Visual Inspector Sample Data

GitHub 공개/부트캠프 데모용 소형 샘플 데이터입니다.

## Files

- `domain_manifest.json`: `inspect-dir`가 생성한 domain artifact directory manifest 샘플
- `sample_eval_results.jsonl`: `general_rag_cli.py visual-eval` / `wiki-export` 재현용 4문항 평가 결과 샘플
- `sample_visual_graph.json`: ontology wiki export에서 entity/relation note를 생성하기 위한 소형 VisualGraphPayload 샘플

## Demo Command

```powershell
PS C:\Projects\obybk> .\tools\scripts\rag\demo_wizard.ps1

PS C:\Projects\obybk> .\venv\Scripts\python.exe tools\scripts\rag\general_rag_cli.py agent-catalog --compact

PS C:\Projects\obybk> .\venv\Scripts\python.exe tools\scripts\rag\general_rag_cli.py inspect-dir `
  --domain-dir sample_data\rag_visual_inspector `
  --output sample_data\rag_visual_inspector\domain_manifest.json `
  --json

PS C:\Projects\obybk> .\venv\Scripts\python.exe tools\scripts\rag\general_rag_cli.py visual-eval `
  --results-jsonl sample_data\rag_visual_inspector\sample_eval_results.jsonl `
  --output C:\Temp\obybk_sample_eval_overview.html `
  --json

PS C:\Projects\obybk> .\venv\Scripts\python.exe tools\scripts\rag\general_rag_cli.py wiki-export `
  --results-jsonl sample_data\rag_visual_inspector\sample_eval_results.jsonl `
  --graph-json sample_data\rag_visual_inspector\sample_visual_graph.json `
  --vault C:\Temp\OBYBK_RAG_Wiki `
  --run-id sample_eval_run `
  --json

PS C:\Projects\obybk> .\venv\Scripts\python.exe tools\scripts\rag\general_rag_cli.py db-init `
  --backend sqlite `
  --db C:\Temp\obybk_rag.sqlite `
  --json

PS C:\Projects\obybk> .\venv\Scripts\python.exe tools\scripts\rag\general_rag_cli.py db-load-eval `
  --backend sqlite `
  --db C:\Temp\obybk_rag.sqlite `
  --results-jsonl sample_data\rag_visual_inspector\sample_eval_results.jsonl `
  --run-id sample_eval_run `
  --json

PS C:\Projects\obybk> .\venv\Scripts\python.exe tools\scripts\rag\general_rag_cli.py workspace-manifest `
  --artifact-dir C:\Temp\OBYBK_RAG_Wiki `
  --output C:\Temp\OBYBK_RAG_Wiki\workspace_manifest.json `
  --run-id sample_eval_run `
  --drive-folder-id GOOGLE_DRIVE_FOLDER_ID `
  --json

PS C:\Projects\obybk> .\venv\Scripts\python.exe tools\scripts\rag\general_rag_cli.py workspace-calendar-test `
  --provider gws `
  --calendar your_account@example.com `
  --summary "OBYBK gws 일정 테스트" `
  --start 2026-05-20T09:00:00 `
  --duration-min 30 `
  --json

PS C:\Projects\obybk> .\venv\Scripts\python.exe tools\scripts\rag\general_rag_cli.py snippet-put `
  --db C:\Temp\obybk_rag.sqlite `
  --key workspace.calendar.test `
  --tags "workspace,calendar" `
  --text "workspace-calendar-test --provider gws --calendar <email> --summary <title> --start <iso> --duration-min 30" `
  --json
```
