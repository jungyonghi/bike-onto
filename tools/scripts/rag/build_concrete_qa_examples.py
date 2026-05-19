# Timestamp: 2026-05-19 23:10:00

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds

TOOLS_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_SCRIPTS_DIR))

from rag.natural_language_labels import display_value

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BASE = PROJECT_ROOT / "data/processed/parquet/bike_cloud"


def _read(name: str, columns: list[str] | None = None) -> pd.DataFrame:
    return pd.read_parquet(BASE / name, columns=columns)


def _table(name: str, columns: list[str], filter_expr: Any | None = None) -> pd.DataFrame:
    return ds.dataset(BASE / name).to_table(columns=columns, filter=filter_expr).to_pandas()


def _fmt_int(value: Any) -> str:
    return f"{int(value):,}"


def _fmt_float(value: Any, digits: int = 2) -> str:
    return f"{float(value):,.{digits}f}"


def _top_list(df: pd.DataFrame, label_col: str, value_col: str, n: int = 5) -> str:
    parts = []
    for i, row in enumerate(df.head(n).itertuples(index=False), start=1):
        label = getattr(row, label_col)
        value = getattr(row, value_col)
        value_text = _fmt_int(value) if float(value).is_integer() else _fmt_float(value)
        parts.append(f"{i}) {label} {value_text}")
    return "; ".join(parts)


