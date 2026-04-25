#!/usr/bin/env python3
"""AI 프로젝트 스캐폴드 생성기 v4
2단계 승인 구조:
  Phase 1 — PRD 생성 → 사용자 검토 (revise / approve / stop)
  Phase 2 — approve 시 파생 문서 일괄 생성
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from datetime import date
from pathlib import Path


# ─── 유틸 ────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\s_-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "new-service"


def folderify(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1F]', " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or "new-service"


def choose_folder_name(description: str, service_name: str, prd_service_name: str) -> str:
    for candidate in (service_name, description, prd_service_name):
        if candidate and re.search(r"[가-힣]", candidate):
            return folderify(candidate)

    for candidate in (service_name, description, prd_service_name):
        folder_name = folderify(candidate)
        if folder_name:
            return folder_name

    return "new-service"


def resolve_output_dir(folder_path: str) -> Path:
    raw_path = (folder_path or "").strip()
    if not raw_path:
        raise ValueError("생성 경로가 비어 있습니다.")

    path_body = re.sub(r"^[A-Za-z]:(\\|/)?", "", raw_path)
    if re.search(r'[<>:"|?*\x00-\x1F]', path_body):
        raise ValueError("생성 경로에 Windows에서 사용할 수 없는 문자가 포함되어 있습니다.")

    output_dir = Path(raw_path).expanduser().resolve()
    if len(str(output_dir)) > 240:
        raise ValueError("생성 경로가 너무 깁니다. 더 짧은 경로를 입력하세요.")

    return output_dir


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    rel = str(path.relative_to(path.parent.parent)).replace("\\", "/")
    print(f"  [OK] {rel}")


def extract_json(raw: str) -> dict:
    if "```" in raw:
        raw = re.sub(r"```[a-z]*\n?", "", raw).replace("```", "").strip()
    return json.loads(raw)


from task_writer import (
    TASK_PRIORITY_GUIDANCE,
    TASK_SYSTEM_RULES,
    AUTO_DEV_QUEUE_HEADING,
    build_code_analysis_prompt,
    ensure_task_system_rules,
    ensure_task_system_rules_in_file,
    render_existing_safe_tasks,
    render_active_task_queue,
    render_tasks,
    render_appended_task_template,
    find_markdown_section_bounds,
    get_next_task_id,
    append_task_to_tasks_md,
    write_tasks_document,
    write_tasks_with_fallback,
    generate_tasks_via_claude_cli,
)

VALID_PROVIDERS = {"template", "claude", "openai"}
CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".rs", ".kt"}
SKIP_CODE_DIRS = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build", ".pytest_cache"}
SKIP_CODE_DIRS_LOWER = {directory.lower() for directory in SKIP_CODE_DIRS}


def normalize_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower()
    if normalized in VALID_PROVIDERS:
        return normalized
    return "template"


def resolve_provider_and_api_key(provider: str, api_key: str = "") -> tuple[str, str]:
    resolved_provider = normalize_provider(provider)
    if resolved_provider == "template":
        return resolved_provider, ""
    env_key_name = "ANTHROPIC_API_KEY" if resolved_provider == "claude" else "OPENAI_API_KEY"
    return resolved_provider, os.environ.get(env_key_name, "").strip()


def detect_code_files(base_dir: Path) -> list[Path]:
    try:
        if not base_dir.exists():
            return []
    except (OSError, PermissionError):
        return []
    code_files: list[Path] = []

    def _onerror(_: OSError) -> None:
        return

    for root, dirs, files in os.walk(base_dir, topdown=True, onerror=_onerror):
        dirs[:] = [directory for directory in dirs if directory.lower() not in SKIP_CODE_DIRS_LOWER]
        root_path = Path(root)
        for filename in files:
            path = root_path / filename
            if path.suffix.lower() not in CODE_EXTENSIONS:
                continue
            try:
                if path.is_file():
                    code_files.append(path)
            except (OSError, PermissionError):
                continue

    return sorted(code_files)


def _extract_python_symbols(text: str) -> tuple[list[str], list[str], bool]:
    imports: list[str] = []
    symbols: list[str] = []
    has_main = False
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return imports, symbols, has_main

    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names[:5])
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.FunctionDef):
            symbols.append(f"func:{node.name}")
        elif isinstance(node, ast.AsyncFunctionDef):
            symbols.append(f"async:{node.name}")
        elif isinstance(node, ast.ClassDef):
            symbols.append(f"class:{node.name}")

    has_main = bool(re.search(r'if\s+__name__\s*==\s*[\'"]__main__[\'"]', text))
    return imports, symbols, has_main


def _extract_generic_symbols(text: str) -> tuple[list[str], list[str], bool]:
    imports = re.findall(
        r'^\s*(?:import|from|require\(|use\s+)\s*([A-Za-z0-9_./@-]+)',
        text,
        flags=re.MULTILINE,
    )[:8]
    symbols: list[str] = []
    for class_name in re.findall(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", text)[:4]:
        symbols.append(f"class:{class_name}")
    for func_name in re.findall(
        r"\b(?:function|async function|const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)",
        text,
    )[:8]:
        symbols.append(f"func:{func_name}")
    has_main = bool(re.search(r"\b(main|start|listen|serve)\s*\(", text))
    return imports, symbols, has_main


def _excerpt_head_lines(text: str, limit: int = 60) -> str:
    return "\n".join(text.splitlines()[:limit]).strip()


def _extract_python_key_functions(text: str, limit: int = 2) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    lines = text.splitlines()
    snippets: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = max(node.lineno - 1, 0)
        end = min(start + 12, len(lines))
        snippet = "\n".join(lines[start:end]).strip()
        if snippet:
            snippets.append(snippet)
        if len(snippets) >= limit:
            break
    return snippets


def _estimate_risks(path: Path, text: str) -> list[str]:
    lower = text.lower()
    risks: list[str] = []
    keyword_risks = [
        ("external_api", ["openai", "anthropic", "requests", "httpx", "fetch(", "axios"]),
        ("mail_send", ["smtp", "send_mail", "sendmail", "mailgun", "ses"]),
        ("retry_logic", ["retry", "backoff", "tenacity"]),
        ("parsing", ["json.loads", "xml", "csv", "parse", "beautifulsoup"]),
        ("subprocess", ["subprocess", "shell=true", "popen("]),
    ]
    for label, needles in keyword_risks:
        if any(needle in lower for needle in needles):
            risks.append(label)
    if "monitor.py" in path.name.lower():
        risks.append("large_monitor_file")
    return risks or ["none"]


def summarize_codebase(base_dir: Path, code_files: list[Path] | None = None) -> str:
    code_files = code_files if code_files is not None else detect_code_files(base_dir)
    sections = [f"PROJECT: {base_dir.name}", f"CODE_FILE_COUNT: {len(code_files)}"]

    for path in code_files[:8]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            sections.append(f"- file: {path.relative_to(base_dir)}")
            sections.append(f"  read_error: {exc}")
            continue

        if path.suffix.lower() == ".py":
            imports, symbols, has_main = _extract_python_symbols(text)
            key_functions = _extract_python_key_functions(text)
        else:
            imports, symbols, has_main = _extract_generic_symbols(text)
            key_functions = []

        head_excerpt = _excerpt_head_lines(text, limit=60)
        sections.append(f"- file: {path.relative_to(base_dir)}")
        sections.append(f"  imports: {', '.join(dict.fromkeys(i for i in imports if i)) or 'none'}")
        sections.append(f"  top_level_symbols: {', '.join(dict.fromkeys(symbols)) or 'none'}")
        sections.append(f"  entrypoint_guess: {'__main__ detected' if has_main else 'not-detected'}")
        sections.append(f"  risk_summary: {', '.join(_estimate_risks(path, text))}")
        sections.append("  head_excerpt:")
        for line in head_excerpt.splitlines():
            sections.append(f"    {line}")
        if key_functions:
            sections.append("  key_functions:")
            for snippet in key_functions[:2]:
                sections.append("    ---")
                for line in snippet.splitlines():
                    sections.append(f"    {line}")

    return "\n".join(sections)


# ─── 시스템 프롬프트 ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """당신은 PM + 서비스기획자 + 시니어 개발리드 + QA 역할을 동시에 수행하는 전문가입니다.

역할별 책임:
- PM: 사용자 가치와 비즈니스 목표를 명확히 정의
- 서비스기획자: 사용자 흐름, 엣지케이스, 예외상황까지 빠짐없이 정의
- 시니어 개발리드: 기술스택에 맞는 구체적 구현 방향과 의존성 순서 설계
- QA: 수락 기준과 검증 방법을 테스트 가능한 수준으로 작성

작업 원칙:
1. 부족한 정보는 합리적으로 가정하고 명시 (질문 최소화)
2. 즉시 실행 가능한 결과물 생성
3. 1기능 = 1작업 = 1검증 원칙 유지
4. 예외처리·입력검증·오류상태·빈상태·로딩상태를 반드시 반영
5. 성공 기준은 수치로 검증 가능해야 함
6. 태스크 번호는 우선순위 순서대로 부여하고 TASK-01을 최우선으로 둔다
7. "나중에", "가능하면", "필요시" 같은 모호한 표현 금지

반드시 유효한 JSON만 반환하세요. 마크다운 코드블록 없이 순수 JSON만."""

# Phase 1: PRD 전용 스키마
PRD_SCHEMA_PROMPT = """다음 서비스에 대한 PRD를 JSON으로 생성하세요.

서비스 설명: {description}
기술스택: {tech_stack}
언어: 한국어
{revision_note}

JSON 스키마:
{{
  "service_name": "서비스명 (간결하게)",
  "slug": "영문-소문자-kebab-case",
  "one_liner": "한 줄 설명 (40자 이내)",
  "target_users": ["구체적 사용자 유형 (직군+상황 명시)", "사용자 유형 2"],
  "problem_statement": "해결하는 핵심 문제 (2-3문장, 수치 포함)",
  "root_cause": "문제의 근본 원인 (1문장)",
  "core_features": ["핵심 기능 1", "핵심 기능 2", "핵심 기능 3"],
  "mvp_scope": ["MVP 1순위 기능", "MVP 2순위 기능"],
  "excluded_scope": ["제외 항목 (이유 포함) 1", "제외 항목 2"],
  "success_metrics": [
    {{"metric": "기술/시스템 지표명", "target": "수치 목표값", "measurement": "측정 방법"}}
  ],
  "user_stories": [
    {{"as": "구체적 사용자", "i_want": "원하는 것", "so_that": "기대 효과"}}
  ],
  "known_risks": [
    {{"risk": "위험 내용", "impact": "영향도 (상/중/하)", "mitigation": "대응 방안"}}
  ]
}}

성공 기준 규칙:
- 반드시 수치(%, 초, 건 등)로 측정 가능한 기술·시스템 지표만 사용하세요.
- 금지 지표: 사용자 등록 수, 사용자 만족도, NPS, 유지율, DAU/MAU 등 사용자 관련 지표.
- 허용 지표 예시: API 응답 시간(초), 기능 성공률(%), 오류율(%), 처리 속도(건/초), 페이지 로드 시간(ms).
MVP 범위는 우선순위 순서로 나열하세요."""

# Phase 2: 파생 문서 스키마
DERIVATIVES_SCHEMA_PROMPT = """아래 승인된 PRD를 기준으로 파생 문서 데이터를 JSON으로 생성하세요.

PRD:
{prd_json}

기술스택: {tech_stack}
언어: 한국어

