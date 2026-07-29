"""
[2단계] step1에서 찾은 빠진 시간대(missing_hours.txt)를 하나씩 다시 조회해서
MERGED CSV에 채워넣는다.

- 중단·재개 가능: fill_gaps.checkpoint 파일에 이미 처리한 시각을 기록해두고,
  다시 실행하면 처리 안 한 것만 이어서 진행한다.
- 그래도 못 찾은 시각은 still_missing.txt에 남긴다 (진짜 결측으로 간주).
- 50개 처리할 때마다 진행 상황 출력.
- 1년 단위는 아니지만, 500개 처리할 때마다 팝업 알림도 띄운다.

사용법:
    python step2_fill_gaps.py
    (Ctrl+C로 중단해도 안전, 다시 실행하면 이어서 진행)
"""

import csv
import os
import time
import threading
import ctypes
import requests
from datetime import datetime

BASE_URL = "https://apihub.kma.go.kr/api/typ01/url/sea_obs.php?tm=202301241200&stn=0&help=1&authKey=VSSVYj7iRBSklWI-4vQU-A"
STN = "22441"
AUTH_KEY = "VSSVYj7iRBSkIWI-4vQU-A"
TP_FILTER = {"B", "C"}

REQUEST_DELAY_SEC = 2.5
RETRY_DELAY_SEC = 10
MAX_RETRIES = 3

OUT_DIR = r"C:\Users\user\Desktop\ocean_data"
MERGED_CSV = os.path.join(OUT_DIR, "sea_obs_stn22441_MERGED.csv")
MISSING_FILE = os.path.join(OUT_DIR, "sea_obs_stn22441_missing_hours.txt")
STILL_MISSING_FILE = os.path.join(OUT_DIR, "sea_obs_stn22441_still_missing.txt")
DONE_CHECKPOINT = os.path.join(OUT_DIR, "fill_gaps.checkpoint")

COLUMNS = [
    "TP", "TM", "STN_ID", "STN_KO", "LON", "LAT",
    "WH", "WD", "WS", "WS_GST", "TW", "TA", "PA", "HM"
]


def show_popup(message: str, title: str = "빠진 데이터 복구 진행 알림"):
    def _show():
        try:
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x40000)
        except Exception:
            pass
    threading.Thread(target=_show, daemon=True).start()


def call_api(tm: str):
    params = {"tm": tm, "stn": STN, "help": "0", "authKey": AUTH_KEY}
    resp = requests.get(BASE_URL, params=params, timeout=30)
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
        if status == 200 and "인증키가 아닙니다" not in raw:
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


def load_missing_list():
    if not os.path.exists(MISSING_FILE):
        print(f"⚠️ {MISSING_FILE} 이 없습니다. step1을 먼저 실행하세요.")
        return []
    with open(MISSING_FILE, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def load_done():
    if os.path.exists(DONE_CHECKPOINT):
        with open(DONE_CHECKPOINT, encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def mark_done(tm_str):
    with open(DONE_CHECKPOINT, "a", encoding="utf-8") as f:
        f.write(tm_str + "\n")


def append_row(row):
    with open(MERGED_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def main():
    missing_list = load_missing_list()
    done = load_done()
    todo = [tm for tm in missing_list if tm not in done]

    print(f"전체 빠진 시각: {len(missing_list)}개")
    print(f"이미 처리됨(재개): {len(done)}개")
    print(f"이번에 처리할 시각: {len(todo)}개\n")

    if not todo:
        print("처리할 게 없습니다. 이미 다 끝났거나 missing 목록이 비어있습니다.")
        return

    recovered = 0
    still_missing = []
    start_time = time.time()

    try:
        for i, tm_str in enumerate(todo, 1):
            status, raw = call_api_with_retry(tm_str)

            found = False
            if status != "TIMEOUT" and "인증키가 아닙니다" not in raw:
                rows = parse_data_lines(raw)
                filtered = [r for r in rows if r and r[0] in TP_FILTER]
                if filtered:
                    for r in filtered:
                        row = r[: len(COLUMNS)] + [""] * (len(COLUMNS) - len(r))
                        append_row(row)
                    recovered += 1
                    found = True

            if not found:
                still_missing.append(tm_str)

            mark_done(tm_str)

            if i % 50 == 0 or i == len(todo):
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta_min = (len(todo) - i) / rate / 60 if rate > 0 else 0
                print(f"[진행] {i}/{len(todo)} ({i/len(todo)*100:.1f}%) | "
                      f"복구됨: {recovered}개 | 예상 남은시간: {eta_min:.1f}분")

            if i % 500 == 0:
                show_popup(f"진행 중...\n{i}/{len(todo)} 처리\n복구됨: {recovered}개",
                           title="빠진 데이터 복구 진행 알림")

            time.sleep(REQUEST_DELAY_SEC)

    except KeyboardInterrupt:
        print("\n[중단됨] 지금까지 처리한 건 저장됐습니다. 다시 실행하면 이어서 진행됩니다.")
        return

    # still_missing 파일은 이번 실행분만 반영 (누적하려면 append 모드로 바꿔도 됨)
    with open(STILL_MISSING_FILE, "w", encoding="utf-8") as f:
        for tm in still_missing:
            f.write(tm + "\n")

    print(f"\n✅ 완료! 복구된 시각: {recovered}개 / 끝까지 못 찾은 시각: {len(still_missing)}개")
    print(f"-> {STILL_MISSING_FILE} 확인")
    show_popup(f"빠진 데이터 복구 완료!\n복구: {recovered}개\n여전히 없음: {len(still_missing)}개",
               title="빠진 데이터 복구 - 완료")


if __name__ == "__main__":
    main()
