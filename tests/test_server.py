import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

import server
from server import app, runner


def test_api_tasks_counts_only_active_section():
    with tempfile.TemporaryDirectory() as tmp:
        runner.project_dir = tmp
        (Path(tmp) / "TASKS.md").write_text(
            textwrap.dedent(
                """\
                # Tasks

                ## Active

                ### Day 1
                - [x] [TASK-01] 완료 태스크
                - [ ] [TASK-02] 진행 태스크

                ## 태스크 상세

                ### TASK-02
                - [ ] 상세 수락 기준 1
                - [ ] 상세 수락 기준 2
                """
            ),
            encoding="utf-8",
        )

        client = app.test_client()
        response = client.get("/api/tasks")
        data = response.get_json()

        assert response.status_code == 200
        assert data == {
            "done": ["[TASK-01] 완료 태스크"],
            "pending": ["[TASK-02] 진행 태스크"],
            "total": 2,
        }


def test_api_tasks_prefers_task_md():
    with tempfile.TemporaryDirectory() as tmp:
        runner.project_dir = tmp
        (Path(tmp) / "TASK.md").write_text(
            textwrap.dedent(
                """\
                # Tasks

                ## Active

                ### Day 1
                - [x] [TASK-01] task md 완료
                - [ ] [TASK-02] task md 진행
                """
            ),
            encoding="utf-8",
        )
        (Path(tmp) / "TASKS.md").write_text(
            textwrap.dedent(
                """\
                # Tasks

                ## Active

                ### Day 9
                - [ ] [TASK-99] tasks md only
                """
            ),
            encoding="utf-8",
        )

        client = app.test_client()
        response = client.get("/api/tasks")
        data = response.get_json()

        assert response.status_code == 200
        assert data == {
            "done": ["[TASK-01] task md 완료"],
            "pending": ["[TASK-02] task md 진행"],
            "total": 2,
        }


def test_api_snapshot_uses_query_param(monkeypatch):
    called = {}

    def fake_get_project_snapshot(repo_dir):
        called["repo_dir"] = repo_dir
        return {
            "available": True,
            "repo_dir": repo_dir,
            "branch": "main",
            "head": "abc1234",
            "remote": "",
            "dirty": False,
            "status": "clean",
            "error": "",
        }

    monkeypatch.setattr(server, "get_project_snapshot", fake_get_project_snapshot)
    client = app.test_client()
    response = client.get("/api/snapshot?repo_dir=D:/demo-project")
    data = response.get_json()

    assert response.status_code == 200
    assert called["repo_dir"] == "D:/demo-project"
    assert data["repo_dir"] == "D:/demo-project"
    assert data["note"] == "이 경로는 Git 저장소가 아니거나, 아직 원격이 설정되지 않았습니다."


def test_api_snapshot_falls_back_to_runner_project_dir(monkeypatch):
    called = {}

    def fake_get_project_snapshot(repo_dir):
        called["repo_dir"] = repo_dir
        return {
            "available": True,
            "repo_dir": repo_dir,
            "branch": "main",
            "head": "abc1234",
            "remote": "https://github.com/pds2225/auto_dev.git",
            "dirty": False,
            "status": "clean",
            "error": "",
        }

    runner.project_dir = "D:/selected-project"
    monkeypatch.setattr(server, "get_project_snapshot", fake_get_project_snapshot)
    client = app.test_client()
    response = client.get("/api/snapshot")
    data = response.get_json()

    assert response.status_code == 200
    assert called["repo_dir"] == "D:/selected-project"
    assert data["note"] == "origin: https://github.com/pds2225/auto_dev.git"
