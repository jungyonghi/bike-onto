# Timestamp: 2026-04-27 16:22:39

# Business Model Ontology OWL 2 DL 형식화 청사진

## 문서 성격

이 문서는 Alexander Osterwalder의 *The Business Model Ontology - A Proposition in a Design Science Approach*를 `OWL 2 DL` 스타일로 최대한 충실하게 형식화하기 위한 `개념 청사진 + 구현 로드맵 + 이후 작업 사양서`다. 성격상 단순 설명문이나 개론이 아니라, 나중에 실제 `Protégé`, `OWLAPI`, `ROBOT`, `SHACL` 작업으로 이어질 수 있도록 `엔터티 목록`, `모듈 경계`, `속성 설계`, `제약 원칙`, `구현 단계`를 함께 정의한다.

## 왜 제목을 `형식화 청사진`으로 잡는가

- `사상`만 담기에는 구현 단계가 구체적이다.
- `알고리즘`이라고 부르기에는 계산 절차보다 개념 구조와 제약 설계가 중심이다.
- `로드맵`이라고만 부르기에는 클래스, 속성, 코드리스트 같은 정적 설계가 부족하게 들린다.
- 그래서 이 문서는 `형식화 청사진 [formalization blueprint]`이라는 이름이 가장 잘 맞는다.

## 기준 소스

- 원 논문 로컬 변환본: [osterwalder_phd_bm_ontology.md](/home/user/Documents/01_Projects/01_Active/obybk/references/literature/converted/osterwalder_phd_bm_ontology/osterwalder_phd_bm_ontology.md)
- 보조 논문: https://ceur-ws.org/Vol-125/paper27.pdf
- 현재 프로젝트의 온톨로지-lite 맥락: [aiplan.md](/home/user/Documents/01_Projects/01_Active/obybk/docs/project/aiplan.md), [architecture.mmd](/home/user/Documents/01_Projects/01_Active/obybk/docs/architecture/architecture.mmd)

## 목표

1. 논문의 `4개 pillar`와 `9개 business model element`를 전부 `OWL 2 DL`에 올릴 수 있는 수준으로 정식 명세화한다.
2. 하위 요소가 아직 비어 있어도 구조를 먼저 만든다.
3. `TBox`와 `ABox`를 분리해, 먼저 개념 스키마를 안정화한 뒤 실제 사례를 넣는다.
4. 나중에 `따릉이`, `공공 모빌리티`, `공공 서비스 BM` 같은 하위 도메인을 자연스럽게 매핑할 수 있게 한다.

## 모델링 입장

### 1. description-first

- 1차 온톨로지는 `실세계 조직 자체`보다 `BusinessModelDescription`을 중심으로 잡는다.
- 즉 “회사가 실제로 무엇을 하고 있나”보다 “그 회사의 비즈니스 모델을 어떻게 기술하나”를 먼저 온톨로지화한다.
- 이 방식은 원 논문의 관점과도 잘 맞고, `OWL 2 DL`에서 깔끔한 `TBox`를 만들기 쉽다.

### 2. open world friendly

- 하위 요소가 비어 있어도 괜찮다.
- `OWL 2 DL`은 `Open World Assumption`을 따르므로, 기록되지 않은 하위 항목을 거짓으로 강제하지 않는다.
- 따라서 지금 단계에서는 “모든 칸을 만든다”가 중요하고, “모든 칸을 채운다”는 다음 단계다.

### 3. conservative restriction

- 논문에 나오는 `1-n`, `0-n` 표기를 그대로 데이터베이스 제약처럼 강제하지 않는다.
- 핵심 상위 요소는 `some` 제약으로 살리고, 세부 completeness 검사는 나중에 `SHACL`로 분리한다.

### 4. qualitative codelist explicitness

- 논문에 나오는 값 범주를 문자열로 흩뿌리지 않고 명시적 코드리스트로 올린다.
- 구현 시점에는 `owl:oneOf` nominal 집합 또는 전용 코드 클래스 계층 가운데 하나로 선택한다.

## 상위 구조

### 레이어

1. `Upper/Core Layer`
   - 비즈니스 모델 기술을 위한 최소 공통 골격
2. `Business Model Description Layer`
   - 논문의 4개 pillar, 9개 element, sub-element
