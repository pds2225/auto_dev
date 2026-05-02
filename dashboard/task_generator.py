"""자동 태스크 생성기 — 로컬/서버에서 TASK.md에 태스크를 자동 추가"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# .env 파일에서 환경변수 로드 (있을 경우)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# 기존 스캐폴드 생성기의 함수 재활용
sys.path.insert(0, str(Path(__file__).parent.parent))
from ai_project_scaffold_generator import (
    append_task_to_tasks_md,
    fallback_derivatives,
    fallback_prd,
    get_next_task_id,
    render_appended_task_template,
    slugify,
    write_tasks_document,
    write_tasks_with_fallback,
)


AUTO_DEV_DIR = Path(__file__).parent.parent


def _build_task_from_description(
    description: str,
    task_id: str = "",
    skill_tag: str = "incremental-implementation",
    effort: str = "1-2시간",
) -> dict:
    """간단한 설명으로부터 태스크 딕셔너리 생성"""
    return {
        "id": task_id or "TASK-NEW",
        "title": description[:60],
        "skill_tag": skill_tag,
        "depends_on": [],
        "effort": effort,
        "subtasks": ["요구사항 분석", "구현", "테스트"],
        "acceptance_criteria": [
            "정상 동작 확인",
            "예외 처리 확인",
            "테스트 통과",
        ],
        "verification": "pytest 또는 수동 실행",
    }


def generate_task_via_template(
    description: str,
    project_dir: str,
    tech_stack: str = "Streamlit",
) -> str:
    """템플릿 모드로 태스크를 생성하고 TASK.md에 추가"""
    proj = Path(project_dir)
    task_md = proj / "TASK.md"
    tasks_md = proj / "TASKS.md"

    # 기존 TASK.md 또는 TASKS.md에서 다음 ID 결정
    source_text = ""
    if task_md.exists():
        source_text = task_md.read_text(encoding="utf-8")
    elif tasks_md.exists():
        source_text = tasks_md.read_text(encoding="utf-8")

    next_id = get_next_task_id(source_text)
    task = _build_task_from_description(description, next_id)

    # TASK.md 또는 TASKS.md에 추가
    target_file = task_md if task_md.exists() else (tasks_md if tasks_md.exists() else None)

    if target_file:
        text = target_file.read_text(encoding="utf-8")
        appended = render_appended_task_template(task, next_id)
        # Active 섹션 찾아서 끝에 추가
        active_match = re.search(r"^## Active\s*$", text, re.MULTILINE)
        if active_match:
            start = active_match.end()
            next_section = re.search(r"^##\s+", text[start:], re.MULTILINE)
            end = start + next_section.start() if next_section else len(text)
            active_body = text[start:end]
            updated = text[:start] + active_body.rstrip() + "\n\n" + appended + "\n" + text[end:]
        else:
            updated = text.rstrip() + "\n\n## Active\n\n" + appended
        target_file.write_text(updated, encoding="utf-8")
    else:
        # TASK.md/TASKS.md 둘 다 없으면: 사용자 입력 기반의 최소 TASK.md 생성
        # (fallback_derivatives의 하드코딩 태스크 대신 사용자가 입력한 내용을 반영)
        doc = (
            f"# TASK.md — {proj.name}\n\n"
            f"## Active\n\n"
            f"### Auto Dev Queue\n\n"
            f"- [ ] [{next_id}] {task['title']}\n"
            f"  - 스킬태그: {task['skill_tag']}\n"
            f"  - 예상 소요: {task['effort']}\n"
            f"  - 검증: {task['verification']}\n"
        )
        task_md.write_text(doc, encoding="utf-8")

    return next_id


def generate_task_via_ai(
    description: str,
    project_dir: str,
    provider: str = "template",
    api_key: str = "",
) -> dict:
    """AI를 통해 태스크를 생성 (API 키 있을 때)"""
    # API 모드는 기존 scaffold_generator의 generate_scaffold를 활용
    from ai_project_scaffold_generator import generate_scaffold

    result = generate_scaffold(
        description=description,
        folder_path=project_dir,
        tech_stack="Streamlit",
        provider=provider,
        api_key=api_key,
    )
    return result


def preview_task(description: str) -> dict:
    """TASK.md에 추가하기 전에 미리보기"""
    return _build_task_from_description(description)


def decompose_tasks_with_ai(description: str, tech_stack: str = "Streamlit") -> list[dict]:
    """OpenAI/Claude API를 통해 사용자 설명을 여러 개발 태스크로 분해"""
    prompt = f"""당신은 소프트웨어 개발 태스크 분석 전문가입니다.
다음 기능 설명을 {tech_stack} 기술스택으로 구현하기 위해 필요한 개발 태스크들을 분해해주세요.

설명: {description}

