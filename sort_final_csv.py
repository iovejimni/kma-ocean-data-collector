"""
[정렬 전용] API 호출 없이, 지금 있는 sea_obs_stn22441_full_hourly.csv를
TM(관측시각) 기준으로 정렬 + 중복제거만 한다.

사용법:
    python sort_final_csv.py
"""

import csv
import os

FINAL_CSV = "sea_obs_stn22441_full_hourly.csv"

COLUMNS = [
    "TP", "TM", "STN_ID", "STN_KO", "LON", "LAT",
    "WH", "WD", "WS", "WS_GST", "TW", "TA", "PA", "HM"
]


def main():
    if not os.path.exists(FINAL_CSV):
        print(f"⚠️ {FINAL_CSV} 파일이 없습니다.")
        return

    with open(FINAL_CSV, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        rows = [r for r in reader if r and len(r) >= 2]

    before = len(rows)
    print(f"정렬 전 행 수: {before}")

    seen = {}
    for r in rows:
        tm = r[1].strip()
        seen[tm] = r  # 같은 TM이 여러 번 있으면 마지막 값으로 덮어씀 (중복 제거)

    sorted_tms = sorted(seen.keys())

    with open(FINAL_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for tm in sorted_tms:
            writer.writerow(seen[tm])

    print(f"정렬/중복제거 후 행 수: {len(sorted_tms)}")
    if before != len(sorted_tms):
        print(f"(중복 제거로 {before - len(sorted_tms)}행이 줄었습니다)")

    if sorted_tms:
        print(f"\n데이터 범위: {sorted_tms[0]} ~ {sorted_tms[-1]}")

    print(f"\n✅ 완료! {FINAL_CSV}가 시간순으로 정렬되었습니다.")


if __name__ == "__main__":
    main()
