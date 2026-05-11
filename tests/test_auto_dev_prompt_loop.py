"""tests/test_auto_dev_prompt_loop.py — auto_dev_prompt_loop 단위 테스트"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from auto_dev_prompt_loop import _parse_pending, _build_prompt, main, FORBIDDEN_FILES

TASKS_FULL = """\
## PENDING
- TASK-003: 샘플 작업 설명
- TASK-004: 두 번째 작업

## RUNNING

## DONE
- TASK-001: 완료된 작업

## BLOCKED
"""

TASKS_EMPTY = """\
## PENDING

## DONE
- TASK-001: 완료된 작업
"""


@pytest.fixture()
def tasks_file(tmp_path: Path) -> Path:
    f = tmp_path / "TASKS.md"
    f.write_text(TASKS_FULL, encoding="utf-8")
    return f


@pytest.fixture()
def tasks_file_empty(tmp_path: Path) -> Path:
    f = tmp_path / "TASKS.md"
    f.write_text(TASKS_EMPTY, encoding="utf-8")
    return f


def test_pending_first_task(tasks_file: Path) -> None:
    """a. PENDING 첫 작업 선택"""
    pending = _parse_pending(tasks_file)
    assert len(pending) == 2
    assert pending[0][0] == "TASK-003"


def test_task_id_selection(tasks_file: Path, tmp_path: Path) -> None:
    """b. --task-id로 특정 TASK 선택"""
    rc = main(["--repo", str(tmp_path), "--task-id", "TASK-004"])
    assert rc == 0
    outputs = list(tmp_path.glob("auto_prompt_*.md"))
    assert outputs, "프롬프트 파일이 생성되어야 한다"
    assert "TASK-004" in outputs[0].read_text(encoding="utf-8")


def test_pending_empty_exits_zero(tasks_file_empty: Path, tmp_path: Path) -> None:
    """c. PENDING 비어 있으면 정상 종료(0)"""
    rc = main(["--repo", str(tmp_path)])
    assert rc == 0
    assert not list(tmp_path.glob("auto_prompt_*.md")), "파일이 생성되면 안 된다"


def test_prompt_contains_forbidden_files(tasks_file: Path, tmp_path: Path) -> None:
    """d. 생성 프롬프트에 금지 파일 목록 포함"""
    main(["--repo", str(tmp_path)])
    outputs = list(tmp_path.glob("auto_prompt_*.md"))
    assert outputs
    content = outputs[0].read_text(encoding="utf-8")
    for f in FORBIDDEN_FILES:
        assert f in content, f"{f} 가 프롬프트에 없다"
