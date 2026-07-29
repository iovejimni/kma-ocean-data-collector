"""
[3단계] step2에서 복구된 행들은 파일 맨 뒤에 순서 없이 追加돼 있으므로,
마지막으로 전체를 TM 기준으로 다시 정렬 + 중복 제거해서 깔끔하게 정리한다.

이 스크립트를 돌리고 나면 sea_obs_stn22441_MERGED.csv 가 최종본입니다.
"""

import csv
import os
from datetime import datetime

OUT_DIR = r"C:\Users\user\Desktop\ocean_data"
MERGED_CSV = os.path.join(OUT_DIR, "sea_obs_stn22441_MERGED.csv")

COLUMNS = [
    "TP", "TM", "STN_ID", "STN_KO", "LON", "LAT",
    "WH", "WD", "WS", "WS_GST", "TW", "TA", "PA", "HM"
]


def main():
    with open(MERGED_CSV, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        rows = [r for r in reader if r and len(r) >= 2]

    print(f"정렬 전 행 수: {len(rows)}")

    # TM 기준 중복 제거 (나중 값으로 덮어씀)
    seen = {}
    for r in rows:
        tm = r[1].strip()
        seen[tm] = r

    sorted_tms = sorted(seen.keys())
    print(f"중복 제거/정렬 후 행 수: {len(sorted_tms)}")

    with open(MERGED_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for tm in sorted_tms:
            writer.writerow(seen[tm])

    if sorted_tms:
        first_dt = datetime.strptime(sorted_tms[0], "%Y%m%d%H%M")
        last_dt = datetime.strptime(sorted_tms[-1], "%Y%m%d%H%M")
        print(f"\n최종 데이터 범위: {first_dt} ~ {last_dt}")

    print(f"\n✅ 최종 정리 완료 -> {MERGED_CSV}")


if __name__ == "__main__":
    main()
