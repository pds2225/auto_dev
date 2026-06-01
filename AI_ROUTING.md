# AI_ROUTING.md

## 목적

사용자는 AI 선택표를 외우지 않는다.
작업 유형을 먼저 분류하고 적합한 AI를 선택한다.

## 역할 분리

| 작업 유형 | 사용 AI | 위치 |
|---|---|---|
| 판단·설계·프롬프트 작성 | GPT 5.5 Thinking | PC/모바일, 웹/앱 |
| 로컬 코드 수정 | Cursor | PC 앱 |
| 로컬 자동개발 | Codex CLI | PC 로컬터미널 |
| 로컬 파일·로그·Git 점검 | Claude Code | PC 로컬터미널 |
| GitHub 원격 PR 작업 | Codex Cloud | 웹 |
| 브라우저 클릭·입력·업로드 자동화 | Kimi Claw / Genspark Claw | 웹 |
| 발표자료·인포그래픽 초안 | Genspark / NotebookLM | 웹 |

## 기본 판단

- GPT = 설계자
- Cursor = 로컬 수정자
- Codex CLI = 자동 구현자
- Claude Code = 리뷰·점검·안정화 담당
- Codex Cloud = GitHub 원격 PR 담당
- Kimi/Genspark Claw = 브라우저 자동화 담당

## 우선순위

1. 기존 기능 정상작동
2. 버그 수정
3. 회귀위험 제거
4. 테스트 보강
5. 자동화
6. 신규 기능