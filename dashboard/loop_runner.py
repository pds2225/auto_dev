import logging
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import ast
from datetime import datetime
from pathlib import Path
from queue import Queue

import json

AUTO_DEV_DIR = Path(__file__).parent.parent
HARDEN_PROMPT_FILE = AUTO_DEV_DIR / "Claude Code improve prompt.md"
DEBUG_PROMPT_FILE = AUTO_DEV_DIR / "Codex Debug Prompt (Claude Handoff Optimized).md"
LOG_FILE = Path(__file__).parent / "runner.log"
QUEUE_FILE = Path(__file__).parent / "queue.json"
DEFAULT_CLAUDE_TIMEOUT_SEC = 180
DEFAULT_CODEX_RETRY_COUNT = 2
TEST_TIMEOUT_SEC = 600
TASK_FILE_CANDIDATES = ("TASK.md", "TASKS.md")
CONTINUE_ON_TEST_FAILURE = os.environ.get("AUTO_DEV_CONTINUE_ON_FAILURE", "true").lower() == "true"
BUILD_TAG = os.getenv(
    "AUTO_DEV_BUILD_TAG",
    datetime.fromtimestamp(Path(__file__).stat().st_mtime).strftime("%Y%m%d-%H%M%S"),
)

logger = logging.getLogger("auto_dev.loop_runner")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)


def get_codex_timeout_sec() -> int:
    raw = os.getenv("CODEX_TIMEOUT", os.getenv("CLAUDE_TIMEOUT", "")).strip()
    if not raw:
        return DEFAULT_CLAUDE_TIMEOUT_SEC
    try:
        timeout = int(raw)
        if timeout > 0:
            return timeout
    except ValueError:
        pass
    logger.warning("Invalid CODEX_TIMEOUT=%r, falling back to default %s", raw, DEFAULT_CLAUDE_TIMEOUT_SEC)
    return DEFAULT_CLAUDE_TIMEOUT_SEC


def get_claude_timeout_sec() -> int:
    return get_codex_timeout_sec()


def get_codex_retry_count() -> int:
    raw = os.getenv("CODEX_RETRY_COUNT", "").strip()
    if not raw:
        return DEFAULT_CODEX_RETRY_COUNT
    try:
        retry_count = int(raw)
        if retry_count > 0:
            return retry_count
    except ValueError:
        pass
    logger.warning("Invalid CODEX_RETRY_COUNT=%r, falling back to default %s", raw, DEFAULT_CODEX_RETRY_COUNT)
    return DEFAULT_CODEX_RETRY_COUNT


