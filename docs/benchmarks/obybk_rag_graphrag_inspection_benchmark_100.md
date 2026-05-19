# OBYBK RAG/GraphRAG Inspection Benchmark 100

Validated with a public mobility case-study binding.

- finalized_at: 2026-05-19 21:41:06
- qa_count: 100
- QP01~QP50: 실행형 데이터 질의
- QO01~QO50: relation, metric definition, provenance, review gate가 필요한 inspection 질의

## 001. QP01 · 최신 기준 일자에 등록된 대여소 수는 몇 개인가?

branch_data.parquet에서 기준일 컬럼(date)의 최댓값을 최신 기준일로 산정한다. 해당 date로 필터링한 뒤 COUNT(DISTINCT branchnum)으로 대여소 수를 집계한다. 결과 해석을 위해 최신 기준일(date_max)과 집계값을 함께 반환한다.

- answerability: executable-with-data
- evidence_sources: branch_data.parquet
- requires_review: False
- review_reason: 

## 002. QP02 · 자치구별 대여소 수는 몇 개인가?

branch_data.parquet에서 최신 기준일(date=MAX(date))만 남긴다. 그 스냅샷에서 location1으로 GROUP BY 한 뒤 COUNT(DISTINCT branchnum)으로 자치구별 대여소 수를 계산한다. 필요 시 대여소 수 기준 내림차순 정렬로 상위 구부터 확인한다.

- answerability: executable-with-data
- evidence_sources: branch_data.parquet
- requires_review: False
- review_reason: 

## 003. QP03 · 최신 기준 대여소명과 좌표 목록을 보여줘.

branch_data.parquet에서 최신 기준일(date=MAX(date)) 레코드를 필터링하고, branchname과 좌표 컬럼(branch_x, branch_y)을 선택해 목록으로 반환한다. 지도 시각화나 거리 계산까지 염두에 둔다면 branch_x/branch_y의 좌표계(경위도 여부), 축 순서, 단위를 스키마로 확정한 뒤 동일 규칙으로 출력해야 한다.

- answerability: needs-schema-confirmation
- evidence_sources: branch_data.parquet
- requires_review: True
- review_reason: branch_x/branch_y의 좌표계(경위도/투영), 축 순서, 단위가 확정되지 않으면 좌표 목록을 해석하거나 후속 분석에 안전하게 사용할 수 없다.

## 004. QP04 · 특정 대여소의 최신 프로필을 보여줘.

입력 파라미터로 대여소 식별자(branchnum=:id)를 받아 branch_data.parquet에서 해당 대여소 레코드를 필터링한다. 최신의 정의를 ‘대여소별 최신(date DESC LIMIT 1)’로 둘지, ‘전체 스냅샷의 최신일(date=MAX(date))에서 해당 대여소 1건’으로 둘지 먼저 선택한 뒤 그 기준으로 1건을 반환한다. 프로필에 포함할 컬럼(예: 이름, 자치구, 좌표, 유형 등)은 재현성을 위해 명시적으로 지정한다.

- answerability: needs-parameter
- evidence_sources: branch_data.parquet
- requires_review: True
- review_reason: ‘최신’의 기준(글로벌 스냅샷 최신 vs 대여소별 최신 레코드)과 반환할 프로필 컬럼 범위를 합의해야 결과가 일관된다.

## 005. QP05 · 유형 `sy`별 대여소 수를 보여줘.

branch_data.parquet에서 최신 기준일(date=MAX(date))만 필터링한다. sy로 GROUP BY 한 뒤 COUNT(DISTINCT branchnum)으로 유형별 대여소 수를 집계한다. 필요하면 집계값 내림차순으로 정렬해 분포를 요약한다.

- answerability: executable-with-data
- evidence_sources: branch_data.parquet
- requires_review: False
- review_reason: 

## 006. QP06 · `iqr` 상위 20개 대여소를 보여줘.

branch_data.parquet에서 최신 기준일(date=MAX(date)) 레코드를 대상으로 iqr 내림차순 정렬 후 LIMIT 20을 적용한다. 반환은 최소한 branchnum, branchname, iqr를 포함하고, 동률 처리 재현을 위해 보조 정렬키(예: branchnum ASC)를 명시한다. iqr이 어떤 대상/기간/산식으로 계산된 지표인지 정의가 고정되어야 ‘상위’의 의미가 동일하게 해석된다.

- answerability: needs-metric-definition
- evidence_sources: branch_data.parquet
- requires_review: True
- review_reason: iqr의 산식과 계산 대상이 정의되지 않으면 값의 비교 기준이 불명확해 상위 20개 결과를 평가하기 어렵다.

## 007. QP07 · 특정 날짜의 전체 시간대 이용 집계 합은 얼마인가?

입력 날짜(date_rt=:d)를 받아 count_data.parquet에서 해당 일자를 필터링한 뒤 cnt_rack의 SUM을 계산한다. hour_cnt가 존재한다면 시간대 누락 여부를 점검하고(0~23 전 범위 존재 여부), 누락을 0으로 보정할지 결측으로 유지할지 규칙을 명시한다. 또한 cnt_rack이 ‘이용량’ 팩트인지 다른 성격의 값인지(재고/용량 등) 컬럼 의미가 확인되어야 합계의 해석이 일관된다.

- answerability: needs-parameter
- evidence_sources: count_data.parquet
- requires_review: True
- review_reason: cnt_rack의 의미와 hour_cnt 누락 시간대 처리 규칙이 확정되지 않으면 ‘이용 집계 합’으로 해석하기 어렵다.

## 008. QP08 · 특정 대여소의 하루 시간대별 이용량을 보여줘.

입력 파라미터로 branchnum=:id, date_rt=:d를 받아 count_data.parquet에서 해당 대여소·일자 레코드를 필터링한다. hour_cnt 오름차순으로 정렬해 hour_cnt와 cnt_rack을 시간대별 테이블로 반환한다. hour_cnt가 정시(0~23)인지 구간 코딩인지, 그리고 누락 시간대를 0으로 채울지 결측으로 둘지 기준이 정해져야 동일한 형태의 결과를 만들 수 있다.

- answerability: needs-parameter
- evidence_sources: count_data.parquet
- requires_review: True
- review_reason: hour_cnt의 시간대 정의(정시/구간)와 누락 시간대 처리 기준이 없으면 시간대별 이용량을 일관된 시계열로 구성하기 어렵다.

## 009. QP09 · 특정 날짜 특정 시간대에 이용량이 높은 대여소 상위 20개는 어디인가?

입력 파라미터(date_rt=:d, hour_cnt=:h)로 count_data.parquet을 필터링한 뒤 cnt_rack 내림차순 정렬로 상위 20개를 추출한다. 결과 식별자(branchnum)를 branch_data.parquet과 조인해 대여소명(branchname)을 함께 반환할 수 있다. 이때 branch 메타데이터를 당일 스냅샷(date=:d)으로 볼지 최신 스냅샷(date=MAX(date))으로 볼지 조인 기준을 고정해야 재현 가능한 순위표가 된다.

- answerability: needs-parameter
- evidence_sources: count_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: branch_data를 어떤 date 스냅샷 기준으로 조인할지(당일 vs 최신)를 정하지 않으면 대여소명 매핑이 달라질 수 있다.

## 010. QP10 · 기간 전체에서 대여소별 평균 시간대 이용량을 구해줘.

먼저 ‘평균 시간대 이용량’의 산식을 고정한다(예: 기간 내 모든 시간대 레코드의 AVG(cnt_rack) vs 일자별 24시간 합계를 낸 뒤 그 일합계의 평균). 산식이 ‘레코드 평균’이라면 count_data.parquet에서 date_rt BETWEEN :d1 AND :d2로 필터링 후 branchnum으로 GROUP BY 하여 AVG(cnt_rack)을 계산한다. 산식이 ‘일평균’이라면 (branchnum, date_rt) 단위로 SUM(cnt_rack)을 만든 뒤 그 값을 기간에 대해 AVG하는 2단계 집계를 수행한다. 기간 중 누락된 날짜/시간대가 평균을 왜곡할 수 있으므로 결측 처리 기준도 함께 명시한다.

- answerability: needs-metric-definition
- evidence_sources: count_data.parquet
- requires_review: True
- review_reason: ‘평균’의 산식(레코드 평균 vs 일합계 기반 평균)과 결측 처리 기준이 없으면 동일 질의의 결과를 재현할 수 없다.

## 011. QP11 · 자치구별 시간대 이용량 총합을 구해줘.

count_data.parquet에서 시간대를 나타내는 컬럼(예: hour_cnt 또는 date_rt에서 파생한 hour)을 기준으로 집계 단위를 만들고, 대여소 키인 branchnum으로 branch_data.parquet과 조인해 자치구 컬럼(location1)을 부여한다. 집계는 (location1, hour)로 GROUP BY 한 뒤 SUM(cnt_rack)으로 시간대 이용량 총합을 계산한다. branch_data의 메타가 날짜에 따라 변한다면 count_data.date_rt와 branch_data.date 간 적용일 정합(동일 날짜 또는 유효기간 조인)을 조건으로 포함해 매핑을 고정한다. 결과는 자치구-시간대 순으로 정렬된 테이블 형태로 반환한다.

- answerability: needs-schema-confirmation
- evidence_sources: branch_data.parquet, count_data.parquet
- requires_review: True
- review_reason: location1이 자치구를 의미하는지와 시간대 컬럼의 존재/단위(0~23, 1~24, 30분 단위 등)를 확인해야 동일 기준으로 집계된다.

## 012. QP12 · 기간 전체 시간대 분포를 히스토그램용으로 뽑아줘.

count_data.parquet에서 date_rt에 대해 기간 필터를 적용한다(예: :start_ts~:end_ts). 시간대 컬럼이 존재하면 이를 bin으로 사용하고, 없으면 date_rt에서 시간(hour)을 추출해 bin을 생성한 뒤 GROUP BY 한다. 각 bin의 값은 SUM(cnt_rack) 또는 단순 발생 건수(COUNT(*)) 중 히스토그램의 의미에 맞는 집계로 산출하고, (hour_bin, value) 형태로 반환한다. 마지막으로 hour_bin 오름차순으로 정렬해 시각화 입력으로 바로 사용할 수 있게 한다.

- answerability: needs-parameter
- evidence_sources: count_data.parquet
- requires_review: False
- review_reason: 

## 013. QP13 · 특정 기간 총 대여 건수는 몇 건인가?

rent_data.parquet에서 대여 시각 컬럼 rentt에 대해 기간 조건을 적용한다(예: rentt >= :start_ts AND rentt < :end_ts). 필터링된 행에 대해 COUNT(*)를 계산하면 해당 기간의 총 대여 건수가 된다. 반환은 단일 스칼라(총 건수)로 제공한다.

- answerability: needs-parameter
- evidence_sources: rent_data.parquet
- requires_review: False
- review_reason: 

## 014. QP14 · 대여 시작 대여소 상위 20개를 구해줘.

rent_data.parquet에서 시작 대여소 식별자 branchnum_r로 GROUP BY 한 뒤 COUNT(*)를 집계한다. 집계 결과를 대여 건수 내림차순으로 정렬하고 LIMIT 20을 적용해 상위 20개를 반환한다. 표시용 메타가 필요하면 branch_data.parquet을 branchnum=branchnum_r로 조인해 location1 등 식별 컬럼을 함께 선택한다.

- answerability: executable-with-data
- evidence_sources: rent_data.parquet, branch_data.parquet
- requires_review: False
- review_reason: 

## 015. QP15 · 반납 대여소 상위 20개를 구해줘.

rent_data.parquet에서 반납 대여소 식별자 branchnum_b로 GROUP BY 하고 COUNT(*)로 반납 건수를 계산한다. 반납 건수 내림차순으로 정렬한 뒤 LIMIT 20을 적용한다. 필요 시 branch_data.parquet을 branchnum=branchnum_b로 조인해 대여소 메타 컬럼을 함께 반환한다.

- answerability: executable-with-data
- evidence_sources: rent_data.parquet, branch_data.parquet
- requires_review: False
- review_reason: 

## 016. QP16 · 날짜별 평균 이동거리를 구해줘.

rent_data.parquet에서 rentt를 날짜로 변환해 일자(date)를 만들고 date로 GROUP BY 하여 AVG(dist)를 계산한다. 평균 계산에 포함할 dist의 유효 범위(예: NULL 제외, 0/음수 제외, 상한 절단 여부)와 dist 단위(km/m) 및 산출 방식(직선거리/경로거리)은 동일한 규칙으로 고정해야 일자별 비교가 재현된다. 결과는 (date, avg_dist) 형태로 날짜 오름차순 정렬해 반환한다.

- answerability: needs-schema-confirmation
- evidence_sources: rent_data.parquet
- requires_review: True
- review_reason: dist의 단위와 결측/이상치 처리 규칙이 확정되지 않으면 날짜별 평균 이동거리 해석이 일관되지 않다.

## 017. QP17 · 이동거리가 가장 긴 대여 기록 100건을 보여줘.

