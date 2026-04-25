import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

from project_snapshot import get_project_snapshot
from project_snapshot import get_snapshot_note


def test_project_snapshot_parses_clean_repo(monkeypatch):
    calls: list[list[str]] = []
    tmp_path = Path(tempfile.mkdtemp(dir=r"C:\Users\Public\Documents\ESTsoft\CreatorTemp"))

    def fake_run(cmd, capture_output, text, check, timeout):
        calls.append(cmd)

        class Result:
            returncode = 0
            stdout = ""

        if cmd[-2:] == ["--abbrev-ref", "HEAD"]:
            Result.stdout = "main\n"
        elif cmd[-2:] == ["--short", "HEAD"]:
            Result.stdout = "a50d40c\n"
        elif cmd[-2:] == ["get-url", "origin"]:
            Result.stdout = "https://github.com/pds2225/auto_dev.git\n"
        elif cmd[-1] == "--short":
            Result.stdout = ""
        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    snapshot = get_project_snapshot(tmp_path)

    assert snapshot["available"] is True
    assert snapshot["branch"] == "main"
    assert snapshot["head"] == "a50d40c"
    assert snapshot["remote"] == "https://github.com/pds2225/auto_dev.git"
    assert snapshot["dirty"] is False
    assert snapshot["status"] == "clean"
    assert calls


def test_project_snapshot_marks_dirty(monkeypatch):
    tmp_path = Path(tempfile.mkdtemp(dir=r"C:\Users\Public\Documents\ESTsoft\CreatorTemp"))
    def fake_run(cmd, capture_output, text, check, timeout):
        class Result:
            returncode = 0
            stdout = ""

        if cmd[-2:] == ["--abbrev-ref", "HEAD"]:
            Result.stdout = "feature/status\n"
        elif cmd[-2:] == ["--short", "HEAD"]:
            Result.stdout = "abc1234\n"
        elif cmd[-2:] == ["get-url", "origin"]:
            Result.stdout = "https://github.com/pds2225/auto_dev.git\n"
        elif cmd[-1] == "--short":
            Result.stdout = " M dashboard/streamlit_app.py\n"
        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    snapshot = get_project_snapshot(tmp_path)

    assert snapshot["dirty"] is True
    assert snapshot["status"] == "dirty"


def test_project_snapshot_handles_non_git_repo(monkeypatch):
    tmp_path = Path(tempfile.mkdtemp(dir=r"C:\Users\Public\Documents\ESTsoft\CreatorTemp"))

    def fake_run(cmd, capture_output, text, check, timeout):
        class Result:
            returncode = 1
            stdout = ""

        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    snapshot = get_project_snapshot(tmp_path)

    assert snapshot["available"] is False
    assert snapshot["branch"] == ""
    assert snapshot["head"] == ""
    assert snapshot["remote"] == ""
    assert snapshot["dirty"] is False
    assert snapshot["status"] == ""
    assert snapshot["error"] == "git repo not available"
    assert get_snapshot_note(snapshot) == "Git 상태를 읽지 못했습니다: git repo not available"


def test_project_snapshot_handles_missing_origin(monkeypatch):
    tmp_path = Path(tempfile.mkdtemp(dir=r"C:\Users\Public\Documents\ESTsoft\CreatorTemp"))

    def fake_run(cmd, capture_output, text, check, timeout):
        class Result:
            returncode = 0
            stdout = ""

        if cmd[-2:] == ["--abbrev-ref", "HEAD"]:
            Result.stdout = "main\n"
        elif cmd[-2:] == ["--short", "HEAD"]:
            Result.stdout = "abc1234\n"
        elif cmd[-2:] == ["get-url", "origin"]:
            Result.returncode = 1
        elif cmd[-1] == "--short":
            Result.stdout = ""
        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    snapshot = get_project_snapshot(tmp_path)

    assert snapshot["available"] is True
    assert snapshot["branch"] == "main"
    assert snapshot["head"] == "abc1234"
    assert snapshot["remote"] == ""
    assert snapshot["dirty"] is False
    assert snapshot["status"] == "clean"
    assert get_snapshot_note(snapshot) == "이 경로는 Git 저장소가 아니거나, 아직 원격이 설정되지 않았습니다."
