"""
kma_buoy2.php (해양기상부이 기간조회) 테스트 스크립트 v2

- BASE_URL에 쿼리스트링이 섞이는 문제 방지 (base URL은 순수 경로만)
- TP=B(해양기상부이)가 확실한 지점(22101 덕적도)으로 테스트
  -> 독도(22441, TP=C 파고부이)가 0줄 나온 게 지점 유형 문제인지 확인
"""

import requests
from datetime import datetime, timedelta
import time

BASE_URL = "https://apihub.kma.go.kr/api/typ01/url/kma_buoy2.php?tm1=202307231200&tm2=202307241200&stn=0&help=1&authKey=VSSVYj7iRBSklWI-4vQU-A"  # 순수 경로만, 쿼리스트링 없음
AUTH_KEY = "VSSVYj7iRBSkIWI-4vQU-A"

# 확실히 TP=B(해양기상부이)인 지점으로 테스트
STN = "22101"  # 덕적도

tm2 = datetime.now().replace(minute=0, second=0, microsecond=0)
tm1 = tm2 - timedelta(hours=6)

MAX_RETRIES = 2
TIMEOUT_SEC = 60


def call(stn, tm1, tm2):
    params = {
        "tm1": tm1.strftime("%Y%m%d%H%M"),
        "tm2": tm2.strftime("%Y%m%d%H%M"),
        "stn": stn,
        "help": "1",
        "authKey": AUTH_KEY,
    }
    for attempt in range(MAX_RETRIES + 1):
        try:
            print(f"[시도 {attempt+1}/{MAX_RETRIES+1}] stn={stn} 요청 중...")
            resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT_SEC)
            resp.encoding = "euc-kr"
            raw = resp.text
            if "�" in raw:
                resp.encoding = "utf-8"
                raw = resp.text
            return resp.status_code, resp.url, raw
        except requests.exceptions.RequestException as e:
            print(f"   -> 실패: {type(e).__name__}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(5)
    return None, None, None


def show_result(label, status, url, raw):
    print(f"\n===== [{label}] =====")
    print(f"[요청 URL] {url}")
    print(f"[HTTP 상태코드] {status}\n")
    print(raw[:2500] if raw else "(응답 없음)")
    if raw:
        data_lines = [l for l in raw.splitlines() if l.strip() and not l.strip().startswith("#")]
        print(f"\n데이터로 보이는 줄 수: {len(data_lines)}")
    print("=" * 60)


def main():
    # 1) 확실한 TP=B 지점(22101)으로 먼저 테스트
    status, url, raw = call("22101", tm1, tm2)
    show_result("22101 덕적도 (해양기상부이 확실)", status, url, raw)

    time.sleep(3)

    # 2) 비교용으로 독도(22441)도 같은 시간대로 재확인
    status2, url2, raw2 = call("22441", tm1, tm2)
    show_result("22441 독도 (파고부이)", status2, url2, raw2)


if __name__ == "__main__":
    main()
