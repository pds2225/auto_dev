"""
Auto Dev 대시보드 — 모바일에서 GitHub Actions 트리거 및 결과 확인
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st

# ── 로컬 루프 러너 import ─────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from loop_runner import runner

STATE_FILE = Path(__file__).parent / "loop_state.json"
QUEUE_FILE = Path(__file__).parent / "queue.json"

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


# ── 로컬 루프 상태 / 큐 헬퍼 ────────────────────────────────────────────────

def _save_local_state() -> None:
    try:
        STATE_FILE.write_text(
            json.dumps(
                {
                    "running": runner.running,
                    "project_dir": runner.project_dir,
                    "current_stage": runner.current_stage,
                    "current_task": runner.current_task,
                    "current_task_id": runner.current_task_id,
                    "current_task_type": runner.current_task_type,
                    "selection_reason": runner.selection_reason,
                    "selected_from_section": runner.selected_from_section,
                    "last_updated": datetime.now().isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"상태 저장 실패: {e}")


def _load_local_state() -> None:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            project_dir = data.get("project_dir", "")
            was_running = data.get("running", False)
            saved_stage = data.get("current_stage", "")
            if project_dir and Path(project_dir).exists():
                runner.project_dir = project_dir
                runner.current_task = data.get("current_task", "")
                runner.current_task_id = data.get("current_task_id", "")
                runner.current_task_type = data.get("current_task_type", "")
                runner.selection_reason = data.get("selection_reason", "")
                runner.selected_from_section = data.get("selected_from_section", "")
                # done/error 상태였으면 재시작하지 않음 (Critical 1 방어)
                if was_running and not runner.running and saved_stage not in ("done", "error"):
                    runner.start(project_dir)
        except Exception as e:
            print(f"상태 로드 실패: {e}")


def _read_queue() -> list:
    try:
        if QUEUE_FILE.exists():
            q = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            return q if isinstance(q, list) else []
    except Exception:
        pass
    return []


def _write_queue(queue: list) -> None:
    QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


def _drain_local_logs() -> list[str]:
    lines: list[str] = []
    while not runner.log_queue.empty():
        try:
            lines.append(runner.log_queue.get_nowait())
        except Exception:
            break
    return lines


# NOTE: server.py의 _save_state()와 동기화 필요
# (향후 공통 모듈 분리 권장)
# 세션당 1회만 상태 복구 (Warning 2)
if "local_state_loaded" not in st.session_state:
    _load_local_state()
    st.session_state.local_state_loaded = True


_load_local_state()


def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_request(method: str, url: str, **kwargs) -> requests.Response:
    """GitHub API 호출은 로컬 프록시 환경변수 영향을 받지 않게 보냅니다."""
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
                f"이 칸은 작업 대상 저장소가 아니라 워크플로우 실행 저장소입니다. "
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


def _render_queue_state_card() -> None:
    """auto_dev_state.json 기반 로컬 상태 카드를 렌더링합니다."""
    st.subheader("🖥️ Auto Dev Queue 상태")
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
    st.info(f"**{task_id}** | {task_status} | {last_run}{extra}")


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


def _run_git_command(args: list[str], cwd: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip()
    except FileNotFoundError:
        return False, "git 명령을 찾을 수 없습니다. Git이 설치되어 있는지 확인하세요."
    except Exception as e:
        return False, str(e)


def _run_gh_command(args: list[str], cwd: str, token: str = "") -> tuple[bool, str]:
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token
    try:
        result = subprocess.run(
            ["gh"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env=env,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip()
    except FileNotFoundError:
        return False, "gh CLI를 찾을 수 없습니다."
    except Exception as e:
        return False, str(e)


def _parse_remote_url(url: str) -> tuple[str, str] | None:
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2)
    return None


def _create_pr_via_api(
    token: str, owner: str, repo: str, title: str, body: str, head: str, base: str
) -> tuple[bool, str]:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    payload = {"title": title, "body": body, "head": head, "base": base}
    try:
        resp = _github_request("POST", url, json=payload, headers=_gh_headers(token), timeout=15)
        if resp.status_code == 201:
            data = resp.json()
            return True, data.get("html_url", "PR 생성 완료")
        elif resp.status_code == 422:
            msg = resp.json().get("message", resp.text[:200])
            return False, f"PR 생성 실패 (중복 가능성): {msg}"
        else:
            return False, f"PR 생성 실패 {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, str(e)


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
if "local_logs" not in st.session_state:
    st.session_state.local_logs = []

# ── 메인 UI ──────────────────────────────────────────────────────────────────
st.title("🤖 Auto Dev")
st.caption("GitHub Actions 자동개발 대시보드")

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

# ── 로컬 자동개발 루프 ────────────────────────────────────────────────────────
st.subheader("🖥️ 로컬 자동개발 루프")
st.caption("이 PC에서 TASKS.md를 읽고 직접 코드 개발을 진행합니다.")
st.warning(
    "Flask 서버(server.py)와 동시에 실행하면 러너/파일 충돌 위험이 있습니다. "
    "둘 중 하나만 켜두세요.",
    icon="⚠️",
)

local_project_dir = st.text_input(
    "프로젝트 경로",
    value=runner.project_dir or "",
    placeholder=r"예: D:\marketgate",
    key="local_project_dir",
)

col_start, col_stop = st.columns(2)
with col_start:
    start_local = st.button(
        "▶️ 로컬 루프 시작",
        type="primary",
        use_container_width=True,
        disabled=runner.running,
    )
with col_stop:
    stop_local = st.button(
        "⏹️ 로컬 루프 중단",
        type="secondary",
        use_container_width=True,
        disabled=not runner.running,
    )

if start_local:
    # 공백/따옴표/개행 제거 및 정규화
    pd = local_project_dir.strip().strip('"').strip("'")
    pd = os.path.normpath(pd)
    path_obj = Path(pd)

    # 디버깅 로그
    import sys
    print(f"[DEBUG] Python 실행 경로: {sys.executable}")
    print(f"[DEBUG] 입력 원본: {repr(local_project_dir)}")
    print(f"[DEBUG] 정규화 후: {repr(pd)}")
    print(f"[DEBUG] exists: {path_obj.exists()}, is_dir: {path_obj.is_dir()}")
    print(f"[DEBUG] os.path.exists: {os.path.exists(pd)}")
    try:
        print(f"[DEBUG] os.listdir: {os.listdir(pd)[:3]}")
    except Exception as e:
        print(f"[DEBUG] os.listdir 실패: {e}")

    if not pd:
        st.error("프로젝트 경로를 입력하세요.")
    elif not path_obj.exists():
        st.error(f"경로가 존재하지 않습니다: {pd}")
    elif not path_obj.is_dir():
        st.error(f"폴터가 아닙니다: {pd}")
    else:
        runner.start(pd)
        _save_local_state()
        st.session_state.local_logs.append(f"▶ 루프 시작됨 | {pd}")
        st.rerun()

if stop_local:
    runner.stop()
    _save_local_state()
    st.session_state.local_logs.append("⏹ 루프 중단됨")
    st.rerun()

# 상태 뱃지
stage_info = {
    "idle": ("⏸️ 대기 중", "#21262d", "#8b949e"),
    "hardening": ("🔨 하드닝 중", "#1c2d4a", "#58a6ff"),
    "testing": ("🧪 테스트 중", "#2d1f55", "#bc8cff"),
    "debug": ("🐛 디버그 중", "#3d1f1f", "#ff7b72"),
    "done": ("✅ 완료", "#1a2d1a", "#3fb950"),
    "error": ("⚠️ 오류 중지", "#4a1c1c", "#ff7b72"),
}
label, bg, fg = stage_info.get(runner.current_stage, ("❓ 알 수 없음", "#21262d", "#8b949e"))
if runner.running and runner.current_task:
    label += f" — {runner.current_task}"

st.markdown(
    f"<div style='margin:8px 0;padding:10px 14px;background:{bg};border-radius:8px;"
    f"color:{fg};font-weight:600;font-size:0.95rem;'>{label}</div>",
    unsafe_allow_html=True,
)

if runner.current_task_id:
    st.caption(
        f"ID: `{runner.current_task_id}` | Type: `{runner.current_task_type}` | "
        f"Reason: `{runner.selection_reason}`"
    )

if runner.current_stage == "error":
    st.error("루프가 오류로 중단되었습니다. 로그를 확인하세요.", icon="⚠️")

# 프로젝트 큐
with st.expander("📂 프로젝트 큐", expanded=False):
    q = _read_queue()
    st.caption(f"대기 중: **{len(q)}개**")
    for idx, qpath in enumerate(q, 1):
        c1, c2 = st.columns([5, 1])
        with c1:
            st.text(f"{idx}. {qpath}")
        with c2:
            if st.button("제거", key=f"rm_q_{idx}"):
                new_q = [p for p in q if p != qpath]
                _write_queue(new_q)
                st.rerun()
    new_q_path = st.text_input("추가할 경로", placeholder=r"예: D:\my-project", key="new_q_path")
    if st.button("큐에 추가", key="add_q"):
        nqp = new_q_path.strip()
        if nqp and Path(nqp).is_dir() and nqp not in q:
            q.append(nqp)
            _write_queue(q)
            st.rerun()
        elif nqp in q:
            st.warning("이미 큐에 있습니다.")
        elif nqp:
            st.error("유효하지 않은 경로입니다.")

# 실시간 로그 (드레인은 렌더링 직전에 수행)
st.session_state.local_logs.extend(_drain_local_logs())
st.session_state.local_logs = st.session_state.local_logs[-500:]

st.markdown(
    "<div style='font-size:0.75rem;color:#8b949e;margin-bottom:6px;'>실시간 로그</div>",
    unsafe_allow_html=True,
)
log_text = "\n".join(st.session_state.local_logs)
st.code(log_text[-4000:] if len(log_text) > 4000 else log_text, language="bash")

st.divider()

# ── GitHub 푸시 및 PR 생성 ────────────────────────────────────────────────────
st.subheader("📤 GitHub에 올리기")
st.caption("로컬에서 수정한 코드를 GitHub에 올리고 Pull Request를 만듭니다.")

push_project_dir = st.text_input(
    "푸시할 프로젝트 경로",
    value=runner.project_dir or local_project_dir or "",
    placeholder=r"예: D:\marketgate",
    key="push_project_dir",
)

push_col1, push_col2 = st.columns(2)
with push_col1:
    push_clicked = st.button("📤 커밋 & 푸시", use_container_width=True)
with push_col2:
    pr_clicked = st.button("🔀 PR 생성", use_container_width=True, disabled=not github_token.strip())

if push_clicked or pr_clicked:
    ppd = push_project_dir.strip()
    if not ppd:
        st.error("프로젝트 경로를 입력하세요.")
    elif not Path(ppd).is_dir():
        st.error(f"유효하지 않은 경로입니다: {ppd}")
    else:
        ok_git, msg_git = _run_git_command(["rev-parse", "--git-dir"], ppd)
        if not ok_git:
            st.error(f"git 저장소가 아닙니다. 먼저 `git init`과 `git remote add origin ...`을 설정하세요.\n{msg_git}")
        else:
            if push_clicked:
                branch = f"auto-dev/{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                _run_git_command(["config", "user.name", "github-actions[bot]"], ppd)
                _run_git_command(["config", "user.email", "github-actions[bot]@users.noreply.github.com"], ppd)
                _run_git_command(["checkout", "-b", branch], ppd)
                _run_git_command(["add", "-A"], ppd)
                ok_c, msg_c = _run_git_command(["commit", "-m", "auto-dev: 로컬 수정"], ppd)
                if not ok_c and ("nothing to commit" in msg_c.lower() or "nothing added" in msg_c.lower()):
                    st.warning("변경사항이 없습니다. 먼저 로컬 루프를 실행하세요.")
                else:
                    ok_p, msg_p = _run_git_command(["push", "-u", "origin", branch], ppd)
                    if ok_p:
                        st.success(f"✅ 푸시 완료: `{branch}`")
                        st.session_state.push_branch = branch
                    else:
                        st.error(f"푸시 실패: {msg_p}")
            if pr_clicked:
                branch = st.session_state.get("push_branch", "")
                if not branch:
                    ok_b, msg_b = _run_git_command(["branch", "--show-current"], ppd)
                    if ok_b:
                        branch = msg_b.strip()
                if not branch:
                    st.error("현재 브랜치를 확인할 수 없습니다. 먼저 커밋 & 푸시를 실행하세요.")
                else:
                    ok_r, msg_r = _run_git_command(["remote", "get-url", "origin"], ppd)
                    remote_info = _parse_remote_url(msg_r) if ok_r else None
                    if not remote_info:
                        st.error("GitHub remote URL을 파싱할 수 없습니다.")
                    else:
                        owner, repo = remote_info
                        ok_gh, msg_gh = _run_gh_command(
                            [
                                "pr", "create",
                                "--title", f"auto-dev: 로컬 수정 ({branch})",
                                "--body", "로컬 자동개발 루프에서 생성된 변경사항입니다.",
                                "--base", "main",
                            ],
                            ppd,
                            github_token,
                        )
                        if ok_gh:
                            st.success(f"✅ PR 생성 완료: {msg_gh}")
                        else:
                            if not github_token.strip():
                                st.error(f"gh CLI 실패 + GitHub Token 없음: {msg_gh}")
                            else:
                                ok_api, msg_api = _create_pr_via_api(
                                    github_token, owner, repo,
                                    f"auto-dev: 로컬 수정 ({branch})",
                                    "로컬 자동개발 루프에서 생성된 변경사항입니다.",
                                    branch, "main",
                                )
                                if ok_api:
                                    st.success(f"✅ PR 생성 완료: {msg_api}")
                                else:
                                    st.error(f"PR 생성 실패: {msg_api}")

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

    # ── 큐 현황 요약 카드 ──────────────────────────────────────────────────────
    st.subheader("📋 큐 현황")
    with st.spinner("큐 상태 불러오는 중..."):
        queue_status = _get_tasks_queue_summary(token_q, owner_q, repo_name_q)

    if queue_status is not None:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("⏳ PENDING", queue_status.get("pending", 0))
        with c2:
            st.metric("🔄 RUNNING", queue_status.get("running", 0))
        with c3:
            failed = queue_status.get("failed", 0)
            st.metric("❌ FAILED", failed)
        with c4:
            blocked = queue_status.get("blocked", 0)
            st.metric("⛔ BLOCKED", blocked)
        if failed > 0 or blocked > 0:
            st.warning(
                f"FAILED {failed}개 / BLOCKED {blocked}개 — "
                "TASKS.md 또는 GitHub Actions 로그를 확인하세요."
            )
    else:
        st.caption("큐 현황을 불러오지 못했습니다.")

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

# ── 로컬 루프 실행 중 자동 갱신 ──────────────────────────────────────────────
if runner.running:
    time.sleep(1)
    st.rerun()