rent_data.parquet에서 dist가 NULL이 아닌 행을 대상으로 dist 내림차순 정렬 후 LIMIT 100을 적용한다. 반환 컬럼은 분석에 필요한 최소 집합(예: bikenum, rentt, branchnum_r, branchnum_b, dist)으로 제한해 노출을 통제한다. 상위 구간에는 센서/입력 오류로 보이는 비현실적 값이 섞일 수 있으므로, 최종 활용 전에는 이상치 판정 기준(상한, IQR 기반, 물리적 이동 한계 등)을 함께 검토한다.

- answerability: needs-human-review
- evidence_sources: rent_data.parquet
- requires_review: True
- review_reason: 상위 dist 레코드는 산출 가능하지만 노출 컬럼 최소화(민감정보 가능성)와 이상치 판정 기준에 대한 사람 검토가 필요하다.

## 018. QP18 · 특정 자전거가 기간 동안 몇 번 대여됐는지 보여줘.

rent_data.parquet에서 bikenum = :bike_id로 필터링하고, rentt에 기간 조건을 추가한다(예: :start_ts~:end_ts). 필터링 결과에 대해 COUNT(*)를 계산하면 해당 자전거의 기간 내 대여 횟수다. 반환은 단일 값(대여 횟수) 또는 자전거 ID와 함께 (bikenum, rent_count) 형태로 제공한다.

- answerability: needs-parameter
- evidence_sources: rent_data.parquet
- requires_review: False
- review_reason: 

## 019. QP19 · 특정 대여소의 시작 대여를 시간대별로 보여줘.

rent_data.parquet에서 시작 대여소 branchnum_r = :branch_id로 필터링한다. rentt에서 시간(hour)을 추출해 hour로 GROUP BY 하고 COUNT(*)로 시간대별 시작 대여 건수를 계산한다. 필요하면 rentt 기간 조건(:start_ts~:end_ts)을 추가하고, 결과는 hour 오름차순으로 (hour, start_count) 형태로 반환한다.

- answerability: needs-parameter
- evidence_sources: rent_data.parquet
- requires_review: False
- review_reason: 

## 020. QP20 · 가장 많이 발생한 시작-반납 대여소 쌍 상위 30개를 구해줘.

rent_data.parquet에서 (branchnum_r, branchnum_b) 조합으로 GROUP BY 한 뒤 COUNT(*)를 집계하고, 건수 내림차순 정렬 후 LIMIT 30을 적용한다. 시작=반납(동일 대여소 회귀)을 포함할지 여부는 결과 순위를 바꾸므로 분석 기준을 먼저 선택하고, 필요 시 branchnum_r <> branchnum_b 조건으로 제외한다. 대여소 이름/지역 등 메타를 붙이려면 branch_data.parquet을 시작용/반납용으로 각각 별칭을 두고 2회 조인해 표시 컬럼을 추가한다.

- answerability: needs-human-review
- evidence_sources: rent_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 시작=반납 포함 여부가 결과를 크게 바꿀 수 있어 기준 합의가 필요하고, 시작/반납 메타를 위한 동일 테이블 2회 조인 설계를 사람이 확인해야 한다.

## 021. QP21 · 날짜별 총 대여 건수를 구해줘.

rent_data.parquet에서 대여 시각 컬럼 rentt를 날짜 단위로 절단해 일자별 대여 건수를 집계한다. 구현은 CAST(rentt AS DATE) 또는 DATE_TRUNC('day', rentt)로 date를 만들고, date별 COUNT(*)를 계산한다. 결과는 date 오름차순으로 정렬해 반환한다.

- answerability: needs-schema-confirmation
- evidence_sources: rent_data.parquet
- requires_review: True
- review_reason: rentt의 타임존/로컬시간 기준과 날짜 경계(일자 절단 기준)가 확정되지 않으면 일자별 집계 결과가 달라질 수 있다.

## 022. QP22 · 시간대별 총 대여 건수를 구해줘.

rent_data.parquet의 rentt에서 시간대(0~23시)를 추출해 시간대별 대여 건수를 집계한다. EXTRACT(HOUR FROM rentt)로 hour를 만들고 hour별 COUNT(*)를 계산한다. 반환은 hour 오름차순(또는 건수 내림차순)으로 정렬한다.

- answerability: needs-schema-confirmation
- evidence_sources: rent_data.parquet
- requires_review: True
- review_reason: rენტt의 타임존(UTC/로컬)과 시간 추출 기준이 확인되지 않으면 시간대별 분포 해석과 집계 값이 달라진다.

## 023. QP23 · 특정 대여소의 순유출입을 구해줘.

대여소 ID를 입력받아, rent_data.parquet에서 해당 ID의 유입(반납) 건수와 유출(대여 시작) 건수를 각각 집계한 뒤 ‘유입−유출’로 순유출입을 계산한다. 계산은 SUM(CASE WHEN branchnum_r = :branch_id THEN 1 END)와 SUM(CASE WHEN branchnum_b = :branch_id THEN 1 END)을 사용하며, 필요 시 rentt로 기간 필터를 추가한다. branch_data.parquet는 입력된 대여소 ID가 유효한지 확인하거나 메타정보 매핑에만 사용한다.

- answerability: needs-schema-confirmation
- evidence_sources: rent_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: branchnum_b/branchnum_r가 각각 대여 시작/반납 지점을 의미하는지 확정되지 않으면 순유출입의 부호와 해석이 뒤바뀔 수 있다.

## 024. QP24 · 이동거리가 5km 이상인 대여 건수는 몇 건인가?

rent_data.parquet에서 dist가 5km 이상인 행만 필터링한 뒤 COUNT(*)로 건수를 산출한다. 임계값은 dist의 저장 단위에 맞춰 설정하며, 예를 들어 dist가 km면 dist >= 5, m면 dist >= 5000으로 비교한다. 반환은 단일 스칼라(건수)로 출력한다.

- answerability: needs-schema-confirmation
- evidence_sources: rent_data.parquet
- requires_review: True
- review_reason: dist의 단위(예: m/km)와 결측/이상치 처리 규칙이 확인되지 않으면 ‘5km 이상’ 필터 조건을 재현 가능하게 고정할 수 없다.

## 025. QP25 · 특정 날짜 특정 시간대의 총 대여 건수를 구해줘.

입력 날짜(:d)와 시간대(:h, 0~23)를 기준으로 rent_data.parquet를 필터링한 뒤 COUNT(*)로 대여 건수를 계산한다. 조건은 CAST(rentt AS DATE) = :d AND EXTRACT(HOUR FROM rentt) = :h 형태로 적용한다. 결과는 단일 건수로 반환한다.

- answerability: needs-parameter
- evidence_sources: rent_data.parquet
- requires_review: False
- review_reason: 

## 026. QP26 · 전체 고장 이벤트 수는 몇 개인가?

broken_data.parquet의 전체 행 수를 COUNT(*)로 집계해 전체 고장 이벤트 수를 산출한다. 반환은 단일 스칼라(총 이벤트 수)로 출력한다.

- answerability: executable-with-data
- evidence_sources: broken_data.parquet
- requires_review: False
- review_reason: 

## 027. QP27 · 고장 유형별 건수를 보여줘.

broken_data.parquet에서 고장 유형 컬럼 type_bk를 기준으로 그룹화하고, 유형별 COUNT(*)를 집계한다. 결과는 cnt 내림차순으로 정렬해 어떤 유형이 빈번한지 바로 확인 가능하게 반환한다.

- answerability: executable-with-data
- evidence_sources: broken_data.parquet
- requires_review: False
- review_reason: 

## 028. QP28 · 날짜별 고장 건수를 구해줘.

broken_data.parquet의 date_bk를 날짜 단위로 정규화한 뒤 일자별 고장 이벤트 건수를 집계한다. CAST(date_bk AS DATE) 또는 DATE_TRUNC('day', date_bk)로 date를 만든 다음 date별 COUNT(*)를 계산한다. 반환은 date 오름차순으로 정렬한다.

- answerability: needs-schema-confirmation
- evidence_sources: broken_data.parquet
- requires_review: True
- review_reason: date_bk의 타입(문자열/타임스탬프)과 타임존/포맷이 불명확하면 날짜 변환 기준이 달라져 일자별 집계가 흔들릴 수 있다.

## 029. QP29 · 고장 기록이 가장 많은 자전거 상위 20개를 보여줘.

broken_data.parquet에서 자전거 식별자 bikenum 기준으로 그룹화해 고장 이벤트 수를 COUNT(*)로 집계한다. 집계 결과를 cnt 내림차순으로 정렬하고 상위 20개를 LIMIT 20으로 반환한다. 출력 컬럼은 bikenum과 cnt로 구성한다.

- answerability: executable-with-data
- evidence_sources: broken_data.parquet
- requires_review: False
- review_reason: 

## 030. QP30 · 시간대별 고장 이벤트 수를 보여줘.

broken_data.parquet의 date_bk에서 시간대(0~23시)를 추출해 시간대별 고장 이벤트 건수를 집계한다. EXTRACT(HOUR FROM date_bk)로 hour를 만든 뒤 hour별 COUNT(*)를 계산하고, 결과는 hour 오름차순으로 정렬한다. date_bk에 시간 정보가 없다면 해당 항목은 일자 단위 집계로만 해석해야 한다.

- answerability: needs-schema-confirmation
- evidence_sources: broken_data.parquet
- requires_review: True
- review_reason: date_bk에 시각 정보 포함 여부와 타임존 기준이 확인되지 않으면 시간대별 집계의 의미가 없거나 값이 왜곡될 수 있다.

## 031. QP31 · 특정 자전거의 고장 이력을 시간순으로 보여줘.

broken_data.parquet에서 bikenum = :bikenum 으로 대상 자전거를 필터링한 뒤, date_bk를 오름차순으로 정렬해 고장 이벤트를 나열한다. 최소 반환 컬럼은 bikenum, date_bk이며, 원본에 고장 코드/유형/처리 상태 등의 속성이 있으면 함께 포함해 이력 해석에 활용한다. 출력은 이벤트 단위 레코드 리스트 형태로 제공한다.

- answerability: needs-parameter
- evidence_sources: broken_data.parquet
- requires_review: False
- review_reason: 

## 032. QP32 · 시간대별 평균 기온을 구해줘.

weather_data.parquet에서 datetime에서 시간(hour)을 추출한 값을 기준으로 그룹화하고, 각 시간대의 temperature 평균을 계산한다. 결과는 hour와 avg_temperature를 포함하며, hour 오름차순으로 정렬해 반환한다. 시간대 집계의 기준(UTC/로컬)과 일광절약시간제(DST) 적용 여부에 따라 ‘몇 시’의 의미가 달라지므로, datetime의 기준 시각 체계를 먼저 확정한 뒤 동일 규칙으로 산출한다.

- answerability: needs-schema-confirmation
- evidence_sources: weather_data.parquet
- requires_review: True
- review_reason: datetime의 타임존/기준시(UTC vs 로컬) 및 DST 처리 규칙이 확정돼야 시간대별 집계의 ‘시간’ 의미가 일관된다.

## 033. QP33 · 강수량이 0보다 큰 시간은 총 몇 번인가?

weather_data.parquet에서 precipitation > 0 조건을 만족하는 레코드 수를 COUNT(*)로 계산한다. 결측치가 존재할 수 있으므로 precipitation IS NOT NULL 조건 포함 여부를 함께 고정하고, 비정상 값(예: 음수)이 있다면 제외 규칙을 명시한다. 이 COUNT를 ‘비가 온 시간 수’로 해석하려면 1레코드가 특정 시간 구간(예: 1시간)을 대표하는지, 그리고 precipitation이 구간 누적/순간값 중 무엇인지가 확인되어야 한다.

- answerability: needs-schema-confirmation
- evidence_sources: weather_data.parquet
- requires_review: True
- review_reason: precipitation의 시간 해상도(1행=1시간 여부)와 누적/순간값 및 단위 정의가 확정돼야 COUNT를 ‘시간 수’로 해석할 수 있다.

## 034. QP34 · 풍속이 가장 높았던 시각 상위 20개를 보여줘.

weather_data.parquet에서 windspeed가 NULL이 아닌 레코드만 대상으로 windspeed 내림차순으로 정렬해 상위 20건을 조회한다. 반환 컬럼은 최소 datetime, windspeed로 하며, 동률 발생 시 재현성을 위해 datetime 오름차순 등의 보조 정렬키를 추가한다. 결과는 상위 20개 레코드 리스트로 제공한다.

- answerability: executable-with-data
- evidence_sources: weather_data.parquet
- requires_review: False
- review_reason: 

## 035. QP35 · 공휴일 평균 이용량은 얼마인가?

weather_data.parquet에서 holiday가 공휴일을 의미하는 값으로 표시된 레코드만 필터링한 뒤, count의 평균을 계산한다. 결과는 단일 값(평균 이용량)으로 반환한다. 단, holiday의 인코딩 규칙(예: 1/0, Y/N)과 count가 의미하는 이용량의 정의(대여 건수인지, 특정 시간 단위 집계인지)를 동일 문서 기준으로 고정해야 해석이 일관된다.