3. `Realization / Domain Extension Layer`
   - 실제 기업, 실제 사례, 따릉이 같은 도메인 인스턴스와 매핑

### 권장 네임스페이스

- 기본 prefix: `bmo:`
- 코드리스트 prefix: `bmov:`
- 예시 인스턴스 prefix: `bmi:`

### 권장 파일 분리

```text
ontology/
  business-model/
    bmo-core.owl
    bmo-pillars.owl
    bmo-elements.owl
    bmo-subelements.owl
    bmo-valuations.owl
    bmo-financial.owl
    bmo-examples.ttl
    shacl/
      bmo-shapes.ttl
    competency_questions.md
    implementation_notes.md
```

## 핵심 상위 클래스

| 클래스 | 역할 | 비고 |
| --- | --- | --- |
| `BusinessModelDescription` | 하나의 비즈니스 모델 설명 객체 | 전체 루트 |
| `BusinessModelPillar` | 4개 pillar의 상위 클래스 | 분류 축 |
| `BusinessModelElement` | 9개 핵심 섹션의 상위 클래스 | 본체 |
| `BusinessModelSubElement` | element 하위 구성 단위 | 세분화 |
| `BusinessModelActor` | 파트너/외부 조직 표현 | `Actor` 앵커 |
| `BusinessValueCodelist` | 값 범주 코드리스트의 상위 분류 | 선택적 추상화 |
| `BusinessModelAssessmentAxis` | 2차 확장용 평가 축 | 나중 단계 |

## 4개 pillar

| Pillar 클래스 | 논문 용어 | 역할 |
| --- | --- | --- |
| `ProductPillar` | Product | 고객에게 제공되는 가치 묶음의 상위 구역 |
| `CustomerInterfacePillar` | Customer Interface | 누구에게 어떻게 닿고 어떤 관계를 맺는지 |
| `InfrastructureManagementPillar` | Infrastructure Management | 가치를 만들기 위한 능력, 자원, 활동, 파트너 구조 |
| `FinancialAspectsPillar` | Financial Aspects | 수익 및 비용 논리 |

## 9개 element와 하위 구조

| Pillar | Element 클래스 | 핵심 의미 | 하위 요소 / 보조 엔터티 | 핵심 연결 |
| --- | --- | --- | --- | --- |
| Product | `ValueProposition` | 고객에게 제공되는 가치 묶음 | `Offering` | `valueForCustomer`, `basedOnCapability` |
| Customer Interface | `TargetCustomer` | 가치 제공 대상 세그먼트 | `Criterion` | `receivesValueProposition` |
| Customer Interface | `DistributionChannel` | 고객에게 닿는 전달 경로 | `Link` | `deliversValueProposition`, `deliversToCustomer` |
| Customer Interface | `Relationship` | 고객과 맺는 관계 유형 | `RelationshipMechanism` | `promotesValueProposition`, `maintainedWithCustomer` |
| Infrastructure Management | `Capability` | 반복 가능한 행동 수행 능력 | `Resource`, `BusinessModelActor` | `supportsValueProposition`, `hasResource` |
| Infrastructure Management | `ValueConfiguration` | 가치창출 활동 배열 | `Activity` | `reliesOnCapability`, `makesPossibleValueProposition` |
| Infrastructure Management | `Partnership` | 외부 조직과의 협력 구조 | `Agreement`, `BusinessModelActor` | `concernsValueConfiguration`, `developedToProvideValueProposition` |
| Financial Aspects | `RevenueModel` | 가치의 현금화 방식 | `RevenueStreamAndPricing` | `builtOnValueProposition` |
| Financial Aspects | `CostStructure` | 비용 구조 | `Account` | `hasAccount` |

## element별 세부 형식화 방침

### 1. `ValueProposition`

- 논문 의미: 고객에게 가치 있는 제품/서비스 번들의 총체적 진술
- 필수 관계:
  - `valueForCustomer some TargetCustomer`
  - `basedOnCapability some Capability`
- 하위 요소:
  - `Offering`
- 핵심 속성:
  - `hasReasoningKind`
  - `hasValueLevel`
  - `hasPriceLevel`
  - `hasValueLifeCyclePhase`

### 2. `TargetCustomer`

