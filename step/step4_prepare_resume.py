"""
[4단계] step3까지 끝낸 최종 병합 파일을,
run_collect.bat(collect_full_history.py)이 계속 이어서 쓸 수 있도록 정리한다.

동작:
1. sea_obs_stn22441_MERGED.csv 를
   sea_obs_stn22441_full_hourly.csv 라는 이름으로 ocean_data 폴더에 덮어씌운다.
   (원래 조각나 있던 파일을 최종본으로 교체)
2. 병합 파일에서 가장 마지막(최신) TM 값을 찾아서
   sea_obs_stn22441_full_hourly.checkpoint 에 저장한다.
   -> 다음 실행부터는 이 시각 바로 다음부터 이어서 수집한다.

실행 후에는 run_collect.bat 을 그대로 실행하면 됩니다.

주의: data_download 폴더 안의 옛날 파일/체크포인트는 이제 안 씁니다.
     (지우거나, 혼동 방지를 위해 old_backup 폴더로 옮겨두는 걸 추천)
"""

import csv
import os
import shutil
from datetime import datetime

OUT_DIR = r"C:\Users\user\Desktop\ocean_data"
MERGED_CSV = os.path.join(OUT_DIR, "sea_obs_stn22441_MERGED.csv")

FINAL_CSV = os.path.join(OUT_DIR, "sea_obs_stn22441_full_hourly.csv")
FINAL_CHECKPOINT = os.path.join(OUT_DIR, "sea_obs_stn22441_full_hourly.checkpoint")


def main():
    if not os.path.exists(MERGED_CSV):
        print(f"⚠️ {MERGED_CSV} 이 없습니다. step1~3을 먼저 끝내주세요.")
        return

    # 1) 병합 파일을 최종 파일명으로 복사 (기존 조각 파일 덮어씀)
    shutil.copyfile(MERGED_CSV, FINAL_CSV)
    print(f"✅ {MERGED_CSV}\n   -> {FINAL_CSV} 로 복사(교체) 완료")

    # 2) 마지막 TM 찾기
    with open(MERGED_CSV, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        last_tm = None
        for row in reader:
            if row and len(row) >= 2:
                last_tm = row[1].strip()

    if not last_tm:
        print("⚠️ 병합 파일에 데이터가 없어서 체크포인트를 만들 수 없습니다.")
        return

    with open(FINAL_CHECKPOINT, "w") as f:
        f.write(last_tm)

    dt = datetime.strptime(last_tm, "%Y%m%d%H%M")
    print(f"✅ 체크포인트 저장: {last_tm} ({dt})")
    print(f"   -> {FINAL_CHECKPOINT}")
    print(f"\n다음 실행부터는 {dt} 다음 시각부터 이어서 수집합니다.")
    print("이제 run_collect.bat 을 실행하시면 됩니다.")


if __name__ == "__main__":
    main()
