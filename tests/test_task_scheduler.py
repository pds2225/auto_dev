import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

from task_scheduler import TaskScheduler


def test_scheduler_load_save():
    with tempfile.TemporaryDirectory() as tmp:
        test_file = Path(tmp) / "schedule.json"
        sched = TaskScheduler(schedule_file=test_file)
        sched.schedules = [{"time": "22:00", "days": ["월"], "project_dir": tmp, "enabled": True, "last_run": ""}]
        sched.save_schedules()

        sched2 = TaskScheduler(schedule_file=test_file)
        sched2.load_schedules()
        assert len(sched2.schedules) == 1
        assert sched2.schedules[0]["time"] == "22:00"


def test_scheduler_triggers_callback_when_matching():
    calls = []

    def fake_cb(project_dir, schedule):
        calls.append((project_dir, schedule["time"]))

    sched = TaskScheduler(trigger_callback=fake_cb)
    sched.schedules = [{
        "time": datetime.now().strftime("%H:%M"),
        "days": ["월", "화", "수", "목", "금", "토", "일"],
        "project_dir": ".",
        "enabled": True,
        "last_run": "",
    }]
    sched._check_schedules()
    assert len(calls) == 1
    assert calls[0][1] == datetime.now().strftime("%H:%M")


def test_scheduler_no_duplicate_same_day():
    calls = []

    def fake_cb(project_dir, schedule):
        calls.append(project_dir)

    sched = TaskScheduler(trigger_callback=fake_cb)
    today_str = datetime.now().strftime("%Y%m%d")
    sched.schedules = [{
        "time": datetime.now().strftime("%H:%M"),
        "days": ["월", "화", "수", "목", "금", "토", "일"],
        "project_dir": ".",
        "enabled": True,
        "last_run": today_str,
    }]
    sched._check_schedules()
    assert calls == []
