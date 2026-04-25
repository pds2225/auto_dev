from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(repo_dir: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def get_project_snapshot(repo_dir: str | Path) -> dict[str, str | bool]:
    repo_path = Path(repo_dir)
    snapshot: dict[str, str | bool] = {
        "available": False,
        "repo_dir": str(repo_path),
        "branch": "",
        "head": "",
        "remote": "",
        "dirty": False,
        "status": "",
        "error": "",
    }

    try:
        if not repo_path.exists():
            snapshot["error"] = "repo_dir not found"
            return snapshot

        branch = _run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
        head = _run_git(repo_path, ["rev-parse", "--short", "HEAD"])
        remote = _run_git(repo_path, ["remote", "get-url", "origin"])
        status = _run_git(repo_path, ["status", "--short"])

        if not branch and not head:
            snapshot["error"] = "git repo not available"
            return snapshot

        snapshot.update(
            {
                "available": True,
                "branch": branch,
                "head": head,
                "remote": remote,
                "dirty": bool(status.strip()),
                "status": "dirty" if status.strip() else "clean",
            }
        )
        return snapshot
    except Exception as exc:
        snapshot["error"] = str(exc)
        return snapshot


def get_snapshot_note(snapshot: dict[str, str | bool]) -> str:
    if snapshot.get("remote"):
        return f"origin: {snapshot['remote']}"
    if snapshot.get("error"):
        return f"Git 상태를 읽지 못했습니다: {snapshot['error']}"
    return "이 경로는 Git 저장소가 아니거나, 아직 원격이 설정되지 않았습니다."