JSON 스키마:
{{
  "tasks": [
    {{
      "id": "TASK-01",
      "title": "태스크 제목",
      "skill_tag": "agent-skills 스킬명",
      "depends_on": [],
      "effort": "예상 소요 시간",
      "subtasks": ["세부 작업 1", "세부 작업 2"],
      "acceptance_criteria": ["수락 기준 1 (테스트 가능)", "수락 기준 2", "수락 기준 3"],
      "verification": "검증 방법 (실행 명령 포함)"
    }}
  ],
  "kpis": [
    {{"name": "KPI명", "target": "목표값", "current": "-"}}
  ],
  "tech_stack_rules": [
    "기술스택 전용 구현 규칙 (구체적으로)"
  ],
  "user_flows": [
    {{
      "flow_name": "흐름 이름",
      "actor": "행위자",
      "steps": [
        {{"step": 1, "action": "사용자 행동", "system": "시스템 반응", "error_case": "오류 시 처리"}}
      ]
    }}
  ],
  "screens": [
    {{
      "name": "화면명",
      "route": "/경로",
      "purpose": "이 화면의 목적",
      "components": ["컴포넌트 1", "컴포넌트 2"],
      "states": ["기본 상태", "로딩 상태", "빈 상태", "오류 상태"],
      "interactions": ["상호작용 1", "상호작용 2"]
    }}
  ],
  "function_specs": [
    {{
      "name": "함수/기능명",
      "purpose": "목적",
      "input": "입력값 설명",
      "output": "출력값 설명",
      "error_cases": ["오류 케이스 1", "오류 케이스 2"],
      "edge_cases": ["엣지 케이스 1"]
    }}
  ],
  "data_models": [
    {{
      "entity": "엔티티명",
      "purpose": "이 데이터의 역할",
      "fields": [
        {{"name": "필드명", "type": "타입", "required": true, "description": "설명"}}
      ]
    }}
  ]
}}

TASK는 5-7개, 각 수락 기준은 3개 이상, 예외처리·빈상태·로딩상태를 반드시 포함하세요."""


# ─── API 호출 ─────────────────────────────────────────────────────────────────

def _call_claude(prompt: str, api_key: str) -> dict | None:
    try:
        import anthropic  # type: ignore
    except ImportError:
        print("[경고] pip install anthropic 필요")
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return extract_json(msg.content[0].text.strip())
    except Exception as e:
        print(f"[경고] Claude API 실패: {e}")
        return None


def _call_openai(prompt: str, api_key: str) -> dict | None:
    try:
        import openai  # type: ignore
    except ImportError:
        print("[경고] pip install openai 필요")
        return None
    try:
        client = openai.OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-5.4",
            max_tokens=8192,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        return extract_json(resp.choices[0].message.content.strip())
    except Exception as e:
        print(f"[경고] OpenAI API 실패: {e}")
        return None


def call_api(prompt: str, provider: str, api_key: str) -> dict | None:
    provider = normalize_provider(provider)
    if provider == "template":
        print("[INFO] provider=template → 외부 LLM 호출 차단")
        return None
    if not api_key:
        print(f"[INFO] provider={provider} 이지만 API 키가 없어 템플릿 폴백")
        return None
    fn = _call_claude if provider == "claude" else _call_openai
    result = fn(prompt, api_key)
    if result is None:
        print("템플릿 모드로 전환합니다.")
    return result


# ─── 폴백 데이터 ─────────────────────────────────────────────────────────────

def fallback_prd(description: str, service_name: str) -> dict:
    return {
        "service_name": service_name,
        "slug": slugify(service_name),
        "one_liner": description[:80],
        "target_users": ["대상 사용자를 직접 작성하세요"],
        "problem_statement": f"{description}\n\n(PRD.md에서 구체적으로 보완하세요)",
        "root_cause": "근본 원인을 직접 작성하세요",
        "core_features": ["핵심 기능 1", "핵심 기능 2", "핵심 기능 3"],
        "mvp_scope": ["MVP 기능 1 (1순위)", "MVP 기능 2 (2순위)"],
        "excluded_scope": ["관리자 페이지 (범위 초과)", "외부 대규모 연동 (복잡도)"],
        "success_metrics": [
            {"metric": "핵심 기능 성공률", "target": "90% 이상", "measurement": "샘플 10건 테스트"},
            {"metric": "응답 시간", "target": "3초 이내", "measurement": "브라우저 Network 탭"},
        ],
        "user_stories": [
            {"as": "사용자", "i_want": "핵심 기능 사용", "so_that": "반복 작업을 줄인다"},
        ],
        "known_risks": [
            {"risk": "입력 형식 다양성", "impact": "중", "mitigation": "입력 검증 강화"},
            {"risk": "외부 의존성 장애", "impact": "상", "mitigation": "폴백 UI 준비"},
        ],
    }


def fallback_derivatives(prd: dict, tech_stack: str) -> dict:
    return {
        "tasks": [
            {
                "id": "TASK-01",
                "title": "실제 데이터 연결 및 입력 원천 고정",
                "skill_tag": "data-integration",
                "depends_on": [],
                "effort": "1-2시간",
                "subtasks": ["실제 데이터 소스 확인", "샘플 데이터/실데이터 경로 정리", "입력 필수값 정의"],
                "acceptance_criteria": [
                    "실제 데이터 또는 샘플 데이터 경로가 1개 이상 정리된다",
                    "입력 원천과 필수 필드가 명시된다",
                    "빈 데이터와 잘못된 입력을 구분할 수 있다",
                ],
                "verification": "데이터 소스 확인 + 빈 입력/잘못된 입력 재현",
            },
            {
                "id": "TASK-02",
                "title": "프론트엔드 MVP 화면 구현",
                "skill_tag": "frontend-ui-engineering",
                "depends_on": ["TASK-01"],
                "effort": "2-4시간",
                "subtasks": ["핵심 입력 폼 구현", "결과 출력 영역 구현", "로딩/빈 상태 표시"],
                "acceptance_criteria": [
                    "최소 1개 핵심 화면이 열린다",
                    "핵심 입력과 결과 표시가 동작한다",
                    "로딩 상태와 빈 상태가 보인다",
                ],
                "verification": "브라우저 실행 후 기본 흐름 클릭 테스트",
            },
            {
                "id": "TASK-03",
                "title": "오류 없이 동작하도록 예외처리 보강",
                "skill_tag": "debugging-and-error-recovery",
                "depends_on": ["TASK-02"],
                "effort": "1-2시간",
                "subtasks": ["빈 입력 처리", "잘못된 형식 처리", "외부 실패 처리"],
                "acceptance_criteria": [
                    "오류 상황에서도 앱이 종료되지 않는다",
                    "사용자가 이해할 수 있는 오류 메시지가 표시된다",
                    "다음 행동을 안내한다",
                ],
                "verification": "빈 입력·잘못된 입력·오류 케이스 테스트",
            },
            {
                "id": "TASK-04",
                "title": "회귀 테스트 작성 및 검증",
                "skill_tag": "test-driven-development",
                "depends_on": ["TASK-03"],
                "effort": "1-2시간",
                "subtasks": ["정상 케이스 테스트", "실패 케이스 테스트", "경계값 테스트"],
                "acceptance_criteria": [
                    "테스트 3종(정상·실패·경계) 모두 통과한다",
                    "테스트 실행 명령이 문서화된다",
                    "각 테스트에 기댓값이 명시된다",
                ],
                "verification": "pytest 또는 수동 테스트 결과 출력",
            },
            {
                "id": "TASK-05",
                "title": "관측성 정리 및 안전한 마무리",
                "skill_tag": "security-and-hardening",
                "depends_on": ["TASK-04"],
                "effort": "1시간",
                "subtasks": ["입력 검증 확인", "로그 확인 포인트 정리", "불필요한 중복 정리"],
                "acceptance_criteria": [
                    "기존 핵심 흐름이 유지된다",
                    "새 회귀가 발생하지 않는다",
                    "주요 상태를 확인할 수 있다",
                ],
                "verification": "기존 실행 경로 재검증",
            },
        ],
        "kpis": [
            {"name": "핵심 기능 성공률", "target": "90%+", "current": "-"},
            {"name": "평균 응답 시간", "target": "3초 이내", "current": "-"},
            {"name": "테스트 커버리지", "target": "80%+", "current": "-"},
        ],
        "tech_stack_rules": [
            f"{tech_stack} 전용 규칙은 RULES.md에서 직접 보완하세요",
            "외부 패키지 추가 시 requirements.txt에 버전 고정",
            "환경변수는 .env 파일로 관리하고 .gitignore에 추가",
        ],
        "user_flows": [
            {
                "flow_name": "핵심 기능 사용 흐름",
                "actor": "사용자",
                "steps": [
                    {"step": 1, "action": "서비스 접속", "system": "메인 화면 표시", "error_case": "로딩 실패 시 재시도 버튼"},
                    {"step": 2, "action": "데이터 입력", "system": "입력 유효성 검사", "error_case": "잘못된 형식 시 안내 문구"},
                    {"step": 3, "action": "실행 버튼 클릭", "system": "처리 중 로딩 표시", "error_case": "타임아웃 시 오류 메시지"},
                    {"step": 4, "action": "결과 확인", "system": "결과 화면 표시", "error_case": "결과 없음 시 안내"},
                ],
            }
        ],
        "screens": [
            {
                "name": "메인 화면",
                "route": "/",
                "purpose": "사용자 입력 및 결과 확인",
                "components": ["제목", "입력창", "실행 버튼", "결과 영역"],
                "states": ["기본 상태", "로딩 상태", "결과 표시 상태", "오류 상태", "빈 결과 상태"],
                "interactions": ["입력창 포커스", "버튼 클릭", "결과 복사"],
            }
        ],
        "function_specs": [
            {
                "name": "process_input",
                "purpose": "사용자 입력을 받아 핵심 기능 처리",
                "input": "문자열 입력값",
                "output": "처리 결과 딕셔너리",
                "error_cases": ["빈 입력", "형식 오류", "처리 실패"],
                "edge_cases": ["최대 길이 초과", "특수문자 포함"],
            }
        ],
        "data_models": [
            {
                "entity": "ProcessResult",
                "purpose": "처리 결과 저장",
                "fields": [
                    {"name": "input", "type": "str", "required": True, "description": "원본 입력값"},
                    {"name": "output", "type": "dict", "required": True, "description": "처리 결과"},
                    {"name": "created_at", "type": "datetime", "required": True, "description": "생성 시각"},
                    {"name": "status", "type": "str", "required": True, "description": "success/error"},
                ],
            }
        ],
    }


# ─── PRD 렌더러 ───────────────────────────────────────────────────────────────

def render_prd(prd: dict, tech_stack: str, version: str, status: str) -> str:
    target_users = "\n".join(f"- {u}" for u in prd["target_users"])
    core_features = "\n".join(f"- {f}" for f in prd["core_features"])
    mvp_scope = "\n".join(f"- {s}" for s in prd["mvp_scope"])
    excluded = "\n".join(f"- {e}" for e in prd["excluded_scope"])
    metrics = "\n".join(
        f"- **{m['metric']}**: {m['target']} (측정: {m.get('measurement', '-')})"
        for m in prd["success_metrics"]
    )
    stories = "\n".join(
        f"- {s['as']}로서, {s['i_want']}, 그래서 {s['so_that']}."
        for s in prd["user_stories"]
    )
    risks = "\n".join(
        f"- [{r.get('impact', '-')}] {r['risk'] if isinstance(r, dict) else r}"
        + (f" → {r['mitigation']}" if isinstance(r, dict) and 'mitigation' in r else "")
        for r in prd["known_risks"]
    )

    return f"""# PRD.md — {prd['service_name']}

