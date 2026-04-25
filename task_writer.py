"""TASKS.md 생성·추가·중복 방지 모듈.

외부 의존성: 없음 (detect_code_files / summarize_codebase는 호출자가 주입).
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Callable


# ─── 상수 ────────────────────────────────────────────────────────────────────

TASK_PRIORITY_GUIDANCE = """태스크 우선순위 규칙:
- TASK-01이 1순위다.
- 실제 데이터/실데이터 연결 또는 입력 원천 확보를 먼저 둔다.
- 그다음 프론트엔드 MVP를 만든다.
- 그다음 오류 없이 동작하도록 예외처리·빈상태·로딩상태를 정리한다.
- 그다음 테스트/회귀 방지를 추가한다.
- 고도화/정리/관측성은 후순위다.
- TASK 번호는 우선순위 순서대로 증가해야 한다.
"""

TASK_SYSTEM_RULES = """## 공통 작업 원칙

### 0. 목표
가장 빠르게 사용자가 실제로 사용가능한 MVP를 만든다.

### 1. 구현 원칙
- 기존 구조를 최대한 유지한다.
- 최소 변경으로 구현한다.
- 단, 코드 효율이 2배 이상 좋아지는 경우 토큰 소모 2배까지는 허용한다.
- 고도화, 리팩토링, 호환성 동기화는 최하위 우선순위로 둔다.
- 우선 지원 기준은 Windows와 Android로 한정한다.
- macOS, iOS, Linux, 전체 브라우저 호환성은 후순위로 둔다.

