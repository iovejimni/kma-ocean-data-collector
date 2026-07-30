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
        "   .env.example을 복사해서 .env로 이름을 바꾸고, 그 안에 실제 발급받은 키를 넣어주세요."
    )

# BASE_URL은 예시 파라미터(tm/stn/authKey)가 박힌 형태 그대로 두고, 실행 시 실제 값으로 치환해서 사용
BASE_URL = "https://apihub.kma.go.kr/api/typ01/url/sea_obs.php?tm=202301241200&stn=0&help=1&authKey=YOUR_AUTH_KEY_HERE"
STN = "22441"
TP_FILTER = {"B", "C"}

REQUEST_DELAY_SEC = 3
RETRY_DELAY_SEC = 10
MAX_RETRIES = 3

CONSECUTIVE_FAIL_LIMIT = 20      # 연속 이만큼 실패하면 쿼터초과로 보고 대기 모드 진입
DAILY_CALL_SAFETY_LIMIT = 19800  # 하루 2만 건 중 안전마진 두고 선제적으로 대기

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
        seen[tm] = r  # 같은 TM이 여러 번 있으면 마지막 값으로 덮어씀

    sorted_tms = sorted(seen.keys())

    with open(FINAL_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for tm in sorted_tms:
            writer.writerow(seen[tm])

    print(f"정렬/중복제거 완료: {before}행 -> {len(sorted_tms)}행 (시간순 정렬됨)")


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
        if len(missing) == 0:
            msg = "빈 시간대가 없습니다!\n전체 기간이 이미 다 채워져 있습니다."
        else:
            msg = f"재조회할 시각이 없습니다.\n(빈 시간대 {len(missing)}개 전부 이미 처리 완료)"
        print(msg.replace("\n", " "))
        show_popup(msg, title="가져올 데이터 없음")
        return

    recovered = 0
    confirmed_missing = 0
    still_missing = []
    consecutive_fail = 0
    start_time = time.time()

    try:
        i = 0
        while i < len(todo):
            # 안전마진 넘으면 선제적으로 대기 (다른 스크립트 포함 공유 카운터 기준)
            today_calls = api_quota.get_today_count()
            if today_calls >= DAILY_CALL_SAFETY_LIMIT:
                print(f"\n오늘 전체 호출 수({today_calls}, 다른 스크립트 포함)가 "
                      f"안전선에 도달해 선제적으로 대기합니다.")
                wait_for_quota_reset()
                consecutive_fail = 0
                continue  # 같은 i부터 다시

            tm_str = todo[i]
            status, raw = call_api_with_retry(tm_str)
            api_quota.increment_call_count(1)

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
                    confirmed_missing += 1
                consecutive_fail = 0
            else:
                consecutive_fail += 1

            if consecutive_fail >= CONSECUTIVE_FAIL_LIMIT:
                print(f"\n⚠️ {consecutive_fail}번 연속 실패 감지 (status={status}). "
                      f"일일 쿼터 초과로 추정됩니다.")
                print(f"   현재 걸려있는 시각: {tm_str} (재개 시 이 시각부터 재시도)")
                wait_for_quota_reset()
                consecutive_fail = 0
                continue  # mark_done 안 하고, i도 안 올리고 같은 항목 재시도

            if status != 200:
                still_missing.append((tm_str, status))

            mark_done(tm_str)
            i += 1

            if i % 50 == 0 or i == len(todo):
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta_min = (len(todo) - i) / rate / 60 if rate > 0 else 0
                print(f"[진행] {i}/{len(todo)} ({i/len(todo)*100:.1f}%) | "
                      f"복구됨: {recovered}개 | 결측확정: {confirmed_missing}개 | "
                      f"오류(재시도필요): {len(still_missing)}개 | 예상 남은시간: {eta_min:.1f}분")

            if i % 500 == 0:
                show_popup(f"복구 진행 중...\n{i}/{len(todo)} 처리\n복구됨: {recovered}개\n결측확정: {confirmed_missing}개")

            time.sleep(REQUEST_DELAY_SEC)

    except KeyboardInterrupt:
        print("\n[중단됨] 지금까지 처리한 건 저장됐습니다. 다시 실행하면 이어서 진행됩니다.")
        if recovered > 0:
            sort_and_dedupe_final_csv()
        return

    if recovered > 0:
        sort_and_dedupe_final_csv()

    with open(STILL_MISSING_LOG, "w", encoding="utf-8") as f:
        for tm, status in still_missing:
            f.write(f"{tm}\t{status}\n")

    print(f"\n✅ 완료! 복구된 시각: {recovered}개 / 결측확정: {confirmed_missing}개 / "
          f"여전히 실패: {len(still_missing)}개")
    print(f"-> {STILL_MISSING_LOG} 확인")

    if len(still_missing) == 0:
        show_popup(
            f"전체 결측 복구 완료!\n복구: {recovered}개\n결측확정: {confirmed_missing}개\n\n"
            f"🎉 더 이상 오류로 남은 시각이 없습니다!\n(가져올 데이터가 더 없습니다)",
            title="가져올 데이터 없음 - 전부 처리 완료"
        )
    else:
        show_popup(f"전체 결측 복구 완료!\n복구: {recovered}개\n결측확정: {confirmed_missing}개\n"
                   f"여전히 실패: {len(still_missing)}개",
                   title="전체 결측 복구 - 완료")


if __name__ == "__main__":
    main()