- 논문 의미: 회사가 가치 제공 대상으로 선택한 고객 세그먼트
- 하위 요소:
  - `Criterion`
- 핵심 속성:
  - 직접적인 정량 속성은 약하고, 주로 기준 분해를 통해 표현

### 3. `DistributionChannel`

- 논문 의미: 가치제안이 고객에게 전달되는 경로
- 하위 요소:
  - `Link`
- 핵심 관계:
  - `deliversValueProposition some ValueProposition`
  - `deliversToCustomer some TargetCustomer`
  - `hasLink only Link`

### 4. `Relationship`

- 논문 의미: 고객과 회사 사이에 형성되는 관계
- 하위 요소:
  - `RelationshipMechanism`
- 핵심 속성:
  - `hasCustomerEquityGoal`
- 핵심 관계:
  - `promotesValueProposition some ValueProposition`
  - `maintainedWithCustomer some TargetCustomer`

### 5. `Capability`

- 논문 의미: 반복 가능한 행동 수행 능력
- 하위 요소:
  - `Resource`
- 보조 엔터티:
  - `BusinessModelActor`
- 핵심 관계:
  - `supportsValueProposition some ValueProposition`
  - `hasResource only Resource`

### 6. `ValueConfiguration`

- 논문 의미: 활동과 자원의 배열을 통한 가치창출 구조
- 하위 요소:
  - `Activity`
- 핵심 속성:
  - `hasConfigurationType`
- 핵심 관계:
  - `reliesOnCapability some Capability`
  - `makesPossibleValueProposition some ValueProposition`

### 7. `Partnership`

- 논문 의미: 가치창출을 위한 자발적 협력 구조
- 하위 요소:
  - `Agreement`
- 보조 엔터티:
  - `BusinessModelActor`
- 핵심 관계:
  - `concernsValueConfiguration some ValueConfiguration`
  - `developedToProvideValueProposition some ValueProposition`

### 8. `RevenueModel`

- 논문 의미: 회사가 가치로부터 돈을 벌어들이는 방식
- 하위 요소:
  - `RevenueStreamAndPricing`
- 핵심 관계:
  - `builtOnValueProposition some ValueProposition`

### 9. `CostStructure`

- 논문 의미: 가치창출과 전달에 사용되는 모든 비용 구조
- 하위 요소:
  - `Account`
- 핵심 관계:
  - `hasAccount only Account`

## sub-element와 보조 엔터티 전체 목록

| 클래스 | 상위 | 설명 |
| --- | --- | --- |
| `Offering` | `BusinessModelSubElement` | `ValueProposition`을 이루는 기본 가치 단위 |
| `Criterion` | `BusinessModelSubElement` | `TargetCustomer`를 분해하는 세분 기준 |
| `Link` | `BusinessModelSubElement` | 채널의 세부 접점/역할 |
| `RelationshipMechanism` | `BusinessModelSubElement` | 관계를 형성·유지하는 메커니즘 |
| `Resource` | `BusinessModelSubElement` | 가치창출의 입력 자원 |
| `Activity` | `BusinessModelSubElement` | 가치창출/전달을 위한 행동 단위 |
| `Agreement` | `BusinessModelSubElement` | 파트너십 조건과 목적을 규정하는 합의 |
| `RevenueStreamAndPricing` | `BusinessModelSubElement` | 수익 흐름과 가격결정 메커니즘 |
| `Account` | `BusinessModelSubElement` | 비용 항목 |
| `BusinessModelActor` | 보조 엔터티 | 파트너, 외부 조직, 역할 수행 주체 |

## 코드리스트와 값 범주

### 공통 원칙

- 1차 구현에서는 값 범주를 모두 별도 코드리스트로 만든다.
- 구현 방식은 아래 둘 중 하나를 고른다.
  - `ObjectProperty + nominal individuals`
  - `ObjectProperty + value classes`
- 추천은 `nominal individual` 방식이다. 논문의 범주가 폐쇄적이기 때문이다.

### `ValueProposition / Offering`

