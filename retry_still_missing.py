"""
[재시도] sea_obs_stn22441_all_still_missing.txt 에 남아있는,
"재조회 시도했지만 오류(403/타임아웃 등)로 확인 못 한" 시각들만 다시 조회한다.

- 성공(200)해서 실제 데이터(B/C)가 있으면 -> 최종 CSV에 추가, 목록에서 제거
- 성공(200)했는데 데이터가 없으면 -> 진짜 결측으로 확정, 목록에서 제거
- 이번에도 오류면 -> 갱신된 still_missing 파일에 계속 남김
- 중단·재개 가능

사용법:
    python retry_still_missing.py
"""

import csv
import os
import time
import threading
import ctypes
import requests
from datetime import datetime


def load_env_file(path=".env"):
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
    raise SystemExit("⚠️ KMA_AUTH_KEY가 설정되어 있지 않습니다. .env 파일을 확인해주세요.")

BASE_URL = "https://apihub.kma.go.kr/api/typ01/url/sea_obs.php?tm=202301241200&stn=0&help=1&authKey=YOUR_AUTH_KEY_HERE"
STN = "22441"
TP_FILTER = {"B", "C"}

REQUEST_DELAY_SEC = 3
RETRY_DELAY_SEC = 10
MAX_RETRIES = 3

FINAL_CSV = "sea_obs_stn22441_full_hourly.csv"
STILL_MISSING_LOG = "sea_obs_stn22441_all_still_missing.txt"
DONE_CHECKPOINT = "retry_still_missing.checkpoint"

COLUMNS = [
    "TP", "TM", "STN_ID", "STN_KO", "LON", "LAT",
    "WH", "WD", "WS", "WS_GST", "TW", "TA", "PA", "HM"
]


def show_popup(message: str, title: str = "still_missing 재조회 알림"):
    def _show():
        try:
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x40000)
        except Exception:
            pass
    threading.Thread(target=_show, daemon=True).start()


def call_api(tm: str):
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


def load_still_missing():
    if not os.path.exists(STILL_MISSING_LOG):
        print(f"⚠️ {STILL_MISSING_LOG} 이 없습니다.")
        return []
    items = []
    with open(STILL_MISSING_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            tm = parts[0].strip()
            if tm:
                items.append(tm)
    return items


def load_done():
    if os.path.exists(DONE_CHECKPOINT):
        with open(DONE_CHECKPOINT, encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def mark_done(tm_str):
    with open(DONE_CHECKPOINT, "a", encoding="utf-8") as f:
        f.write(tm_str + "\n")


def append_row(row):
    with open(FINAL_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def sort_and_dedupe_final_csv():
    """복구 과정에서 파일 맨 끝에 순서 없이 쌓인 행들을,
    TM(관측시각) 기준으로 다시 정렬하고 중복을 제거해서 깔끔하게 재작성한다."""
    print("\n최종 정렬/중복제거 진행 중...")

    with open(FINAL_CSV, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        rows = [r for r in reader if r and len(r) >= 2]

    before = len(rows)

    seen = {}
    for r in rows:
        tm = r[1].strip()
        seen[tm] = r

    sorted_tms = sorted(seen.keys())

    with open(FINAL_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for tm in sorted_tms:
            writer.writerow(seen[tm])

    print(f"정렬/중복제거 완료: {before}행 -> {len(sorted_tms)}행 (시간순 정렬됨)")


def main():
    targets = load_still_missing()
    done = load_done()
    todo = [tm for tm in targets if tm not in done]

    print(f"still_missing에 기록된 시각: {len(targets)}개")
    print(f"이미 재시도 처리됨(재개): {len(done)}개")
    print(f"이번에 재시도할 시각: {len(todo)}개\n")

    if not todo:
        if len(targets) == 0:
            msg = "still_missing 목록 자체가 비어있습니다.\n(현재 알려진 결측/오류가 없습니다)"
        else:
            msg = f"재시도할 시각이 없습니다.\n(총 {len(targets)}개 전부 이미 처리 완료)"
        print(msg.replace("\n", " "))
        show_popup(msg, title="가져올 데이터 없음")
        return

    recovered = 0
    confirmed_missing = 0
    still_failed = []
    start_time = time.time()

    try:
        for i, tm_str in enumerate(todo, 1):
            status, raw = call_api_with_retry(tm_str)

            if status == 200:
                rows = parse_data_lines(raw)
                filtered = [r for r in rows if r and r[0] in TP_FILTER]
                if filtered:
                    for r in filtered:
                        row = r[: len(COLUMNS)] + [""] * (len(COLUMNS) - len(r))
                        append_row(row)
                    recovered += 1
                else:
                    confirmed_missing += 1
            else:
                still_failed.append((tm_str, status))

            mark_done(tm_str)

            if i % 50 == 0 or i == len(todo):
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta_min = (len(todo) - i) / rate / 60 if rate > 0 else 0
                print(f"[진행] {i}/{len(todo)} ({i/len(todo)*100:.1f}%) | "
                      f"복구됨: {recovered}개 | 진짜결측확정: {confirmed_missing}개 | "
                      f"예상 남은시간: {eta_min:.1f}분")

            time.sleep(REQUEST_DELAY_SEC)

    except KeyboardInterrupt:
        print("\n[중단됨] 지금까지 처리한 건 저장됐습니다. 다시 실행하면 이어서 진행됩니다.")
        if recovered > 0:
            sort_and_dedupe_final_csv()
        return

    if recovered > 0:
        sort_and_dedupe_final_csv()

    # still_missing 파일을 이번에도 실패한 것들로만 새로 씀
    with open(STILL_MISSING_LOG, "w", encoding="utf-8") as f:
        for tm, status in still_failed:
            f.write(f"{tm}\t{status}\n")

    print(f"\n✅ 완료!")
    print(f"   복구됨(CSV에 추가): {recovered}개")
    print(f"   진짜 결측으로 확정(더 이상 재시도 대상 아님): {confirmed_missing}개")
    print(f"   여전히 오류로 확인 못함: {len(still_failed)}개 -> {STILL_MISSING_LOG}에 갱신됨")

    if len(still_failed) == 0:
        show_popup(
            f"still_missing 재조회 완료!\n복구: {recovered}개\n결측확정: {confirmed_missing}개\n\n"
            f"🎉 더 이상 오류로 남은 시각이 없습니다!\n(가져올 데이터가 더 없습니다)",
            title="가져올 데이터 없음 - 전부 처리 완료"
        )
    else:
        show_popup(
            f"still_missing 재조회 완료!\n복구: {recovered}개\n결측확정: {confirmed_missing}개\n"
            f"여전히 실패: {len(still_failed)}개"
        )


if __name__ == "__main__":
    main()
