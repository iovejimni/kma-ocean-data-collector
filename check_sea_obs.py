"""
기상청 API 허브 - 해양기상종합관측(해양기상부이·파고부이·표류부이 등) 데이터 확인 스크립트
(홈페이지 제공 샘플 코드 스타일 - requests 사용)

1. 지점번호(stn) 하나를 넣어서 데이터를 요청
2. 응답에서 관측종류(TP)가 무엇으로 나오는지 먼저 확인
3. 문제없으면 CSV로 저장

사용법:
    python check_sea_obs.py

필요하면 아래 STN, AUTH_KEY, OMIT_TM 값만 바꿔서 쓰면 됩니다.
"""

import csv
import requests
from datetime import datetime

# ----------------------------
# 요청 파라미터 (필요시 수정)
# ----------------------------
BASE_URL = "https://apihub.kma.go.kr/api/typ01/url/sea_obs.php?tm=202301241200&stn=0&help=1&authKey=VSSVYj7iRBSklWI-4vQU-A"
STN = "22441"                 # 지점번호 (0이면 전체 지점) - 독도
HELP = "0"                    # 0: 도움말 없이 순수 데이터만
AUTH_KEY = "VSSVYj7iRBSkIWI-4vQU-A"  # 발급받은 API 인증키

# True면 tm 파라미터를 아예 안 보냄 (문서상 "안 주면 현재시간 기준")
# 이걸로 오류가 나면 False로 바꿔서 코드가 현재시각을 직접 만들어 넣도록 하세요.
OMIT_TM = False

# CSV에 남길 관측종류(TP) 필터
# B = 해양기상부이, C = 파고부이, D = 표류부이, L = 등표, N = 조위관측소, F = 연안방재, G = 파랑계, J = 기상1호
# 여기 담긴 값만 CSV에 저장됩니다. 전체 다 보고 싶으면 None으로 바꾸세요.
TP_FILTER = {"B", "C"}

# 컬럼명 (제공된 문서 기준)
COLUMNS = [
    "TP", "STN_ID", "STN_KO", "LON", "LAT",
    "WH", "WD", "WS", "WS_GST", "TW", "TA", "PA", "HM"
]


def fetch_sea_obs(stn: str, auth_key: str, help_flag: str = "0", omit_tm: bool = True) -> str:
    """API 호출 후 원문 텍스트(raw text) 반환 (requests 사용, 홈페이지 샘플과 동일한 방식)"""
    headers = {
        'Content-Type': 'application/json'
    }

    params = {
        "stn": stn,
        "help": help_flag,
        "authKey": auth_key,
    }

    if not omit_tm:
        # tm 파라미터를 직접 넣고 싶을 때: 현재시각(KST) 기준으로 YYYYMMDDHHMM 생성
        params["tm"] = datetime.now().strftime("%Y%m%d%H%M")

    resp = requests.get(BASE_URL, headers=headers, params=params, timeout=15)
    print(f"[요청 URL] {resp.url}\n")
    print(f"[HTTP 상태코드] {resp.status_code}\n")

    resp.encoding = "euc-kr"  # 기상청 API는 보통 euc-kr 인코딩
    raw = resp.text
    if "�" in raw:
        resp.encoding = "utf-8"
        raw = resp.text

    return raw


def parse_lines(raw: str):
    """#으로 시작하지 않는 실제 데이터 줄만 파싱"""
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 줄 끝의 '=' 제거
        line = line.rstrip(",=").rstrip("=")
        parts = [p.strip() for p in line.split(",")]
        rows.append(parts)
    return rows


def main():
    raw = fetch_sea_obs(STN, AUTH_KEY, HELP, OMIT_TM)

    print("========== [원문 응답 미리보기] ==========")
    print(raw[:1000])
    print("==========================================\n")

    rows = parse_lines(raw)

    if not rows:
        print("⚠️ 파싱된 데이터가 없습니다. authKey, stn 값이나 API 상태를 확인해주세요.")
        return

    print(f"총 {len(rows)}개 행 수신\n")

    # TP(관측종류) 먼저 확인
    tp_values = set(r[0] for r in rows if len(r) > 0)
    print(f"[확인] 이번 응답에 포함된 관측종류(TP) 종류: {tp_values}")
    print("  B = 해양기상부이, C = 파고부이, D = 표류부이, L = 등표, N = 조위관측소, F = 연안방재, G = 파랑계, J = 기상1호\n")

    # TP_FILTER가 설정돼 있으면 B, C 등 원하는 관측종류만 남김
    if TP_FILTER:
        before = len(rows)
        rows = [r for r in rows if len(r) > 0 and r[0] in TP_FILTER]
        print(f"[필터 적용] TP in {TP_FILTER} 기준으로 {before}개 → {len(rows)}개 행 남음\n")

    if not rows:
        print("⚠️ 필터 조건에 맞는 행이 없습니다. TP_FILTER나 STN 값을 확인해주세요.")
        return

    # CSV로 저장
    tag = "current" if OMIT_TM else datetime.now().strftime("%Y%m%d%H%M")
    out_path = f"sea_obs_stn{STN}_{tag}.csv"
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for r in rows:
            # 컬럼 개수 안 맞으면 뒤에 빈 값 채우거나 잘라서 맞춤
            row = r[: len(COLUMNS)] + [""] * (len(COLUMNS) - len(r))
            writer.writerow(row)

    print(f"✅ CSV 저장 완료: {out_path}")


if __name__ == "__main__":
    main()
