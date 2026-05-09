#!/usr/bin/env python3
"""
Auto Dev One-Shot Runner
GitHub Actions에서 한 번만 실행되는 자동 개발 스크립트.
무한루프 없음 — 태스크 1개 처리 후 종료.

환경변수:
  GOAL             : 개발 목표 (필수, MOCK_MODE일 때는 선택)
  MODE             : 실행 모드 (default: standard)
  OPENAI_API_KEY   : OpenAI API 키
  ANTHROPIC_API_KEY: Anthropic API 키
  OPENAI_MODEL     : OpenAI 모델 (default: gpt-4o)
  ANTHROPIC_MODEL  : Anthropic 모델 (default: claude-3-5-sonnet-20241022)
  MOCK_MODE        : 1/true → 실제 API 호출 없이 dry-run 검증
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
MOCK_MODE: bool = os.environ.get("MOCK_MODE", "").lower() in ("1", "true", "yes")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_EXTENSIONS = {".py", ".md", ".yaml", ".yml", ".json", ".txt", ".html", ".css", ".js"}

# 절대 수정하지 않을 경로 (접두사 매칭)
DENIED_PATH_PREFIXES = [
    ".github/workflows/",
    "scripts/run_auto_dev_once.py",
    ".env",
]

# ── 로그 ────────────────────────────────────────────────────────────────────

_SECTION_BAR = "═" * 56


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def log_section(tag: str, title: str = "") -> None:
    """섹션 구분 헤더를 출력합니다."""
    header = f"[{tag}]" + (f" {title}" if title else "")
    print(f"\n{_SECTION_BAR}", flush=True)
    print(header, flush=True)
    print(_SECTION_BAR, flush=True)


def fail(msg: str, next_action: str = "") -> None:
    log(f"ERROR: {msg}")
    if next_action:
        log(f"다음 행동: {next_action}")
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

# 패치 방식(search/replace)과 전체 파일 교체 방식을 모두 지원합니다.
# 단순 문구 수정은 반드시 "patch" 모드를 사용하도록 유도합니다.
_SYSTEM_PROMPT = """\
You are an AI software developer. Given a development goal and project context,
generate minimal, focused code changes to achieve the goal.

CRITICAL RULES:
- Make the SMALLEST change necessary. Do NOT rewrite entire files for simple changes.
- For simple text/string changes (UI labels, messages, captions, docstrings):
  ALWAYS use "patch" mode with search/replace pairs.
- For structural or logic changes that require broader edits: use "full" mode.
- Do NOT modify workflow files (.github/workflows/), .env, or security-related files.
- Python code must be syntactically valid.
- All paths must be relative to the repository root (no leading slash).
- If no code change is needed, return: {"explanation": "no change needed", "files": []}

Return ONLY a valid JSON object. Two supported formats:

FORMAT A — patch mode (PREFERRED for simple/text changes):
{
  "explanation": "brief description of changes",
  "files": [
    {
      "path": "relative/path/from/repo/root",
      "mode": "patch",
      "patches": [
        {"search": "exact verbatim text to find", "replace": "new text"}
      ]
    }
  ]
}

FORMAT B — full mode (ONLY for structural changes that cannot be expressed as patches):
{
  "explanation": "brief description of changes",
  "files": [
    {
      "path": "relative/path/from/repo/root",
      "mode": "full",
      "content": "complete new file content as a string"
    }
  ]
}