- answerability: needs-schema-confirmation
- evidence_sources: weather_data.parquet
- requires_review: True
- review_reason: holiday 인코딩과 count가 나타내는 이용량의 집계 단위/의미가 확정돼야 올바르게 필터링하고 결과를 해석할 수 있다.

## 036. QP36 · 적설이 있었던 시간대를 보여줘.

weather_data.parquet에서 snowfall > 0 조건으로 적설 관측 레코드를 필터링하고, datetime(필요 시 snowfall 포함)을 시간순으로 반환한다. 0과 NULL이 각각 ‘무적설’과 ‘결측/미관측’을 무엇으로 의미하는지에 따라 포함 범위가 달라질 수 있으므로, 보고 목적에 맞게 결측 처리 규칙을 먼저 정한다. 적설량 단위가 존재한다면 함께 명시해 후속 해석에서 혼선을 줄인다.

- answerability: needs-schema-confirmation
- evidence_sources: weather_data.parquet
- requires_review: True
- review_reason: snowfall의 단위와 0/NULL 값의 의미(무적설 vs 결측/미관측)가 확정돼야 필터 기준이 재현된다.

## 037. QP37 · 가시거리가 가장 낮았던 시간대 상위 20개를 보여줘.

weather_data.parquet에서 visibility가 NULL이 아닌 레코드를 대상으로 visibility 오름차순으로 정렬해 최저값 기준 상위 20건을 조회한다. 반환은 datetime, visibility를 포함하며, 동률 시에는 datetime 등을 보조 정렬키로 추가해 결과 순서를 고정한다. visibility의 유효 범위(예: 0의 의미, 음수/이상치 존재 여부)에 따라 사전 필터(예: visibility > 0)가 필요할 수 있으므로 적용 규칙을 명시한다.

- answerability: needs-schema-confirmation
- evidence_sources: weather_data.parquet
- requires_review: True
- review_reason: visibility의 단위·유효범위와 0/이상치 처리 규칙이 확정돼야 ‘최저 가시거리’ 상위 20개가 왜곡되지 않는다.

## 038. QP38 · 요일별 평균 이용량을 구해줘.

weather_data.parquet에서 weekday로 그룹화하고, 각 요일의 count 평균을 계산해 요일별 평균 이용량을 산출한다. 결과는 weekday와 avg_count를 포함하며 weekday 기준으로 정렬해 반환한다. weekday가 숫자(0~6)인지 문자열인지, 그리고 숫자일 경우 어떤 요일부터 시작하는지에 따라 라벨링과 정렬이 달라지므로 코딩 규칙을 확인한 뒤 출력 표기를 고정한다.

- answerability: needs-schema-confirmation
- evidence_sources: weather_data.parquet
- requires_review: True
- review_reason: weekday의 코딩 규칙(값 범위와 요일 매핑)이 확정돼야 요일별 결과를 올바르게 라벨링·정렬할 수 있다.

## 039. QP39 · 습도가 80 이상인 시간은 몇 번인가?

weather_data.parquet에서 humidity >= 80 조건을 만족하는 레코드 수를 COUNT(*)로 계산한다. 결측치(NULL) 및 비정상 값이 존재할 수 있으므로 포함/제외 규칙을 명시하고 동일 기준으로 집계한다. 이 값을 ‘습도 80 이상인 시간 횟수’로 해석하려면 데이터가 시간 단위 관측(예: 1행=1시간)인지와 humidity의 단위/스케일(일반적으로 %)이 확인되어야 한다.

- answerability: needs-schema-confirmation
- evidence_sources: weather_data.parquet
- requires_review: True
- review_reason: 레코드의 시간 해상도(1행=1시간 여부)와 humidity 단위/결측 처리 규칙이 확정돼야 COUNT를 ‘시간 횟수’로 해석할 수 있다.

## 040. QP40 · 월별 평균 기온을 구해줘.

weather_data.parquet에서 datetime을 월 단위로 버킷팅(예: 월 시작 시각으로 절단)한 뒤, 월별로 temperature 평균을 계산한다. 결과는 month, avg_temperature 형태로 반환하고 month 오름차순으로 정렬한다. 월 경계는 타임존과 DST의 영향을 받을 수 있으므로, datetime이 어떤 기준 시각 체계로 저장되었는지 확인한 뒤 동일 기준으로 월 집계를 수행한다.

- answerability: needs-schema-confirmation
- evidence_sources: weather_data.parquet
- requires_review: True
- review_reason: datetime의 타임존/기준시 및 DST 처리 규칙이 확정돼야 월 경계가 일관되어 월별 평균을 재현할 수 있다.

## 041. QP41 · 월별 신규 가입자 수를 보여줘.

newmeta.parquet에서 신규 가입 일자 컬럼(new_dt)을 월 단위로 묶어 집계 키를 만든다(월 단위 컬럼이 이미 있으면 그 컬럼을 사용). 해당 월 키로 GROUP BY 후 신규 가입자 수 컬럼(new)을 SUM 집계하여 월별 합계를 산출한다. 결과는 [월 키, monthly_new] 형태로 반환하고 월 키 오름차순으로 정렬한다.

- answerability: executable-with-data
- evidence_sources: newmeta.parquet
- requires_review: False
- review_reason: 

## 042. QP42 · 연령대별 신규 가입자 수를 보여줘.

newmeta.parquet에서 연령 관련 컬럼(age)이 ‘구간 라벨(예: 20대)’인지 ‘정수 나이(예: 23)’인지 먼저 확인한다. 구간 라벨이라면 age로 GROUP BY 후 new를 SUM 집계해 연령대별 신규 가입자 수를 반환한다. 정수 나이라면 버킷 기준(예: 10–19, 20–29 등)으로 age_band를 파생한 뒤 age_band로 재집계해야 결과가 재현된다. 결측/이상치 연령을 제외할지 별도 범주로 둘지도 동일하게 고정한다.

- answerability: needs-schema-confirmation
- evidence_sources: newmeta.parquet
- requires_review: True
- review_reason: age가 정수 나이인지 이미 구간화된 연령대 라벨인지에 따라 버킷 생성 및 집계 축이 달라진다.

## 043. QP43 · 성별별 신규 가입자 수를 보여줘.

newmeta.parquet에서 성별 컬럼(gender)을 기준으로 GROUP BY 하고 신규 가입자 수(new)를 SUM 집계한다. 출력은 [gender, gender_new]처럼 성별 값과 집계값을 함께 제공하면 된다. 다만 gender의 코드 체계(M/F, 0/1, 기타/미상 포함 여부)와 결측값 처리(제외 vs ‘미상’ 유지)를 확정해야 범주 수와 라벨이 흔들리지 않는다.

- answerability: needs-schema-confirmation
- evidence_sources: newmeta.parquet
- requires_review: True
- review_reason: gender의 코드/범주 정의와 결측 처리 규칙이 확정돼야 성별별 집계 결과가 일관되게 재현된다.

## 044. QP44 · 월-연령대 매트릭스를 만들어줘.

newmeta.parquet에서 월 키(예: new_dt를 월 단위로 변환한 값)와 연령대 축을 만들고, 두 축으로 GROUP BY 한 뒤 new를 SUM 집계하여 셀 값을 만든다. 산출 테이블은 [월 키, age_band(또는 age), cell_new] 형태로 반환하고, 필요하면 월 키를 행/연령대를 열로 피벗해 매트릭스로 변환한다. age가 정수 나이라면 연령대 버킷 기준을 먼저 고정해야 하며, new_dt의 월 표현(월 시작일/문자열 등)도 정렬과 피벗의 일관성을 위해 확인한다.

- answerability: needs-schema-confirmation
- evidence_sources: newmeta.parquet
- requires_review: True
- review_reason: 연령대 버킷(또는 age의 의미)과 월 키 표현 형식이 확정되지 않으면 매트릭스 축 정의가 달라질 수 있다.

## 045. QP45 · 월-성별 매트릭스를 만들어줘.

newmeta.parquet에서 월 키(예: new_dt를 월 단위로 변환)와 성별(gender)을 2차원 집계 키로 두고 GROUP BY 후 new를 SUM 집계해 셀 값을 만든다. 결과는 [월 키, gender, cell_new] 형태로 제공하고, 보고 목적이면 월을 행으로 두고 gender를 열로 피벗해 매트릭스로 표현한다. gender의 범주(미상/기타 포함)와 결측 처리 규칙을 고정해야 열 구성이 변하지 않는다.

- answerability: needs-schema-confirmation
- evidence_sources: newmeta.parquet
- requires_review: True
- review_reason: gender 범주 정의 및 결측 처리 방식에 따라 매트릭스 열 구성과 비교 해석이 달라진다.

## 046. QP46 · 대여소별 월간 이용 보조 집계 총합을 구해줘.

uselate_data.parquet에서 ‘월간’ 집계를 위한 월 키 컬럼(예: date_ym)이 존재하는지 확인하고, 존재한다면 [date_ym, branchnum]으로 GROUP BY 한다. 집계값은 SUM(cnt_r) + SUM(cnt_b)로 정의해 대여/반납 보조 집계의 월간 총합을 산출한다. 출력은 [date_ym, branchnum, total_usage]로 반환하며, 대여소명이 필요하면 branch_data.parquet를 branchnum으로 조인해 이름 컬럼을 추가한다.

- answerability: needs-schema-confirmation
- evidence_sources: uselate_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: uselate_data에 월 집계 키(date_ym 등)가 있는지와 해당 키의 정의(월 경계/형식)를 확인해야 ‘월간’ 집계가 성립한다.

## 047. QP47 · 특정 월에 `cnt_r`가 높은 대여소 상위 20개를 보여줘.

uselate_data.parquet에서 월 키(date_ym)를 입력 월로 필터링한다. branchnum 단위로 cnt_r를 기준으로 내림차순 정렬하고 LIMIT 20을 적용해 상위 20개를 반환한다(필요 시 branchnum별로 사전 집계가 필요한지 여부는 데이터 그레인에 맞춘다). 대여소명을 함께 제공하려면 branch_data.parquet를 branchnum으로 조인해 이름 컬럼을 추가한다.

- answerability: needs-parameter
- evidence_sources: uselate_data.parquet, branch_data.parquet
- requires_review: False
- review_reason: 

## 048. QP48 · 특정 월에 `cnt_b`가 높은 대여소 상위 20개를 보여줘.

uselate_data.parquet에서 date_ym을 입력 월로 제한한 뒤 branchnum과 cnt_b를 기준으로 순위를 만든다. cnt_b 내림차순으로 ORDER BY 하고 LIMIT 20으로 상위 대여소를 선택해 반환한다(데이터가 일/건 단위면 branchnum별 SUM(cnt_b)로 먼저 집계). 대여소명 표기가 필요하면 branch_data.parquet를 branchnum으로 조인해 이름 컬럼을 붙인다.

- answerability: needs-parameter
- evidence_sources: uselate_data.parquet, branch_data.parquet
- requires_review: False
- review_reason: 

## 049. QP49 · 월별 `cnt_r - cnt_b` 순차를 보여줘.

uselate_data.parquet에서 date_ym으로 GROUP BY 하여 월별 합계를 만든다. 월별 차이는 net_diff = SUM(cnt_r) - SUM(cnt_b)로 계산해 반환하고, 해석을 위해 SUM(cnt_r), SUM(cnt_b)를 함께 제공할 수도 있다. 결과는 date_ym 오름차순으로 정렬해 월별 추이를 확인 가능하게 구성한다.

- answerability: executable-with-data
- evidence_sources: uselate_data.parquet
- requires_review: False
- review_reason: 

## 050. QP50 · 특정 월 상위 이용 대여소 목록에 이름을 붙여줘.

‘상위 이용’의 정렬 지표를 먼저 고정한다(예: total_usage = cnt_r + cnt_b, 또는 cnt_r만, 또는 cnt_b만). 그다음 uselate_data.parquet에서 date_ym을 입력 월로 필터링하고, 선택한 지표를 기준으로 내림차순 정렬해 상위 N개 대여소(branchnum)를 선택한다. 마지막으로 branch_data.parquet를 branchnum으로 조인해 branchname을 추가하여 [순위, branchnum, branchname, 지표값] 형태로 출력한다. 동률 처리(공동 순위 포함 여부)와 N 값이 정해져야 동일 조건으로 재현 가능하다.

- answerability: needs-metric-definition
- evidence_sources: uselate_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: ‘상위 이용’의 정렬 지표(총합/대여/반납)와 상위 N·동률 처리 규칙이 확정돼야 결과가 일관되게 산출된다.

## 051. QO01 · 비 오는 출근시간에 가장 빨리 비어가는 대여소는 어디인가?

먼저 ‘비어간다’를 관측 가능한 값으로 고정해야 한다. count_data.parquet의 hour_cnt가 시간대별 재고(잔여 대수)라면, weather_data.parquet에서 precipitation>0인 시간 중 출근시간(예: 07–09시)을 필터링한 뒤 branchnum별로 hour_cnt의 시간차(Δ) 또는 감소율을 계산해 감소 속도가 가장 큰 대여소를 순위화한다. 반대로 hour_cnt가 대여/반납 같은 흐름 카운트라면 ‘비어감’은 직접 계산되지 않으므로, 재고 테이블 추가 또는 ‘순유출(대여-반납)’을 비어감의 대리 지표로 쓸지부터 결정해야 한다. 결과 표시는 branch_data.parquet로 branchnum을 대여소 메타정보에 매핑해 해석 가능한 형태로 제공한다.