> Version: {version}
> Status: {status}
> Based on: PRD {version}
> Last Updated: {date.today()}

## 서비스 개요
**한 줄 설명:** {prd['one_liner']}
**개발 환경:** {tech_stack}

## 대상 사용자
{target_users}

## 문제 정의
{prd['problem_statement']}

**근본 원인:** {prd['root_cause']}

## 핵심 기능
{core_features}

## MVP 범위 (우선순위 순)
{mvp_scope}

## 제외 범위
{excluded}

## 사용자 스토리
{stories}

## 성공 기준
{metrics}

## 알려진 위험
{risks}

## 개발 원칙
- 기능 추가 전 이 문서의 MVP 범위를 먼저 확인한다.
- 성공 기준은 협상 불가다. 수치로 검증한다.
- 제외 범위 기능 요청은 다음 버전 backlog에 기록한다.
- 승인 전에는 구현 코드를 작성하지 않는다.
"""


# ─── 파생 문서 렌더러 ─────────────────────────────────────────────────────────

def render_agents(prd: dict, der: dict, tech_stack: str, prd_version: str) -> str:
    task_ids = " → ".join(t["id"] for t in der["tasks"])
    return f"""# AGENTS.md — {prd['service_name']}

> Based on: PRD {prd_version}
> Status: Generated

## 역할
PM + 서비스기획자 + 시니어 개발리드 + QA를 동시에 수행한다.
개발 환경: {tech_stack}
"완료"는 수락 기준 통과 + 테스트 근거 제출이 끝난 상태만을 의미한다.

## 작업 원칙
1. 질문 최소화 — 부족한 정보는 합리적으로 가정하고 명시한다
2. 설명보다 즉시 실행 가능한 결과물 우선
3. 기존 구조 최대한 유지, 최소 변경으로 구현
4. 1기능 = 1작업 = 1검증 원칙 유지
5. 예외처리·입력검증·오류상태·빈상태·로딩상태 반드시 반영
6. 코드 변경 시 실행 명령어·검증 방법·다음 할 일까지 함께 제시
7. README/TASKS/문서가 있으면 같이 업데이트
8. 대규모 갈아엎기보다 점진적 고도화 우선
9. PRD에 없는 기능은 절대 추가하지 않는다

## 작업 흐름
```
기획(spec) → 설계(plan) → 구현(build) → 테스트(test) → 문서화(review) → 배포(ship)
```

## TASK 순서
```
{task_ids}
```

## 출력 형식 (매번 반드시 준수)
```
### 작업 요약
### 변경 파일
### 구현 내용
### 실행 방법
### 검증 체크리스트
### 다음 작업
```

## 변명 금지 목록
| 변명 | 반박 |
|------|------|
| "나중에 테스트 추가할게요" | 테스트는 증거다. 지금 작성한다. |
| "일단 작동하면 됩니다" | 예외처리 없는 코드는 미완성이다. |
| "범위를 약간 넓혔습니다" | PRD 밖 기능은 삭제 대상이다. |
| "잘 될 것 같습니다" | 실행 결과가 증거다. 보여줘라. |
| "복잡해서 어쩔 수 없어요" | 단순함은 설계 목표다. |

## 페르소나 참조
코드 리뷰:   personas/code-reviewer.md
테스트 설계: personas/test-engineer.md
보안 점검:   personas/security-auditor.md

## 체크리스트 참조
테스트 패턴: checklists/testing.md
보안 기준:   checklists/security.md
성능 기준:   checklists/performance.md
"""


def render_rules(prd: dict, der: dict, tech_stack: str, prd_version: str) -> str:
    stack_rules = "\n".join(f"- {r}" for r in der["tech_stack_rules"])
    return f"""# RULES.md — {prd['service_name']}

> Based on: PRD {prd_version}

## {tech_stack} 전용 규칙
{stack_rules}

## 구현 규칙
- 함수 하나는 역할 하나만 담당한다 (단일 책임 원칙).
- PRD MVP 범위를 벗어나는 기능은 구현하지 않는다.
- 복잡한 구조보다 단순한 구조를 우선한다.
- 하드코딩 금지: 설정값은 상수 또는 환경변수로 분리한다.
- Chesterton's Fence: 기존 코드를 삭제하기 전에 왜 있는지 이해한다.

## 입력/검증 규칙
- 모든 외부 입력(사용자 입력, API 응답)은 시스템 진입점에서 검증한다.
- 빈 입력, 너무 긴 입력, 특수문자에 대한 처리를 명시한다.
- 검증 실패 시 사용자가 다음 행동을 알 수 있는 메시지를 제공한다.

## 테스트 규칙
- 정상 케이스 1개 이상 (Happy Path)
- 실패 케이스 1개 이상 (Unhappy Path)
- 경계값 케이스 1개 이상 (Edge Case)
- 테스트 없이 완료 선언은 금지다.

## 보안 규칙
- 민감정보(API 키, 비밀번호, 토큰)를 코드에 직접 작성하지 않는다.
- .env 파일은 .gitignore에 반드시 추가한다.
- checklists/security.md 기준을 커밋 전에 확인한다.

## 금지 사항
- 테스트 없이 완료 선언
- PRD에 없는 기능 임의 추가
- 개인정보·민감정보 하드코딩
- 빈 except/catch 블록으로 에러 무시
"""


def render_loop(prd: dict, der: dict, prd_version: str) -> str:
    kpis_table = "\n".join(
        f"| {k['name']} | {k['target']} | {k['current']} |" for k in der["kpis"]
    )
    task_candidates = "\n".join(f"- {t['id']}: {t['title']}" for t in der["tasks"])
    return f"""# LOOP.md — {prd['service_name']}

> Based on: PRD {prd_version}

## 현재 반복 목표
MVP 초기 구현 완료 ({der['tasks'][0]['id']} ~ {der['tasks'][-1]['id']})

## KPI 추적
| 지표 | 목표 | 현재 |
|------|------|------|
{kpis_table}

## 알려진 문제
- 없음 (초기 상태)
- 문제 발견 시: `[날짜] 문제 설명 — 담당 TASK`

## 다음 반복 후보
{task_candidates}

## 완료 기준
모든 TASK의 수락 기준이 통과되고, KPI 목표가 달성된 상태.
"""


def render_user_flow(prd: dict, der: dict, prd_version: str) -> str:
    sections = []
    for flow in der["user_flows"]:
        steps = ""
        for s in flow["steps"]:
            steps += f"| {s['step']} | {s['action']} | {s['system']} | {s['error_case']} |\n"
        sections.append(f"""## {flow['flow_name']}

**행위자:** {flow['actor']}

| 단계 | 사용자 행동 | 시스템 반응 | 오류 처리 |
|------|------------|------------|----------|
{steps}""")

    return f"""# USER_FLOW.md — {prd['service_name']}

> Based on: PRD {prd_version}
> Status: Generated
> Last Updated: {date.today()}

""" + "\n\n".join(sections)


def render_screens(prd: dict, der: dict, prd_version: str) -> str:
    sections = []
    for scr in der["screens"]:
        components = "\n".join(f"  - {c}" for c in scr["components"])
        states = "\n".join(f"  - {s}" for s in scr["states"])
        interactions = "\n".join(f"  - {i}" for i in scr["interactions"])
        sections.append(f"""## {scr['name']}

**경로:** `{scr['route']}`
**목적:** {scr['purpose']}

### 컴포넌트
{components}

### 상태 목록
{states}

### 상호작용
{interactions}

---""")

    return f"""# SCREENS.md — {prd['service_name']}

> Based on: PRD {prd_version}
> Status: Generated
> Last Updated: {date.today()}

""" + "\n\n".join(sections)


def render_function_specs(prd: dict, der: dict, prd_version: str) -> str:
    sections = []
    for fn in der["function_specs"]:
        errors = "\n".join(f"  - {e}" for e in fn["error_cases"])
        edges = "\n".join(f"  - {e}" for e in fn.get("edge_cases", []))
        sections.append(f"""## `{fn['name']}`

**목적:** {fn['purpose']}
**입력:** {fn['input']}
**출력:** {fn['output']}

### 오류 케이스
{errors}

### 엣지 케이스
{edges if edges else "  - 없음"}

---""")

    return f"""# FUNCTION_SPECS.md — {prd['service_name']}

> Based on: PRD {prd_version}
> Status: Generated
> Last Updated: {date.today()}

""" + "\n\n".join(sections)


def render_data_model(prd: dict, der: dict, prd_version: str) -> str:
    sections = []
    for model in der["data_models"]:
        fields = "\n".join(
            f"| {f['name']} | {f['type']} | {'필수' if f.get('required') else '선택'} | {f['description']} |"
            for f in model["fields"]
        )
        sections.append(f"""## {model['entity']}

**역할:** {model['purpose']}

| 필드 | 타입 | 필수 여부 | 설명 |
|------|------|----------|------|
{fields}

---""")

    return f"""# DATA_MODEL.md — {prd['service_name']}

> Based on: PRD {prd_version}
> Status: Generated
> Last Updated: {date.today()}

""" + "\n\n".join(sections)


def render_test_checklist(prd: dict, der: dict, prd_version: str) -> str:
    task_checks = ""
    for task in der["tasks"]:
        ac = "\n".join(f"  - [ ] {c}" for c in task["acceptance_criteria"])
        task_checks += f"""
### {task['id']} — {task['title']}
{ac}
"""
    return f"""# TEST_CHECKLIST.md — {prd['service_name']}

> Based on: PRD {prd_version}
> Status: Generated
> Last Updated: {date.today()}

## 수락 기준 체크리스트

{task_checks}

## 테스트 3종 필수 확인
- [ ] 정상 케이스 (Happy Path): 올바른 입력 → 예상 결과
- [ ] 실패 케이스 (Unhappy Path): 잘못된 입력 → 적절한 에러
- [ ] 경계값 케이스 (Edge Case): 빈 값, 최대/최소, 특수문자

## 성공 기준 검증
""" + "\n".join(
        f"- [ ] {m['metric']}: {m['target']} (측정: {m.get('measurement', '-')})"
        for m in prd["success_metrics"]
    )


def render_prompt_codex(prd: dict, der: dict, prd_version: str, tech_stack: str) -> str:
    task_list = "\n".join(
        f"- {t['id']}: {t['title']} ({t['effort']})" for t in der["tasks"]
    )
    first_task = der["tasks"][0]
    ac = "\n".join(f"  - [ ] {c}" for c in first_task["acceptance_criteria"])
    return f"""# PROMPT_CODEX.md — {prd['service_name']}

> Based on: PRD {prd_version}

## 역할
너는 PM + 서비스기획자 + 시니어 개발리드 + QA 역할을 동시에 수행한다.
기획 → 설계 → 구현 → 테스트 → 문서화 순서로 일한다.

## 원칙
1. 질문 최소화 — 부족한 정보는 합리적으로 가정하고 명시
2. 즉시 실행 가능한 결과물 우선
3. 기존 구조 최대한 유지, 최소 변경으로 구현
4. 1기능 = 1작업 = 1검증 원칙 유지
5. 예외처리·입력검증·오류상태·빈상태·로딩상태 반드시 반영
6. 코드 변경 시 실행 명령어·검증 방법·다음 할 일까지 함께 제시
7. README/TASKS/문서가 있으면 같이 업데이트
8. 대규모 갈아엎기보다 점진적 고도화 우선
9. 출력은 항상 작업요약 / 변경파일 / 구현내용 / 실행방법 / 검증체크리스트 / 다음작업 순서로 정리

