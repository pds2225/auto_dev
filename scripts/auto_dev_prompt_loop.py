#!/usr/bin/env python3
"""
auto_dev_prompt_loop.py
TASKS.md의 PENDING 태스크를 읽어 Claude Code에 붙여넣을 프롬프트를 생성한다.
브랜치 생성, 커밋, push, PR 생성은 수행하지 않는다.

사용법:
  python scripts/auto_dev_prompt_loop.py [--copy] [--task-id TASK-XXX] [--repo PATH]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# ── 수정 금지 파일 목록 (AGENTS.md 섹션 2 기준) ─────────────────────────────
FORBIDDEN_FILES = [
    ".github/workflows/*.yml",
    "scripts/run_auto_dev_once.py",
    "scripts/auto_dev_queue.py",
    ".env",
    ".env.*",
    "AGENTS.md",
    "RULES.md",
]


def _parse_pending(tasks_md: Path) -> list[tuple[str, str]]:
    """PENDING 섹션에서 (task_id, full_line) 목록을 반환한다."""
    text = tasks_md.read_text(encoding="utf-8")
    in_pending = False
    tasks: list[tuple[str, str]] = []
    for line in text.splitlines():
        if line.strip() == "## PENDING":
            in_pending = True
            continue
        if in_pending and line.startswith("## "):
            break
        if in_pending and line.startswith("- TASK-"):
            raw = line[2:].strip()
            task_id = raw.split(":")[0].strip()
            tasks.append((task_id, raw))
    return tasks


def _build_prompt(task_id: str, task_desc: str, repo_root: Path) -> str:
    forbidden = "\n".join(f"  - {f}" for f in FORBIDDEN_FILES)
    return f"""\
# Claude Code 자동개발 프롬프트 — {task_id}

## 작업 저장소
{repo_root}

## 선택 TASK
{task_desc}

## 준수 규칙 (AGENTS.md)
- 기존 구조 유지, 최소 변경만 수행한다.
- 아래 파일은 절대 수정하지 않는다:
{forbidden}
- .claude/settings.local.json은 커밋 대상에서 제외한다.
- main 브랜치에 직접 push 금지.
- 새 브랜치에서만 작업한다.
- PR 생성하지 말고 변경 내용만 보고한다.
- 무제한 루프 금지. 기본 실행은 1회만 수행한다.

## 작업 후 보고 형식
1. 변경 파일 목록
2. 검증 명령 및 결과
3. 변경 내용 요약
"""


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="PENDING TASK → Claude Code 프롬프트 생성")
    parser.add_argument("--copy", action="store_true", help="생성된 프롬프트를 Windows 클립보드에 복사")
    parser.add_argument("--task-id", metavar="TASK-XXX", help="지정 TASK 우선 선택")
    parser.add_argument("--repo", metavar="PATH", help="repo root 경로 (기본: 현재 디렉터리)")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo).resolve() if args.repo else Path.cwd()
    tasks_md = repo_root / "TASKS.md"

    if not tasks_md.exists():
        print(f"ERROR: TASKS.md not found at {tasks_md}", file=sys.stderr)
        return 1

    pending = _parse_pending(tasks_md)

    if not pending:
        print("PENDING task not found")
        return 0

    if args.task_id:
        matched = [(tid, desc) for tid, desc in pending if tid == args.task_id]
        if not matched:
            print(f"ERROR: {args.task_id} not found in PENDING", file=sys.stderr)
            return 1
        task_id, task_desc = matched[0]
    else:
        task_id, task_desc = pending[0]

    prompt = _build_prompt(task_id, task_desc, repo_root)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = repo_root / f"auto_prompt_{timestamp}.md"
    out_file.write_text(prompt, encoding="utf-8")
    print(f"선택 TASK : {task_desc}")
    print(f"저장 경로 : {out_file}")

    if args.copy:
        try:
            import subprocess
            proc = subprocess.run(
                ["powershell", "-Command", f"Set-Clipboard -Value @'\n{prompt}\n'@"],
                capture_output=True,
            )
            if proc.returncode == 0:
                print("Copied to clipboard.")
            else:
                print("WARNING: clipboard copy failed.", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: clipboard copy error: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
