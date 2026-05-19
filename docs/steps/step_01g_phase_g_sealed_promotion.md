# Timestamp: 2026-04-20 20:12:00

# Phase G: Sealed Promotion

## Purpose

후보를 `core_upper`, `business_archetype`, `general_reference`, `hold_for_review`, `reject`로 승격 분류하고 최종 요약을 만든다. retained 후보에 대해서만 `candidate_record.antonyms`를 개념적 반대축 기준으로 채운다.

## Input

- 병합 판단이 끝난 `candidate_record[]`
- `merge_record[]`

## Output

- 반의어가 채워진 `candidate_record[]`
- `promotion_record[]`
- `run_summary`

## Selection Rules

- 아래 판정 클래스를 사용한다.
- `core_upper`
- `business_archetype`
- `general_reference`
- `hold_for_review`
- `reject`

## Reject Rules

- `noise`와 `instance_like`는 원칙적으로 reject한다.
- domain-specific 표현을 일반화 검토 없이 성급히 승격하지 않는다.

## Required Fields

- `promotion_decision`
- `canonical_name`
- `short_definition`
- `rationale`
- `possible_parent_classes`
- `possible_related_classes`
- retained 후보의 `antonyms`

## Decision Criteria

- 도메인 재사용성
- 비즈니스 중요도
- 관계 중심성
- 상위/하위 구조 적합성
- 작은 모델에도 남을 정도의 압축 안정성
- 명확한 ontological opposite가 있는가

## Prompt Template

```text
다음 후보가 sealed archetype ontology에 포함될 가치가 있는지 판단하라.

판정 클래스:
- core_upper
- business_archetype
- general_reference
- hold_for_review
- reject

규칙:
- business 중요도와 general grounding을 함께 보라.
- possible_parent_classes와 possible_related_classes를 함께 제안하라.
- 확신이 낮으면 hold_for_review를 사용하라.
- `reject`는 antonyms를 빈 배열로 둬라.
- antonyms는 lexical opposite가 아니라 conceptual opposite axis 기준으로 제안하라.
- 명확한 반의어가 없으면 antonyms는 빈 배열로 둬라.

입력 후보:
[CANDIDATE]
```

## Edge Cases

- `actor`, `event`, `asset`, `place`, `policy`는 `core_upper` 가능성이 높다.
- `customer`, `service point`, `usage transaction`, `entitlement`은 `business_archetype` 가능성이 높다.
- `time interval`, `physical object`, `information object`는 `general_reference` 가능성이 높다.
