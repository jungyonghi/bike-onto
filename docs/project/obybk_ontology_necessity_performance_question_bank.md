# Timestamp: 2026-04-27 19:24:37

# OBYBK 온톨로지 도입 타당성 및 기본 성능 증명 질문셋

## 목적

- `온톨로지 도입 타당성 질문 50개`와 `기본 성능 증명 질문 50개`를 한 문서에서 같이 관리한다.
- 각 질문마다 `기대 호출 DB 쿼리`와 `실제 결과 DB 쿼리 추정`의 차이를 드러내서, 어디서 온톨로지가 필요한지 분별한다.
- 이 문서의 쿼리는 실행용 정식 SQL이 아니라, 현재 OBYBK 데이터 구조를 기준으로 한 `pseudo SQL`과 `실행 스텝 추정`이다.

## 개념 질의 별칭

| 개념 질의 이름 | 현재 물리 데이터 기준 |
| :--- | :--- |
| `Station` | `branch_data` |
| `TripEvent` | `rent_data` |
| `StationHourlyCount` | `count_data` |
| `StationMonthlyUsage` | `uselate_data` |
| `BrokenEvent` | `broken_data` |
| `WeatherObservation` | `weather_data` |
| `SignupAggregate` | `newmeta` |
| `DateBucket` | 비물리 파생 시간 버킷 |

## 해석 규칙

| 컬럼 | 의미 |
| :--- | :--- |
| `기대 호출 DB 쿼리` | 온톨로지 또는 ontology-lite 계층이 있으면 자연스럽게 호출될 개념 질의다. |
| `실제 결과 DB 쿼리 추정` | 현재 Parquet 물리 스키마와 파생 규칙만으로 답하려고 할 때 필요한 조인, CTE, 후처리 흐름이다. |
| `판정` | `높음`은 온톨로지 도입 타당성이 크다는 뜻이고, `낮음`은 DB-only baseline으로 충분하다는 뜻이다. |

## 1. 온톨로지 도입 타당성 질문 50개