You may mix modes across different files in the same response.
When in doubt, use patch mode.
"""


def _parse_json_response(raw: str) -> dict:
    """AI 응답에서 JSON을 추출합니다 (코드 블록 처리 포함).

    잘린 출력, 미닫힌 따옴표, 잘못된 JSON을 각각 구분해서 오류를 냅니다.
    """
    raw = raw.strip()
    # 코드 블록 안의 JSON 추출
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if m:
        raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        # 오류 원인 분류
        if raw.endswith('"') or raw.endswith("'"):
            raise ValueError(
                "AI 응답이 미닫힌 문자열로 끝남 (max_tokens 초과로 잘린 출력 가능성)"
            ) from exc
        if len(raw) > 3900:
            raise ValueError(
                f"AI 응답이 최대 토큰에서 잘린 것으로 추정됨 ({len(raw)} chars)"
            ) from exc
        raise ValueError(f"잘못된 JSON 형식: {exc}") from exc


def call_openai(goal: str, context: str) -> dict:
    import openai  # noqa: PLC0415

    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    user_msg = f"**개발 목표:** {goal}\n\n**프로젝트 컨텍스트:**\n{context}"
    log(f"사용 모델: {OPENAI_MODEL}")
    log("OpenAI API 호출 중...")

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
    raw = response.choices[0].message.content
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"OpenAI 응답 JSON 파싱 실패: {exc}\n응답 미리보기: {raw[:200]}"
        ) from exc


def call_anthropic(goal: str, context: str) -> dict:
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    user_msg = f"**개발 목표:** {goal}\n\n**프로젝트 컨텍스트:**\n{context}"
    log(f"사용 모델: {ANTHROPIC_MODEL}")
    log("Anthropic API 호출 중...")

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
    fail(
        "OPENAI_API_KEY 또는 ANTHROPIC_API_KEY가 설정되지 않았습니다.",
        "GitHub Settings > Secrets > Actions 에서 API Key를 등록하세요.",
    )


# ── 안전성 검증 ──────────────────────────────────────────────────────────────

def is_allowed_path(rel_path: str) -> bool:
    """변경이 허용된 경로인지 확인합니다."""
    p = Path(rel_path)
    if p.suffix not in ALLOWED_EXTENSIONS:
        log(f"  거부: 허용되지 않는 확장자 ({p.suffix})")
        return False
    for denied in DENIED_PATH_PREFIXES:
        if rel_path.startswith(denied) or rel_path == denied:
            log(f"  거부: 보호된 경로 ({rel_path})")
            return False
    # 상위 디렉토리 탈출 방지
    try:
        resolved = (PROJECT_ROOT / rel_path).resolve()
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        log(f"  거부: 경로 탈출 시도 차단 ({rel_path})")
        return False
    return True


def _classify_syntax_error(err_msg: str) -> str:
    """py_compile 오류를 원인 유형별로 분류합니다."""
    msg_lower = err_msg.lower()
    if "unterminated string literal" in msg_lower or "eol while scanning string" in msg_lower:
        return "잘린 문자열 / 미닫힌 따옴표 (unterminated string literal) — AI 출력이 중간에 잘렸을 가능성 높음"
    if "unexpected eof" in msg_lower or "unexpected end" in msg_lower:
        return "파일 내용이 중간에 잘림 (unexpected EOF) — max_tokens 한도 도달 가능성"
    if "invalid syntax" in msg_lower:
        return "일반 Python 문법 오류 (invalid syntax)"
    if "indentation" in msg_lower:
        return "들여쓰기 오류 (IndentationError)"
    return f"Python 문법 오류: {err_msg}"


def validate_python_syntax(content: str, label: str) -> tuple[bool, str]:
    """Python 파일 문법을 임시 파일로 검증합니다.

    실패 시 실제 파일에 내용을 쓰지 않습니다.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        py_compile.compile(tmp_path, doraise=True)
        return True, ""
    except py_compile.PyCompileError as exc:
        return False, _classify_syntax_error(str(exc))
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ── 파일 적용 ────────────────────────────────────────────────────────────────

def _apply_patches(existing_content: str, patches: list[dict], label: str) -> tuple[bool, str]:
    """search/replace 패치 목록을 순서대로 적용합니다.

    반환값: (성공 여부, 결과 내용 또는 오류 메시지)
    """
    result = existing_content
    for i, patch in enumerate(patches, start=1):
        search = patch.get("search", "")
        replace = patch.get("replace", "")
        if not search:
            log(f"  패치 #{i}: search 텍스트가 비어있어 건너뜁니다.")
            continue
        if search not in result:
            return (
                False,
                f"패치 #{i}: search 텍스트를 파일에서 찾을 수 없습니다.\n"
                f"    검색어(앞 80자): {search[:80]!r}",
            )
        result = result.replace(search, replace, 1)
        log(f"  패치 #{i} 적용: {search[:50]!r} → {replace[:50]!r}")
    return True, result


