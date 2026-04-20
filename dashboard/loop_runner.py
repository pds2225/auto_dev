import logging
import re
import subprocess
import threading
from pathlib import Path
from queue import Queue

AUTO_DEV_DIR = Path(__file__).parent.parent
HARDEN_PROMPT_FILE = AUTO_DEV_DIR / "Claude Code improve prompt.md"
DEBUG_PROMPT_FILE = AUTO_DEV_DIR / "Codex Debug Prompt (Claude Handoff Optimized).md"
LOG_FILE = Path(__file__).parent / "runner.log"
CLAUDE_TIMEOUT_SEC = 90
TEST_TIMEOUT_SEC = 120

logger = logging.getLogger("auto_dev.loop_runner")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)


class LoopRunner:
    def __init__(self):
        self.project_dir: str = ""
        self.running = False
        self.current_stage = "idle"
        self.current_task = ""
        self.log_queue: Queue = Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self, project_dir: str):
        if self.running:
            return
        self.project_dir = project_dir
        self.running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        self._stop_event.set()
        self.current_stage = "idle"
        self._log("⏹ 루프 중단됨")

    def _log(self, msg: str):
        self.log_queue.put(msg)
        logger.info(msg)

    def _get_next_task(self) -> str | None:
        tasks_path = Path(self.project_dir) / "TASKS.md"
        if not tasks_path.exists():
            return None
        try:
            text = tasks_path.read_text(encoding="utf-8")
            match = re.search(r"- \[ \] (.+)", text)
            return match.group(1).strip() if match else None
        except Exception as e:
            self._log(f"⚠ TASKS.md 읽기 실패: {e}")
            return None

    def _mark_task_done(self, task: str):
        tasks_path = Path(self.project_dir) / "TASKS.md"
        if not tasks_path.exists():
            return
        try:
            text = tasks_path.read_text(encoding="utf-8")
            updated = text.replace(f"- [ ] {task}", f"- [x] {task}", 1)
            tasks_path.write_text(updated, encoding="utf-8")
        except Exception as e:
            self._log(f"⚠ TASKS.md 업데이트 실패: {e}")

    def _read_prompt(self, prompt_file: Path) -> str:
        if prompt_file.exists():
            try:
                return prompt_file.read_text(encoding="utf-8")
            except Exception as e:
                self._log(f"⚠ 프롬프트 읽기 실패 ({prompt_file.name}): {e}")
        return ""

    def _run_claude(self, prompt: str, extra_context: str = "") -> tuple[str, int]:
        import json as _json
        import threading as _threading
        full_prompt = prompt
        if extra_context:
            full_prompt += f"\n\n---\n\n{extra_context}"
        try:
            proc = subprocess.Popen(
                [
                    "claude", "-p", full_prompt,
                    "--dangerously-skip-permissions",
                    "--output-format", "stream-json",
                    "--include-partial-messages",
                ],
                cwd=self.project_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            output_lines = []

            def _reader():
                if proc.stdout is None:
                    return
                try:
                    for raw in proc.stdout:
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            obj = _json.loads(raw)
                            # assistant 텍스트 델타만 추출
                            t = obj.get("type", "")
                            if t == "assistant":
                                for block in obj.get("message", {}).get("content", []):
                                    if block.get("type") == "text":
                                        for ln in block["text"].splitlines():
                                            if ln.strip():
                                                self._log(f"  {ln}")
                                                output_lines.append(ln)
                            elif t == "result":
                                txt = obj.get("result", "")
                                for ln in txt.splitlines():
                                    if ln.strip():
                                        self._log(f"  {ln}")
                                        output_lines.append(ln)
                        except _json.JSONDecodeError:
                            if raw:
                                self._log(f"  {raw}")
                                output_lines.append(raw)
                except Exception as e:
                    self._log(f"⚠ Claude 출력 읽기 실패: {e}")

            t = _threading.Thread(target=_reader, daemon=True)
            t.start()
            try:
                proc.wait(timeout=CLAUDE_TIMEOUT_SEC)
            except subprocess.TimeoutExpired:
                proc.kill()
                self._log("⚠ Claude Code 실행 시간 초과 - 다음 단계로 진행")
                return f"오류: claude 실행 시간 초과 ({CLAUDE_TIMEOUT_SEC}초)", 1
            t.join(timeout=5)
            return "\n".join(output_lines), proc.returncode
        except FileNotFoundError:
            return "오류: claude CLI를 찾을 수 없습니다.", 1
        except Exception as e:
            self._log(f"❌ Claude 호출 실패: {e}")
            return f"오류: {e}", 1

    def _run_tests(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "--tb=short", "-q"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=TEST_TIMEOUT_SEC,
                encoding="utf-8",
                errors="replace",
            )
            output = (result.stdout or "") + (result.stderr or "")
            passed = result.returncode == 0
            return passed, output
        except FileNotFoundError:
            return False, "오류: pytest를 찾을 수 없습니다."
        except subprocess.TimeoutExpired:
            return False, "오류: 테스트 시간 초과 (2분)"
        except Exception as e:
            return False, f"오류: {e}"

    def _install_deps(self):
        proj = Path(self.project_dir)
        for req in [proj / "requirements.txt", proj / "omni-sync" / "requirements.txt"]:
            if req.exists():
                self._log(f"📦 의존성 설치 중: {req.name} ({req.parent.name})")
                try:
                    result = subprocess.run(
                        ["pip", "install", "-r", str(req), "-q"],
                        capture_output=True, text=True, timeout=120, encoding="utf-8",
                    )
                    if result.returncode != 0:
                        self._log(f"  ⚠ pip install 경고: {result.stderr.strip()[:200]}")
                    else:
                        self._log("  ✅ 의존성 설치 완료")
                except Exception as e:
                    self._log(f"  ❌ 의존성 설치 실패: {e}")

    def _run(self):
        try:
            self._log("▶ 루프 시작")
            self._install_deps()

            while not self._stop_event.is_set():
                task = self._get_next_task()
                if not task:
                    self.current_stage = "done"
                    self._log("✅ 모든 태스크 완료. 루프 종료.")
                    break

                self.current_task = task
                self._log(f"\n📌 태스크: {task}")

                # ── 1단계: Claude Code 하드닝 ──────────────────────────────
                self.current_stage = "hardening"
                self._log("🔨 [1/3] Claude Code 하드닝 실행 중...")
                harden_prompt = self._read_prompt(HARDEN_PROMPT_FILE)
                context = f"현재 태스크: {task}\n프로젝트 경로: {self.project_dir}"
                harden_output, harden_code = self._run_claude(harden_prompt, context)
                if harden_code != 0:
                    self._log("↻ [1/3] 하드닝 재시도")
                    retry_prompt = harden_prompt or "하드닝 실행"
                    retry_context = f"현재 태스크: {task}"
                    harden_output, harden_code = self._run_claude(retry_prompt, retry_context)
                    if harden_code != 0:
                        self._log("⚠ 하드닝 실패. 다음 단계로 진행")
                if self._stop_event.is_set():
                    break

                # ── 2단계: 테스트 ───────────────────────────────────────────
                self.current_stage = "testing"
                self._log("🧪 [2/3] 테스트 실행 중...")
                passed, test_output = self._run_tests()
                for line in test_output.splitlines():
                    self._log(f"  {line}")

                if passed:
                    self._log("✅ 테스트 통과!")
                    self._mark_task_done(task)
                    self._log(f"  → [{task}] 완료 처리")
                    continue

                if self._stop_event.is_set():
                    break

                # ── 3단계: Codex 디버그 ─────────────────────────────────────
                self.current_stage = "debug"
                self._log("🐛 [3/3] 테스트 실패. 디버그 실행 중...")
                debug_prompt = self._read_prompt(DEBUG_PROMPT_FILE)
                debug_context = f"현재 태스크: {task}\n에러 로그:\n{test_output}"
                self._run_claude(debug_prompt, debug_context)
                if self._stop_event.is_set():
                    break

                # ── 4단계: 재테스트 ─────────────────────────────────────────
                self.current_stage = "testing"
                self._log("🧪 재테스트 실행 중...")
                passed, test_output = self._run_tests()
                for line in test_output.splitlines():
                    self._log(f"  {line}")

                if passed:
                    self._log("✅ 재테스트 통과!")
                    self._mark_task_done(task)
                    self._log(f"  → [{task}] 완료 처리")
                else:
                    self.current_stage = "error"
                    self._log("⚠ 재테스크도 실패. 루프 일시 중지 — 수동 확인 필요")
                    break
        except Exception as e:
            self.current_stage = "error"
            self._log(f"❌ 루프 내부 오류: {e}")
        finally:
            self.running = False
            if self.current_stage not in {"done", "error"}:
                self.current_stage = "idle"
            self._log("⏹ 루프 가동 중지")


runner = LoopRunner()
