#!/usr/bin/env python3
"""
Auto Dev Queue Runner
TASKS.md의 큐에서 PENDING TASK를 하나씩 꺼내 처리하고 상태를 기록합니다.

운영 원칙:
- 1회 실행 시 PENDING TASK 1개만 처리
- 실패해도 전체 큐가 멈추지 않음 (다음 실행 시 다음 TASK 처리)
- 동일 TASK 최대 MAX_RETRIES(2)회까지만 재시도
- BLOCKED TASK는 자동 재시도하지 않음

환경변수:
  OPENAI_API_KEY   : OpenAI API 키
  ANTHROPIC_API_KEY: Anthropic API 키
  GH_TOKEN         : GitHub Token (PR 생성용)
  GITHUB_REPOSITORY: 저장소 경로 (owner/repo)
  MOCK_MODE        : 1/true → 실제 API 호출 없이 dry-run
  GITHUB_STEP_SUMMARY: GitHub Actions Step Summary 파일 경로
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── 설정 ────────────────────────────────────────────────────────────────────

OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "").strip()
GITHUB_REPOSITORY: str = os.environ.get("GITHUB_REPOSITORY", "").strip()
MOCK_MODE: bool = os.environ.get("MOCK_MODE", "").lower() in ("1", "true", "yes")
GITHUB_STEP_SUMMARY: str = os.environ.get("GITHUB_STEP_SUMMARY", "")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TASKS_FILE = PROJECT_ROOT / "TASKS.md"
STATE_FILE = PROJECT_ROOT / "auto_dev_state.json"
FAILED_FILE = PROJECT_ROOT / "failed_tasks.md"
DONE_FILE = PROJECT_ROOT / "done_tasks.md"
BLOCKED_FILE = PROJECT_ROOT / "blocked_tasks.md"
RUNNER_SCRIPT = PROJECT_ROOT / "scripts" / "run_auto_dev_once.py"

MAX_RETRIES: int = 2

# ── TASK 유형 분류 ────────────────────────────────────────────────────────────

TASK_TYPE_KEYWORDS: dict[str, list[str]] = {
    # 더 구체적인 유형을 먼저 검사해 오탐을 방지합니다.
    "ui_improvement": [
        "ui", "화면", "카드", "대시보드", "버튼", "문구", "표시", "디자인", "레이아웃",
    ],
    "docs": [
        "문서", "readme", "agents", "rules", "설명", "docs", "가이드", "주석",
    ],
    "test": [
        "테스트", "pytest", "mock", "dry-run", "test", "단위",
    ],
    "error_fix": [
        "오류", "에러", "실패", "failure", "failed", "bug", "fix", "traceback", "권한", "secret", "error",
    ],
    # feature는 가장 마지막에 검사 (일반 키워드 오탐 방지)
    "feature": [
        "기능", "추가", "구현", "연동", "생성", "feature",
    ],
}


def classify_task_type(task_desc: str) -> str:
    """TASK 설명문을 기준으로 작업 유형을 분류합니다.

    반환값: "error_fix" | "ui_improvement" | "feature" | "docs" | "test"
    """
    desc_lower = task_desc.lower()
    for task_type, keywords in TASK_TYPE_KEYWORDS.items():
        if any(kw in desc_lower for kw in keywords):
            return task_type
    return "feature"


def select_task_with_track(
    pending: list[tuple[str, str]], state: dict
) -> tuple[tuple[str, str], str]:
    """Track A/B 분기 로직에 따라 PENDING TASK를 선택합니다.

    Track A: error_fix 우선 (직전 결과 FAILED/BLOCKED 또는 기본)
    Track B: 기능 고도화 허용 (consecutive_successes >= 2)

    반환: ((task_id, task_desc), track)
    """
    last_result = state.get("last_result", "")
    consecutive = state.get("consecutive_successes", 0)

    # Track A: 직전 결과가 FAILED/BLOCKED이면 error_fix 우선
    if last_result in ("FAILED", "BLOCKED"):
        error_tasks = [
            (tid, tdesc) for tid, tdesc in pending
            if classify_task_type(tdesc) == "error_fix"
        ]
        if error_tasks:
            log(f"[QUEUE] Track A 선택: last_result={last_result}, error_fix 우선")
            return error_tasks[0], "A"
        log(f"[QUEUE] Track A: last_result={last_result}, error_fix 없음 → 일반 PENDING")
        return pending[0], "A"

    # Track B: 연속 성공 2회 이상이면 기능 고도화 허용
    if consecutive >= 2:
        log(f"[QUEUE] Track B 허용: consecutive_successes={consecutive}")
        return pending[0], "B"

    # 기본: Track A
    return pending[0], "A"


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


def write_summary(lines: list[str]) -> None:
    """GitHub Actions Step Summary 파일에 내용을 추가합니다."""
    if not GITHUB_STEP_SUMMARY:
        return
    try:
        with open(GITHUB_STEP_SUMMARY, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
    except Exception as exc:
        log(f"Step Summary 쓰기 실패 (무시): {exc}")


# ── 상태 파일 ────────────────────────────────────────────────────────────────

def load_state() -> dict:
    """auto_dev_state.json을 읽습니다. 없거나 손상된 경우 기본값 반환."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_run": None, "last_task": None, "retry_count": {}, "runs": []}


