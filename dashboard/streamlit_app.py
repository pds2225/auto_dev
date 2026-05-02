"""
Auto Dev 대시보드 — Streamlit 버전 (server.py 대체)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from loop_runner import QUEUE_FILE, runner
from project_snapshot import get_project_snapshot, get_snapshot_note

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
    tasks_path = runner._get_task_file_path()
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


def _get_task_entries() -> list[dict]:
    """태스크 원본 라인 + 상태 + 표시 텍스트를 반환"""
    import re
    entries = []
    if not runner.project_dir:
        return entries
    tasks_path = runner._get_task_file_path()
    if not tasks_path.exists():
        return entries
    try:
        text = tasks_path.read_text(encoding="utf-8")
        active = runner._get_active_section(text)
        for line in active.splitlines():
            stripped = line.strip()
            m = re.match(r"^- \[x\] (.+)$", stripped)
            if m:
                entries.append({"raw": line, "text": m.group(1).strip(), "done": True})
                continue
            m = re.match(r"^- \[ \] ~~.+~~.*$", stripped)
            if m:
                continue
            m = re.match(r"^- \[ \] (.+)$", stripped)
            if m:
                entries.append({"raw": line, "text": m.group(1).strip(), "done": False})
    except Exception:
        pass
    return entries


def _save_task_entries(entries: list[dict]) -> None:
    """entries를 기반으로 TASKS.md의 Active 섹션을 재생성"""
    import re
    if not runner.project_dir:
        return
    tasks_path = runner._get_task_file_path()
    if not tasks_path.exists():
        return
    full_text = tasks_path.read_text(encoding="utf-8")

    # Active 섹션 바운드 찾기
    match = re.search(r"^## Active\s*$", full_text, flags=re.MULTILINE)
    if not match:
        return
    start = match.end()
    next_section = re.search(r"^##\s+", full_text[start:], flags=re.MULTILINE)
    end = start + next_section.start() if next_section else len(full_text)

    # 새 Active 섹션 빌드
    new_lines = []
    for e in entries:
        prefix = "- [x] " if e["done"] else "- [ ] "
        new_lines.append(prefix + e["text"])
    new_active = "\n".join(new_lines)

    new_text = full_text[:start] + "\n\n" + new_active + "\n\n" + full_text[end:]
    tasks_path.write_text(new_text, encoding="utf-8")


def _delete_task_by_index(idx: int) -> None:
    entries = _get_task_entries()
    if 0 <= idx < len(entries):
        entries.pop(idx)
        _save_task_entries(entries)


def _update_task_by_index(idx: int, new_text: str) -> None:
    entries = _get_task_entries()
    if 0 <= idx < len(entries):
        entries[idx]["text"] = new_text.strip()
        _save_task_entries(entries)


# ── 로그를 세션 상태에 드레인 ────────────────────────────────────────────────

if "logs" not in st.session_state:
    st.session_state.logs = []
if "edit_task_idx" not in st.session_state:
    st.session_state.edit_task_idx = None

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
selected_project_dir = project_dir_input.strip() or runner.project_dir
snapshot_target = Path(selected_project_dir) if selected_project_dir else Path(__file__).resolve().parent.parent
snapshot = get_project_snapshot(snapshot_target)

STAGE_LABELS = {
    "idle": "⬜ 대기",
    "testing": "🧪 테스트 중",
    "hardening": "🔨 하드닝 중",
    "debug": "🐛 디버그 중",
    "done": "✅ 완료",
    "error": "❌ 오류",
}

# 상태 행
c_status, c_task, c_stage, c_repo = st.columns(4)
with c_status:
    if runner.running:
        st.success("● 실행 중")
    else:
        st.info("○ 중지됨")
with c_task:
    st.metric("현재 태스크", runner.current_task_id or "—")
with c_stage:
    st.metric("단계", STAGE_LABELS.get(runner.current_stage, runner.current_stage))
with c_repo:
    st.metric("브랜치", snapshot["branch"] or "—")

if runner.current_task:
    st.info(f"📌 {runner.current_task}")

st.divider()

st.subheader("📦 프로젝트 상태")
repo_cols = st.columns(4)
with repo_cols[0]:
    st.metric("HEAD", snapshot["head"] or "—")
with repo_cols[1]:
    st.metric("원격", "연결됨" if snapshot["remote"] else "—")
with repo_cols[2]:
    st.metric("작업트리", "변경 있음" if snapshot["dirty"] else "clean")
with repo_cols[3]:
    st.metric("Git 상태", snapshot["status"] or "—")

if snapshot["remote"]:
    st.caption(get_snapshot_note(snapshot))
elif snapshot["error"]:
    st.warning(get_snapshot_note(snapshot))
else:
    st.caption(get_snapshot_note(snapshot))

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
            entries = _get_task_entries()
            pending_entries = [e for e in entries if not e["done"]]
            for i, e in enumerate(pending_entries):
                col1, col2, col3 = st.columns([6, 1, 1])
                with col1:
                    st.markdown(f"- {e['text']}")
                with col2:
                    if st.button("✏️", key=f"edit_{i}"):
                        st.session_state.edit_task_idx = i
                        st.session_state.edit_task_text = e["text"]
                        st.rerun()
                with col3:
                    if st.button("🗑️", key=f"del_{i}"):
                        _delete_task_by_index(i)
                        st.rerun()

                if st.session_state.edit_task_idx == i:
                    new_text = st.text_area("수정", value=st.session_state.edit_task_text, key=f"ta_{i}")
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        if st.button("💾 저장", key=f"save_{i}"):
                            _update_task_by_index(i, new_text)
                            st.session_state.edit_task_idx = None
                            st.rerun()
                    with c2:
                        if st.button("❌ 취소", key=f"cancel_{i}"):
                            st.session_state.edit_task_idx = None
                            st.rerun()

        if done_tasks:
            st.markdown("**✅ 완료**")
            for t in done_tasks:
                st.markdown(f"- ~~{t}~~")
    else:
        st.caption(f"{runner._get_task_file_path().name} 없음 또는 태스크 없음")

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

# ── 기존 streamlit_app.py 맨 아래에 추가 ─────────────────────

st.divider()
st.subheader("🛠️ 도구")

# 탭으로 분리
tab_gen, tab_sched = st.tabs(["📝 태스크 자동 생성", "⏰ 예약 설정"])

# ── 탭 1: 자동 태스크 생성 ────────────────────────────────────
with tab_gen:
    st.markdown("**AI가 할 일을 자동으로 만들어줍니다**")
    
    task_desc = st.text_area(
        "새 태스크 설명",
        placeholder="예: 대시보드에 다크모드 토글 버튼 추가",
        height=80,
    )
    
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        task_stack = st.selectbox("기술스택", ["Streamlit", "FastAPI", "Python", "기타"], index=0)
    with c2:
        task_skill = st.selectbox("스킬 태그", ["frontend-ui", "backend-api", "debugging", "test"], index=0)
    with c3:
        ai_decompose = st.toggle("AI 분해 모드", value=True, help="켜면 AI가 설명을 여러 세부 태스크로 자동 분해합니다")
    
    if st.button("✨ 태스크 생성 및 TASK.md에 추가", use_container_width=True):
        if task_desc.strip():
            try:
                project_dir = runner.project_dir or "D:/auto_dev"
                if ai_decompose:
                    from task_generator import decompose_tasks_with_fallback, batch_append_tasks
                    
                    with st.spinner("AI가 태스크를 분해하는 중..."):
                        tasks, task_source = decompose_tasks_with_fallback(task_desc, task_stack)
                    
                    st.json({"생성된 태스크": [t["title"] for t in tasks]})
                    
                    new_ids = batch_append_tasks(tasks, project_dir)
                    if task_source == "ai":
                        st.success(f"✅ {len(new_ids)}개 태스크({new_ids[0]}~{new_ids[-1]})가 TASK.md에 추가되었습니다!")
                    else:
                        st.warning("AI 분해에 실패해 입력 설명 기반 단일 태스크로 추가했습니다.")
                        st.success(f"✅ {new_ids[0]}가 TASK.md에 추가되었습니다!")
                else:
                    from task_generator import generate_task_via_template, preview_task
                    preview = preview_task(task_desc)
                    st.json(preview)
                    new_id = generate_task_via_template(
                        description=task_desc,
                        project_dir=project_dir,
                        tech_stack=task_stack,
                    )
                    st.success(f"✅ {new_id}가 TASK.md에 추가되었습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"추가 실패: {e}")
        else:
            st.warning("설명을 입력하세요")

# ── 탭 2: 예약 설정 (TASK-31) ─────────────────────────────────
with tab_sched:
    st.markdown("**루프를 자동으로 실행할 시간을 설정합니다**")
    
    try:
        from task_scheduler import get_schedule, save_schedule_from_ui
        
        cfg = get_schedule()
        
        sched_enabled = st.toggle("예약 실행 활성화", value=cfg.get("enabled", False))
        sched_time = st.time_input("실행 시간", value=datetime.strptime(cfg.get("time", "09:00"), "%H:%M").time())
        sched_project = st.text_input("대상 프로젝트 경로", value=cfg.get("project_dir", runner.project_dir or "D:/auto_dev"))
        
        st.markdown("**실행 요일**")
        days_cols = st.columns(7)
        day_names = ["월", "화", "수", "목", "금", "토", "일"]
        selected_days = []
        for i, col in enumerate(days_cols):
            with col:
                if st.checkbox(day_names[i], value=i in cfg.get("days", [0,1,2,3,4])):
                    selected_days.append(i)
        
        if st.button("💾 예약 저장", use_container_width=True):
            save_schedule_from_ui(
                enabled=sched_enabled,
                time_str=sched_time.strftime("%H:%M"),
                days=selected_days,
                project_dir=sched_project,
            )
            st.success("예약 설정이 저장되었습니다!")
            
            # Windows Task Scheduler 등록 안내
            if os.name == "nt":
                st.info("""
                💡 **Windows에서 부팅 시 자동 실행하려면:**
                1. `Win + R` → `taskschd.msc`
                2. 작업 만들기 → `python streamlit_app.py` 등록
                3. 또는 `run_scheduler.bat`를 시작 프로그램에 추가
                """)
    except Exception as e:
        st.error(f"스케줄러 로드 실패: {e}")
