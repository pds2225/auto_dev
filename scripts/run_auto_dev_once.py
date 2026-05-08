#!/usr/bin/env python3
"""
Auto Dev One-Shot Runner
GitHub Actions에서 한 번만 실행되는 자동 개발 스크립트.
무한루프 없음 — 태스크 1개 처리 후 종료.
"""
from __future__ import annotations

import json
import os
import py_compile
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ── 설정 ────────────────────────────────────────────────────────────────────

GOAL: str = os.environ.get("GOAL", "").strip()
MODE: str = os.environ.get("MODE", "standard").strip()
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "").strip()
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_MODEL: str = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_EXTENSIONS = {".py", ".md", ".yaml", ".yml", ".json", ".txt", ".html", ".css", ".js"}

# 절대 수정하지 않을 경로 (접두사 매칭)
DENIED_PATH_PREFIXES = [
    ".github/workflows/",
    "scripts/run_auto_dev_once.py",
    ".env",
]


# ── 로그 ────────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def fail(msg: str) -> None:
    log(f"ERROR: {msg}")
    sys.exit(1)


# ── TASKS.md 업데이트 ─────────────────────────────────────────────────────────

def add_goal_to_tasks(goal: str) -> None:
    """TASKS.md의 ## Active 섹션에 목표를 태스크로 추가합니다."""
    tasks_path = PROJECT_ROOT / "TASKS.md"
    if not tasks_path.exists():
        log("TASKS.md가 없습니다. 건너뜁니다.")
        return

    text = tasks_path.read_text(encoding="utf-8")
    match = re.search(r"^## Active\s*$", text, flags=re.MULTILINE)
    if not match:
        log("TASKS.md에 ## Active 섹션이 없습니다. 건너뜁니다.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d")
    new_task_line = f"\n- [ ] [AUTO] {goal} ({timestamp})"
    insert_pos = match.end()
    updated = text[:insert_pos] + new_task_line + text[insert_pos:]
    tasks_path.write_text(updated, encoding="utf-8")
    log(f"TASKS.md에 태스크 추가: {goal}")


# ── 프로젝트 컨텍스트 수집 ────────────────────────────────────────────────────

_SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv", ".mypy_cache"}


def get_project_context(max_files: int = 15, max_chars_per_file: int = 2500) -> str:
    """주요 Python 파일 내용을 수집해 AI에 전달할 컨텍스트 문자열을 만듭니다."""
    parts: list[str] = []

    py_files = sorted(
        p for p in PROJECT_ROOT.rglob("*.py")
        if not any(skip in p.parts for skip in _SKIP_DIRS)
    )[:max_files]

    for fpath in py_files:
        try:
            content = fpath.read_text(encoding="utf-8")[:max_chars_per_file]
            rel = fpath.relative_to(PROJECT_ROOT)
            parts.append(f"### {rel}\n```python\n{content}\n```")
        except Exception:
            pass

    return "\n\n".join(parts)


# ── AI 호출 ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an AI software developer. Given a development goal and project context,
generate minimal, focused code changes to achieve the goal.

Rules:
- Make the smallest change necessary to achieve the goal.
- Prefer modifying existing files over creating new ones.
- Return ONLY a valid JSON object with this exact structure:
  {
    "explanation": "brief description of changes",
    "files": [
      {
        "path": "relative/path/from/repo/root",
        "content": "complete new file content as a string"
      }
    ]
  }
- All paths must be relative to the repository root (no leading slash).
- Do NOT modify workflow files, .env, or security-related files.
- Python code must be syntactically valid.
- If no code change is needed, return: {"explanation": "no change needed", "files": []}
"""


def _parse_json_response(raw: str) -> dict:
    """AI 응답에서 JSON을 추출합니다 (코드 블록 처리 포함)."""
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if m:
        raw = m.group(1).strip()
    return json.loads(raw)


def call_openai(goal: str, context: str) -> dict:
    import openai  # noqa: PLC0415

    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    user_msg = f"**개발 목표:** {goal}\n\n**프로젝트 컨텍스트:**\n{context}"
    log(f"OpenAI API 호출 중 (model={OPENAI_MODEL})...")

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def call_anthropic(goal: str, context: str) -> dict:
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    user_msg = f"**개발 목표:** {goal}\n\n**프로젝트 컨텍스트:**\n{context}"
    log(f"Anthropic API 호출 중 (model={ANTHROPIC_MODEL})...")

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return _parse_json_response(response.content[0].text)


def get_ai_changes(goal: str, context: str) -> dict:
    """사용 가능한 AI API로 코드 변경안을 생성합니다."""
    if OPENAI_API_KEY:
        return call_openai(goal, context)
    if ANTHROPIC_API_KEY:
        return call_anthropic(goal, context)
    fail("OPENAI_API_KEY 또는 ANTHROPIC_API_KEY가 설정되지 않았습니다.")


# ── 안전성 검증 ──────────────────────────────────────────────────────────────

def is_allowed_path(rel_path: str) -> bool:
    """변경이 허용된 경로인지 확인합니다."""
    p = Path(rel_path)
    if p.suffix not in ALLOWED_EXTENSIONS:
        log(f"  허용되지 않는 확장자: {p.suffix}")
        return False
    for denied in DENIED_PATH_PREFIXES:
        if rel_path.startswith(denied) or rel_path == denied:
            log(f"  보호된 경로: {rel_path}")
            return False
    # 상위 디렉토리 탈출 방지
    try:
        resolved = (PROJECT_ROOT / rel_path).resolve()
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        log(f"  경로 탈출 시도 차단: {rel_path}")
        return False
    return True


def validate_python_syntax(content: str, label: str) -> tuple[bool, str]:
    """Python 파일 문법을 임시 파일로 검증합니다."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        py_compile.compile(tmp_path, doraise=True)
        return True, ""
    except py_compile.PyCompileError as exc:
        return False, str(exc)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ── 파일 적용 ────────────────────────────────────────────────────────────────

