import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

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
