# Claude Code Review Prompt (Lite)

아래 5개 파일을 읽고, 최근에 추가된 4가지 수정사항이 기존 구조와 충돌하거나 어색한지만 검토해 주세요.

```
C:\Users\ekth3\.codex\skills\project-health-auditor\SKILL.md
C:\Users\ekth3\.codex\skills\project-health-auditor\references\diagnostic-checklist.md
C:\Users\ekth3\.codex\skills\project-health-auditor\references\prompt-templates.md
C:\Users\ekth3\.codex\skills\project-health-auditor\references\severity-matrix.md
C:\Users\ekth3\.codex\skills\project-health-auditor\agents\openai.yaml
```

## 이번에 추가된 내용 (4가지)

1. **SKILL.md 상단**: `> 실행 환경: 이 스킬은 Claude Code(로컬 저장소) 또는 Claude.ai(파일 첨부/경로 입력)에서 실행합니다...`
2. **SKILL.md AI Handoff Choice**: `If Kimi produced an oversized plan, Claude must review it first, remove scope that is too large, and convert only one selected item into a developer-ready prompt.`
3. **diagnostic-checklist.md 기능 개선 섹션**: `Difficulty mapping` 추가 (Easy/Medium/Hard 정의)
4. **prompt-templates.md 3개 템플릿**: `검증 방법` 마지막에 `테스트가 없는 프로젝트라면, 수동 확인 절차(어떤 화면/동작을 확인하는지)를 기술한다.` 추가

## 검토해 줄 것 (3가지만)

1. **문서 간 모순**: 새로 추가한 내용이 기존 Core Rules / Fallbacks / Workflow와 논리적으로 충돌하는가?
2. **중복 여부**: SKILL.md에 추가한 "Kimi produced an oversized plan..." 규칙이 이미 Core Rules의 "If another AI produced a plan..."와 중복되는가? 중복이면 어느 쪽을 지우는 게 나은가?
3. **실무 가능성**: prompt-templates.md의 "테스트가 없으면 수동 확인 절차 기술" 지시가 3개 템플릿에 모두 들어간 것이 실제로 쓸모 있을까, 아니면 노이즈일까?

## 출력 형식

```
- 평가: Pass / Minor fix / Major fix
- 이슈 (있으면 파일명 + 이유)
- 최종 권장사항
```
