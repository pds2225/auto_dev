import os
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

from loop_runner import DEFAULT_CLAUDE_TIMEOUT_SEC, LoopRunner, get_claude_timeout_sec


# ── 타임아웃 환경변수 ─────────────────────────────────────────────────────────

def test_timeout_default(monkeypatch):
    monkeypatch.delenv("CLAUDE_TIMEOUT", raising=False)
    assert get_claude_timeout_sec() == DEFAULT_CLAUDE_TIMEOUT_SEC


def test_timeout_env_override(monkeypatch):
    monkeypatch.setenv("CLAUDE_TIMEOUT", "240")
    assert get_claude_timeout_sec() == 240


def test_timeout_env_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("CLAUDE_TIMEOUT", "invalid")
    assert get_claude_timeout_sec() == DEFAULT_CLAUDE_TIMEOUT_SEC


# ── 태스크 선택 ───────────────────────────────────────────────────────────────

def test_select_newest_generated_task():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "TASKS.md").write_text(textwrap.dedent("""\
            # Tasks

            ## Active

            ### Auto Dev Queue
            - [ ] [TASK-01] First task
            - [ ] [TASK-02] Second task
        """), encoding="utf-8")
        r = LoopRunner()
        r.project_dir = tmp
        sel = r._get_next_task_selection()
        assert sel is not None
        assert sel["selected_task_id"] == "TASK-02"
        assert sel["selected_task_type"] == "generated"
        assert sel["selection_reason"] == "newest_generated_pending"


def test_select_newest_generated_among_mixed():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "TASKS.md").write_text(textwrap.dedent("""\
            # Tasks

            ## Active

            ### Day 2
            - [ ] regular pending task
            - [ ] [TASK-30] earlier generated task
            - [ ] [TASK-31] newest generated task
        """), encoding="utf-8")
        r = LoopRunner()
        r.project_dir = tmp
        sel = r._get_next_task_selection()
        assert sel["selected_task_id"] == "TASK-31"


def test_select_fallback_when_no_generated():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "TASKS.md").write_text(textwrap.dedent("""\
            # Tasks

            ## Active

            ### Day 1
            - [ ] regular pending task

            ## Waiting On
            - [ ] ignored generated task
        """), encoding="utf-8")
        r = LoopRunner()
        r.project_dir = tmp
        sel = r._get_next_task_selection()
        assert sel["selected_task_id"] == ""
        assert sel["selected_task_type"] == "regular_pending"
        assert sel["selection_reason"] == "fallback_selected"


def test_select_returns_none_no_tasks_md():
    with tempfile.TemporaryDirectory() as tmp:
        r = LoopRunner()
        r.project_dir = tmp
        assert r._get_next_task_selection() is None


def test_select_returns_none_only_waiting_on():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "TASKS.md").write_text(
            "# Tasks\n\n## Waiting On\n\n- [ ] ignored task\n", encoding="utf-8"
        )
        r = LoopRunner()
        r.project_dir = tmp
        assert r._get_next_task_selection() is None


def test_select_returns_none_all_done():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "TASKS.md").write_text(
            "# Tasks\n\n## Active\n\n### Day 1\n\n- [x] done task\n", encoding="utf-8"
        )
        r = LoopRunner()
        r.project_dir = tmp
        assert r._get_next_task_selection() is None


# ── _mark_task_done ───────────────────────────────────────────────────────────

def test_mark_task_done():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "TASKS.md"
        p.write_text("# Tasks\n\n## Active\n\n- [ ] [TASK-01] 할 일\n", encoding="utf-8")
        r = LoopRunner()
        r.project_dir = tmp
        r._mark_task_done("[TASK-01] 할 일")
        result = p.read_text(encoding="utf-8")
        assert "- [x] [TASK-01] 할 일" in result
        assert "- [ ] [TASK-01] 할 일" not in result


# ── _find_test_dir ────────────────────────────────────────────────────────────

def test_find_test_dir_subdirectory():
    with tempfile.TemporaryDirectory() as tmp:
        sub = Path(tmp) / "my-app"
        sub.mkdir()
        (sub / "tests").mkdir()
        r = LoopRunner()
        r.project_dir = tmp
        assert r._find_test_dir() == sub


def test_find_test_dir_fallback_to_root():
    with tempfile.TemporaryDirectory() as tmp:
        r = LoopRunner()
        r.project_dir = tmp
        assert r._find_test_dir() == Path(tmp)


# ── 타임아웃 시 루프 중단 ─────────────────────────────────────────────────────

def test_timeout_stops_loop():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "TASKS.md").write_text(textwrap.dedent("""\
            # Tasks

            ## Active

            ### Day 2
            - [ ] [TASK-03] timeout-prone task
        """), encoding="utf-8")

        class TimeoutRunner(LoopRunner):
            def __init__(self):
                super().__init__()
                self.timeout_calls = 0
                self.test_calls = 0

            def _install_deps(self): return

            def _read_prompt(self, prompt_file): return "prompt"

            def _run_claude(self, prompt, extra_context=""):
                self.timeout_calls += 1
                return "오류: claude 실행 시간 초과", 1, True

            def _run_tests(self):
                self.test_calls += 1
                if self.test_calls > 1:
                    raise AssertionError("should not reach post-hardening tests after timeout")
                return False, "0 passed"  # step 0 기준 테스트

        r = TimeoutRunner()
        r.project_dir = tmp
        r.running = True
        r._run()
        assert r.current_stage == "error"
        assert r.timeout_calls == 2
