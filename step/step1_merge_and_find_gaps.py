"""
[1단계] 두 폴더에 흩어진 CSV를 하나로 합치고, 빠진 시간대를 찾는다.

- 두 CSV를 합쳐서 TM(관측시각) 기준 중복 제거
- 결과를 새 파일(MERGED)로 저장
- START_TM ~ 마지막 수집 시각 사이에서, 시간(hour) 단위로 비어있는 구간을 찾아
  missing_hours.txt로 저장 (2단계에서 이걸로 재수집)

실행 전에 아래 CSV_PATHS 경로가 실제 파일 위치와 맞는지 확인하세요.
"""

import csv
import os
from datetime import datetime, timedelta

CSV_PATHS = [
    r"C:\Users\user\Desktop\ocean_data\sea_obs_stn22441_full_hourly.csv",
    r"C:\Users\user\Desktop\ocean_data\data_download\sea_obs_stn22441_full_hourly.csv"
]

OUT_DIR = r"C:\Users\user\Desktop\ocean_data"
MERGED_OUT = os.path.join(OUT_DIR, "sea_obs_stn22441_MERGED.csv")
MISSING_OUT = os.path.join(OUT_DIR, "sea_obs_stn22441_missing_hours.txt")

COLUMNS = [
    "TP", "TM", "STN_ID", "STN_KO", "LON", "LAT",
    "WH", "WD", "WS", "WS_GST", "TW", "TA", "PA", "HM"
]

START_TM = datetime(2011, 11, 15, 0, 0)


def load_rows(path):
    rows = []
    if not os.path.exists(path):
        print(f"⚠️ 파일 없음: {path}")
        return rows
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if row and len(row) >= 2:
                rows.append(row)
    return rows


def main():
    all_rows = []
    for p in CSV_PATHS:
        rows = load_rows(p)
        print(f"{p} : {len(rows)}행 로드")
        all_rows.extend(rows)

    # TM(두번째 컬럼) 기준 중복 제거
    seen = {}
    for r in all_rows:
        tm = r[1].strip()
        seen[tm] = r

    print(f"\n중복 제거 후 고유 시각 수: {len(seen)}개")

    sorted_tms = sorted(seen.keys())

    with open(MERGED_OUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for tm in sorted_tms:
            writer.writerow(seen[tm])

    print(f"✅ 병합 완료 -> {MERGED_OUT}")

    if not sorted_tms:
        print("데이터가 하나도 없어서 빠진 시간대 계산을 건너뜁니다.")
        return

    last_tm = datetime.strptime(sorted_tms[-1], "%Y%m%d%H%M")

    # 실제 관측시각을 '정시' 기준으로 정규화해서 비교
    existing_hours = set()
    for tm in sorted_tms:
        dt = datetime.strptime(tm, "%Y%m%d%H%M")
        existing_hours.add(dt.replace(minute=0, second=0))

    missing = []
    t = START_TM
    while t <= last_tm:
        if t not in existing_hours:
            missing.append(t)
        t += timedelta(hours=1)

    with open(MISSING_OUT, "w", encoding="utf-8") as f:
        for m in missing:
            f.write(m.strftime("%Y%m%d%H%M") + "\n")

    print(f"\n분석 범위: {START_TM.strftime('%Y-%m-%d %H:%M')} ~ {last_tm.strftime('%Y-%m-%d %H:%M')}")
    print(f"빠진 시간대: {len(missing)}개 -> {MISSING_OUT}에 저장했습니다.")
    print("\n다음 단계: step2_fill_gaps.py 를 실행해서 빠진 시간대를 재수집하세요.")


if __name__ == "__main__":
    main()