def apply_changes(files: list[dict]) -> list[str]:
    """AI가 제안한 파일 변경을 적용합니다. 적용된 파일의 상대 경로 목록 반환."""
    changed: list[str] = []

    for entry in files:
        rel_path = (entry.get("path") or "").strip()
        content = entry.get("content", "")

        if not rel_path:
            log("경로가 빈 항목을 건너뜁니다.")
            continue

        log(f"검토 중: {rel_path}")
        if not is_allowed_path(rel_path):
            continue

        if rel_path.endswith(".py"):
            ok, err = validate_python_syntax(content, rel_path)
            if not ok:
                log(f"  문법 오류 → 건너뜁니다: {err}")
                continue
            log("  문법 검증 통과")

        target = PROJECT_ROOT / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        log(f"  적용 완료: {rel_path}")
        changed.append(rel_path)

    return changed


# ── 관련 테스트 실행 ─────────────────────────────────────────────────────────

def run_related_tests(changed_files: list[str]) -> bool:
    """변경된 파일과 직접 연관된 테스트만 실행합니다. 전체 테스트는 실행하지 않습니다."""
    test_dir = PROJECT_ROOT / "tests"
    if not test_dir.exists():
        log("tests/ 디렉토리가 없습니다. 테스트를 건너뜁니다.")
        return True

    related: list[str] = []
    for rel in changed_files:
        stem = Path(rel).stem
        candidate = test_dir / f"test_{stem}.py"
        if candidate.exists():
            related.append(str(candidate))

    if not related:
        log("관련 테스트 파일이 없습니다. 테스트를 건너뜁니다.")
        return True

    log(f"관련 테스트 실행: {related}")
    result = subprocess.run(
        [sys.executable, "-m", "pytest"] + related + ["-v", "--tb=short", "-x"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        log("테스트 실패.")
        return False

    log("테스트 통과.")
    return True


# ── 메인 ────────────────────────────────────────────────────────────────────

def main() -> None:
    log(f"=== Auto Dev One-Shot 시작 ===")
    log(f"목표: {GOAL!r}")
    log(f"모드: {MODE!r}")

    if not GOAL:
        fail("GOAL 환경변수가 설정되지 않았습니다.")

    # 1. TASKS.md에 목표 추가
    add_goal_to_tasks(GOAL)

    # 2. 프로젝트 컨텍스트 수집
    log("프로젝트 컨텍스트 수집 중...")
    context = get_project_context()
    log(f"컨텍스트 수집 완료 ({len(context)} chars)")

    # 3. AI로 코드 변경안 생성
    try:
        ai_result = get_ai_changes(GOAL, context)
    except Exception as exc:
        fail(f"AI API 호출 실패: {exc}")

    explanation = ai_result.get("explanation", "")
    files = ai_result.get("files", [])
    log(f"AI 응답: {explanation}")
    log(f"변경 대상 파일 수: {len(files)}")

    if not files:
        log("변경할 파일이 없습니다. 완료.")
        sys.exit(0)

    # 4. 파일 적용
    changed = apply_changes(files)
    if not changed:
        log("적용된 파일이 없습니다. (모두 거부되거나 검증 실패)")
        sys.exit(1)

    # 5. 관련 테스트 실행
    test_ok = run_related_tests(changed)
    if not test_ok:
        fail("테스트 실패. 변경 내용을 확인하세요.")

    log(f"=== 완료. 변경된 파일: {changed} ===")
    sys.exit(0)


if __name__ == "__main__":
    main()
