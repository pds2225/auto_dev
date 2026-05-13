# Diagnostic Checklist

Use this checklist to find practical issues for a non-developer. Do not force every item into the output; include only evidence-backed findings.

## 오류 해결

Check:

- Does the app start from the documented command?
- Are required environment variables documented without exposing secret values?
- Can the main user flow fail with a vague error?
- Are paths hardcoded to one local machine, port, or folder?
- Are dependencies split across multiple requirement/package files in a confusing way?
- Do tests exist for the workflow the user cares about?
- Are generated files, logs, caches, or local settings likely to be committed by mistake?
- Are security-sensitive values printed, hardcoded, or sent to the frontend?

Translate to the user as:

- "사용자에게 보이는 증상"
- "안 고치면 생길 문제"
- "지금 고쳐야 하는 이유"

## 기능 개선

Check:

- Is there a repeated manual step that can be made one-click?
- Is there a useful empty state or fallback missing?
- Can the user recover after a failed action?
- Is the next action unclear after a result appears?
- Is there an obvious MVP feature already supported by the backend but not surfaced?
- Can the improvement be done without changing DB/API contracts?

Avoid:

- New product strategy.
- Large feature bundles.
- Ideas that require unclear business decisions.

## 프론트엔드 개선

Check only when the project has a UI.

- Does the first screen show the real task, not marketing filler?
- Are buttons, forms, and result states understandable?
- Does long Korean or English text fit on mobile?
- Are loading, empty, error, and success states visible?
- Is the next user action obvious after each result?
- Does the UI use familiar controls instead of text-heavy blocks?
- Does the page avoid cards inside cards and over-decorated layouts?

If the project is CLI/API/backend-only, write:

`해당 없음: 현재 확인 범위에서 사용자 화면 또는 프론트엔드 진입점이 확인되지 않음.`

## Scope Filter

Before selecting the one implementation task, reject candidates that:

- require full rewrite,
- require broad DB/API contract changes,
- touch unrelated files,
- depend on missing credentials,
- require multiple agents to complete at once,
- cannot be verified locally or with a clear manual check.
