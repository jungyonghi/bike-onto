# Timestamp: 2026-04-20 18:24:07

# Phase D: Generalization Assessment

## Purpose

도메인 특화 표현이 더 재사용 가능한 상위 후보로 일반화될 수 있는지 평가한다.

## Input

- 타입 분류가 끝난 `candidate_record[]`

## Output

- 일반화 판정이 반영된 `candidate_record[]`

## Selection Rules

- 도메인 특수성이 높으면 `suggested_generalization`을 제안한다.
- 원문 표현은 alias로 유지하고 일반화 표현은 canonical 후보로 검토한다.

## Reject Rules

- 일반화 과정에서 핵심 의미 제약이 사라지는 경우
- `thing`, `data`, `system`처럼 공허한 초상위어만 남는 경우

## Required Fields

- `is_domain_specific`
- `generalizable`
- `suggested_generalization`

## Decision Criteria

- 다른 산업에도 같은 구조가 반복되는가
- 일반화 결과가 관계 설계에 유용한가
- 너무 빈 추상어가 아닌가

## Prompt Template

```text
다음 후보가 지나치게 domain-specific한지 검토하고,
필요하면 더 generalizable한 후보를 제안하라.

규칙:
- 원문 표현은 유지하라.
- suggested_generalization은 비어 있을 수 있다.
- 일반화가 불명확하면 notes에 uncertain 또는 needs_review를 남겨라.

입력 후보:
[CANDIDATES]
```

## Edge Cases

- `bike rental pass`는 `access entitlement`, `subscription offering`, `pricing plan` 계열을 검토한다.
- `station kiosk login error`는 `access incident` 또는 `service point access issue` 계열을 검토한다.
- 특정 공급사 제품명은 제품 타입보다 상위의 제공물 또는 자산 클래스를 우선 검토한다.