def save_state(state: dict) -> None:
    """auto_dev_state.json을 저장합니다."""
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── TASKS.md 파싱 / 업데이트 ─────────────────────────────────────────────────

def _section_re(name: str) -> re.Pattern:
    """정확한 섹션 헤더 패턴 (대소문자 구분)."""
    return re.compile(rf"^## {re.escape(name)}\s*$", re.MULTILINE)


def _section_block(text: str, section_name: str) -> tuple[int, int]:
    """섹션 헤더 직후부터 다음 ## 헤더 직전까지의 (start, end) 인덱스 반환."""
    m = _section_re(section_name).search(text)
    if not m:
        return (-1, -1)
    start = m.end()
    next_h = re.search(r"^## ", text[start:], re.MULTILINE)
    end = start + next_h.start() if next_h else len(text)
    return (start, end)


def read_pending_tasks(tasks_text: str) -> list[tuple[str, str]]:
    """PENDING 섹션에서 (task_id, task_description) 목록을 반환합니다."""
    start, end = _section_block(tasks_text, "PENDING")
    if start == -1:
        return []
    block = tasks_text[start:end]
    tasks: list[tuple[str, str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        content = line[2:].strip()
        m = re.match(r"(TASK-[\w-]+):\s*(.+)", content)
        if m:
            tasks.append((m.group(1), m.group(2).strip()))
    return tasks


def move_task(
    tasks_text: str,
    task_id: str,
    task_desc: str,
    from_section: str,
    to_section: str,
    extra_info: str = "",
) -> str:
    """TASK를 from_section에서 to_section으로 이동합니다.

    기존 섹션 (Active, Waiting On, Done)은 절대 건드리지 않습니다.
    큐 전용 섹션 (PENDING, RUNNING, DONE, FAILED, BLOCKED)만 수정합니다.
    """
    _QUEUE_SECTIONS = {"PENDING", "RUNNING", "DONE", "FAILED", "BLOCKED"}
    if from_section not in _QUEUE_SECTIONS or to_section not in _QUEUE_SECTIONS:
        log(f"  WARN: 큐 섹션 외 이동 시도 차단: {from_section} → {to_section}")
        return tasks_text

    # from_section에서 해당 task 라인 제거
    line_pattern = re.compile(
        rf"^- {re.escape(task_id)}[^\n]*\n?", re.MULTILINE
    )
    tasks_text = line_pattern.sub("", tasks_text)
    # 연속 3줄 이상 빈 줄 → 2줄로 정리
    tasks_text = re.sub(r"\n{3,}", "\n\n", tasks_text)

    # to_section에 task 추가
    to_m = _section_re(to_section).search(tasks_text)
    if not to_m:
        return tasks_text

    timestamp = _now_date()
    desc_line = f"{task_desc}"
    if extra_info:
        desc_line += f" [{extra_info}]"
    new_line = f"\n- {task_id}: {desc_line} ({timestamp})"
    insert_pos = to_m.end()
    tasks_text = tasks_text[:insert_pos] + new_line + tasks_text[insert_pos:]

    return tasks_text


# ── 보조 파일 업데이트 ────────────────────────────────────────────────────────

def append_to_file(fpath: Path, content: str) -> None:
    """마크다운 파일에 내용을 안전하게 추가합니다."""
    if fpath.exists():
        existing = fpath.read_text(encoding="utf-8")
    else:
        title = fpath.stem.replace("_", " ").title()
        existing = f"# {title}\n\n"
    fpath.write_text(existing + content, encoding="utf-8")


# ── TASK 실행 ────────────────────────────────────────────────────────────────

def run_task(task_id: str, task_desc: str) -> tuple[str, str]:
    """TASK를 실행합니다. run_auto_dev_once.py를 subprocess로 호출합니다.

    반환값:
      (status, detail)
      status: "DONE" | "FAILED" | "BLOCKED"
      detail: 상세 설명 메시지
    """
    if MOCK_MODE:
        log(f"[MOCK] TASK 실행 시뮬레이션: {task_id}: {task_desc}")
        return "DONE", f"[MOCK] {task_id}: {task_desc}"

    if not RUNNER_SCRIPT.exists():
        return "BLOCKED", "scripts/run_auto_dev_once.py 파일이 없습니다."

    env = {**os.environ, "GOAL": task_desc}

    log(f"scripts/run_auto_dev_once.py 실행 중 (GOAL={task_desc!r})...")
    try:
        result = subprocess.run(
            [sys.executable, str(RUNNER_SCRIPT)],
            env=env,
            cwd=PROJECT_ROOT,
            timeout=600,
        )
        if result.returncode == 0:
            return "DONE", f"성공 (exit 0)"
        else:
            return "FAILED", f"실행 실패 (exit {result.returncode})"
    except subprocess.TimeoutExpired:
        return "FAILED", "실행 시간 초과 (600초)"
    except Exception as exc:
        return "FAILED", f"실행 오류: {exc}"


# ── 메인 ────────────────────────────────────────────────────────────────────

def main() -> None:

    # ── [PRECHECK] ──────────────────────────────────────────────────────────
    log_section("PRECHECK", "Auto Dev Queue 사전 점검")
    if MOCK_MODE:
        log("[MOCK_MODE] dry-run으로 실행합니다. 실제 API 호출 없음.")

    preflight_ok = True

    # 필수 파일 확인
    for rel in ["TASKS.md", "scripts/run_auto_dev_once.py"]:
        p = PROJECT_ROOT / rel
        if p.exists():
            log(f"✓ {rel}")
        else:
            log(f"ERROR: {rel} 없음")
            preflight_ok = False

    # API Key 확인 (MOCK_MODE 아닐 때만)
    if not MOCK_MODE:
        if not OPENAI_API_KEY and not ANTHROPIC_API_KEY:
            log("ERROR: OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 중 하나가 필요합니다.")
            log("  → GitHub Settings > Secrets > Actions 에서 등록 후 재실행")
            _record_blocked("NO_TASK", "API Key 없음", "OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 등록 필요")
            _update_state_blocked("API Key 없음")
            log_section("RESULT", "BLOCKED - API Key 없음 (큐는 유지됩니다)")
            write_summary([
                "## Auto Dev Queue",
                "- 상태: ⛔ BLOCKED",
                "- 원인: API Key 없음",
                "- 해결: GitHub Secrets에 OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 등록",
            ])
            sys.exit(0)  # exit 0: 큐가 멈추지 않도록
        else:
            if OPENAI_API_KEY:
                log("✓ OPENAI_API_KEY 설정됨")
            if ANTHROPIC_API_KEY:
                log("✓ ANTHROPIC_API_KEY 설정됨")

    # TASKS.md conflict marker 검사
    if TASKS_FILE.exists():
        tasks_raw = TASKS_FILE.read_text(encoding="utf-8")
        for marker in ("<<<<<<< ", ">>>>>>> "):
            if marker in tasks_raw:
                log("[PRECHECK] BLOCKED: TASKS.md contains merge conflict markers")
                log("[PRECHECK] 해결: git checkout -- TASKS.md 또는 수동 conflict 해결 후 재실행")
                _record_blocked("MERGE_CONFLICT", "TASKS.md conflict", "TASKS.md에 merge conflict marker 발견")
                _update_state_blocked("TASKS.md merge conflict")
                write_summary([
                    "## Auto Dev Queue",
                    "- 상태: ⛔ BLOCKED",
                    "- 원인: TASKS.md에 merge conflict markers 발견",
                    "- 해결: conflict 해결 후 재실행",
                ])
                sys.exit(0)
        log("[PRECHECK] ✓ TASKS.md conflict marker 없음")

    if not preflight_ok:
        log_section("RESULT", "FAILED - 필수 파일 없음")
        sys.exit(1)

    log("✅ 사전 점검 통과")

    # ── [QUEUE] ─────────────────────────────────────────────────────────────
    log_section("QUEUE", "PENDING TASK 선택")

    tasks_text = TASKS_FILE.read_text(encoding="utf-8")
    pending = read_pending_tasks(tasks_text)

    if not pending:
        log("PENDING 큐가 비어있습니다. 처리할 작업이 없습니다.")
        log_section("RESULT", "SUCCESS - 큐 비어있음")
        write_summary([
            "## Auto Dev Queue",
            "- 상태: ✅ 큐 비어있음",
            "- TASKS.md의 `## PENDING` 섹션에 새 TASK를 추가하세요.",
        ])
        sys.exit(0)

    state = load_state()
    (task_id, task_desc), track = select_task_with_track(pending, state)
    task_type = classify_task_type(task_desc)
    log(f"[QUEUE] selected task: {task_id}: {task_desc}")
    log(f"[TASK] type={task_type} track={track}")
    log(f"[QUEUE] 남은 PENDING: {len(pending)}개 (현재 포함)")

    # 재시도 횟수 확인
    retry_count_map: dict = state.get("retry_count", {})
    run_count = retry_count_map.get(task_id, 0)

    if run_count >= MAX_RETRIES:
        log(f"[QUEUE] {task_id}: 최대 재시도 {MAX_RETRIES}회 도달 → BLOCKED")
        tasks_text = move_task(tasks_text, task_id, task_desc, "PENDING", "BLOCKED",
                               f"최대 재시도 초과 {run_count}/{MAX_RETRIES}")
        TASKS_FILE.write_text(tasks_text, encoding="utf-8")
        append_to_file(
            BLOCKED_FILE,
            f"\n## {task_id}: {task_desc}\n"
            f"- 차단 시각: {_now()}\n"
            f"- 사유: 최대 재시도 횟수 초과 ({run_count}/{MAX_RETRIES})\n\n",
        )
        _finalize_state(state, task_id, task_desc, "BLOCKED", track, task_type)
        log_section("RESULT", f"BLOCKED — {task_id} 최대 재시도 초과")
        write_summary([
            "## Auto Dev Queue",
            f"- TASK: `{task_id}: {task_desc}`",
            "- 상태: ⛔ BLOCKED (최대 재시도 초과)",
            f"- 재시도 횟수: {run_count}/{MAX_RETRIES}",
            "- 해결: `auto_dev_state.json`에서 retry_count 초기화 후 재실행",
        ])
        sys.exit(0)

    # PENDING → RUNNING
    log(f"[QUEUE] {task_id}: PENDING → RUNNING")
    tasks_text = move_task(tasks_text, task_id, task_desc, "PENDING", "RUNNING")
    TASKS_FILE.write_text(tasks_text, encoding="utf-8")

    # ── [EXECUTION] ─────────────────────────────────────────────────────────
    log_section("EXECUTION", f"TASK 실행: {task_id}")

    status, detail = run_task(task_id, task_desc)

    # ── [STATE] ─────────────────────────────────────────────────────────────
    log_section("STATE", f"결과 처리: {status}")

    tasks_text = TASKS_FILE.read_text(encoding="utf-8")

    if status == "DONE":
        tasks_text = move_task(tasks_text, task_id, task_desc, "RUNNING", "DONE")
        TASKS_FILE.write_text(tasks_text, encoding="utf-8")
        append_to_file(
            DONE_FILE,
            f"\n## {task_id}: {task_desc}\n"
            f"- 완료 시각: {_now()}\n"
            f"- 상세: {detail}\n\n",
        )
        log(f"✓ {task_id} → DONE")

    elif status == "BLOCKED":
        tasks_text = move_task(tasks_text, task_id, task_desc, "RUNNING", "BLOCKED",
                               detail[:80])
        TASKS_FILE.write_text(tasks_text, encoding="utf-8")
        append_to_file(
            BLOCKED_FILE,
            f"\n## {task_id}: {task_desc}\n"
            f"- 차단 시각: {_now()}\n"
            f"- 사유: {detail}\n\n",
        )
        log(f"⚠ {task_id} → BLOCKED: {detail}")

    else:  # FAILED
        new_count = retry_count_map.get(task_id, 0) + 1
        retry_count_map[task_id] = new_count
        state["retry_count"] = retry_count_map

        extra = f"재시도 {new_count}/{MAX_RETRIES}"
        tasks_text = move_task(tasks_text, task_id, task_desc, "RUNNING", "FAILED", extra)
        TASKS_FILE.write_text(tasks_text, encoding="utf-8")
        append_to_file(
            FAILED_FILE,
            f"\n## {task_id}: {task_desc}\n"
            f"- 실패 시각: {_now()}\n"
            f"- 사유: {detail}\n"
            f"- 재시도: {new_count}/{MAX_RETRIES}\n\n",
        )
        log(f"✗ {task_id} → FAILED ({extra}): {detail}")

        if new_count < MAX_RETRIES:
            log(f"  → 다음 실행 시 재시도 가능 ({new_count}/{MAX_RETRIES})")

    # state 최종 저장
    _finalize_state(state, task_id, task_desc, status, track, task_type)

    # GitHub Actions Step Summary
    remaining = max(0, len(pending) - 1)
    icon = {"DONE": "✅", "BLOCKED": "⛔", "FAILED": "❌"}.get(status, "❓")
    write_summary([
        "## Auto Dev Queue 실행 결과",
        "",
        f"| 항목 | 값 |",
        f"|---|---|",
        f"| TASK | `{task_id}: {task_desc}` |",
        f"| 유형 | {task_type} |",
        f"| Track | {track} |",
        f"| 상태 | {icon} {status} |",
        f"| 상세 | {detail[:100]} |",
        f"| 시각 | {_now()} |",
        f"| 남은 PENDING | {remaining}개 |",
    ])

    result_label = "SUCCESS" if status in ("DONE",) else status
    log_section("RESULT", f"{result_label} — {task_id}")

    # exit 코드: DONE/BLOCKED → 0(큐 유지), FAILED → 1(workflow 실패 감지 가능)
    sys.exit(0 if status in ("DONE", "BLOCKED") else 1)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _record_blocked(task_id: str, task_desc: str, reason: str) -> None:
    append_to_file(
        BLOCKED_FILE,
        f"\n## {task_id}: {task_desc}\n"
        f"- 차단 시각: {_now()}\n"
        f"- 사유: {reason}\n\n",
    )


def _update_state_blocked(reason: str) -> None:
    state = load_state()
    state["last_run"] = _now()
    state["last_task"] = {"id": "N/A", "status": "BLOCKED", "reason": reason}
    state["consecutive_successes"] = 0
    state["last_result"] = "BLOCKED"
    runs = state.get("runs", [])
    runs.append({"task_id": "N/A", "status": "BLOCKED", "time": _now(), "reason": reason})
    state["runs"] = runs[-50:]
    save_state(state)


def _finalize_state(
    state: dict,
    task_id: str,
    task_desc: str,
    status: str,
    track: str = "A",
    task_type: str = "feature",
) -> None:
    """상태 파일을 최종 업데이트합니다. Track A/B 및 연속 성공 카운트 포함."""
    if status == "DONE":
        state["consecutive_successes"] = state.get("consecutive_successes", 0) + 1
        state["last_result"] = "SUCCESS"
    else:
        state["consecutive_successes"] = 0
        state["last_result"] = status  # "FAILED" or "BLOCKED"

    state["last_track"] = track
    state["last_task_type"] = task_type
    state["last_run"] = _now()
    state["last_task"] = {"id": task_id, "desc": task_desc, "status": status}
    runs = state.get("runs", [])
    runs.append({
        "task_id": task_id,
        "status": status,
        "time": _now(),
        "track": track,
        "type": task_type,
    })
    state["runs"] = runs[-50:]
    save_state(state)


if __name__ == "__main__":
    main()