class LoopRunner:
    _runner_lock = threading.Lock()
    _active_runner: "LoopRunner | None" = None
    _active_project_dir: str = ""

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
        normalized_project_dir = str(Path(project_dir))
        previous_runner: LoopRunner | None = None
        restart_self = False

        with self.__class__._runner_lock:
            active_runner = self.__class__._active_runner
            active_project_dir = self.__class__._active_project_dir

            if (
                active_runner is self
                and self.running
                and self._thread is not None
                and self._thread.is_alive()
                and active_project_dir == normalized_project_dir
            ):
                self._log(f"⏭ 이미 실행 중 — start 무시 | project={normalized_project_dir}")
                return

            if active_runner is not None and active_runner._thread is not None and active_runner._thread.is_alive():
                if active_runner is self:
                    restart_self = True
                else:
                    previous_runner = active_runner

        if restart_self:
            self._request_stop_for_restart(normalized_project_dir)

        with self.__class__._runner_lock:
            self.project_dir = normalized_project_dir
            self.running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self.__class__._active_runner = self
            self.__class__._active_project_dir = normalized_project_dir

        if previous_runner is not None:
            previous_runner._request_stop_for_restart(normalized_project_dir)

        self._thread.start()

    def stop(self):
        self.running = False
        self._stop_event.set()
        self.current_stage = "idle"
        self._log("⏹ 루프 중단됨")
        self._clear_active_runner_if_self()

    def _request_stop_for_restart(self, next_project_dir: str):
        self._log(f"🔁 기존 러너 정리 후 새 러너 시작 | next_project={next_project_dir}")
        self.stop()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                self._log("⚠ 기존 러너 종료 대기 시간 초과")

    def _clear_active_runner_if_self(self):
        with self.__class__._runner_lock:
            if self.__class__._active_runner is self:
                self.__class__._active_runner = None
                self.__class__._active_project_dir = ""

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

    def _get_project_cwd(self) -> str | None:
        project_dir = (self.project_dir or "").strip()
        return project_dir or None

    def _format_command_for_log(self, cmd: list[str]) -> str:
        return shlex.join([str(part) for part in cmd])

    def _log_command(self, cmd: list[str], cwd: str | None):
        self._log(f"[RUN] cwd={cwd or os.getcwd()} cmd={self._format_command_for_log(cmd)}")

    def _run_project_command(self, cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        cwd = self._get_project_cwd()
        self._log_command(cmd, cwd)
        return subprocess.run(cmd, cwd=cwd, **kwargs)

    def _popen_project_command(self, cmd: list[str], **kwargs) -> subprocess.Popen:
        cwd = self._get_project_cwd()
        self._log_command(cmd, cwd)
        return subprocess.Popen(cmd, cwd=cwd, **kwargs)

    def _get_task_file_path(self) -> Path:
        project_root = Path(self.project_dir)
        for name in TASK_FILE_CANDIDATES:
            candidate = project_root / name
            if candidate.exists():
                return candidate
        return project_root / TASK_FILE_CANDIDATES[0]

    def _task_file_label(self) -> str:
        return self._get_task_file_path().name

    def _get_active_section(self, text: str) -> str:
        match = re.search(r"^## Active\s*$", text, flags=re.MULTILINE)
        if not match:
            return ""
        start = match.end()
        next_section = re.search(r"^##\s+", text[start:], flags=re.MULTILINE)
        end = start + next_section.start() if next_section else len(text)
        return text[start:end]

    def _get_pending_section(self, text: str) -> str:
        match = re.search(r"^## PENDING\s*$", text, flags=re.MULTILINE)
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
        tasks_path = self._get_task_file_path()
        if not tasks_path.exists():
            self._log(f"⚠ {tasks_path.name} 파일이 없습니다.")
            return None
        try:
            text = tasks_path.read_text(encoding="utf-8")
            active = self._get_active_section(text)
            current_day = ""
            first_entry: dict[str, str] | None = None
            lowest_generated_entry: dict[str, str] | None = None
            lowest_generated_id: int | None = None
            for line in active.splitlines():
                day_match = re.match(r"^###\s+(.+)$", line.strip())
                if day_match:
                    current_day = day_match.group(1).strip()
                    continue
                task_match = re.match(r"^- \[ \] (.+)$", line.strip())
                if task_match:
                    task = task_match.group(1).strip()
                    # TASK-XX: 콜론 형식 → [TASK-XX] 형식으로 정규화
                    task = re.sub(r"^(TASK-\d+):\s*", r"[\1] ", task)
                    generated_task_id = self._extract_generated_task_id(task)
                    if generated_task_id is None and "[TASK-" in task:
                        self._log(f"⚠ TASK ID 추출 실패: {task}")
                    if generated_task_id is not None and (
                        lowest_generated_id is None or generated_task_id < lowest_generated_id
                    ):
                        lowest_generated_id = generated_task_id
                        lowest_generated_entry = self._build_task_selection(
                            current_day,
                            task,
                            "generated",
                            "lowest_generated_pending",
                        )
                    if first_entry is None:
                        first_entry = self._build_task_selection(
                            current_day,
                            task,
                            "regular_pending",
                            "fallback_selected",
                        )
            # Active에서 미완료 태스크가 없으면 PENDING 섹션도 확인 (fallback)
            if first_entry is None and lowest_generated_entry is None:
                pending = self._get_pending_section(text)
                for line in pending.splitlines():
                    pm = re.match(r"^- (TASK-[\w-]+):\s*(.+)$", line.strip())
                    if pm:
                        task = f"[{pm.group(1)}] {pm.group(2).strip()}"
                        generated_task_id = self._extract_generated_task_id(task)
                        if generated_task_id is not None and (
                            lowest_generated_id is None or generated_task_id < lowest_generated_id
                        ):
                            lowest_generated_id = generated_task_id
                            lowest_generated_entry = self._build_task_selection(
                                "", task, "generated", "lowest_generated_pending",
                            )
                            lowest_generated_entry["selected_from_section"] = "PENDING"
                        if first_entry is None:
                            first_entry = self._build_task_selection(
                                "", task, "regular_pending", "fallback_selected",
                            )
                            first_entry["selected_from_section"] = "PENDING"
                if first_entry is None and lowest_generated_entry is None:
                    self._log("⚠ Active 섹션이 없습니다.")
            return lowest_generated_entry or first_entry
        except Exception as e:
            self._log(f"⚠ {tasks_path.name} 읽기 실패: {e}")
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
        tasks_path = self._get_task_file_path()
        if not tasks_path.exists():
            return
        try:
            text = tasks_path.read_text(encoding="utf-8")
            updated = text
            active = self._get_active_section(text)
            if active:
                updated_active = active.replace(f"- [ ] {task}", f"- [x] {task}", 1)
                # [TASK-XX] 정규화 형식인 경우 원본 TASK-XX: 콜론 형식도 시도
                if updated_active == active:
                    colon_task = re.sub(r"^\[TASK-(\d+)\]\s*", r"TASK-\1: ", task)
                    if colon_task != task:
                        updated_active = active.replace(f"- [ ] {colon_task}", f"- [x] {colon_task}", 1)
                updated = text.replace(active, updated_active, 1)
            # Active 업데이트 실패 시 PENDING 섹션에서 DONE으로 이동 시도
            if updated == text:
                updated = self._move_pending_task_to_done(text, task)
            tasks_path.write_text(updated, encoding="utf-8")
        except Exception as e:
            self._log(f"⚠ {tasks_path.name} 업데이트 실패: {e}")

    def _move_pending_task_to_done(self, text: str, task: str) -> str:
        colon_id = re.sub(r"^\[(TASK-[\w-]+)\]\s*", r"\1: ", task)
        if colon_id == task:
            return text
        task_key = colon_id.split(":")[0].strip()
        line_re = re.compile(rf"^- {re.escape(task_key)}:[^\n]*\n?", re.MULTILINE)
        if not line_re.search(text):
            return text
        updated = line_re.sub("", text, count=1)
        updated = re.sub(r"\n{3,}", "\n\n", updated)
        done_m = re.search(r"^## DONE\s*$", updated, flags=re.MULTILINE)
        if done_m:
            timestamp = datetime.now().strftime("%Y-%m-%d")
            task_desc = colon_id.split(":", 1)[1].strip() if ":" in colon_id else ""
            new_line = f"\n- {task_key}: {task_desc} ({timestamp})"
            updated = updated[:done_m.end()] + new_line + updated[done_m.end():]
        return updated

    def _read_prompt(self, prompt_file: Path) -> str:
        if prompt_file.exists():
            try:
                return prompt_file.read_text(encoding="utf-8")
            except Exception as e:
                self._log(f"⚠ 프롬프트 읽기 실패 ({prompt_file.name}): {e}")
        return ""

    def _build_codex_command(
        self, full_prompt: str, last_message_path: str, *, bypass_sandbox: bool = False
    ) -> list[str]:
        cmd = ["codex", "exec"]
        if bypass_sandbox:
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            cmd.append("--full-auto")
        cmd += [
            "--skip-git-repo-check",
            "--ephemeral",
            "--json",
            "-o", last_message_path,
            full_prompt,
        ]
        return cmd

    def _extract_codex_json_lines(self, raw: str) -> list[str]:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return [raw.strip()] if raw.strip() else []
        if not isinstance(obj, dict):
            return []

        lines: list[str] = []

        def _add(text: object) -> None:
            if isinstance(text, str):
                for ln in text.strip().splitlines():
                    cleaned = ln.strip()
                    if cleaned and len(cleaned) <= 2000:
                        lines.append(cleaned)

        event_type = obj.get("type", "")

        # codex JSONL 이벤트 형식 우선 처리
        if event_type == "assistant":
            for block in obj.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    _add(block.get("text", ""))
        elif event_type == "result":
            _add(obj.get("result", ""))
        elif event_type in {"error", "system"}:
            _add(obj.get("message", obj.get("error", "")))
        elif event_type == "tool_result":
            for block in obj.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    _add(block.get("text", ""))
        else:
            # 알 수 없는 이벤트 — 재귀 탐색 fallback (depth 제한)
            def _walk(value: object, depth: int = 0) -> None:
                if depth > 4:
                    return
                if isinstance(value, dict):
                    for key, nested in value.items():
                        if key in {"text", "result", "error"} and isinstance(nested, str):
                            _add(nested)
                        else:
                            _walk(nested, depth + 1)
                elif isinstance(value, list):
                    for item in value:
                        _walk(item, depth + 1)
            _walk(obj)

        return lines

    def _save_prompt_fallback(self, prompt: str) -> str:
        """CLI 없을 때 프롬프트를 파일로 저장 후 경로 반환."""
        from datetime import datetime as _dt
        ts = _dt.now().strftime("%m%d_%H%M%S")
        out = Path(self.project_dir) / f"auto_prompt_{ts}.md"
        try:
            out.write_text(prompt, encoding="utf-8")
        except Exception:
            out = Path(__file__).parent / f"auto_prompt_{ts}.md"
            out.write_text(prompt, encoding="utf-8")
        return str(out)

    _PERM_RE = re.compile(
        r"permission.denied|access.denied|requires.approval|sandbox.violation"
        r"|approval.required|needs.approval|approval.request",
        re.I,
    )
    _AUTH_RE = re.compile(r"\b401\b|unauthorized|invalid.api.key", re.I)
    _RATE_RE = re.compile(r"\b429\b|rate.limit|too.many.requests", re.I)

    _CODEX_SAFETY_NOTE = (
        "승인 요청이 필요한 작업은 실행하지 말고 BLOCKED로 보고하라. "
        "네트워크 설치, 외부 다운로드, destructive git 명령, 시스템 경로 수정은 승인 없이 수행하지 마라."
    )

    def _classify_codex_error(self, output: str, returncode: int) -> str:
        """오류 유형 반환: 'perm' | 'auth' | 'rate' | 'other'"""
        if self._AUTH_RE.search(output):
            return "auth"
        if self._RATE_RE.search(output):
            return "rate"
        if returncode == 126 or self._PERM_RE.search(output):
            return "perm"
        return "other"

    def _run_codex(
        self, prompt: str, extra_context: str = "", *, bypass_sandbox: bool = False
    ) -> tuple[str, int, bool]:
        full_prompt = prompt + "\n\n---\n\n" + self._CODEX_SAFETY_NOTE
        timeout_sec = get_codex_timeout_sec()
        if extra_context:
            full_prompt += f"\n\n---\n\n{extra_context}"

        last_message_fd, last_message_path = tempfile.mkstemp(
            prefix="codex-last-message-",
            suffix=".txt",
            dir=self.project_dir if self.project_dir else None,
        )
        os.close(last_message_fd)

        try:
            cmd = self._build_codex_command(full_prompt, last_message_path, bypass_sandbox=bypass_sandbox)
            proc = self._popen_project_command(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            output_lines: list[str] = []

            def _reader(pipe, label: str):
                if pipe is None:
                    return
                try:
                    for raw in pipe:
                        raw = raw.strip()
                        if not raw:
                            continue
                        parsed_lines = self._extract_codex_json_lines(raw) if label == "stdout" else [raw]
                        for line in parsed_lines:
                            cleaned = line.strip()
                            if not cleaned:
                                continue
                            self._log(f"  {cleaned}")
                            output_lines.append(cleaned)
                except Exception as e:
                    self._log(f"⚠ Codex {label} 읽기 실패: {e}")

            stdout_thread = threading.Thread(target=_reader, args=(proc.stdout, "stdout"), daemon=True)
            stderr_thread = threading.Thread(target=_reader, args=(proc.stderr, "stderr"), daemon=True)
            stdout_thread.start()
            stderr_thread.start()
            try:
                proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                proc.kill()
                self._log(f"⚠ Codex 실행 시간 초과 ({timeout_sec}초)")
                return f"오류: codex 실행 시간 초과 ({timeout_sec}초)", 1, True
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)

            try:
                last_message = Path(last_message_path).read_text(encoding="utf-8").strip()
            except Exception:
                last_message = ""
            if last_message:
                for line in last_message.splitlines():
                    cleaned = line.strip()
                    if cleaned:
                        self._log(f"  {cleaned}")
                        output_lines.append(cleaned)

            return "\n".join(output_lines), proc.returncode, False
        except FileNotFoundError:
            saved = self._save_prompt_fallback(full_prompt)
            self._log(f"⚠ Codex CLI 없음 → 프롬프트 저장: {saved}")
            return f"[FALLBACK] 프롬프트 저장됨: {saved}", 0, False
        except Exception as e:
            self._log(f"❌ Codex 호출 실패: {e}")
            saved = self._save_prompt_fallback(full_prompt)
            self._log(f"  → 프롬프트 저장: {saved}")
            return f"[FALLBACK] {e}", 0, False
        finally:
            try:
                Path(last_message_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _run_codex_with_retries(
        self, prompt: str, extra_context: str = "", stage_label: str = "Codex 실행"
    ) -> tuple[str, int, bool]:
        attempts = get_codex_retry_count()
        collected_outputs: list[str] = []
        last_code = 1
        last_timed_out = False
        bypass = False

        for attempt in range(1, attempts + 1):
            if attempt > 1:
                self._log(f"↻ {stage_label} 재시도 ({attempt}/{attempts})"
                          + (" [bypass-sandbox]" if bypass else ""))
            output, code, timed_out = self._run_codex(prompt, extra_context, bypass_sandbox=bypass)
            if output:
                collected_outputs.append(output)
            last_code = code
            last_timed_out = timed_out

            if code == 0:
                break

            if self._stop_event.is_set():
                break

            error_kind = self._classify_codex_error(output, code)

            if error_kind == "auth":
                self._log(f"  ❌ 인증 오류 — 재시도 불가")
                break

            if error_kind == "perm":
                if not bypass:
                    self._log("  🔓 권한/승인 오류 → --dangerously-bypass-approvals-and-sandbox 재시도")
                    bypass = True
                    continue
                self._log("  ⚠ 승인 필요 또는 권한 문제로 해당 태스크를 건너뜁니다 (bypass 재시도 후에도 실패)")
                break

            if attempt < attempts:
                if error_kind == "rate":
                    delay_sec = 30
                    self._log(f"  ⏳ 레이트리밋 — {delay_sec}초 대기 후 재시도")
                else:
                    delay_sec = min(5 * attempt, 15)
                    self._log(f"  ⏳ {delay_sec}초 후 재시도")
                time.sleep(delay_sec)

        return "\n".join(collected_outputs), last_code, last_timed_out

    def _run_claude(self, prompt: str, extra_context: str = "") -> tuple[str, int, bool]:
        return self._run_codex(prompt, extra_context)

    def _find_test_dir(self) -> Path:
        """tests/ 폴더가 있는 가장 적합한 루트를 반환."""
        proj = Path(self.project_dir)
        # 1순위: TASKS.md의 'cd <path> && pytest' 힌트
        for fname in ("TASKS.md", "TASK.md"):
            tasks_path = proj / fname
            if tasks_path.exists():
                try:
                    text = tasks_path.read_text(encoding="utf-8")
                    import re as _re
                    m = _re.search(r"cd\s+([\w./\\-]+)\s*&&.*pytest", text)
                    if m:
                        candidate = proj / m.group(1).strip()
                        if candidate.is_dir():
                            return candidate
                except Exception:
                    pass
        # 2순위: 루트 바로 아래 tests/
        if (proj / "tests").is_dir():
            return proj
        # 3순위: 1단계 서브디렉토리 (omni-sync/ 등)
        for sub in sorted(proj.iterdir()):
            if sub.is_dir() and (sub / "tests").is_dir():
                return sub
        # 4순위: services/*/tests, apps/*/tests 패턴 (marketgate 등)
        for parent_name in ("services", "apps"):
            parent = proj / parent_name
            if parent.is_dir():
                for sub in sorted(parent.iterdir()):
                    if sub.is_dir() and (sub / "tests").is_dir():
                        return sub
        # 5순위: 2단계 전체 탐색
        for sub in sorted(proj.iterdir()):
            if sub.is_dir():
                for sub2 in sorted(sub.iterdir()):
                    if sub2.is_dir() and (sub2 / "tests").is_dir():
                        return sub2
        return proj

    def _find_test_targets(self) -> list[str]:
        """pytest 대상으로 넘길 tests 경로 목록을 반환. 여러 tests/ 디렉토리 모두 수집."""
        proj = Path(self.project_dir)
        targets: list[Path] = []
        try:
            for tests_dir in proj.rglob("tests"):
                if not tests_dir.is_dir():
                    continue
                if any(part in self._SKIP_DIRS for part in tests_dir.parts):
                    continue
                targets.append(tests_dir)
        except Exception as e:
            self._log(f"⚠ tests 탐색 실패: {e}")
            return ["."]

        if not targets:
            return ["."]

        ordered = sorted(
            {path.resolve() for path in targets},
            key=lambda path: (len(path.relative_to(proj).parts), str(path.relative_to(proj)).casefold()),
        )
        return [os.path.relpath(path, proj) for path in ordered]

    def _run_tests(self) -> tuple[bool, str]:
        # TASKS.md 힌트 → _find_test_dir()이 올바른 cwd 반환
        test_dir = self._find_test_dir()
        self._log(f"  📂 테스트 경로: {test_dir.name}")
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests", "--tb=short", "-q"],
                cwd=str(test_dir),
                capture_output=True,
                text=True,
                timeout=TEST_TIMEOUT_SEC,
                encoding="utf-8",
                errors="replace",
            )
            output = (result.stdout or "") + (result.stderr or "")
            # 출력이 없거나 테스트가 없는 경우(exit 5) → 경고 후 통과 처리
            if not output.strip() or result.returncode == 5:
                self._log("  ⚠ 테스트 없음 — 다음 태스크로 진행")
                return True, output
            passed = result.returncode == 0
            return passed, output
        except FileNotFoundError:
            return False, "오류: pytest를 찾을 수 없습니다."
        except subprocess.TimeoutExpired:
            return False, f"오류: 테스트 시간 초과 ({TEST_TIMEOUT_SEC}초)"
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
                req_target = os.path.relpath(req, proj)
                self._log(f"📦 의존성 설치 중: {req_target} ({req.parent.name})")
                try:
                    result = self._run_project_command(
                        ["pip", "install", "-r", req_target, "-q"],
                        capture_output=True, text=True, timeout=120, encoding="utf-8",
                    )
                    if result.returncode != 0:
                        self._log(f"  ⚠ pip install 경고: {result.stderr.strip()[:200]}")
                    else:
                        self._log("  ✅ 의존성 설치 완료")
                except Exception as e:
                    self._log(f"  ❌ 의존성 설치 실패: {e}")

    _CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".rs", ".kt"}
    _SKIP_DIRS = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build"}

    def _detect_code_files(self) -> list[Path]:
        proj = Path(self.project_dir)
        return [
            f for f in proj.rglob("*")
            if f.suffix in self._CODE_EXTS
            and not any(p in self._SKIP_DIRS for p in f.parts)
        ]

    def _run_scaffold_if_needed(self) -> bool:
        """TASK.md 또는 TASKS.md가 없으면 프로젝트 상태에 따라 적절한 방법으로 생성."""
        tasks_path = self._get_task_file_path()
        if tasks_path.exists():
            return False
        self._log(f"📋 {tasks_path.name} 없음 — scaffold 생성 시작")
        code_files = self._detect_code_files()
        if code_files:
            self._log(f"  📂 기존 코드 {len(code_files)}개 감지 → 코드 분석 후 {tasks_path.name} 생성")
            return self._scaffold_from_code_analysis(code_files)
        self._log("  🌱 코드 파일 없음 → template provider scaffold 분기")
        return self._scaffold_from_template()

    def _scaffold_from_template(self) -> bool:
        """빈 프로젝트: scaffold_generator 템플릿으로 태스크 파일 생성."""
        tasks_path = self._get_task_file_path()
        folder_name = Path(self.project_dir).name
        try:
            self._log(f"[SCAFFOLD] provider=template build_tag={BUILD_TAG}")
            result = self._run_project_command(
                [
                    "python",
                    str(AUTO_DEV_DIR / "ai_project_scaffold_generator.py"),
                    "--description", folder_name,
                    "--path", self.project_dir,
                    "--stack", "Streamlit",
                    "--provider", "template",
                ],
                capture_output=True, text=True, timeout=120,
                encoding="utf-8", errors="replace",
            )
            for line in (result.stdout or "").splitlines():
                if line.strip():
                    self._log(f"  {line}")
            if result.returncode != 0:
                for line in (result.stderr or "").splitlines():
                    if line.strip():
                        self._log(f"  ⚠ {line}")
            if tasks_path.exists():
                self._log("✅ scaffold 자동 생성 완료")
                return True
            self._log(f"⚠ scaffold 생성 실패 — {tasks_path.name} 없이 루프 시작 불가")
            return False
        except subprocess.TimeoutExpired:
            self._log("⚠ scaffold 생성 시간 초과 (120초)")
            return False
        except Exception as e:
            self._log(f"⚠ scaffold 실행 오류: {e}")
            return False

    def summarize_codebase(self, code_files: list[Path]) -> str:
        """전체 원문 대신 구조 요약만 LLM에 전달한다."""
        proj = Path(self.project_dir)
        prioritized: list[Path] = []
        for name in ("CLAUDE.md", "README.md"):
            candidate = proj / name
            if candidate.exists():
                prioritized.append(candidate)
        remaining = [f for f in code_files if f not in prioritized]
        top_code = sorted(remaining, key=lambda f: f.stat().st_size, reverse=True)[:8]
        targets = prioritized + top_code

        sections = [f"PROJECT: {proj.name}", f"BUILD_TAG: {BUILD_TAG}"]
        for path in targets:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                sections.append(f"- file: {path.relative_to(proj)}")
                sections.append(f"  read_error: {exc}")
                continue

            imports: list[str] = []
            functions: list[str] = []
            classes: list[str] = []
            entrypoint = "none"
            risks: list[str] = []

            if path.suffix == ".py":
                try:
                    tree = ast.parse(text)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            imports.extend(alias.name for alias in node.names[:5])
                        elif isinstance(node, ast.ImportFrom):
                            mod = node.module or ""
                            imports.append(mod)
                        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            functions.append(node.name)
                        elif isinstance(node, ast.ClassDef):
                            classes.append(node.name)
                    if re.search(r'if\s+__name__\s*==\s*[\'"]__main__[\'"]', text):
                        entrypoint = "__main__"
                    elif re.search(r"\b(app|main|run|start)\s*\(", text):
                        entrypoint = "callable-detected"
                except SyntaxError:
                    risks.append("python-parse-error")
            else:
                imports = re.findall(r'^\s*(?:import|from|require\(|use\s+)\s*([A-Za-z0-9_./-]+)', text, flags=re.MULTILINE)[:8]
                functions = re.findall(r'\b(?:function|def|async function|class)\s+([A-Za-z_][A-Za-z0-9_]*)', text)[:10]
                if re.search(r"\b(main|start|listen|serve)\b", text):
                    entrypoint = "keyword-detected"

            lower_text = text.lower()
            if "os.environ.get(" in text and ('"' in text or "'" in text):
                risks.append("env-fallback-present")
            if "subprocess" in lower_text or "shell=true" in lower_text:
                risks.append("subprocess-usage")
            if "openai" in lower_text or "anthropic" in lower_text or "claude" in lower_text:
                risks.append("llm-coupling")
            if "monitor.py" in path.name.lower():
                risks.append("large-monitor-file")

            import_list = list(dict.fromkeys(i for i in imports if i))[:10]
            function_list = list(dict.fromkeys(functions))[:12]
            class_list = list(dict.fromkeys(classes))[:8]
            risk_list = list(dict.fromkeys(risks))

            sections.append(f"- file: {path.relative_to(proj)}")
            sections.append(f"  imports: {', '.join(import_list) or 'none'}")
            sections.append(f"  functions: {', '.join(function_list) or 'none'}")
            sections.append(f"  classes: {', '.join(class_list) or 'none'}")
            sections.append(f"  entrypoint: {entrypoint}")
            sections.append(f"  core_risk_estimate: {', '.join(risk_list) or 'none'}")
        return "\n".join(sections)

    def _write_existing_safe_tasks(self, summary: str) -> bool:
        tasks_path = self._get_task_file_path()
        proj_name = Path(self.project_dir).name
        task_doc_name = tasks_path.name
        summary_lines = [line for line in summary.splitlines() if line.startswith("- file: ")][:5]
        focus = "\n".join(summary_lines) or "- file: existing codebase"
        doc = (
            f"# {task_doc_name} — {proj_name} / Based on: Existing Safe Fallback\n\n"
            f"Codex 분석 실패 시 기존 코드 구조 요약 기반으로 생성됨.\n\n"
            f"## Analysis Summary\n\n{focus}\n\n"
            f"## Task Details\n\n"
            f"### TASK-01 Existing behavior snapshot\n"
            f"- 현재 진입점과 실행 흐름을 재현 가능한 명령어로 고정한다.\n"
            f"- 수락 기준: 핵심 실행 경로 1개 이상 문서화.\n"
            f"- 수락 기준: 실패 로그 위치 확인 가능.\n"
            f"- 검증: pytest 또는 수동 실행 절차 기록.\n\n"
            f"### TASK-02 High-risk branch hardening\n"
            f"- 요약에서 식별된 위험 분기를 우선 보강한다.\n"
            f"- 수락 기준: 예외 처리 추가.\n"
            f"- 수락 기준: 잘못된 provider/entry 흐름 차단.\n"
            f"- 검증: 실패 케이스 재현.\n\n"
            f"### TASK-03 Regression coverage\n"
            f"- 현재 버그 재현 테스트를 추가한다.\n"
            f"- 수락 기준: 정상/예외/회귀 케이스 포함.\n"
            f"- 수락 기준: 자동 실행 가능.\n"
            f"- 검증: pytest.\n\n"
            f"### TASK-04 Logging and observability\n"
            f"- 시작 로그와 주요 분기 로그를 강화한다.\n"
            f"- 수락 기준: build tag 및 provider 분기 확인 가능.\n"
            f"- 수락 기준: 실패 지점 추적 가능.\n"
            f"- 검증: runner.log 확인.\n\n"
            f"### TASK-05 Safe incremental cleanup\n"
            f"- 동작을 바꾸지 않는 범위에서 중복/취약 분기를 정리한다.\n"
            f"- 수락 기준: 기존 핵심 흐름 유지.\n"
            f"- 수락 기준: 새 회귀 없음.\n"
            f"- 검증: 테스트 재실행.\n\n"
            f"## Active\n\n"
            f"### Auto Dev Queue\n\n"
            f"- [ ] [TASK-01] Existing behavior snapshot\n"
            f"- [ ] [TASK-02] High-risk branch hardening\n"
            f"- [ ] [TASK-03] Regression coverage\n"
            f"- [ ] [TASK-04] Logging and observability\n"
            f"- [ ] [TASK-05] Safe incremental cleanup\n"
        )
        tasks_path.write_text(doc, encoding="utf-8")
        self._log(f"✅ existing-safe fallback {tasks_path.name} 생성 완료")
        return True

    def _scaffold_from_code_analysis(self, code_files: list[Path]) -> bool:
        """기존 코드 분석 → Codex가 실제 코드 기반 태스크 파일 직접 생성."""
        tasks_path = self._get_task_file_path()
        proj = Path(self.project_dir)
        summary = self.summarize_codebase(code_files)

        prompt = (
            f"아래는 '{proj.name}' 프로젝트의 구조 요약이다. 전체 파일 원문이 아니라 요약만 제공된다.\n\n"
            + summary
            + f"\n\n위 요약을 분석해서 이 프로젝트에 실제로 필요한 개선·구현 작업을 {tasks_path.name}로 작성해라.\n\n"
            f"[규칙]\n"
            f"1. 이미 잘 구현된 기능은 태스크로 만들지 않는다\n"
            f"2. 실제로 부족하거나 개선이 필요한 부분만 5~7개 태스크로 만든다\n"
            f"3. 각 태스크는 구체적이고 실행 가능하게 작성한다\n"
            f"4. monitor.py 같은 대형 파일은 원문 전체를 요구하지 말고 요약만 기준으로 판단한다\n"
            f"4. 파일 마지막에 반드시 아래 형식의 Active 섹션 포함:\n\n"
            f"## Active\n\n### Auto Dev Queue\n\n"
            f"- [ ] [TASK-01] 태스크 제목\n- [ ] [TASK-02] 태스크 제목\n...\n\n"
            f"{tasks_path.name} 파일을 {self.project_dir} 에 저장해라."
        )

        self._log(f"🔍 코드 분석 중... build_tag={BUILD_TAG}")
        self._log(f"[SCAFFOLD] provider=codex-analysis summary_chars={len(summary)}")
        _, code, _ = self._run_codex_with_retries(prompt, stage_label="코드 분석")

        if tasks_path.exists():
            self._log(f"✅ 코드 분석 기반 {tasks_path.name} 생성 완료")
            return True
        self._log("⚠ Codex 분석 실패 — existing-safe fallback 시도")
        if self._write_existing_safe_tasks(summary):
            return True
        self._log("⚠ existing-safe fallback 실패 — template provider로 재시도")
        return self._scaffold_from_template()

    def _run(self):
        try:
            self._log(f"▶ 루프 시작 | build_tag={BUILD_TAG} | pid={os.getpid()} | project={self.project_dir}")
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

                # ── 1단계: Codex 하드닝 ───────────────────────────────────
                self.current_stage = "hardening"
                self._log("🔨 [1/3] Codex 하드닝 실행 중...")
                harden_prompt = self._read_prompt(HARDEN_PROMPT_FILE)
                context = f"현재 태스크: {display_task}\n프로젝트 경로: {self.project_dir}"
                harden_output, harden_code, harden_timed_out = self._run_codex_with_retries(
                    harden_prompt,
                    context,
                    stage_label="[1/3] 하드닝",
                )
                if harden_code != 0:
                    if harden_timed_out:
                        self.current_stage = "error"
                        self._log("⚠ Codex 타임아웃 재시도 한도 초과. 루프 일시 중지 — 수동 확인 필요")
                        break
                    self._log("⚠ Codex 하드닝 실패. 다음 단계로 진행")
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
                debug_output, debug_code, debug_timed_out = self._run_codex_with_retries(
                    debug_prompt,
                    debug_context,
                    stage_label="[3/3] 디버그",
                )
                if debug_code != 0:
                    if debug_timed_out:
                        self._log("⚠ Codex 디버그가 재시도 후에도 시간 초과되었습니다.")
                    elif debug_output:
                        self._log("⚠ Codex 디버그가 실패했지만 재테스트는 계속 진행합니다.")
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
                    if CONTINUE_ON_TEST_FAILURE:
                        self._log(
                            "⚠ 재테스트 실패 — AUTO_DEV_CONTINUE_ON_FAILURE=true 이므로 다음 태스크로 진행"
                        )
                        self._mark_task_done(task)
                        self._log(f"  → [{task}] 실패 후 완료 처리")
                        continue
                    self.current_stage = "error"
                    self._log("⚠ 재테스트도 실패. 루프 일시 중지 — 수동 확인 필요")
                    break
        except Exception as e:
            self.current_stage = "error"
            self._log(f"❌ 루프 내부 오류: {e}")
        finally:
            self.running = False
            if self.current_stage not in {"done", "error"}:
                self.current_stage = "idle"
            self._clear_active_runner_if_self()
            self._log("⏹ 루프 가동 중지")
            # ── 상태 파일 동기화 (Flask/Streamlit 공유) ──────────────────────
            try:
                _state_file = Path(__file__).parent / "loop_state.json"
                _state_file.write_text(
                    json.dumps(
                        {
                            "running": False,
                            "project_dir": self.project_dir,
                            "current_stage": self.current_stage,
                            "current_task": self.current_task,
                            "current_task_id": self.current_task_id,
                            "current_task_type": self.current_task_type,
                            "selection_reason": self.selection_reason,
                            "selected_from_section": self.selected_from_section,
                            "last_updated": datetime.now().isoformat(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass


runner = LoopRunner()


def run_self_tests():
    import tempfile
    import textwrap

    original_timeout = os.environ.get("CODEX_TIMEOUT")
    os.environ.pop("CODEX_TIMEOUT", None)
    assert get_codex_timeout_sec() == DEFAULT_CLAUDE_TIMEOUT_SEC
    os.environ["CODEX_TIMEOUT"] = "240"
    assert get_codex_timeout_sec() == 240
    os.environ["CODEX_TIMEOUT"] = "invalid"
    assert get_codex_timeout_sec() == DEFAULT_CLAUDE_TIMEOUT_SEC
    if original_timeout is None:
        os.environ.pop("CODEX_TIMEOUT", None)
    else:
        os.environ["CODEX_TIMEOUT"] = original_timeout

    runner = LoopRunner()
    command = runner._build_codex_command("sample prompt", "last-message.txt")
    assert command[:2] == ["codex", "exec"]
    assert "--full-auto" in command
    assert "--sandbox" not in command
    assert "--ephemeral" in command
    bypass_cmd = runner._build_codex_command("p", "f", bypass_sandbox=True)
    assert "--dangerously-bypass-approvals-and-sandbox" in bypass_cmd
    assert "--full-auto" not in bypass_cmd

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
        assert selection["selected_task_id"] == "TASK-01"
        assert selection["selected_task_type"] == "generated"
        assert selection["selection_reason"] == "lowest_generated_pending"

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
        assert selection["selected_task_id"] == "TASK-30"
        assert selection["selected_task_type"] == "generated"
        assert selection["selection_reason"] == "lowest_generated_pending"

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

            def _run_codex(
                self, prompt: str, extra_context: str = "", *, bypass_sandbox: bool = False
            ) -> tuple[str, int, bool]:
                self.timeout_calls += 1
                return "오류: codex 실행 시간 초과", 1, True

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

    with tempfile.TemporaryDirectory() as tmp:
        tasks_path = Path(tmp) / "TASKS.md"
        tasks_path.write_text(
            textwrap.dedent(
                """\
                # Tasks

                ## Active

                ### Night Queue
                - [ ] [TASK-01] failing task
                - [ ] [TASK-02] next task
                """
            ),
            encoding="utf-8",
        )

        class ContinueAfterFailureRunner(LoopRunner):
            def __init__(self):
                super().__init__()
                self.test_calls = 0

            def _install_deps(self):
                return

            def _read_prompt(self, prompt_file: Path) -> str:
                return "prompt"

            def _run_codex(
                self, prompt: str, extra_context: str = "", *, bypass_sandbox: bool = False
            ) -> tuple[str, int, bool]:
                return "", 0, False

            def _run_tests(self) -> tuple[bool, str]:
                self.test_calls += 1
                return False, "0 passed"

        original_continue_on_failure = CONTINUE_ON_TEST_FAILURE
        try:
            globals()["CONTINUE_ON_TEST_FAILURE"] = True
            runner = ContinueAfterFailureRunner()
            runner.project_dir = tmp
            runner.running = True
            runner._run()
        finally:
            globals()["CONTINUE_ON_TEST_FAILURE"] = original_continue_on_failure

        result = tasks_path.read_text(encoding="utf-8")
        assert runner.current_stage == "done"
        assert "- [x] [TASK-01] failing task" in result
        assert "- [x] [TASK-02] next task" in result
        assert "AUTO_DEV_CONTINUE_ON_FAILURE=true" in "\n".join(list(runner.log_queue.queue))

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

    # ── project_dir cwd 보정 ─────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp)
        (proj / "tests").mkdir()
        calls: list[dict[str, object]] = []
        original_run = subprocess.run

        def fake_run(cmd, **kwargs):
            calls.append({"cmd": cmd, "cwd": kwargs.get("cwd")})

            class Result:
                returncode = 0
                stdout = "ok"
                stderr = ""

            return Result()

        subprocess.run = fake_run
        try:
            r = LoopRunner()
            r.project_dir = tmp
            passed, _ = r._run_tests()
            assert passed is True
        finally:
            subprocess.run = original_run

        assert calls, "pytest 실행 기록이 없습니다."
        assert calls[0]["cwd"] == tmp
        assert calls[0]["cmd"][:4] == ["python", "-m", "pytest", "tests"]
        assert any("테스트 경로:" in line for line in list(r.log_queue.queue))

    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp)
        (proj / "requirements.txt").write_text("pytest\n", encoding="utf-8")
        calls = []
        original_run = subprocess.run

        def fake_run(cmd, **kwargs):
            calls.append({"cmd": cmd, "cwd": kwargs.get("cwd")})

            class Result:
                returncode = 0
                stdout = ""
                stderr = ""

            return Result()

        subprocess.run = fake_run
        try:
            r = LoopRunner()
            r.project_dir = tmp
            r._install_deps()
        finally:
            subprocess.run = original_run

        assert calls, "requirements 설치 기록이 없습니다."
        assert calls[0]["cwd"] == tmp
        assert calls[0]["cmd"][:4] == ["pip", "install", "-r", "requirements.txt"]

    with tempfile.TemporaryDirectory() as tmp:
        calls: list[dict[str, object]] = []

        class FakeProc:
            def __init__(self):
                self.stdout = []
                self.stderr = []
                self.returncode = 0

            def wait(self, timeout=None):
                return 0

        class CaptureRunner(LoopRunner):
            def _popen_project_command(self, cmd: list[str], **kwargs):
                calls.append({"cmd": cmd, "cwd": kwargs.get("cwd", self._get_project_cwd())})
                return FakeProc()

        r = CaptureRunner()
        r.project_dir = tmp
        codex_output, codex_code, codex_timed_out = r._run_codex("prompt")
        claude_output, claude_code, claude_timed_out = r._run_claude("prompt")

        assert codex_output == ""
        assert codex_code == 0
        assert codex_timed_out is False
        assert claude_output == ""
        assert claude_code == 0
        assert claude_timed_out is False
        assert len(calls) == 2
        assert calls[0]["cwd"] == tmp
        assert calls[1]["cwd"] == tmp
        assert calls[0]["cmd"][0] == "codex"
        assert calls[1]["cmd"][0] == "codex"

    # ── 단일 실행 보장 ───────────────────────────────────────────────────────
    class BlockingRunner(LoopRunner):
        def _run(self):
            try:
                self.running = True
                self.current_stage = "running"
                self._log(f"blocking-runner-start:{self.project_dir}")
                while not self._stop_event.is_set():
                    time.sleep(0.01)
            finally:
                self.running = False
                self.current_stage = "idle"
                self._clear_active_runner_if_self()
                self._log(f"blocking-runner-stop:{self.project_dir}")

    LoopRunner._active_runner = None
    LoopRunner._active_project_dir = ""
    BlockingRunner._active_runner = None
    BlockingRunner._active_project_dir = ""

    with tempfile.TemporaryDirectory() as tmp:
        r = BlockingRunner()
        r.start(tmp)
        time.sleep(0.05)
        first_thread = r._thread
        r.start(tmp)
        time.sleep(0.05)
        assert r._thread is first_thread
        assert any("이미 실행 중" in line for line in list(r.log_queue.queue))
        r.stop()
        if r._thread is not None:
            r._thread.join(timeout=1)

    LoopRunner._active_runner = None
    LoopRunner._active_project_dir = ""
    BlockingRunner._active_runner = None
    BlockingRunner._active_project_dir = ""

    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        first = BlockingRunner()
        second = BlockingRunner()
        first.start(tmp1)
        time.sleep(0.05)
        second.start(tmp2)
        time.sleep(0.1)
        assert first._stop_event.is_set()
        assert second.running is True
        assert BlockingRunner._active_project_dir == str(Path(tmp2))
        assert second._thread is not None and second._thread.is_alive()
        assert any("기존 러너 정리 후 새 러너 시작" in line for line in list(first.log_queue.queue))
        second.stop()
        if first._thread is not None:
            first._thread.join(timeout=1)
        if second._thread is not None:
            second._thread.join(timeout=1)

    print("self-tests passed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        run_self_tests()
