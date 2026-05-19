---
type: evaluation_question
run_id: pi_ext_qa_run
question_id: SAMPLE-002
category: "추천/재배치/우선순위"
contract_pass: true
requires_review: true
llm_mode: live
data_gap_count: 2
quality_guard_notes:
  - review_gate_preserved
ontology_type: Question
upper_concepts:
  - Event
  - Place
  - ReviewGate
domain_concepts:
  - Question
  - Station
  - ReallocationRecommendation
  - ReviewGate
entity_ids:
  - ST-152
relations:
  - forStation
  - requiresReview
tags:
  - "#obybk"
  - "#rag/question"
  - "#rag/eval/category/reallocation-priority"
  - "#rag/eval/contract-pass"
  - "#review/needed"
  - "#sim/risk/review-needed"
  - "#sim/risk/data-gap"
  - "#ontology/domain/question"
  - "#ontology/domain/station"
  - "#ontology/domain/reallocation-recommendation"
  - "#ontology/domain/review-gate"
  - "#ontology/upper/event"
  - "#ontology/upper/place"
  - "#ontology/upper/review-gate"
  - "#sim/location/station"
  - "#entity/station/ST-152"
  - "#relation/for-station"
  - "#relation/requires-review"
  - "#sim/operation/reallocation"
---

# SAMPLE-002 충무로역 주변 재배치 후보를 검토해줘

Tags: #obybk #rag/question #rag/eval/category/reallocation-priority #rag/eval/contract-pass #review/needed #sim/risk/review-needed #sim/risk/data-gap #ontology/domain/question #ontology/domain/station #ontology/domain/reallocation-recommendation #ontology/domain/review-gate #ontology/upper/event #ontology/upper/place #ontology/upper/review-gate #sim/location/station #entity/station/ST-152 #relation/for-station #relation/requires-review #sim/operation/reallocation

## Run
- [[pi_ext_qa_run]]

## Ontology Links
- Concepts: [[Question]], [[Station]], [[ReallocationRecommendation]], [[ReviewGate]]
- Entities: [[충무로역 3.4호선 ST-152]]
- Relations: [[forStation]], [[requiresReview]]

## Question
충무로역 주변 재배치 후보를 검토해줘

## Answer
재배치 후보는 사람 검토 후 승인해야 합니다.

## Review Signals
- contract_pass: `True`
- requires_review: `True`
- data_gap_count: `2`
- quality_guard_notes: `['review_gate_preserved']`
