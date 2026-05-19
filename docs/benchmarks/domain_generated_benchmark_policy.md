# Domain-generated Benchmark Policy

OBYBK의 100 QA benchmark는 특정 도메인에 고정된 질문 목록이 아니라, 도메인 artifact에서 생성되는 **versioned competency-question snapshot**이어야 한다.

## Why

고정 100문항은 한 도메인의 regression fixture로는 유용하지만, 다른 도메인에 그대로 적용하면 schema, entity, relation, metric, review-risk가 달라진다. 따라서 framework 평가의 핵심은 “이 100개 질문을 외웠는가”가 아니라, 새 도메인에서 다음 구조를 생성하고 검증할 수 있는가다.

```text
domain artifact directory
→ domain_manifest.json
→ LLM-generated QP/QO candidate questions
→ deterministic answerability/review-policy validation
→ frozen benchmark snapshot
→ visual-eval / wiki-export / profile comparison
```

## Two-layer design

| Layer | Role |
|---|---|
| Framework template | QP/QO 비율, answerability labels, evidence/relation/review gate 요구사항을 고정한다. |
| Domain-generated snapshot | 각 도메인의 source/schema/entity/relation 후보에 맞춰 LLM이 질문을 생성하고, 생성 결과를 versioned artifact로 저장한다. |

## Recommended composition

| Group | Count | Purpose |
|---|---:|---|
| QP | 50 | DB-only baseline으로도 가능한 실행형 데이터 질의 |
| QO | 50 | metric definition, schema confirmation, provenance, relation, confidence, review gate가 필요한 inspection 질의 |

## Generation constraints

LLM은 자유롭게 질문을 지어내는 것이 아니라 다음 입력을 근거로 생성해야 한다.

- `domain_manifest.json`
- dataset/source list
- known schema or field summary
- domain entities and candidate relations
- BMO/upper-ontology seed axes
- answerability/review policy labels

LLM 출력은 이후 deterministic policy로 검증한다.

- QP/QO count balance
- expected sources present
- answerability label valid
- `requires_review=True` reason is a real review risk, not merely “not executed”
- internal code labels are not leaked in user-facing wording
- provenance/relation/review-gate questions are separated from simple lookup questions

## Reproducibility rule

질문은 LLM이 생성하되, 평가에는 생성 결과를 고정 snapshot으로 사용한다.

```text
Generated dynamically for a domain.
Frozen when used for evaluation.
Versioned with model, prompt, source manifest, timestamp, and policy report.
```

이렇게 해야 domain adaptation과 evaluation reproducibility를 동시에 만족한다.

## Current repository artifact

현재 포함된 `obybk_rag_graphrag_inspection_benchmark_100.*`는 Seoul Bike case-study binding으로 만든 reference snapshot이다. universal fixed benchmark가 아니라, framework의 expected benchmark shape을 보여주는 예시이자 regression fixture다.
