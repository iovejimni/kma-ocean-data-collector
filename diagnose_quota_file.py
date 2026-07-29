"""
[진단용] api_quota가 실제로 어떤 파일을, 어떤 내용으로 읽고 있는지 그대로 보여준다.
"""

import os
from datetime import datetime
import api_quota

path = api_quota.QUOTA_FILE
abs_path = os.path.abspath(path)

print(f"api_quota가 찾는 파일 경로: {abs_path}")
print(f"이 파일이 실제로 존재하는가?: {os.path.exists(abs_path)}\n")

if os.path.exists(abs_path):
    with open(abs_path, "rb") as f:
        raw_bytes = f.read()
    print(f"파일 크기: {len(raw_bytes)} bytes")
    print(f"raw bytes (앞부분): {raw_bytes[:50]!r}\n")

    try:
        text = raw_bytes.decode("utf-8")
        print(f"utf-8로 디코딩한 내용: {text!r}")
    except Exception as e:
        print(f"utf-8 디코딩 실패: {e}")

print(f"\n오늘 날짜(파이썬 기준): {datetime.now().strftime('%Y-%m-%d')}")
print(f"api_quota.get_today_count() 결과: {api_quota.get_today_count()}")

# 혹시 다른 폴더에 같은 이름의 파일이 더 있는지도 확인해보고 싶으면
# 아래 경로를 실제 ocean_data 폴더로 바꿔서 확인 가능
print(f"\n현재 파이썬이 실행 중인 폴더(작업 디렉토리): {os.getcwd()}")
