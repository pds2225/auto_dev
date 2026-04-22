"""
Auto Dev 대시보드 — Streamlit 버전 (server.py 대체)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from loop_runner import QUEUE_FILE, runner

st.set_page_config(
    page_title="Auto Dev 대시보드",
    page_icon="🤖",
    layout="wide",
)

# ── 큐 헬퍼 ─────────────────────────────────────────────────────────────────

def _read_queue() -> list[str]:
    try:
        if QUEUE_FILE.exists():
            data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _write_queue(queue: list[str]) -> None:
    QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 태스크 헬퍼 ──────────────────────────────────────────────────────────────

def _get_tasks() -> tuple[list[str], list[str]]:
    import re
    done, pending = [], []
    if not runner.project_dir:
        return done, pending
    tasks_path = Path(runner.project_dir) / "TASKS.md"
    if not tasks_path.exists():
        return done, pending
    try:
        text = tasks_path.read_text(encoding="utf-8")
        active = runner._get_active_section(text)
        for line in active.splitlines():
            m = re.match(r"^- \[x\] (.+)$", line.strip())
            if m:
                done.append(m.group(1).strip())
                continue
            m = re.match(r"^- \[ \] ~~.+~~.*$", line.strip())
            if m:
                continue
            m = re.match(r"^- \[ \] (.+)$", line.strip())
            if m:
                pending.append(m.group(1).strip())
    except Exception:
        pass
    return done, pending


# ── 로그를 세션 상태에 드레인 ────────────────────────────────────────────────

if "logs" not in st.session_state:
    st.session_state.logs = []

while not runner.log_queue.empty():
    st.session_state.logs.append(runner.log_queue.get())

if len(st.session_state.logs) > 300:
    st.session_state.logs = st.session_state.logs[-300:]

# ── 사이드바 ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("🤖 Auto Dev")

    project_dir_input = st.text_input(
        "프로젝트 경로",
        value=runner.project_dir,
        placeholder="D:/my-project",
        key="project_dir_input",
    )

    if runner.running:
        if st.button("⏹ 루프 중단", type="primary", use_container_width=True):
            runner.stop()
            st.rerun()
    else:
        if st.button("▶ 루프 시작", type="primary", use_container_width=True):
            pdir = project_dir_input.strip()
            if pdir and Path(pdir).is_dir():
                runner.start(pdir)
                st.rerun()
            else:
                st.error("유효한 프로젝트 경로를 입력하세요.")

    st.divider()

    # 큐 관리
    st.subheader("📋 대기 큐")
    queue = _read_queue()

    new_item = st.text_input("큐에 추가", placeholder="D:/another-project", key="queue_input")
    if st.button("➕ 추가", use_container_width=True) and new_item:
        pdir = new_item.strip()
        if Path(pdir).is_dir():
            if pdir not in queue:
                queue.append(pdir)
                _write_queue(queue)
            st.rerun()
        else:
            st.error("유효하지 않은 경로")

    if queue:
        for item in queue:
            c1, c2 = st.columns([5, 1])
            c1.caption(item)
            if c2.button("✕", key=f"del_{item}"):
                queue = [p for p in queue if p != item]
                _write_queue(queue)
                st.rerun()
    else:
        st.caption("대기 중인 프로젝트 없음")

# ── 메인 영역 ─────────────────────────────────────────────────────────────────

st.title("🤖 Auto Dev 대시보드")

STAGE_LABELS = {
    "idle": "⬜ 대기",
    "testing": "🧪 테스트 중",
    "hardening": "🔨 하드닝 중",
    "debug": "🐛 디버그 중",
    "done": "✅ 완료",
    "error": "❌ 오류",
}

# 상태 행
c_status, c_task, c_stage = st.columns(3)
with c_status:
    if runner.running:
        st.success("● 실행 중")
    else:
        st.info("○ 중지됨")
with c_task:
    st.metric("현재 태스크", runner.current_task_id or "—")
with c_stage:
    st.metric("단계", STAGE_LABELS.get(runner.current_stage, runner.current_stage))

if runner.current_task:
    st.info(f"📌 {runner.current_task}")

st.divider()

# 태스크 진행
col_tasks, col_logs = st.columns([1, 2])

with col_tasks:
    st.subheader("📊 태스크 진행")
    done_tasks, pending_tasks = _get_tasks()
    total = len(done_tasks) + len(pending_tasks)

    if total > 0:
        st.progress(len(done_tasks) / total, text=f"{len(done_tasks)} / {total} 완료")

        if pending_tasks:
            st.markdown("**⬜ 대기**")
            for t in pending_tasks:
                st.markdown(f"- {t}")

        if done_tasks:
            st.markdown("**✅ 완료**")
            for t in done_tasks:
                st.markdown(f"- ~~{t}~~")
    else:
        st.caption("TASKS.md 없음 또는 태스크 없음")

with col_logs:
    st.subheader("📜 실행 로그")
    log_box = st.container(height=450)
    with log_box:
        logs = st.session_state.logs
        for line in reversed(logs[-150:]):
            st.text(line)

# 루프 실행 중이면 1초마다 자동 갱신
if runner.running:
    time.sleep(1)
    st.rerun()
