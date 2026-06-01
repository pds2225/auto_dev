import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

from log_analyzer import analyze_runner_log, get_weekly_summary


def test_analyze_empty_log():
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "runner.log"
        log_path.write_text("", encoding="utf-8")
        stats = analyze_runner_log(log_path)
        assert stats["total_tasks"] == 0
        assert stats["avg_duration_sec"] == 0.0


def test_analyze_legacy_format():
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "runner.log"
        lines = [
            "2026-05-17 10:00:00,000 [INFO] ▶ 루프 시작",
            "2026-05-17 10:00:01,000 [INFO] 📌 태스크: TASK-01 테스트",
            "2026-05-17 10:00:02,000 [INFO] ✅ 테스트 통과!",
            "2026-05-17 10:00:02,000 [INFO]   → [TASK-01 테스트] 완료 처리",
            "2026-05-17 10:01:00,000 [INFO] 📌 태스크: TASK-02 실패 태스크",
            "2026-05-17 10:02:00,000 [INFO] ⚠ 재테스트 실패",
            "2026-05-17 10:02:00,000 [INFO]   → [TASK-02 실패 태스크] 실패 후 완료 처리",
        ]
        log_path.write_text("\n".join(lines), encoding="utf-8")
        stats = analyze_runner_log(log_path)
        assert stats["total_tasks"] == 2
        assert stats["daily_completed"]["2026-05-17"] == 2
        assert stats["failed_tasks"] == 1
        assert stats["avg_duration_sec"] == 30.5  # (1 + 60) / 2


def test_analyze_new_format():
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "runner.log"
        lines = [
            "2026-05-17 10:00:00,000 [INFO] [START] task=TASK-01 ts=2026-05-17T10:00:00",
            "2026-05-17 10:00:30,000 [INFO] [DONE] task=TASK-01 duration_sec=30.0 status=passed",
            "2026-05-17 10:01:00,000 [INFO] [START] task=TASK-02 ts=2026-05-17T10:01:00",
            "2026-05-17 10:02:00,000 [INFO] [DONE] task=TASK-02 duration_sec=60.0 status=failed",
        ]
        log_path.write_text("\n".join(lines), encoding="utf-8")
        stats = analyze_runner_log(log_path)
        assert stats["total_tasks"] == 2
        assert stats["failed_tasks"] == 1
        assert stats["avg_duration_sec"] == 45.0


def test_weekly_summary():
    stats = {"total_tasks": 12, "avg_duration_sec": 480, "failed_tasks": 1}
    summary = get_weekly_summary(stats)
    assert "12개" in summary
    assert "8분" in summary
    assert "1개" in summary