def apply_changes(files: list[dict]) -> list[str]:
    """AI가 제안한 파일 변경을 적용합니다. 적용된 파일의 상대 경로 목록 반환."""
    changed: list[str] = []
    rejected_reasons: list[str] = []

    for entry in files:
        rel_path = (entry.get("path") or "").strip()
        # "mode" 미지정 시 이전 버전 호환을 위해 "full"로 처리
        mode = entry.get("mode", "full")

        if not rel_path:
            log("경로가 빈 항목을 건너뜁니다.")
            rejected_reasons.append("경로가 없는 항목")
            continue

        log(f"검토 중: {rel_path} (mode={mode})")

        if not is_allowed_path(rel_path):
            rejected_reasons.append(f"{rel_path}: 보호된 경로 또는 허용되지 않는 확장자")
            continue

        target = PROJECT_ROOT / rel_path

        if mode == "patch":
            patches = entry.get("patches", [])
            if not patches:
                log("  거부: patches 목록이 비어있습니다.")
                rejected_reasons.append(f"{rel_path}: patches 목록이 비어있음")
                continue
            if not target.exists():
                log(f"  거부: 패치 대상 파일이 존재하지 않습니다 ({rel_path})")
                rejected_reasons.append(f"{rel_path}: 파일이 없어 패치 불가")
                continue
            existing = target.read_text(encoding="utf-8")
            ok, result = _apply_patches(existing, patches, rel_path)
            if not ok:
                log(f"  거부: {result}")
                rejected_reasons.append(f"{rel_path}: 패치 실패 — {result}")
                continue
            new_content = result
            if rel_path.endswith(".py"):
                syntax_ok, err = validate_python_syntax(new_content, rel_path)
                if not syntax_ok:
                    log("  거부: 패치 후 문법 검증 실패")
                    log(f"    원인 분류: {err}")
                    log("    실제 파일은 수정되지 않았습니다.")
                    rejected_reasons.append(f"{rel_path}: 패치 후 문법검증 실패 ({err})")
                    continue
                log("  문법 검증 통과 (patch)")

        else:
            # full 모드 — 이전 버전 호환: "content" 키가 없으면 거부
            new_content = entry.get("content", "")
            if not new_content:
                log("  거부: content가 비어있습니다.")
                rejected_reasons.append(f"{rel_path}: content가 비어있음")
                continue
            if rel_path.endswith(".py"):
                syntax_ok, err = validate_python_syntax(new_content, rel_path)
                if not syntax_ok:
                    log("  거부: AI 수정안 문법검증 실패")
                    log(f"    원인 분류: {err}")
                    log("    실제 파일은 수정되지 않았습니다.")
                    rejected_reasons.append(f"{rel_path}: AI 수정안 문법검증 실패 ({err})")
                    continue
                log("  문법 검증 통과 (full)")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content, encoding="utf-8")
        log(f"  적용 완료: {rel_path}")
        changed.append(rel_path)

    if not changed and rejected_reasons:
        log("─── 거부 사유 요약 ──────────────────────────────────────────────")
        for reason in rejected_reasons:
            log(f"  • {reason}")
        log("──────────────────────────────────────────────────────────────────")

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

    log(f"관련 테스트 실행: {[Path(t).name for t in related]}")
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
        # 실패한 테스트 파일 출력
        for line in result.stdout.splitlines():
            if "FAILED" in line:
                log(f"  실패: {line.strip()}")
        log("테스트 실패.")
        return False

    log("테스트 통과.")
    return True


# ── 메인 ────────────────────────────────────────────────────────────────────