---

## 프로젝트 컨텍스트
서비스: {prd['service_name']}
기술스택: {tech_stack}
한 줄 설명: {prd['one_liner']}

아래 파일을 먼저 읽어라:
- PRD.md (Based on: {prd_version})
- AGENTS.md
- TASKS.md
- RULES.md
- FUNCTION_SPECS.md
- DATA_MODEL.md

---

## TASK 목록
{task_list}

---

## 지금 할 일: {first_task['id']} — {first_task['title']}

**수락 기준:**
{ac}

**검증 방법:** {first_task['verification']}

**수행 순서:**
1. 변경할 파일과 범위를 먼저 설명해라
2. 코드를 작성해라
3. 수락 기준 항목을 하나씩 체크해라
4. 실제 실행 결과 또는 테스트 출력을 첨부해라
5. README·TASKS.md를 업데이트해라
6. 남은 문제와 다음 TASK를 정리해라

**절대 금지:**
- PRD 범위 초과
- 수락 기준 미확인 완료 선언
- 테스트 없이 "잘 됩니다" 선언
- 예외처리 생략
"""


def render_prompt_claude_review(prd: dict, der: dict, prd_version: str) -> str:
    task_ids = " / ".join(t["id"] for t in der.get("tasks", []))
    risks_block = "\n".join(f"- {r}" for r in prd.get("known_risks", [])) or "- PRD.md의 known_risks 참조"
    metrics_block = "\n".join(
        f"- {m['metric']}: 목표 {m['target']}" for m in prd.get("success_metrics", [])
    ) or "- PRD.md의 success_metrics 참조"

    return f"""# PROMPT_CLAUDE_REVIEW.md — {prd['service_name']}

> Based on: PRD {prd_version}
> 대상 TASK: {task_ids}

## 역할
너는 Codex가 구현한 결과물을 고도화하는 Claude Code 전담 리뷰어다.
기획 → 설계 → 구현 → 테스트 → 문서화 순서로 일한다.

## 이번 목표
Codex가 만든 코드를 전면 재작성하지 말고, 기존 구조를 유지한 채 품질만 높여라.

## 원칙 (9개)
1. 질문 최소화 — 부족한 정보는 합리적으로 가정하고 명시
2. 즉시 실행 가능한 결과물 우선
3. 기존 구조 최대한 유지, 최소 변경으로 구현
4. 1기능 = 1작업 = 1검증 원칙 유지
5. 예외처리·입력검증·오류상태·빈상태·로딩상태 반드시 반영
6. 코드 변경 시 실행 명령어·검증 방법·다음 할 일까지 함께 제시
7. README/TASKS/문서가 있으면 같이 업데이트
8. 대규모 갈아엎기보다 점진적 고도화 우선
9. 출력은 항상 작업요약 / 변경파일 / 구현내용 / 실행방법 / 검증체크리스트 / 다음작업 순서로 정리

---

## 처리 범위
1. 구조 문제 점검
2. 예외 처리 보강
3. 테스트 보완
4. 중복 코드 최소화
5. README/TASKS 문서 업데이트

## 제외 범위 (절대 하지 않는다)
- 기술스택 변경
- 전면 리팩토링
- 기능 추가
- API 스펙 변경

---

## 컨텍스트 파일 (먼저 읽어라)
- AGENTS.md / PRD.md / TASKS.md / RULES.md / TEST_CHECKLIST.md
- checklists/security.md / checklists/performance.md

---

## 입력 자료 (직접 채워라)

**Codex가 수정한 파일 목록:**
- [파일 경로와 코드를 여기에 붙여넣기]

**DONE.md — 이번 작업 결과:**
- [Codex가 완료한 내용]

**TASK_NEXT.md — 다음 작업:**
- [Codex가 남긴 다음 할 일]

**KNOWN_ISSUES.md — 남은 문제:**
- [예: null 처리 부족]
- [예: API 실패 시 사용자 메시지 없음]
- [예: 테스트 케이스 부족]

**TEST_PLAN.md — 검증 항목:**
- [테스트해야 할 시나리오]

**현재 실행 명령어:**
```
[서비스 실행 명령어]
```

**현재 테스트 명령어:**
```
[테스트 실행 명령어]
```

---

## PRD 성공 기준 (리뷰 후 재측정)
{metrics_block}

## PRD 알려진 위험 (우선 점검 대상)
{risks_block}

---

## 리뷰 5축
| 축 | 점검 내용 | 심각도 기준 |
|----|-----------|-------------|
| 정확성 | 버그·잘못된 로직·엣지케이스 누락 | BLOCK |
| 유지보수성 | 가독성·단일 책임·중복 코드 | WARN |
| 보안 | 입력 검증·민감정보 노출·OWASP Top10 | BLOCK |
| 성능 | 불필요한 연산·느린 쿼리·메모리 누수 | WARN |
| 테스트 | 커버리지·테스트 품질·누락 케이스 | WARN |

## 심각도 레이블
- **BLOCK**: 머지 전 반드시 수정
- **WARN**: 권장 수정
- **NIT**: 선택적 개선

## 중요 제약
- 최소 변경 원칙 — 동작하는 코드는 건드리지 않는다
- 회귀 방지 우선 — 기존 기능이 깨지면 즉시 복원
- null/빈값/API 실패 처리 필수
- 로딩·오류·빈 상태 UI 반영
- 문서도 코드와 함께 업데이트

---

## 출력 형식 (반드시 순서 준수)

### 작업 요약

### 구조 문제 (상위 3개, 심각도 표시)
| # | 문제 | 위치 | 심각도 | 수정 이유 |
|---|------|------|--------|-----------|
| 1 | | | BLOCK/WARN/NIT | |
| 2 | | | | |
| 3 | | | | |

### 변경 파일 목록

### 파일별 수정 코드

### 실행 명령어
```
[복사해서 바로 실행 가능해야 한다]
```

### 테스트 방법
```
[복사해서 바로 실행 가능해야 한다]
```

### 검증 체크리스트
- [ ] 기존 기능이 그대로 동작하는가? (회귀 없음)
- [ ] BLOCK 항목이 모두 해결됐는가?
- [ ] 예외처리·빈상태·로딩상태가 반영됐는가?
- [ ] checklists/security.md 통과했는가?
- [ ] 테스트 케이스가 Happy/Unhappy/Edge 3종인가?
- [ ] README/TASKS가 업데이트됐는가?
- [ ] PRD 성공 기준 수치를 재측정했는가?

### 남은 리스크

### 다음 작업 3개
1.
2.
3.

### 바로 붙여넣을 다음 프롬프트
[ship 단계: prompts/5_ship.txt 사용]
"""


# ─── prompts/ 렌더러 ──────────────────────────────────────────────────────────

def render_prompt_spec(prd: dict, der: dict, prd_version: str) -> str:
    features = "\n".join(f"- {f}" for f in prd["core_features"])
    mvp = "\n".join(f"- {s}" for s in prd["mvp_scope"])
    excluded = "\n".join(f"- {e}" for e in prd["excluded_scope"])
    metrics = "\n".join(
        f"- {m['metric']}: {m['target']}" for m in prd["success_metrics"]
    )
    risks = "\n".join(
        f"- {r['risk'] if isinstance(r, dict) else r}" for r in prd["known_risks"]
    )
    stories = "\n".join(
        f"- {s['as']}로서 {s['i_want']} → {s['so_that']}" for s in prd["user_stories"]
    )
    return f"""# /spec — {prd['service_name']}

> Based on: PRD {prd_version}

## 역할
PM + 서비스기획자 + 시니어 개발리드 + QA를 동시에 수행한다.
기획 → 설계 → 구현 → 테스트 → 문서화 순서로 일한다.

## 원칙
1. 질문 최소화 — 부족한 정보는 합리적으로 가정하고 명시
2. 즉시 실행 가능한 결과물 우선
3. 기존 구조 최대한 유지, 최소 변경으로 구현
4. 1기능 = 1작업 = 1검증 원칙 유지
5. 예외처리·입력검증·오류상태·빈상태·로딩상태 반드시 반영
6. 코드 변경 시 실행 명령어·검증 방법·다음 할 일까지 함께 제시
7. README/TASKS/문서가 있으면 같이 업데이트
8. 대규모 갈아엎기보다 점진적 고도화 우선
9. 출력은 항상 작업요약 / 변경파일 / 구현내용 / 실행방법 / 검증체크리스트 / 다음작업 순서로 정리

---

## 지금 할 일: 스펙 검증

아래 파일을 먼저 읽어라:
- AGENTS.md / PRD.md / TASKS.md / USER_FLOW.md / SCREENS.md

9개 항목 점검:
1. 대상 사용자가 구체적인가? (직군·상황·목적 명시)
2. 성공 기준이 수치로 검증 가능한가?
3. MVP 범위가 우선순위 순으로 정의됐는가?
4. 제외 범위가 명시됐는가?
5. 알려진 위험이 식별됐는가?
6. 사용자 스토리가 구체적인가?
7. 각 TASK에 수락 기준이 3개 이상 있는가?
8. 예외처리·오류상태·빈상태·로딩상태가 반영됐는가?
9. 의존성 순서가 올바른가?

---

## 현재 스펙 요약 (PRD {prd_version} 기준)

### 핵심 기능
{features}

### MVP 범위
{mvp}

### 제외 범위
{excluded}

### 성공 기준
{metrics}

### 사용자 스토리
{stories}

### 알려진 위험
{risks}

---

## 출력 형식

### 작업 요약
### 스펙 완성도 평가
| 항목 | 상태 | 비고 |
|------|------|------|
| ... | OK/보완필요 | ... |

### 구현 내용
보완 항목별 구체적 수정 제안

### 실행 방법
다음 단계: prompts/1_plan.txt

### 검증 체크리스트
- [ ] 9개 항목 모두 OK인가?
- [ ] 수락 기준이 테스트 가능한가?
- [ ] TASK-01 진입 가능한가?

### 다음 작업
TASK-01 진입 가능 여부 + 우선 수정 항목
"""


def render_prompt_plan(prd: dict, der: dict, prd_version: str) -> str:
    tasks_summary = "\n".join(
        f"- {t['id']} ({t['effort']}): {t['title']} [의존: {', '.join(t['depends_on']) or '없음'}]"
        for t in der["tasks"]
    )
    ac_summary = ""
    for t in der["tasks"]:
        ac_lines = "\n".join(f"    - [ ] {c}" for c in t["acceptance_criteria"])
        ac_summary += f"  **{t['id']}** — {t['title']}\n{ac_lines}\n\n"

    return f"""# /plan — {prd['service_name']}

> Based on: PRD {prd_version}

## 역할
PM + 서비스기획자 + 시니어 개발리드 + QA를 동시에 수행한다.

## 원칙
1~9 (AGENTS.md 동일)

---

## 지금 할 일: 구현 계획 설계

아래 파일을 먼저 읽어라:
- AGENTS.md / PRD.md / TASKS.md / RULES.md / FUNCTION_SPECS.md / DATA_MODEL.md

8개 항목 점검:
1. 각 TASK가 하루 이내 완료 가능한 크기인가?
2. 의존성 순서가 올바른가?
3. 수락 기준이 테스트 가능한 수준인가?
4. 예외처리·빈상태·오류상태를 다루는 TASK가 있는가?
5. 보안 점검 TASK가 포함됐는가?
6. 문서화·README 업데이트 TASK가 있는가?
7. 누락된 태스크가 있는가?
8. 첫 번째로 시작할 TASK가 명확한가?

