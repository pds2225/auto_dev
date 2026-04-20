import json
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from loop_runner import runner

app = Flask(__name__)

STATE_FILE = Path(__file__).parent / "loop_state.json"


def _save_state():
    STATE_FILE.write_text(
        json.dumps(
            {
                "running": runner.running,
                "project_dir": runner.project_dir,
                "current_stage": runner.current_stage,
                "current_task": runner.current_task,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _load_state():
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        runner.project_dir = data.get("project_dir", "")


_load_state()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/loop/toggle", methods=["POST"])
def toggle():
    body = request.get_json(silent=True) or {}
    project_dir = body.get("project_dir", runner.project_dir).strip()

    if runner.running:
        runner.stop()
        _save_state()
        return jsonify({"running": False, "message": "루프 중단됨"})

    if not project_dir:
        return jsonify({"error": "project_dir을 입력하세요"}), 400

    if not Path(project_dir).exists():
        return jsonify({"error": f"경로를 찾을 수 없습니다: {project_dir}"}), 400

    runner.start(project_dir)
    _save_state()
    return jsonify({"running": True, "message": "루프 시작됨", "project_dir": project_dir})


@app.route("/api/loop/state")
def state():
    return jsonify(
        {
            "running": runner.running,
            "current_stage": runner.current_stage,
            "current_task": runner.current_task,
            "project_dir": runner.project_dir,
        }
    )


@app.route("/api/loop/stream")
def stream():
    def event_generator():
        while True:
            if not runner.log_queue.empty():
                msg = runner.log_queue.get()
                yield f"data: {msg}\n\n"
            else:
                yield f"data: \n\n"
            time.sleep(0.3)

    return Response(event_generator(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    print("대시보드 시작: http://localhost:5000")
    app.run(debug=False, threaded=True, port=5000)
