---
type: evaluation_question
run_id: pi_ext_qa_run
question_id: SAMPLE-004
category: "데이터/스키마/근거"
contract_pass: false
requires_review: true
llm_mode: fallback_parse_error
data_gap_count: 4
quality_guard_notes:
  - insufficient_context
ontology_type: Question
upper_concepts:
  - Event
  - ReviewGate
domain_concepts:
  - Question
  - ReviewGate
entity_ids: []
relations:
  - hasEvidence
  - requiresReview
  - forStation
tags:
  - "#obybk"
  - "#rag/question"
  - "#rag/eval/category/data-schema-evidence"
  - "#rag/eval/contract-fail"
  - "#review/needed"
  - "#sim/risk/review-needed"
  - "#sim/risk/data-gap"
  - "#ontology/domain/question"
  - "#ontology/domain/review-gate"
  - "#ontology/upper/event"
  - "#ontology/upper/review-gate"
  - "#relation/has-evidence"
  - "#relation/requires-review"
  - "#relation/for-station"
---

# SAMPLE-004 근거가 부족한 질문은 어떻게 표시돼?

Tags: #obybk #rag/question #rag/eval/category/data-schema-evidence #rag/eval/contract-fail #review/needed #sim/risk/review-needed #sim/risk/data-gap #ontology/domain/question #ontology/domain/review-gate #ontology/upper/event #ontology/upper/review-gate #relation/has-evidence #relation/requires-review #relation/for-station

## Run
- [[pi_ext_qa_run]]

## Ontology Links
- Concepts: [[Question]], [[ReviewGate]]
- Entities: (none)
- Relations: [[hasEvidence]], [[requiresReview]], [[forStation]]

## Question
근거가 부족한 질문은 어떻게 표시돼?

## Answer
근거가 부족하면 data gap과 review queue로 분리합니다.

## Review Signals
- contract_pass: `False`
- requires_review: `True`
- data_gap_count: `4`
- quality_guard_notes: `['insufficient_context']`
