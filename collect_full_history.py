"""
독도(22441) 파고부이 - 전체 기간 시간별(1시간 간격) 데이터 수집 스크립트
(연속 실행 모드: 하루 쿼터를 다 쓰면 자동으로 다음날까지 대기했다가 이어서 진행)

- 시작: 2011-11-15 00:00 (실측으로 확인된 데이터 시작 시점)
- 끝: 없음 (컴퓨터를 계속 켜두면 실시간까지 계속 따라잡으며 무기한 실행)
- TP가 B 또는 C인 행만 CSV에 저장
- 중간에 멈춰도 체크포인트 파일 덕분에 이어서 실행 가능
- 매 요청 결과를 즉시 CSV에 append
- 하루 API 쿼터(2만 건)를 다 쓴 것으로 보이면(연속 실패 감지),
  스스로 종료하지 않고 다음날 자정 이후까지 대기했다가 자동으로 재개

사용법:
    python collect_full_history.py
    (컴퓨터를 계속 켜두면 별도 조작 없이 매일 이어서 수집됩니다)
    (Ctrl+C로 언제든 안전하게 중단 가능, 다시 실행하면 이어서 진행)
"""

import csv
import os
import time
import threading
import ctypes
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import api_quota


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
        "   .env.example을 복사해서 .env로 이름을 바꾸고, 그 안에 실제 발급받은 키를 넣어주세요.\n"
        "   예) KMA_AUTH_KEY=실제키값"
    )

# BASE_URL은 예시 파라미터(tm/stn/authKey)가 박힌 형태 그대로 두고, 실행 시 실제 값으로 치환해서 사용
BASE_URL = "https://apihub.kma.go.kr/api/typ01/url/sea_obs.php?tm=202301241200&stn=0&help=1&authKey=YOUR_AUTH_KEY_HERE"
STN = "22441"
TP_FILTER = {"B", "C"}

RETRY_DELAY_SEC = 10
MAX_RETRIES = 3

# 속도 관련 설정: 동시에 BATCH_SIZE개씩 요청을 날리고, 배치 사이에 BATCH_DELAY_SEC만큼 쉰다.
# (기존 방식: 1개씩 2.5초 간격 -> 대략 시간당 1440건)
# (지금 방식: 4개씩 동시에, 배치 사이 2초 -> 이론상 3~4배 빠름, 단 처음 실행 시 401/403 다시 뜨는지 꼭 확인할 것)
BATCH_SIZE = 4
BATCH_DELAY_SEC = 2.0

CONSECUTIVE_FAIL_LIMIT = 20   # 연속 이만큼 실패하면 쿼터초과로 보고 대기 모드 진입
DAILY_CALL_SAFETY_LIMIT = 19800  # 하루 2만 건 중 안전마진 두고 선제적으로 대기

START_TM = datetime(2011, 11, 15, 0, 0)

OUT_CSV = f"sea_obs_stn{STN}_full_hourly.csv"
CHECKPOINT_FILE = f"sea_obs_stn{STN}_full_hourly.checkpoint"

COLUMNS = [
    "TP", "TM", "STN_ID", "STN_KO", "LON", "LAT",
    "WH", "WD", "WS", "WS_GST", "TW", "TA", "PA", "HM"
]


def show_popup(message: str, title: str = "독도 데이터 수집 진행 알림"):
    def _show():
        try:
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x40000)
        except Exception:
            pass
    threading.Thread(target=_show, daemon=True).start()


def call_api(tm: str):
    # BASE_URL에 이미 예시 tm/stn/authKey가 박혀있으므로, 실제 원하는 값으로 문자열 치환해서 사용
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
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES:
                print(f"      -> 네트워크 오류({type(e).__name__}), {RETRY_DELAY_SEC}초 후 재시도")
                time.sleep(RETRY_DELAY_SEC)
                continue
            return "TIMEOUT", ""

        if status == 200:
            return status, raw

        if attempt < MAX_RETRIES:
            print(f"      -> status={status}, {RETRY_DELAY_SEC}초 후 재시도")
            time.sleep(RETRY_DELAY_SEC)

    return f"FAILED_{status}", raw


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


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            saved = f.read().strip()
            if saved:
                return datetime.strptime(saved, "%Y%m%d%H%M")
    return None


