"""
2011년 11월 1일 ~ 15일을 하루 단위(정오 기준)로 훑어서
정확히 언제부터 데이터가 시작되는지 확인하는 스크립트.
"""

import time
import requests
from datetime import datetime

BASE_URL = "https://apihub.kma.go.kr/api/typ01/url/sea_obs.php?tm=202301241200&stn=0&help=1&authKey=VSSVYj7iRBSklWI-4vQU-A"
STN = "22441"
AUTH_KEY = "VSSVYj7iRBSkIWI-4vQU-A"
TP_FILTER = {"B", "C"}

REQUEST_DELAY_SEC = 3
RETRY_DELAY_SEC = 10
MAX_RETRIES = 3

IDX_WH = 6

YEAR = 2011
MONTH = 11
DAYS = range(1, 16)  # 1일 ~ 15일


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
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES:
                print(f"      -> 네트워크 오류({type(e).__name__}), {RETRY_DELAY_SEC}초 후 재시도")
                time.sleep(RETRY_DELAY_SEC)
                continue
            return "TIMEOUT", ""

        if status == 200 and "인증키가 아닙니다" not in raw:
            return status, raw
        if attempt < MAX_RETRIES:
            print(f"      -> status={status}, {RETRY_DELAY_SEC}초 후 재시도")
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


def check_one_time(tm: str):
    status, raw = call_api_with_retry(tm)
    if status == "TIMEOUT":
        return "TIMEOUT", None, None
    if "인증키가 아닙니다" in raw:
        return "AUTH_FAIL", None, None
    rows = parse_data_lines(raw)
    if not rows:
        return "EMPTY", None, None
    tp_here = set(r[0] for r in rows if r)
    filtered = [r for r in rows if r and r[0] in TP_FILTER]
    if filtered:
        wh = filtered[0][IDX_WH] if len(filtered[0]) > IDX_WH else "?"
        return "OK", tp_here, wh
    return "NO_BC", tp_here, None


def main():
    print(f"[{YEAR}년 {MONTH}월 1~15일 일 단위 스캔 - 매일 12:00 기준]\n")
    print(f"{'일':<4} {'기준 tm':<16}  {'결과'}")
    print("-" * 60)

    for day in DAYS:
        tm = datetime(YEAR, MONTH, day, 12, 0).strftime("%Y%m%d%H%M")
        result, tp_here, wh = check_one_time(tm)

        if result == "OK":
            line = f"있음 (TP={tp_here}, WH={wh})"
        elif result == "NO_BC":
            line = f"응답은 있으나 B/C 없음 ({tp_here})"
        elif result == "AUTH_FAIL":
            line = "인증오류"
        elif result == "TIMEOUT":
            line = "타임아웃"
        else:
            line = "없음"

        print(f"{day:<4} {tm:<16}  {line}")
        time.sleep(REQUEST_DELAY_SEC)

    print("-" * 60)
    print("'없음' -> '있음'으로 바뀌는 날짜가 데이터 시작일에 가장 가깝습니다.")


if __name__ == "__main__":
    main()