| ID | 질문 | 기대 호출 DB 쿼리 | 실제 결과 DB 쿼리 추정 | 판정 |
| :--- | :--- | :--- | :--- | :--- |
| QO01 | 비 오는 출근시간에 가장 빨리 비어가는 대여소는 어디인가? | `StationHourlyCount JOIN WeatherObservation JOIN Station WHERE precipitation > 0 AND hour IN (7,8,9)` | `weather_data`에서 강수 시간 추출 후 `count_data(date_rt, hour_cnt, branchnum)`와 조인하고 `branch_data`로 이름을 붙인 뒤 Python에서 시간별 감소율 계산 | 높음: `비어감`과 `출근시간 shortage episode`가 물리 컬럼이 아니라 파생 개념이다. |
| QO02 | 비가 그친 뒤 2시간 안에 수요가 급회복되는 대여소는 어디인가? | `RecoveryEpisode AFTER WeatherObservation.precipitation_end WITH StationHourlyCount` | `weather_data`로 강수 종료 시점 추출 후 `count_data`를 후행 2시간 window로 다시 스캔하고 slope 계산 | 높음: `회복 episode`와 시간 window 규칙을 개념 계층으로 고정해야 재사용된다. |
| QO03 | 같은 자치구 안에서 날씨 민감도가 가장 높은 대여소와 낮은 대여소는 어디인가? | `WeatherSensitivityProfile BY district, station` | `branch_data.location1`로 자치구 매핑 후 `count_data`와 `weather_data`를 날짜-시간 버킷으로 묶고 상관 또는 변화율을 후처리 | 높음: `날씨 민감도`는 반복 계산되는 파생 속성이라 개념화 가치가 크다. |
| QO04 | 대여소 유형 `sy`별로 비나 눈에 대한 회복력이 다른가? | `Station.type JOIN WeatherObservation JOIN RecoveryEpisode` | `branch_data.sy`를 `count_data`와 조인하고 강수/적설 조건별 회복 시간을 별도 집계 | 높음: `회복력`과 `유형별 resilience`는 단순 집계보다 의미 모델이 필요하다. |
| QO05 | 휴일이면서 비 오는 날에도 수요가 유지되는 대여소는 어디인가? | `StationHourlyCount JOIN WeatherObservation WHERE holiday = 1 AND precipitation > 0` | `weather_data.holiday`와 강수 조건으로 시간대를 잡고 `count_data`를 조인한 뒤 휴일-비 조건 평균 대비 편차 계산 | 높음: `유지된다`는 기준선 대비 편차 판단이 필요하다. |
| QO06 | 기온 급락과 풍속 상승이 동시에 일어난 시간대에 수요가 급감한 대여소는 어디인가? | `WeatherObservation WHERE temp_drop AND windspeed_rise JOIN StationHourlyCount` | `weather_data`에서 연속 시간 차분을 계산하고 해당 버킷을 `count_data`와 조인한 뒤 급감 threshold 적용 | 높음: 복합 기상 이벤트를 일관된 객체로 다루려면 온톨로지가 유리하다. |
| QO07 | 비는 오지 않았지만 가시거리 저하만으로 수요가 무너진 시간대가 있는가? | `WeatherObservation.visibility_low AND precipitation = 0 JOIN StationHourlyCount` | `weather_data` 조건 필터 후 `count_data` 조인, 날짜별 정상선 대비 하락률 계산 | 높음: `가시거리 이벤트`와 `수요 붕괴`가 파생 관계다. |
| QO08 | 눈 오는 아침에도 출근 수요가 유지되는 대여소는 어디인가? | `WeatherObservation.snowfall > 0 JOIN StationHourlyCount morning profile` | 적설 시간 추출 후 `count_data` 아침 구간 집계와 평시 baseline 비교 | 높음: baseline 비교와 event class가 필요하다. |
| QO09 | 폭염 시간대에 오히려 저녁 수요가 늦게 이동하는 대여소는 어디인가? | `WeatherObservation.temperature_high JOIN TripEvent or StationHourlyCount evening shift` | `weather_data`에서 고온 시간 추출 후 `count_data`와 `rent_data`를 조합해 피크 시간 이동량 계산 | 높음: `피크 이동`은 다중 테이블 시퀀스 해석이 필요하다. |
| QO10 | 날씨 변화가 발생한 뒤 수요 변화가 몇 시간 후 따라오는 대여소가 있는가? | `WeatherObservation CHANGE LAGGED TO StationHourlyCount` | `weather_data`와 `count_data`를 여러 lag 버전으로 반복 조인해 최적 지연을 탐색 | 높음: lag relation을 개념으로 고정하면 질의 재사용성이 높다. |
| QO11 | 출근시간에는 대여 시작점이고 퇴근시간에는 반납 종착점으로 바뀌는 대여소는 어디인가? | `TripEvent ROLE start_station vs return_station BY time_band` | `rent_data.branchnum_r`와 `branchnum_b`를 역할 분리 집계한 뒤 `branch_data`로 이름 조인 | 높음: 동일 대여소의 역할 전환을 모델링해야 start/return 혼동을 줄일 수 있다. |
| QO12 | 평일에는 시작점이지만 휴일에는 목적지가 되는 대여소는 어디인가? | `TripEvent station_role BY weekday_or_holiday` | `rent_data`의 timestamp에서 요일을 파생하고 시작/반납 역할을 따로 집계해 비교 | 높음: `station role`을 명시적 관계로 다루는 편이 안전하다. |
| QO13 | 반복적으로 한쪽 방향으로만 수요가 쏠리는 대여소 쌍은 어디인가? | `TripEvent GROUP BY start_station, return_station imbalance corridor` | `rent_data`에서 대여소 쌍별 편도량을 집계하고 기간별 지속성까지 후처리 | 높음: `corridor`와 `지속 imbalance`는 단일 테이블 컬럼명이 아니다. |
| QO14 | 심야 반납이 몰린 뒤 아침 공급 부족이 반복되는 대여소는 어디인가? | `LateNightReturnEpisode PRECEDES MorningShortageEpisode` | `rent_data`에서 심야 반납량 집계 후 다음날 `count_data` 아침 shortage를 연결하는 2단계 질의 | 높음: episode 간 인과 후보를 표현하려면 개념 계층이 필요하다. |
| QO15 | 거치 관련 metric이 낮은데도 회전율이 높은 대여소는 어디인가? | `Station.profile_metric JOIN StationHourlyCount turnover` | `branch_data.ilcd/iqr`와 `count_data`를 묶어 회전율 계산 후 예외 대여소 추출 | 중간-높음: 컬럼 의미가 불명확해 semantic labeling이 중요하다. |
| QO16 | 월별 이용 보조 집계와 시간대 집계가 서로 다른 추세를 보이는 대여소는 어디인가? | `StationMonthlyUsage COMPARE StationHourlyCount BY station` | `uselate_data`와 `count_data`를 월 단위로 재집계해 편차 계산 | 높음: 서로 다른 grain fact 정합성을 관리할 온톨로지 축이 필요하다. |
| QO17 | 대여소 스냅샷 속성 변화가 있어도 같은 운영 개체로 이어 봐야 하는 경우는 무엇인가? | `StationProfileSnapshot CONTINUITY BY station identity` | `branch_data`를 날짜별 self-join해서 이름, 좌표, 위치 변화량을 추적 | 높음: `동일성 continuity`는 raw row 비교보다 identity 모델이 더 중요하다. |
| QO18 | 이름이 바뀌었거나 좌표가 조금 이동한 대여소를 같은 대여소로 볼 수 있는가? | `Station SAME_AS resolution` | `branch_data`의 날짜별 유사 이름, 근접 좌표, 같은 `branchnum` 여부를 조합한 규칙 기반 매칭 | 높음: `same_as`류 관계가 없으면 질문 재사용이 어렵다. |
| QO19 | 날짜에 따라 같은 대여소를 다른 별칭으로 찾더라도 일관되게 응답할 수 있는가? | `Station alias resolution` | `branch_data.branchname` 문자열 정규화와 `branchnum` 매핑을 별도 사전으로 유지해야 함 | 높음: alias 문제는 온톨로지나 canonical dictionary 없이 반복 비용이 크다. |
| QO20 | 자치구가 달라도 유사한 흐름 패턴을 보이는 대여소 군집은 무엇인가? | `StationFlowPattern cluster` | `count_data`와 `rent_data`를 station별 feature vector로 요약한 뒤 DB 밖 군집화 수행 | 높음: `pattern class`가 있어야 설명 가능한 군집 질의가 가능하다. |
| QO21 | 장거리 이동 직후 24시간 내 고장이 자주 나는 자전거는 무엇인가? | `TripEvent.distance_high PRECEDES BrokenEvent WITHIN 24h` | `rent_data.bikenum`과 `broken_data.bikenum`을 시간 window self-join하고 거리 threshold 적용 | 높음: `고장 직전 장거리`는 시간 기반 event relation이다. |
| QO22 | 고장 유형별로 자주 나타나는 대여소-시간대 조합은 무엇인가? | `BrokenEvent.type JOIN Station, DateBucket` | `broken_data`를 `bikenum`으로 `rent_data` 최근 이벤트와 연결해 추정 대여소를 붙이고 시간대별 집계 | 높음: `BrokenEvent` 자체에는 대여소가 없어 관계 추론이 필요하다. |
| QO23 | 짧은 시간 안에 반복 대여된 자전거가 더 자주 고장 나는가? | `TripEvent rapid_turnaround -> BrokenEvent risk` | `rent_data`에서 같은 `bikenum`의 연속 이벤트 간격 계산 후 `broken_data`와 window join | 높음: `rapid turnaround`가 파생 개념이라 개념화 이점이 크다. |
| QO24 | 급격한 기상 악화 직후 고장 이벤트가 늘어나는가? | `WeatherShock PRECEDES BrokenEvent` | `weather_data`로 shock 조건을 만들고 `broken_data`를 날짜-시간 버킷으로 매핑해 집계 | 높음: 외생 이벤트와 고장 event를 같은 시간 ontology 위에서 맞춰야 한다. |
| QO25 | 여러 대여소를 거치며 반복 고장을 보이는 자전거 경로는 무엇인가? | `BikeLifecyclePath WITH repeated BrokenEvent` | `rent_data`로 자전거 경로를 재구성하고 `broken_data`를 삽입해 path sequence 생성 | 높음: 경로 객체가 없으면 반복 시퀀스를 매번 재구성해야 한다. |
| QO26 | 이용량이 많은데 고장은 적은 대여소와, 이용량은 낮은데 고장이 많은 대여소의 차이는 무엇인가? | `Station demand profile COMPARE failure profile` | `count_data` 또는 `rent_data`로 수요 proxy를 만들고 `broken_data`와 연결한 뒤 `branch_data` 특성 비교 | 높음: 서로 다른 의미축을 비교하는 정규화 계층이 필요하다. |
| QO27 | 반납이 많이 몰린 대여소가 이후 고장 자전거를 더 많이 배출하는가? | `ReturnHeavyStation PRECEDES BrokenBikeEmission` | `rent_data.branchnum_b` 집계 후 이후 `broken_data`와 `bikenum`으로 연결해 직전 반납소 추정 | 높음: `반납-heavy station`과 `고장 배출`은 role-aware relation이 필요하다. |
| QO28 | 장거리 유입이 늘어난 뒤 특정 대여소 주변에서 고장이 증가하는가? | `InboundLongTripEpisode -> BrokenEvent hotspot` | `rent_data`에서 `branchnum_b` 기준 장거리 유입을 계산하고 후행 `broken_data`와 연결 | 높음: inflow episode와 failure hotspot을 함께 보는 의미 계층이 필요하다. |
| QO29 | 고장 자전거가 반복적으로 수렴하는 정비 취약 대여소는 어디인가? | `MaintenanceSinkStation` | `broken_data`와 직전 `rent_data` 반납소를 연결해 고장 집중 대여소를 산출 | 높음: `정비 취약` 같은 운영 개념을 명시해야 설명력이 생긴다. |
| QO30 | 고장 기록이 있었는데도 곧바로 다시 대여된 자전거는 무엇인가? | `BrokenEvent FOLLOWED BY TripEvent too_soon` | `broken_data` 후행 `rent_data`를 `bikenum` 기준 시간 조인해 재대여 간격 계산 | 높음: 상태 전이 규칙을 다루는 ontology가 유용하다. |
| QO31 | 시간대 집계상 수요 급증인데 실제 대여 이벤트 증거가 약한 구간은 어디인가? | `StationHourlyCount anomaly WITHOUT matching TripEvent evidence` | `count_data` 급증 구간을 찾고 동일 구간 `rent_data` 건수와 대조 | 높음: `증거 불일치`를 provenance와 confidence로 다뤄야 한다. |
| QO32 | `count_data`와 `rent_data`가 서로 모순되는 날짜-시간-대여소 구간은 어디인가? | `FactConsistencyCheck BETWEEN StationHourlyCount AND TripEvent` | 동일 버킷으로 재집계한 `rent_data`와 `count_data`를 비교하는 정합성 CTE 필요 | 높음: fact 정합성은 ontology-lite의 핵심 검증 축이다. |
| QO33 | 날씨 테이블의 전체 이용량 `count`와 대여소별 집계 총합이 어긋나는 시점은 어디인가? | `WeatherObservation.count COMPARE aggregate(StationHourlyCount)` | `weather_data.count`와 같은 시간의 `count_data` 총합을 비교 | 높음: 서로 다른 source metric 의미를 명시하지 않으면 오해가 생긴다. |
| QO34 | 같은 자치구, 비슷한 날씨인데 회복 속도가 전혀 다른 대여소는 어디인가? | `RecoveryEpisode JOIN StationProfile BY district` | `branch_data.location1` 기준 그룹 내부에서 QO02 방식 회복 시간을 비교 | 높음: `회복 속도`를 재사용 가능한 속성으로 두는 편이 좋다. |
| QO35 | 날씨 변화에도 거의 흔들리지 않는 대여소는 무엇인가? | `WeatherInsensitiveStation` | `weather_data`와 `count_data`를 장기간 조인해 민감도 점수를 만든 뒤 임계값 필터 | 높음: `weather-insensitive`는 derived class 후보다. |
| QO36 | `ilcd`나 `iqr` 같은 프로필 metric이 부족 지속시간과 연결되는가? | `Station.profile_metric -> ShortageDuration` | `branch_data` metric과 `count_data` shortage duration을 결합하는 후처리 필요 | 중간-높음: 컬럼 의미 불명확성 때문에 ontology annotation이 있으면 해석 안정성이 높다. |
| QO37 | 신규 가입자 증가가 있던 달에 어떤 자치구 대여소들이 더 큰 부담을 받았는가? | `SignupAggregate contextualizes Station demand strain` | `newmeta` 월별 증가량과 같은 월 `count_data` 또는 `rent_data`를 자치구 단위로 재집계 | 높음: station key가 없는 월별 메타를 `context evidence`로 다루는 규칙이 필요하다. |
| QO38 | 특정 연령대나 성별 가입자 증가가 주말 대여 패턴 변화와 연결되는가? | `SignupAggregate demographic context -> WeekendTripPattern` | `newmeta(age, gender, new_dt)`와 `rent_data` 주말 집계를 월 단위로 연결하는 느슨한 상관 분석 | 높음: 직접 인과가 아니라 약한 근거라는 점을 ontology에서 표시해야 한다. |
| QO39 | 같은 유형의 대여소라도 자치구마다 비에 대한 회복력이 다른가? | `Station.type + district + RecoveryEpisode` | `branch_data.sy`, `location1`, `count_data`, `weather_data`를 함께 묶은 다차원 집계 | 높음: station type, district, weather event, recovery를 같은 의미 그래프에 두는 편이 낫다. |
| QO40 | 프로필상 수용 여력이 낮아 보이는데 피크 수요를 반복적으로 견디는 대여소는 어디인가? | `Station.profile_capacity_hint vs PeakDemandEpisode` | `branch_data.ilcd/iqr`를 capacity hint로 보고 `count_data` 피크 episode와 비교 | 높음: `capacity hint` 같은 해석 규칙을 고정할 의미 계층이 필요하다. |
| QO41 | 특정 날짜 특정 대여소의 이상 현상을 날씨, 이동, 고장 근거를 묶어 한 번에 설명할 수 있는가? | `Explain StationDayAnomaly USING WeatherObservation, TripEvent, BrokenEvent` | `count_data` 이상 시점을 잡은 뒤 `weather_data`, `rent_data`, `broken_data`, `branch_data`를 따로 조회해 사람이 종합 | 높음: multi-evidence explanation은 온톨로지 도입 명분이 가장 큰 질문이다. |
| QO42 | 서로 부족과 과잉 역할을 번갈아 가지는 대여소 쌍은 어디인가? | `StationPair imbalance swap pattern` | `rent_data`와 `count_data`를 station pair 또는 인접 역할 관점으로 재구성한 후 주기성 탐색 | 높음: `swap pattern`은 관계 중심 질의라 ontology와 궁합이 좋다. |
| QO43 | 스냅샷 변화를 보면 사실상 신설, 이동, 이름변경으로 봐야 하는 대여소 lifecycle 이벤트가 있는가? | `StationLifecycleEvent FROM StationProfileSnapshot` | `branch_data` 날짜별 변화를 self-join하고 규칙 기반으로 lifecycle label 생성 | 높음: lifecycle event를 명시하면 후속 질의 품질이 크게 오른다. |
| QO44 | 어떤 답변은 직접 조인 근거보다 추론 조인 근거가 더 많아서 신뢰도 표기가 필요한가? | `EvidenceGraph WHERE inferred_edges > direct_edges` | 현재는 질의별로 어떤 조인이 logical join인지 사람이 수동 추적해야 함 | 높음: provenance와 confidence edge가 없으면 답변 신뢰도를 통제하기 어렵다. |
| QO45 | 시작 대여소와 반납 대여소를 구분하지 않으면 완전히 다른 결론이 나오는 질문은 무엇인가? | `TripEvent.role-aware query` | `rent_data.branchnum_r`와 `branchnum_b`를 같은 station key로만 보면 오류가 생기므로 역할별 집계가 필요 | 높음: role disambiguation은 ontology-lite의 직접 효과다. |
| QO46 | `cnt_rack` 같은 컬럼이 실제로 무엇을 뜻하는지 모르면 어떤 질문들이 잘못 해석되는가? | `MetricSemanticsCatalog IMPACT ON query set` | 현재는 `count_data.cnt_rack`, `rent_data.cnt_rack`, `cnt_rack_b`를 문맥별로 별도 해석해야 함 | 높음: metric semantics를 ontology property로 정리해야 한다. |
| QO47 | 답변마다 근거 신뢰도와 source priority를 같이 내보내야 하는 질문은 무엇인가? | `Answer WITH evidence_confidence, source_priority` | 현재는 `branch_data`, `count_data`, `rent_data`, `broken_data`, `weather_data`를 동일 가중치처럼 취급하기 쉬움 | 높음: operational QA에서는 confidence model이 필요하다. |
| QO48 | 상위 운영 질문 10개를 가장 적은 class 수로 덮으려면 최소 온톨로지 slice가 무엇인가? | `CoverageQuery OVER classes Station, TripEvent, BrokenEvent, WeatherObservation` | 현재는 문서와 테이블을 수동 비교해 범위 산정 | 높음: 도입 범위 최소화를 위해서도 ontology coverage 관점이 필요하다. |
| QO49 | 질문 커버리지 기준으로 가장 재사용성이 높은 class와 relation은 무엇인가? | `QuestionCoverage BY ontology class or relation` | 현재는 질문셋과 물리 테이블 매핑을 수동으로 세어야 함 | 높음: 설계 우선순위를 정하는 메타 질의다. |
| QO50 | provenance와 confidence edge가 없으면 끝내 답하지 못하는 질문은 어떤 것들인가? | `UnanswerableQuestions WITHOUT provenance and confidence model` | 현재는 `추론 조인`, `약한 근거`, `문맥 보조 근거`를 구조적으로 표현할 테이블이 없음 | 높음: 온톨로지 도입의 핵심 명분을 보여주는 메타 질문이다. |