| 코드리스트 | 값 |
| --- | --- |
| `ReasoningKind` | `UseReasoning`, `RiskReductionReasoning`, `EffortReductionReasoning` |
| `ValueLevel` | `MeToo`, `InnovativeImitation`, `Excellence`, `Innovation` |
| `PriceLevel` | `Free`, `Economy`, `Market`, `HighEnd` |
| `ValueLifeCyclePhase` | `Creation`, `Purchase`, `Use`, `Renewal`, `Transfer` |

### `DistributionChannel / Link`

| 코드리스트 | 값 |
| --- | --- |
| `CustomerBuyingCyclePhase` | `Awareness`, `Evaluation`, `Purchase`, `AfterSales` |

### `Relationship / RelationshipMechanism`

| 코드리스트 | 값 |
| --- | --- |
| `CustomerEquityGoal` | `Acquisition`, `Retention`, `AddOnSelling` |
| `RelationshipFunction` | `Personalization`, `Trust`, `Brand` |

### `Capability / Resource / ValueConfiguration / Activity`

| 코드리스트 | 값 |
| --- | --- |
| `ResourceType` | `TangibleResource`, `IntangibleResource`, `HumanResource` |
| `ResourceActivityLinkType` | `Fit`, `Flow`, `Shared` |
| `ConfigurationType` | `ValueChainConfiguration`, `ValueShopConfiguration`, `ValueNetworkConfiguration` |
| `ActivityLevel` | `PrimaryActivity`, `SupportActivity` |

### `ActivityNature`

| 분기 | 값 |
| --- | --- |
| `ValueChainActivityNature` | `InboundLogistics`, `Operations`, `OutboundLogistics`, `MarketingAndSales`, `Service` |
| `ValueShopActivityNature` | `ProblemFindingAndAcquisition`, `ProblemSolving`, `Choice`, `Execution`, `ControlAndEvaluation` |
| `ValueNetworkActivityNature` | `NetworkPromotionAndContractManagement`, `ServiceProvisioning`, `NetworkInfrastructureOperation` |

### `Agreement`

| 코드리스트 | 값 |
| --- | --- |
| `PartnershipReason` | `OptimizationAndEconomiesOfScale`, `ReductionOfRiskAndUncertainty`, `AcquisitionOfResources` |

추가 수치 속성:

- `hasStrategicImportance`: `xsd:integer` with range `0..5`
- `hasDegreeOfCompetition`: `xsd:integer` with range `0..5`
- `hasDegreeOfIntegration`: `xsd:integer` with range `0..5`
- `hasSubstitutability`: `xsd:integer` with range `0..5`

### `RevenueStreamAndPricing / Account`

| 코드리스트 | 값 |
| --- | --- |
| `RevenueStreamType` | `Selling`, `Lending`, `Licensing`, `TransactionCut`, `Advertising` |
| `PricingMethod` | `FixedPricing`, `DifferentialPricing`, `MarketPricing` |

추가 수치 속성:

- `hasPercentage`: `xsd:decimal`
- `hasSumAmount`: `xsd:decimal`

## ObjectProperty 카탈로그

### 구조적 속성

| 속성 | Domain | Range | 용도 |
| --- | --- | --- | --- |
| `hasPillar` | `BusinessModelDescription` | `BusinessModelPillar` | 설명 객체가 pillar를 가짐 |
| `hasElement` | `BusinessModelPillar` | `BusinessModelElement` | pillar 내부 요소 연결 |
| `hasSubElement` | `BusinessModelElement` | `BusinessModelSubElement` | element 내부 분해 |
| `partOfDescription` | `BusinessModelPillar` | `BusinessModelDescription` | 역방향 |
| `partOfPillar` | `BusinessModelElement` | `BusinessModelPillar` | 역방향 |
| `partOfElement` | `BusinessModelSubElement` | `BusinessModelElement` | 역방향 |

### 가치/고객 관련 속성

| 속성 | Domain | Range |
| --- | --- | --- |
| `valueForCustomer` | `ValueProposition` | `TargetCustomer` |
| `basedOnCapability` | `ValueProposition` | `Capability` |
| `hasOffering` | `ValueProposition` | `Offering` |
| `hasCriterion` | `TargetCustomer` | `Criterion` |
| `deliversValueProposition` | `DistributionChannel` | `ValueProposition` |
| `deliversToCustomer` | `DistributionChannel` | `TargetCustomer` |
| `hasLink` | `DistributionChannel` | `Link` |
| `connectedToLink` | `Link` | `Link` |
| `promotesValueProposition` | `Relationship` | `ValueProposition` |
| `maintainedWithCustomer` | `Relationship` | `TargetCustomer` |
| `hasRelationshipMechanism` | `Relationship` | `RelationshipMechanism` |