- answerability: needs-metric-definition
- evidence_sources: count_data.parquet, weather_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: hour_cnt의 의미(재고 vs 흐름)와 ‘비어감/감소속도’ 산식, 출근시간 범위를 확정해야 동일한 기준으로 비교가 가능하다.

## 052. QO02 · 비가 그친 뒤 2시간 안에 수요가 급회복되는 대여소는 어디인가?

강수 ‘종료 시점’을 이벤트로 정의한 뒤, 종료 후 2시간 구간에서 수요가 얼마나 회복했는지의 KPI를 정해 대여소를 비교한다. weather_data.parquet에서 precipitation이 0으로 전환되는 시각을 종료로 볼지, 0이 n시간 연속 지속될 때 종료로 볼지 등 종료 규칙과 간헐 강수 병합/분할 규칙을 먼저 고정한다. 회복은 예를 들어 (a) 종료 후 2시간 내 baseline 대비 회복률, (b) 종료 이후 증가 기울기, (c) baseline 도달까지 걸린 시간 중 하나로 정의하며 baseline(비 없는 동일 요일·동일 시간대 평균 등)과 임계치를 함께 명시해야 재현된다. 정의가 확정되면 count_data.parquet를 이벤트 타임라인에 맞춰 조인해 branchnum별 회복 KPI를 산출하고, branch_data.parquet로 대여소 정보를 연결해 상위 대상을 제시한다.

- answerability: needs-metric-definition
- evidence_sources: weather_data.parquet, count_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 강수 종료 이벤트 규칙과 ‘급회복’의 KPI/baseline/임계치를 합의해야 대여소 간 급회복을 일관되게 판정할 수 있다.

## 053. QO03 · 같은 자치구 안에서 날씨 민감도가 가장 높은 대여소와 낮은 대여소는 어디인가?

‘날씨 민감도’를 어떤 통계량으로 산출할지 먼저 정한 뒤, 자치구(location1) 단위로 최고/최저 대여소를 뽑는다. 예를 들어 precipitation(또는 기온/풍속 포함)과 수요 지표 간의 상관계수, 회귀계수, 날씨 1단위 변화당 수요 변화율 등 중 하나를 민감도 점수로 정의하고, count_data.parquet–weather_data.parquet를 date_rt 등 시간 키로 정렬·조인해 branchnum별 점수를 계산한다. 요일/시간대/계절성을 통제할지(더미 변수, 고정효과 등), 최소 관측치와 이상치 처리 규칙을 어떻게 둘지에 따라 점수 안정성이 달라지므로 기준을 고정하는 것이 필요하다. 이후 branch_data.parquet의 location1으로 같은 자치구 내 대여소를 묶고, 민감도 점수의 최대/최소 branchnum을 반환한다.

- answerability: needs-metric-definition
- evidence_sources: branch_data.parquet, count_data.parquet, weather_data.parquet
- requires_review: True
- review_reason: 민감도 산식(상관/회귀/변화율)과 통제변수·최소표본·이상치 처리 기준이 정해져야 자치구 내 최고/최저 비교가 재현된다.

## 054. QO04 · 대여소 유형 `sy`별로 비나 눈에 대한 회복력이 다른가?

유형(sy)별 비교를 위해 강수/강설 이벤트와 ‘회복력’ KPI를 먼저 표준화해야 한다. weather_data.parquet에서 비·눈 이벤트를 어떻게 구성할지(연속 구간 병합, 종료 조건, 비·눈 혼합 포함 여부)를 정하고, snowfall 컬럼의 존재/단위/의미(적설량 vs 발생 플래그)를 확인해 눈 이벤트를 안정적으로 정의한다. 회복력은 종료 후 baseline까지 걸린 시간, 종료 후 k시간 내 회복률, 종료 이후 증가 기울기 등 중 하나로 선택하며 baseline(비·눈 없는 동일 조건 평균 등)과 비교 창 길이를 함께 고정한다. 그 다음 count_data.parquet를 이벤트 기준으로 정렬해 sy별 KPI 분포(평균/중앙값/분산 또는 신뢰구간)를 비교하고, 표본 수 불균형이 큰 경우 가중치나 부트스트랩 등 비교 방식을 명시한다.

- answerability: needs-metric-definition
- evidence_sources: weather_data.parquet, count_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 눈 이벤트 구성(snowfall 스키마 포함)과 회복력 KPI/baseline/비교방법이 확정되어야 sy별 차이를 해석 가능한 형태로 검정할 수 있다.

## 055. QO05 · 휴일이면서 비 오는 날에도 수요가 유지되는 대여소는 어디인가?

‘수요가 유지된다’를 기준선 대비 하락이 제한적인 상태로 정의하고, 휴일·강수 조건 하에서 이를 만족하는 대여소를 선별한다. weather_data.parquet에서 holiday=true AND precipitation>0인 시간대를 선택한 뒤 count_data.parquet와 date_rt(및 시간 키)로 조인해 branchnum별 조건부 평균(또는 합계)을 계산한다. 유지 판정은 비 없는 휴일의 동일 시간대 평균, 또는 비 없는 동일 요일·동일 시간대 평균 등 어떤 baseline을 쓸지와 허용 편차(예: baseline 대비 -x% 이내, 또는 통계적 비유의)를 명시해야 재현된다. 기준을 고정한 뒤 유지 판정을 통과한 branchnum을 산출하고, branch_data.parquet로 대여소 정보를 매핑해 결과를 제공한다.

- answerability: needs-metric-definition
- evidence_sources: weather_data.parquet, count_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 휴일·강수 조건에서의 ‘수요 유지’ baseline과 허용 편차/임계치가 정의되어야 자동 선별 기준이 일관된다.

## 056. QO06 · 기온 급락과 풍속 상승이 동시에 일어난 시간대에 수요가 급감한 대여소는 어디인가?

날씨 동시 이벤트(기온 급락+풍속 상승)를 정의하고, 같은 시간대에 수요 급감이 발생했는지 대여소별로 판정한다. weather_data.parquet에서 기온/풍속 컬럼의 필드명·단위·시간 해상도를 확인한 뒤, 직전 시간 대비 변화량 기준(절대값/퍼센트)과 임계치, 동시성 허용 범위(동일 시간만 vs ±1시간 윈도우)를 고정한다. 수요 급감도 count_data.parquet의 지표가 ‘이용량’인지 ‘재고’인지에 따라 방향 해석이 달라지므로 지표 의미를 확인하고, 급감 판정 방식(전시간 대비 하락률, baseline 대비 편차, z-score 등)과 임계치를 명시한다. 이후 이벤트 시간대를 키로 count_data를 조인해 branchnum별 급감 동반 여부/빈도를 집계하고, branch_data.parquet로 대여소 정보를 연결해 보고한다.

- answerability: needs-metric-definition
- evidence_sources: weather_data.parquet, count_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 기온·풍속·수요 지표의 의미와 급락/상승/급감 임계치 및 동시성 기준이 확정되어야 이벤트-수요 동반을 판정할 수 있다.

## 057. QO07 · 비는 오지 않았지만 가시거리 저하만으로 수요가 무너진 시간대가 있는가?

먼저 ‘비 없음’과 ‘가시거리 저하’ 조건으로 시간대를 정의한 뒤, 그 시간대에 수요 붕괴가 있었는지를 판정해 이벤트 목록을 구성한다. 이를 위해 weather_data.parquet에 visibility(가시거리) 컬럼이 존재하는지와 단위/결측 처리 규칙을 확인하고, precipitation=0 조건과 함께 가시거리 저하 기준(절대 임계치 또는 하위 분위 등)을 고정한다. 수요 ‘무너짐’은 count_data.parquet에서 시간대·요일 패턴을 반영한 baseline 대비 급락으로 정의하는 것이 일반적이므로, baseline 구성과 급락 임계치(z-score 또는 -x% 등)를 명시해야 결과가 재현된다. 정의가 확정되면 (date_rt, 시간, branchnum) 단위로 조건을 만족하는 레코드를 추출해 붕괴 여부를 라벨링하고, 존재 여부(있다/없다)와 함께 해당 시간대 목록을 출력한다.

- answerability: needs-schema-confirmation
- evidence_sources: weather_data.parquet, count_data.parquet
- requires_review: True
- review_reason: 가시거리 컬럼의 존재/단위/결측 규칙 확인이 선행되어야 ‘가시거리 저하’ 필터와 후속 붕괴 판정이 유효하다.

## 058. QO08 · 눈 오는 아침에도 출근 수요가 유지되는 대여소는 어디인가?

적설(눈) 아침을 이벤트로 정의하고, 출근 시간대 수요가 기준선 대비 유지되는 대여소를 선별한다. weather_data.parquet에서 snowfall(또는 대체 필드)의 의미와 단위를 확인한 뒤 눈 이벤트 기준(혼합 강수 포함 여부, 간헐적 0값 처리, 연속 구간 병합)을 고정하고, 출근 시간대 범위(예: 07–09시)도 사전에 확정한다. ‘유지’는 눈 오는 아침의 수요가 비·눈 없는 baseline(동일 요일 아침 평균, 최근 N주 등) 대비 얼마나 덜 감소했는지로 정의하며, 허용 편차/임계치를 함께 명시해야 자동 판정이 가능하다. 이후 count_data.parquet를 해당 시간대로 필터링해 branchnum별 지표를 산출하고 baseline과 비교해 유지 대여소를 도출한 다음, branch_data.parquet로 대여소 정보를 매핑한다.

- answerability: needs-metric-definition
- evidence_sources: weather_data.parquet, count_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: snowfall 기반 적설 이벤트 처리(혼합·간헐)와 출근시간 범위, ‘유지’ baseline/임계치가 고정되어야 선별 결과가 재현된다.

## 059. QO09 · 폭염 시간대에 오히려 저녁 수요가 늦게 이동하는 대여소는 어디인가?

폭염일과 비폭염일에서 ‘저녁 피크 시각’을 추정한 뒤, 폭염 조건에서 피크가 늦춰진 대여소를 판정한다. 폭염은 weather_data.parquet의 어떤 컬럼(기온/체감온도 등)을 쓸지와 임계치·지속시간 규칙을 먼저 정해야 하며, 저녁 시간대 범위도 고정해야 비교가 가능하다. 피크 시각은 count_data.parquet의 시간대 집계로 산출하거나, rent_data.parquet의 실제 대여 시각 분포로 추정할 수 있는데, 동률 처리와 스무딩(이동평균 등) 규칙을 명시하지 않으면 피크가 흔들릴 수 있다. 기준선은 ‘비폭염 동일 요일’처럼 매칭 규칙을 두고, ‘늦게 이동’의 판정 임계치(예: +h시간 이상)를 정한 뒤 대여소별 피크 시각 차이를 계산해 상위 대상을 반환한다.

- answerability: needs-metric-definition
- evidence_sources: weather_data.parquet, count_data.parquet, rent_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 폭염 기준과 저녁/피크 추정 방법(동률·스무딩 포함), 피크 이동 임계치가 정의되어야 ‘늦게 이동’ 대여소를 일관되게 식별할 수 있다.

## 060. QO10 · 날씨 변화가 발생한 뒤 수요 변화가 몇 시간 후 따라오는 대여소가 있는가?

날씨 변화 이벤트를 정의한 뒤, lag(지연) 0~N시간에서 날씨 변수와 수요 지표의 연관이 최대가 되는 지연시간을 대여소별로 추정한다. 날씨 변화는 강수 시작/종료, 기온 변화량, 풍속 급변 등 후보가 많으므로 사용할 이벤트/변수와 시간 해상도, 탐색할 최대 lag N을 고정해야 한다. 대표 lag는 교차상관 최대 시점, 회귀의 지연항 계수 최대 시점, 상호정보량 최대 등 중 하나로 정하고, 다중 lag 탐색에 따른 우연 효과를 줄이기 위해 최소 효과크기·유의성 기준 또는 기간 분할 검증 같은 재현성 조건을 함께 둔다. 또한 count_data.parquet 지표가 재고인지 이용량인지에 따라 ‘수요 변화’의 방향성이 달라질 수 있으므로 스키마 확인 후 branchnum별 lag 분포와 지연 반응이 뚜렷한 대여소를 제시한다.

- answerability: needs-metric-definition
- evidence_sources: weather_data.parquet, count_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 날씨 변화/수요 변화 정의와 lag 탐색 범위, 대표 lag 선택 규칙 및 유의성·재현성 기준이 정해져야 지연시간을 신뢰 가능하게 산출할 수 있다.

## 061. QO11 · 출근시간에는 대여 시작점이고 퇴근시간에는 반납 종착점으로 바뀌는 대여소는 어디인가?

