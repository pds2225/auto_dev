import contextlib
import io
import json
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from loop_runner import QUEUE_FILE, runner
from project_snapshot import get_project_snapshot, get_snapshot_note

_SCAFFOLD_GENERATOR = Path(__file__).parent.parent / "ai_project_scaffold_generator.py"
sys.path.insert(0, str(Path(__file__).parent.parent))
from ai_project_scaffold_generator import generate_scaffold

_scaffold_lock = threading.Lock()
_scaffold_state: dict = {"running": False, "log": [], "result": None}

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from auto_dev_prompt_loop import _parse_pending, _build_prompt
from auto_dev_handoff_loop import (
    _build_codex_prompt, _build_claude_prompt, _read_optional, _summarize,
)

app = Flask(__name__)

STATE_FILE = Path(__file__).parent / "loop_state.json"


def _save_state():
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


def _load_state():
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            project_dir = data.get("project_dir", "")
            was_running = data.get("running", False)
            if project_dir and Path(project_dir).exists():
                runner.project_dir = project_dir
                runner.current_task = data.get("current_task", "")
                runner.current_task_id = data.get("current_task_id", "")
                runner.current_task_type = data.get("current_task_type", "")
                runner.selection_reason = data.get("selection_reason", "")
                runner.selected_from_section = data.get("selected_from_section", "")
                if was_running:
                    print(f"[*] 서버 재시작 감지: 루프 자동 복구 중... ({project_dir})")
                    runner.start(project_dir)
        except Exception as e:
            print(f"상태 로드 실패: {e}")


_load_state()


@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({"error": str(e), "message": "서버 내부 오류 발생"}), 500


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/loop/toggle", methods=["POST"])
def toggle():
    try:
        body = request.get_json(silent=True) or {}
        project_dir = str(body.get("project_dir", runner.project_dir)).strip()

        if runner.running:
            runner.stop()
            _save_state()
            return jsonify({"running": False, "message": "루프 중단됨"})

        if not project_dir:
            return jsonify({"error": "project_dir을 입력하세요"}), 400

        project_path = Path(project_dir)
        if not project_path.exists() or not project_path.is_dir():
            return jsonify({"error": f"유효하지 않은 경로입니다: {project_dir}"}), 400

        runner.start(project_dir)
        _save_state()
        return jsonify({"running": True, "message": "루프 시작됨", "project_dir": project_dir})
    except Exception as e:
        return jsonify({"error": str(e), "message": "루프 토글 처리 실패"}), 500


@app.route("/api/loop/state")
def state():
    return jsonify(
        {
            "running": runner.running,
            "current_stage": runner.current_stage,
            "current_task": runner.current_task,
            "current_task_id": runner.current_task_id,
            "current_task_type": runner.current_task_type,
            "selection_reason": runner.selection_reason,
            "selected_from_section": runner.selected_from_section,
            "project_dir": runner.project_dir,
        }
    )


def _read_queue() -> list:
    try:
        if QUEUE_FILE.exists():
            q = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            return q if isinstance(q, list) else []
    except Exception:
        pass
    return []


def _write_queue(queue: list):
    QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


@app.route("/api/queue", methods=["GET"])
def queue_list():
    return jsonify({"queue": _read_queue()})


@app.route("/api/queue", methods=["POST"])
def queue_add():
    body = request.get_json(silent=True) or {}
    project_dir = str(body.get("project_dir", "")).strip()
    if not project_dir or not Path(project_dir).is_dir():
        return jsonify({"error": f"유효하지 않은 경로: {project_dir}"}), 400
    queue = _read_queue()
    if project_dir not in queue:
        queue.append(project_dir)
        _write_queue(queue)
    return jsonify({"queue": queue})


@app.route("/api/queue", methods=["DELETE"])
def queue_remove():
    body = request.get_json(silent=True) or {}
    project_dir = str(body.get("project_dir", "")).strip()
    queue = [p for p in _read_queue() if p != project_dir]
    _write_queue(queue)
    return jsonify({"queue": queue})


@app.route("/api/tasks")
def tasks():
    done, pending = [], []
    if runner.project_dir:
        tasks_path = runner._get_task_file_path()
        if tasks_path.exists():
            try:
                text = tasks_path.read_text(encoding="utf-8")
                active_section = runner._get_active_section(text)
                for line in active_section.splitlines():
                    m = re.match(r"^- \[x\] (.+)$", line.strip())
                    if m:
                        done.append(m.group(1).strip())
                        continue
                    m = re.match(r"^- \[ \] ~~.+~~.*$", line.strip())
                    if m:
                        continue  # 취소선 항목은 집계 제외
                    m = re.match(r"^- \[ \] (.+)$", line.strip())
                    if m:
                        pending.append(m.group(1).strip())
            except Exception:
                pass
    return jsonify({"done": done, "pending": pending, "total": len(done) + len(pending)})


