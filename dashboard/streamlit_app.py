"""
Auto Dev 대시보드 — GitHub Actions 자동개발 트리거 및 모니터링

외부(모바일 등)에서 GitHub Actions 워크플로우를 트리거하고
실행 현황과 PR 목록을 확인합니다.
"""
from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st

DEFAULT_WORKFLOW_REPO = "pds2225/auto_dev"

st.set_page_config(
    page_title="Auto Dev",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        .block-container { padding-top: 1rem; padding-bottom: 1rem; }
        .stButton button { width: 100%; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── 헬퍼 ────────────────────────────────────────────────────────────────────

def _get_secret(key: str, default: str = "") -> str:
    """Streamlit Secrets 또는 환경변수에서 값을 가져옵니다."""
    try:
        val = st.secrets.get(key)
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, default)


def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_request(method: str, url: str, **kwargs) -> requests.Response:
    """GitHub API 호출은 로컬 프록시 환경변수 영향을 받지 않게 본냅니다."""
    session = requests.Session()
    session.trust_env = False
    return session.request(method, url, **kwargs)


def _trigger_workflow(token: str, owner: str, repo: str, goal: str, mode: str) -> tuple[bool, str]:
    """GitHub Actions workflow_dispatch를 호출합니다."""
    url = (
        f"https://api.github.com/repos/{owner}/{repo}"
        "/actions/workflows/auto-dev-loop.yml/dispatches"
    )
    payload = {
        "ref": "main",
        "inputs": {"goal": goal, "mode": mode},
    }
    try:
        resp = _github_request("POST", url, json=payload, headers=_gh_headers(token), timeout=15)
        if resp.status_code == 204:
            return True, "GitHub Actions 워크플로우가 성공적으로 트리거되었습니다."
        elif resp.status_code == 404:
            return False, (
                f"{owner}/{repo} 저장소에서 auto-dev-loop.yml 워크플로우를 찾을 수 없습니다. "
                f"기본값 {DEFAULT_WORKFLOW_REPO}를 사용하세요."
            )
        elif resp.status_code == 401:
            return False, "인증 실패: GitHub Token을 확인하세요."
        elif resp.status_code == 422:
            msg = resp.json().get("message", resp.text[:200])
            return False, f"입력값이 올바르지 않습니다: {msg}"
        else:
            return False, f"오류 {resp.status_code}: {resp.text[:200]}"
    except requests.exceptions.Timeout:
        return False, "요청 시간 초과. 네트워크 상태를 확인하세요."
    except requests.exceptions.RequestException as exc:
        return False, f"네트워크 오류: {exc}"


def _get_recent_runs(token: str, owner: str, repo: str, limit: int = 5) -> list[dict]:
    """최근 GitHub Actions 실행 목록을 가져옵니다."""
    url = (
        f"https://api.github.com/repos/{owner}/{repo}"
        "/actions/workflows/auto-dev-loop.yml/runs"
    )
    try:
        resp = _github_request(
            "GET",
            url, params={"per_page": limit}, headers=_gh_headers(token), timeout=15
        )
        if resp.status_code == 200:
            return resp.json().get("workflow_runs", [])
    except Exception:
        pass
    return []


def _get_recent_prs(token: str, owner: str, repo: str, limit: int = 5) -> list[dict]:
    """최근 PR 목록을 가져옵니다."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    try:
        resp = _github_request(
            "GET",
            url,
            params={"state": "all", "per_page": limit, "sort": "created", "direction": "desc"},
            headers=_gh_headers(token),
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


def _load_queue_state() -> dict | None:
    """프로젝트 루트의 auto_dev_state.json을 읽어 반환합니다.

    반환값:
      {}   → 파일 없음
      None → JSON 파싱 실패
      dict → 정상 (필드 일부 누락 가능)
    """
    state_file = Path(__file__).resolve().parent.parent / "auto_dev_state.json"
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _friendly_task_status(status: str) -> str:
    labels = {
        "PENDING": "아직 시작 전(PENDING)",
        "RUNNING": "처리 중(RUNNING)",
        "DONE": "완료(DONE)",
        "FAILED": "다시 확인 필요(FAILED)",
        "BLOCKED": "사람 확인 필요(BLOCKED)",
    }
    return labels.get(status, status or "-")


def _render_queue_state_card() -> None:
    """auto_dev_state.json 기반 로컬 상태 카드를 렌더링합니다."""
    st.subheader("🖥️ 자동개발 할 일 상태")
    data = _load_queue_state()

    if data == {}:
        st.caption("📭 상태 파일 없음 — Auto Dev Queue를 1회 실행하면 표시됩니다.")
        return
    if data is None:
        st.caption("⚠️ 상태 파일 읽기 실패")
        return

    last_task = data.get("last_task") or {}
    task_status = last_task.get("status", "-")

    task_id = last_task.get("id", "-")
    last_run = data.get("last_run") or "-"
    extra = f" | 차단: {last_task['reason']}" if task_status == "BLOCKED" and last_task.get("reason") else ""
    st.info(f"**{task_id}** | {_friendly_task_status(task_status)} | {last_run}{extra}")


def _get_tasks_queue_summary(token: str, owner: str, repo: str) -> dict | None:
    """GitHub API로 TASKS.md의 큐 상태를 읽어옵니다.

    반환: {"pending": int, "running": int, "failed": int, "blocked": int}
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/TASKS.md"
    try:
        resp = _github_request("GET", url, headers=_gh_headers(token), timeout=10)
        if resp.status_code != 200:
            return None
        raw = base64.b64decode(resp.json()["content"]).decode("utf-8")
        counts: dict[str, int] = {}
        for section in ("PENDING", "RUNNING", "FAILED", "BLOCKED"):
            m = re.search(
                rf"^## {section}\s*$(.*?)(?=^## |\Z)",
                raw,
                re.MULTILINE | re.DOTALL,
            )
            counts[section.lower()] = (
                len(re.findall(r"^- TASK-", m.group(1), re.MULTILINE)) if m else 0
            )
        return counts
    except Exception:
        return None


def _fmt_dt(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%m/%d %H:%M")
    except Exception:
        return iso[:16]


def _run_icon(run: dict) -> str:
    status = run.get("status", "")
    conclusion = run.get("conclusion", "")
    if status == "completed":
        return {"success": "✅", "failure": "❌", "cancelled": "⚫", "skipped": "⏭️"}.get(
            conclusion, "❓"
        )
    return {"in_progress": "🔄", "queued": "⏳"}.get(status, "❓")


# ── 세션 상태 ────────────────────────────────────────────────────────────────
if "trigger_msg" not in st.session_state:
    st.session_state.trigger_msg = None
if "trigger_ok" not in st.session_state:
    st.session_state.trigger_ok = None

# ── 메인 UI ──────────────────────────────────────────────────────────────────
st.title("🤖 Auto Dev")
st.caption("목표를 입력하면 GitHub Actions가 자동으로 개발합니다.")

st.divider()

# ── 설정 ─────────────────────────────────────────────────────────────────────
with st.expander("⚙️ 설정", expanded=not bool(_get_secret("GITHUB_TOKEN"))):
    github_token = st.text_input(
        "GitHub Token",
        value=_get_secret("GITHUB_TOKEN"),
        type="password",
        placeholder="ghp_xxxx...  (또는 Streamlit Secrets의 GITHUB_TOKEN)",
        help="repo · workflow 권한이 있는 Personal Access Token",
    )
    repo_input = st.text_input(
        "워크플로우 저장소 (owner/repo)",
        value=_get_secret("GITHUB_REPO", DEFAULT_WORKFLOW_REPO),
        placeholder=DEFAULT_WORKFLOW_REPO,
        help="auto-dev-loop.yml이 있는 저장소입니다. 작업 대상 저장소가 아닙니다.",
    )

st.divider()

# ── GitHub Actions 개발 목표 ─────────────────────────────────────────────────
st.subheader("🎯 GitHub Actions 개발 목표")
goal_input = st.text_area(
    "goal",
    placeholder=(
        "예: 로그인 페이지에 소셜 로그인 버튼 추가\n"
        "예: API 응답 속도를 50% 개선\n"
        "예: 모바일 반응형 레이아웃 적용"
    ),
    height=100,
    label_visibility="collapsed",
)
mode_input = st.selectbox(
    "실행 모드",
    options=["standard", "night", "quick"],
    index=0,
    help="standard: 일반 / night: 야간 집중 / quick: 간단 수정",
)

st.divider()

# ── 실행 버튼 ─────────────────────────────────────────────────────────────────
run_clicked = st.button("🚀 GitHub Actions 실행", type="primary", use_container_width=True)

if run_clicked:
    token = github_token.strip()
    repo_full = repo_input.strip()
    goal = goal_input.strip()

    if not token:
        st.error("GitHub Token을 입력하거나 Streamlit Secrets에 GITHUB_TOKEN을 설정하세요.")
    elif not repo_full or "/" not in repo_full:
        st.error("저장소 경로를 'owner/repo' 형식으로 입력하세요.")
    elif not goal:
        st.error("개발 목표를 입력하세요.")
    else:
        owner, repo = repo_full.split("/", 1)
        with st.spinner("GitHub Actions 트리거 중..."):
            ok, msg = _trigger_workflow(token, owner, repo, goal, mode_input)
        st.session_state.trigger_ok = ok
        st.session_state.trigger_msg = msg
        st.rerun()

if st.session_state.trigger_msg:
    if st.session_state.trigger_ok:
        st.success(st.session_state.trigger_msg)
    else:
        st.error(st.session_state.trigger_msg)

# ── 실행 현황 / PR 목록 ────────────────────────────────────────────────────────
st.divider()

# ── Auto Dev Queue 로컬 상태 카드 (토큰 불필요) ────────────────────────────────
_render_queue_state_card()

st.divider()

token_q = github_token.strip() if "github_token" in dir() else ""
repo_q = repo_input.strip() if "repo_input" in dir() else ""

if token_q and repo_q and "/" in repo_q:
    owner_q, repo_name_q = repo_q.split("/", 1)

    _, col_refresh = st.columns([4, 1])
    with col_refresh:
        if st.button("🔄 새로고침", use_container_width=True):
            st.rerun()

    # ── 할 일 현황 요약 카드 ──────────────────────────────────────────────────
    st.subheader("📋 할 일 현황")
    with st.spinner("할 일 상태 불러오는 중..."):
        queue_status = _get_tasks_queue_summary(token_q, owner_q, repo_name_q)

    if queue_status is not None:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("⏳ 시작 전", queue_status.get("pending", 0))
        with c2:
            st.metric("🔄 처리 중", queue_status.get("running", 0))
        with c3:
            failed = queue_status.get("failed", 0)
            st.metric("❌ 다시 확인", failed)
        with c4:
            blocked = queue_status.get("blocked", 0)
            st.metric("⛔ 사람 확인", blocked)
        if failed > 0 or blocked > 0:
            st.warning(
                f"다시 확인 {failed}개 / 사람 확인 {blocked}개 — "
                "TASKS.md 또는 GitHub Actions 로그를 확인하세요."
            )
    else:
        st.caption("할 일 현황을 불러오지 못했습니다.")

    st.divider()

    # 최근 Actions 실행
    st.subheader("⚡ 최근 Actions 실행")
    with st.spinner("불러오는 중..."):
        runs = _get_recent_runs(token_q, owner_q, repo_name_q)

    if runs:
        for run in runs:
            icon = _run_icon(run)
            title = (
                run.get("display_title")
                or (run.get("head_commit") or {}).get("message", "")[:50]
                or f"Run #{run.get('run_number', '?')}"
            )
            created = _fmt_dt(run.get("created_at", ""))
            url = run.get("html_url", "#")
            status_label = run.get("conclusion") or run.get("status", "")
            st.markdown(
                f"{icon} **[{title}]({url})**  \n"
                f"&nbsp;&nbsp;&nbsp;&nbsp;`{status_label}` · {created}"
            )
    else:
        st.caption("실행 기록이 없거나 불러오지 못했습니다.")

    st.divider()

    # 최근 PR
    st.subheader("🔀 최근 Pull Requests")
    with st.spinner("불러오는 중..."):
        prs = _get_recent_prs(token_q, owner_q, repo_name_q)

    if prs:
        for pr in prs:
            state = pr.get("state", "")
            merged_at = pr.get("merged_at") or (pr.get("pull_request") or {}).get("merged_at")
            if merged_at:
                state_icon = "🟣"
            elif state == "open":
                state_icon = "🟢"
            else:
                state_icon = "⚫"
            title = pr.get("title", "")[:60]
            number = pr.get("number")
            pr_url = pr.get("html_url", "#")
            branch = (pr.get("head") or {}).get("ref", "")
            created = _fmt_dt(pr.get("created_at", ""))
            st.markdown(
                f"{state_icon} **[#{number} {title}]({pr_url})**  \n"
                f"&nbsp;&nbsp;&nbsp;&nbsp;`{branch}` · {created}"
            )
    else:
        st.caption("PR이 없거나 불러오지 못했습니다.")
else:
    st.info("설정에서 GitHub Token과 저장소를 입력하면 실행 현황과 PR을 확인할 수 있습니다.")
