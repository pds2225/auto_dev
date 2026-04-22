import logging
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from queue import Queue

import json

AUTO_DEV_DIR = Path(__file__).parent.parent
HARDEN_PROMPT_FILE = AUTO_DEV_DIR / "Claude Code improve prompt.md"
DEBUG_PROMPT_FILE = AUTO_DEV_DIR / "Codex Debug Prompt (Claude Handoff Optimized).md"
LOG_FILE = Path(__file__).parent / "runner.log"
QUEUE_FILE = Path(__file__).parent / "queue.json"
DEFAULT_CLAUDE_TIMEOUT_SEC = 180
TEST_TIMEOUT_SEC = 120

logger = logging.getLogger("auto_dev.loop_runner")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)


def get_claude_timeout_sec() -> int:
    raw = os.getenv("CLAUDE_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_CLAUDE_TIMEOUT_SEC
    try:
        timeout = int(raw)
        if timeout > 0:
            return timeout
    except ValueError:
        pass
    logger.warning("Invalid CLAUDE_TIMEOUT=%r, falling back to default %s", raw, DEFAULT_CLAUDE_TIMEOUT_SEC)
    return DEFAULT_CLAUDE_TIMEOUT_SEC


class LoopRunner:
    def __init__(self):
        self.project_dir: str = ""
        self.running = False
        self.current_stage = "idle"
        self.current_task = ""
        self.current_task_id = ""
        self.current_task_type = ""
        self.selection_reason = ""
        self.selected_from_section = ""
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

    def _pop_queue(self) -> str | None:
        try:
            if not QUEUE_FILE.exists():
                return None
            queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            if not isinstance(queue, list) or not queue:
                return None
            next_dir = queue.pop(0)
            QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
            return next_dir if Path(next_dir).is_dir() else None
        except Exception as e:
            self._log(f"⚠ 큐 로드 실패: {e}")
            return None

    def _log(self, msg: str):
        self.log_queue.put(msg)
        logger.info(msg)

    def _get_active_section(self, text: str) -> str:
        match = re.search(r"^## Active\s*$", text, flags=re.MULTILINE)
        if not match:
            return ""
        start = match.end()
        next_section = re.search(r"^##\s+", text[start:], flags=re.MULTILINE)
        end = start + next_section.start() if next_section else len(text)
        return text[start:end]

    def _format_task_display(self, day_label: str, task: str) -> str:
        tagged_task_match = re.match(r"^((?:\[[^\]]+\])+\s*)(.+)$", task)
        if tagged_task_match:
            tag_block, remainder = tagged_task_match.groups()
            tags = "".join(re.findall(r"\[[^\]]+\]", tag_block))
            if day_label:
                return f"[{day_label}]{tags} {remainder}"
            return f"{tags} {remainder}"
        return f"[{day_label}] {task}" if day_label else task

    def _clear_current_selection(self):
        self.current_task = ""
        self.current_task_id = ""
        self.current_task_type = ""
        self.selection_reason = ""
        self.selected_from_section = ""

    def _extract_generated_task_id(self, task: str) -> int | None:
        match = re.search(r"\[TASK-(\d+)\]|\bTASK-(\d+)\b", task)
        if not match:
            return None
        task_id = match.group(1) or match.group(2)
        return int(task_id) if task_id else None

    def _build_task_selection(self, day_label: str, task: str, task_type: str, reason: str) -> dict[str, str]:
        task_id_num = self._extract_generated_task_id(task)
        task_id = f"TASK-{task_id_num:02d}" if task_id_num is not None else ""
        return {
            "selected_task_text": self._format_task_display(day_label, task),
            "selected_task_raw": task,
            "selected_task_id": task_id,
            "selected_task_type": task_type,
            "selection_reason": reason,
            "selected_from_section": "Active",
        }

    def _get_next_task_selection(self) -> dict[str, str] | None:
        tasks_path = Path(self.project_dir) / "TASKS.md"
        if not tasks_path.exists():
            self._log("⚠ TASKS.md 파일이 없습니다.")
            return None
        try:
            text = tasks_path.read_text(encoding="utf-8")
            active = self._get_active_section(text)
            if not active.strip():
                self._log("⚠ Active 섹션이 없습니다.")
                return None
            current_day = ""
            first_entry: dict[str, str] | None = None
            newest_generated_entry: dict[str, str] | None = None
            newest_generated_id = -1
            for line in active.splitlines():
                day_match = re.match(r"^###\s+(.+)$", line.strip())
                if day_match:
                    current_day = day_match.group(1).strip()
                    continue
                task_match = re.match(r"^- \[ \] (.+)$", line.strip())
                if task_match:
                    task = task_match.group(1).strip()
                    generated_task_id = self._extract_generated_task_id(task)
                    if generated_task_id is None and "[TASK-" in task:
                        self._log(f"⚠ TASK ID 추출 실패: {task}")
                    if generated_task_id is not None and generated_task_id >= newest_generated_id:
                        newest_generated_id = generated_task_id
                        newest_generated_entry = self._build_task_selection(
                            current_day,
                            task,
                            "generated",
                            "newest_generated_pending",
                        )
                    if first_entry is None:
                        first_entry = self._build_task_selection(
                            current_day,
                            task,
                            "regular_pending",
                            "fallback_selected",
                        )
            return newest_generated_entry or first_entry
        except Exception as e:
            self._log(f"⚠ TASKS.md 읽기 실패: {e}")
            return None

    def _get_next_task_entry(self) -> tuple[str, str] | None:
        selection = self._get_next_task_selection()
        if not selection:
            return None
        return selection["selected_task_text"], selection["selected_task_raw"]

    def _get_next_task(self) -> str | None:
        entry = self._get_next_task_entry()
        return entry[0] if entry else None

    def _mark_task_done(self, task: str):
        tasks_path = Path(self.project_dir) / "TASKS.md"
        if not tasks_path.exists():
            return
        try:
            text = tasks_path.read_text(encoding="utf-8")
            active = self._get_active_section(text)
            if not active:
                return
            updated_active = active.replace(f"- [ ] {task}", f"- [x] {task}", 1)
            updated = text.replace(active, updated_active, 1)
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

    def _run_claude(self, prompt: str, extra_context: str = "") -> tuple[str, int, bool]:
        import json as _json
        import threading as _threading
        full_prompt = prompt
        timeout_sec = get_claude_timeout_sec()
        if extra_context:
            full_prompt += f"\n\n---\n\n{extra_context}"
        try:
            proc = subprocess.Popen(
                [
                    "claude", "-p", full_prompt,
                    "--dangerously-skip-permissions",
                    "--output-format", "stream-json",
                    "--include-partial-messages",
                    "--verbose",
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
                proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                proc.kill()
                self._log(f"⚠ Claude Code 실행 시간 초과 ({timeout_sec}초)")
                return f"오류: claude 실행 시간 초과 ({timeout_sec}초)", 1, True
            t.join(timeout=5)
            return "\n".join(output_lines), proc.returncode, False
        except FileNotFoundError:
            return "오류: claude CLI를 찾을 수 없습니다.", 1, False
        except Exception as e:
            self._log(f"❌ Claude 호출 실패: {e}")
            return f"오류: {e}", 1, False

    def _find_test_dir(self) -> Path:
        """tests/ 폴더가 있는 가장 적합한 디렉토리를 반환."""
        proj = Path(self.project_dir)
        # 서브디렉토리 중 tests/ 가진 것 우선 (예: omni-sync/)
        for sub in sorted(proj.iterdir()):
            if sub.is_dir() and (sub / "tests").is_dir():
                return sub
        return proj

    def _run_tests(self) -> tuple[bool, str]:
        test_dir = self._find_test_dir()
        self._log(f"  📂 테스트 경로: {test_dir.name}")
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "--tb=short", "-q"],
                cwd=str(test_dir),
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
        if not proj.exists() or not proj.is_dir():
            self._log(f"⚠ 프로젝트 경로를 찾을 수 없습니다: {proj}")
            return

        candidates = [proj / "requirements.txt"]
        try:
            candidates.extend(
                subdir / "requirements.txt"
                for subdir in sorted(proj.iterdir())
                if subdir.is_dir()
            )
        except Exception as e:
            self._log(f"⚠ requirements 탐색 실패: {e}")
            return

        for req in candidates:
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

    def _run_scaffold_if_needed(self) -> bool:
        """TASKS.md가 없으면 scaffold_generator를 Claude Code로 자동 실행. 생성됐으면 True."""
        tasks_path = Path(self.project_dir) / "TASKS.md"
        if tasks_path.exists():
            return False
        self._log("📋 TASKS.md 없음 — scaffold 자동 생성 시작")
        prompt = (
            f"D:/auto_dev/ai_project_scaffold_generator.py를 실행해서 "
            f"이 프로젝트({self.project_dir})에 맞는 TASKS.md와 PRD.md를 생성해라. "
            f"프로젝트 경로: {self.project_dir}"
        )
        _, code, _ = self._run_claude(prompt)
        if tasks_path.exists():
            self._log("✅ scaffold 자동 생성 완료")
            return True
        self._log("⚠ scaffold 생성 실패 — TASKS.md 없이 루프 시작 불가")
        return False

    def _run(self):
        try:
            self._log("▶ 루프 시작")
            self._run_scaffold_if_needed()
            selection = self._get_next_task_selection()
            if not selection:
                self._clear_current_selection()
                self.current_stage = "done"
                self._log("✅ 미완료 태스크가 없습니다. 루프 종료.")
                return

            self._install_deps()

            while not self._stop_event.is_set():
                selection = self._get_next_task_selection()
                if not selection:
                    self._clear_current_selection()
                    next_dir = self._pop_queue()
                    if next_dir:
                        self._log(f"📂 다음 프로젝트로 전환: {next_dir}")
                        self.project_dir = next_dir
                        self._install_deps()
                        continue
                    self.current_stage = "done"
                    self._log("✅ 모든 태스크 완료. 루프 종료.")
                    break
                display_task = selection["selected_task_text"]
                task = selection["selected_task_raw"]

                self.current_task = display_task
                self.current_task_id = selection["selected_task_id"]
                self.current_task_type = selection["selected_task_type"]
                self.selection_reason = selection["selection_reason"]
                self.selected_from_section = selection["selected_from_section"]
                log_task_id = self.current_task_id or "-"
                self._log(
                    f"[TASK_SELECT] id={log_task_id} "
                    f"type={self.current_task_type} "
                    f"reason={self.selection_reason} "
                    f"section={self.selected_from_section}"
                )
                self._log(f"\n📌 태스크: {display_task}")

                # ── 0단계: 하드닝 전 기준 테스트 ───────────────────────────
                self.current_stage = "testing"
                self._log("📊 [0/3] 하드닝 전 기준 테스트...")
                pre_passed, pre_output = self._run_tests()
                pre_summary = pre_output.strip().splitlines()[-1] if pre_output.strip() else "결과 없음"
                self._log(f"  기준: {pre_summary}")

                # ── 1단계: Claude Code 하드닝 ──────────────────────────────
                self.current_stage = "hardening"
                self._log("🔨 [1/3] Claude Code 하드닝 실행 중...")
                harden_prompt = self._read_prompt(HARDEN_PROMPT_FILE)
                context = f"현재 태스크: {display_task}\n프로젝트 경로: {self.project_dir}"
                harden_output, harden_code, harden_timed_out = self._run_claude(harden_prompt, context)
                if harden_code != 0:
                    self._log("↻ [1/3] 하드닝 재시도")
                    retry_prompt = harden_prompt or "하드닝 실행"
                    retry_context = f"현재 태스크: {display_task}"
                    harden_output, harden_code, retry_timed_out = self._run_claude(retry_prompt, retry_context)
                    harden_timed_out = harden_timed_out and retry_timed_out
                    if harden_code != 0:
                        if harden_timed_out:
                            self.current_stage = "error"
                            self._log("⚠ Claude Code 타임아웃 2회 연속 발생. 루프 일시 중지 — 수동 확인 필요")
                            break
                        self._log("⚠ 하드닝 실패. 다음 단계로 진행")
                if self._stop_event.is_set():
                    break

                # ── 2단계: 테스트 ───────────────────────────────────────────
                self.current_stage = "testing"
                self._log("🧪 [2/3] 테스트 실행 중...")
                passed, test_output = self._run_tests()
                for line in test_output.splitlines():
                    self._log(f"  {line}")
                post_summary = test_output.strip().splitlines()[-1] if test_output.strip() else "결과 없음"
                self._log(f"  📊 하드닝 효과: [{pre_summary}] → [{post_summary}]")

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
                debug_context = f"현재 태스크: {display_task}\n에러 로그:\n{test_output}"
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


def run_self_tests():
    import tempfile
    import textwrap

    original_timeout = os.environ.get("CLAUDE_TIMEOUT")
    os.environ.pop("CLAUDE_TIMEOUT", None)
    assert get_claude_timeout_sec() == DEFAULT_CLAUDE_TIMEOUT_SEC
    os.environ["CLAUDE_TIMEOUT"] = "240"
    assert get_claude_timeout_sec() == 240
    os.environ["CLAUDE_TIMEOUT"] = "invalid"
    assert get_claude_timeout_sec() == DEFAULT_CLAUDE_TIMEOUT_SEC
    if original_timeout is None:
        os.environ.pop("CLAUDE_TIMEOUT", None)
    else:
        os.environ["CLAUDE_TIMEOUT"] = original_timeout

    with tempfile.TemporaryDirectory() as tmp:
        tasks_path = Path(tmp) / "TASKS.md"
        tasks_path.write_text(
            textwrap.dedent(
                """\
                # Tasks

                ## TASK-01 — First task

                상세 설명

                ## Active

                ### Auto Dev Queue

                - [ ] [TASK-01] First task
                - [ ] [TASK-02] Second task
                """
            ),
            encoding="utf-8",
        )
        runner = LoopRunner()
        runner.project_dir = tmp
        selection = runner._get_next_task_selection()
        assert selection is not None
        assert selection["selected_task_id"] == "TASK-02"
        assert selection["selected_task_type"] == "generated"
        assert selection["selection_reason"] == "newest_generated_pending"

    with tempfile.TemporaryDirectory() as tmp:
        tasks_path = Path(tmp) / "TASKS.md"
        tasks_path.write_text(
            textwrap.dedent(
                """\
                # Tasks

                ## Active

                ### Day 2 - Rule Engine
                - [ ] regular pending task
                - [ ] [TASK-30] earlier generated task
                - [ ] [TASK-31] newest generated task
                """
            ),
            encoding="utf-8",
        )
        runner = LoopRunner()
        runner.project_dir = tmp
        selection = runner._get_next_task_selection()
        assert selection is not None
        assert selection["selected_task_id"] == "TASK-31"
        assert selection["selected_task_type"] == "generated"
        assert selection["selection_reason"] == "newest_generated_pending"

    with tempfile.TemporaryDirectory() as tmp:
        tasks_path = Path(tmp) / "TASKS.md"
        tasks_path.write_text(
            textwrap.dedent(
                """\
                # Tasks

                ## Active

                ### Day 1
                - [ ] regular pending task

                ## Waiting On
                - [ ] ignored generated task
                """
            ),
            encoding="utf-8",
        )
        runner = LoopRunner()
        runner.project_dir = tmp
        selection = runner._get_next_task_selection()
        assert selection is not None
        assert selection["selected_task_id"] == ""
        assert selection["selected_task_type"] == "regular_pending"
        assert selection["selection_reason"] == "fallback_selected"

    with tempfile.TemporaryDirectory() as tmp:
        runner = LoopRunner()
        runner.project_dir = tmp
        selection = runner._get_next_task_selection()
        assert selection is None

        tasks_path = Path(tmp) / "TASKS.md"
        tasks_path.write_text("# Tasks\n\n## Waiting On\n\n- [ ] ignored task\n", encoding="utf-8")
        selection = runner._get_next_task_selection()
        assert selection is None

        tasks_path.write_text("# Tasks\n\n## Active\n\n### Day 1\n\n- [x] done task\n", encoding="utf-8")
        selection = runner._get_next_task_selection()
        assert selection is None

        runner._install_deps()

    with tempfile.TemporaryDirectory() as tmp:
        tasks_path = Path(tmp) / "TASKS.md"
        tasks_path.write_text(
            textwrap.dedent(
                """\
                # Tasks

                ## Active

                ### Day 2
                - [ ] [TASK-03] timeout-prone task
                """
            ),
            encoding="utf-8",
        )

        class TimeoutRunner(LoopRunner):
            def __init__(self):
                super().__init__()
                self.timeout_calls = 0
                self.test_calls = 0

            def _install_deps(self):
                return

            def _read_prompt(self, prompt_file: Path) -> str:
                return "prompt"

            def _run_claude(self, prompt: str, extra_context: str = "") -> tuple[str, int, bool]:
                self.timeout_calls += 1
                return "오류: claude 실행 시간 초과", 1, True

            def _run_tests(self) -> tuple[bool, str]:
                self.test_calls += 1
                if self.test_calls > 1:
                    raise AssertionError("Timeout after hardening should stop before post-hardening tests")
                return False, "0 passed"  # step 0 기준 테스트

        runner = TimeoutRunner()
        runner.project_dir = tmp
        runner.running = True
        runner._run()
        assert runner.current_stage == "error"
        assert runner.timeout_calls == 2
        assert "수동 확인 필요" in "\n".join(list(runner.log_queue.queue))
        assert "- [ ] [TASK-03] timeout-prone task" in tasks_path.read_text(encoding="utf-8")

    # ── _mark_task_done ───────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tasks_path = Path(tmp) / "TASKS.md"
        tasks_path.write_text(
            "# Tasks\n\n## Active\n\n- [ ] [TASK-01] 할 일\n",
            encoding="utf-8",
        )
        r = LoopRunner()
        r.project_dir = tmp
        r._mark_task_done("[TASK-01] 할 일")
        result = tasks_path.read_text(encoding="utf-8")
        assert "- [x] [TASK-01] 할 일" in result
        assert "- [ ] [TASK-01] 할 일" not in result

    # ── _find_test_dir ────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        # 루트에 tests/ 없고 서브디렉토리에만 있을 때 → 서브디렉토리 반환
        sub = Path(tmp) / "my-app"
        sub.mkdir()
        (sub / "tests").mkdir()
        r = LoopRunner()
        r.project_dir = tmp
        assert r._find_test_dir() == sub

    with tempfile.TemporaryDirectory() as tmp:
        # 어디에도 tests/ 없을 때 → 루트 반환
        r = LoopRunner()
        r.project_dir = tmp
        assert r._find_test_dir() == Path(tmp)

    print("self-tests passed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        run_self_tests()
