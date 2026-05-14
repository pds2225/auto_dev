"""tests/test_auto_dev_handoff_loop.py — auto_dev_handoff_loop 단위 테스트"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from auto_dev_handoff_loop import main, FORBIDDEN_FILES

CLAUDE_RESULT = """\
## 작업 완료 보고

TASK-010 구현 완료.
- dashboard/tunnel.py 수정
- tests/test_tunnel.py 추가

pytest: 12 passed
"""

CODEX_RESULT = """\
## Codex 작업 완료

코드 구현:
- main.py 수정
- utils.py 추가

모든 테스트 통과.
"""


@pytest.fixture()
def claude_input(tmp_path: Path) -> Path:
    f = tmp_path / "claude_result.md"
    f.write_text(CLAUDE_RESULT, encoding="utf-8")
    return f


@pytest.fixture()
def codex_input(tmp_path: Path) -> Path:
    f = tmp_path / "codex_result.md"
    f.write_text(CODEX_RESULT, encoding="utf-8")
    return f


def test_from_claude_generates_codex_handoff(tmp_path: Path, claude_input: Path) -> None:
    """--from claude 시 codex_handoff_*.md 생성"""
    rc = main(["--repo", str(tmp_path), "--from", "claude", "--input", str(claude_input)])
    assert rc == 0
    outputs = list(tmp_path.glob("codex_handoff_*.md"))
    assert len(outputs) == 1, "codex_handoff_*.md 파일이 하나 생성되어야 한다"


def test_from_codex_generates_claude_handoff(tmp_path: Path, codex_input: Path) -> None:
    """--from codex 시 claude_handoff_*.md 생성"""
    rc = main(["--repo", str(tmp_path), "--from", "codex", "--input", str(codex_input)])
    assert rc == 0
    outputs = list(tmp_path.glob("claude_handoff_*.md"))
    assert len(outputs) == 1, "claude_handoff_*.md 파일이 하나 생성되어야 한다"


def test_missing_input_file_returns_error(tmp_path: Path) -> None:
    """--input 파일 없으면 rc=1 반환"""
    rc = main(["--repo", str(tmp_path), "--from", "claude", "--input", str(tmp_path / "not_exist.md")])
    assert rc == 1


def test_no_tasks_md_still_works(tmp_path: Path, claude_input: Path) -> None:
    """TASKS.md 없어도 정상 동작"""
    assert not (tmp_path / "TASKS.md").exists()
    rc = main(["--repo", str(tmp_path), "--from", "claude", "--input", str(claude_input)])
    assert rc == 0


def test_no_agents_md_still_works(tmp_path: Path, codex_input: Path) -> None:
    """AGENTS.md 없어도 정상 동작"""
    assert not (tmp_path / "AGENTS.md").exists()
    rc = main(["--repo", str(tmp_path), "--from", "codex", "--input", str(codex_input)])
    assert rc == 0


def test_prompt_contains_repo_path(tmp_path: Path, claude_input: Path) -> None:
    """생성 프롬프트에 repo 절대경로 포함"""
    main(["--repo", str(tmp_path), "--from", "claude", "--input", str(claude_input)])
    out = next(tmp_path.glob("codex_handoff_*.md"))
    content = out.read_text(encoding="utf-8")
    assert str(tmp_path.resolve()) in content


def test_prompt_contains_input_path(tmp_path: Path, claude_input: Path) -> None:
    """생성 프롬프트에 input 파일 경로 포함"""
    main(["--repo", str(tmp_path), "--from", "claude", "--input", str(claude_input)])
    out = next(tmp_path.glob("codex_handoff_*.md"))
    content = out.read_text(encoding="utf-8")
    assert str(claude_input.resolve()) in content


def test_prompt_contains_forbidden_files(tmp_path: Path, claude_input: Path) -> None:
    """생성 프롬프트에 수정 금지 파일 목록 포함"""
    main(["--repo", str(tmp_path), "--from", "claude", "--input", str(claude_input)])
    out = next(tmp_path.glob("codex_handoff_*.md"))
    content = out.read_text(encoding="utf-8")
    for f in FORBIDDEN_FILES:
        assert f in content, f"{f} 가 프롬프트에 없다"


def test_copy_flag_not_required_for_file_creation(tmp_path: Path, codex_input: Path) -> None:
    """--copy 없이도 파일 생성 가능"""
    rc = main(["--repo", str(tmp_path), "--from", "codex", "--input", str(codex_input)])
    assert rc == 0
    outputs = list(tmp_path.glob("claude_handoff_*.md"))
    assert outputs


def test_prompt_contains_shared_claude_guidelines(tmp_path: Path, claude_input: Path) -> None:
    """공통 CLAUDE 지침이 핸드오프 프롬프트에 포함된다"""
    main(["--repo", str(tmp_path), "--from", "claude", "--input", str(claude_input)])
    out = next(tmp_path.glob("codex_handoff_*.md"))
    content = out.read_text(encoding="utf-8")
    assert "공통 작업 지침 (CLAUDE.md)" in content
    assert "Windows PowerShell" in content
