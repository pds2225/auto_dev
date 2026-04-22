import json
import re
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from loop_runner import QUEUE_FILE, runner

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
        tasks_path = Path(runner.project_dir) / "TASKS.md"
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


if __name__ == "__main__":
    print("대시보드 시작: http://localhost:5000")
    app.run(host="0.0.0.0", debug=False, threaded=True, port=5000)
