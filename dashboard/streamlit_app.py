
"""
Auto Dev 대시보드 — 모바일에서 GitHub Actions 트리거 및 결과 확인
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
        resp = requests.post(url, json=payload, headers=_gh_headers(token), timeout=15)
        if resp.status_code == 204:
            return True, "GitHub Actions 워크플로우가 성공적으로 트리거되었습니다."
        elif resp.status_code == 404:
            return False, "저장소 또는 워크플로우 파일을 찾을 수 없습니다. owner/repo와 브랜치를 확인하세요."
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
        f"https://api.github.com/repos/{owner}/{repo}/actions/runs"
    )
    headers = _gh_headers(token)
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("workflow_runs", [])[:limit]
        else:
            return []
    except requests.exceptions.RequestException:
        return []


def _display_status_card():
    """Mock 실행 결과를 상태 카드로 표시합니다."""
    mock_result = "Mock execution completed successfully."
    st.markdown(
        f"""
        <div style="border: 1px solid #ddd; padding: 10px; border-radius: 5px;">
            <h4>Auto Dev Queue Status</h4>
            <p>{mock_result}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── 메인 대시보드 ────────────────────────────────────────────────────────────

def main():
    st.title("Auto Dev Dashboard")
    _display_status_card()


if __name__ == "__main__":
    main()
