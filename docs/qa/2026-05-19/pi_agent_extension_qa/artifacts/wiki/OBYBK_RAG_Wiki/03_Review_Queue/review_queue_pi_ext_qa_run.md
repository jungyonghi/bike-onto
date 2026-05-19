---
type: review_queue
run_id: pi_ext_qa_run
review_count: 4
tags:
  - "#obybk"
  - "#review/queue"
  - "#rag/eval/review-queue"
---

# Review Queue pi_ext_qa_run

Tags: #obybk #review/queue #rag/eval/review-queue

## [[SAMPLE-001_오늘_운영자가_먼저_확인해야_할_이상_징후는_무엇인가]]
- Category: `운영 모니터링`
- contract_pass: `True`
- requires_review: `False`
- data_gap_count: `1`
- quality_guard_notes: `[]`

## [[SAMPLE-002_충무로역_주변_재배치_후보를_검토해줘]]
- Category: `추천/재배치/우선순위`
- contract_pass: `True`
- requires_review: `True`
- data_gap_count: `2`
- quality_guard_notes: `['review_gate_preserved']`

## [[SAMPLE-003_API_지연_상태는]]
- Category: `API/DB/성능`
- contract_pass: `True`
- requires_review: `False`
- data_gap_count: `0`
- quality_guard_notes: `['profile_specific_guard']`

## [[SAMPLE-004_근거가_부족한_질문은_어떻게_표시돼]]
- Category: `데이터/스키마/근거`
- contract_pass: `False`
- requires_review: `True`
- data_gap_count: `4`
- quality_guard_notes: `['insufficient_context']`
