"""
독도(22441) 파고부이 설치(자료 시작) 시점을 좁혀서 찾는 스크립트

- 10년 전(2016, 자료 있음)과 15년 전(2011, 자료 없음) 사이를
  연 단위로 훑어서, 어느 해부터 자료가 나오기 시작하는지 확인한다.
- 경계가 되는 해를 찾으면, 그 해를 다시 월 단위로 더 좁혀볼 수 있다.
"""

import time
import requests
from datetime import datetime, timedelta

BASE_URL = "https://apihub.kma.go.kr/api/typ01/url/sea_obs.php?tm=202301241200&stn=0&help=1&authKey=VSSVYj7iRBSklWI-4vQU-A"
STN = "22441"
AUTH_KEY = "VSSVYj7iRBSkIWI-4vQU-A"
TP_FILTER = {"B", "C"}

REQUEST_DELAY_SEC = 3
RETRY_DELAY_SEC = 10
MAX_RETRIES = 3

IDX_WH = 6
HOUR_OFFSETS = [0, 6, -6, 12, -12]  # 하루 안에서 넓게 훑기

# 테스트할 연도 (7월 20일 기준, 2011~2017년 사이를 훑어봄)
TEST_YEARS = [2011, 2012, 2013, 2014, 2015, 2016, 2017]


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
    print(f"{'연도':<6}  {'기준 tm':<16}  {'결과'}")
    print("-" * 90)

    for year in TEST_YEARS:
        base = datetime(year, 7, 20, 16, 45)
        base_tm = base.strftime("%Y%m%d%H%M")

        found_any = False
        detail_parts = []

        for h in HOUR_OFFSETS:
            t = base + timedelta(hours=h)
            tm = t.strftime("%Y%m%d%H%M")
            result, tp_here, wh = check_one_time(tm)

            if result == "OK":
                found_any = True
                detail_parts.append(f"{h:+d}h:있음(WH={wh})")
            elif result == "NO_BC":
                detail_parts.append(f"{h:+d}h:B/C없음({tp_here})")
            elif result == "AUTH_FAIL":
                detail_parts.append(f"{h:+d}h:인증오류")
            elif result == "TIMEOUT":
                detail_parts.append(f"{h:+d}h:타임아웃")
            else:
                detail_parts.append(f"{h:+d}h:없음")

            time.sleep(REQUEST_DELAY_SEC)

        summary = "★있음★" if found_any else "없음"
        print(f"{year:<6}  {base_tm:<16}  [{summary}] " + ", ".join(detail_parts))

    print("\n" + "-" * 90)
    print("이 표에서 '없음' -> '있음'으로 바뀌는 연도가 대략적인 자료 시작 시점입니다.")
    print("그 해를 찾으면 월 단위로 더 좁혀서 정확한 시작월을 확인할 수 있어요.")


if __name__ == "__main__":
    main()
