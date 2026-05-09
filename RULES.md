# RULES.md — 금지사항 및 검증 기준

> Auto Dev Queue 운영 규칙. AI 에이전트와 사람 모두 이 규칙을 따릅니다.

---

## 절대 금지 (Hard Rules)

| # | 금지 행동 | 이유 |
|---|---|---|
| 1 | 기존 앱 기능 파일 직접 수정 | 기존 서비스 중단 방지 |
| 2 | `main` 브랜치 직접 push | 검토 없는 배포 방지 |
| 3 | 자동 merge 수행 | 사람이 검토 후 직접 merge |
| 4 | Secret/API Key/Token 값 출력 | 보안 |
| 5 | `.env`, `.env.*` 파일 수정 | 환경변수 보호 |
| 6 | `.github/workflows/*.yml` 자동 수정 | 워크플로우 보호 |
| 7 | 동일 TASK 3회 이상 자동 재시도 | 무한 루프 방지 |
| 8 | BLOCKED TASK 자동 재시도 | 사람 개입 필요 항목 보호 |
| 9 | 대규모 리팩토링 | 범위 초과 |
| 10 | 불필요한 패키지 설치 | 의존성 오염 방지 |
| 11 | 로컬 PC 경로 (`D:/`, `C:/`) 하드코딩 | 이식성 |
| 12 | PowerShell 의존 코드 추가 | Linux 환경 호환 |
| 13 | Codex CLI 의존 추가 | 외부 CLI 의존 금지 |

---

## 검증 기준 (Validation Checklist)

### Python 파일 변경 시

- [ ] `python -m py_compile <파일>` 통과
- [ ] 관련 테스트 파일이 있으면 실행 (`tests/test_<stem>.py`)
- [ ] import 오류 없음

### YAML 파일 변경 시

- [ ] `python -c "import yaml; yaml.safe_load(open('<파일>'))"` 통과
- [ ] 들여쓰기 일관성 확인

### JSON 파일 변경 시

- [ ] `python -c "import json; json.load(open('<파일>'))"` 통과

### Secret 검사

- [ ] 코드에 `sk-`, `ghp_`, `xoxb-` 등 Key 패턴 없음
- [ ] `.env` 파일 내용이 코드에 하드코딩되지 않음

### 기존 파일 보호

- [ ] `git diff --name-only`에 기존 앱 파일이 포함되지 않음
- [ ] `dashboard/streamlit_app.py` 수정 안 됨 (의도적 변경 제외)
- [ ] `dashboard/server.py`, `dashboard/loop_runner.py` 등 수정 안 됨

---

## TASK 상태 정의

| 상태 | 의미 | 자동 처리 |
|---|---|---|
| `PENDING` | 처리 대기 중 | 다음 실행 시 선택됨 |
| `RUNNING` | 현재 실행 중 | — |
| `DONE` | 성공 완료 | `done_tasks.md`에 기록 |
| `FAILED` | 실패 (재시도 가능) | 재시도 횟수 < MAX_RETRIES이면 재시도 |
| `BLOCKED` | 외부 설정 필요 | 자동 재시도 안 함, 사람 개입 필요 |

---

## BLOCKED 판정 기준

다음 중 하나라도 해당하면 BLOCKED:

- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` 모두 없음
- `GH_TOKEN`, `AUTO_DEV_PAT` 권한 부족으로 PR 생성 불가
- 필수 파일 (`TASKS.md`, `scripts/run_auto_dev_once.py`) 없음
- 동일 TASK가 `MAX_RETRIES` (기본 2회) 이상 실패

---

## PR 생성 규칙

- PR 생성: `AUTO_DEV_PAT` 우선, 없으면 `secrets.GITHUB_TOKEN`
- PR 중복 방지: 생성 전 `gh pr list --state open --head <branch>` 확인
- PR 내용: 변경 파일 목록, 변경 이유, 검증 결과 포함
- **자동 merge 금지** — 사람이 직접 검토 후 merge

---

## 필요한 Secret 목록

| Secret 이름 | 용도 | 등록 위치 |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI GPT API | GitHub Settings → Secrets → Actions |
| `ANTHROPIC_API_KEY` | Anthropic Claude API | GitHub Settings → Secrets → Actions |
| `AUTO_DEV_PAT` | PR 생성용 Personal Access Token | GitHub Settings → Secrets → Actions |

`AUTO_DEV_PAT` 없을 경우:
→ GitHub Settings → Actions → General → **Allow GitHub Actions to create and approve pull requests** 활성화