---

## 현재 태스크 목록

{tasks_summary}

## 수락 기준 요약

{ac_summary}
---

## 출력 형식

### 작업 요약
### 변경 파일
### 구현 내용
| TASK | 상태 | 조정 내용 |
|------|------|-----------|

### 실행 방법
TASK-01 시작: prompts/2_build.txt 열고 "TASK-01 수행해" 붙여넣기

### 검증 체크리스트
- [ ] 모든 TASK가 하루 이내 완료 가능한가?
- [ ] 의존성 순서가 올바른가?
- [ ] 예외처리 TASK가 포함됐는가?
- [ ] 보안 점검 TASK가 있는가?
- [ ] TASK-01 즉시 시작 가능한가?

### 다음 작업
TASK-01 진입 — prompts/2_build.txt 사용
"""


def render_prompt_build(prd: dict, der: dict, prd_version: str) -> str:
    tasks_block = ""
    for t in der["tasks"]:
        dep = ", ".join(t["depends_on"]) if t["depends_on"] else "없음"
        subtasks = "\n".join(f"  - {s}" for s in t["subtasks"])
        ac = "\n".join(f"  - [ ] {c}" for c in t["acceptance_criteria"])
        tasks_block += f"""
---
### {t['id']} — {t['title']}
**스킬:** `{t['skill_tag']}` | **의존성:** {dep} | **예상 소요:** {t['effort']}

**작업 내용:**
{subtasks}

**수락 기준:**
{ac}

**검증 방법:** {t['verification']}
"""
    return f"""# /build — {prd['service_name']}

> Based on: PRD {prd_version}

## 역할
PM + 서비스기획자 + 시니어 개발리드 + QA를 동시에 수행한다.

## 원칙 (9개)
1. 질문 최소화 / 2. 즉시 실행 가능 결과물 / 3. 최소 변경 / 4. 1기능=1작업=1검증
5. 예외·오류·빈·로딩 상태 반드시 반영 / 6. 실행명령+검증방법+다음할일 함께
7. README/TASKS 같이 업데이트 / 8. 점진적 고도화 우선 / 9. 출력 6단계 준수

---

## 사용법
이 파일 전체 내용 복사 → AI에 붙여넣기 → 아래에 TASK ID 지정

```
(이 파일 전체)

TASK-01 수행해
```

---

## TASK 목록 및 수락 기준
{tasks_block}

---

## 수행 순서 (매번 반드시)
1. AGENTS.md·PRD.md·TASKS.md·RULES.md·FUNCTION_SPECS.md·DATA_MODEL.md 먼저 읽기
2. 변경할 파일과 범위를 먼저 설명 (코드 작성 전)
3. 수락 기준을 하나씩 충족하며 코드 작성
4. 오류상태·빈상태·로딩상태 반드시 포함
5. 실제 실행 결과 또는 테스트 출력 첨부
6. README·TASKS.md 완료 표시·관련 문서 업데이트
7. 출력 형식 6단계로 마무리

## 출력 형식
```
### 작업 요약
### 변경 파일
### 구현 내용
### 실행 방법
### 검증 체크리스트
### 다음 작업
```

## 절대 금지
- PRD 범위 초과 / 수락 기준 미확인 완료 선언 / 테스트 없이 완료
- 이 TASK 외 기능 추가 / 예외처리 생략
"""


def render_prompt_test(prd: dict, der: dict, prd_version: str) -> str:
    metrics_block = ""
    for m in prd.get("success_metrics", []):
        metrics_block += f"- {m['metric']}: 목표 {m['target']}\n"

    task_ids = " / ".join(t["id"] for t in der.get("tasks", []))

    return f"""# /test — {prd['service_name']}

> Based on: PRD {prd_version}

## 역할
PM + QA 전문가. 테스트는 증거다. 테스트 없는 완료는 없다.

## 원칙 (9개)
1. 질문 최소화 / 2. 즉시 실행 가능 결과물 / 3. 최소 변경 / 4. 1기능=1작업=1검증
5. 예외·오류·빈·로딩 상태 반드시 반영 / 6. 실행명령+검증방법+다음할일 함께
7. README/TASKS 같이 업데이트 / 8. 점진적 고도화 우선 / 9. 출력 6단계 준수

---

## 사용법
이 파일 전체 내용 복사 → AI에 붙여넣기 → 아래에 TASK ID 지정

```
(이 파일 전체)

TASK-01 테스트 작성 및 검증해
```

---

## 컨텍스트 파일 (먼저 읽어라)
- AGENTS.md / PRD.md / TASKS.md / TEST_CHECKLIST.md / checklists/testing.md

## 대상 TASK
{task_ids}

## PRD 성공 기준 (수치로 검증해야 한다)
{metrics_block.strip() or "- PRD.md의 success_metrics 참조"}

---

## 필수 테스트 3종 (각 TASK마다)

### 1. Happy Path — 올바른 입력 → 예상 결과
### 2. Unhappy Path — 잘못된 입력 → 적절한 에러 메시지
### 3. Edge Case — 빈 입력, 최대 길이, 특수문자, 동시 요청

---

## 수행 순서
1. AGENTS.md·PRD.md·TASKS.md·TEST_CHECKLIST.md 먼저 읽기
2. 각 TASK의 수락 기준을 테스트 시나리오로 변환
3. 테스트 코드 작성 (실행 가능한 형태)
4. 실제 실행 결과 출력 첨부 (스크린샷 또는 로그)
5. TEST_CHECKLIST.md 항목 체크 완료
6. 출력 형식 6단계로 마무리

## 출력 형식
```
### 작업 요약
### 변경 파일
### 구현 내용
| 테스트 | 입력 | 기댓값 | 실제 결과 | 통과여부 |
|--------|------|--------|-----------|----------|

### 실행 방법
[테스트 실행 명령어 — 복사해서 바로 실행 가능해야 한다]

### 검증 체크리스트
- [ ] Happy Path / Unhappy Path / Edge Case 각 1개 이상 통과
- [ ] TEST_CHECKLIST.md 전체 항목 체크 완료
- [ ] 성공 기준 수치를 실측으로 확인했는가?
- [ ] 실행 결과 또는 로그를 첨부했는가?

### 다음 작업
```

## 절대 금지
- "작동하는 것 같다" — 실행 결과 없는 완료 선언
- 테스트 코드 없이 "수동 확인했다"로 대체
- TEST_CHECKLIST.md 항목 미체크 완료 처리
"""


def render_prompt_review(prd: dict, prd_version: str) -> str:
    metrics_block = "\n".join(
        f"- {m['metric']}: 목표 {m['target']}" for m in prd.get("success_metrics", [])
    ) or "- PRD.md의 success_metrics 참조"
    risks_block = "\n".join(
        f"- {r['risk'] if isinstance(r, dict) else r}" for r in prd.get("known_risks", [])
    ) or "- PRD.md의 known_risks 참조"

    return f"""# /review — {prd['service_name']}

> Based on: PRD {prd_version}

## 역할
너는 Codex가 구현한 결과물을 고도화하는 Claude Code 전담 리뷰어다.

## 이번 목표
Codex가 만든 코드를 전면 재작성하지 말고, 기존 구조를 유지한 채 품질만 높여라.

## 처리 범위
1. 구조 문제 점검
2. 예외 처리 보강
3. 테스트 보완
4. 중복 코드 최소화
5. README/TASKS 업데이트

## 제외 범위
기술스택 변경 / 전면 리팩토링 / 기능 추가 / API 스펙 변경

---

## 컨텍스트 파일 (먼저 읽어라)
- AGENTS.md / PRD.md / TASKS.md / RULES.md / TEST_CHECKLIST.md

## PRD 성공 기준 (리뷰 후 재측정)
{metrics_block}

## PRD 알려진 위험 (우선 점검 대상)
{risks_block}

---

## 입력 자료 (직접 채워라)

**Codex가 수정한 파일 목록:**
- [파일 경로와 코드를 여기에 붙여넣기]

**DONE.md — 이번 작업 결과:**
- [Codex가 완료한 내용]

**TASK_NEXT.md — 다음 작업:**
- [Codex가 남긴 다음 할 일]

**KNOWN_ISSUES.md — 남은 문제:**
- [예: null 처리 부족]
- [예: API 실패 시 사용자 메시지 없음]

**TEST_PLAN.md — 검증 항목:**
- [테스트해야 할 시나리오]

**현재 실행 명령어:**
```
[서비스 실행 명령어]
```

**현재 테스트 명령어:**
```
[테스트 실행 명령어]
```

---

## 리뷰 5축
| 축 | 점검 내용 | 심각도 |
|----|-----------|--------|
| 정확성 | 버그·잘못된 로직·엣지케이스 누락 | BLOCK |
| 유지보수성 | 가독성·단일 책임·중복 코드 | WARN |
| 보안 | 입력 검증·민감정보 노출·OWASP Top10 | BLOCK |
| 성능 | 불필요한 연산·느린 쿼리·메모리 누수 | WARN |
| 테스트 | 커버리지·테스트 품질·누락 케이스 | WARN |

## 심각도: BLOCK / WARN / NIT

## 중요 제약
- 최소 변경 원칙 / 회귀 방지 우선
- null/빈값/API 실패 처리 필수
- 로딩/오류/빈 상태 반영
- 문서도 같이 업데이트

---

## 출력 형식

### 작업 요약

### 구조 문제 (상위 3개)
| # | 문제 | 위치 | 심각도 | 수정 이유 |
|---|------|------|--------|-----------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

### 변경 파일 목록

### 파일별 수정 코드

### 실행 명령어
```
[복사해서 바로 실행 가능해야 한다]
```

### 테스트 방법
```
[복사해서 바로 실행 가능해야 한다]
```

### 검증 체크리스트
- [ ] 기존 기능이 그대로 동작하는가? (회귀 없음)
- [ ] BLOCK 항목이 모두 해결됐는가?
- [ ] 예외처리·빈상태·로딩상태가 반영됐는가?
- [ ] checklists/security.md 통과했는가?
- [ ] 테스트 케이스가 3종(Happy/Unhappy/Edge) 이상인가?
- [ ] README/TASKS가 업데이트됐는가?

### 남은 리스크

### 다음 작업 3개
1.
2.
3.

### 바로 붙여넣을 다음 프롬프트
[ship 단계: prompts/5_ship.txt 사용]
"""


def render_prompt_ship(prd: dict, prd_version: str) -> str:
    metrics_block = ""
    for m in prd.get("success_metrics", []):
        metrics_block += f"- [ ] {m['metric']}: 목표 {m['target']} — 실측값: ______\n"

    risks_block = ""
    for r in prd.get("known_risks", []):
        risks_block += f"- [ ] {r}\n"

    return f"""# /ship — {prd['service_name']}

> Based on: PRD {prd_version}

## 역할
PM + 시니어 개발리드 + QA. 배포는 증거 기반으로 승인한다.

## 원칙 (9개)
1. 질문 최소화 / 2. 즉시 실행 가능 결과물 / 3. 최소 변경 / 4. 1기능=1작업=1검증
5. 예외·오류·빈·로딩 상태 반드시 반영 / 6. 실행명령+검증방법+다음할일 함께
7. README/TASKS 같이 업데이트 / 8. 점진적 고도화 우선 / 9. 출력 6단계 준수

---

