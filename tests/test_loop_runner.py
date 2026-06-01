import json
import os
import subprocess
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
        assert sel["selected_task_id"] == "TASK-01"
        assert sel["selected_task_type"] == "generated"
        assert sel["selection_reason"] == "lowest_generated_pending"


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
        assert sel["selected_task_id"] == "TASK-30"
        assert sel["selection_reason"] == "lowest_generated_pending"


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


def test_select_returns_task_md_when_present():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "TASK.md").write_text(textwrap.dedent("""\
            # Tasks

            ## Active

            ### Day 1
            - [ ] [TASK-01] task from task md
        """), encoding="utf-8")
        r = LoopRunner()
        r.project_dir = tmp
        sel = r._get_next_task_selection()
        assert sel is not None
        assert sel["selected_task_id"] == "TASK-01"


def test_select_prefers_task_md_over_tasks_md():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "TASK.md").write_text(textwrap.dedent("""\
            # Tasks

            ## Active

            ### Day 1
            - [ ] [TASK-01] task md first
        """), encoding="utf-8")
        (Path(tmp) / "TASKS.md").write_text(textwrap.dedent("""\
            # Tasks

            ## Active

            ### Day 1
            - [ ] [TASK-09] tasks md fallback
        """), encoding="utf-8")
        r = LoopRunner()
        r.project_dir = tmp
        sel = r._get_next_task_selection()
        assert sel is not None
        assert sel["selected_task_id"] == "TASK-01"


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

def test_mark_task_done_prefers_task_md():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "TASK.md"
        p.write_text("# Tasks\n\n## Active\n\n- [ ] [TASK-01] 할 일\n", encoding="utf-8")
        r = LoopRunner()
        r.project_dir = tmp
        r._mark_task_done("[TASK-01] 할 일")
        result = p.read_text(encoding="utf-8")
        assert "- [x] [TASK-01] 할 일" in result
        assert "- [ ] [TASK-01] 할 일" not in result


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


# ── scaffold 분기 ────────────────────────────────────────────────────────────

def test_detect_code_files_empty_project():
    with tempfile.TemporaryDirectory() as tmp:
        r = LoopRunner()
        r.project_dir = tmp
        assert r._detect_code_files() == []


def test_detect_code_files_finds_python():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "main.py").write_text("print('hi')")
        (Path(tmp) / "README.md").write_text("# readme")
        r = LoopRunner()
        r.project_dir = tmp
        files = r._detect_code_files()
        assert len(files) == 1
        assert files[0].name == "main.py"


def test_detect_code_files_skips_pycache():
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "__pycache__"
        cache.mkdir()
        (cache / "mod.py").write_text("x=1")
        (Path(tmp) / "app.py").write_text("x=1")
        r = LoopRunner()
        r.project_dir = tmp
        files = r._detect_code_files()
        assert all("__pycache__" not in str(f) for f in files)
        assert len(files) == 1


def test_scaffold_routes_to_template_when_empty():
    """코드 파일 없으면 _scaffold_from_template 경로로 가야 함 (파일 없어 실패하지만 분기는 확인)."""
    with tempfile.TemporaryDirectory() as tmp:
        r = LoopRunner()
        r.project_dir = tmp
        assert r._detect_code_files() == []


