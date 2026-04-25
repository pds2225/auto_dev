"""HISTORY.md 자동 관리자
- TASK.md에서 [x] 완료된 태스크를 HISTORY.md로 이동
- TASKS.md는 TASK.md + HISTORY.md를 합쳐서 자동 생성
- 루프는 TASKS.md만 읽음
"""
from __future__ import annotations

import re
from pathlib import Path
from datetime import date, datetime


def _extract_section(text: str, heading: str, level: int = 2) -> str:
    """마크다운 섹션 추출"""
    pattern = rf"^{re.escape('#' * level)} {re.escape(heading)}\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_section = re.search(rf"^{re.escape('#' * level)}\s+", text[start:], flags=re.MULTILINE)
    end = start + next_section.start() if next_section else len(text)
    return text[start:end].strip()


def _extract_tasks(lines: list[str]) -> list[dict]:
    """체크박스 라인에서 태스크 정보 추출"""
    tasks = []
    for line in lines:
        line = line.strip()
        # 완료된 태스크 [x]
        m = re.match(r"^- \[x\] (.+)$", line)
        if m:
            tasks.append({"text": m.group(1).strip(), "done": True, "raw": line})
            continue
        # 미완료 태스크 [ ]
        m = re.match(r"^- \[ \] (.+)$", line)
        if m:
            tasks.append({"text": m.group(1).strip(), "done": False, "raw": line})
    return tasks


def _build_task_md(active_text: str, project_name: str = "auto_dev") -> str:
    """TASK.md 형식으로 생성"""
    lines = [
        f"# TASK.md — {project_name}",
        "",
        f"> Based on: TASKS.md",
        f"> Status: Active",
        f"> Last Updated: {date.today()}",
        f"> 대상 프로젝트: D:/{project_name}",
        "",
        "---",
        "",
        "## Active",
        "",
        "### Auto Dev Queue",
        "",
    ]

    if active_text.strip():
        for task_line in active_text.strip().splitlines():
            if task_line.strip():
                lines.append(task_line.strip())
    else:
        lines.append("- [ ] [TASK-01] 첫 번째 태스크를 여기에 작성하세요")

    lines.extend([
        "",
        "---",
        "",
        "## Waiting On",
        "",
        "- (없음)",
        "",
    ])
    return "\n".join(lines)


def _build_history_md(done_tasks: list[str], project_name: str = "auto_dev") -> str:
    """HISTORY.md 형식으로 생성"""
    lines = [
        f"# HISTORY.md — {project_name}",
        "",
        f"> 완료된 태스크 기록",
        f"> Last Updated: {date.today()}",
        "",
        "---",
        "",
        "## Done",
        "",
    ]

    if done_tasks:
        for task in done_tasks:
            lines.append(f"- [x] {task}")
    else:
        lines.append("- [x] 초기 설정 완료")

    lines.append("")
    return "\n".join(lines)


def _build_tasks_md(task_md_text: str, history_md_text: str, project_name: str = "auto_dev") -> str:
    """TASK.md + HISTORY.md → TASKS.md 통합본 생성"""
    # TASK.md에서 Active 섹션 추출
    active = _extract_section(task_md_text, "Active")
    # HISTORY.md에서 Done 섹션 추출
    done = _extract_section(history_md_text, "Done")

    lines = [
        f"# TASKS.md — {project_name}",
        "",
        f"> Based on: TASK.md + HISTORY.md",
        f"> Status: Unified",
        f"> Last Updated: {date.today()}",
        f"> 대상 프로젝트: D:/{project_name}",
        "",
        "---",
        "",
    ]

    # Active 섹션
    if active.strip():
        lines.append("## Active")
        lines.append("")
        lines.append(active)
    else:
        lines.append("## Active")
        lines.append("")
        lines.append("### Auto Dev Queue")
        lines.append("")
        lines.append("- [ ] [TASK-01] 첫 번째 태스크를 여기에 작성하세요")

    lines.extend([
        "",
        "---",
        "",
        "## Waiting On",
        "",
        "- (없음)",
        "",
        "---",
        "",
    ])

    # Done 섹션
    if done.strip():
        lines.append("## Done")
        lines.append("")
        lines.append(done)
    else:
        lines.append("## Done")
        lines.append("")
        lines.append("- [x] 초기 설정 완료")

    lines.append("")
    return "\n".join(lines)


