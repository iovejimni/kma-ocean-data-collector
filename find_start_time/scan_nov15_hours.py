"""
2011년 11월 15일 00시~12시를 1시간 단위로 훑어서
정확히 몇 시부터 데이터가 시작되는지 확인하는 스크립트.

주의: 이 API는 요청 시각 기준 '과거 59분 이내' 생산된 자료만 찾아서 보여준다.
      그래서 1시간 간격으로 촘촘히 찔러보면 시작 시각을 좁힐 수 있다.
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

YEAR, MONTH, DAY = 2011, 11, 14
HOURS = range(0, 13)  # 0시 ~ 12시


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
        return "TIMEOUT", None, None, None
    if "인증키가 아닙니다" in raw:
        return "AUTH_FAIL", None, None, None
    rows = parse_data_lines(raw)
    if not rows:
        return "EMPTY", None, None, None
    tp_here = set(r[0] for r in rows if r)
    filtered = [r for r in rows if r and r[0] in TP_FILTER]
    if filtered:
        wh = filtered[0][IDX_WH] if len(filtered[0]) > IDX_WH else "?"
        actual_tm = filtered[0][1] if len(filtered[0]) > 1 else "?"
        return "OK", tp_here, wh, actual_tm
    return "NO_BC", tp_here, None, None


def main():
    print(f"[{YEAR}-{MONTH:02d}-{DAY:02d} 0시~12시 1시간 단위 스캔]\n")
    print(f"{'요청시각':<6} {'기준 tm':<16}  {'결과'}")
    print("-" * 70)

    for hour in HOURS:
        tm = datetime(YEAR, MONTH, DAY, hour, 0).strftime("%Y%m%d%H%M")
        result, tp_here, wh, actual_tm = check_one_time(tm)

        if result == "OK":
            line = f"있음 (실제 관측시각={actual_tm}, WH={wh})"
        elif result == "NO_BC":
            line = f"응답은 있으나 B/C 없음 ({tp_here})"
        elif result == "AUTH_FAIL":
            line = "인증오류"
        elif result == "TIMEOUT":
            line = "타임아웃"
        else:
            line = "없음"

        print(f"{hour:02d}:00  {tm:<16}  {line}")
        time.sleep(REQUEST_DELAY_SEC)

    print("-" * 70)
    print("'없음' -> '있음'으로 바뀌는 시각이 데이터 시작 시각에 가장 가깝습니다.")
    print("(실제 관측시각 컬럼(TM)을 보면 정확한 최초 생산시각도 확인 가능)")


if __name__ == "__main__":
    main()