### 2. 설명 원칙
- 비개발자도 이해할 수 있게 설명한다.
- 최대한 짧고 간단하게 설명한다.
- 이유와 원인은 최소화한다.
- 결과, 해야 할 일, 실행 방법, 검증 방법 중심으로 작성한다.
"""

AUTO_DEV_QUEUE_HEADING = "### Auto Dev Queue"


# ─── 내부 파일 쓰기 ───────────────────────────────────────────────────────────

def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    rel = str(path.relative_to(path.parent.parent)).replace("\\", "/")
    print(f"  [OK] {rel}")


# ─── TASK_SYSTEM_RULES 보장 ───────────────────────────────────────────────────

def ensure_task_system_rules(text: str) -> str:
    """TASKS.md 텍스트에 TASK_SYSTEM_RULES 블록이 없으면 삽입 (멱등)."""
    if TASK_SYSTEM_RULES in text:
        return text

    block = TASK_SYSTEM_RULES.strip()
    active_match = re.search(r"^## Active\s*$", text, flags=re.MULTILINE)

    if active_match is None:
        base = text.rstrip()
        parts = [base] if base else []
        parts.append(block)
        return "\n\n".join(parts).rstrip() + "\n"

    insert_at = active_match.start()
    before_active = text[:insert_at].rstrip()
    after_active = text[insert_at:].lstrip("\n")
    rebuilt_before = "\n\n".join(part for part in [before_active, block] if part).rstrip()
    return f"{rebuilt_before}\n\n{after_active}".rstrip() + "\n"


def ensure_task_system_rules_in_file(tasks_path: Path) -> None:
    original = tasks_path.read_text(encoding="utf-8")
    updated = ensure_task_system_rules(original)
    if updated != original:
        tasks_path.write_text(updated, encoding="utf-8")


# ─── 프롬프트 빌더 ────────────────────────────────────────────────────────────

def build_code_analysis_prompt(base_dir: Path, prd_version: str, summary: str) -> str:
    return (
        f"아래는 기존 프로젝트 '{base_dir.name}'의 구조 요약이다. 전체 파일 원문이 아니라 요약만 제공된다.\n\n"
        f"{summary}\n\n"
        f"이 요약만 바탕으로 TASKS.md를 생성해라. 목적은 기존 기능 재생성이 아니라 안정화/예외처리/테스트/보안/문서화 태스크 도출이다.\n\n"
        f"{TASK_PRIORITY_GUIDANCE}\n"
        f"[금지]\n"
        f"- 기본 구조 생성 금지\n"
        f"- 핵심 기능 1차 구현 금지\n"
        f"- UI 생성 금지\n"
        f"- 이미 존재하는 파일 재구현 금지\n\n"
        f"[필수 규칙]\n"
        f"- 기존 코드의 안정화, 예외 처리, 회귀 방지, 테스트 보강, 보안 점검, 문서화만 태스크로 만든다\n"
        f"- monitor.py 같은 대형 파일은 요약만 기준으로 판단한다\n"
        f"- 태스크는 5~7개\n"
        f"- 각 태스크는 구체적이고 실행 가능해야 한다\n"
        f"- 각 태스크는 수락 기준 3개 이상 포함한다\n"
        f"- 파일 헤더는 '# TASKS.md — <서비스명> / Based on: PRD {prd_version}' 형식으로 작성한다\n"
        f"- 아래 공통 작업 원칙 블록을 본문에 정확히 1회 포함한다\n\n"
        f"{TASK_SYSTEM_RULES}\n\n"
        f"- 파일 마지막에는 반드시 아래 Active 섹션을 포함한다\n\n"
        f"## Active\n\n### Auto Dev Queue\n\n"
        f"- [ ] [TASK-01] 태스크 제목\n"
        f"- [ ] [TASK-02] 태스크 제목\n"
        f"...\n"
    )


# ─── 렌더러 ──────────────────────────────────────────────────────────────────

def render_existing_safe_tasks(prd: dict, prd_version: str, summary: str) -> str:
    summary_lower = summary.lower()
    summary_lines = [line for line in summary.splitlines() if line.startswith("- file: ")][:5]
    focus = "\n".join(summary_lines) or "- file: existing codebase"
    context_notes: list[str] = []
    if "monitor.py" in summary_lower:
        context_notes.append("- monitor.py의 스케줄 실행, 상태 집계, 실패 분기를 우선 점검한다.")
    if "config.py" in summary_lower:
        context_notes.append("- config.py의 환경변수 로딩, 기본값, 잘못된 설정 입력 처리를 점검한다.")
    if "mailer.py" in summary_lower:
        context_notes.append("- mailer.py의 메일 전송 실패, 재시도, 예외 메시지 노출 범위를 점검한다.")
    if "fetchers/" in summary_lower or "fetchers\\" in summary_lower:
        context_notes.append("- fetchers/ 하위 수집기의 파싱 실패, 빈 응답, 외부 API 오류 처리를 점검한다.")
    context_block = "\n".join(context_notes)
    if context_block:
        context_block = f"## Project Context\n\n{context_block}\n\n"

    return (
        f"# TASKS.md — {prd['service_name']}\n\n"
        f"> Based on: PRD {prd_version}\n"
        f"> Status: Existing Safe Fallback\n"
        f"> Last Updated: {date.today()}\n\n"
        f"{TASK_SYSTEM_RULES}\n\n"
        f"기존 코드 프로젝트 분석 실패로 인해 구조 요약 기반 안전 태스크를 생성함.\n"
        f"이 폴백도 우선순위는 실제 데이터/입력 연결 → 프론트엔드 MVP → 오류 없이 동작 → 테스트/회귀 방지 순서로 맞춘다.\n\n"
        f"## Analysis Summary\n\n{focus}\n\n"
        f"{context_block}"
        f"## TASK-01 — Real data and input baseline\n\n"
        f"### 작업 내용\n"
        f"  - 실제 데이터 소스와 입력 경로를 먼저 확인한다\n"
        f"  - 샘플 데이터와 실데이터 중 무엇을 먼저 연결할지 정리한다\n"
        f"  - 데이터 유무에 따른 빈상태와 실패 상태를 문서화한다\n"
        f"  - 입력 검증과 최소 필수 필드를 고정한다\n\n"
        f"### 수락 기준 (Acceptance Criteria)\n"
        f"  - [ ] 실제 데이터 또는 샘플 데이터 경로가 1개 이상 정리된다\n"
        f"  - [ ] 빈 데이터와 잘못된 입력의 처리 기준이 적힌다\n"
        f"  - [ ] 입력 검증 규칙이 명시된다\n\n"
        f"### 검증 방법\n"
        f"데이터 소스 확인 + 빈 입력/잘못된 입력 재현\n\n"
        f"---\n\n"
        f"## TASK-02 — Frontend MVP shell\n\n"
        f"### 작업 내용\n"
        f"  - 사용자가 바로 볼 수 있는 첫 화면을 만든다\n"
        f"  - 핵심 입력, 실행, 결과 표시만 남긴 MVP 화면으로 정리한다\n"
        f"  - 로딩 상태와 빈 상태를 화면에서 확인할 수 있게 만든다\n"
        f"  - 화면에서 바로 실행 가능한 최소 흐름을 고정한다\n\n"
        f"### 수락 기준 (Acceptance Criteria)\n"
        f"  - [ ] 최소 1개 핵심 화면이 열린다\n"
        f"  - [ ] 빈 상태와 로딩 상태가 보인다\n"
        f"  - [ ] 핵심 실행 버튼이나 입력 흐름이 동작한다\n\n"
        f"### 검증 방법\n"
        f"브라우저에서 화면 확인 + 기본 흐름 클릭 테스트\n\n"
        f"---\n\n"
        f"## TASK-03 — Error-free operation and exception handling\n\n"
        f"### 작업 내용\n"
        f"  - 입력 오류, 데이터 없음, 외부 실패를 앱이 죽지 않게 처리한다\n"
        f"  - 사용자가 다음 행동을 알 수 있는 안내를 추가한다\n"
        f"  - 불필요한 예외 스택 노출을 줄인다\n"
        f"  - 오류 발생 시 복구 가능한 흐름을 만든다\n\n"
        f"### 수락 기준 (Acceptance Criteria)\n"
        f"  - [ ] 오류 상황에서도 앱이 종료되지 않는다\n"
        f"  - [ ] 사용자가 이해할 수 있는 오류 메시지가 나온다\n"
        f"  - [ ] 예외 상황에서 다음 동작이 안내된다\n\n"
        f"### 검증 방법\n"
        f"오류 입력 재현 + 예외 메시지 확인\n\n"
        f"---\n\n"
        f"## TASK-04 — Regression coverage\n\n"
        f"### 작업 내용\n"
        f"  - 정상/실패/경계 케이스 테스트를 추가한다\n"
        f"  - 실데이터/샘플 데이터 기준 회귀를 막는다\n"
        f"  - 핵심 흐름의 자동 검증 명령을 고정한다\n"
        f"  - 변경 시 바로 깨지는 지점을 테스트로 묶는다\n\n"
        f"### 수락 기준 (Acceptance Criteria)\n"
        f"  - [ ] 정상 경로 테스트가 통과한다\n"
        f"  - [ ] 실패 경로 테스트가 통과한다\n"
        f"  - [ ] 경계값 또는 회귀 테스트가 통과한다\n\n"
        f"### 검증 방법\n"
        f"python -m pytest --tb=short -q\n\n"
        f"---\n\n"
        f"## TASK-05 — Observability and safe cleanup\n\n"
        f"### 작업 내용\n"
        f"  - 동작 변경 없이 중복 분기와 취약한 분기를 정리한다\n"
        f"  - 로그와 문서를 맞춘다\n"
        f"  - 운영 확인 포인트를 최소한으로 정리한다\n\n"
        f"### 수락 기준 (Acceptance Criteria)\n"
        f"  - [ ] 기존 핵심 흐름이 유지된다\n"
        f"  - [ ] 새 회귀가 발생하지 않는다\n"
        f"  - [ ] 주요 상태를 확인할 수 있다\n\n"
        f"### 검증 방법\n"
        f"기존 실행 경로 재검증\n\n"
        f"## Active\n\n"
        f"### Auto Dev Queue\n\n"
        f"- [ ] [TASK-01] Real data and input baseline\n"
        f"- [ ] [TASK-02] Frontend MVP shell\n"
        f"- [ ] [TASK-03] Error-free operation and exception handling\n"
        f"- [ ] [TASK-04] Regression coverage\n"
        f"- [ ] [TASK-05] Observability and safe cleanup\n"
    )


def render_active_task_queue(tasks: list[dict]) -> str:
    lines = ["## Active", "", AUTO_DEV_QUEUE_HEADING, ""]
    for task in tasks:
        lines.append(f"- [ ] [{task['id']}] {task['title']}")
    return "\n".join(lines)


def render_tasks(prd: dict, der: dict, prd_version: str) -> str:
    sections = []
    for task in der["tasks"]:
        dep = ", ".join(task["depends_on"]) if task["depends_on"] else "없음"
        subtasks = "\n".join(f"  - {s}" for s in task["subtasks"])
        ac = "\n".join(f"  - [ ] {c}" for c in task["acceptance_criteria"])
        sections.append(f"""## {task['id']} — {task['title']}

