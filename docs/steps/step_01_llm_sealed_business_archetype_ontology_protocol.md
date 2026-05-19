# Timestamp: 2026-04-20 20:12:00

# LLM Sealed Business Archetype Ontology Distillation Protocol

## 1. Purpose and Outcome

이 문서는 `sealed business archetype ontology` 증류 작업의 개요 문서다. 실제 페이즈별 실행 규약은 `step_01a`부터 `step_01g`까지의 분리 문서를 사용하고, 본 문서는 공통 비율 규칙, 구조화 출력 계약, 파일 맵, 실행 순서를 정의한다. 외부 문서, 런타임 텍스트, 입력 코퍼스는 사용하지 않고 `LLM 내부 지식 + protocol rules`만으로 후보를 생성하고 증류한다.

- 최종 산출 목표는 `business_archetype 70%`와 `general_reference + core_upper 30%`다.
- 초기 수집 목표는 `business-linked 50%`와 `general-even 50%`다.
- 출력은 항상 구조화된 형식만 허용한다.
- 설명이 필요하면 자유서술 문단 대신 JSON의 `notes` 또는 `run_summary.notes`를 사용한다.

## 2. System Role and Core Principles

시스템 역할은 `concept extraction and ontology distillation engine`이다. 단순 키워드가 아니라 재사용 가능한 `concept candidate`를 생성하고, 정규화, 분류, 일반화, 병합, 승격 판단을 거쳐 sealed 후보 집합으로 증류한다.

- `class`, `relation`, `attribute`, `role`, `state`, `event`, `process`를 구분한다.
- 가능한 한 명사 또는 2~4단어 명사구로 정리한다.
- 특정 산업 표현은 먼저 일반화 가능성을 검토한다.
- low-confidence 항목은 임의 확정하지 않고 `uncertain` 또는 `needs_review`로 기록한다.
- 상태/값/속성은 함부로 클래스화하지 않는다.
- 인스턴스성 표현, UI 라벨, 구현 세부, 내부 약어는 제외 우선이다.
- LLM 호출이 실패하면 heuristic fallback으로 대체하지 않고 run을 즉시 실패 처리한다.

## 3. Distribution Control

최종 결과와 초기 수집은 아래 분포를 따른다.

- 최종 결과: `business_archetype 70%`, `general_reference + core_upper 30%`
- 초기 수집: `business-linked 50%`, `general-even 50%`

일반 영역은 아래 12개 카테고리에 균등 분포하도록 관리한다.

- `actor/person`
- `organization`
- `place/location`
- `time/schedule`
- `object/asset`
- `event`
- `process/capability`
- `information/document`
- `contract/policy/right`
- `value/cost/revenue`
- `risk/compliance`
- `channel/interface/touchpoint`

운영 규칙:

- 특정 카테고리가 과대표집되면 다음 배치에서 해당 카테고리 가중치를 낮춘다.
- 부족 카테고리는 다음 배치에서 보충 추출한다.
- 일반 영역 분포 균형은 `run_summary.general_category_balance`로 기록한다.

## 4. Structured Output Contracts

모든 단계 산출은 아래 스키마를 따른다.

### `candidate_record[]`

```json
[
  {
    "surface_form": "",
    "normalized_form": "",
    "canonical_candidate": "",
    "candidate_type": "",
    "business_relevance": 0,
    "general_reusability": 0,
    "cross_domain_applicability": 0,
    "relational_centrality": 0,
    "abstraction_fitness": 0,
    "ontological_clarity": 0,
    "composability": 0,
    "compression_survival_likelihood": 0,
    "is_domain_specific": false,
    "generalizable": false,
    "suggested_generalization": "",
    "promotion_decision": "",
    "notes": "",
    "antonyms": []
  }
]
```

### `merge_record[]`

```json
[
  {
    "canonical_candidate": "",
    "duplicate_group": [],
    "relation_among_candidates": "",
    "merge_recommendation": "",
    "notes": ""
  }
]
```

### `promotion_record[]`

```json
[
  {
    "promotion_decision": "",
    "canonical_name": "",
    "short_definition": "",
    "rationale": "",
    "possible_parent_classes": [],
    "possible_related_classes": []
  }
]
```

### `run_summary`

```json
{
  "target_ratio": {
    "business_archetype": 0.7,
    "general_reference_plus_core_upper": 0.3
  },
  "observed_ratio": {
    "business_archetype": 0.0,
    "general_reference_plus_core_upper": 0.0
  },
  "general_category_balance": {
    "actor/person": 0,
    "organization": 0,
    "place/location": 0,
    "time/schedule": 0,
    "object/asset": 0,
    "event": 0,
    "process/capability": 0,
    "information/document": 0,
    "contract/policy/right": 0,
    "value/cost/revenue": 0,
    "risk/compliance": 0,
    "channel/interface/touchpoint": 0
  },
  "review_count": 0,
  "rejected_count": 0,
  "notes": ""
}
```

## 5. File Map

- `step_01a_phase_a_candidate_extraction.md`
- `step_01b_phase_b_normalization.md`
- `step_01c_phase_c_type_classification.md`
- `step_01d_phase_d_generalization_assessment.md`
- `step_01e_phase_e_ontology_fitness_evaluation.md`
- `step_01f_phase_f_merge_duplicate_handling.md`
- `step_01g_phase_g_sealed_promotion.md`

## 6. Prompt Template Index

### System Prompt

`step_01a`부터 `step_01g`의 모든 프롬프트는 아래 시스템 역할을 공유한다.

```text
당신은 concept extraction and ontology distillation engine이다.
당신의 역할은 외부 문서 입력 없이 LLM 내부 지식과 protocol rules만으로 재사용 가능한 concept candidate를 생성하고,
이를 정규화하여 sealed business archetype ontology 후보 집합으로 증류하는 것이다.
출력은 항상 구조화된 JSON 형식으로만 반환하라.
확신이 낮은 경우 uncertain 또는 needs_review를 notes에 남겨라.
```

### Template 1

`Template 1`은 1차 후보 추출 템플릿이며 상세 규칙은 `step_01a_phase_a_candidate_extraction.md`를 사용한다.

### Template 2

`Template 2`는 타입 분류 템플릿이며 상세 규칙은 `step_01c_phase_c_type_classification.md`를 사용한다.

### Template 3

`Template 3`은 유사 후보 병합 템플릿이며 상세 규칙은 `step_01f_phase_f_merge_duplicate_handling.md`를 사용한다.

### Template 4

`Template 4`는 sealed 승격 판단 템플릿이며 상세 규칙은 `step_01g_phase_g_sealed_promotion.md`를 사용한다.

## 7. Execution Order

실행 순서는 고정한다.

1. `phase_a`: 축별 raw 후보 생성
2. `phase_b`: 정규화
3. `phase_c`: 타입 분류
4. `phase_d`: 일반화 판정
5. `phase_e`: 온톨로지 적합성 평가
6. `phase_f`: 병합/중복 처리
7. `phase_g`: sealed 승격과 요약

## 8. Minimal Quality Gates

- 자유서술만 있는 응답은 거부한다.
- `instance_like`와 `noise`는 승격 대상이 아니다.
- `customer`, `client`, `subscriber`는 의미 차이를 검토한 뒤 병합 여부를 판단한다.
- `bike rental pass`는 일반화 후보를 반드시 검토한다.
- `station kiosk login error`는 더 상위의 incident 계열 후보로 흡수 가능한지 검토한다.
- protocol 문구 자체를 surface candidate로 승격하지 않는다.