## 사용법
이 파일 전체 내용 복사 → AI에 붙여넣기

```
(이 파일 전체)

배포 전 최종 점검해줘
```

---

## 컨텍스트 파일 (먼저 읽어라)
- PRD.md / AGENTS.md / TASKS.md / TEST_CHECKLIST.md
- checklists/security.md / checklists/performance.md

---

## 배포 전 체크리스트

### 코드 품질
- [ ] 모든 TASK의 수락 기준이 실행 결과로 증명됐는가?
- [ ] 테스트 3종(Happy·Unhappy·Edge) 각각 통과됐는가?
- [ ] /review 결과의 BLOCK 항목이 모두 해결됐는가?
- [ ] 예외처리·빈 상태·로딩 상태가 구현됐는가?

### PRD 성공 기준 (수치 실측 필수)
{metrics_block.strip() or "- PRD.md의 success_metrics 참조 — 실측값 기입"}

### 보안
- [ ] 민감정보(API 키, 비밀번호)가 코드/커밋에 없는가?
- [ ] .gitignore에 .env·secrets 포함됐는가?
- [ ] checklists/security.md 전체 항목 확인 완료

### 성능
- [ ] PRD 성공 기준 수치 실측 완료
- [ ] checklists/performance.md 항목 확인 완료

### 알려진 위험 해소 여부
{risks_block.strip() or "- PRD.md의 known_risks 참조"}

### 배포 준비
- [ ] 실행 방법이 README에 문서화됐는가?
- [ ] 장애 시 롤백 방법이 있는가?
- [ ] 모니터링 기준(임계값·알림)이 정의됐는가?
- [ ] TASKS.md 완료 항목이 체크됐는가?

---

## 수행 순서
1. 위 체크리스트 전체 항목 확인 (실행 결과 기반)
2. 미통과 항목 → 즉시 수정 또는 위험 명시
3. 배포 명령어 실행 및 결과 첨부
4. 모니터링 지표 초기값 기록
5. 이슈 발생 시 롤백 절차 명시
6. 출력 형식 6단계로 마무리

## 출력 형식
```
### 작업 요약
### 변경 파일
### 구현 내용
체크리스트 결과 (항목별 OK/NG + 실측값)

### 실행 방법
[배포 명령어 — 복사해서 바로 실행 가능해야 한다]

### 검증 체크리스트
- [ ] 전체 체크리스트 OK 항목 수: ____ / ____
- [ ] 미통과 항목 조치 완료 또는 위험 명시 완료

### 다음 작업
```

## 절대 금지
- 체크리스트 미완료 상태로 "배포 준비 완료" 선언
- 실측 수치 없이 성공 기준 통과 처리
- BLOCK 이슈 미해결 배포 진행
"""


# ─── 정적 파일 ────────────────────────────────────────────────────────────────

def render_persona_code_reviewer() -> str:
    return """# personas/code-reviewer.md

## 역할
시니어 스태프 엔지니어. "스태프 엔지니어가 승인할 수준인가?"를 기준으로 코드를 검토한다.

## 관점
- 지금 동작하는가보다 6개월 후에도 유지보수 가능한가를 본다.
- Hyrum's Law: 사용자가 많아지면 문서에 없는 동작에도 누군가 의존한다.
- Chesterton's Fence: 이유를 모르면 삭제하지 말고 먼저 이해하라.

## 리뷰 5축
1. 정확성 — 버그, 엣지케이스, 잘못된 가정
2. 유지보수성 — 단일 책임, 중복 제거, 명확한 네이밍
3. 보안 — 입력 검증, 권한, 민감정보
4. 성능 — 불필요한 연산, 메모리, I/O
5. 테스트 — 커버리지, 테스트 품질

## 심각도: BLOCK / WARN / NIT
단일 PR은 ~100줄 이내가 이상적.
"""


def render_persona_test_engineer() -> str:
    return """# personas/test-engineer.md

## 역할
QA 전문가. 테스트는 "기능이 작동한다"는 증거다. 테스트 없는 완료는 없다.

## 핵심 원칙
- Beyonce Rule: 중요한 동작은 테스트로 잡아둬라.
- DAMP over DRY: 테스트는 읽기 쉬워야 한다.
- 테스트 피라미드: 단위 80% · 통합 15% · E2E 5%

## 필수 테스트 3종
1. Happy Path: 올바른 입력 → 예상 결과
2. Unhappy Path: 잘못된 입력 → 적절한 에러
3. Edge Case: 빈 값, 최대/최소, 특수문자

## 증거 요건
실행 결과 출력 없이 "테스트 완료"는 인정하지 않는다.
"""


def render_persona_security_auditor() -> str:
    return """# personas/security-auditor.md

## 역할
보안 엔지니어. 취약점을 코드 리뷰 단계에서 잡는다.

## OWASP Top 10 포인트
1. 인젝션 / 2. 인증·세션 / 3. 민감 데이터 노출 / 4. 권한 제어 실패
5. 보안 설정 오류 / 6. 취약한 의존성 / 7. 인증 실패 / 8. 무결성 오류
9. 로깅·모니터링 부재 / 10. SSRF

## 3계층 경계
1. 입력 경계: 사용자 입력은 모두 신뢰 불가
2. 서비스 경계: 내부 서비스 호출도 검증
3. 저장 경계: DB/파일 저장 전 검증

## 시크릿 관리
- API 키, 비밀번호를 코드에 직접 작성 금지
- .env 파일은 .gitignore에 반드시 추가

## 커밋 전 체크
checklists/security.md 전체 항목 확인
"""


def render_checklist_testing() -> str:
    return """# checklists/testing.md

## 테스트 구조 (AAA 패턴)
```
# Arrange
input_data = "..."
# Act
result = function_under_test(input_data)
# Assert
assert result == expected_value
```

## 필수 케이스 3종
| 케이스 | 설명 | 예시 |
|--------|------|------|
| Happy Path | 정상 입력 → 정상 결과 | 올바른 이메일 형식 |
| Unhappy Path | 잘못된 입력 → 에러 처리 | 빈 문자열 |
| Edge Case | 경계값 | 최대 길이, 특수문자, null |

## 안티패턴
- assert 없는 테스트
- 항상 통과하는 테스트 (assert True)
- 모든 것을 mock해서 실제 통합을 테스트하지 않음

## 실행 명령
```bash
pytest -v
pytest --tb=short -q
```
"""


def render_checklist_security() -> str:
    return """# checklists/security.md

## 커밋 전 필수 체크
- [ ] API 키, 비밀번호, 토큰이 코드에 없다
- [ ] .env 파일이 .gitignore에 있다
- [ ] 사용자 입력이 검증된다
- [ ] 에러 메시지에 내부 구조 정보가 없다

## OWASP Top 10 빠른 체크
- [ ] SQL 인젝션: 파라미터 바인딩 사용
- [ ] XSS: 출력 시 이스케이프 처리
- [ ] 민감 데이터: 전송 시 HTTPS, 저장 시 암호화
- [ ] 취약한 의존성: pip audit 또는 safety check
"""


def render_checklist_performance() -> str:
    return """# checklists/performance.md

## Core Web Vitals 목표 (웹 서비스)
| 지표 | 목표 |
|------|------|
| LCP | < 2.5초 |
| INP | < 200ms |
| CLS | < 0.1 |

## 측정 전 최적화 금지
1. 먼저 측정 → 2. 병목 식별 → 3. 최적화 → 4. 재측정