rent_data.parquet에서 지정한 출근/퇴근 시간대에 대해 시작 대여소(branchnum_r) 기준 대여 건수와 반납 대여소(branchnum_b) 기준 반납 건수를 각각 집계한다. 대여소별로 출근 시간대에는 시작 비중(또는 시작-반납 차이)이 우세하고, 퇴근 시간대에는 반납 비중(또는 차이 부호)이 우세해지는지 판단하는 ‘역할 전환’ 규칙을 먼저 고정한 뒤 해당 대여소만 필터링한다. 결과에는 출근/퇴근 시간대의 시작·반납 집계값과 전환 판정에 사용한 지표를 함께 포함하고, branch_data.parquet를 branchnum으로 조인해 대여소 이름 등 식별 정보를 붙여 반환한다.

- answerability: needs-metric-definition
- evidence_sources: rent_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 역할 전환을 어떤 지표(비중/차이)와 임계치(최소 건수 포함)로 판정할지 정의가 고정돼야 결과가 재현된다.

## 062. QO12 · 평일에는 시작점이지만 휴일에는 목적지가 되는 대여소는 어디인가?

rent_data.parquet에서 날짜를 평일과 휴일로 구분하는 기준(주말만인지 공휴일 캘린더 포함인지)을 확정한 뒤, 각 집단별로 시작/반납을 분리 집계한다. 대여소별로 평일에는 시작 우세, 휴일에는 반납 우세로 바뀌는지(비중 또는 차이 기반)를 계산하고, 표본 안정성을 위해 최소 트립 수 조건을 함께 적용해 후보를 선정한다. 출력에는 대여소 ID와 함께 평일·휴일의 시작/반납 집계치 및 판정에 사용한 전환 규칙을 같이 제공해 검증 가능하게 만든다.

- answerability: needs-schema-confirmation
- evidence_sources: rent_data.parquet
- requires_review: True
- review_reason: 휴일 구분(공휴일 포함 여부)과 시작/반납을 나타내는 컬럼의 의미가 확정돼야 집단 간 역할 비교가 성립한다.

## 063. QO13 · 반복적으로 한쪽 방향으로만 수요가 쏠리는 대여소 쌍은 어디인가?

rent_data.parquet에서 (시작 대여소, 반납 대여소) OD 쌍별 이동 건수를 기간 단위(일/주/월 중 택1)로 분할 집계하고, 각 OD에 대해 역방향(반납→시작)과 비교한 불균형 지표(비율/차이/로그오즈 등)를 계산한다. ‘반복적’ 조건은 동일 방향 우세가 연속 N기간 이상 유지되거나, 전체 기간 중 일정 비율 이상에서 우세한지처럼 지속성 규칙으로 정의한 뒤 필터링한다. 표본이 작은 OD 쌍의 과대 판정을 막기 위해 최소 이동 건수 기준을 함께 두고, 결과에는 OD쌍·불균형 지표·지속성 요약(기간별 값 포함)을 함께 반환한다.

- answerability: needs-metric-definition
- evidence_sources: rent_data.parquet
- requires_review: True
- review_reason: 불균형 지표와 반복/지속 판정 규칙(기간 단위, 연속 조건, 최소 건수)이 고정되지 않으면 후보 OD쌍이 달라진다.

## 064. QO14 · 심야 반납이 몰린 뒤 아침 공급 부족이 반복되는 대여소는 어디인가?

rent_data.parquet에서 대여소별로 심야 시간대 반납 건수를 날짜 단위로 집계하고, ‘심야 반납 집중’ 에피소드 판정 기준(시간대 경계, 임계치, 최소 건수)을 적용해 이벤트를 생성한다. count_data.parquet에서 다음날 아침 시간대의 재고/가용 상태를 추출해 ‘공급 부족’(예: 가용 대수 또는 가용 비율이 임계치 미만) 에피소드를 산출하고, 날짜 키로 심야 이벤트와 다음날 아침 부족을 연결해 선후 관계를 구성한다. 이 연결이 반복적으로 관측되는 대여소를 기준(반복 횟수, 관측 기간, 결측 처리)으로 정렬 또는 필터링해 반환하며, 사용한 시간대/임계치/결측 처리 규칙을 함께 기록한다.

- answerability: needs-metric-definition
- evidence_sources: rent_data.parquet, count_data.parquet
- requires_review: True
- review_reason: 심야·아침 시간대 경계와 부족(Shortage) 산식/임계치가 정해져야 에피소드와 반복 판정이 일관되게 재현된다.

## 065. QO15 · 거치 관련 metric이 낮은데도 회전율이 높은 대여소는 어디인가?

branch_data.parquet에서 대여소별 ilcd, iqr 값을 읽고, count_data.parquet에서 동일 대여소의 회전율을 계산할 수 있는 기간 집계(분모가 되는 운영 시간/일수 포함)를 구성한다. 대여소 식별자로 두 데이터를 조인한 뒤, ilcd/iqr ‘낮음’과 회전율 ‘높음’을 구분하는 기준(절대 임계치 또는 분위수 컷)을 명시하고 해당 조건을 만족하는 대여소를 추출한다. 결과에는 ilcd, iqr, 회전율과 함께 사용한 산식(집계 기간, 분모 정의)과 컷오프 값을 포함해 동일 조건으로 재실행 가능하게 만든다.

- answerability: needs-metric-definition
- evidence_sources: branch_data.parquet, count_data.parquet
- requires_review: True
- review_reason: ilcd/iqr의 의미와 방향성(낮을수록 무엇을 뜻하는지), 회전율 산식 및 임계치가 고정돼야 ‘예외 조합’ 판정이 왜곡되지 않는다.

## 066. QO16 · 월별 이용 보조 집계와 시간대 집계가 서로 다른 추세를 보이는 대여소는 어디인가?

uselate_data.parquet에서 대여소별 월 키와 ‘월별 이용 보조 집계’ 지표의 의미/단위를 확인한 뒤 월 시계열을 구성한다. count_data.parquet의 시간대 단위 집계가 무엇을 측정하는지(대여/반납 이벤트인지, 재고 스냅샷인지)에 따라 동일 월로 재집계하거나(이벤트) 월 요약 지표로 변환하는 규칙(스냅샷이면 변화량/가용률 요약 등)을 먼저 정한다. 두 월 시계열에 대해 월간 증감률, 추세 기울기, 상관/부호 불일치 같은 비교 지표를 계산해 추세가 유의미하게 다른 대여소를 후보로 반환하고, branch_data.parquet를 조인해 해석용 속성(자치구 등)을 덧붙인다.

- answerability: needs-schema-confirmation
- evidence_sources: uselate_data.parquet, count_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: uselate_data와 count_data의 측정 대상/단위 및 월 재집계 기준이 확인되지 않으면 ‘추세 불일치’가 정의 차이에서 비롯될 수 있다.

## 067. QO17 · 대여소 스냅샷 속성 변화가 있어도 같은 운영 개체로 이어 봐야 하는 경우는 무엇인가?

branch_data.parquet의 스냅샷 시점별 레코드를 대여소 식별자 기준으로 정렬하고, 이름/좌표/주소 등 속성 변경 이력을 추적한다. 동일 운영 개체로 연속성을 유지할지 여부는 허용 가능한 변경 범위(좌표 이동 거리, 문자열 변경 수준, 운영 공백 허용 기간)와 분리 조건(큰 위치 이동, 관할/주소 동시 변경 등)을 규칙으로 정의해 판정한다. 산출물은 ‘동일성 유지’와 ‘분리’ 케이스를 각각 대표 사례로 제시하고, 각 판정에 대해 식별자 기반 직접 근거와 유사도/거리 기반 추론 근거를 분리해 함께 기록한다. 이때 same_as 연결의 신뢰도(confidence)와 근거 출처(provenance)를 명시해 후속 조인에서의 오류 전파를 통제한다.

- answerability: needs-provenance
- evidence_sources: branch_data.parquet, ontology-lite
- requires_review: True
- review_reason: 스냅샷 간 동일 개체 연결은 직접 식별 근거와 유사도 기반 추론을 분리하고 provenance/confidence를 관리해야 한다.

## 068. QO18 · 이름이 바뀌었거나 좌표가 조금 이동한 대여소를 같은 대여소로 볼 수 있는가?

branch_data.parquet에서 동일 branchnum이 지속되는 경우는 기본적으로 동일 대여소로 취급하고, branchnum이 변경/누락되는 경우에만 이름 정규화 후 유사도와 좌표 거리 기반으로 same_as 후보를 생성한다. ‘조금 이동’에 해당하는 거리 임계치와 이름 유사도 컷오프를 파라미터로 두고, 각 매칭 후보에 대해 거리·유사도 점수·발생 시점을 함께 출력해 판정 근거를 노출한다. 자동으로 확정 가능한 케이스와 검토가 필요한 케이스를 분리해 반환하며, 최종 확정은 운영 관점의 예외(폐쇄 후 재개장, 좌표 오차 등)를 점검하는 절차를 포함한다.

- answerability: needs-human-review
- evidence_sources: branch_data.parquet
- requires_review: True
- review_reason: 같은 대여소로 볼지의 거리/유사도 임계치와 예외 케이스 처리 기준은 운영 정책에 따라 달라 사람의 확정 검토가 필요하다.

## 069. QO19 · 날짜에 따라 같은 대여소를 다른 별칭으로 찾더라도 일관되게 응답할 수 있는가?

branch_data.parquet에서 branchname과 branchnum의 시점별 관계를 이용해 ‘별칭(입력명) → canonical branchnum’ 매핑을 구축하고, 질의 처리 시에는 입력 문자열 정규화(공백/특수문자/접미어 처리 등) 후 매핑을 통해 branchnum으로 정규화한다. 이후 모든 조인과 집계는 branchnum 기준으로 수행해 날짜별 표기 변화가 있어도 동일 개체로 일관되게 응답한다. 다만 서로 다른 branchnum이 유사한 이름을 공유하는 경우나 오탈자 입력에는 fuzzy 매칭 후보 목록과 근거 점수를 함께 제공하고, 샘플링으로 오매칭률을 점검할 수 있도록 로그를 남긴다.

- answerability: needs-human-review
- evidence_sources: branch_data.parquet
- requires_review: True
- review_reason: 별칭 정규화와 fuzzy 매칭은 동명이인/오탈자에서 오매칭 위험이 있어 품질 점검을 위한 수동 검토가 필요하다.

## 070. QO20 · 자치구가 달라도 유사한 흐름 패턴을 보이는 대여소 군집은 무엇인가?

rent_data.parquet에서 대여소별 시간대 이용 분포, 요일 패턴, 주요 OD 비중 등 ‘흐름’ 특징을 정의해 feature vector를 구성하고, 필요 시 count_data.parquet에서 운영 특징(가용률 변동, 반복 부족 시간대, 결측률 등)을 추가한다. 선택한 군집 알고리즘(K-means/계층/DBSCAN 등)과 거리척도, 스케일링 방식, 하이퍼파라미터 및 랜덤시드를 고정해 군집을 생성한다. branch_data.parquet의 자치구 정보를 조인해 군집별 자치구 다양성(예: 서로 다른 자치구 수, 집중도)을 계산하고, 자치구가 서로 달라도 동일 군집에 포함되는 패턴을 중심으로 군집 대표 특징을 요약해 반환한다. 해석이 핵심인 항목이므로 군집 결과에는 사용한 특징 정의와 거리/알고리즘 선택 근거를 함께 남기고, 운영적 라벨링은 사후 검토로 확정한다.

- answerability: inferential-only
- evidence_sources: rent_data.parquet, count_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 군집은 특징/거리/알고리즘 선택에 따라 해석이 달라지므로 산출 후 사람이 운영 의미와 라벨을 검토해야 한다.

## 071. QO21 · 장거리 이동 직후 24시간 내 고장이 자주 나는 자전거는 무엇인가?

rent_data.parquet에서 bikenum별 이동(대여/반납) 이벤트의 시각과 거리(또는 거리 산출에 필요한 컬럼)를 준비하고, ‘장거리’로 분류되는 이벤트를 기준 시점 t0로 정의한다. broken_data.parquet의 고장 이벤트를 bikenum으로 결합한 뒤, 고장 시각 t1이 t0부터 t0+24시간 사이에 포함되는 경우만 매칭하는 time-window join을 수행한다. 매칭 건수를 bikenum별로 집계해 내림차순 정렬하면 ‘장거리 이동 후 24시간 내 고장’이 반복되는 자전거 후보를 얻는다. 장거리 임계값과 ‘자주’의 컷오프(상위 N, 최소 매칭 횟수 등), 그리고 t0에 사용할 시각 컬럼(대여 시작/반납 시각)은 파라미터로 고정해야 동일 결과가 재현된다.

- answerability: needs-metric-definition
- evidence_sources: rent_data.parquet, broken_data.parquet
- requires_review: True
- review_reason: 장거리 임계값·‘자주’ 판정 기준과 기준시각(t0) 정의(대여 시작/반납)가 바뀌면 time-window join 결과가 달라진다.

## 072. QO22 · 고장 유형별로 자주 나타나는 대여소-시간대 조합은 무엇인가?