@app.route("/api/loop/stream")
def stream():
    def event_generator():
        last_heartbeat = time.time()
        while True:
            if not runner.log_queue.empty():
                msg = runner.log_queue.get()
                yield f"data: {msg}\n\n"
            else:
                now = time.time()
                if now - last_heartbeat >= 30:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
            time.sleep(0.3)

    return Response(event_generator(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/scaffold", methods=["POST"])
def scaffold_start():
    body = request.get_json(silent=True) or {}
    description = str(body.get("description", "")).strip()
    folder_path = str(body.get("folder_path", "")).strip()
    service_name = str(body.get("service_name", "")).strip()
    tech_stack = str(body.get("tech_stack", "Streamlit")).strip()
    provider = str(body.get("provider", "template")).strip()
    api_key = str(body.get("api_key", "")).strip()

    if not description:
        return jsonify({"error": "description 필요"}), 400
    if not folder_path:
        return jsonify({"error": "folder_path 필요"}), 400

    with _scaffold_lock:
        if _scaffold_state["running"]:
            return jsonify({"error": "이미 실행 중"}), 409
        _scaffold_state["running"] = True
        _scaffold_state["log"] = []
        _scaffold_state["result"] = None

    def _run():
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                result = generate_scaffold(
                    description=description,
                    folder_path=folder_path,
                    service_name=service_name,
                    tech_stack=tech_stack,
                    api_key=api_key,
                    provider=provider,
                )
        except Exception as e:
            result = {"ok": False, "error": str(e)}
        finally:
            lines = [l for l in buf.getvalue().splitlines() if l.strip()]
            with _scaffold_lock:
                _scaffold_state["running"] = False
                _scaffold_state["log"] = lines
                _scaffold_state["result"] = result

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/scaffold/status")
def scaffold_status():
    with _scaffold_lock:
        return jsonify({
            "running": _scaffold_state["running"],
            "log": list(_scaffold_state["log"]),
            "result": _scaffold_state["result"],
        })


@app.route("/api/prompt-generate", methods=["POST"])
def prompt_generate():
    body = request.get_json(silent=True) or {}
    repo_dir = str(body.get("repo_dir", "")).strip()
    mode = str(body.get("mode", "")).strip()
    task_id = str(body.get("task_id", "")).strip() or None
    input_file = str(body.get("input_file", "")).strip() or None

    if not repo_dir:
        return jsonify({"ok": False, "error": "repo_dir을 입력하세요."}), 400
    repo_path = Path(repo_dir)
    if not repo_path.exists() or not repo_path.is_dir():
        return jsonify({"ok": False, "error": f"저장소 경로를 찾을 수 없습니다: {repo_dir}"}), 400
    if mode not in ("task_to_claude", "claude_to_codex", "codex_to_claude"):
        return jsonify({"ok": False, "error": f"지원하지 않는 mode: {mode}"}), 400

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        if mode == "task_to_claude":
            tasks_md = repo_path / "TASKS.md"
            if not tasks_md.exists():
                return jsonify({"ok": False, "error": f"TASKS.md가 없습니다: {tasks_md}"}), 400
            pending = _parse_pending(tasks_md)
            if not pending:
                return jsonify({"ok": False, "error": "아직 시작 전인 할 일(PENDING)이 없습니다."}), 400
            if task_id:
                matched = [(tid, desc) for tid, desc in pending if tid == task_id]
                if not matched:
                    return jsonify({"ok": False, "error": f"{task_id}를 아직 시작 전인 할 일(PENDING)에서 찾을 수 없습니다."}), 400
                sel_id, sel_desc = matched[0]
            else:
                sel_id, sel_desc = pending[0]
            prompt = _build_prompt(sel_id, sel_desc, repo_path)
            out_file = repo_path / f"auto_prompt_{timestamp}.md"
        else:
            if not input_file:
                return jsonify({"ok": False, "error": "input_file 경로를 입력하세요."}), 400
            ip = Path(input_file)
            if not ip.exists():
                return jsonify({"ok": False, "error": f"입력 파일을 찾을 수 없습니다: {input_file}"}), 400
            content = ip.read_text(encoding="utf-8", errors="replace")
            tasks_summary = _summarize(_read_optional(repo_path / "TASKS.md"), 20)
            agents_summary = _read_optional(repo_path / "AGENTS.md")
            if mode == "claude_to_codex":
                prompt = _build_codex_prompt(repo_path, ip, content, tasks_summary, agents_summary)
                out_file = repo_path / f"codex_handoff_{timestamp}.md"
            else:
                prompt = _build_claude_prompt(repo_path, ip, content, tasks_summary, agents_summary)
                out_file = repo_path / f"claude_handoff_{timestamp}.md"

        out_file.write_text(prompt, encoding="utf-8")
        return jsonify({"ok": True, "output_file": str(out_file), "prompt": prompt, "message": "프롬프트 생성 완료"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"프롬프트 생성 중 오류: {e}"}), 500


@app.route("/api/snapshot")
def snapshot():
    repo_dir = request.args.get("repo_dir") or runner.project_dir or str(Path(__file__).parent.parent)
    snapshot_data = get_project_snapshot(repo_dir)
    snapshot_data["note"] = get_snapshot_note(snapshot_data)
    return jsonify(snapshot_data)


if __name__ == "__main__":
    print("대시보드 시작: http://localhost:5000")
    app.run(host="0.0.0.0", debug=False, threaded=True, port=5000)
