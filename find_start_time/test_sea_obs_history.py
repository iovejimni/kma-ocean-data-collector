"""
기상청 API 허브 - 해양기상종합관측(sea_obs.php) 과거 데이터 한계 테스트 스크립트 v2

개선점:
- WH 인덱스 버그 수정 (컬럼 순서: TP,TM,STN_ID,STN_KO,LON,LAT,WH,...)
- 각 날짜마다 단일 시각이 아니라 주변 여러 시각(±0,3,6시간)을 같이 찔러봐서
  "그 근방에 자료가 진짜 없는지" 확인 (결측 하나로 오판하는 걸 방지)
- 요청 사이 딜레이 + 401 자동 재시도 유지

사용법:
    python test_sea_obs_history.py
"""

import time
import requests
from datetime import datetime, timedelta

BASE_URL = "https://apihub.kma.go.kr/api/typ01/url/sea_obs.php?tm=202301241200&stn=0&help=1&authKey=VSSVYj7iRBSklWI-4vQU-A"
STN = "22441"                 # 독도
AUTH_KEY = "VSSVYj7iRBSkIWI-4vQU-A"
TP_FILTER = {"B", "C"}

REQUEST_DELAY_SEC = 3
RETRY_DELAY_SEC = 10
MAX_RETRIES = 3

# 컬럼 순서 (문서 기준)
# 0:TP 1:TM 2:STN_ID 3:STN_KO 4:LON 5:LAT 6:WH 7:WD 8:WS 9:WS_GST 10:TW 11:TA 12:PA 13:HM
IDX_WH = 6

# 각 날짜에서 같이 찔러볼 시간 오프셋(시간 단위)
HOUR_OFFSETS = [0, 3, -3, 6, -6]

TEST_DAYS_AGO = [
    0, 1, 7, 30, 90, 180,
    365, 365 * 2, 365 * 3, 365 * 5,
    365 * 10, 365 * 15, 365 * 20,
]


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
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            status, raw = call_api(tm)
        except requests.exceptions.RequestException as e:
            last_err = e
            if attempt < MAX_RETRIES:
                print(f"      -> 네트워크 오류({type(e).__name__}), {RETRY_DELAY_SEC}초 후 재시도 ({attempt+1}/{MAX_RETRIES})")
                time.sleep(RETRY_DELAY_SEC)
                continue
            else:
                # 재시도 다 소진 -> 이 시각은 실패로 처리하고 넘어감
                return "TIMEOUT", ""

        if status == 200 and "인증키가 아닙니다" not in raw:
            return status, raw
        if attempt < MAX_RETRIES:
            print(f"      -> status={status}, {RETRY_DELAY_SEC}초 후 재시도 ({attempt+1}/{MAX_RETRIES})")
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
    """해당 tm으로 조회해서 (성공여부, TP집합, WH값) 반환"""
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
    now = datetime.now()
    print(f"{'며칠 전':>8}  {'기준 tm':<16}  {'근방 조회 결과'}")
    print("-" * 90)

    for days_ago in TEST_DAYS_AGO:
        base_target = now - timedelta(days=days_ago)
        base_tm = base_target.strftime("%Y%m%d%H%M")

        found_any = False
        detail_parts = []

        for h in HOUR_OFFSETS:
            t = base_target + timedelta(hours=h)
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
                detail_parts.append(f"{h:+d}h:타임아웃(재확인필요)")
            else:
                detail_parts.append(f"{h:+d}h:없음")

            time.sleep(REQUEST_DELAY_SEC)

        summary = "★자료 있음★" if found_any else "자료 없음(근방 전체)"
        print(f"{days_ago:>7}일  {base_tm:<16}  [{summary}] " + ", ".join(detail_parts))

    print("\n" + "-" * 90)
    print("'자료 없음(근방 전체)'로 나온 시점부터가 실제 조회 한계에 가깝습니다.")
    print("(±0,3,6시간을 다 찔러도 없으면 단순 결측이 아니라 그 시기 자체에 자료가 없다는 뜻)")


if __name__ == "__main__":
    main()
