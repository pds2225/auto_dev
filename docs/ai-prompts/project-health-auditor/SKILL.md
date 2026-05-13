---
name: project-health-auditor
description: Diagnose an existing project for non-developers before implementation. Use when the user asks what is wrong with a project, wants project health review, feature ideas, frontend improvement candidates, implementation priority, or a Claude/Codex/Cursor prompt. Produces 오류 해결, 기능 개선, 프론트엔드 개선 findings, ranks priorities, chooses one next task, and writes a copy-paste implementation prompt without editing code.
---

# Project Health Auditor

Use this skill to inspect a project and explain what should be fixed or improved before any implementation begins. The local Codex skill and the repo copy should stay equivalent: update both when changing the workflow.

## Core Rules

- Do not edit code, create product scope, or start implementation.
- Do not recommend a full rewrite unless the project cannot run and there is evidence.
- Do not suggest multiple simultaneous implementation tasks.
- Do not change DB/API contracts unless the finding is explicitly about a broken contract.
- Do not invent frontend work for CLI, library, or backend-only projects.
- Prefer evidence from files, commands, tests, logs, routes, UI entrypoints, and git state.
- Explain every issue in non-developer language first, then add implementation detail.
- Treat refactoring as one possible solution, not the goal. First decide whether the user problem is 오류 해결, 기능 개선, or 프론트엔드 개선.
- If another AI produced a plan, review it first, remove oversized scope, and convert only one selected item into a developer-ready prompt.

## Workflow

1. Identify project type and entrypoints.
2. Read the smallest useful set of files: README, task tracker, package/dependency files, app entrypoints, tests, route/API definitions, and frontend entrypoints if present.
3. Use `references/diagnostic-checklist.md` to avoid missing common non-developer pain points.
4. Classify findings into:
   - 오류 해결: broken behavior, run/deploy failure, security, environment, data loss, test failure.
   - 기능 개선: useful workflow or product improvement that fits the current structure.
   - 프론트엔드 개선: screen flow, mobile layout, labels, forms, empty states, result views.
5. Score severity and difficulty using `references/severity-matrix.md`.
6. Choose TOP 3 by user impact, severity, effort, and regression risk.
7. Select exactly one task for the next implementation turn.
8. Generate a copy-paste prompt using `references/prompt-templates.md`.

## AI Handoff Choice

- Use Kimi for broad diagnosis, idea generation, and non-developer explanations only.
- Use Claude for plan review, risk review, and complex logic or test strategy.
- Use Cursor for small UI patches, code-location discovery, and narrow bug fixes.
- Use Codex for local execution, validation, repo edits, git/PR work, Notion updates, and skill maintenance.
- If the user asks "누구한테 시킬까", recommend the AI role and provide the exact copy-paste prompt.

## Required Output

Always output the following seven sections in order.

### 1. 전체 결론

State whether the project is mostly healthy, needs partial fixes, or needs scope cleanup. Keep it short and decision-ready.

### 2. 오류 해결 후보

Use a table with:

| 문제 | 사용자에게 보이는 증상 | 발생 가능한 문제 | 심각도 | 구현 난이도 | 추천 여부 | 예상 수정 파일 |
|---|---|---|---|---|---|---|

If there is no evidence, write `확인된 오류 해결 후보 없음`.

### 3. 기능 개선 후보

Use a table with:

| 개선 아이디어 | 사용자 가치 | 지금 가능한 범위 | 발생 가능한 문제 | 심각도 | 구현 난이도 | 추천 여부 | 예상 수정 파일 |
|---|---|---|---|---|---|---|---|

Only include improvements that fit the current product direction.

### 4. 프론트엔드 개선 후보

If the project has UI screens, use a table with:

| 화면/흐름 문제 | 사용자가 헷갈릴 지점 | 개선 방향 | 모바일 영향 | 심각도 | 구현 난이도 | 추천 여부 | 예상 수정 파일 |
|---|---|---|---|---|---|---|---|

If the project is CLI/API/backend-only, write:

`해당 없음: 현재 확인 범위에서 사용자 화면 또는 프론트엔드 진입점이 확인되지 않음.`

### 5. 우선순위 TOP 3

For each item include:

- 분류: 오류 해결 / 기능 개선 / 프론트엔드
- 사용자 가치:
- 구현 난이도:
- 회귀 위험:
- 추천 이유:

### 6. 이번에 구현할 1개

Pick one task only.

Include:

- 선택 항목:
- 선택 이유:
- 수정 예상 범위:
- 하지 말아야 할 것:
- 검증 방법:

### 7. 구현 프롬프트

Write one copy-paste prompt for Claude, Codex, or Cursor.

The prompt must include:

- 역할
- 작업 목표
- 배경
- 수정 가능 범위
- 수정 금지 범위
- 구현 요구사항
- 검증 방법
- 출력 형식

Start the prompt with the target AI when useful:

- `Cursor에게 줄 프롬프트` for narrow UI or one-file bug fixes.
- `Claude에게 줄 프롬프트` for plan review, logic, and tests.
- `Codex에게 줄 프롬프트` for local execution, verification, and repo changes.

## Fallbacks

- If tests cannot run, state the exact blocker and continue with static evidence.
- If a file cannot be found, do not invent it. Mark the expected file as `확인 필요`.
- If there are too many findings, keep only the highest-impact candidates.
- If the user asks for implementation after the audit, convert the selected single task into an implementation prompt and stop.
- If a helper skill or external review is missing, do not block the audit. Continue with standalone evidence and mark that helper as `미사용`.
- If multiple CRITICAL findings are found, select the one that is Easy difficulty and independently fixable. If all are Hard, mark the highest user-impact finding as P0 and the rest as P0-pending.
