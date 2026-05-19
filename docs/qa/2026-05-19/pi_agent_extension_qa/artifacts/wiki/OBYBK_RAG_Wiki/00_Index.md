---
type: wiki_index
project: OBYBK
run_id: pi_ext_qa_run
tags:
  - "#obybk"
  - "#wiki/index"
  - "#rag/wiki"
---

# OBYBK RAG Wiki

## Dashboard
- Latest Run: [[pi_ext_qa_run]]
- Review Queue: [[review_queue_pi_ext_qa_run]]
- Questions: `4`
- Contract Pass: `3/4`
- Review Items: `4`
- Data-gap Questions: `3`
- Entities: `1` / Concepts: `8` / Relations: `3`

## Category Counts
- **운영 모니터링**: `1`
- **추천/재배치/우선순위**: `1`
- **API/DB/성능**: `1`
- **데이터/스키마/근거**: `1`

## LLM Mode Counts
- `live`: `2`
- `offline_cli`: `1`
- `fallback_parse_error`: `1`

## Question Samples
- ✅ [[SAMPLE-001_오늘_운영자가_먼저_확인해야_할_이상_징후는_무엇인가]] — 오늘 운영자가 먼저 확인해야 할 이상 징후는 무엇인가?
- ✅ [[SAMPLE-002_충무로역_주변_재배치_후보를_검토해줘]] — 충무로역 주변 재배치 후보를 검토해줘 review
- ✅ [[SAMPLE-003_API_지연_상태는]] — API 지연 상태는?
- ⚠️ [[SAMPLE-004_근거가_부족한_질문은_어떻게_표시돼]] — 근거가 부족한 질문은 어떻게 표시돼? review

## Review Hotlist
- [[SAMPLE-001_오늘_운영자가_먼저_확인해야_할_이상_징후는_무엇인가]] — contract_pass=`True`, data_gap_count=`1`
- [[SAMPLE-002_충무로역_주변_재배치_후보를_검토해줘]] — contract_pass=`True`, data_gap_count=`2`
- [[SAMPLE-003_API_지연_상태는]] — contract_pass=`True`, data_gap_count=`0`
- [[SAMPLE-004_근거가_부족한_질문은_어떻게_표시돼]] — contract_pass=`False`, data_gap_count=`4`

## Ontology Entry Points
- Domain concepts: [[Question]], [[Station]], [[UsageMetric]], [[ReallocationRecommendation]], [[ReviewGate]]
- Relations: [[hasEvidence]], [[forStation]], [[requiresReview]]
- Entity examples: [[충무로역 3.4호선 ST-152]]

## Query Examples
- `tag:#sim/operation/reallocation tag:#ontology/domain/station`
- `tag:#review/needed tag:#sim/risk/data-gap`
- `tag:#entity/station/ST-152`
- `tag:#relation/has-evidence tag:#rag/eval/contract-fail`