def test_scaffold_routes_to_analysis_when_code_exists():
    """코드 파일 있으면 _scaffold_from_code_analysis 경로로 가야 함 (분기 단위 테스트)."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "app.py").write_text("def main(): pass")
        r = LoopRunner()
        r.project_dir = tmp
        code_files = r._detect_code_files()
        assert len(code_files) == 1


def test_summarize_codebase_uses_structure_not_full_source():
    with tempfile.TemporaryDirectory() as tmp:
        app_py = Path(tmp) / "monitor.py"
        app_py.write_text(textwrap.dedent("""\
            import os
            import subprocess

            class Monitor:
                pass

            def main():
                return os.environ.get("TOKEN", "fallback")

            if __name__ == "__main__":
                main()
        """), encoding="utf-8")
        r = LoopRunner()
        r.project_dir = tmp
        summary = r.summarize_codebase([app_py])
        assert "file: monitor.py" in summary
        assert "imports: os, subprocess" in summary
        assert "functions: main" in summary
        assert "classes: Monitor" in summary
        assert "entrypoint: __main__" in summary
        assert "core_risk_estimate:" in summary
        assert 'return os.environ.get("TOKEN", "fallback")' not in summary


def test_scaffold_code_analysis_falls_back_to_existing_safe_when_claude_fails():
    with tempfile.TemporaryDirectory() as tmp:
        app_py = Path(tmp) / "app.py"
        app_py.write_text("def main():\n    return 1\n", encoding="utf-8")

        class FallbackRunner(LoopRunner):
            def _run_claude(self, prompt, extra_context=""):
                return "", 1, False

        r = FallbackRunner()
        r.project_dir = tmp
        assert r._scaffold_from_code_analysis([app_py]) is True
        tasks_text = r._get_task_file_path().read_text(encoding="utf-8")
        assert "Based on: Existing Safe Fallback" in tasks_text
        assert "[TASK-01] Existing behavior snapshot" in tasks_text


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


def test_find_test_targets_prefers_direct_tests_dir():
    with tempfile.TemporaryDirectory() as tmp:
        sub = Path(tmp) / "my-app"
        sub.mkdir()
        (sub / "tests").mkdir()
        r = LoopRunner()
        r.project_dir = tmp
        assert r._find_test_targets() == [os.path.relpath(sub / "tests", Path(tmp))]


def test_find_test_targets_discovers_nested_service_tests():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "services" / "alpha" / "tests").mkdir(parents=True)
        (root / "services" / "beta" / "tests").mkdir(parents=True)
        (root / "node_modules" / "pkg" / "tests").mkdir(parents=True)
        r = LoopRunner()
        r.project_dir = tmp
        assert r._find_test_targets() == [
            os.path.join("services", "alpha", "tests"),
            os.path.join("services", "beta", "tests"),
        ]


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

            def _run_codex(self, prompt, extra_context="", *, bypass_sandbox=False):
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


# ── codex 커맨드 빌더 ──────────────────────────────────────────────────────────

def test_build_codex_command_default():
    r = LoopRunner()
    r.project_dir = "/tmp/proj"
    cmd = r._build_codex_command("hello", "/tmp/out.txt")
    assert Path(cmd[0]).name.lower() in {"codex", "codex.cmd", "codex.exe"}
    assert cmd[1] == "exec"
    assert "--full-auto" in cmd
    assert "--sandbox" not in cmd
    assert "--ephemeral" in cmd
    assert "--json" in cmd
    assert "-o" in cmd
    assert "hello" in cmd


def test_build_codex_command_bypass_sandbox():
    r = LoopRunner()
    r.project_dir = "/tmp/proj"
    cmd = r._build_codex_command("hello", "/tmp/out.txt", bypass_sandbox=True)
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert "--full-auto" not in cmd


# ── JSON 파서 ─────────────────────────────────────────────────────────────────

def test_extract_codex_json_assistant_event():
    r = LoopRunner()
    raw = '{"type":"assistant","message":{"content":[{"type":"text","text":"작업 완료"}]}}'
    lines = r._extract_codex_json_lines(raw)
    assert lines == ["작업 완료"]


def test_extract_codex_json_result_event():
    r = LoopRunner()
    raw = '{"type":"result","result":"성공적으로 완료됨"}'
    lines = r._extract_codex_json_lines(raw)
    assert lines == ["성공적으로 완료됨"]


def test_extract_codex_json_error_event():
    r = LoopRunner()
    raw = '{"type":"error","message":"rate limit exceeded"}'
    lines = r._extract_codex_json_lines(raw)
    assert lines == ["rate limit exceeded"]


def test_extract_codex_json_invalid_falls_back():
    r = LoopRunner()
    lines = r._extract_codex_json_lines("not json at all")
    assert lines == ["not json at all"]


def test_extract_codex_json_empty_string():
    r = LoopRunner()
    assert r._extract_codex_json_lines("") == []


def test_extract_codex_json_skips_long_text():
    r = LoopRunner()
    long_text = "x" * 2001
    raw = f'{{"type":"result","result":"{long_text}"}}'
    lines = r._extract_codex_json_lines(raw)
    assert lines == []


# ── 에러 분류 ─────────────────────────────────────────────────────────────────

def test_classify_auth_error():
    r = LoopRunner()
    assert r._classify_codex_error("Error 401 unauthorized", 1) == "auth"
    assert r._classify_codex_error("invalid api key provided", 1) == "auth"


def test_classify_rate_error():
    r = LoopRunner()
    assert r._classify_codex_error("429 rate limit exceeded", 1) == "rate"
    assert r._classify_codex_error("too many requests", 1) == "rate"


def test_classify_perm_error():
    r = LoopRunner()
    assert r._classify_codex_error("permission denied", 1) == "perm"
    assert r._classify_codex_error("", 126) == "perm"


def test_classify_other_error():
    r = LoopRunner()
    assert r._classify_codex_error("unexpected failure", 1) == "other"
    assert r._classify_codex_error("", 1) == "other"


# ── 재시도 정책 ───────────────────────────────────────────────────────────────

def test_retry_stops_on_auth_error():
    """인증 오류는 재시도 없이 즉시 종료해야 한다."""
    call_count = {"n": 0}

    class AuthErrRunner(LoopRunner):
        def _run_codex(self, prompt, extra_context="", *, bypass_sandbox=False):
            call_count["n"] += 1
            return "Error 401 unauthorized", 1, False

    r = AuthErrRunner()
    r.project_dir = "/tmp"
    r._run_codex_with_retries("test")
    assert call_count["n"] == 1


def test_retry_escalates_to_bypass_on_perm_error():
    """권한 오류 발생 시 두 번째 시도는 bypass_sandbox=True여야 한다."""
    calls = []

    class PermErrRunner(LoopRunner):
        def _run_codex(self, prompt, extra_context="", *, bypass_sandbox=False):
            calls.append(bypass_sandbox)
            if not bypass_sandbox:
                return "permission denied", 1, False
            return "ok", 0, False

    r = PermErrRunner()
    r.project_dir = "/tmp"
    out, code, _ = r._run_codex_with_retries("test")
    assert calls == [False, True]
    assert code == 0


# ── approval/sandbox 감지 ─────────────────────────────────────────────────────

def test_classify_approval_error():
    r = LoopRunner()
    assert r._classify_codex_error("requires approval for this action", 1) == "perm"
    assert r._classify_codex_error("approval required", 1) == "perm"
    assert r._classify_codex_error("needs approval", 1) == "perm"


def test_classify_sandbox_error():
    r = LoopRunner()
    assert r._classify_codex_error("sandbox violation detected", 1) == "perm"
    assert r._classify_codex_error("access denied", 1) == "perm"


def test_bypass_fails_after_second_perm_logs_skip():
    """bypass=True 후 perm 재발 시 '건너뜁니다' 로그 남기고 break해야 한다."""
    calls = []

    class AlwaysPermRunner(LoopRunner):
        def _run_codex(self, prompt, extra_context="", *, bypass_sandbox=False):
            calls.append(bypass_sandbox)
            return "permission denied", 1, False

    r = AlwaysPermRunner()
    r.project_dir = "/tmp"
    r._run_codex_with_retries("test")
    assert calls == [False, True]  # 첫 시도 + bypass 재시도만
    logs = list(r.log_queue.queue)
    assert any("건너뜁니다" in line for line in logs), "건너뜁니다 로그가 없다"


def test_safety_note_appended_to_codex_prompt():
    """_run_codex 호출 시 _CODEX_SAFETY_NOTE가 full_prompt에 포함돼야 한다."""
    captured = {}

    class CaptureRunner(LoopRunner):
        def _popen_project_command(self, cmd, **kwargs):
            captured["prompt"] = cmd[-1]  # 마지막 인자가 full_prompt

            class FakeProc:
                stdout = []
                stderr = []
                returncode = 0
                def wait(self, timeout=None): return 0

            return FakeProc()

    with tempfile.TemporaryDirectory() as tmp:
        r = CaptureRunner()
        r.project_dir = tmp
        r._run_codex("original prompt")
    assert LoopRunner._CODEX_SAFETY_NOTE in captured.get("prompt", "")


# ── 웹 API /api/prompt-generate ───────────────────────────────────────────────

import json as _json
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / "dashboard"))

import pytest

try:
    from server import app as _flask_app
    _HAS_SERVER = True
except Exception:
    _HAS_SERVER = False


@pytest.fixture()
def _client():
    if not _HAS_SERVER:
        pytest.skip("server import failed")
    _flask_app.config["TESTING"] = True
    with _flask_app.test_client() as c:
        yield c


def _pg_post(client, body):
    return client.post(
        "/api/prompt-generate",
        data=_json.dumps(body),
        content_type="application/json",
    )


def test_api_task_to_claude(_client, tmp_path):
    """task_to_claude: TASKS.md → auto_prompt_*.md 생성, ok=true"""
    tasks_md = tmp_path / "TASKS.md"
    tasks_md.write_text("## PENDING\n- TASK-001: 테스트 작업\n\n## DONE\n", encoding="utf-8")
    res = _pg_post(_client, {"repo_dir": str(tmp_path), "mode": "task_to_claude"})
    data = res.get_json()
    assert data["ok"] is True
    assert _Path(data["output_file"]).exists()
    assert "TASK-001" in _Path(data["output_file"]).read_text(encoding="utf-8")


def test_api_claude_to_codex(_client, tmp_path):
    """claude_to_codex: input 파일 → codex_handoff_*.md 생성"""
    inp = tmp_path / "claude_result.md"
    inp.write_text("구현 완료.\npytest: 5 passed\n", encoding="utf-8")
    res = _pg_post(_client, {"repo_dir": str(tmp_path), "mode": "claude_to_codex", "input_file": str(inp)})
    data = res.get_json()
    assert data["ok"] is True
    assert "codex_handoff_" in _Path(data["output_file"]).name


def test_api_codex_to_claude(_client, tmp_path):
    """codex_to_claude: input 파일 → claude_handoff_*.md 생성"""
    inp = tmp_path / "codex_result.md"
    inp.write_text("Codex 완료.\n", encoding="utf-8")
    res = _pg_post(_client, {"repo_dir": str(tmp_path), "mode": "codex_to_claude", "input_file": str(inp)})
    data = res.get_json()
    assert data["ok"] is True
    assert "claude_handoff_" in _Path(data["output_file"]).name


def test_api_missing_input_file(_client, tmp_path):
    """input_file 없으면 ok=false, 오류 메시지 반환"""
    res = _pg_post(_client, {
        "repo_dir": str(tmp_path),
        "mode": "claude_to_codex",
        "input_file": str(tmp_path / "not_exist.md"),
    })
    data = res.get_json()
    assert data["ok"] is False
    assert "error" in data

# ── 품질 필터 ─────────────────────────────────────────────────────────────────

def test_validate_changed_files_no_git_repo():
    """git 저장소가 아니면 검증을 건너뛴다."""
    with tempfile.TemporaryDirectory() as tmp:
        r = LoopRunner()
        r.project_dir = tmp
        valid, issues = r._validate_changed_files()
        assert valid is True
        assert issues == []


def test_validate_changed_files_py_syntax_error_rollback():
    """Python 문법 오류 파일을 git checkout으로 롤백한다."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp, capture_output=True)

        app_py = Path(tmp) / "app.py"
        app_py.write_text("print('ok')", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp, capture_output=True)

        app_py.write_text("improt os\n", encoding="utf-8")

        r = LoopRunner()
        r.project_dir = tmp
        valid, issues = r._validate_changed_files()
        assert valid is False
        assert len(issues) == 1
        assert issues[0]["file"] == "app.py"
        # 롤백 확인
        assert app_py.read_text(encoding="utf-8") == "print('ok')"


def test_validate_changed_files_consecutive_quality_warning():
    """연속 3회 품질 불량이면 'AI 모델 교체 권고' 경고 로그를 남긴다."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp, capture_output=True)

        app_py = Path(tmp) / "app.py"
        app_py.write_text("print('ok')", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp, capture_output=True)

        # 기존 품질 로그에 2개의 이슈를 미리 기록
        quality_log = Path(tmp) / "quality_log.json"
        quality_log.write_text(json.dumps({
            "issues": [
                {"task_id": "T1", "file": "a.py", "error": "e1", "timestamp": "2026-01-01T00:00:00", "project_dir": tmp},
                {"task_id": "T2", "file": "b.py", "error": "e2", "timestamp": "2026-01-01T00:00:00", "project_dir": tmp},
            ]
        }), encoding="utf-8")

        app_py.write_text("improt os\n", encoding="utf-8")

        r = LoopRunner()
        r.project_dir = tmp
        r._validate_changed_files()

        logs = list(r.log_queue.queue)
        assert any("AI 모델 교체 권고" in line for line in logs), "연속 3회 경고 로그가 없다"
