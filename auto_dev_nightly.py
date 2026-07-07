"""auto_dev_nightly — 멀티 repo 야간 무인 자동개발 엔진 (오케 백엔드).

각 repo의 미완성(열린 PR·실패 테스트·RESUME 다음액션)을 탐지해, 할 일이 있으면
headless claude 로 자동개발(작업브랜치→검증→PR→검증통과 시 병합)을 시킨다.

기본은 DRY-RUN(탐지·계획만, 실제 변경 없음). 실제 무인 실행은 --run.
protected repo(mail 등)는 --run 이어도 안전을 위해 강제 DRY-RUN.

재활용: auto_loop(state/LOCK/retry/headless·임시파일 stdin), auto_agent(멀티repo),
_night_pilot(allowedTools 화이트리스트), work-cockpit(ntfy 알림).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path

# Windows cp949 콘솔 크래시 가드: 출력 스트림을 UTF-8로 재설정
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

BASE_DIR = Path(r"D:\auto_dev")
CONFIG_FILE = BASE_DIR / "auto_dev_nightly_config.json"
STATE_FILE = BASE_DIR / "nightly_state.json"
LOCK_FILE = BASE_DIR / "nightly.lock"
LOG_DIR = BASE_DIR / "logs"
REPORT_FILE = BASE_DIR / "NIGHTLY_REPORT.md"


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_config() -> dict:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 미완성 탐지

def _run(cmd, cwd, timeout=120):
    """서브프로세스 실행 헬퍼. (returncode, stdout, stderr) 반환. cp949 가드."""
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env)
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "", f"TIMEOUT({timeout}s)"
    except Exception as e:  # noqa: BLE001
        return -2, "", f"{type(e).__name__}: {e}"


def detect_open_prs(repo: str) -> list:
    code, out, _ = _run(["gh", "pr", "list", "--state", "open",
                         "--json", "number,title"], cwd=repo, timeout=60)
    if code != 0 or not out.strip():
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []


def _has_tests(repo: str) -> bool:
    p = Path(repo)
    if (p / "pytest.ini").exists() or (p / "conftest.py").exists():
        return True
    if (p / "tests").is_dir():
        return True
    return any(p.glob("test_*.py")) or any(p.glob("*_test.py"))


def detect_failing_tests(repo: str, enabled: bool) -> dict:
    """pytest 실행해 실패 개수 탐지. {ran, passed, failed, summary}."""
    if not enabled or not _has_tests(repo):
        return {"ran": False, "passed": 0, "failed": 0, "summary": "테스트 없음/생략"}
    code, out, err = _run([sys.executable, "-m", "pytest", "-q", "--tb=no"],
                          cwd=repo, timeout=300)
    text = (out + "\n" + err)
    m_pass = re.search(r"(\d+)\s+passed", text)
    m_fail = re.search(r"(\d+)\s+failed", text)
    m_err = re.search(r"(\d+)\s+error", text)
    passed = int(m_pass.group(1)) if m_pass else 0
    failed = (int(m_fail.group(1)) if m_fail else 0) + (int(m_err.group(1)) if m_err else 0)
    last = next((ln for ln in reversed(text.splitlines()) if ln.strip()), "")
    return {"ran": True, "passed": passed, "failed": failed, "summary": last.strip()[:120]}


def detect_resume_actions(repo: str) -> list:
    """RESUME.md 에서 진짜 '할 일'만 추출(과탐 방지 휴리스틱).

    ① 미완 체크박스 '- [ ]' 가 있으면 그것만(가장 명확한 신호).
    ② 없으면 '다음 액션/다음 할 일' 섹션(진행 중 제외)에서
       완료·실행절차·사용법·선택 라인을 뺀 항목만.
    """
    f = Path(repo) / "RESUME.md"
    if not f.exists():
        return []
    text = f.read_text(encoding="utf-8", errors="replace")
    # ① 미완 체크박스가 가장 명확한 신호
    boxes = [re.sub(r"^- \[ \]\s*", "", ln.strip())[:100]
             for ln in text.splitlines() if ln.strip().startswith("- [ ]")]
    if boxes:
        return boxes
    # ② 체크박스가 없으면 '다음 액션' 섹션만(진행 중 제외), 노이즈 라인 제거
    done = re.compile(r"✅|\(완료\)|\[x\]|\bdone\b|완료", re.IGNORECASE)
    guide = re.compile(r"`[^`]*\.(py|ps1|cmd|md)|python\s|\.py\b|실행|붙여넣|입력\s*후|참고|확인\s*끝|최초\s*1회|즉시\s*1회|선택\)")
    actions, capture = [], False
    for ln in text.splitlines():
        s = ln.strip()
        if re.match(r"^#{1,4}\s", s):  # 헤더
            capture = bool(re.search(r"다음\s*(액션|할\s*일)", s)) and not re.search(r"진행\s*중", s)
            continue
        if not capture:
            continue
        if re.match(r"^(\d+[.)]|[-*])\s", s):
            if done.search(s) or guide.search(s):
                continue
            actions.append(re.sub(r"^(\d+[.)]|[-*])\s*", "", s)[:100])
    return actions


def git_sync_state(repo: str) -> dict:
    _run(["git", "fetch", "--all", "--prune"], cwd=repo, timeout=120)
    code, dirty, _ = _run(["git", "status", "--short"], cwd=repo, timeout=30)
    _, ab, _ = _run(["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"],
                    cwd=repo, timeout=30)
    return {"dirty": bool(dirty.strip()), "aheadbehind": ab.strip()}


def detect_incomplete(repo: str, with_tests: bool) -> dict:
    prs = detect_open_prs(repo)
    tests = detect_failing_tests(repo, with_tests)
    actions = detect_resume_actions(repo)
    git = git_sync_state(repo)
    has_work = bool(prs) or tests["failed"] > 0 or bool(actions)
    return {"open_prs": prs, "tests": tests, "resume_actions": actions,
            "git": git, "has_work": has_work}


# ---------------------------------------------------------------- 실제 실행

def build_claude_cmd(repo: str, cfg: dict, tier: str) -> list:
    """tier 별 프롬프트·차단도구 구성.
    merge=PR 병합까지 무인 / pr=PR 생성까지만(병합은 사람, gh pr merge 차단).
    """
    base = (
        "자동개발: 이 repo의 미완성 작업(열린 PR·실패 테스트·RESUME 다음액션)을 완료하라. "
        "각 항목을 작업브랜치에서 구현→테스트 통과→요구사항 추적성 감사 통과→커밋→PR 생성. "
        "[요구사항 추적성 감사(기본)] 커밋/PR 전에, 완료한 작업이 원래 요구사항을 반영했는지 "
        "RESUME.md 핵심 결정·제약, .omc/specs 인수기준, repo CLAUDE.md/AGENTS.md/RULES.md 불변제약과 "
        "1:1로 대조해 file:line 증거로 확인하고, 금지(부재) 요구사항(실제 메일발송·결제 클릭·Secret 출력 등)은 "
        "grep으로 '매칭 0'을 증명하라. 미반영·제약위반이면 수정 후 재감사, 못 고치면 그 항목 BLOCKED. "
        "감사 통과 전에는 커밋/PR/병합으로 넘어가지 마라. 코드로 검증 불가능한 부분은 추측 수정 말고 리포트에 분리 기록. "
        "main 직접 push 금지(작업브랜치→PR만), 파일 삭제 금지(이동은 가능), "
        "실제 메일발송 금지(dry-run), Secret 출력·커밋 금지. 막히면 BLOCKED로 남기고 다음으로."
    )
    disallowed = cfg.get("disallowed_tools", "")
    if tier == "merge":
        prompt = base + (" 테스트가 통과하고 머지 충돌·동시세션 경합이 없으면 "
                         "`gh pr merge`로 병합까지 한다(충돌·테스트 실패 시 병합하지 말고 BLOCKED).")
    else:  # pr (병합 금지)
        prompt = base + (" ⚠️ PR 생성까지만 하고 절대 병합하지 마라 — "
                         "main 반영(gh pr merge·main push)은 아침에 사람이 검토 후 한다.")
        merge_deny = "Bash(gh pr merge:*)"
        disallowed = (disallowed + "," + merge_deny) if disallowed else merge_deny
    return [
        cfg["claude_bin"], "-p", prompt,
        "--add-dir", repo,
        "--permission-mode", "default",
        "--allowedTools", cfg.get("allowed_tools", "Read,Edit,Write,Glob,Grep,Bash"),
        "--disallowedTools", disallowed,
    ]


def run_repo_live(repo: str, cfg: dict, tier: str) -> int:
    cmd = build_claude_cmd(repo, cfg, tier)
    out = LOG_DIR / f"nightly_{Path(repo).name}_{tier}_{stamp()}.txt"
    timeout = int(cfg.get("timeout_seconds", 2400))
    try:
        r = subprocess.run(cmd, capture_output=True, encoding="utf-8",
                           errors="replace", cwd=repo, timeout=timeout)
        out.write_text((r.stdout or "") + "\n---STDERR---\n" + (r.stderr or ""),
                       encoding="utf-8")
        return r.returncode
    except subprocess.TimeoutExpired:
        out.write_text(f"TIMEOUT {timeout}s\n", encoding="utf-8")
        return -1


# ---------------------------------------------------------------- 알림/리포트

def notify_ntfy(cfg: dict, title: str, body: str):
    topic = (cfg.get("ntfy_topic") or "").strip()
    if not topic:
        return
    try:
        ascii_title = title.encode("ascii", "ignore").decode() or "auto-dev nightly"
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
            headers={"Title": ascii_title, "Content-Type": "text/plain; charset=utf-8"})
        urllib.request.urlopen(req, timeout=20)
    except Exception:  # noqa: BLE001
        pass


def write_report(results: list, dry: bool) -> str:
    lines = [f"# auto-dev nightly 리포트 ({now()})",
             f"모드: {'DRY-RUN(탐지·계획만)' if dry else 'LIVE(무인 실행)'}", "",
             "| repo | 열린PR | 실패테스트 | RESUME미완 | 할일 | 처리 |",
             "|---|---|---|---|---|---|"]
    for r in results:
        d = r["detect"]
        lines.append(
            f"| {Path(r['repo']).name} | {len(d['open_prs'])} | "
            f"{d['tests']['failed']}{'' if d['tests']['ran'] else '(-)'} | "
            f"{len(d['resume_actions'])} | {'예' if d['has_work'] else '—'} | {r['action']} |")
    lines.append("")
    for r in results:
        d = r["detect"]
        if not d["has_work"]:
            continue
        lines.append(f"## {Path(r['repo']).name}")
        if d["open_prs"]:
            lines.append("- 열린 PR: " + ", ".join(f"#{p['number']} {p['title']}" for p in d["open_prs"]))
        if d["tests"]["failed"]:
            lines.append(f"- 실패 테스트: {d['tests']['failed']} ({d['tests']['summary']})")
        for a in d["resume_actions"][:8]:
            lines.append(f"- RESUME: {a}")
        if d["git"]["dirty"]:
            lines.append("- ⚠️ 미커밋 변경 있음(dry, 건드리지 않음)")
        lines.append("")
    report = "\n".join(lines)
    REPORT_FILE.write_text(report, encoding="utf-8")
    return report


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="멀티 repo 야간 자동개발 엔진")
    ap.add_argument("--run", action="store_true", help="실제 무인 실행(기본은 dry-run)")
    ap.add_argument("--repo", help="특정 repo 경로만")
    ap.add_argument("--no-tests", action="store_true", help="테스트 탐지 생략(빠름)")
    args = ap.parse_args()

    dry = not args.run
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_config()

    if args.run and LOCK_FILE.exists():
        print(f"이미 실행 중(lock: {LOCK_FILE}). 종료.")
        return 0
    if args.run:
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")

    try:
        repos = cfg["repos"]
        if args.repo:
            want = str(Path(args.repo))
            repos = [r for r in repos if str(Path(r["path"])) == want]
            if not repos:
                repos = [{"path": args.repo, "protected": False}]

        results = []
        for r in repos:
            repo, protected = r["path"], r.get("protected", False)
            if not (Path(repo) / ".git").exists():
                results.append({"repo": repo, "detect": _empty_detect(), "action": "SKIP(노repo)"})
                continue
            print(f"[{now()}] 탐지: {repo}")
            detect = detect_incomplete(repo, with_tests=not args.no_tests)
            tier = (r.get("tier") or "dry").lower()
            if protected:
                tier = "dry"  # 보호 repo는 tier 무시하고 강제 점검만
            if not detect["has_work"]:
                action = "할일없음"
            elif dry:
                action = f"DRY(계획만·예정tier={tier})"
            elif tier == "dry":
                action = "점검만(보호)"
            else:
                code = run_repo_live(repo, cfg, tier)
                action = f"{tier.upper()} exit={code}"
            results.append({"repo": repo, "detect": detect, "action": action})

        report = write_report(results, dry)
        print("\n" + report)
        work = [f"{Path(r['repo']).name}:{r['action']}"
                for r in results if r["detect"]["has_work"]]
        notify_ntfy(cfg, "auto-dev nightly",
                    f"{'DRY' if dry else 'LIVE'} 완료. " + ("; ".join(work) if work else "할일 없음"))
        return 0
    finally:
        if args.run:
            LOCK_FILE.unlink(missing_ok=True)


def _empty_detect() -> dict:
    return {"open_prs": [], "tests": {"ran": False, "passed": 0, "failed": 0, "summary": ""},
            "resume_actions": [], "git": {"dirty": False, "aheadbehind": ""}, "has_work": False}


if __name__ == "__main__":
    sys.exit(main())