각 태스크는 다음 필드를 포함해야 합니다:
- id: 임시 TASK-01, TASK-02, ...
- title: 태스크 제목 (50자 이내)
- skill_tag: frontend-ui, backend-api, debugging, test, data-integration 중 하나
- effort: 예상 소요 시간 (예: "1-2시간", "2-4시간", "30분")
- subtasks: 세부 작업 목록 (문자열 배열, 2-4개)
- acceptance_criteria: 수락 기준 (문자열 배열, 2-4개)
- verification: 검증 방법 (문자열)

반드시 아래 JSON 형식으로만 응답하세요. 추가 설명 없이 순수 JSON만 반환하세요.
{{
  "tasks": [
    {{
      "id": "TASK-01",
      "title": "...",
      "skill_tag": "...",
      "effort": "...",
      "subtasks": ["..."],
      "acceptance_criteria": ["..."],
      "verification": "..."
    }}
  ]
}}"""

    # OpenAI 먼저 시도
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "당신은 소프트웨어 개발 태스크 분석 전문가입니다. JSON으로만 응답하세요."},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = resp.choices[0].message.content
            data = json.loads(raw)
            tasks = data.get("tasks", [])
            if tasks:
                return tasks
        except Exception as e:
            print(f"[경고] OpenAI 태스크 분해 실패: {e}")

    # Claude fallback
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            msg = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text
            data = json.loads(raw)
            tasks = data.get("tasks", [])
            if tasks:
                return tasks
        except Exception as e:
            print(f"[경고] Claude 태스크 분해 실패: {e}")

    raise RuntimeError("AI API를 통해 태스크 분해에 실패했습니다. API 키와 네트워크를 확인하세요.")


def decompose_tasks_with_fallback(description: str, tech_stack: str = "Streamlit") -> tuple[list[dict], str]:
    """AI 분해를 시도하되 실패하면 입력 설명 기반 단일 태스크로 fallback."""
    try:
        tasks = decompose_tasks_with_ai(description, tech_stack)
        if tasks:
            return tasks, "ai"
    except Exception as exc:
        print(f"[경고] AI 태스크 분해 실패, 템플릿 fallback 사용: {exc}")

    return [_build_task_from_description(description)], "template-fallback"


def _extract_task_number(task_id: str) -> int:
    m = re.search(r"TASK-(\d+)", task_id)
    return int(m.group(1)) if m else 0


def batch_append_tasks(tasks: list[dict], project_dir: str) -> list[str]:
    """여러 태스크를 TASK.md 또는 TASKS.md의 Active 섹션에 일괄 추가"""
    proj = Path(project_dir)
    task_md = proj / "TASK.md"
    tasks_md = proj / "TASKS.md"

    target_file = task_md if task_md.exists() else (tasks_md if tasks_md.exists() else None)

    # 기존 파일에서 다음 ID 결정
    source_text = ""
    if target_file:
        source_text = target_file.read_text(encoding="utf-8")
    next_id_num = _extract_task_number(get_next_task_id(source_text))

    appended_lines = []
    for i, task in enumerate(tasks):
        new_id_num = next_id_num + i
        new_id = f"TASK-{new_id_num:02d}"
        task["id"] = new_id
        appended_lines.append(render_appended_task_template(task, new_id))

    appended = "\n\n".join(appended_lines)

    if target_file:
        text = target_file.read_text(encoding="utf-8")
        active_match = re.search(r"^## Active\s*$", text, re.MULTILINE)
        if active_match:
            start = active_match.end()
            next_section = re.search(r"^##\s+", text[start:], re.MULTILINE)
            end = start + next_section.start() if next_section else len(text)
            active_body = text[start:end]
            updated = text[:start] + active_body.rstrip() + "\n\n" + appended + "\n" + text[end:]
        else:
            updated = text.rstrip() + "\n\n## Active\n\n" + appended
        target_file.write_text(updated, encoding="utf-8")
    else:
        doc = (
            f"# TASK.md — {proj.name}\n\n"
            f"## Active\n\n"
            f"### Auto Dev Queue\n\n"
            f"{appended}\n"
        )
        task_md.write_text(doc, encoding="utf-8")

    return [f"TASK-{next_id_num + i:02d}" for i in range(len(tasks))]


# ── 셀프 테스트 ─────────────────────────────────────────────
def _self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp)
        # 기본 TASK.md 생성
        task_md = proj / "TASK.md"
        task_md.write_text("""# TASK.md — test

## Active

### Auto Dev Queue
- [ ] [TASK-01] 기존 태스크
""", encoding="utf-8")

        # 태스크 추가
        new_id = generate_task_via_template("새로운 로그인 기능 구현", str(proj))
        text = task_md.read_text(encoding="utf-8")
        assert new_id == "TASK-02"
        assert "로그인 기능" in text
        print(f"✅ 자동 생성 및 추가 완료: {new_id}")

    print("self-test passed")


if __name__ == "__main__":
    _self_test()