broken_data.parquet에서 고장 유형(type)과 고장 시각을 가져오고, 고장 이벤트를 어떤 대여소에 귀속할지 규칙을 먼저 정한다(예: 고장 직전 마지막 반납 대여소, 고장 직후 첫 대여 대여소 등). 대여소 귀속이 broken_data에 없으면 bikenum을 키로 rent_data.parquet의 이벤트 시계열을 연결해 해당 규칙에 맞는 대여소를 선택한다. 고장 시각(또는 귀속 규칙에 사용한 기준 시각)을 시간대 버킷(예: 1시간 단위, 피크/비피크)으로 변환한 다음, (type, 대여소, time_bucket)별 COUNT를 계산해 내림차순으로 정렬한다. branch_data.parquet는 대여소명/권역 등 해석용 메타데이터를 덧붙일 때만 사용하며, 핵심은 ‘고장 당시 대여소’ 및 시간 버킷 기준을 문서에 명시하는 것이다.

- answerability: needs-schema-confirmation
- evidence_sources: broken_data.parquet, rent_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 고장 이벤트에 대여소를 귀속하는 규칙(직전 반납/직후 대여 등)과 시간 버킷 기준이 스키마 및 정의 선택에 따라 달라진다.

## 073. QO23 · 짧은 시간 안에 반복 대여된 자전거가 더 자주 고장 나는가?

rent_data.parquet에서 bikenum별 대여 이벤트를 시간순으로 정렬하고, 연속 대여 간 간격 Δt를 계산해 Δt≤X를 ‘단시간 반복 대여(rapid)’로 라벨링한다(X는 입력 파라미터). broken_data.parquet의 고장 이벤트를 bikenum으로 연결한 뒤, rapid 라벨이 발생한 시점 이후 관찰창(예: N시간/7일) 내 고장만 집계하여 노출(rapid)과 결과(고장)의 시간 순서를 맞춘다. 비교는 단순 건수가 아니라 ‘고장 건수/대여 건수’ 또는 ‘고장 건수/관찰시간’처럼 분모가 동일한 발생률로 수행하고, 이용량이 많은 자전거로 쏠리는 교란을 완화하기 위해 최소 대여횟수 필터나 이용량 구간별 층화(또는 매칭) 기준을 함께 둔다. 최종 해석에는 X, 관찰창 길이, 발생률 분모와 교란 통제 규칙을 함께 기록해야 재계산이 가능하다.

- answerability: needs-metric-definition
- evidence_sources: rent_data.parquet, broken_data.parquet
- requires_review: True
- review_reason: rapid 기준(X), 관찰창(N), 발생률 분모(대여건수/시간)와 교란 통제(층화·매칭 등)가 정의되지 않으면 결론이 달라질 수 있다.

## 074. QO24 · 급격한 기상 악화 직후 고장 이벤트가 늘어나는가?

weather_data.parquet에서 강수·풍속·기온 변화 등 후보 변수를 선택하고, 임계값을 넘는 구간을 WeatherShock으로 라벨링한다(변수 조합, 임계값, 집계 단위는 파라미터). broken_data.parquet의 고장 시각을 동일한 시간 버킷으로 집계한 뒤, shock 발생 직후 H시간(또는 1일) 구간의 고장 건수/발생률을 shock 직전 구간 또는 비-shock 구간과 비교한다. 요일·시간대·계절성에 따른 자연 변동을 줄이기 위해 동일 요일/동일 시간대의 비-shock 구간을 대조군으로 두거나 이동평균 대비 초과분을 계산하는 등 기준선 정의를 포함한다. 또한 시간대(timezone)와 시간 컬럼의 기준이 불일치하면 버킷 정렬이 흔들릴 수 있으므로, 분석 전 시간 기준을 확인해 동일 축으로 정규화한다.

- answerability: needs-metric-definition
- evidence_sources: weather_data.parquet, broken_data.parquet
- requires_review: True
- review_reason: WeatherShock 변수·임계값, ‘직후’ 시간창(H), 그리고 계절·요일을 반영한 기준선(대조군) 정의가 없으면 증가 판단이 임의적이 된다.

## 075. QO25 · 여러 대여소를 거치며 반복 고장을 보이는 자전거 경로는 무엇인가?

rent_data.parquet에서 bikenum별로 시간순 정렬된 대여/반납 기록을 사용해 대여소 이동 시퀀스(노드=대여소, 엣지=이동)를 구성한다(출발/도착 대여소 컬럼을 어떤 것으로 볼지 스키마를 먼저 확정한다). broken_data.parquet의 고장 이벤트를 bikenum과 시각으로 결합하고, 각 고장을 경로의 어느 지점에 귀속할지(예: 고장 직전 반납 대여소, 고장 직후 첫 대여 대여소) 규칙을 하나로 고정한다. ‘여러 대여소’는 서로 다른 대여소 수 ≥ K, ‘반복 고장’은 고장 횟수 ≥ M처럼 임계값을 두고 해당 조건을 만족하는 bikenum을 필터링한다. 출력은 선택된 bikenum별 대여소 경로와 고장 삽입 위치를 함께 제시해 경로 기반 점검이 가능하도록 한다.

- answerability: needs-schema-confirmation
- evidence_sources: rent_data.parquet, broken_data.parquet
- requires_review: True
- review_reason: 대여소 컬럼(출발·도착) 해석과 고장 이벤트를 경로의 어느 노드/구간에 귀속할지 규칙이 확정되어야 경로가 일관되게 재구성된다.

## 076. QO26 · 이용량이 많은데 고장은 적은 대여소와, 이용량은 낮은데 고장이 많은 대여소의 차이는 무엇인가?

count_data.parquet(또는 rent_data.parquet)로 대여소별 이용량을 산출하되, 이용량 기준을 ‘대여 기준’으로 볼지 ‘반납 기준’으로 볼지 먼저 고정한다. broken_data.parquet의 고장은 bikenum을 통해 rent_data.parquet에 연결해 대여소로 귀속시키고(예: 고장 직전 반납 대여소), 동일 기간에 대해 대여소별 고장 건수를 집계한다. 대여소별 고장률(예: 고장건수/이용건수)을 계산한 뒤, 분위수(z-score 포함) 등으로 ‘고이용·저고장’과 ‘저이용·고고장’ 극단 집단을 정의하고 분류한다. branch_data.parquet의 권역/입지/규모 같은 속성을 붙여 두 집단 간 분포 차이를 비교 요약하되, 저이용 대여소의 비율 불안정을 완화하기 위한 최소 이용량 필터 또는 스무딩 규칙을 함께 명시한다.

- answerability: needs-metric-definition
- evidence_sources: count_data.parquet, rent_data.parquet, broken_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 이용량 정의(대여/반납), 고장 귀속 규칙, 고장률 산식과 극단 집단 선정 기준(저표본 보정 포함)이 고정되어야 비교가 재현된다.

## 077. QO27 · 반납이 많이 몰린 대여소가 이후 고장 자전거를 더 많이 배출하는가?

rent_data.parquet에서 반납 대여소(예: branchnum_b)별 반납 건수를 시간 버킷(시간/일)으로 집계하고, 상위 퍼센타일 또는 임계 건수 이상인 버킷을 ‘반납 집중’으로 라벨링한다(집중 기준은 파라미터). broken_data.parquet의 고장 이벤트를 bikenum으로 rent_data.parquet에 연결해 고장 직전 반납 대여소와 그 반납 시각을 찾고, 해당 반납 시각 이후 W시간 내 고장이 발생했는지로 연결 건수를 계산한다. 대여소별로 ‘반납 집중 버킷에서의 연결 고장 건수’ 또는 ‘연결 고장 건수/반납 건수’ 같은 지표를 산출해, 집중 구간과 비집중 구간을 비교한다. 고장을 직전 반납소에 귀속하는 가정은 오분류를 낳을 수 있으므로, 샘플 점검이나 대안 귀속 규칙(예: 직후 대여소) 민감도 분석을 포함해 해석 안정성을 확인한다.

- answerability: needs-metric-definition
- evidence_sources: rent_data.parquet, broken_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 반납 집중 기준과 이후 시간창(W), 그리고 고장을 직전 반납소에 귀속하는 가정의 타당성은 사람이 규칙을 확정·점검해야 한다.

## 078. QO28 · 장거리 유입이 늘어난 뒤 특정 대여소 주변에서 고장이 증가하는가?

rent_data.parquet에서 반납 대여소(예: branchnum_b) 기준으로 ‘장거리 이동 후 반납’ 건수를 시간 버킷별로 계산하고, 이동평균 대비 급증·전주 대비 증가율 등 규칙으로 유입 증가 episode를 탐지한다(장거리 기준과 episode 탐지 규칙은 파라미터). broken_data.parquet의 고장은 bikenum을 통해 rent_data.parquet에 연결해 대여소 연관성을 부여하되, 연관을 ‘고장 직전 반납소=대상 대여소’로 볼지, branch_data.parquet 좌표를 사용해 ‘대여소 반경 R 내’로 볼지 중 하나를 선택한다. episode 이후 T시간/일의 고장 건수 또는 고장률을 episode 이전/비-episode 구간과 비교하여 증가 여부를 평가하고, 요일·시간대 기준선 또는 차분(Δ) 비교로 추세 영향을 완화한다. 보고 시에는 장거리 임계값, episode 탐지 설정, 주변(연관) 정의, 사후 창(T)을 함께 기록해 재현성을 확보한다.

- answerability: needs-metric-definition
- evidence_sources: rent_data.parquet, broken_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 장거리 기준·episode 탐지 규칙·대여소 ‘주변’(연관) 정의와 기준선 설정이 확정되지 않으면 증가 판정이 분석자 선택에 좌우된다.

## 079. QO29 · 고장 자전거가 반복적으로 수렴하는 정비 취약 대여소는 어디인가?

broken_data.parquet의 고장 이벤트를 bikenum으로 rent_data.parquet에 연결해 각 고장을 어느 대여소에 귀속할지(예: 고장 직전 반납 대여소) 규칙을 먼저 고정한다. 그 규칙으로 대여소별 고장 귀속 건수를 집계하되, 단순 건수는 이용량 큰 대여소에 편향될 수 있으므로 rent_data 또는 count_data를 통해 대여소 이용량을 산출하고 정규화된 고장률(고장/이용)을 함께 계산한다. ‘수렴’은 동일 bikenum의 고장이 반복될 때 특정 대여소로 귀속되는 집중도를 의미하므로, 예를 들어 대여소별로 (반복 귀속 횟수, 반복 귀속 비율, 또는 엔트로피 기반 집중도) 같은 지표를 정의해 고장률과 결합해 취약성을 점수화한다. 최종적으로는 (정규화 고장률, 수렴 지표)의 조합으로 취약 대여소를 선정하고, 사용한 지표 정의와 임계값을 문서에 명시한다.

- answerability: needs-metric-definition
- evidence_sources: broken_data.parquet, rent_data.parquet
- requires_review: True
- review_reason: ‘수렴/취약’의 판정 지표(반복 귀속 포함)와 고장 귀속 규칙, 이용량 정규화 방식이 정의되어야 대여소를 일관되게 특정할 수 있다.

## 080. QO30 · 고장 기록이 있었는데도 곧바로 다시 대여된 자전거는 무엇인가?

broken_data.parquet에서 bikenum과 고장 시각을 추출하고, rent_data.parquet에서 동일 bikenum의 대여 이벤트 시계열을 준비한다. 각 고장 이벤트 이후 최초로 발생한 다음 대여 시각을 찾아 time join을 수행한 뒤, 재대여까지의 소요시간 Δt를 계산한다. Δt≤X를 ‘곧바로 재대여’로 플래그하고, bikenum별로 해당 사례 수(또는 최소 Δt)를 요약해 리스트로 반환한다. 단, X(예: 1시간/당일/24시간)와 rent_data에서 사용할 ‘대여 시각’ 컬럼이 시작/종료 중 무엇인지가 확정되어야 Δt 계산이 동일하게 재현된다.

- answerability: needs-schema-confirmation
- evidence_sources: broken_data.parquet, rent_data.parquet
- requires_review: True
- review_reason: rent_data의 시간 컬럼이 대여 시작/종료 중 무엇을 의미하는지와 ‘곧바로’ 임계값(X)을 확정해야 Δt 산출이 일관된다.

## 081. QO31 · 시간대 집계상 수요 급증인데 실제 대여 이벤트 증거가 약한 구간은 어디인가?

먼저 `count_data`에서 날짜-시간-대여소 단위로 ‘수요 급증’ 버킷을 탐지한다(예: 이동평균 대비 배수, z-score, 또는 분위수 기반 플래그). 같은 키로 `rent_data`를 재집계해 TripEventCount(대여 이벤트 수)를 붙인 뒤, 급증으로 표시되었으나 TripEventCount가 사전 정의한 최소 기준을 밑도는 버킷을 추출해 나열한다. 이때 시간 해상도/타임존이 두 테이블에서 일치하는지, 대여소 식별자가 `branch_data`로 정규화되는지 확인하여 조인 불일치가 ‘증거 약함’으로 오인되지 않게 한다. 결과에는 버킷 키, 급증 점수(또는 플래그), TripEventCount, 판정 근거를 함께 제공하고 직접 근거(원시 집계)와 판정 근거(임계값 규칙)를 분리해 confidence를 기록한다.

