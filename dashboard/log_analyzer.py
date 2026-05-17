"""
Auto Dev runner.log 분석기

일별/주별 통계를 계산합니다.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def analyze_runner_log(log_path: Path) -> dict:
    """runner.log를 파싱해서 통계를 반환합니다."""
    if not log_path.exists():
        return _empty_stats()

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()

    daily_completed: dict[str, int] = {}
    durations: list[float] = []
    failed_count = 0
    total_count = 0

    current_task_start: datetime | None = None

    for line in lines:
        ts = _extract_timestamp(line)
        if not ts:
            continue

        # 새 형식 [START] / [DONE]
        start_match = re.search(r"\[START\] task=(.+?)(?:\s+ts=|$)", line)
        if start_match:
            current_task_start = ts
            continue

        done_match = re.search(
            r"\[DONE\] task=(.+?)\s+duration_sec=([\d.]+)\s+status=(\w+)", line
        )
        if done_match:
            duration = float(done_match.group(2))
            status = done_match.group(3)
            date_str = ts.strftime("%Y-%m-%d")
            daily_completed[date_str] = daily_completed.get(date_str, 0) + 1
            durations.append(duration)
            total_count += 1
            if status == "failed":
                failed_count += 1
            current_task_start = None
            continue

        # 기존 형식: 📌 태스크:
        if "📌 태스크:" in line:
            current_task_start = ts
            continue

        # 기존 형식: 완료 처리
        if "완료 처리" in line:
            date_str = ts.strftime("%Y-%m-%d")
            daily_completed[date_str] = daily_completed.get(date_str, 0) + 1
            total_count += 1
            if current_task_start:
                duration = (ts - current_task_start).total_seconds()
                durations.append(duration)
                current_task_start = None
            if "실패 후 완료 처리" in line:
                failed_count += 1
            continue

    avg_duration = sum(durations) / len(durations) if durations else 0.0
    fail_rate = failed_count / total_count if total_count > 0 else 0.0

    return {
        "daily_completed": daily_completed,
        "avg_duration_sec": avg_duration,
        "fail_rate": fail_rate,
        "total_tasks": total_count,
        "failed_tasks": failed_count,
    }


def _extract_timestamp(line: str) -> datetime | None:
    """로그 줄에서 타임스탬프를 추출합니다. 형식: YYYY-MM-DD HH:MM:SS,mmm"""
    m = re.match(r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}),(\d{3})", line)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    return None


def _empty_stats() -> dict:
    return {
        "daily_completed": {},
        "avg_duration_sec": 0.0,
        "fail_rate": 0.0,
        "total_tasks": 0,
        "failed_tasks": 0,
    }


def get_weekly_summary(stats: dict) -> str:
    """요약 문자열을 반환합니다. 예: '완료: 12개 / 평균 8분 / 실패 1개'"""
    total = stats.get("total_tasks", 0)
    avg_sec = stats.get("avg_duration_sec", 0)
    failed = stats.get("failed_tasks", 0)
    avg_min = int(avg_sec / 60)
    return f"완료: {total}개 / 평균 {avg_min}분 / 실패 {failed}개"
