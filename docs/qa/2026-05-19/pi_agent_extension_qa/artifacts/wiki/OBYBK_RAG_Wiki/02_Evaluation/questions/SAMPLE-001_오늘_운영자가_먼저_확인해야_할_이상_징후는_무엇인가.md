---
type: evaluation_question
run_id: pi_ext_qa_run
question_id: SAMPLE-001
category: "운영 모니터링"
contract_pass: true
requires_review: false
llm_mode: live
data_gap_count: 1
quality_guard_notes: []
ontology_type: Question
upper_concepts:
  - Event
  - Place
domain_concepts:
  - Question
  - Station
entity_ids:
  - ST-152
relations:
  - forStation
tags:
  - "#obybk"
  - "#rag/question"
  - "#rag/eval/category/operation-monitoring"
  - "#rag/eval/contract-pass"
  - "#sim/risk/data-gap"
  - "#ontology/domain/question"
  - "#ontology/domain/station"
  - "#ontology/upper/event"
  - "#ontology/upper/place"
  - "#sim/location/station"
  - "#entity/station/ST-152"
  - "#relation/for-station"
  - "#sim/question/monitoring"
---

# SAMPLE-001 오늘 운영자가 먼저 확인해야 할 이상 징후는 무엇인가?

Tags: #obybk #rag/question #rag/eval/category/operation-monitoring #rag/eval/contract-pass #sim/risk/data-gap #ontology/domain/question #ontology/domain/station #ontology/upper/event #ontology/upper/place #sim/location/station #entity/station/ST-152 #relation/for-station #sim/question/monitoring

## Run
- [[pi_ext_qa_run]]

## Ontology Links
- Concepts: [[Question]], [[Station]]
- Entities: [[충무로역 3.4호선 ST-152]]
- Relations: [[forStation]]

## Question
오늘 운영자가 먼저 확인해야 할 이상 징후는 무엇인가?

## Answer
충무로역 3.4호선 (ST-152)를 우선 확인합니다.

## Review Signals
- contract_pass: `True`
- requires_review: `False`
- data_gap_count: `1`
- quality_guard_notes: `[]`
