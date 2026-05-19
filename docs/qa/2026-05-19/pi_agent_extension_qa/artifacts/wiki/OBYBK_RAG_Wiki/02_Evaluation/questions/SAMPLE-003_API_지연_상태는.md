---
type: evaluation_question
run_id: pi_ext_qa_run
question_id: SAMPLE-003
category: "API/DB/성능"
contract_pass: true
requires_review: false
llm_mode: offline_cli
data_gap_count: 0
quality_guard_notes:
  - profile_specific_guard
ontology_type: Question
upper_concepts:
  - Event
  - Metric
domain_concepts:
  - Question
  - UsageMetric
  - Metric
entity_ids: []
relations:
  - forStation
tags:
  - "#obybk"
  - "#rag/question"
  - "#rag/eval/category/api-db-performance"
  - "#rag/eval/contract-pass"
  - "#ontology/domain/question"
  - "#ontology/domain/usage-metric"
  - "#ontology/domain/metric"
  - "#ontology/upper/event"
  - "#ontology/upper/metric"
  - "#relation/for-station"
  - "#sim/question/performance"
---

# SAMPLE-003 API 지연 상태는?

Tags: #obybk #rag/question #rag/eval/category/api-db-performance #rag/eval/contract-pass #ontology/domain/question #ontology/domain/usage-metric #ontology/domain/metric #ontology/upper/event #ontology/upper/metric #relation/for-station #sim/question/performance

## Run
- [[pi_ext_qa_run]]

## Ontology Links
- Concepts: [[Question]], [[UsageMetric]], [[Metric]]
- Entities: (none)
- Relations: [[forStation]]

## Question
API 지연 상태는?

## Answer
API/DB 성능 지표는 latency metric 중심으로 확인합니다.

## Review Signals
- contract_pass: `True`
- requires_review: `False`
- data_gap_count: `0`
- quality_guard_notes: `['profile_specific_guard']`
