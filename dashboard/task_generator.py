"""자동 태스크 생성기 — 로컬/서버에서 TASK.md에 태스크를 자동 추가"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# 기존 스캐폴드 생성기의 함수 재활용
sys.path.insert(0, str(Path(__file__).parent.parent))
from ai_project_scaffold_generator import (
    append_task_to_tasks_md,
    fallback_derivatives,
    fallback_prd,
    get_next_task_id,
    render_appended_task_template,
    slugify,
    write_tasks_document,
    write_tasks_with_fallback,
)


AUTO_DEV_DIR = Path(__file__).parent.parent


def _build_task_from_description(
    description: str,
    task_id: str = "",
    skill_tag: str = "incremental-implementation",
    effort: str = "1-2시간",
) -> dict:
    """간단한 설명으로부터 태스크 딕셔너리 생성"""
    return {
        "id": task_id or "TASK-NEW",
        "title": description[:60],
        "skill_tag": skill_tag,
        "depends_on": [],
        "effort": effort,
        "subtasks": ["요구사항 분석", "구현", "테스트"],
        "acceptance_criteria": [
            "정상 동작 확인",
            "예외 처리 확인",
            "테스트 통과",
        ],
        "verification": "pytest 또는 수동 실행",
    }


def generate_task_via_template(
    description: str,
    project_dir: str,
    tech_stack: str = "Streamlit",
) -> str:
    """템플릿 모드로 태스크를 생성하고 TASK.md에 추가"""
    proj = Path(project_dir)
    task_md = proj / "TASK.md"
    tasks_md = proj / "TASKS.md"

    # 기존 TASK.md 또는 TASKS.md에서 다음 ID 결정
    source_text = ""
    if task_md.exists():
        source_text = task_md.read_text(encoding="utf-8")
    elif tasks_md.exists():
        source_text = tasks_md.read_text(encoding="utf-8")

    next_id = get_next_task_id(source_text)
    task = _build_task_from_description(description, next_id)

    # TASK.md에 추가
    if task_md.exists():
        text = task_md.read_text(encoding="utf-8")
        appended = render_appended_task_template(task, next_id)
        # Active 섹션 찾아서 추가
        active_match = re.search(r"^(## Active\s*)$", text, re.MULTILINE)
        if active_match:
            insert_pos = active_match.end()
            updated = text[:insert_pos] + "\n\n" + appended + text[insert_pos:]
        else:
            updated = text.rstrip() + "\n\n## Active\n\n" + appended
        task_md.write_text(updated, encoding="utf-8")
    else:
        # TASK.md가 없으면 기본 구조 생성 후 추가
        prd = fallback_prd(description, proj.name)
        der = fallback_derivatives(prd, tech_stack)
        write_tasks_document(proj, prd, der, "v0.1")

    return next_id


def generate_task_via_ai(
    description: str,
    project_dir: str,
    provider: str = "template",
    api_key: str = "",
) -> dict:
    """AI를 통해 태스크를 생성 (API 키 있을 때)"""
    # API 모드는 기존 scaffold_generator의 generate_scaffold를 활용
    from ai_project_scaffold_generator import generate_scaffold

    result = generate_scaffold(
        description=description,
        folder_path=project_dir,
        tech_stack="Streamlit",
        provider=provider,
        api_key=api_key,
    )
    return result


def preview_task(description: str) -> dict:
    """TASK.md에 추가하기 전에 미리보기"""
    return _build_task_from_description(description)


# ── 셀프 테스트 ─────────────────────────────────────────────
def _self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp)
        # 기본 TASK.md 생성
        task_md = proj / "TASK.md"
        task_md.write_text("""# TASK.md — test

## Active

### Auto Dev Queue
- [ ] [TASK-01] 기존 태스크
""", encoding="utf-8")

        # 태스크 추가
        new_id = generate_task_via_template("새로운 로그인 기능 구현", str(proj))
        text = task_md.read_text(encoding="utf-8")
        assert new_id == "TASK-02"
        assert "로그인 기능" in text
        print(f"✅ 자동 생성 및 추가 완료: {new_id}")

    print("self-test passed")


if __name__ == "__main__":
    _self_test()