def main() -> int:
    out_dir = PROJECT_ROOT / "docs/qa/2026-05-19/concrete_user_qa_examples"
    out_dir.mkdir(parents=True, exist_ok=True)
    qa: list[dict[str, str]] = []

    branch = _read("branch_data.parquet")
    branch["date"] = pd.to_datetime(branch["date"], errors="coerce").dt.date
    latest_date = branch["date"].dropna().max()
    latest_branch = branch[branch["date"] == latest_date].copy()
    latest_branch["branchnum"] = latest_branch["branchnum"].astype(int)
    latest_by_station = branch.dropna(subset=["date", "branchnum"]).sort_values("date").groupby("branchnum", as_index=False).tail(1).copy()
    latest_by_station["branchnum"] = latest_by_station["branchnum"].astype(int)
    name_map = latest_by_station.set_index("branchnum")["branchname"].to_dict()
    district_map = latest_by_station.set_index("branchnum")["location1"].to_dict()

    qa.append({"qid": "CQA01", "question": "대여소별 최신 레코드 기준 등록 대여소는 몇 개인가?", "answer": f"대여소별로 가장 최근 date 1건만 남기면 등록 대여소는 {_fmt_int(latest_by_station['branchnum'].nunique())}개입니다. branch_data의 전체 글로벌 최댓값({latest_date})은 일부 대여소만 포함해 스냅샷 기준으로 쓰기 어렵기 때문에, 여기서는 대여소별 최신 레코드 기준으로 계산했습니다."})
    top_district = latest_by_station.groupby("location1")["branchnum"].nunique().sort_values(ascending=False).reset_index(name="station_count")
    qa.append({"qid": "CQA02", "question": "대여소별 최신 레코드 기준 대여소가 가장 많은 자치구 TOP 5는 어디인가?", "answer": f"상위 5개 자치구는 {_top_list(top_district, 'location1', 'station_count')}입니다."})
    sy_counts = latest_by_station.groupby("sy")["branchnum"].nunique().sort_values(ascending=False).reset_index(name="station_count")
    qa.append({"qid": "CQA03", "question": "대여소별 최신 레코드 기준 유형(sy)별 대여소 수는 어떻게 되는가?", "answer": f"유형별 대여소 수는 {_top_list(sy_counts, 'sy', 'station_count', n=len(sy_counts))}입니다."})
    top_iqr = latest_by_station.drop_duplicates(subset=["branchnum"]).sort_values(["iqr", "branchnum"], ascending=[False, True]).head(5).copy()
    top_iqr["label"] = top_iqr.apply(lambda r: f"{r['branchname']}({int(r['branchnum'])})", axis=1)
    qa.append({"qid": "CQA04", "question": "대여소별 최신 레코드 기준 iqr 상위 5개 대여소는 어디인가?", "answer": f"iqr 상위 5개는 {_top_list(top_iqr[['label','iqr']], 'label', 'iqr')}입니다. iqr의 정확한 의미는 별도 지표 정의에 따라 해석해야 합니다."})
    station_102 = latest_by_station[latest_by_station["branchnum"] == 102].iloc[0]
    qa.append({"qid": "CQA05", "question": "대여소 102의 최신 프로필은 무엇인가?", "answer": f"대여소 102는 {station_102['date']} 기준 '{station_102['branchname']}'이며 자치구는 {station_102['location1']}, 주소/위치는 {station_102['location2']}입니다. 좌표는 ({station_102['branch_x']}, {station_102['branch_y']}), 유형은 {station_102['sy']}입니다."})

    target_day = date(2024, 12, 31)
    count_day = _table("count_data.parquet", ["date_rt", "branchnum", "hour_cnt", "cnt_rack"], pc.field("date_rt") == target_day)
    qa.append({"qid": "CQA06", "question": f"{target_day} 전체 cnt_rack 합계는 얼마인가?", "answer": f"{target_day}의 cnt_rack 합계는 {_fmt_int(count_day['cnt_rack'].sum())}입니다. 이 값은 원본 cnt_rack을 그대로 합산한 결과이며, cnt_rack의 업무적 의미는 스키마 정의에 따라 해석해야 합니다."})
    station_102_day = count_day[count_day["branchnum"] == 102].sort_values("hour_cnt")
    peak_102 = station_102_day.loc[station_102_day["cnt_rack"].idxmax()]
    qa.append({"qid": "CQA07", "question": f"{target_day} 대여소 102의 cnt_rack 최고 시간대는 언제인가?", "answer": f"대여소 102('{name_map.get(102, '명칭 미확인')}')는 {target_day} {int(peak_102['hour_cnt'])}시에 cnt_rack {_fmt_int(peak_102['cnt_rack'])}로 가장 높았습니다."})
    top_8 = count_day[count_day["hour_cnt"] == 8].groupby("branchnum", as_index=False)["cnt_rack"].sum().sort_values("cnt_rack", ascending=False).head(5)
    top_8["label"] = top_8["branchnum"].astype(int).map(lambda x: f"{name_map.get(x, '명칭 미확인')}({x})")
    qa.append({"qid": "CQA08", "question": f"{target_day} 08시에 cnt_rack이 가장 높은 대여소 TOP 5는 어디인가?", "answer": f"{target_day} 08시 기준 TOP 5는 {_top_list(top_8[['label','cnt_rack']], 'label', 'cnt_rack')}입니다."})
    count_day["district"] = count_day["branchnum"].astype(int).map(district_map)
    district_hour8 = count_day[count_day["hour_cnt"] == 8].groupby("district", as_index=False)["cnt_rack"].sum().dropna().sort_values("cnt_rack", ascending=False).head(5)
    qa.append({"qid": "CQA09", "question": f"{target_day} 08시 자치구별 cnt_rack 합계 TOP 5는 어디인가?", "answer": f"상위 자치구는 {_top_list(district_hour8, 'district', 'cnt_rack')}입니다."})
    hour_dist = count_day.groupby("hour_cnt", as_index=False)["cnt_rack"].sum().sort_values("cnt_rack", ascending=False).head(3)
    hour_dist["label"] = hour_dist["hour_cnt"].astype(int).astype(str) + "시"
    qa.append({"qid": "CQA10", "question": f"{target_day} cnt_rack 합계가 큰 시간대는 언제인가?", "answer": f"상위 시간대는 {_top_list(hour_dist[['label','cnt_rack']], 'label', 'cnt_rack', n=3)}입니다."})

    start = datetime(2024, 12, 31)
    end = datetime(2025, 1, 1)
    rent_day = _table("rent_data.parquet", ["rentt", "bikenum", "branchnum_r", "branchnum_b", "hour_cnt", "dist"], (pc.field("rentt") >= start) & (pc.field("rentt") < end))
    qa.append({"qid": "CQA11", "question": "2024-12-31 총 대여 건수는 몇 건인가?", "answer": f"2024-12-31 rentt 기준 총 대여 건수는 {_fmt_int(len(rent_day))}건입니다."})
    top_start = rent_day.groupby("branchnum_r").size().reset_index(name="cnt").sort_values("cnt", ascending=False).head(5)
    top_start["label"] = top_start["branchnum_r"].astype(int).map(lambda x: f"{name_map.get(x, '명칭 미확인')}({x})")
    qa.append({"qid": "CQA12", "question": "2024-12-31 시작 대여소 TOP 5는 어디인가?", "answer": f"시작 대여 기준 TOP 5는 {_top_list(top_start[['label','cnt']], 'label', 'cnt')}입니다."})
    top_return = rent_day.groupby("branchnum_b").size().reset_index(name="cnt").sort_values("cnt", ascending=False).head(5)
    top_return["label"] = top_return["branchnum_b"].astype(int).map(lambda x: f"{name_map.get(x, '명칭 미확인')}({x})")
    qa.append({"qid": "CQA13", "question": "2024-12-31 반납 대여소 TOP 5는 어디인가?", "answer": f"반납 대여 기준 TOP 5는 {_top_list(top_return[['label','cnt']], 'label', 'cnt')}입니다."})
    same_excluded = rent_day[rent_day["branchnum_r"] != rent_day["branchnum_b"]]
    top_od = same_excluded.groupby(["branchnum_r", "branchnum_b"]).size().reset_index(name="cnt").sort_values("cnt", ascending=False).head(5)
    top_od["label"] = top_od.apply(lambda r: f"{name_map.get(int(r['branchnum_r']), '명칭 미확인')}({int(r['branchnum_r'])})→{name_map.get(int(r['branchnum_b']), '명칭 미확인')}({int(r['branchnum_b'])})", axis=1)
    qa.append({"qid": "CQA14", "question": "2024-12-31 같은 대여소 회귀를 제외한 시작-반납 OD TOP 5는 무엇인가?", "answer": f"동일 대여소 회귀를 제외하면 TOP 5 OD는 {_top_list(top_od[['label','cnt']], 'label', 'cnt')}입니다."})
    long_rows = rent_day.dropna(subset=["bikenum", "branchnum_r", "branchnum_b", "dist"]).sort_values("dist", ascending=False).head(3).copy()
    long_rows["label"] = long_rows.apply(lambda r: f"자전거 {int(r['bikenum'])}, {name_map.get(int(r['branchnum_r']), '명칭 미확인')}→{name_map.get(int(r['branchnum_b']), '명칭 미확인')}", axis=1)
    qa.append({"qid": "CQA15", "question": "2024-12-31 이동거리가 가장 긴 대여 기록 TOP 3은 무엇인가?", "answer": f"상위 3건은 {_top_list(long_rows[['label','dist']], 'label', 'dist', n=3)}입니다. dist 단위는 원본 스키마 확인 후 최종 해석해야 합니다."})
    station_102_rent = rent_day[(rent_day["branchnum_r"] == 102) | (rent_day["branchnum_b"] == 102)]
    out_count = int((station_102_rent["branchnum_r"] == 102).sum())
    in_count = int((station_102_rent["branchnum_b"] == 102).sum())
    qa.append({"qid": "CQA16", "question": "2024-12-31 대여소 102의 순유입은 얼마인가?", "answer": f"대여소 102('{name_map.get(102, '명칭 미확인')}')는 시작 대여 {out_count:,}건, 반납 {in_count:,}건입니다. 순유입(반납-시작)은 {in_count - out_count:,}건입니다."})
    dist5 = int((rent_day["dist"] >= 5000).sum())
    qa.append({"qid": "CQA17", "question": "2024-12-31 이동거리 5,000 이상 대여는 몇 건인가?", "answer": f"dist >= 5,000 조건을 적용하면 {_fmt_int(dist5)}건입니다. dist가 미터 단위라는 전제의 계산이므로, 단위가 다르면 임계값을 바꿔야 합니다."})

    broken = _read("broken_data.parquet")
    qa.append({"qid": "CQA18", "question": "전체 고장 이벤트 수는 몇 건인가?", "answer": f"broken_data.parquet 기준 전체 고장 이벤트는 {_fmt_int(len(broken))}건입니다."})
    type_counts = broken.groupby("type_bk").size().reset_index(name="cnt").sort_values("cnt", ascending=False).head(5)
    qa.append({"qid": "CQA19", "question": "고장 유형 TOP 5는 무엇인가?", "answer": f"고장 유형 TOP 5는 {_top_list(type_counts, 'type_bk', 'cnt')}입니다."})
    broken_20241231 = broken[(broken["date_bk"] >= pd.Timestamp("2024-12-31")) & (broken["date_bk"] < pd.Timestamp("2025-01-01"))]
    qa.append({"qid": "CQA20", "question": "2024-12-31 고장 이벤트는 몇 건인가?", "answer": f"2024-12-31 발생한 고장 이벤트는 {_fmt_int(len(broken_20241231))}건입니다."})
    top_bike_broken = broken.groupby("bikenum").size().reset_index(name="cnt").sort_values("cnt", ascending=False).head(3)
    top_bike_broken["label"] = top_bike_broken["bikenum"].astype(int).astype(str)
    qa.append({"qid": "CQA21", "question": "고장 기록이 가장 많은 자전거 TOP 3은 무엇인가?", "answer": f"고장 기록 TOP 3 자전거는 {_top_list(top_bike_broken[['label','cnt']], 'label', 'cnt', n=3)}입니다."})

    weather = _read("weather_data.parquet")
    weather_2024 = weather[(weather["datetime"] >= pd.Timestamp("2024-01-01")) & (weather["datetime"] < pd.Timestamp("2025-01-01"))]
    precip_hours = int((weather_2024["precipitation"] > 0).sum())
    qa.append({"qid": "CQA22", "question": "2024년에 강수량이 0보다 큰 시간은 몇 번인가?", "answer": f"2024년 weather_data 기준 precipitation > 0인 시간은 {_fmt_int(precip_hours)}회입니다."})
    max_wind = weather_2024.sort_values("windspeed", ascending=False).iloc[0]
    qa.append({"qid": "CQA23", "question": "2024년 풍속이 가장 높았던 시각은 언제인가?", "answer": f"2024년 최고 풍속은 {max_wind['datetime']}의 {max_wind['windspeed']}입니다."})
    low_vis = weather_2024.dropna(subset=["visibility"]).sort_values("visibility", ascending=True).iloc[0]
    qa.append({"qid": "CQA24", "question": "2024년 가시거리가 가장 낮았던 시각은 언제인가?", "answer": f"2024년 최저 가시거리는 {low_vis['datetime']}의 {low_vis['visibility']}입니다."})
    holiday_avg = weather_2024[weather_2024["holiday"] == 1]["count"].mean()
    qa.append({"qid": "CQA25", "question": "2024년 공휴일 평균 count는 얼마인가?", "answer": f"2024년 holiday=1인 레코드의 count 평균은 {_fmt_float(holiday_avg)}입니다. count의 업무적 의미는 weather_data 스키마 기준으로 해석해야 합니다."})
    monthly_temp = weather_2024.assign(month=weather_2024["datetime"].dt.to_period("M").astype(str)).groupby("month", as_index=False)["temperature"].mean()
    cold = monthly_temp.sort_values("temperature").iloc[0]
    hot = monthly_temp.sort_values("temperature", ascending=False).iloc[0]
    qa.append({"qid": "CQA26", "question": "2024년 월평균 기온이 가장 낮고 높은 달은 언제인가?", "answer": f"월평균 기온 최저는 {cold['month']}({_fmt_float(cold['temperature'])}), 최고는 {hot['month']}({_fmt_float(hot['temperature'])})입니다."})

    newmeta = _read("newmeta.parquet")
    month_new = newmeta.groupby("new_dt", as_index=False)["new"].sum().sort_values("new", ascending=False).head(3)
    month_new["label"] = month_new["new_dt"].astype(str)
    qa.append({"qid": "CQA27", "question": "신규 가입자가 가장 많았던 월 TOP 3은 언제인가?", "answer": f"월별 신규 가입자 합계 TOP 3은 {_top_list(month_new[['label','new']], 'label', 'new', n=3)}입니다."})
    age_new = newmeta.groupby("age", as_index=False)["new"].sum().sort_values("new", ascending=False).head(5)
    age_new["label"] = age_new["age"].astype(str)
    qa.append({"qid": "CQA28", "question": "신규 가입자가 많은 연령대 TOP 5는 무엇인가?", "answer": f"age 기준 TOP 5는 {_top_list(age_new[['label','new']], 'label', 'new')}입니다. age가 정수 나이인지 연령대 코드인지는 스키마 확인 후 라벨링해야 합니다."})
    gender_new = newmeta.groupby("gender", as_index=False)["new"].sum().sort_values("new", ascending=False)
    gender_new["label"] = gender_new["gender"].map(lambda value: display_value("gender", value))
    qa.append({"qid": "CQA29", "question": "성별별 신규 가입자 합계는 어떻게 되는가?", "answer": f"성별별 신규 가입자 합계는 {_top_list(gender_new[['label','new']], 'label', 'new', n=len(gender_new))}입니다. 원본 CSV의 성별 값은 F/M이고, 전처리된 newmeta.parquet에서는 F→0.0, M→1.0으로 코드화되어 있어 사용자-facing 답변에서는 라벨로 복원했습니다."})

    uselate = _read("uselate_data.parquet")
    u_month = pd.Timestamp("2024-12-01").date()
    u_dec = uselate[uselate["date_ym"] == u_month].copy()
    u_dec["total_usage"] = u_dec["cnt_r"] + u_dec["cnt_b"]
    top_u = u_dec.sort_values("total_usage", ascending=False).head(5)
    top_u["label"] = top_u["branchnum"].astype(int).map(lambda x: f"{name_map.get(x, '명칭 미확인')}({x})")
    qa.append({"qid": "CQA30", "question": "2024-12 월간 보조 집계에서 cnt_r+cnt_b가 높은 대여소 TOP 5는 어디인가?", "answer": f"2024-12 기준 cnt_r+cnt_b TOP 5는 {_top_list(top_u[['label','total_usage']], 'label', 'total_usage')}입니다."})

    jsonl_path = out_dir / "concrete_user_qa_examples_30.jsonl"
    md_path = out_dir / "concrete_user_qa_examples_30.md"
    jsonl_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in qa), encoding="utf-8")
    lines = ["# Concrete User-facing QA Examples", "", "실제 parquet 데이터를 실행해 숫자/대상까지 채운 예시입니다.", ""]
    for i, row in enumerate(qa, start=1):
        lines.extend([f"{i:03d}. {row['qid']}", f"- 질의: {row['question']}", f"- 답변: {row['answer']}", ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
