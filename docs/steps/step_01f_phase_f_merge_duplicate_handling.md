# Timestamp: 2026-04-20 18:24:07

# Phase F: Merge and Duplicate Handling

## Purpose

중복, 근접 중복, 상하위 관계, 별도 유지가 필요한 후보를 구분한다.

## Input

- 점수 평가까지 끝난 `candidate_record[]`

## Output

- `merge_record[]`

## Selection Rules

- 아래 관계 중 하나를 판단한다.
- `duplicate`
- `near_duplicate`
- `related_but_distinct`
- `broader_narrower`
- `uncertain`

## Reject Rules

- 의미 차이가 있는 후보를 억지로 병합하지 않는다.
- role 차이나 subclass 차이를 무시하지 않는다.

## Required Fields

- `canonical_candidate`
- `duplicate_group`
- `relation_among_candidates`
- `merge_recommendation`
- `notes`

## Decision Criteria

- 표기만 다른가
- 의미가 매우 가깝지만 완전히 같지는 않은가
- 상위/하위 관계인가
- 역할 차이 또는 문맥 차이가 중요한가

## Prompt Template

```text
다음 후보군을 비교해 merge 여부를 판단하라.

규칙:
- 동일 개념은 canonical form으로 병합 가능하다.
- 의미 차이가 있으면 억지로 병합하지 말라.
- broader/narrower 관계가 있으면 표시하라.
- alias, subclass, role difference 가능성을 notes에 남겨라.

입력 후보군:
[CANDIDATE_GROUP]
```

## Edge Cases

- `customer`, `client`, `subscriber`는 무조건 병합 금지다.
- `customer`와 `customers`는 duplicate 가능성이 높다.
- 동일 normalized form이더라도 notes에 다른 정의가 있으면 related_but_distinct 검토가 필요하다.