### 인프라/파트너 관련 속성

| 속성 | Domain | Range |
| --- | --- | --- |
| `hasResource` | `Capability` | `Resource` |
| `providedByActor` | `Resource` | `BusinessModelActor` |
| `supportsValueProposition` | `Capability` | `ValueProposition` |
| `hasActivity` | `ValueConfiguration` | `Activity` |
| `reliesOnCapability` | `ValueConfiguration` | `Capability` |
| `makesPossibleValueProposition` | `ValueConfiguration` | `ValueProposition` |
| `executedByActor` | `Activity` | `BusinessModelActor` |
| `usesResource` | `Activity` | `Resource` |
| `concernsValueConfiguration` | `Partnership` | `ValueConfiguration` |
| `developedToProvideValueProposition` | `Partnership` | `ValueProposition` |
| `hasAgreement` | `Partnership` | `Agreement` |
| `agreementWithActor` | `Agreement` | `BusinessModelActor` |

### 재무 관련 속성

| 속성 | Domain | Range |
| --- | --- | --- |
| `hasRevenueStreamAndPricing` | `RevenueModel` | `RevenueStreamAndPricing` |
| `builtOnValueProposition` | `RevenueModel` | `ValueProposition` |
| `forOffering` | `RevenueStreamAndPricing` | `Offering` |
| `attachedToLink` | `RevenueStreamAndPricing` | `Link` |
| `hasAccount` | `CostStructure` | `Account` |

### 코드리스트 연결 속성

| 속성 | Domain | Range |
| --- | --- | --- |
| `hasReasoningKind` | `Offering` or `Link` or `RelationshipMechanism` | `ReasoningKind` |
| `hasValueLevel` | `Offering` or `ValueProposition` | `ValueLevel` |
| `hasPriceLevel` | `Offering` or `ValueProposition` | `PriceLevel` |
| `hasValueLifeCyclePhase` | `Offering` or `ValueProposition` | `ValueLifeCyclePhase` |
| `hasCustomerBuyingCyclePhase` | `Link` | `CustomerBuyingCyclePhase` |
| `hasCustomerEquityGoal` | `Relationship` | `CustomerEquityGoal` |
| `hasRelationshipFunction` | `RelationshipMechanism` | `RelationshipFunction` |
| `hasResourceType` | `Resource` | `ResourceType` |
| `hasResourceActivityLinkType` | `Activity` or reified edge | `ResourceActivityLinkType` |
| `hasConfigurationType` | `ValueConfiguration` | `ConfigurationType` |
| `hasActivityLevel` | `Activity` | `ActivityLevel` |
| `hasActivityNature` | `Activity` | `ActivityNature` |
| `hasPartnershipReason` | `Agreement` | `PartnershipReason` |
| `hasRevenueStreamType` | `RevenueStreamAndPricing` | `RevenueStreamType` |
| `hasPricingMethod` | `RevenueStreamAndPricing` | `PricingMethod` |

## DataProperty 카탈로그

| 속성 | Domain | Range | 비고 |
| --- | --- | --- | --- |
| `hasName` | 거의 모든 엔터티 | `xsd:string` | 표준 명칭 |
| `hasDescription` | 거의 모든 엔터티 | `xsd:string` | 텍스트 설명 |
| `hasStrategicImportance` | `Agreement` | `xsd:integer` | `0..5` |
| `hasDegreeOfCompetition` | `Agreement` | `xsd:integer` | `0..5` |
| `hasDegreeOfIntegration` | `Agreement` | `xsd:integer` | `0..5` |
| `hasSubstitutability` | `Agreement` | `xsd:integer` | `0..5` |
| `hasPercentage` | `RevenueStreamAndPricing`, `Account` | `xsd:decimal` | 구성 비중 |
| `hasSumAmount` | `Account` | `xsd:decimal` | 비용 총액 |
| `hasSourceCitation` | 모든 주요 엔터티 | `xsd:string` | 논문, 인터뷰, 보고서 등 |
| `hasLocalIdentifier` | 인스턴스 계층 | `xsd:string` | 후속 매핑용 |