def save_checkpoint(tm_dt: datetime):
    with open(CHECKPOINT_FILE, "w") as f:
        f.write(tm_dt.strftime("%Y%m%d%H%M"))


def ensure_csv_header():
    is_new = not os.path.exists(OUT_CSV)
    if is_new:
        with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)


def append_rows(rows):
    if not rows:
        return
    with open(OUT_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        for r in rows:
            row = r[: len(COLUMNS)] + [""] * (len(COLUMNS) - len(r))
            writer.writerow(row)


def seconds_until_next_reset():
    """다음날 00:05 KST 기준까지 남은 초 (쿼터가 자정에 리셋된다고 가정, 여유 5분)"""
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return max((tomorrow - now).total_seconds(), 60)


def wait_for_quota_reset():
    wait_sec = seconds_until_next_reset()
    resume_time = datetime.now() + timedelta(seconds=wait_sec)
    print(f"\n⏸ 오늘 API 쿼터를 다 쓴 것으로 보입니다.")
    print(f"   {resume_time.strftime('%Y-%m-%d %H:%M')}쯤 자동으로 재개합니다. "
          f"(컴퓨터만 계속 켜두시면 됩니다)")
    show_popup(
        f"오늘 API 쿼터 소진 추정.\n"
        f"{resume_time.strftime('%Y-%m-%d %H:%M')}에 자동으로 재개됩니다.\n\n"
        f"컴퓨터를 끄지 않고 두시면 알아서 이어서 진행됩니다.",
        title="쿼터 대기 중 - 자동 재개 예정"
    )
    remaining = wait_sec
    while remaining > 0:
        chunk = min(remaining, 300)  # 5분 단위로 나눠서 대기 (반응성 위해)
        time.sleep(chunk)
        remaining -= chunk
    print(f"[재개] 대기 끝 ({datetime.now().strftime('%Y-%m-%d %H:%M')}), 수집을 다시 시작합니다.\n")


def main():
    resume_from = load_checkpoint()
    if resume_from:
        current = resume_from + timedelta(hours=1)
        print(f"[재개] 체크포인트 발견: {resume_from.strftime('%Y-%m-%d %H:%M')} 이후부터 이어서 진행합니다.")
    else:
        current = START_TM
        print(f"[신규 시작] {START_TM.strftime('%Y-%m-%d %H:%M')} 부터 시작합니다.")

    ensure_csv_header()

    print("연속 실행 모드입니다. 컴퓨터를 계속 켜두면 매일 자동으로 이어서 수집됩니다.")
    print("종료하려면 이 창에서 Ctrl+C를 누르세요.\n")

    processed = 0
    saved_count = 0
    consecutive_fail = 0
    caught_up_notified = False  # 실시간을 다 따라잡아서 대기 중이라는 알림을 이미 띄웠는지
    start_time = time.time()

    try:
        while True:
            # 안전마진 넘으면 선제적으로 대기 (실제 403 맞을 때까지 낭비하지 않기 위함)
            # -> 이 프로그램만의 카운트가 아니라, 공유 파일(api_quota)에 기록된 '오늘 전체 호출 수' 기준
            today_calls = api_quota.get_today_count()
            if today_calls >= DAILY_CALL_SAFETY_LIMIT:
                print(f"\n오늘 전체 호출 수({today_calls}, 다른 스크립트 포함)가 "
                      f"안전선에 도달해 선제적으로 대기합니다.")
                wait_for_quota_reset()
                consecutive_fail = 0
                continue

            end_tm = datetime.now().replace(minute=0, second=0, microsecond=0)
            if current > end_tm:
                # 실시간을 다 따라잡음 -> 지금 당장은 더 가져올 새 데이터가 없는 상태
                if not caught_up_notified:
                    print(f"\n✅ 실시간까지 다 따라잡았습니다. (현재 {current.strftime('%Y-%m-%d %H:%M')} 대기 중)")
                    print("   더 가져올 새 데이터가 없어서, 다음 정시가 될 때까지 대기합니다.")
                    show_popup(
                        f"실시간까지 다 따라잡았습니다!\n\n"
                        f"지금 당장은 더 가져올 새 데이터가 없습니다.\n"
                        f"다음 정시({(current).strftime('%H:%M')})가 되면 자동으로 이어서 수집합니다.",
                        title="가져올 데이터 없음 - 실시간 따라잡음"
                    )
                    caught_up_notified = True
                # 아직 다음 정시가 안 됨 -> 잠깐 쉬었다가 재확인
                time.sleep(60)
                continue

            # 다음 정시가 되어 새로 처리할 시각이 생겼으므로 알림 상태 초기화
            caught_up_notified = False

            # 이번 배치에 포함할 시각들 (BATCH_SIZE개, end_tm과 일일한도를 넘지 않는 선에서)
            batch_times = []
            t = current
            while (len(batch_times) < BATCH_SIZE and t <= end_tm
                   and today_calls + len(batch_times) < DAILY_CALL_SAFETY_LIMIT):
                batch_times.append(t)
                t += timedelta(hours=1)

            if not batch_times:
                time.sleep(60)
                continue

            # 배치 안의 시각들을 동시에 요청
            with ThreadPoolExecutor(max_workers=len(batch_times)) as executor:
                results = list(executor.map(
                    lambda dt: call_api_with_retry(dt.strftime("%Y%m%d%H%M")),
                    batch_times
                ))
            today_calls = api_quota.increment_call_count(len(batch_times))

            # 결과는 시간 순서 그대로 하나씩 처리 (체크포인트/연속실패 로직 일관성 유지)
            quota_hit = False
            for dt, (status, raw) in zip(batch_times, results):
                tm_str = dt.strftime("%Y%m%d%H%M")

                if status == 200:
                    rows = parse_data_lines(raw)
                    filtered = [r for r in rows if r and r[0] in TP_FILTER]
                    append_rows(filtered)
                    saved_count += len(filtered)
                    consecutive_fail = 0
                else:
                    # 여기서 실패 시각을 따로 로그 남기지 않음.
                    # -> find_and_fill_all_gaps.py가 전체 기간을 CSV와 대조해서
                    #    빈 시간대를 찾아내므로, 이 실패도 결국 거기서 다시 잡힌다.
                    consecutive_fail += 1

                if consecutive_fail >= CONSECUTIVE_FAIL_LIMIT:
                    # 이 시각 이전까지만 확정 저장, 이 시각부터 다시 시도하도록
                    save_checkpoint(dt - timedelta(hours=1))
                    print(f"\n⚠️ {consecutive_fail}번 연속 실패 감지 (status={status}). "
                          f"일일 쿼터 초과로 추정됩니다.")
                    print(f"   현재 걸려있는 시각: {tm_str} (재개 시 이 시각부터 재시도)")
                    current = dt  # 다음 재개 시 이 시각부터 다시
                    wait_for_quota_reset()
                    consecutive_fail = 0
                    quota_hit = True
                    break

                save_checkpoint(dt)
                processed += 1
                current = dt + timedelta(hours=1)

                if processed % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    print(f"[진행] {dt.strftime('%Y-%m-%d %H:%M')} | "
                          f"처리: {processed}개 | 수집된 행: {saved_count}개 | "
                          f"오늘 전체 호출(공유): {today_calls}개 | 속도: 시간당 약 {rate*3600:.0f}건")

                if current.year != dt.year:
                    show_popup(
                        f"{dt.year}년까지 수집 완료!\n\n"
                        f"누적 처리: {processed}개 시각\n"
                        f"수집된 행: {saved_count}개\n\n"
                        f"(이 창은 안 눌러도 다운로드는 계속됩니다)"
                    )

            if quota_hit:
                continue

            time.sleep(BATCH_DELAY_SEC)

    except KeyboardInterrupt:
        print("\n[중단됨] Ctrl+C로 멈췄습니다. 지금까지 진행분은 저장됐고, "
              "다시 실행하면 이어서 진행됩니다.")
        return


if __name__ == "__main__":
    main()