def main() -> None:

    # ── [PRECHECK] ──────────────────────────────────────────────────────────
    log_section("PRECHECK", "사전 점검")
    log(f"목표: {GOAL!r}")
    log(f"모드: {MODE!r}")
    if MOCK_MODE:
        log("MOCK_MODE: 실제 API 호출 없이 dry-run으로 실행합니다.")

    preflight_ok = True

    # GOAL 검사
    if not GOAL and not MOCK_MODE:
        log("ERROR: GOAL 환경변수가 설정되지 않았습니다.")
        preflight_ok = False

    # API Key 검사 (MOCK_MODE가 아닐 때만)
    if not MOCK_MODE:
        if not OPENAI_API_KEY and not ANTHROPIC_API_KEY:
            log("ERROR: OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 중 하나가 필요합니다.")
            log("  → GitHub Settings > Secrets > Actions 에서 등록하세요.")
            preflight_ok = False
        else:
            if OPENAI_API_KEY:
                log("✓ OPENAI_API_KEY 설정됨")
            if ANTHROPIC_API_KEY:
                log("✓ ANTHROPIC_API_KEY 설정됨")

    # 핵심 파일 존재 확인 (경고만, 실패 아님)
    for rel_check in ["TASKS.md", "dashboard/streamlit_app.py"]:
        p = PROJECT_ROOT / rel_check
        if p.exists():
            log(f"✓ {rel_check}")
        else:
            log(f"⚠ WARN: {rel_check} 없음 (선택적)")

    if not preflight_ok:
        log_section("RESULT", "FAILED")
        log("다음 행동: 위 사전 점검 오류를 해결 후 재실행하세요.")
        sys.exit(1)

    log("✅ 사전 점검 통과")

    effective_goal = GOAL or "[MOCK] dry-run test goal"

    # 1. TASKS.md에 목표 추가
    add_goal_to_tasks(effective_goal)

    # 2. 프로젝트 컨텍스트 수집
    log("프로젝트 컨텍스트 수집 중...")
    context = get_project_context()
    log(f"컨텍스트 수집 완료 ({len(context)} chars)")

    # MOCK_MODE dry-run: 실제 API 없이 단계별 검증 후 종료
    if MOCK_MODE:
        log("✓ 컨텍스트 수집 검증 완료.")
        log("✓ AI 응답 파싱 전 단계: _parse_json_response() 담당")
        log("✓ 적용 검증 로직: is_allowed_path() → validate_python_syntax() 순서")
        log_section("RESULT", "SUCCESS (MOCK DRY-RUN)")
        log("다음 행동: MOCK_MODE를 해제하고 실제 GOAL과 API Key로 실행하세요.")
        sys.exit(0)

    # ── [AI] ────────────────────────────────────────────────────────────────
    log_section("AI", "AI 코드 변경 생성")

    # JSON 파싱 실패 시 1회 재시도
    ai_result = None
    for _attempt in range(2):
        try:
            ai_result = get_ai_changes(effective_goal, context)
            break
        except ValueError as exc:
            if _attempt == 0:
                log("[AI] JSON parse failed. retrying once.")
                continue
            log(f"ERROR: AI 응답 파싱 실패 (2회 시도): {exc}")
            log_section("RESULT", "FAILED")
            log("다음 행동: 모델 변경(OPENAI_MODEL/ANTHROPIC_MODEL) 또는 GOAL 단순화 후 재실행하세요.")
            sys.exit(1)
        except Exception as exc:
            log(f"ERROR: AI API 호출 실패 — {exc}")
            log_section("RESULT", "FAILED")
            log("다음 행동: API Key 유효성 및 네트워크 상태를 확인하세요.")
            sys.exit(1)

    explanation = ai_result.get("explanation", "")
    files = ai_result.get("files", [])
    log(f"AI 응답: {explanation}")
    modes_used = {f.get("mode", "full") for f in files}
    log(f"응답 형식: {', '.join(sorted(modes_used)) if modes_used else 'none'}")
    log(f"수정 대상 파일 수: {len(files)}")

    if not files:
        log("변경할 파일이 없습니다.")
        log_section("RESULT", "SUCCESS")
        log("다음 행동: AI가 변경이 필요 없다고 판단했습니다. GOAL을 더 구체적으로 작성해 재실행하세요.")
        sys.exit(0)

    # ── [VALIDATION] ────────────────────────────────────────────────────────
    log_section("VALIDATION", "파일 검증 및 적용")

    changed = apply_changes(files)

    if not changed:
        log("━━━ AI 수정안이 문법검증을 통과하지 못함 ━━━")
        log("원인: AI가 생성한 파일 내용이 모두 검증에 실패했습니다.")
        log("원본 파일은 변경되지 않았습니다.")
        log_section("RESULT", "FAILED")
        log("다음 행동: 위의 '거부 사유 요약'을 확인하고 GOAL을 구체화하거나 재실행하세요.")
        log("  검색 키워드: '거부 사유 요약' 또는 'AI 수정안 문법검증 실패'")
        sys.exit(1)

    # 관련 테스트 실행
    test_ok = run_related_tests(changed)
    if not test_ok:
        log_section("RESULT", "FAILED")
        log("다음 행동: 테스트 실패 파일을 확인하고 변경 내용을 검토하세요.")
        sys.exit(1)

    log_section("RESULT", "SUCCESS")
    log(f"변경된 파일: {changed}")
    log("다음 행동: GitHub Actions [GIT] 섹션에서 생성된 PR을 확인하고 검토 후 Merge 하세요.")
    sys.exit(0)


if __name__ == "__main__":
    main()