def sync_all(project_dir: str | Path) -> dict[str, Path]:
    """TASK.md + HISTORY.md → TASKS.md 동기화"""
    proj = Path(project_dir)
    task_md = proj / "TASK.md"
    history_md = proj / "HISTORY.md"
    tasks_md = proj / "TASKS.md"

    # TASK.md 읽기 (없으면 기본 생성)
    if task_md.exists():
        task_text = task_md.read_text(encoding="utf-8")
    else:
        task_text = _build_task_md("", proj.name)
        task_md.write_text(task_text, encoding="utf-8")

    # HISTORY.md 읽기 (없으면 기본 생성)
    if history_md.exists():
        history_text = history_md.read_text(encoding="utf-8")
    else:
        history_text = _build_history_md([], proj.name)
        history_md.write_text(history_text, encoding="utf-8")

    # TASKS.md 생성 (통합)
    tasks_text = _build_tasks_md(task_text, history_text, proj.name)
    tasks_md.write_text(tasks_text, encoding="utf-8")

    return {
        "task_md": task_md,
        "history_md": history_md,
        "tasks_md": tasks_md,
    }


def mark_task_done(project_dir: str | Path, task_text: str) -> bool:
    """태스크를 완료 처리: TASK.md에서 제거 → HISTORY.md에 추가"""
    proj = Path(project_dir)
    task_md = proj / "TASK.md"
    history_md = proj / "HISTORY.md"

    if not task_md.exists():
        return False

    # TASK.md에서 해당 태스크를 [x]로 표시하거나 제거
    task_content = task_md.read_text(encoding="utf-8")
    # [ ] → [x]로 변경
    updated = task_content.replace(f"- [ ] {task_text}", f"- [x] {task_text}", 1)

    # 만약 완료된 태스크를 HISTORY.md로 이동하고 싶으면 아래 주석 해제
    # if updated != task_content:
    #     # HISTORY.md에 추가
    #     history_lines = []
    #     if history_md.exists():
    #         history_text = history_md.read_text(encoding="utf-8")
    #         history_lines = [l.strip() for l in history_text.splitlines() if l.strip()]
    #     history_lines.append(f"- [x] {task_text} | 완료: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    #     history_md.write_text("\n".join(history_lines) + "\n", encoding="utf-8")
    #     # TASK.md에서 제거
    #     updated = updated.replace(f"- [x] {task_text}\n", "\n", 1)

    task_md.write_text(updated, encoding="utf-8")

    # TASKS.md 재생성
    sync_all(project_dir)
    return True


# ── 셀프 테스트 ─────────────────────────────────────────────
def _self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp)

        # 케이스 1: 빈 폴더에서 전체 생성
        result = sync_all(proj)
        assert result["task_md"].exists()
        assert result["history_md"].exists()
        assert result["tasks_md"].exists()

        tasks_text = result["tasks_md"].read_text(encoding="utf-8")
        assert "## Active" in tasks_text
        assert "## Done" in tasks_text
        print("✅ 케이스 1: 빈 폴더에서 3개 파일 자동 생성")

        # 케이스 2: TASK.md에 태스크 추가 후 동기화
        task_content = result["task_md"].read_text(encoding="utf-8")
        task_content = task_content.replace(
            "- [ ] [TASK-01] 첫 번째 태스크를 여기에 작성하세요",
            "- [ ] [TASK-14] 프롬프트 중앙화\n- [ ] [TASK-15] Streamlit 통합"
        )
        result["task_md"].write_text(task_content, encoding="utf-8")

        sync_all(proj)
        tasks_text = result["tasks_md"].read_text(encoding="utf-8")
        assert "TASK-14" in tasks_text
        assert "TASK-15" in tasks_text
        print("✅ 케이스 2: TASK.md 수정 후 TASKS.md 동기화")

        # 케이스 3: 완료 처리
        mark_task_done(proj, "[TASK-14] 프롬프트 중앙화")
        task_text = result["task_md"].read_text(encoding="utf-8")
        assert "[x] [TASK-14]" in task_text
        print("✅ 케이스 3: 태스크 완료 처리")

    print("모든 self-test 통과!")


if __name__ == "__main__":
    _self_test()