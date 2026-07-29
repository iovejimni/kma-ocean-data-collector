"""
[전체 구간 결측 복구] 2011-11-15 ~ 현재 체크포인트 시각까지 전체를 훑어서
비어있는 시간대를 찾고, 하나씩 재조회해서 채워넣는다.

- 지금까지 모은 sea_obs_stn22441_full_hourly.csv 전체를 대상으로 검사
- 진짜 결측(200 응답인데 데이터 없음)과, 재조회로 복구 가능한 것(403/타임아웃으로 놓친 것)을 구분
- 중단·재개 가능

사용법:
    python find_and_fill_all_gaps.py
"""

import csv
import os
import time
import threading
import ctypes
import requests
from datetime import datetime, timedelta


def load_env_file(path=".env"):
    """.env 파일이 있으면 읽어서 os.environ에 반영 (외부 라이브러리 없이 최소 구현)"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env_file()

KMA_AUTH_KEY = os.environ.get("KMA_AUTH_KEY")
if not KMA_AUTH_KEY:
    raise SystemExit(
        "⚠️ KMA_AUTH_KEY가 설정되어 있지 않습니다.\n"
        "   .env.example을 복사해서 .env로 이름을 바꾸고, 그 안에 실제 발급받은 키를 넣어주세요."
    )

# BASE_URL은 예시 파라미터(tm/stn/authKey)가 박힌 형태 그대로 두고, 실행 시 실제 값으로 치환해서 사용
BASE_URL = "https://apihub.kma.go.kr/api/typ01/url/sea_obs.php?tm=202301241200&stn=0&help=1&authKey=YOUR_AUTH_KEY_HERE"
STN = "22441"
TP_FILTER = {"B", "C"}

REQUEST_DELAY_SEC = 3
RETRY_DELAY_SEC = 10
MAX_RETRIES = 3

OUT_DIR = r"C:\Users\user\Desktop\ocean_data"
FINAL_CSV = os.path.join(OUT_DIR, "sea_obs_stn22441_full_hourly.csv")
MAIN_CHECKPOINT = os.path.join(OUT_DIR, "sea_obs_stn22441_full_hourly.checkpoint")
RECOVER_CHECKPOINT = os.path.join(OUT_DIR, "recover_all_gaps.checkpoint")
STILL_MISSING_LOG = os.path.join(OUT_DIR, "sea_obs_stn22441_all_still_missing.txt")

COLUMNS = [
    "TP", "TM", "STN_ID", "STN_KO", "LON", "LAT",
    "WH", "WD", "WS", "WS_GST", "TW", "TA", "PA", "HM"
]

# 전체 기간의 진짜 시작점 (실측으로 확인했던 데이터 시작 시각)
GAP_START = datetime(2011, 11, 15, 0, 0)


def show_popup(message: str, title: str = "전체 결측 복구 알림"):
    def _show():
        try:
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x40000)
        except Exception:
            pass
    threading.Thread(target=_show, daemon=True).start()


def call_api(tm: str):
    # BASE_URL에 이미 tm/stn/authKey가 박혀있으므로, 우리가 원하는 값으로 치환해서 사용
    url = BASE_URL
    url = url.replace("tm=202301241200", f"tm={tm}")
    url = url.replace("stn=0", f"stn={STN}")
    url = url.replace("authKey=YOUR_AUTH_KEY_HERE", f"authKey={KMA_AUTH_KEY}")
    resp = requests.get(url, timeout=30)
    resp.encoding = "euc-kr"
    raw = resp.text
    if "�" in raw:
        resp.encoding = "utf-8"
        raw = resp.text
    return resp.status_code, raw


def call_api_with_retry(tm: str):
    for attempt in range(MAX_RETRIES + 1):
        try:
            status, raw = call_api(tm)
        except requests.exceptions.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC)
                continue
            return "TIMEOUT", ""
        if status == 200:
            return status, raw
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SEC)
    return status, raw


def parse_data_lines(raw: str):
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.rstrip(",=").rstrip("=")
        parts = [p.strip() for p in line.split(",")]
        rows.append(parts)
    return rows


def get_gap_end():
    if os.path.exists(MAIN_CHECKPOINT):
        with open(MAIN_CHECKPOINT) as f:
            saved = f.read().strip()
            if saved:
                return datetime.strptime(saved, "%Y%m%d%H%M")
    raise SystemExit(f"⚠️ {MAIN_CHECKPOINT} 을 찾을 수 없습니다.")


def load_existing_hours():
    existing = set()
    if not os.path.exists(FINAL_CSV):
        return existing
    with open(FINAL_CSV, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if row and len(row) >= 2:
                try:
                    dt = datetime.strptime(row[1].strip(), "%Y%m%d%H%M")
                    existing.add(dt.replace(minute=0, second=0))
                except ValueError:
                    continue
    return existing


def load_done():
    if os.path.exists(RECOVER_CHECKPOINT):
        with open(RECOVER_CHECKPOINT, encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def mark_done(tm_str):
    with open(RECOVER_CHECKPOINT, "a", encoding="utf-8") as f:
        f.write(tm_str + "\n")


def append_row(row):
    with open(FINAL_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def main():
    gap_end = get_gap_end()
    print(f"검사 구간: {GAP_START} ~ {gap_end}  (전체 데이터 범위)")

    existing_hours = load_existing_hours()
    print(f"현재 CSV에 있는 고유 시각 수: {len(existing_hours)}개")

    missing = []
    t = GAP_START
    while t <= gap_end:
        if t not in existing_hours:
            missing.append(t)
        t += timedelta(hours=1)

    total_hours_in_range = int((gap_end - GAP_START).total_seconds() // 3600) + 1
    print(f"전체 구간 시간 수: {total_hours_in_range}개")
    print(f"그중 비어있는 시간대: {len(missing)}개 "
          f"({len(missing)/total_hours_in_range*100:.2f}%)\n")

    done = load_done()
    todo = [t.strftime("%Y%m%d%H%M") for t in missing if t.strftime("%Y%m%d%H%M") not in done]
    print(f"이미 재조회 처리됨(재개): {len(done)}개")
    print(f"이번에 재조회할 시각: {len(todo)}개\n")

    if not todo:
        print("재조회할 게 없습니다.")
        return

    recovered = 0
    still_missing = []
    start_time = time.time()

    try:
        for i, tm_str in enumerate(todo, 1):
            status, raw = call_api_with_retry(tm_str)

            found = False
            if status == 200:
                rows = parse_data_lines(raw)
                filtered = [r for r in rows if r and r[0] in TP_FILTER]
                if filtered:
                    for r in filtered:
                        row = r[: len(COLUMNS)] + [""] * (len(COLUMNS) - len(r))
                        append_row(row)
                    recovered += 1
                    found = True
            else:
                still_missing.append((tm_str, status))

            mark_done(tm_str)

            if i % 50 == 0 or i == len(todo):
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta_min = (len(todo) - i) / rate / 60 if rate > 0 else 0
                print(f"[진행] {i}/{len(todo)} ({i/len(todo)*100:.1f}%) | "
                      f"복구됨: {recovered}개 | 예상 남은시간: {eta_min:.1f}분")

            if i % 500 == 0:
                show_popup(f"복구 진행 중...\n{i}/{len(todo)} 처리\n복구됨: {recovered}개")

            time.sleep(REQUEST_DELAY_SEC)

    except KeyboardInterrupt:
        print("\n[중단됨] 지금까지 처리한 건 저장됐습니다. 다시 실행하면 이어서 진행됩니다.")
        return

    with open(STILL_MISSING_LOG, "w", encoding="utf-8") as f:
        for tm, status in still_missing:
            f.write(f"{tm}\t{status}\n")

    print(f"\n✅ 완료! 복구된 시각: {recovered}개 / 여전히 실패: {len(still_missing)}개")
    print(f"-> {STILL_MISSING_LOG} 확인")
    show_popup(f"전체 결측 복구 완료!\n복구: {recovered}개\n여전히 실패: {len(still_missing)}개",
               title="전체 결측 복구 - 완료")


if __name__ == "__main__":
    main()
