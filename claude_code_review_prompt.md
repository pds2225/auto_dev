# Claude Code Review Prompt — project-health-auditor skill

## 배경

`project-health-auditor` 스킬에 대한 낮은 수준의 리뷰를 진행했고, 지적된 사항 4가지를 수정했습니다. Claude Code에서 해당 파일들을 읽고 전체 품질을 한 번 더 검토해 주세요.

## 대상 파일 (로컬 경로)

```
C:\Users\ekth3\.codex\skills\project-health-auditor\SKILL.md
C:\Users\ekth3\.codex\skills\project-health-auditor\references\diagnostic-checklist.md
C:\Users\ekth3\.codex\skills\project-health-auditor\references\prompt-templates.md
C:\Users\ekth3\.codex\skills\project-health-auditor\references\severity-matrix.md
C:\Users\ekth3\.codex\skills\project-health-auditor\agents\openai.yaml
```

## 이번에 반영한 수정사항 요약

### 1. SKILL.md
- **실행 환경 명시** 추가: "이 스킬은 Claude Code(로컬 저장소) 또는 Claude.ai(파일 첨부/경로 입력)에서 실행합니다. 사용자는 프로젝트 경로 또는 파일을 제공합니다."
- **AI Handoff Choice**에 Kimi → Claude 과도한 기획안 처리 규칙 추가: "If Kimi produced an oversized plan, Claude must review it first, remove scope that is too large, and convert only one selected item into a developer-ready prompt."

### 2. diagnostic-checklist.md
- **기능 개선 섹션에 Difficulty mapping** 추가:
  - Easy: single file change, simple display/text change, no contract change.
  - Medium: a few files, small test update, or UI flow adjustment without DB/API contract change.
  - Hard: requires DB/API contract change, cross-module behavior, auth, payments, or deployment changes.

### 3. prompt-templates.md
- **3개 템플릿의 "검증 방법"**에 모두 수동 검증 fallback 추가:
  - "테스트가 없는 프로젝트라면, 수동 확인 절차(어떤 화면/동작을 확인하는지)를 기술한다."

### 4. severity-matrix.md, agents/openai.yaml
- 기존 리뷰에서 "꼭 수정할 것"으로 지적된 항목은 이미 이전에 반영되어 있음 (변경 없음).

## 리뷰 요청 항목

아래 항목을 검토해서 문제가 있으면 지적해 주세요.

1. **문서 간 일관성**
   - SKILL.md, diagnostic-checklist.md, prompt-templates.md, severity-matrix.md 간에 용어(예: "DB/API 계약", "회귀 위험", "수동 확인")가 일관되게 사용되는가?
   - 한/영 혼용이 자연스러운가? (AI 도구 호환성을 위해 의도적으로 혼용하고 있음)

2. **누락 또는 모순**
   - 이번 수정으로 인해 기존 규칙과 충돌하는 문장이 있는가?
   - Fallback이나 Core Rules와 새로 추가된 내용이 논리적으로 맞지 않는 부분이 있는가?

3. **실무 적용 가능성**
   - "테스트가 없는 프로젝트라면 수동 확인 절차를 기술한다"는 문장이 3개 템플릿에 모두 추가되었는데, Codex/Cursor/Claude가 실제로 이 지시를 따를 수 있는가?
   - Difficulty mapping이 diagnostic-checklist.md에만 있고 severity-matrix.md에는 없는데, 이 구조가 문제 없는가?

4. **SKILL.md 구조**
   - 실행 환경 안내가 SKILL.md 상단에 위치한 것이 적절한가? 아니면 Workflow 앞이나 Fallbacks 쪽이 더 나은가?
   - AI Handoff Choice에 추가한 Kimi → Claude 규칙이 이미 Core Rules에 있는 "If another AI produced a plan..."과 중복되는가? 중복이라면 어떤 쪽을 남기는 게 나은가?

5. **오탈자/문법**
   - 영어 문장에 어색한 표현이 있는가?
   - 한국어 문장에 어색한 표현이 있는가?

## 출력 형식

```
1. 전체 평가 (Pass / Minor fix needed / Major fix needed)
2. 파일별 이슈 목록 (파일명, 줄 번호, 문제, 권장 수정안)
3. 구조적 제안 (있는 경우에만)
4. 최종 권장사항
```

리뷰를 마치면, 발견한 문제가 없다면 "Pass"라고 명확히 표기해 주세요.