## Manchester Syntax 골격

```manchester
Class: BusinessModelDescription
  SubClassOf:
    hasPillar some ProductPillar,
    hasPillar some CustomerInterfacePillar,
    hasPillar some InfrastructureManagementPillar,
    hasPillar some FinancialAspectsPillar,
    hasValueProposition some ValueProposition,
    hasTargetCustomer some TargetCustomer,
    hasDistributionChannel some DistributionChannel,
    hasRelationship some Relationship,
    hasCapability some Capability,
    hasValueConfiguration some ValueConfiguration,
    hasPartnership some Partnership,
    hasRevenueModel some RevenueModel,
    hasCostStructure some CostStructure

Class: ValueProposition
  SubClassOf:
    BusinessModelElement,
    valueForCustomer some TargetCustomer,
    basedOnCapability some Capability,
    hasOffering only Offering

Class: DistributionChannel
  SubClassOf:
    BusinessModelElement,
    deliversValueProposition some ValueProposition,
    deliversToCustomer some TargetCustomer,
    hasLink only Link

Class: Relationship
  SubClassOf:
    BusinessModelElement,
    promotesValueProposition some ValueProposition,
    maintainedWithCustomer some TargetCustomer,
    hasRelationshipMechanism only RelationshipMechanism

Class: ValueConfiguration
  SubClassOf:
    BusinessModelElement,
    reliesOnCapability some Capability,
    makesPossibleValueProposition some ValueProposition,
    hasActivity only Activity

Class: Partnership
  SubClassOf:
    BusinessModelElement,
    concernsValueConfiguration some ValueConfiguration,
    developedToProvideValueProposition some ValueProposition,
    hasAgreement only Agreement

Class: RevenueModel
  SubClassOf:
    BusinessModelElement,
    builtOnValueProposition some ValueProposition,
    hasRevenueStreamAndPricing only RevenueStreamAndPricing

Class: CostStructure
  SubClassOf:
    BusinessModelElement,
    hasAccount only Account
```

## 구현 시 주의할 점

### OWL에서 하지 말 것

- `수익 = 매출 - 비용` 같은 산술 규칙
- “모든 하위 항목이 반드시 채워져야 한다”는 완전성 검사
- 운영 데이터 품질 검증
- 시점별 집계와 순위 계산

### 나중에 SHACL로 넘길 것

- `Agreement`의 점수 범위 검증
- `RevenueStreamAndPricing`에 `PricingMethod`가 없는 경우 탐지
- `Relationship`에 최소 하나의 `RelationshipMechanism`이 있어야 한다는 운영 규칙
- 프로젝트별 필수 입력 completeness

## 2차 확장: 논문의 평가 축까지 넣는 방법

원 논문은 후반부에서 9개 element를 기준으로 비즈니스 모델을 평가하는 축도 제안한다. 본 청사진에서는 이 부분을 `BusinessModelAssessment` 모듈로 분리해 확장하는 것을 권장한다.

### 권장 확장 클래스

- `BusinessModelAssessment`
- `BusinessModelAssessmentAxis`
- `AssessmentObservation`
- `AssessmentScaleValue`

### 예시 평가 축

- `ValuePropositionValueLeadershipAxis`
- `TargetCustomerMarketShareAxis`
- `DistributionChannelComplexityAxis`
- `RelationshipCustomerIntegrationAxis`
- `ValueConfigurationIntegrationAxis`
- `CapabilitySpreadAxis`
- `PartnershipNetworkednessAxis`
- `CostStructureLowCostLeadershipAxis`
- `RevenueModelRevenueDiversityAxis`

## 구현 로드맵

### Phase 0. source anchoring

- 원 논문과 CEUR 보조 논문에서 용어를 고정한다.
- 로컬 기준본은 [osterwalder_phd_bm_ontology.md](/home/user/Documents/01_Projects/01_Active/obybk/references/literature/converted/osterwalder_phd_bm_ontology/osterwalder_phd_bm_ontology.md)로 통일한다.
- 산출물:
  - `competency_questions.md`
  - `term_freeze.md`

### Phase 1. TBox skeleton