- answerability: needs-metric-definition
- evidence_sources: count_data.parquet, rent_data.parquet, branch_data.parquet, ontology-lite
- requires_review: True
- review_reason: ‘급증’과 ‘이벤트 증거 약함’의 임계값/점수화 규칙 및 시간·대여소 키 정규화가 고정되지 않으면 실제 현상과 조인/정렬 오류를 구분할 수 없다.

## 082. QO32 · `count_data`와 `rent_data`가 서로 모순되는 날짜-시간-대여소 구간은 어디인가?

`count_data`의 시간대별 집계값(예: StationHourlyCount)을 기준 키(날짜-시간-대여소)로 두고, `rent_data`를 동일한 시간 버킷으로 재집계해 TripEventCount를 만든 뒤 1:1로 비교한다. 모순은 |차이| 또는 비율이 ‘허용 오차’ 규칙을 초과하는 버킷으로 정의하고, 해당 버킷의 두 값과 차이/비율을 표로 반환한다. 다만 두 값이 같은 사건을 세는지(대여만 포함인지, 반납/재배치 포함인지, 중복 제거 여부 등)와 결측·적재 지연을 오차로 허용할지 정책이 선행되어야 한다. 또한 `branch_data`를 이용해 대여소 키를 정규화한 후 비교해야 단순 키 불일치가 모순으로 과대 탐지되지 않는다.

- answerability: needs-schema-confirmation
- evidence_sources: count_data.parquet, rent_data.parquet, branch_data.parquet, ontology-lite
- requires_review: True
- review_reason: 두 테이블 집계값의 의미(포함 이벤트 범위)와 허용 오차/결측 처리 규칙이 확정되지 않으면 ‘모순’ 판정이 임의적으로 변한다.

## 083. QO33 · 날씨 테이블의 전체 이용량 `count`와 대여소별 집계 총합이 어긋나는 시점은 어디인가?

`weather_data.count`를 시간 축으로 정렬한 뒤, 같은 시간 버킷에서 `count_data`를 대여소별로 집계해 전체 합계(SUM)를 계산하고 두 값을 같은 타임스탬프에 정렬해 비교한다. 불일치 시점은 (weather_count, station_sum, diff, diff_ratio)를 산출해 임계값(절대 차이 또는 비율)을 넘는 시각으로 정의해 추출한다. 비교 전에 `weather_data.count`가 ‘전체 이용량’인지(집계 범위/단위/누락 포함 여부)와 시간 해상도(관측 시각 vs 시간대 버킷)를 스키마로 확정해야 해석이 일관된다. 또한 누락된 대여소/시간대가 station_sum을 작게 만들 수 있으므로 결측 처리 및 포함 대여소 범위(예: 운영중 스테이션만)도 함께 명시한다.

- answerability: needs-schema-confirmation
- evidence_sources: weather_data.parquet, count_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: weather_data.count의 집계 범위/의미와 시간 해상도 정렬 규칙이 확인되지 않으면 불일치가 데이터 누락인지 정의 차이인지 판정할 수 없다.

## 084. QO34 · 같은 자치구, 비슷한 날씨인데 회복 속도가 전혀 다른 대여소는 어디인가?

`branch_data.location1`로 자치구를 동일하게 제한한 뒤, `weather_data`에서 ‘비슷한 날씨’ 조건을 만족하는 시간 구간을 정의하고 해당 구간에 대해 `count_data`에서 대여소별 회복 속도를 계산해 비교한다. 회복 속도는 특정 운영 상태(예: 부족/이상)에서 정상 범위로 복귀하기까지의 시간처럼 episode 기반 지표로 두는 것이 일반적이며, 상태 임계값과 episode 병합(허용 갭, 최소 지속시간) 규칙이 필요하다. 날씨 유사도는 강수 유무/강수량 구간, 기온 범위, 풍속 등 선택 변수와 허용 오차를 명시해 재현 가능하게 고정한다. 산출물은 자치구 및 날씨 조건별로 대여소별 회복시간 요약(평균/중앙값/분포)과 비교 근거가 되는 episode 수를 함께 제시한다.

- answerability: needs-metric-definition
- evidence_sources: branch_data.parquet, count_data.parquet, weather_data.parquet, ontology-lite
- requires_review: True
- review_reason: 회복(상태 임계값·episode 규칙)과 ‘유사 날씨’ 유사도 기준이 정의되지 않으면 대여소 간 차이가 규칙 설정에 따라 뒤바뀔 수 있다.

## 085. QO35 · 날씨 변화에도 거의 흔들리지 않는 대여소는 무엇인가?

`count_data`의 대여소별 이용량과 `weather_data`의 기상 변수(예: 강수, 기온, 풍속)를 시간 정렬한 뒤, ‘날씨 변화에 대한 민감도’ 지표를 정의해 대여소별로 산출한다(예: 날씨 변수에 대한 회귀계수/탄력성의 절대값, 날씨 구간 간 평균 차이, 또는 상관계수). 기간 범위, 사용할 기상 변수, 계절성·요일·시간대 효과 통제 방식(더미/분해/정규화)을 고정해야 결과가 비교 가능하다. 단순 평균 차이만 쓰면 ‘항상 수요가 낮은’ 대여소가 비민감으로 섞일 수 있으므로 규모 보정(표준화, 비율 지표 등) 여부도 함께 결정한다. 결과는 대여소별 민감도 점수와 사용한 모델/통제 변수를 요약해 제공한다.

- answerability: needs-metric-definition
- evidence_sources: count_data.parquet, weather_data.parquet, branch_data.parquet, ontology-lite
- requires_review: True
- review_reason: 민감도 산식(변수·기간·통제·보정·임계값)이 고정되지 않으면 ‘거의 흔들리지 않음’ 판정이 분석자 선택에 좌우된다.

## 086. QO36 · `ilcd`나 `iqr` 같은 프로필 metric이 부족 지속시간과 연결되는가?

`count_data`에서 대여소별 ‘부족’ episode를 정의하고(부족 임계값, 허용 갭, 최소 지속시간), episode별 지속시간을 합산 또는 요약해 shortage_duration을 만든다. `branch_data`에서 동일한 대여소 키로 `ilcd`, `iqr` 값을 결합한 뒤, (ilcd, iqr, shortage_duration) 데이터셋을 구성해 상관 분석 또는 회귀로 연관성을 평가한다. 해석 가능성을 위해 `ilcd`/`iqr`의 의미·단위·계산 기준을 스키마로 확인하고, 필요하면 자치구/규모 등 교란요인을 `branch_data`로 보정한 모델을 함께 산출한다. 출력은 효과 크기(상관계수 또는 회귀계수), 신뢰구간/유의성(사용 시), 그리고 부족 episode 정의를 포함한 재현 가능 규칙으로 구성한다.

- answerability: needs-schema-confirmation
- evidence_sources: count_data.parquet, branch_data.parquet, ontology-lite
- requires_review: True
- review_reason: ilcd/iqr의 정의·단위와 부족 episode 산출 규칙이 확정되지 않으면 연관 분석 결과의 해석과 재현성이 보장되지 않는다.

## 087. QO37 · 신규 가입자 증가가 있던 달에 어떤 자치구 대여소들이 더 큰 부담을 받았는가?

먼저 `newmeta`에서 월 단위 신규 가입자 증가가 발생한 ‘대상 월’을 식별하고(월 경계/타임존 규칙 포함), 같은 월에 대해 `count_data`와/또는 `rent_data`로 자치구별 운영 부담 지표를 계산한다. 부담 지표는 피크 이용량, 상위 분위수, 부족 시간, 급증 빈도 등 중 하나로 고정하고, 자치구 집계 시 합/평균 및 대여소 수로의 정규화 여부를 명시한다. `branch_data.location1`로 대여소를 자치구에 매핑한 뒤, 자치구별 부담 지표 변화(전월 대비 등)와 내부의 상위 기여 대여소 목록을 함께 산출한다. 가입자 데이터가 대여소에 직접 귀속되지 않는 경우, 결과 해석은 ‘동기간 동조’ 수준의 근거로 제한하고 직접 근거와 추론 근거를 분리해 제시한다.

- answerability: needs-metric-definition
- evidence_sources: newmeta.parquet, count_data.parquet, rent_data.parquet, branch_data.parquet, ontology-lite
- requires_review: True
- review_reason: ‘부담’ 지표 정의와 월 단위 집계/정규화 규칙이 필요하고, 가입자 지표의 대여소 귀속 불가로 해석 강도를 별도 관리해야 한다.

## 088. QO38 · 특정 연령대나 성별 가입자 증가가 주말 대여 패턴 변화와 연결되는가?

`newmeta`에서 `age`, `gender`별 신규 가입자 증가 시계열을 만들고, 동일한 시간 해상도(주/월 등)로 `rent_data`에서 주말 대여 패턴 지표 시계열을 산출해 두 시계열의 동조 여부를 평가한다. 주말 정의(현지 요일 기준, 타임존, 공휴일 포함 여부)와 패턴 지표(주말 총건수, 주말/평일 비중, 시간대별 분포 변화 등)를 사전에 고정해야 비교가 흔들리지 않는다. 필요하면 시차 상관(예: 가입 증가가 이후 주말 수요 변화로 이어지는지)을 함께 계산하되, 인과가 아니라 상관 기반 신호로 해석 범위를 제한한다. 출력은 demographic별 가입 증가량, 주말 패턴 지표, 상관(또는 시차 상관) 요약과 사용한 주말/기간 정의를 포함한다.

- answerability: needs-metric-definition
- evidence_sources: newmeta.parquet, rent_data.parquet, ontology-lite
- requires_review: True
- review_reason: 주말/기간 정렬 규칙과 ‘주말 패턴 변화’ 지표가 정의되지 않으면 허위 상관 또는 과해석 위험이 커진다.

## 089. QO39 · 같은 유형의 대여소라도 자치구마다 비에 대한 회복력이 다른가?

`branch_data`에서 대여소 유형(`sy`)이 동일한 집단을 구성하고, 자치구(`location1`)별로 나누어 비 이벤트 이후의 회복력 지표를 비교한다. 비 이벤트는 `weather_data`의 강수량/강수 여부 임계값과 이벤트 병합 규칙(연속 강수, 허용 공백)으로 정의해 사건 단위를 만들고, 회복력은 `count_data`에서 회복시간/일정 시간 내 정상 복귀율 등 하나의 지표로 고정해 계산한다. weather 관측 시각과 count 집계 버킷의 시간 정렬 규칙을 명시한 뒤, 유형별로 자치구 간 회복력 분포(요약통계 및 필요 시 검정)를 제시한다. 결과에는 비교에 사용된 비 이벤트 목록(강도·지속)과 표본 수를 함께 제공해 해석의 신뢰도를 점검 가능하게 한다.

- answerability: needs-metric-definition
- evidence_sources: branch_data.parquet, count_data.parquet, weather_data.parquet, ontology-lite
- requires_review: True
- review_reason: 비 이벤트 정의와 회복력 지표(임계값·episode 규칙)가 고정되지 않으면 자치구 간 차이가 정의 변경에 따라 달라진다.

## 090. QO40 · 프로필상 수용 여력이 낮아 보이는데 피크 수요를 반복적으로 견디는 대여소는 어디인가?

`branch_data`의 프로필 지표(`ilcd`, `iqr`)로 ‘수용 여력이 낮음’ 선별 규칙을 먼저 정의하고(상·하위 분위, 임계값 등), 해당 대여소 집합을 만든다. `count_data`에서 피크 수요 episode를 정의한 뒤(피크 임계값, 계절성 보정 여부, 최소 지속시간), 기간 내 episode 횟수로 ‘반복적 피크’를 계량화한다. ‘견딤’ 조건은 피크 동안 운영 이상(예: 부족 상태 동반 여부) 또는 피크 후 회복시간처럼 추가 기준이 필요하며, 어떤 기준을採用했는지와 판정 근거를 함께 기록한다. 최종 결과는 (저여력 프로필)∩(피크 반복)∩(견딤) 교집합의 대여소 목록과 각 단계 필터링에 사용된 지표 값을 함께 제시한다.

- answerability: needs-metric-definition
- evidence_sources: count_data.parquet, branch_data.parquet, ontology-lite
- requires_review: True
- review_reason: 프로필 지표(ilcd/iqr) 해석과 피크·견딤 판정(임계값, episode 규칙)이 정해지지 않으면 ‘예외 대여소’ 선별의 재현성이 없다.

## 091. QO41 · 특정 날짜 특정 대여소의 이상 현상을 날씨, 이동, 고장 근거를 묶어 한 번에 설명할 수 있는가?

