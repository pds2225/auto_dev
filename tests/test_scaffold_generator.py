import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_project_scaffold_generator import (
    append_task_to_tasks_md,
    build_code_analysis_prompt,
    TASK_SYSTEM_RULES,
    ensure_task_system_rules,
    fallback_derivatives,
    fallback_prd,
    get_next_task_id,
    normalize_provider,
    render_tasks,
    render_existing_safe_tasks,
    resolve_provider_and_api_key,
)


def _prd():
    return fallback_prd("테스트 서비스", "test-service")


def _der():
    return fallback_derivatives(_prd(), "Python")


# ── render_tasks ──────────────────────────────────────────────────────────────

def test_render_tasks_has_active_section():
    result = render_tasks(_prd(), _der(), "v1.0")
    assert "## Active" in result


def test_render_tasks_has_task_checkboxes():
    result = render_tasks(_prd(), _der(), "v1.0")
    assert "- [ ] [TASK-01]" in result


def test_render_tasks_includes_common_rules_once():
    result = render_tasks(_prd(), _der(), "v1.0")
    assert result.count(TASK_SYSTEM_RULES) == 1


# ── priority order ───────────────────────────────────────────────────────────

def test_fallback_derivatives_prioritizes_real_data_then_frontend():
    der = fallback_derivatives(_prd(), "Python")
    titles = [task["title"] for task in der["tasks"]]
    assert titles[:3] == [
        "실제 데이터 연결 및 입력 원천 고정",
        "프론트엔드 MVP 화면 구현",
        "오류 없이 동작하도록 예외처리 보강",
    ]
    assert der["tasks"][0]["id"] == "TASK-01"
    assert der["tasks"][1]["depends_on"] == ["TASK-01"]
    assert der["tasks"][2]["depends_on"] == ["TASK-02"]


def test_build_code_analysis_prompt_mentions_priority_rules():
    prompt = build_code_analysis_prompt(Path("D:/auto_dev"), "v0.1", "- file: app.py")
    assert "TASK-01이 1순위" in prompt
    assert "실제 데이터/실데이터 연결" in prompt


def test_render_existing_safe_tasks_uses_priority_order():
    result = render_existing_safe_tasks(_prd(), "v0.1", "- file: app.py")
    assert "Real data and input baseline" in result
    assert "Frontend MVP shell" in result
    assert "Error-free operation and exception handling" in result


def test_render_existing_safe_tasks_includes_common_rules_once():
    result = render_existing_safe_tasks(_prd(), "v0.1", "- file: app.py")
    assert result.count(TASK_SYSTEM_RULES) == 1


# ── get_next_task_id ──────────────────────────────────────────────────────────

def test_get_next_task_id_empty():
    assert get_next_task_id("# Tasks\n") == "TASK-01"


def test_get_next_task_id_increments():
    text = "- [x] [TASK-05] 완료 태스크\n- [x] [TASK-03] 다른 태스크\n"
    assert get_next_task_id(text) == "TASK-06"


# ── append_task_to_tasks_md ───────────────────────────────────────────────────

def test_append_task_creates_active_section():
    task = {"id": "TASK-01", "title": "기본 구조", "depends_on": [], "verification": "실행 확인"}
    with tempfile.TemporaryDirectory() as tmp:
        tasks_path = Path(tmp) / "TASKS.md"
        tasks_path.write_text("# Tasks\n", encoding="utf-8")
        new_id = append_task_to_tasks_md(tasks_path, task)
        result = tasks_path.read_text(encoding="utf-8")
        assert "## Active" in result
        assert "- [ ] [TASK-01]" in result
        assert new_id == "TASK-01"


def test_append_task_preserves_existing_active():
    task = {"id": "TASK-99", "title": "신규 태스크", "depends_on": [], "verification": "실행 확인"}
    with tempfile.TemporaryDirectory() as tmp:
        tasks_path = Path(tmp) / "TASKS.md"
        tasks_path.write_text(
            "# Tasks\n\n## Active\n\n- [ ] [TASK-01] 기존 태스크\n",
            encoding="utf-8",
        )
        append_task_to_tasks_md(tasks_path, task)
        result = tasks_path.read_text(encoding="utf-8")
        assert "- [ ] [TASK-01] 기존 태스크" in result
        assert "TASK-02" in result  # get_next_task_id가 TASK-02를 부여


def test_append_task_inserts_common_rules_without_duplication():
    task = {"id": "TASK-99", "title": "신규 태스크", "depends_on": [], "verification": "실행 확인"}
    with tempfile.TemporaryDirectory() as tmp:
        tasks_path = Path(tmp) / "TASKS.md"
        tasks_path.write_text(
            "# Tasks\n\n## Active\n\n- [ ] [TASK-01] 기존 태스크\n",
            encoding="utf-8",
        )
        append_task_to_tasks_md(tasks_path, task)
        first = tasks_path.read_text(encoding="utf-8")
        append_task_to_tasks_md(tasks_path, task)
        second = tasks_path.read_text(encoding="utf-8")
        assert first.count(TASK_SYSTEM_RULES) == 1
        assert second.count(TASK_SYSTEM_RULES) == 1


def test_ensure_task_system_rules_places_block_before_active():
    text = "# Tasks\n\n## Active\n\n- [ ] [TASK-01] 기존 태스크\n"
    result = ensure_task_system_rules(text)
    assert result.count(TASK_SYSTEM_RULES) == 1
    assert result.index(TASK_SYSTEM_RULES) < result.index("## Active")


def test_normalize_provider_defaults_to_template():
    assert normalize_provider("") == "template"
    assert normalize_provider("unknown") == "template"


def test_resolve_provider_template_ignores_env_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-env-key")
    provider, api_key = resolve_provider_and_api_key("template", "")
    assert provider == "template"
    assert api_key == ""


def test_resolve_provider_uses_matching_env_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-env-key")
    provider, api_key = resolve_provider_and_api_key("claude", "")
    assert provider == "claude"
    assert api_key == "claude-env-key"


def test_resolve_provider_ignores_explicit_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env-key")
    provider, api_key = resolve_provider_and_api_key("openai", "manual-key")
    assert provider == "openai"
    assert api_key == "openai-env-key"
