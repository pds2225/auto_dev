import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))

import task_generator


def test_decompose_tasks_with_fallback_uses_template_when_ai_fails(monkeypatch):
    def fail_decompose(description, tech_stack="Streamlit"):
        raise RuntimeError("network down")

    monkeypatch.setattr(task_generator, "decompose_tasks_with_ai", fail_decompose)

    tasks, source = task_generator.decompose_tasks_with_fallback("외부 접속 링크 생성 실패 보완", "Streamlit")

    assert source == "template-fallback"
    assert len(tasks) == 1
    assert tasks[0]["title"] == "외부 접속 링크 생성 실패 보완"
    assert tasks[0]["verification"] == "pytest 또는 수동 실행"


def test_decompose_tasks_with_fallback_keeps_ai_tasks(monkeypatch):
    ai_tasks = [
        {
            "id": "TASK-01",
            "title": "AI 분해 태스크",
            "skill_tag": "frontend-ui",
            "effort": "30분",
            "subtasks": ["구현"],
            "acceptance_criteria": ["동작"],
            "verification": "pytest",
        }
    ]

    monkeypatch.setattr(task_generator, "decompose_tasks_with_ai", lambda *_args, **_kwargs: ai_tasks)

    tasks, source = task_generator.decompose_tasks_with_fallback("설명", "Streamlit")

    assert source == "ai"
    assert tasks == ai_tasks
