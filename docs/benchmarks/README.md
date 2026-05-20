# Timestamp: 2026-05-19 22:35:00

# OBYBK Benchmarks

이 디렉토리는 OBYBK를 특정 도메인 챗봇이 아니라 **범용 RAG/GraphRAG 답변 검토 프레임워크**로 평가하기 위한 benchmark 문서를 보관한다.

## Benchmark Policy

OBYBK의 100 QA benchmark는 특정 도메인에 영구 고정된 질문 목록이 아니라, 도메인 artifact에서 생성되는 **versioned competency-question snapshot**이어야 한다.

```text
domain artifact directory
→ domain_manifest.json
→ LLM-generated QP/QO candidate questions
→ deterministic answerability/review-policy validation
→ frozen benchmark snapshot
→ visual-eval / wiki-export / profile comparison
```

자세한 정책:

```text
domain_generated_benchmark_policy.md
```

## Reference Snapshot

아래 파일은 Seoul Bike case-study binding으로 만든 reference snapshot이다. universal fixed benchmark가 아니라, framework의 expected benchmark shape을 보여주는 예시이자 regression fixture다.

```text
obybk_rag_graphrag_inspection_benchmark_100.md
obybk_rag_graphrag_inspection_benchmark_100.jsonl
obybk_rag_graphrag_inspection_benchmark_100.csv
obybk_rag_graphrag_inspection_benchmark_100_report.md
```

## Design Policy

- QP01~QP50: 해당 도메인의 원자료와 파라미터가 있으면 실행 가능한 데이터 분석 질의
- QO01~QO50: metric definition, schema confirmation, provenance, confidence, review gate가 필요한 inspection 질의
- `requires_review=True`는 단순히 현재 숫자를 실행하지 않았다는 뜻이 아니라, 사람 검토가 필요한 정의/스키마/임계치/추론 신뢰도 문제가 있다는 뜻이다.
- `ontology-lite`는 class/relation/provenance/confidence가 실제로 필요한 항목에만 evidence source로 둔다.

## Rebuild

이미 다듬어진 JSONL을 형식 검증/재출력만 하려면 live LLM 없이 실행한다.

```bash
venv/bin/python tools/scripts/rag/general_rag_cli.py benchmark-polish \
  --input-jsonl docs/qa/2026-05-19/llm_qa_pairs_100/llm_qa_pairs_100_final.jsonl \
  --output-dir /tmp/obybk_benchmark_polish_check \
  --no-llm
```

새 원본 QA를 자연스러운 benchmark 문체로 다시 쓰려면 `--no-llm`을 빼고 OpenAI-compatible key file을 제공한다.
