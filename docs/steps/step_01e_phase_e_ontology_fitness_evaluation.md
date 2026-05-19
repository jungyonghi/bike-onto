# Timestamp: 2026-04-20 18:24:07

# Phase E: Ontology Fitness Evaluation

## Purpose

각 후보의 비즈니스 재사용성과 온톨로지 적합성을 점수화한다.

## Input

- 일반화 검토가 끝난 `candidate_record[]`

## Output

- 점수가 반영된 `candidate_record[]`

## Selection Rules

- 아래 8개 필드를 `1..5` 범위로 평가한다.
- `business_relevance`
- `general_reusability`
- `cross_domain_applicability`
- `relational_centrality`
- `abstraction_fitness`
- `ontological_clarity`
- `composability`
- `compression_survival_likelihood`

## Reject Rules

- 비즈니스 관련성만 높다고 승격하지 않는다.
- 점수를 직관적으로 몰아주지 말고 재사용성과 구조 적합성을 기준으로 준다.

## Required Fields

- 위 8개 점수 필드 전체

## Decision Criteria

- `1`: 매우 약함
- `2`: 제한적
- `3`: 유지 검토 가능
- `4`: 강함
- `5`: 핵심 축

## Prompt Template

```text
다음 후보를 온톨로지 적합성 기준으로 점수화하라.

규칙:
- 8개 필드를 모두 1..5로 채워라.
- business relevance가 높아도 cross-domain applicability가 낮으면 낮게 점수화할 수 있다.
- 점수 근거가 필요하면 notes에 짧게 남겨라.

입력 후보:
[CANDIDATES]
```

## Edge Cases

- 구현체 용어는 business relevance가 높아도 abstraction fitness를 낮게 줄 수 있다.
- 매우 추상적인 상위 개념은 business relevance가 낮아도 composability가 높을 수 있다.
- 상태값 후보는 ontological clarity가 높아도 class 승격 적합성이 낮을 수 있다.