## 2. 기본 성능 증명 질문 50개

| ID | 질문 | 기대 호출 DB 쿼리 | 실제 결과 DB 쿼리 추정 | 판정 |
| :--- | :--- | :--- | :--- | :--- |
| QP01 | 최신 기준 일자에 등록된 대여소 수는 몇 개인가? | `SELECT COUNT(DISTINCT station_id) FROM Station WHERE snapshot_date = latest` | `SELECT COUNT(DISTINCT branchnum) FROM branch_data WHERE date = (SELECT MAX(date) FROM branch_data)` | 낮음: 단일 dimension 집계라 DB-only benchmark에 적합하다. |
| QP02 | 자치구별 대여소 수는 몇 개인가? | `SELECT district, COUNT(*) FROM Station GROUP BY district` | `SELECT location1, COUNT(DISTINCT branchnum) FROM branch_data WHERE date = latest GROUP BY location1` | 낮음: 단일 테이블 group by다. |
| QP03 | 최신 기준 대여소명과 좌표 목록을 보여줘. | `SELECT station_name, x, y FROM Station WHERE snapshot_date = latest` | `SELECT branchname, branch_x, branch_y FROM branch_data WHERE date = latest` | 낮음: projection 질의다. |
| QP04 | 특정 대여소의 최신 프로필을 보여줘. | `SELECT * FROM Station WHERE station_id = :id AND snapshot_date = latest` | `SELECT * FROM branch_data WHERE branchnum = :id ORDER BY date DESC LIMIT 1` | 낮음: key lookup이다. |
| QP05 | 유형 `sy`별 대여소 수를 보여줘. | `SELECT type, COUNT(*) FROM Station GROUP BY type` | `SELECT sy, COUNT(DISTINCT branchnum) FROM branch_data WHERE date = latest GROUP BY sy` | 낮음: DB-only로 충분하다. |
| QP06 | `iqr` 상위 20개 대여소를 보여줘. | `SELECT station_name, iqr FROM Station ORDER BY iqr DESC LIMIT 20` | `SELECT branchname, iqr FROM branch_data WHERE date = latest ORDER BY iqr DESC LIMIT 20` | 낮음: 정렬 기반 단순 조회다. |
| QP07 | 특정 날짜의 전체 시간대 이용 집계 합은 얼마인가? | `SELECT SUM(hourly_count) FROM StationHourlyCount WHERE date = :d` | `SELECT SUM(cnt_rack) FROM count_data WHERE date_rt = :d` | 낮음: 단일 fact sum이다. |
| QP08 | 특정 대여소의 하루 시간대별 이용량을 보여줘. | `SELECT hour, hourly_count FROM StationHourlyCount WHERE station_id = :id AND date = :d` | `SELECT hour_cnt, cnt_rack FROM count_data WHERE branchnum = :id AND date_rt = :d ORDER BY hour_cnt` | 낮음: 기본 시계열 조회다. |
| QP09 | 특정 날짜 특정 시간대에 이용량이 높은 대여소 상위 20개는 어디인가? | `SELECT station_id, hourly_count FROM StationHourlyCount WHERE date = :d AND hour = :h ORDER BY hourly_count DESC LIMIT 20` | `SELECT branchnum, cnt_rack FROM count_data WHERE date_rt = :d AND hour_cnt = :h ORDER BY cnt_rack DESC LIMIT 20` | 낮음: simple filter + order다. |
| QP10 | 기간 전체에서 대여소별 평균 시간대 이용량을 구해줘. | `SELECT station_id, AVG(hourly_count) FROM StationHourlyCount WHERE date BETWEEN :d1 AND :d2 GROUP BY station_id` | `SELECT branchnum, AVG(cnt_rack) FROM count_data WHERE date_rt BETWEEN :d1 AND :d2 GROUP BY branchnum` | 낮음: 단일 fact aggregate다. |
| QP11 | 자치구별 시간대 이용량 총합을 구해줘. | `SELECT district, SUM(hourly_count) FROM StationHourlyCount JOIN Station GROUP BY district` | `SELECT b.location1, SUM(c.cnt_rack) FROM count_data c JOIN branch_data b ON c.branchnum = b.branchnum AND b.date = c.date_rt GROUP BY b.location1` | 낮음: 1회 조인 baseline이다. |
| QP12 | 기간 전체 시간대 분포를 히스토그램용으로 뽑아줘. | `SELECT hour, SUM(hourly_count) FROM StationHourlyCount GROUP BY hour` | `SELECT hour_cnt, SUM(cnt_rack) FROM count_data WHERE date_rt BETWEEN :d1 AND :d2 GROUP BY hour_cnt` | 낮음: 단순 group by다. |
| QP13 | 특정 기간 총 대여 건수는 몇 건인가? | `SELECT COUNT(*) FROM TripEvent WHERE rent_time BETWEEN :t1 AND :t2` | `SELECT COUNT(*) FROM rent_data WHERE rentt BETWEEN :t1 AND :t2` | 낮음: 큰 테이블 카운트 benchmark로 적합하다. |
| QP14 | 대여 시작 대여소 상위 20개를 구해줘. | `SELECT start_station, COUNT(*) FROM TripEvent GROUP BY start_station ORDER BY COUNT(*) DESC LIMIT 20` | `SELECT branchnum_r, COUNT(*) FROM rent_data GROUP BY branchnum_r ORDER BY COUNT(*) DESC LIMIT 20` | 낮음: 역할이 명시돼 있어 기본 집계가 가능하다. |
| QP15 | 반납 대여소 상위 20개를 구해줘. | `SELECT return_station, COUNT(*) FROM TripEvent GROUP BY return_station ORDER BY COUNT(*) DESC LIMIT 20` | `SELECT branchnum_b, COUNT(*) FROM rent_data GROUP BY branchnum_b ORDER BY COUNT(*) DESC LIMIT 20` | 낮음: 단순 집계다. |
| QP16 | 날짜별 평균 이동거리를 구해줘. | `SELECT date, AVG(distance) FROM TripEvent GROUP BY date` | `SELECT CAST(rentt AS DATE) AS d, AVG(dist) FROM rent_data GROUP BY CAST(rentt AS DATE)` | 낮음: date cast만 추가되면 된다. |
| QP17 | 이동거리가 가장 긴 대여 기록 100건을 보여줘. | `SELECT * FROM TripEvent ORDER BY distance DESC LIMIT 100` | `SELECT * FROM rent_data ORDER BY dist DESC LIMIT 100` | 낮음: 정렬 조회다. |
| QP18 | 특정 자전거가 기간 동안 몇 번 대여됐는지 보여줘. | `SELECT bike_id, COUNT(*) FROM TripEvent WHERE bike_id = :bike GROUP BY bike_id` | `SELECT bikenum, COUNT(*) FROM rent_data WHERE bikenum = :bike GROUP BY bikenum` | 낮음: key filter다. |
| QP19 | 특정 대여소의 시작 대여를 시간대별로 보여줘. | `SELECT hour, COUNT(*) FROM TripEvent WHERE start_station = :id GROUP BY hour` | `SELECT EXTRACT(HOUR FROM rentt) AS h, COUNT(*) FROM rent_data WHERE branchnum_r = :id GROUP BY EXTRACT(HOUR FROM rentt)` | 낮음: 기본 집계다. |
| QP20 | 가장 많이 발생한 시작-반납 대여소 쌍 상위 30개를 구해줘. | `SELECT start_station, return_station, COUNT(*) FROM TripEvent GROUP BY start_station, return_station ORDER BY COUNT(*) DESC LIMIT 30` | `SELECT branchnum_r, branchnum_b, COUNT(*) FROM rent_data GROUP BY branchnum_r, branchnum_b ORDER BY COUNT(*) DESC LIMIT 30` | 낮음: pair aggregate다. |
| QP21 | 날짜별 총 대여 건수를 구해줘. | `SELECT date, COUNT(*) FROM TripEvent GROUP BY date` | `SELECT CAST(rentt AS DATE) AS d, COUNT(*) FROM rent_data GROUP BY CAST(rentt AS DATE)` | 낮음: 기본 time aggregate다. |
| QP22 | 시간대별 총 대여 건수를 구해줘. | `SELECT hour, COUNT(*) FROM TripEvent GROUP BY hour` | `SELECT EXTRACT(HOUR FROM rentt) AS h, COUNT(*) FROM rent_data GROUP BY EXTRACT(HOUR FROM rentt)` | 낮음: 단일 테이블 histogram이다. |
| QP23 | 특정 대여소의 순유출입을 구해줘. | `SELECT station_id, start_count - return_count FROM TripEvent` | `SELECT :id AS branchnum, SUM(CASE WHEN branchnum_r = :id THEN 1 ELSE 0 END) - SUM(CASE WHEN branchnum_b = :id THEN 1 ELSE 0 END) FROM rent_data` | 낮음: 역할 분리만 하면 DB-only로 가능하다. |
| QP24 | 이동거리가 5km 이상인 대여 건수는 몇 건인가? | `SELECT COUNT(*) FROM TripEvent WHERE distance >= 5000` | `SELECT COUNT(*) FROM rent_data WHERE dist >= 5000` | 낮음: threshold filter다. |
| QP25 | 특정 날짜 특정 시간대의 총 대여 건수를 구해줘. | `SELECT COUNT(*) FROM TripEvent WHERE date = :d AND hour = :h` | `SELECT COUNT(*) FROM rent_data WHERE CAST(rentt AS DATE) = :d AND EXTRACT(HOUR FROM rentt) = :h` | 낮음: point-in-time benchmark다. |
| QP26 | 전체 고장 이벤트 수는 몇 개인가? | `SELECT COUNT(*) FROM BrokenEvent` | `SELECT COUNT(*) FROM broken_data` | 낮음: 단일 테이블 카운트다. |
| QP27 | 고장 유형별 건수를 보여줘. | `SELECT failure_type, COUNT(*) FROM BrokenEvent GROUP BY failure_type` | `SELECT type_bk, COUNT(*) FROM broken_data GROUP BY type_bk` | 낮음: category aggregate다. |
| QP28 | 날짜별 고장 건수를 구해줘. | `SELECT date, COUNT(*) FROM BrokenEvent GROUP BY date` | `SELECT CAST(date_bk AS DATE) AS d, COUNT(*) FROM broken_data GROUP BY CAST(date_bk AS DATE)` | 낮음: 기본 시계열 집계다. |
| QP29 | 고장 기록이 가장 많은 자전거 상위 20개를 보여줘. | `SELECT bike_id, COUNT(*) FROM BrokenEvent GROUP BY bike_id ORDER BY COUNT(*) DESC LIMIT 20` | `SELECT bikenum, COUNT(*) FROM broken_data GROUP BY bikenum ORDER BY COUNT(*) DESC LIMIT 20` | 낮음: key aggregate다. |
| QP30 | 시간대별 고장 이벤트 수를 보여줘. | `SELECT hour, COUNT(*) FROM BrokenEvent GROUP BY hour` | `SELECT EXTRACT(HOUR FROM date_bk) AS h, COUNT(*) FROM broken_data GROUP BY EXTRACT(HOUR FROM date_bk)` | 낮음: 파생 hour만 있으면 된다. |
| QP31 | 특정 자전거의 고장 이력을 시간순으로 보여줘. | `SELECT * FROM BrokenEvent WHERE bike_id = :bike ORDER BY broken_time` | `SELECT * FROM broken_data WHERE bikenum = :bike ORDER BY date_bk` | 낮음: lookup 질의다. |
| QP32 | 시간대별 평균 기온을 구해줘. | `SELECT hour, AVG(temperature) FROM WeatherObservation GROUP BY hour` | `SELECT EXTRACT(HOUR FROM datetime) AS h, AVG(temperature) FROM weather_data GROUP BY EXTRACT(HOUR FROM datetime)` | 낮음: 단일 테이블 aggregate다. |
| QP33 | 강수량이 0보다 큰 시간은 총 몇 번인가? | `SELECT COUNT(*) FROM WeatherObservation WHERE precipitation > 0` | `SELECT COUNT(*) FROM weather_data WHERE precipitation > 0` | 낮음: filter count다. |
| QP34 | 풍속이 가장 높았던 시각 상위 20개를 보여줘. | `SELECT observed_at, windspeed FROM WeatherObservation ORDER BY windspeed DESC LIMIT 20` | `SELECT datetime, windspeed FROM weather_data ORDER BY windspeed DESC LIMIT 20` | 낮음: order by 질의다. |
| QP35 | 공휴일 평균 이용량은 얼마인가? | `SELECT AVG(count) FROM WeatherObservation WHERE holiday = 1` | `SELECT AVG(count) FROM weather_data WHERE holiday = 1` | 낮음: 이미 테이블에 holiday와 count가 있다. |
| QP36 | 적설이 있었던 시간대를 보여줘. | `SELECT observed_at, snowfall FROM WeatherObservation WHERE snowfall > 0` | `SELECT datetime, snowfall FROM weather_data WHERE snowfall > 0` | 낮음: 조건 조회다. |
| QP37 | 가시거리가 가장 낮았던 시간대 상위 20개를 보여줘. | `SELECT observed_at, visibility FROM WeatherObservation ORDER BY visibility ASC LIMIT 20` | `SELECT datetime, visibility FROM weather_data ORDER BY visibility ASC LIMIT 20` | 낮음: 정렬 조회다. |
| QP38 | 요일별 평균 이용량을 구해줘. | `SELECT weekday, AVG(count) FROM WeatherObservation GROUP BY weekday` | `SELECT weekday, AVG(count) FROM weather_data GROUP BY weekday` | 낮음: 단일 테이블 group by다. |
| QP39 | 습도가 80 이상인 시간은 몇 번인가? | `SELECT COUNT(*) FROM WeatherObservation WHERE humidity >= 80` | `SELECT COUNT(*) FROM weather_data WHERE humidity >= 80` | 낮음: filter count다. |
| QP40 | 월별 평균 기온을 구해줘. | `SELECT month, AVG(temperature) FROM WeatherObservation GROUP BY month` | `SELECT DATE_TRUNC('month', datetime) AS m, AVG(temperature) FROM weather_data GROUP BY DATE_TRUNC('month', datetime)` | 낮음: date trunc만 있으면 충분하다. |
| QP41 | 월별 신규 가입자 수를 보여줘. | `SELECT month_key, SUM(new_users) FROM SignupAggregate GROUP BY month_key` | `SELECT new_dt, SUM(new) FROM newmeta GROUP BY new_dt` | 낮음: 기본 monthly aggregate다. |
| QP42 | 연령대별 신규 가입자 수를 보여줘. | `SELECT age_band, SUM(new_users) FROM SignupAggregate GROUP BY age_band` | `SELECT age, SUM(new) FROM newmeta GROUP BY age` | 낮음: 단순 group by다. |
| QP43 | 성별별 신규 가입자 수를 보여줘. | `SELECT gender, SUM(new_users) FROM SignupAggregate GROUP BY gender` | `SELECT gender, SUM(new) FROM newmeta GROUP BY gender` | 낮음: basic aggregate다. |
| QP44 | 월-연령대 매트릭스를 만들어줘. | `SELECT month_key, age_band, SUM(new_users) FROM SignupAggregate GROUP BY month_key, age_band` | `SELECT new_dt, age, SUM(new) FROM newmeta GROUP BY new_dt, age` | 낮음: 2차원 피벗용 집계다. |
| QP45 | 월-성별 매트릭스를 만들어줘. | `SELECT month_key, gender, SUM(new_users) FROM SignupAggregate GROUP BY month_key, gender` | `SELECT new_dt, gender, SUM(new) FROM newmeta GROUP BY new_dt, gender` | 낮음: 2차원 집계다. |
| QP46 | 대여소별 월간 이용 보조 집계 총합을 구해줘. | `SELECT station_id, SUM(monthly_usage) FROM StationMonthlyUsage GROUP BY station_id` | `SELECT branchnum, SUM(cnt_r + cnt_b) FROM uselate_data GROUP BY branchnum` | 낮음: 단일 aggregate다. |
| QP47 | 특정 월에 `cnt_r`가 높은 대여소 상위 20개를 보여줘. | `SELECT station_id, cnt_r FROM StationMonthlyUsage WHERE month_key = :m ORDER BY cnt_r DESC LIMIT 20` | `SELECT branchnum, cnt_r FROM uselate_data WHERE date_ym = :m ORDER BY cnt_r DESC LIMIT 20` | 낮음: simple filter + order다. |
| QP48 | 특정 월에 `cnt_b`가 높은 대여소 상위 20개를 보여줘. | `SELECT station_id, cnt_b FROM StationMonthlyUsage WHERE month_key = :m ORDER BY cnt_b DESC LIMIT 20` | `SELECT branchnum, cnt_b FROM uselate_data WHERE date_ym = :m ORDER BY cnt_b DESC LIMIT 20` | 낮음: DB-only benchmark 적합하다. |
| QP49 | 월별 `cnt_r - cnt_b` 순차를 보여줘. | `SELECT month_key, SUM(cnt_r - cnt_b) FROM StationMonthlyUsage GROUP BY month_key` | `SELECT date_ym, SUM(cnt_r - cnt_b) FROM uselate_data GROUP BY date_ym` | 낮음: 계산식이 단순하다. |
| QP50 | 특정 월 상위 이용 대여소 목록에 이름을 붙여줘. | `SELECT Station.name, StationMonthlyUsage.total FROM StationMonthlyUsage JOIN Station` | `SELECT b.branchname, u.cnt_r, u.cnt_b FROM uselate_data u JOIN branch_data b ON u.branchnum = b.branchnum WHERE u.date_ym = :m` | 낮음: 1회 조인으로 충분하다. |

## 3. 권장 측정 필드

| 필드 | 의미 |
| :--- | :--- |
| `latency_ms` | 질문별 총 응답 시간 |
| `rows_scanned_est` | 대략적으로 읽은 row 수 |
| `join_count` | 실제 조인 횟수 |
| `post_sql_steps` | SQL 밖 Python 후처리 단계 수 |
| `evidence_sources` | 사용한 source 수 |
| `answerability` | `direct`, `inferred`, `weak-context`, `unanswerable` 중 하나 |
| `ontology_gain_note` | 온톨로지 계층이 줄여주는 복잡도 요약 |

## 4. 사용 메모

- `QO01`부터 `QO50`은 `DB 질의 복잡도 차이`를 보여주는 용도다.
- `QP01`부터 `QP50`은 `DB-only baseline latency and correctness`를 확인하는 용도다.
- 실측 시에는 같은 질문을 `db-only`, `ontology-lite`, `ontology-hybrid` 3개 프로필로 반복 실행하면 비교가 쉽다.
