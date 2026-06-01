"""
Auto Dev 루프 예약 스케줄러

schedule.json에 저장된 시간/요일에 맞춰 자동으로 LoopRunner를 시작합니다.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

SCHEDULE_FILE = Path(__file__).parent / "schedule.json"
_DAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


class TaskScheduler:
    def __init__(self, trigger_callback=None, schedule_file=None):
        self.schedules: list[dict] = []
        self.trigger_callback = trigger_callback
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._schedule_file = schedule_file or SCHEDULE_FILE

    def load_schedules(self) -> list[dict]:
        if not self._schedule_file.exists():
            return []
        try:
            data = json.loads(self._schedule_file.read_text(encoding="utf-8"))
            self.schedules = data.get("schedules", [])
        except Exception:
            self.schedules = []
        return self.schedules

    def save_schedules(self) -> None:
        try:
            self._schedule_file.write_text(
                json.dumps({"schedules": self.schedules}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"schedule.json 저장 실패: {e}")

    def add_schedule(self, time_str: str, days: list[str], project_dir: str, enabled: bool = True) -> None:
        self.schedules.append({
            "time": time_str,
            "days": days,
            "project_dir": project_dir,
            "enabled": enabled,
            "last_run": "",
        })
        self.save_schedules()

    def remove_schedule(self, index: int) -> None:
        if 0 <= index < len(self.schedules):
            self.schedules.pop(index)
            self.save_schedules()

    def start_monitoring(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop_monitoring(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            self._check_schedules()
            for _ in range(60):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    def _check_schedules(self) -> None:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = _DAY_NAMES[now.weekday()]
        today_str = now.strftime("%Y%m%d")

        for schedule in self.schedules:
            if not schedule.get("enabled", True):
                continue
            if schedule.get("time") != current_time:
                continue
            if current_day not in schedule.get("days", []):
                continue
            if schedule.get("last_run") == today_str:
                continue

            project_dir = schedule.get("project_dir", "")
            if not project_dir or not Path(project_dir).is_dir():
                continue

            if self.trigger_callback:
                try:
                    self.trigger_callback(project_dir, schedule)
                except Exception as e:
                    print(f"스케줄 콜백 실패: {e}")

            schedule["last_run"] = today_str
            self.save_schedules()