## 빠른 체크
- [ ] 반복 계산을 캐싱하고 있는가?
- [ ] 불필요한 외부 API 호출이 없는가?
- [ ] 대용량 데이터를 한 번에 로드하지 않는가?
"""


def _temporary_test_directory():
    import tempfile

    test_root = Path.home() / ".codex" / "memories" / "ai_project_scaffold_generator_tests"
    test_root.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=str(test_root))


def run_self_tests() -> None:
    import textwrap

    dashboard_dir = Path(__file__).parent / "dashboard"
    if str(dashboard_dir) not in sys.path:
        sys.path.insert(0, str(dashboard_dir))

    LoopRunner = None
    try:
        from loop_runner import LoopRunner as ImportedLoopRunner
        LoopRunner = ImportedLoopRunner
    except Exception as exc:
        print(f"[self-test] loop_runner import skip: {exc}")

    test_summarize_codebase_includes_core_fields()
    test_code_analysis_prompt_uses_summary_not_full_source()
    test_existing_code_fallback_uses_existing_safe_tasks()

    sample_task = {
        "id": "TASK-01",
        "title": "신규 회귀 방지 태스크",
        "depends_on": ["TASK-00"],
        "verification": "python -m pytest --tb=short -q",
    }

    try:
        with _temporary_test_directory() as tmp:
            tasks_path = Path(tmp) / "TASKS.md"
            tasks_path.write_text(
                textwrap.dedent(
                    """\
                    # Tasks

                    ## Active

                    ### Day 1

                    - [x] 기존 완료 태스크
                    - [ ] 기존 진행 중 태스크

                    ## Waiting On

                    - [ ] 대기 태스크
                    """
                ),
                encoding="utf-8",
            )

            appended_id = append_task_to_tasks_md(tasks_path, sample_task)
            updated = tasks_path.read_text(encoding="utf-8")
            assert appended_id == "TASK-01"
            assert "- [x] 기존 완료 태스크" in updated
            assert "- [ ] 기존 진행 중 태스크" in updated
            assert f"- [ ] [{appended_id}] 신규 회귀 방지 태스크" in updated

        with _temporary_test_directory() as tmp:
            tasks_path = Path(tmp) / "TASKS.md"
            tasks_path.write_text(
                textwrap.dedent(
                    """\
                    # Tasks

                    ## Active

                    ### Day 1

                    - [ ] 기존 진행 중 태스크

                    ### Auto Dev Queue

                    - [ ] [TASK-04] 이전 신규 태스크
                    """
                ),
                encoding="utf-8",
            )

            appended_id = append_task_to_tasks_md(tasks_path, sample_task)
            updated = tasks_path.read_text(encoding="utf-8")
            assert appended_id == "TASK-05"
            assert f"- [ ] [{appended_id}] 신규 회귀 방지 태스크" in updated

            if LoopRunner is not None:
                runner = LoopRunner()
                runner.project_dir = tmp
                display_task, raw_task = runner._get_next_task_entry() or ("", "")
                assert re.search(r"\[TASK-\d+\]", raw_task), f"no TASK-XX in {raw_task!r}"
                runner._mark_task_done(raw_task)
                final_text = tasks_path.read_text(encoding="utf-8")
                assert f"- [x] {raw_task}" in final_text
                assert "- [ ] 기존 진행 중 태스크" in final_text
    except PermissionError as exc:
        print(f"[self-test] filesystem write skip: {exc}")

    print("self-tests passed")


def test_summarize_codebase_includes_core_fields():
    base_dir = Path(__file__).parent
    summary = summarize_codebase(base_dir, [Path(__file__)])
    assert f"file: {Path(__file__).name}" in summary
    assert "imports:" in summary
    assert "top_level_symbols:" in summary
    assert "func:summarize_codebase" in summary
    assert "entrypoint_guess: __main__ detected" in summary


def test_code_analysis_prompt_uses_summary_not_full_source():
    base_dir = Path(__file__).parent
    summary = summarize_codebase(base_dir, [Path(__file__)])
    prompt = build_code_analysis_prompt(base_dir, "v0.1", summary)
    assert Path(__file__).name in prompt
    assert "top_level_symbols:" in prompt
    assert "checklists/performance.md 전체 항목 확인 완료" not in prompt
    assert "기본 구조 생성 금지" in prompt
    assert "UI 생성 금지" in prompt


def test_existing_code_fallback_uses_existing_safe_tasks():
    def fake_detect_code_files(base_dir: Path) -> list[Path]:
        return [base_dir / "worker.py"]

    def fake_summarize_codebase(base_dir: Path, code_files: list[Path] | None = None) -> str:
        return "PROJECT: demo\nCODE_FILE_COUNT: 1\n- file: worker.py\n  top_level_symbols: func:run_worker"

    prd = fallback_prd("기존 코드 안정화", "기존 서비스")
    der = fallback_derivatives(prd, "Streamlit")

    with _temporary_test_directory() as tmp:
        tmp_path = Path(tmp)
        write_tasks_with_fallback(tmp_path, prd, der, "v0.1", fake_detect_code_files, fake_summarize_codebase)
        content = (tmp_path / "TASKS.md").read_text(encoding="utf-8")

    assert content.startswith("# TASKS.md — 기존 서비스")
    assert "> Based on: PRD v0.1" in content
    assert "> Status: Existing Safe Fallback" in content
    assert "## Analysis Summary" in content
    assert "## Active" in content
    assert "프로젝트 기본 구조 및 화면 생성" not in content


def test_detect_code_files_skips_inaccessible_paths(monkeypatch):
    base_dir = Path("D:/project")
    inaccessible = base_dir / "broken.py"
    accessible = base_dir / "ok.py"

    def fake_exists(self: Path) -> bool:
        return True

    def fake_walk(_base_dir, topdown=True, onerror=None):
        yield (str(base_dir), [], ["broken.py", "ok.py"])

    original_is_file = Path.is_file

    def fake_is_file(self: Path) -> bool:
        if self == inaccessible:
            raise OSError("WinError 1920")
        if self == accessible:
            return True
        return original_is_file(self)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(os, "walk", fake_walk)
    monkeypatch.setattr(Path, "is_file", fake_is_file)

    result = detect_code_files(base_dir)
    assert result == [accessible]


def test_detect_code_files_returns_empty_when_base_dir_exists_raises(monkeypatch):
    base_dir = Path("D:/special-entry")

    def fake_exists(self: Path) -> bool:
        raise OSError("WinError 1920")

    monkeypatch.setattr(Path, "exists", fake_exists)

    result = detect_code_files(base_dir)
    assert result == []


def test_detect_code_files_prunes_node_modules(monkeypatch):
    base_dir = Path("D:/project")
    observed_after_prune: list[str] = []

    def fake_exists(self: Path) -> bool:
        return True

    def fake_walk(_base_dir, topdown=True, onerror=None):
        dirs = ["node_modules", "src", ".git", "__pycache__"]
        yield (str(base_dir), dirs, ["root.py"])
        observed_after_prune.extend(dirs)
        if "node_modules" in dirs:
            yield (str(base_dir / "node_modules"), [], ["should_not_be_seen.py"])
        if "src" in dirs:
            yield (str(base_dir / "src"), [], ["app.py"])

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(os, "walk", fake_walk)
    monkeypatch.setattr(Path, "is_file", lambda self: True)

    result = detect_code_files(base_dir)
    assert base_dir / "root.py" in result
    assert base_dir / "src" / "app.py" in result
    assert base_dir / "node_modules" / "should_not_be_seen.py" not in result
    assert "node_modules" not in observed_after_prune
    assert ".git" not in observed_after_prune
    assert "__pycache__" not in observed_after_prune


def test_detect_code_files_prunes_skip_dirs_case_insensitive(monkeypatch):
    base_dir = Path("D:/project")
    observed_after_prune: list[str] = []

    def fake_exists(self: Path) -> bool:
        return True

    def fake_walk(_base_dir, topdown=True, onerror=None):
        dirs = ["NODE_MODULES", "Src", ".GIT", "__PYCACHE__", "Build"]
        yield (str(base_dir), dirs, [])
        observed_after_prune.extend(dirs)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(os, "walk", fake_walk)

    result = detect_code_files(base_dir)
    assert result == []
    assert "NODE_MODULES" not in observed_after_prune
    assert ".GIT" not in observed_after_prune
    assert "__PYCACHE__" not in observed_after_prune
    assert "Build" not in observed_after_prune
    assert "Src" in observed_after_prune


def test_render_existing_safe_tasks_reflects_auto_mail_context():
    prd = fallback_prd("기존 코드 안정화", "auto_mail")
    summary = "\n".join(
        [
            "PROJECT: auto_mail",
            "CODE_FILE_COUNT: 4",
            "- file: monitor.py",
            "- file: config.py",
            "- file: mailer.py",
            "- file: fetchers/naver.py",
        ]
    )

    content = render_existing_safe_tasks(prd, "v0.1", summary)
    assert "## Project Context" in content
    assert "monitor.py의 스케줄 실행" in content
    assert "config.py의 환경변수 로딩" in content
    assert "mailer.py의 메일 전송 실패" in content
    assert "fetchers/ 하위 수집기" in content
    assert "monitor.py, config.py, mailer.py, fetchers/" in content


# ─── 메인 ─────────────────────────────────────────────────────────────────────

def print_prd_summary(prd: dict, version: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  PRD 초안 ({version}): {prd['service_name']}")
    print(f"{'=' * 60}")
    print(f"  설명: {prd['one_liner']}")
    print(f"  대상: {', '.join(prd['target_users'][:2])}")
    print(f"\n  핵심 기능:")
    for f in prd["core_features"]:
        print(f"    - {f}")
    print(f"\n  MVP 범위:")
    for s in prd["mvp_scope"]:
        print(f"    - {s}")
    print(f"\n  제외 범위:")
    for e in prd["excluded_scope"][:3]:
        print(f"    - {e}")
    print(f"\n  성공 기준:")
    for m in prd["success_metrics"]:
        print(f"    - {m['metric']}: {m['target']}")
    print(f"{'=' * 60}")


def generate_scaffold(
    description: str,
    folder_path: str,
    service_name: str = "",
    tech_stack: str = "Streamlit",
    api_key: str = "",
    provider: str = "template",
) -> dict:
    """비대화형 스캐폴드 생성. loop_runner 및 웹 API에서 호출.

    Returns {"ok": True, "base_dir": str, "service_name": str}
         or {"ok": False, "error": str}
    """
    try:
        base_dir = resolve_output_dir(folder_path)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    provider, api_key = resolve_provider_and_api_key(provider, api_key)

    prd_version = "v0.1"
    today = str(date.today())
    fallback_name = service_name or description[:30].strip()

    print(f"[INFO] provider_resolved={provider} api_key_source={'env' if api_key else 'empty'}")
    print(f"[1/2] PRD 생성 중... (provider={provider})")
    if provider != "template" and api_key:
        prompt = PRD_SCHEMA_PROMPT.format(
            description=description, tech_stack=tech_stack, revision_note="",
        )
        prd_data = call_api(prompt, provider, api_key)
    else:
        prd_data = None

    if prd_data is None:
        prd_data = fallback_prd(description, fallback_name)
    if service_name:
        prd_data["service_name"] = service_name
        prd_data["slug"] = slugify(service_name)

    print("[2/2] 파생 문서 생성 중...")
    if provider != "template" and api_key:
        prd_json = json.dumps(prd_data, ensure_ascii=False, indent=2)
        der_prompt = DERIVATIVES_SCHEMA_PROMPT.format(prd_json=prd_json, tech_stack=tech_stack)
        der_data = call_api(der_prompt, provider, api_key)
    else:
        der_data = None
    if der_data is None:
        der_data = fallback_derivatives(prd_data, tech_stack)

    write_file(base_dir / "PRD.md", render_prd(prd_data, tech_stack, prd_version, "Approved"))
    write_file(base_dir / "AGENTS.md", render_agents(prd_data, der_data, tech_stack, prd_version))
    print("  [TASKS] TASKS.md 생성 중...")
    use_claude_cli = provider != "template" and bool(api_key)
    print(f"  [TASKS] Claude CLI 사용 여부: {use_claude_cli}")
    if not (use_claude_cli and generate_tasks_via_claude_cli(base_dir, prd_version, detect_code_files, summarize_codebase)):
        write_tasks_with_fallback(base_dir, prd_data, der_data, prd_version, detect_code_files, summarize_codebase)
    write_file(base_dir / "RULES.md", render_rules(prd_data, der_data, tech_stack, prd_version))
    write_file(base_dir / "LOOP.md", render_loop(prd_data, der_data, prd_version))
    write_file(base_dir / "USER_FLOW.md", render_user_flow(prd_data, der_data, prd_version))
    write_file(base_dir / "SCREENS.md", render_screens(prd_data, der_data, prd_version))
    write_file(base_dir / "FUNCTION_SPECS.md", render_function_specs(prd_data, der_data, prd_version))
    write_file(base_dir / "DATA_MODEL.md", render_data_model(prd_data, der_data, prd_version))
    write_file(base_dir / "TEST_CHECKLIST.md", render_test_checklist(prd_data, der_data, prd_version))
    write_file(base_dir / "PROMPT_CODEX.md", render_prompt_codex(prd_data, der_data, prd_version, tech_stack))
    write_file(base_dir / "PROMPT_CLAUDE_REVIEW.md", render_prompt_claude_review(prd_data, der_data, prd_version))
    write_file(base_dir / "prompts" / "0_spec.txt", render_prompt_spec(prd_data, der_data, prd_version))
    write_file(base_dir / "prompts" / "1_plan.txt", render_prompt_plan(prd_data, der_data, prd_version))
    write_file(base_dir / "prompts" / "2_build.txt", render_prompt_build(prd_data, der_data, prd_version))
    write_file(base_dir / "prompts" / "3_test.txt", render_prompt_test(prd_data, der_data, prd_version))
    write_file(base_dir / "prompts" / "4_review.txt", render_prompt_review(prd_data, prd_version))
    write_file(base_dir / "prompts" / "5_ship.txt", render_prompt_ship(prd_data, prd_version))
    write_file(base_dir / "personas" / "code-reviewer.md", render_persona_code_reviewer())
    write_file(base_dir / "personas" / "test-engineer.md", render_persona_test_engineer())
    write_file(base_dir / "personas" / "security-auditor.md", render_persona_security_auditor())
    write_file(base_dir / "checklists" / "testing.md", render_checklist_testing())
    write_file(base_dir / "checklists" / "security.md", render_checklist_security())
    write_file(base_dir / "checklists" / "performance.md", render_checklist_performance())
    write_file(base_dir / "README.md", (
        f"# {prd_data['service_name']}\n\n{prd_data['one_liner']}\n\n"
        f"> PRD Version: {prd_version} (Approved)\n> Generated: {today}\n"
    ))

    print(f"완료! 경로={base_dir} | 서비스={prd_data['service_name']}")
    return {"ok": True, "base_dir": str(base_dir), "service_name": prd_data["service_name"]}


def main() -> None:
    print("=" * 60)
    print("  AI 프로젝트 스캐폴드 생성기 v4")
    print("  Phase 1: PRD 생성 → 검토 → Phase 2: 파생 문서 생성")
    print("=" * 60)

    # ── 입력 수집 ──
    description = ask("\n서비스 설명 (한 줄로 자유롭게)")
    if not description:
        print("서비스 설명이 필요합니다.")
        sys.exit(1)

    folder_path = ask("생성 경로", os.getcwd())
    service_name = ask("서비스명 (비워두면 AI가 결정)", "")

    stacks = ["Streamlit", "FastAPI", "Next.js", "Python CLI", "기타"]
    print("\n기술스택 선택:")
    for i, s in enumerate(stacks, 1):
        print(f"  {i}. {s}")
    stack_choice = ask("번호 선택", "1")
    try:
        tech_stack = stacks[int(stack_choice) - 1]
    except (ValueError, IndexError):
        tech_stack = stack_choice or "Streamlit"

    print("\nPRD 생성에 사용할 AI:")
    print("  1. Claude (Anthropic)")
    print("  2. GPT (OpenAI) [기본]")
    print("  3. 템플릿 모드 (API 없이)")
    ai_choice = ask("번호 선택", "2")

    if ai_choice == "2":
        provider = "openai"
    elif ai_choice == "1":
        provider = "claude"
    else:
        provider = "template"

    api_key = resolve_provider_and_api_key(provider, "")[1]

    # ── Phase 1: PRD 생성 ──
    prd_version = "v0.1"
    revision_count = 0

    print(f"\n[STEP 1/2] PRD 초안 생성 중...")

    if provider != "template" and api_key:
        prompt = PRD_SCHEMA_PROMPT.format(
            description=description,
            tech_stack=tech_stack,
            revision_note="",
        )
        prd_data = call_api(prompt, provider, api_key)
    else:
        prd_data = None

    if prd_data is None:
        fallback_name = service_name or description[:30].strip()
        prd_data = fallback_prd(description, fallback_name)
        print("[템플릿 모드] PRD 초안을 기본 구조로 생성했습니다.")

    if service_name:
        prd_data["service_name"] = service_name
        prd_data["slug"] = slugify(service_name)

    # ── 승인 루프 ──
    try:
        base_dir = resolve_output_dir(folder_path)
    except ValueError as exc:
        print(f"[오류] {exc}")
        sys.exit(1)

    while True:
        print_prd_summary(prd_data, prd_version)
        print("""
