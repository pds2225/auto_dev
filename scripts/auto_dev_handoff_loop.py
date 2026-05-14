#!/usr/bin/env python3
"""
auto_dev_handoff_loop.py
Claude ↔ Codex 파일 기반 왕복 루프 핸드오프 프롬프트 생성기.

사용법:
  python scripts/auto_dev_handoff_loop.py --repo D:\\walk --from claude --input D:\\walk\\claude_result.md [--copy]
  python scripts/auto_dev_handoff_loop.py --repo D:\\walk --from codex  --input D:\\walk\\codex_result.md  [--copy]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AUTO_DEV_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_FILES = [
    ".github/workflows/*.yml",
    "scripts/run_auto_dev_once.py",
    "scripts/auto_dev_queue.py",
    ".env",
    ".env.*",
    "AGENTS.md",
    "RULES.md",
]

_FORBIDDEN_BLOCK = "\n".join(f"  - {f}" for f in FORBIDDEN_FILES)


def _read_shared_claude_guidelines() -> str:
    shared = AUTO_DEV_ROOT / "CLAUDE.md"
    if not shared.exists():
        return ""
    return shared.read_text(encoding="utf-8", errors="replace").strip()


def _read_optional(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _summarize(text: str, max_lines: int = 30) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... (이하 {len(lines) - max_lines}줄 생략)"


def _build_codex_prompt(
    repo_root: Path,
    input_path: Path,
    input_content: str,
    tasks_summary: str,
    agents_summary: str,
) -> str:
    shared_rules = _read_shared_claude_guidelines()
    shared_block = f"""\
## 공통 작업 지침 (CLAUDE.md)
{shared_rules}

""" if shared_rules else ""
    return f"""\
# Codex 핸드오프 프롬프트 (Claude 결과 → Codex 작업)

## 작업 저장소
{repo_root}

## 입력 결과 파일
{input_path}

## Claude 결과 요약
{_summarize(input_content)}

## TASKS.md 요약
{tasks_summary or "(TASKS.md 없음 — 입력 파일 내용 기준으로 작업)"}

## AGENTS.md 규칙 요약
{_summarize(agents_summary, 20) if agents_summary else "(AGENTS.md 없음)"}

{shared_block}## Codex가 해야 할 일
1. 위 Claude 결과를 검토하고 저장소에 실제 변경을 구현한다.
2. 기존 구조를 최대한 유지하며 최소 변경만 수행한다.
3. 아래 파일은 절대 수정하지 않는다:
{_FORBIDDEN_BLOCK}
4. 변경 후 아래 검증 명령을 반드시 실행한다:
   python -m pytest tests/ -q
   python -m py_compile <수정한 파일>
5. 기능 추가·전면 재작성 금지. Claude가 지시한 범위 내에서만 작업한다.

## 최소 변경 원칙
- 요청된 기능 외 리팩터링·정리·주석 추가 금지.
- 기존 테스트가 깨지면 즉시 수정한다.

## 최종 보고 형식
1. 변경 파일 목록
2. 검증 명령 및 결과
3. 변경 내용 요약
4. 다음 Claude에게 넘길 요약 (파일로도 저장 권장: claude_result.md)
"""


def _build_claude_prompt(
    repo_root: Path,
    input_path: Path,
    input_content: str,
    tasks_summary: str,
    agents_summary: str,
) -> str:
    shared_rules = _read_shared_claude_guidelines()
    shared_block = f"""\
## 공통 작업 지침 (CLAUDE.md)
{shared_rules}

""" if shared_rules else ""
    return f"""\
# Claude 핸드오프 프롬프트 (Codex 결과 → Claude 리뷰/개선)

## 작업 저장소
{repo_root}

## 입력 결과 파일
{input_path}

## Codex 결과 요약
{_summarize(input_content)}

## TASKS.md 요약
{tasks_summary or "(TASKS.md 없음 — 입력 파일 내용 기준으로 검토)"}

## AGENTS.md 규칙 요약
{_summarize(agents_summary, 20) if agents_summary else "(AGENTS.md 없음)"}

{shared_block}## Claude가 해야 할 일
1. Codex가 구현한 결과를 리뷰하고 문제점을 파악한다.
2. 예외 처리·엣지 케이스·테스트 보강을 중심으로 개선한다.
3. 전면 재작성 금지. 구조 개선과 버그 수정만 수행한다.
4. 아래 파일은 절대 수정하지 않는다:
{_FORBIDDEN_BLOCK}
5. .claude/settings.local.json은 커밋 대상에서 제외한다.

## 검증 명령
python -m pytest tests/ -q

## 최종 보고 형식
1. 리뷰 결과 (문제점·개선점)
2. 변경 파일 목록
3. 검증 결과
4. 다음 Codex에게 넘길 요약 (파일로도 저장 권장: codex_result.md)
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claude ↔ Codex 핸드오프 프롬프트 생성")
    parser.add_argument("--repo", required=True, metavar="PATH", help="작업 저장소 경로")
    parser.add_argument(
        "--from", dest="source", required=True, choices=["claude", "codex"],
        help="입력 결과 출처 (claude 또는 codex)",
    )
    parser.add_argument("--input", required=True, metavar="FILE", help="결과 파일 경로")
    parser.add_argument("--copy", action="store_true", help="생성된 프롬프트를 Windows 클립보드에 복사")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo).resolve()
    input_path = Path(args.input).resolve()

    if not input_path.exists():
        print(f"ERROR: 입력 파일을 찾을 수 없습니다: {input_path}", file=sys.stderr)
        return 1

    input_content = input_path.read_text(encoding="utf-8", errors="replace")
    tasks_summary = _summarize(_read_optional(repo_root / "TASKS.md"), 20)
    agents_summary = _read_optional(repo_root / "AGENTS.md")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.source == "claude":
        prompt = _build_codex_prompt(repo_root, input_path, input_content, tasks_summary, agents_summary)
        out_file = repo_root / f"codex_handoff_{timestamp}.md"
    else:
        prompt = _build_claude_prompt(repo_root, input_path, input_content, tasks_summary, agents_summary)
        out_file = repo_root / f"claude_handoff_{timestamp}.md"

    out_file.write_text(prompt, encoding="utf-8")

    print(f"선택 repo  : {repo_root}")
    print(f"입력 파일  : {input_path}")
    print(f"출력 파일  : {out_file}")

    if args.copy:
        try:
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
