"""
api_quota.py

여러 스크립트(collect_full_history.py, 결측복구 스크립트 등)가 공통으로 참조하는
'오늘 API를 몇 번 불렀는지' 카운터.

- 날짜별로 파일(kma_api_daily_calls.txt)에 기록
- 어떤 스크립트든 API를 부를 때마다 increment_call_count()를 호출하면,
  그날 총 호출 수가 프로세스/스크립트 상관없이 공유됨
- 날짜가 바뀌면 자동으로 0부터 다시 시작

사용법 (다른 스크립트에서):
    import api_quota

    today_count = api_quota.get_today_count()
    if today_count >= DAILY_CALL_SAFETY_LIMIT:
        ...대기...

    # API 부를 때마다:
    api_quota.increment_call_count()   # 1번 호출했다고 기록
"""

import os
import threading
from datetime import datetime

QUOTA_FILE = "kma_api_daily_calls.txt"
_lock = threading.Lock()


def _read_raw(path):
    if not os.path.exists(path):
        return None, None
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if not content or "\t" not in content:
        return None, None
    saved_date, saved_count = content.split("\t", 1)
    try:
        return saved_date, int(saved_count)
    except ValueError:
        return None, None


def _write_raw(path, date_str, count):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{date_str}\t{count}")


def get_today_count(path: str = None) -> int:
    """오늘(현재 컴퓨터 날짜 기준) 총 호출 수를 반환. 파일에 오늘 날짜가 아니면 0."""
    path = path or QUOTA_FILE
    today = datetime.now().strftime("%Y-%m-%d")
    with _lock:
        saved_date, saved_count = _read_raw(path)
        if saved_date != today:
            return 0
        return saved_count


def increment_call_count(n: int = 1, path: str = None) -> int:
    """API를 n번 불렀다고 기록하고, 갱신된 오늘 누적 호출 수를 반환한다.
    날짜가 바뀌어 있으면 자동으로 0부터 다시 센다."""
    path = path or QUOTA_FILE
    today = datetime.now().strftime("%Y-%m-%d")
    with _lock:
        saved_date, saved_count = _read_raw(path)
        if saved_date != today:
            saved_count = 0
        new_count = saved_count + n
        _write_raw(path, today, new_count)
        return new_count