PRD 초안이 생성되었습니다.
선택:
  revise  : PRD 수정 요청
  approve : 현재 PRD 기준으로 파생 문서 생성
  stop    : 종료
""")
        choice = ask("입력").strip().lower()

        if choice == "stop":
            print("종료합니다.")
            sys.exit(0)

        elif choice == "revise":
            revision_count += 1
            prd_version = f"v0.{revision_count + 1}"
            revision_note = ask("수정 요청 내용")
            if not revision_note:
                print("수정 내용이 없으면 approve 또는 stop을 입력하세요.")
                continue

            print(f"\nPRD 재생성 중... ({prd_version})")
            if provider != "template" and api_key:
                prompt = PRD_SCHEMA_PROMPT.format(
                    description=description,
                    tech_stack=tech_stack,
                    revision_note=f"\n수정 요청: {revision_note}",
                )
                new_prd = call_api(prompt, provider, api_key)
                if new_prd:
                    if service_name:
                        new_prd["service_name"] = service_name
                        new_prd["slug"] = slugify(service_name)
                    prd_data = new_prd
                else:
                    print("[경고] 재생성 실패. 기존 PRD를 유지합니다.")
            else:
                print("[템플릿 모드] API 없이는 자동 수정이 불가합니다. PRD.md를 직접 수정하세요.")

        elif choice == "approve":
            break

        else:
            print("revise / approve / stop 중 하나를 입력하세요.")

    # ── Phase 2: 파생 문서 생성 ──
    print(f"\n[STEP 2/2] PRD {prd_version} 기준으로 파생 문서 생성 중...")

    if provider != "template" and api_key:
        prd_json = json.dumps(prd_data, ensure_ascii=False, indent=2)
        der_prompt = DERIVATIVES_SCHEMA_PROMPT.format(
            prd_json=prd_json, tech_stack=tech_stack
        )
        der_data = call_api(der_prompt, provider, api_key)
    else:
        der_data = None

    if der_data is None:
        der_data = fallback_derivatives(prd_data, tech_stack)

    if base_dir.exists():
        overwrite = ask(
            f"\n[경고] {base_dir} 이미 존재합니다. 문서를 갱신할까요? TASKS.md는 완료 이력을 유지하고 새 태스크만 append합니다. (y/N)",
            "N",
        )
        if overwrite.lower() != "y":
            print("취소했습니다.")
            sys.exit(0)

    # PRD (단일 기준 문서)
    today = str(date.today())
    write_file(base_dir / "PRD.md", render_prd(prd_data, tech_stack, prd_version, "Approved"))

    # 파생 문서 루트
    write_file(base_dir / "AGENTS.md", render_agents(prd_data, der_data, tech_stack, prd_version))

    # TASKS.md: Claude CLI로 생성, 실패 시 기존 코드 프로젝트는 safe fallback 사용
    print("  [TASKS] Claude CLI로 TASKS.md 생성 중...")
    tasks_ok = generate_tasks_via_claude_cli(base_dir, prd_version, detect_code_files, summarize_codebase)
    if not tasks_ok:
        print("  [TASKS] 폴백 적용")
        write_tasks_with_fallback(base_dir, prd_data, der_data, prd_version, detect_code_files, summarize_codebase)
    write_file(base_dir / "RULES.md", render_rules(prd_data, der_data, tech_stack, prd_version))
    write_file(base_dir / "LOOP.md", render_loop(prd_data, der_data, prd_version))
    write_file(base_dir / "USER_FLOW.md", render_user_flow(prd_data, der_data, prd_version))
    write_file(base_dir / "SCREENS.md", render_screens(prd_data, der_data, prd_version))
    write_file(base_dir / "FUNCTION_SPECS.md", render_function_specs(prd_data, der_data, prd_version))
    write_file(base_dir / "DATA_MODEL.md", render_data_model(prd_data, der_data, prd_version))
    write_file(base_dir / "TEST_CHECKLIST.md", render_test_checklist(prd_data, der_data, prd_version))

    # 프롬프트
    write_file(base_dir / "PROMPT_CODEX.md", render_prompt_codex(prd_data, der_data, prd_version, tech_stack))
    write_file(base_dir / "PROMPT_CLAUDE_REVIEW.md", render_prompt_claude_review(prd_data, der_data, prd_version))

    # prompts/
    write_file(base_dir / "prompts" / "0_spec.txt", render_prompt_spec(prd_data, der_data, prd_version))
    write_file(base_dir / "prompts" / "1_plan.txt", render_prompt_plan(prd_data, der_data, prd_version))
    write_file(base_dir / "prompts" / "2_build.txt", render_prompt_build(prd_data, der_data, prd_version))
    write_file(base_dir / "prompts" / "3_test.txt", render_prompt_test(prd_data, der_data, prd_version))
    write_file(base_dir / "prompts" / "4_review.txt", render_prompt_review(prd_data, prd_version))
    write_file(base_dir / "prompts" / "5_ship.txt", render_prompt_ship(prd_data, prd_version))

    # personas/
    write_file(base_dir / "personas" / "code-reviewer.md", render_persona_code_reviewer())
    write_file(base_dir / "personas" / "test-engineer.md", render_persona_test_engineer())
    write_file(base_dir / "personas" / "security-auditor.md", render_persona_security_auditor())

    # checklists/
    write_file(base_dir / "checklists" / "testing.md", render_checklist_testing())
    write_file(base_dir / "checklists" / "security.md", render_checklist_security())
    write_file(base_dir / "checklists" / "performance.md", render_checklist_performance())

    # README
    readme = f"""# {prd_data['service_name']}

{prd_data['one_liner']}

> PRD Version: {prd_version} (Approved)
> Generated: {today}

## 파일 구조

### 단일 기준 문서 (Source of Truth)
- `PRD.md` — 모든 파생 문서의 기준

### 파생 문서 (PRD {prd_version} 기준)
```
PRD.md
 ├─ AGENTS.md          AI 에이전트 총괄 규칙
 ├─ TASKS.md           수락기준 포함 태스크 목록
 ├─ RULES.md           구현·테스트·보안 규칙
 ├─ LOOP.md            반복 추적 KPI
 ├─ USER_FLOW.md       사용자 흐름 정의
 ├─ SCREENS.md         화면 구성서
 ├─ FUNCTION_SPECS.md  기능 명세
 ├─ DATA_MODEL.md      데이터 모델
 ├─ TEST_CHECKLIST.md  테스트 체크리스트
 ├─ PROMPT_CODEX.md    Codex 1차 구현 프롬프트
 └─ PROMPT_CLAUDE_REVIEW.md  Claude 리뷰/고도화 프롬프트
```

## 시작 순서
1. `prompts/0_spec.txt` → AI에 붙여넣기 (스펙 검증)
2. `PROMPT_CODEX.md` → Codex에 붙여넣기 (1차 구현)
3. `PROMPT_CLAUDE_REVIEW.md` → Claude Code에 붙여넣기 (고도화)
4. `prompts/5_ship.txt` → 배포 전 최종 점검

## 개발 환경
{tech_stack}

## 생성 경로 규칙
사용자가 입력한 `생성 경로`가 최종 폴더입니다.
한글이 있으면 폴더명에 그대로 유지됩니다.
한글이 전혀 없을 때만 안전한 영문 slug를 사용합니다.
Windows 금지 문자나 너무 긴 경로는 생성 전에 오류로 중단됩니다.

## PRD 변경 시
PRD.md를 수정하면 파생 문서도 재생성 또는 동기화가 필요합니다.
재생성: `run_generator.bat` 재실행
"""
    write_file(base_dir / "README.md", readme)

    total = 25
    print(f"\n{'=' * 60}")
    print(f"  완료! 파일 {total}개 생성됨")
    print(f"  경로: {base_dir}")
    print(f"  PRD 버전: {prd_version} (Approved)")
    print(f"{'=' * 60}")

    # auto_dev 루프 큐에 자동 등록
    queue_file = Path(__file__).parent / "dashboard" / "queue.json"
    try:
        import json as _json
        queue = []
        if queue_file.exists():
            try:
                queue = _json.loads(queue_file.read_text(encoding="utf-8"))
                if not isinstance(queue, list):
                    queue = []
            except Exception:
                queue = []
        project_str = str(base_dir)
        if project_str not in queue:
            queue.append(project_str)
            queue_file.write_text(_json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n  ✅ 루프 큐에 자동 등록됨: {project_str}")
        else:
            print(f"\n  ℹ 이미 큐에 등록돼 있습니다: {project_str}")
    except Exception as e:
        print(f"\n  ⚠ 큐 등록 실패: {e}")

    print("\n다음 단계:")
    print("  1. PROMPT_CODEX.md → Codex에 붙여넣기 (1차 구현)")
    print("  2. 대시보드 ON → 루프 자동 실행")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        run_self_tests()
    elif len(sys.argv) > 1 and sys.argv[1] == "--description":
        import argparse as _ap
        _p = _ap.ArgumentParser()
        _p.add_argument("--description", required=True)
        _p.add_argument("--path", default=os.getcwd())
        _p.add_argument("--service-name", default="")
        _p.add_argument("--stack", default="Streamlit")
        _p.add_argument("--provider", default="template")
        _p.add_argument("--api-key", default="")
        _args = _p.parse_args()
        _result = generate_scaffold(
            description=_args.description,
            folder_path=_args.path,
            service_name=_args.service_name,
            tech_stack=_args.stack,
            api_key=_args.api_key,
            provider=_args.provider,
        )
        if not _result["ok"]:
            print(f"[ERROR] {_result['error']}")
            sys.exit(1)
    else:
        main()
