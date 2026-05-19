# Timestamp: 2026-04-20 18:24:07

# Phase C: Type Classification

## Purpose

각 후보를 온톨로지 구축 관점의 기본 타입으로 분류한다.

## Input

- 정규화된 `candidate_record[]`

## Output

- 타입 분류가 반영된 `candidate_record[]`

## Selection Rules

- 아래 라벨 중 하나를 `candidate_type`에 부여한다.
- `class_candidate`
- `relation_candidate`
- `attribute_candidate`
- `role_candidate`
- `state_candidate`
- `event_candidate`
- `process_candidate`
- `instance_like`
- `noise`

## Reject Rules

- 클래스 경계가 불명확한 항목을 억지로 클래스화하지 않는다.
- 상태나 속성을 과도하게 독립 클래스처럼 승격하지 않는다.

## Required Fields

- `candidate_type`
- `notes`

## Decision Criteria

- 안정된 개념 범주인가
- 관계, 속성, 역할, 상태 중 무엇이 본질인가
- 이벤트와 프로세스를 구분할 수 있는가

## Prompt Template

```text
다음 후보 목록을 타입 분류하라.

분류 라벨:
- class_candidate
- relation_candidate
- attribute_candidate
- role_candidate
- state_candidate
- event_candidate
- process_candidate
- instance_like
- noise

규칙:
- class와 state를 구분하라.
- role과 본질 class를 구분하라.
- relation과 attribute를 구분하라.
- 확신이 낮으면 notes에 needs_review를 남겨라.

입력 후보:
[CANDIDATES]
```

## Edge Cases

- `subscriber`는 role과 class 경계가 애매하면 notes에 보조 타입 후보를 남긴다.
- `status`류 표현은 state와 attribute를 먼저 검토한다.
- `payment processing`처럼 활동성과 절차성이 모두 있으면 process 우선 검토 후 notes에 event 가능성을 남긴다.
