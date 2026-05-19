# Timestamp: 2026-04-20 18:24:07

# Phase B: Normalization

## Purpose

표기 흔들림과 형태 변이를 정리해 `canonical_candidate`를 도출한다.

## Input

- `candidate_record[]`

## Output

- 정규화된 `candidate_record[]`

## Selection Rules

- 소문자 기준으로 통일한다.
- 단수형을 우선한다.
- 하이픈과 공백 표기를 정리한다.
- 불필요한 수식어를 제거한다.
- 약어는 가능한 경우 풀어쓰고 약어는 notes에 alias로 남긴다.

## Reject Rules

- 정규화 후에도 인스턴스성이 유지되는 표현
- 정규화 후 의미가 지나치게 공허해지는 표현

## Required Fields

- `surface_form`
- `normalized_form`
- `canonical_candidate`

## Decision Criteria

- 표기 차이를 제거해도 의미가 유지되는가
- canonical 표현이 하위 도메인을 포괄할 수 있는가

## Prompt Template

```text
다음 후보 목록을 정규화하라.

규칙:
- lowercase 기준 통일
- singular 우선
- hyphen/space 표기 통일
- unnecessary modifier 제거
- canonical_candidate를 지정하라

입력 후보:
[CANDIDATES]
```

## Edge Cases

- `service-point`와 `service point`는 동일 표기로 수렴시킨다.
- `customers`와 `customer`는 동일 canonical 후보로 처리한다.
- 의미가 달라질 수 있는 pluralia tantum은 notes에 보존 사유를 기록한다.
