# Timestamp: 2026-04-20 20:12:00

# Phase A: Candidate Extraction

## Purpose

외부 원문 없이 `LLM 내부 지식 + protocol rules`만으로 재사용 가능한 `concept candidate`를 생성한다.

## Input

- `generation_stratum`
- `general_category`
- `target_count`
- 분포 제어값

## Output

- `candidate_record[]`

## Selection Rules

- 재사용 가능한 명사 또는 명사구를 우선 생성한다.
- 역할명, 자산/자원, 서비스/제품/제공물, 이벤트/거래/운영 활동, 계약/정책/권리/의무, 조직/장소/시간, 문서/레코드/정보 객체를 우선 포함한다.
- 가능한 경우 원형화한다.
- `business` stratum은 비즈니스 구조 중심 후보를 우선 생성한다.
- `non_business` stratum은 일반 상위 온톨로지 축 후보를 우선 생성한다.

## Reject Rules

- 순수 동사
- UI 요소, 버튼명, 화면 라벨
- 지나치게 구현체적인 기술 용어
- 특정 회사 내부 약어
- 인스턴스성 고유명
- 의미 불명확 단일 단어

## Required Fields

- `surface_form`
- `normalized_form`
- `candidate_type`
- `business_relevance`
- `is_domain_specific`
- `suggested_generalization`

## Decision Criteria

- 개념 단위인가
- 여러 도메인에서 반복 재사용 가능한가
- 관계망의 노드나 축이 될 수 있는가

## Prompt Template

```text
주어진 제어값에 따라 재사용 가능한 concept candidate를 생성하라.

규칙:
- 단순 keyword가 아니라 concept candidate를 뽑아라.
- 가능하면 명사 또는 명사구로 정리하라.
- 구현체적, 일회성, 고유명, noise는 제외하라.
- 출력은 candidate_record[] JSON 배열로만 하라.
- 확신이 낮은 경우 notes에 uncertain 또는 needs_review를 남겨라.
- 외부 문서나 입력 텍스트를 가정하지 마라.
- `business`와 `non_business` stratum을 구분하라.
- `non_business` stratum이면 주어진 `general_category`에 맞춰 생성하라.

제어값:
- generation_stratum
- general_category
- target_count
```

## Edge Cases

- 복수형은 가능한 한 단수형으로 정리한다.
- 고유명과 일반 개념이 결합된 표현은 일반 개념 쪽을 우선 후보화한다.
- protocol 문구 자체를 재기록하지 말고 개념만 생성한다.