입력된 날짜와 대여소 ID를 기준으로 count_data.parquet에서 시간순 스냅샷을 구성한 뒤, 재고/거치 상태의 급변·0 지속·포화 지속 구간을 이상 후보로 표시한다. 같은 시간축에 rent_data.parquet의 유출(시작 대여소)과 유입(반납 대여소)을 분리 집계해 순유출/순유입을 붙이고, broken_data.parquet의 고장·수리 이벤트와 weather_data.parquet의 강수·기온·풍속 등을 동일 시간창으로 매핑해 근거를 병렬로 제시한다. branch_data.parquet는 위치/권역 등 맥락 설명에 활용하되, 원인 단정의 1차 근거로 사용하지 않도록 근거 유형을 분리해 서술한다. 단일 원인으로 결론을 내리려면 이상 임계치·지속시간과 근거 우선순위(날씨/고장/이동의 충돌 처리)가 먼저 고정되어야 하며, 그 규칙에 따라 결과가 재현된다.

- answerability: needs-metric-definition
- evidence_sources: count_data.parquet, rent_data.parquet, broken_data.parquet, weather_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 이상 판정 임계치/지속시간과 다중 근거가 동시에 존재할 때의 우선순위 규칙이 합의돼야 동일한 설명을 자동 생성할 수 있다.

## 092. QO42 · 서로 부족과 과잉 역할을 번갈아 가지는 대여소 쌍은 어디인가?

count_data.parquet에서 대여소-시간창 단위로 ‘부족’과 ‘과잉’ 상태를 라벨링하는 파생 지표를 먼저 정의한 뒤(저재고/0 지속, 고재고/포화 지속 등), 시간창별 상태 시계열을 만든다. rent_data.parquet에서는 시작/반납을 분리해 OD 흐름과 순유출/순유입을 계산하고, (A 부족 & B 과잉)과 (A 과잉 & B 부족)이 각각 어떤 시간창에서 관측되는지 쌍 단위로 교차 확인한다. 이후 두 상태가 일정 기준 이상 반복되는 쌍만 남기고, branch_data.parquet의 거리/권역 정보를 이용해 비현실적인 장거리 조합이나 해석 불가능한 조합을 필터링한다. ‘번갈아’의 최소 반복 횟수, 주기(일/주/시간대), 허용 오차가 고정되어야 결과가 규칙적으로 재현된다.

- answerability: needs-metric-definition
- evidence_sources: count_data.parquet, rent_data.parquet, branch_data.parquet
- requires_review: True
- review_reason: 부족/과잉 임계치와 ‘번갈아’의 시간창·반복 기준에 따라 쌍 추출 결과가 크게 달라져 기준 확정이 필요하다.

## 093. QO43 · 스냅샷 변화를 보면 사실상 신설, 이동, 이름변경으로 봐야 하는 대여소 lifecycle 이벤트가 있는가?

branch_data.parquet의 스냅샷 시점별로 대여소 ID를 기준 자기조인하여 신규 등장, 좌표 변화, 명칭 변화 같은 변화를 탐지하고 이벤트 후보를 생성한다. 예를 들어 특정 시점에 ID가 새로 나타나면 신설 후보, 동일 ID에서 좌표/주소가 거리 임계치 이상 변하면 이동 후보, 좌표가 유지되면서 명칭만 바뀌면 이름변경 후보로 분류한다. 다만 ID가 바뀌면서 위치·명칭이 유사한 경우처럼 동일성 추론이 필요한 패턴은 규칙(거리/이름 유사도)과 예외 처리가 없으면 안정적으로 분류되지 않는다. 좌표계·단위와 주소 정규화 방식이 확인된 뒤 임계치를 적용하고, 후보 표본을 사람이 점검해 규칙을 보정하는 절차가 필요하다.

- answerability: needs-schema-confirmation
- evidence_sources: branch_data.parquet
- requires_review: True
- review_reason: 좌표계/단위와 주소·명칭 정규화가 확정되지 않으면 이동·동일성 추론 규칙이 과탐/미탐을 유발해 사람이 기준을 조정해야 한다.

## 094. QO44 · 어떤 답변은 직접 조인 근거보다 추론 조인 근거가 더 많아서 신뢰도 표기가 필요한가?

답변 생성 과정에서 사용된 근거를 엣지 단위로 기록하는 EvidenceGraph(또는 동등한 로그/메타 스키마)가 전제되어야 하며, 각 엣지에 direct(키 조인/동일 레코드 기반)와 inferred(규칙·유사도·휴리스틱 기반) 구분이 포함돼야 한다. 답변 ID 단위로 direct_edges와 inferred_edges를 집계해 inferred가 더 큰 경우를 플래그로 표시하고, 함께 사용된 rule_id와 입력 소스 목록을 반환하면 판정이 재현된다. 이런 라벨과 집계 규칙이 없으면 “추론 근거가 더 많다”를 자동으로 판별할 수 없으므로, 메타 필드(예: edge_type, rule_id, confidence_score, source_priority)를 설계해 두는 것이 핵심이다.

- answerability: needs-provenance
- evidence_sources: ontology-lite
- requires_review: True
- review_reason: direct/inferred 구분, 집계 단위(답변/클레임), rule_id 등 증거 그래프 메타데이터 정의가 선행돼야 자동 판정이 가능하다.

## 095. QO45 · 시작 대여소와 반납 대여소를 구분하지 않으면 완전히 다른 결론이 나오는 질문은 무엇인가?

rent_data.parquet에서 시작 대여소(branchnum_r)와 반납 대여소(branchnum_b)를 하나로 합쳐 집계하면 유출과 유입이 상쇄되어 방향성이 사라지므로, 역할 분리가 결론에 본질적으로 영향을 주는 질문을 식별해야 한다. 예를 들어 대여소의 순유출/순유입 판단, 공급자(유출 중심)·수요자(유입 중심) 구분, OD 불균형의 방향 추정처럼 ‘방향’이 핵심인 질문은 role-agnostic 집계로 해석이 달라진다. 따라서 질문 카탈로그를 대상으로 role-aware(시작/반납 분리) 결과와 role-agnostic(통합) 결과를 비교하고, 결론 변화가 유의미하다고 판정되는 질문을 목록화한다. 이 판정은 “완전히 다른 결론”의 기준(변화 임계치, 비교 기간/시간창)을 정의해야 자동화할 수 있다.

- answerability: needs-human-review
- evidence_sources: rent_data.parquet, ontology-lite
- requires_review: True
- review_reason: ‘완전히 다른 결론’의 판정 기준을 정한 뒤 질의별 비교 결과를 검토해 오탐(의미 없는 차이)을 걸러야 한다.

## 096. QO46 · `cnt_rack` 같은 컬럼이 실제로 무엇을 뜻하는지 모르면 어떤 질문들이 잘못 해석되는가?

cnt_rack이 용량(거치대 총량)인지, 현재 거치 가능 수인지, 현재 자전거 수(재고)인지에 따라 포화/빈 상태와 관련 지표의 해석이 달라지므로, count_data.parquet 기반의 부족/과잉 판정과 재배치 필요성 같은 질문이 우선적으로 왜곡된다. rent_data.parquet에 cnt_rack 또는 cnt_rack_b가 존재한다면 그 값이 대여/반납 직전·직후 상태인지, 스냅샷과 동일 정의인지가 확인되지 않으면 이벤트 데이터와 스냅샷을 잘못 비교하게 된다. 또한 uselate_data.parquet에서 이용률 등 분모/분자 구조의 지표를 만들 때 cnt_rack이 용량인지 재고인지가 고정되어야 산식이 성립한다. 따라서 의미, 단위, 갱신 시점(스냅샷/이벤트), 역할(시작/반납) 정보를 데이터 딕셔너리로 확정한 뒤 해석을 진행해야 한다.

- answerability: needs-schema-confirmation
- evidence_sources: count_data.parquet, rent_data.parquet, uselate_data.parquet
- requires_review: True
- review_reason: cnt_rack 계열의 의미·단위·기준시점·시작/반납 역할이 확정되지 않으면 포화/부족 및 이용률 산식이 일관되게 정의되지 않는다.

## 097. QO47 · 답변마다 근거 신뢰도와 source priority를 같이 내보내야 하는 질문은 무엇인가?

여러 파일을 결합해 원인 후보나 종합 설명을 만드는 질문은 근거 간 충돌 가능성이 있으므로 source priority와 confidence를 함께 출력하는 대상으로 분류한다. 예를 들어 count_data.parquet의 상태 변화에 대해 rent_data.parquet의 유입/유출, broken_data.parquet의 공급 제약, weather_data.parquet의 외부 요인을 동시에 연결하는 경우 각 근거가 직접측정인지 파생/추론인지 구분하고 우선순위를 명시해야 설명이 재현된다. 반면 단일 소스의 단순 집계(기간별 건수, 평균 등)는 일반적으로 우선순위/신뢰도 표기 요구가 낮다. 분류를 자동화하려면 ontology-lite(또는 로그 스키마)에 evidence_unit, source_priority, confidence, rule_id 같은 메타데이터와 ‘다중 소스 결합 여부/결론 단정 위험도’ 태깅 규칙이 필요하다.

- answerability: needs-provenance
- evidence_sources: count_data.parquet, rent_data.parquet, broken_data.parquet, weather_data.parquet, ontology-lite
- requires_review: True
- review_reason: 소스 우선순위와 confidence 산정은 소스 품질 기준 및 결합/추론 규칙을 정해야 일관되게 적용된다.

## 098. QO48 · 상위 운영 질문 10개를 가장 적은 class 수로 덮으려면 최소 온톨로지 slice가 무엇인가?

상위 운영 질문 10개를 대상으로 각 질문이 요구하는 엔터티/이벤트/근거 유형을 태깅한 뒤, 중복을 최소화하는 방향으로 class 후보를 압축해 최소 slice를 설계한다. 예를 들어 Station, TripEvent, InventorySnapshot(스냅샷), WeatherObservation, FaultEvent 같은 핵심 클래스와, start/end 역할·관측시각·대여소 연결을 표현하는 최소 relation만 남기는 방식으로 커버리지를 평가한다. 이때 coverage(질문 충족)와 단순성(클래스 수 최소화) 사이의 우선순위와 제외 기준을 문서화해야 결과가 재현된다. ontology-lite 또는 별도 benchmark mapping artifact에 질문-구성요소 매핑이 있다면 후보 slice별 커버리지 계산은 가능하지만, ‘상위 10개’ 선정 기준과 class 경계는 설계 결정 사항이다.

- answerability: inferential-only
- evidence_sources: ontology-lite
- requires_review: True
- review_reason: 상위 질문 선정 기준과 class 경계(무엇을 합치고 나눌지)는 평가 목적에 따라 달라 사람이 설계 결정을 확정해야 한다.

## 099. QO49 · 질문 커버리지 기준으로 가장 재사용성이 높은 class와 relation은 무엇인가?

ontology-lite 또는 별도 benchmark mapping artifact에 ‘질문 ↔ class/relation’ 매핑이 존재한다는 전제에서, 재사용성 점수를 질문 등장 빈도와 질문 그룹 간 교차 사용도(필요 시 중요도 가중치 포함)로 정의해 집계한다. 집계 시 한 질문 내 중복 출현을 1회로 처리할지, 실제 사용 횟수로 셀지 규칙을 먼저 고정하고, 그 규칙에 따라 class/relation별 점수를 계산해 상위 항목을 정렬 반환한다. 가중치 컬럼이 있다면 가중합으로 확장하되, 가중치의 의미와 범위를 확인해야 해석이 일관된다. 즉, 계산 자체는 GROUP BY로 가능하지만 메타 스키마 필드 정의가 선행돼야 한다.

- answerability: needs-schema-confirmation
- evidence_sources: ontology-lite
- requires_review: True
- review_reason: 질문-온톨로지 매핑 필드, 가중치 의미, 중복 카운트 규칙이 확정되지 않으면 재사용성 순위가 집계 방식에 따라 달라진다.

## 100. QO50 · provenance와 confidence edge가 없으면 끝내 답하지 못하는 질문은 어떤 것들인가?

여러 근거를 비교해 하나의 설명이나 원인 후보를 채택해야 하는 질문은, 근거의 출처와 신뢰 수준을 표현하는 provenance/confidence 엣지가 없으면 결론 선택 기준을 재현할 수 없다. 또한 ID 변경 추정, 유사도 기반 매칭처럼 inferred edge가 핵심인 관계 질의는 rule_id와 근거가 남지 않으면 연결 자체를 검증할 수 없다. 마지막으로 여러 소스를 조인해 만든 파생 이벤트/지표는 입력 버전과 생성 규칙이 기록되지 않으면 동일 결과를 다시 구성하기 어렵다. 따라서 ontology-lite(또는 동등한 메타 스키마)에는 최소한 edge_type(direct/inferred), rule_id, source_list, source_priority, confidence(점수 또는 등급), 생성 시각/버전, 답변 단위 EvidenceGraph 식별자가 필요하며, 어떤 질문을 ‘필수 의존’으로 분류할지 기준도 함께 정의돼야 한다.

- answerability: needs-provenance
- evidence_sources: ontology-lite
- requires_review: True
- review_reason: ‘답변 가능’의 기준과 provenance/confidence 최소 필드가 합의돼야 질문별로 의존성(없으면 불가)을 일관되게 분류할 수 있다.