- `BusinessModelDescription`, `BusinessModelPillar`, `BusinessModelElement`, `BusinessModelSubElement`를 만든다.
- 4 pillars, 9 elements, 9+ 보조 엔터티를 전부 빈 껍데기로라도 올린다.
- 산출물:
  - `bmo-core.owl`
  - `bmo-pillars.owl`
  - `bmo-elements.owl`

### Phase 2. property and decomposition

- `hasPillar`, `hasElement`, `hasSubElement`, `valueForCustomer`, `basedOnCapability` 등 핵심 `ObjectProperty`를 올린다.
- 분해 관계와 연관 관계를 구분한다.
- 산출물:
  - `bmo-subelements.owl`

### Phase 3. codelist formalization

- `ReasoningKind`, `ValueLevel`, `PriceLevel`, `PricingMethod` 등 값 범주를 `owl:oneOf` 기반 nominal 집합으로 구현한다.
- 산출물:
  - `bmo-valuations.owl`
  - `bmo-financial.owl`

### Phase 4. conservative restrictions

- 상위 섹션은 `some` 제약으로 걸고, 하위 요소는 `only` 중심으로 제한한다.
- `exactly 1` 같은 강한 제약은 최소화한다.
- 이유는 `Open World Assumption` 하에서 지나친 엄격함이 추후 인스턴스 적재를 방해하기 때문이다.

### Phase 5. example ABox

- 논문 사례 또는 간단한 예시 기업 1개를 넣는다.
- 예시 인스턴스:
  - `bmi:ExampleBusinessModel`
  - `bmi:ExampleValueProposition`
  - `bmi:ExampleTargetCustomer`
  - `bmi:ExampleRevenueModel`
- 산출물:
  - `bmo-examples.ttl`

### Phase 6. reasoner and validation

- `HermiT` 또는 `Pellet`로 논리 일관성을 본다.
- `ROBOT reason`, `ROBOT report`를 자동화한다.
- completeness와 숫자 제약은 `SHACL`로 넘긴다.

### Phase 7. domain specialization

- 이 단계에서 비로소 `공공 모빌리티`, `따릉이`, `공공 서비스 운영` 같은 도메인 하위 온톨로지를 붙인다.
- 현재 `OBYBK`의 `ontology-hybrid`는 이 단계의 `ABox` 및 문서 근거 계층으로 활용할 수 있다.

## 구현 순서 제안

1. 논문 vocabulary를 그대로 반영한 `설명 중심 ontology`를 먼저 만든다.
2. 하위 요소가 비어 있어도 구조를 모두 만든다.
3. 코드리스트를 정식 개체로 분리한다.
4. OWL에서 무거운 운영 규칙을 빼고 SHACL로 옮긴다.
5. 마지막에 `따릉이 BM` 또는 `공공 모빌리티 BM`을 별도 도메인 layer로 연결한다.

## OBYBK 맥락에서의 연결 지점

- 현재 [ttareungi_rag.py](/home/user/Documents/01_Projects/01_Active/obybk/tools/scripts/rag/ttareungi_rag.py)는 `ontology-hybrid` 근거 수집 계층을 담당한다.
- 이 문서의 구조는 그 다음 단계인 `정식 BM ontology`의 `TBox` 설계 기준선이다.
- 장기적으로는 아래처럼 역할이 나뉜다.
  - `ontology-hybrid RAG`: 원천/문서 근거 수집
  - `OWL 2 DL BM ontology`: 개념 스키마와 논리 제약
  - `domain ABox`: 실제 공공 모빌리티/따릉이 인스턴스
  - `SHACL`: 프로젝트별 completeness/정합성 검사

## 최종 판단

- 지금 필요한 것은 “당장 완벽한 하위 채움”이 아니라 “4개 pillar, 9개 section, sub-element, 코드리스트, 속성군을 빠짐없이 OWL 2 DL 가능한 구조로 먼저 세우는 것”이다.
- 이 청사진은 그 목적에 맞게 `전부 넣되, 비어 있는 하위는 비어 있는 상태로 보존`하는 전략을 취한다.
- 따라서 다음 구현 단계는 이 문서를 기준으로 실제 `owl` 파일 골격을 생성하는 작업이 된다.