**스킬:** `{task['skill_tag']}`
**의존성:** {dep}
**예상 소요:** {task['effort']}

### 작업 내용
{subtasks}

### 수락 기준 (Acceptance Criteria)
{ac}

### 검증 방법
{task['verification']}

---""")

    active_queue = render_active_task_queue(der["tasks"])
    body_sections = [
        f"""# TASKS.md — {prd['service_name']}

> Based on: PRD {prd_version}
> Status: Generated
> Last Updated: {date.today()}""",
        TASK_SYSTEM_RULES,
        "\n\n".join(sections),
        active_queue,
    ]
    return ensure_task_system_rules(
        "\n\n".join(section.strip() for section in body_sections if section.strip())
    )


def render_appended_task_template(task: dict, next_task_id: str) -> str:
    depends_on = ", ".join(task.get("depends_on") or []) or "없음"
    verification = task.get("verification", "실행 후 결과를 확인한다.")
    original_id = task.get("id", "-")
    title = task.get("title", "신규 태스크")
    return "\n".join(
        [
            f"- [ ] [{next_task_id}] {title}",
            f"  - 원본 태스크: {original_id}",
            f"  - 의존성: {depends_on}",
            f"  - 검증: {verification}",
        ]
    )


# ─── 추가·쓰기 로직 (append 방식·중복 방지) ──────────────────────────────────

def find_markdown_section_bounds(text: str, heading: str, level: int = 2) -> tuple[int, int] | None:
    pattern = rf"^{re.escape('#' * level)} {re.escape(heading)}\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return None
    start = match.end()
    next_section = re.search(rf"^{re.escape('#' * level)}\s+", text[start:], flags=re.MULTILINE)
    end = start + next_section.start() if next_section else len(text)
    return start, end


def get_next_task_id(tasks_text: str) -> str:
    """기존 TASKS.md에서 최대 번호를 읽어 +1 반환 — 중복 ID 방지."""
    numbers = [int(num) for num in re.findall(r"\bTASK-(\d+)\b", tasks_text)]
    return f"TASK-{max(numbers, default=0) + 1:02d}"


def append_task_to_tasks_md(tasks_path: Path, task: dict) -> str:
    """기존 TASKS.md에 새 태스크를 append. 중복 방지 ID를 자동 부여."""
    text = tasks_path.read_text(encoding="utf-8")
    text = ensure_task_system_rules(text)
    next_task_id = get_next_task_id(text)
    appended_task = render_appended_task_template(task, next_task_id)
    active_bounds = find_markdown_section_bounds(text, "Active")

    if active_bounds is None:
        base = text.rstrip()
        sections = [base] if base else []
        sections.extend(["## Active", "", AUTO_DEV_QUEUE_HEADING, "", appended_task])
        updated = "\n\n".join(sections).rstrip() + "\n"
    else:
        start, end = active_bounds
        active_body = text[start:end].strip("\n")
        if AUTO_DEV_QUEUE_HEADING not in active_body:
            active_body = (
                f"{active_body}\n\n{AUTO_DEV_QUEUE_HEADING}".strip()
                if active_body
                else AUTO_DEV_QUEUE_HEADING
            )
        active_body = f"{active_body}\n\n{appended_task}".strip() + "\n"
        updated = text[:start] + "\n\n" + active_body + text[end:]

    tasks_path.write_text(updated, encoding="utf-8")
    print(f"  [OK] TASKS.md (append {next_task_id})")
    return next_task_id


def write_tasks_document(base_dir: Path, prd: dict, der: dict, prd_version: str) -> str | None:
    """TASKS.md가 없으면 새로 생성, 있으면 append."""
    tasks_path = base_dir / "TASKS.md"
    if tasks_path.exists() and der.get("tasks"):
        return append_task_to_tasks_md(tasks_path, der["tasks"][0])

    _write_file(tasks_path, render_tasks(prd, der, prd_version))
    return None


# ─── 오케스트레이터 ───────────────────────────────────────────────────────────
# detect_code_files / summarize_codebase를 호출자가 주입 → 순환 import 없음.

def write_tasks_with_fallback(
    base_dir: Path,
    prd: dict,
    der: dict,
    prd_version: str,
    detect_code_files_fn: Callable[[Path], list[Path]],
    summarize_codebase_fn: Callable[..., str],
) -> str | None:
    code_files = detect_code_files_fn(base_dir)
    if code_files:
        summary = summarize_codebase_fn(base_dir, code_files)
        tasks_path = base_dir / "TASKS.md"
        _write_file(tasks_path, render_existing_safe_tasks(prd, prd_version, summary))
        return None
    return write_tasks_document(base_dir, prd, der, prd_version)


def generate_tasks_via_claude_cli(
    base_dir: Path,
    prd_version: str,
    detect_code_files_fn: Callable[[Path], list[Path]],
    summarize_codebase_fn: Callable[..., str],
) -> bool:
    """Claude CLI로 PRD.md를 읽어 TASKS.md를 직접 생성. 성공하면 True."""
    import subprocess

    prd_path = base_dir / "PRD.md"
    if not prd_path.exists():
        return False

    code_files = detect_code_files_fn(base_dir)
    if code_files:
        summary = summarize_codebase_fn(base_dir, code_files)
        prompt = build_code_analysis_prompt(base_dir, prd_version, summary)
    else:
        prompt = (
            f"PRD.md를 읽고, 아래 조건을 지켜서 TASKS.md를 생성해라.\n\n"
            f"{TASK_PRIORITY_GUIDANCE}\n"
            f"[TASKS.md 형식 규칙]\n"
            f"- 헤더: # TASKS.md — <서비스명> / Based on: PRD {prd_version}\n"
            f"- 태스크 5~7개, 각 TASK에 수락 기준 3개 이상\n"
            f"- 예외처리·빈상태·로딩상태 반드시 반영\n"
            f"- 아래 공통 작업 원칙 블록을 본문에 정확히 1회 포함:\n\n{TASK_SYSTEM_RULES}\n\n"
            f"- 파일 끝에 반드시 아래 Active 섹션 포함:\n"
            f"  ## Active\n\n  ### Auto Dev Queue\n\n  - [ ] [TASK-01] <제목>\n  - [ ] [TASK-02] <제목>\n  ...\n"
            f"- loop_runner.py가 인식하는 형식: '- [ ] [TASK-XX] 제목' (대소문자 구분 없음)"
        )

    try:
        subprocess.run(
            ["claude", "-p", prompt, "--dangerously-skip-permissions"],
            cwd=str(base_dir),
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
            errors="replace",
        )
        tasks_path = base_dir / "TASKS.md"
        if tasks_path.exists():
            ensure_task_system_rules_in_file(tasks_path)
            return True
        return False
    except FileNotFoundError:
        print("[경고] claude CLI를 찾을 수 없습니다. 템플릿으로 대체합니다.")
        return False
    except subprocess.TimeoutExpired:
        print("[경고] claude CLI 시간 초과. 템플릿으로 대체합니다.")
        return False
    except Exception as e:
        print(f"[경고] claude CLI 실패: {e}")
        return False
