# auto_dev

자동 개발 루프 — TASKS.md에 할 일을 적어두면 AI가 순서대로 처리합니다.

> **비개발자도 사용 가능합니다.** 복잡한 설정 없이 메모장과 웹브라우저만으로 AI에게 개발을 맡길 수 있습니다.

---

## 사용 환경

| 방식 | 필요한 것 | 난이도 |
|---|---|---|
| **로컬 (Windows)** | Python 설치 + 메모장 | ⭐ 쉬움 |
| **클릭 한 번 (GitHub)** | GitHub 계정 + 웹브라우저 | ⭐⭐ 보통 |

> API 키(Claude/OpenAI)가 있으면 똑똑한 AI가 작업합니다. **없어도 기본 기능은 사용 가능**합니다.

---

## 비개발자용 사용법

### 방법 1 — 로컬에서 AI 지시서 만들기 (가장 쉬움)

1. **메모장으로 `TASKS.md` 열기**
2. `## PENDING` 아래에 이렇게 적기:
   ```
   - TASK-100: 로그인 버튼 디자인 개선
   ```
   - 쉽게 말하면 `PENDING`은 **아직 시작 전인 할 일 칸**입니다.
3. **PowerShell** 실행 후 아래 명령 입력:
   ```powershell
   cd D:\auto_dev
   .\venv\Scripts\activate
   python scripts\auto_dev_prompt_loop.py
   ```
4. `auto_prompt_날짜_시간.md` 파일이 생성됨
5. 이 파일 내용을 ChatGPT, Claude, Codex 등에 붙여넣기 → AI가 코드를 짜줍니다

> 💡 `--copy` 옵션을 붙이면 파일 대신 **바로 클립보드에 복사**됩니다:
> ```powershell
> python scripts\auto_dev_prompt_loop.py --copy
> ```

---

### 방법 2 — GitHub에서 클릭 한 번으로 실행 (클우드)

> **yml 파일이 뭔가요?** → GitHub에게 "이런 순서로 일해"라고 적어놓은 설명서입니다. 세탁기의 '표준 코스' 버튼처럼, 누륾면 정해진 순서로 자동 실행됩니다. **직접 열어볼 필요 없어요.**

**핸드폰에서도 실행 가능합니다.**

**1. 아래 링크 중 하나 클릭**

| 기능 | 설명 | 바로가기 링크 |
|---|---|---|
| **Auto Dev Loop** | 개발 목표 1개를 입력하면 AI가 코드 짜고 PR 생성 | [클릭해서 이동](https://github.com/pds2225/auto_dev/actions/workflows/auto-dev-loop.yml) |
| **Auto Dev Queue** | TASKS.md의 할 일 목록을 순서대로 자동 처리 | [클릭해서 이동](https://github.com/pds2225/auto_dev/actions/workflows/auto-dev-queue.yml) |

**2. 실행하기 (PC나 핸드폰 브라우저)**
- 링크를 클릭하면 웹페이지가 열립니다
- 오른쪽 위의 **Run workflow** 버튼 클릭 (핸드폰에서는 ⋮ 메뉴 안에 있음)
- 개발 목표를 입력 (예: "로그인 버튼 디자인 개선")
- **Run workflow** 버튼을 다시 클릭하면 실행 시작

**3. 결과 확인**
- 실행이 끝나면 **자동으로 PR이 생성**됩니다
- Pull Requests 탭에서 생성된 PR을 확인
- 내용을 검토하고 "Merge" 버튼을 누륾면 코드가 적용됩니다

> ⚠️ GitHub Actions를 사용하려면 아래 **초기 설정 1회**가 필요합니다.

---

### 방법 3 — TASKS.md 할 일 목록을 자동으로 처리하기

여러 개의 할 일을 한 번에 처리하고 싶을 때:

1. `TASKS.md` 파일에 여러 개의 할 일을 `## PENDING` 아래에 추가
2. GitHub Actions → **"Auto Dev Queue"** 실행
3. AI가 위에서부터 하나씩 자동으로 처리하고, 완료된 것은 `## DONE`으로 옮김
4. 코드 변경이 있으면 **자동으로 PR 생성**

상태 이름은 아래처럼 이해하면 됩니다:

| 화면/파일에 보이는 이름 | 쉬운 뜻 |
|---|---|
| `PENDING` | 아직 시작 전인 할 일 |
| `RUNNING` | 지금 처리 중인 일 |
| `DONE` | 처리 완료 |
| `FAILED` | 자동 처리 실패, 다시 확인 필요 |
| `BLOCKED` | API 키/권한처럼 사람이 먼저 해결해야 함 |

---

### 방법 4 — AI끼리 작업 넘기기 (Claude ↔ Codex)

Claude가 설계·리뷰를 하고 Codex가 로컬에서 코드를 수정하는 왕복 루프입니다.

**한 사이클 흐름**

| 단계 | 입력 파일 | 명령 | 생성 파일 | 다음 행동 |
|---|---|---|---|---|
| 1 | - | Claude에게 작업 지시 | `claude_result.md` (수동 저장) | Claude가 설계/리뷰 결과를 파일로 저장 |
| 2 | `claude_result.md` | `--from claude` | `codex_handoff_*.md` | 생성된 프롬프트를 Codex에 붙여넣기 |
| 3 | - | Codex에 프롬프트 실행 | `codex_result.md` (수동 저장) | Codex가 코드 수정 후 결과를 파일로 저장 |
| 4 | `codex_result.md` | `--from codex` | `claude_handoff_*.md` | 생성된 프롬프트를 Claude에 붙여넣기 |

> `--from`은 "누구의 결과를 입력으로 받았는가"가 아니라 **"누구에게 넘길 프롬프트를 만드는가"**를 의미합니다.
> - `--from claude` → **Codex**가 실행할 프롬프트 생성
> - `--from codex` → **Claude**가 리뷰할 프롬프트 생성

**예시**

```powershell
# 1. Claude 결과를 D:\walk\claude_result.md 로 저장한 뒤
python scripts\auto_dev_handoff_loop.py --repo D:\walk --from claude --input D:\walk\claude_result.md --copy
# → codex_handoff_YYYYMMDD_HHMMSS.md 생성 + 클립보드 복사
# → 복사된 내용을 Codex에 붙여넣기

# 2. Codex 결과를 D:\walk\codex_result.md 로 저장한 뒤
python scripts\auto_dev_handoff_loop.py --repo D:\walk --from codex --input D:\walk\codex_result.md --copy
# → claude_handoff_YYYYMMDD_HHMMSS.md 생성 + 클립보드 복사
# → 복사된 내용을 Claude에 붙여넣기
```

**종료 조건**
- 테스트가 모두 통과하고 더 이상 개선할 부분이 없으면 종료
- 같은 실패를 3번 이상 반복하면 중단하고 사람이 개입

---

### 방법 5 — 새 프로젝트 기획서 자동 생성

아이디어만 있으면 개발 기획서와 할 일 목록을 자동으로 만들어줍니다:

```powershell
python ai_project_scaffold_generator.py
```

입력 예시:
- "배달음식 리뷰 요약 웹사이트"
- "기술스택: React + Python"

결과: `PRD.md`, `TASKS.md`, `AGENTS.md` 등 10개 문서가 **한 번에** 생성됩니다.

---

### 방법 6 — 대시보드에서 실행하고 모니터링하기

**대시보드란?** → 할 일 목록과 실행 버튼을 **화면**으로 보여주는 창입니다.

**1. 대시보드 실행**
```powershell
cd D:\auto_dev
python -m streamlit run dashboard\streamlit_app.py
```
→ 브라우저가 열리면 `http://localhost:8501`에서 확인

**2. 대시보드에서 할 수 있는 것**
| 기능 | 설명 |
|---|---|
| 🎯 GitHub Actions 실행 | 목표를 입력하고 버튼 클릭 → GitHub에서 AI가 개발 시작 |
| ⏰ 예약 설정 | 원하는 시간/요일을 설정하면 **자동으로 루프 시작** |
| 📊 통계 카드 | "완료 N개 / 평균 N분 / 실패 N개"를 한눈에 확인 |
| 📋 할 일 현황 | PENDING/RUNNING/DONE 개수 확인 |

**3. 핸드폰에서 대시보드 접속 (외부에서 보기)**

집 PC를 켜두고 핸드폰에서 대시보드를 보고 싶을 때:

```powershell
# 1. 대시보드 실행 (첫 번째 터미널)
cd D:\auto_dev
python -m streamlit run dashboard\streamlit_app.py

# 2. ngrok 터널링 (두 번째 터미널)
python -m ngrok http 8501
# → https://abcd1234.ngrok.io 같은 주소가 나옴
# → 이 주소를 핸드폰 브라우저에서 접속
```

> ngrok 주소는 실행할 때마다 바뀝니다. 고정 주소를 원하면 ngrok 무료 가입 후 토큰 등록이 필요합니다.

---

### 대시보드 개발자 운영 메모

최근 대시보드는 단순 실행 버튼을 넘어 로컬 루프 실행, 예약 실행, 큐 전환, 로그 통계를 함께 다룹니다. 운영 중 문제가 생기면 아래 파일과 상태값을 먼저 확인하세요.

| 영역 | 주요 파일 | 역할 |
|---|---|---|
| Streamlit UI | `dashboard/streamlit_app.py` | 로컬 루프 시작/중지, 예약 편집, GitHub Actions 트리거, 최근 로그 표시 |
| Flask API | `dashboard/server.py` | `/api/loop/*`, `/api/queue`, `/api/tasks`, `/api/prompt-generate`, `/api/snapshot` 제공 |
| 실행 루프 | `dashboard/loop_runner.py` | TASK 선택, Codex 실행, 테스트/디버그/재테스트, 완료 처리 |
| 예약 | `dashboard/task_scheduler.py` | `schedule.json`을 읽어 지정 시간에 `LoopRunner` 시작 |
| 통계 | `dashboard/log_analyzer.py` | `runner.log`의 완료/실패/평균 소요시간 계산 |
| Git 상태 | `dashboard/project_snapshot.py` | 브랜치, HEAD, origin, dirty 상태 조회 |

**실행 방식**

```powershell
# Streamlit 대시보드
python -m streamlit run dashboard\streamlit_app.py

# Flask API 대시보드
python dashboard\server.py
```

- `streamlit_app.py`와 `server.py`는 같은 전역 `runner`와 `loop_state.json`을 공유하므로 동시에 실행하지 마세요.
- GitHub Actions 실행 저장소 기본값은 `pds2225/auto_dev`입니다. 작업 대상 저장소 경로와 혼동하지 마세요.
- GitHub Actions 트리거/최근 실행/PR 조회에는 `GITHUB_TOKEN`이 필요합니다. Streamlit Secrets 또는 환경변수로만 넣고 파일에 저장하지 않습니다.

**런타임 파일**

| 파일 | 생성 위치 | 내용 | 커밋 여부 |
|---|---|---|---|
| `dashboard/loop_state.json` | 대시보드 실행 중 | 현재 실행 여부, 단계, 태스크, 프로젝트 경로 | 커밋하지 않음 |
| `dashboard/queue.json` | 프로젝트 대기 목록 사용 시 | 다음에 실행할 프로젝트 경로 배열 | 커밋하지 않음 |
| `dashboard/schedule.json` | 예약 설정 저장 시 | 실행 시간/요일/프로젝트 경로/마지막 실행일 | 개인 PC 설정이면 커밋하지 않음 |
| `dashboard/runner.log` | 루프 실행 중 | 루프 단계, 명령, 테스트 결과, 완료/실패 기록 | 커밋하지 않음 |
| `<project>/quality_log.json` | 품질 필터 동작 시 | Python 문법 오류와 연속 품질 이슈 | 보통 커밋하지 않음 |

**예약 설정 형식**

`TaskScheduler`는 1분마다 현재 시간을 `HH:MM`으로 비교하고, 오늘 요일이 포함된 활성 예약만 실행합니다. 같은 예약은 `last_run`에 `YYYYMMDD`가 기록되어 하루에 한 번만 실행됩니다.

```json
{
  "schedules": [
    {
      "time": "22:00",
      "days": ["월", "화", "수", "목", "금"],
      "project_dir": "D:\\my-project",
      "enabled": true,
      "last_run": ""
    }
  ]
}
```

- `project_dir`은 대시보드를 실행하는 PC에서 실제 존재하는 폴더여야 합니다.
- 요일 값은 `월`, `화`, `수`, `목`, `금`, `토`, `일` 중 하나입니다.
- 예약 시간이 지났는데 실행되지 않았다면 `enabled`, `days`, `project_dir`, `last_run`을 순서대로 확인하세요.

**루프 실행 흐름**

1. 대상 프로젝트에서 `TASK.md`를 먼저 찾고, 없으면 `TASKS.md`를 사용합니다.
2. `## Active`의 미완료 항목 중 가장 낮은 `TASK-숫자` 항목을 우선 선택합니다.
3. `## Active`에 실행할 항목이 없으면 `## PENDING`의 `- TASK-001: 설명` 또는 `- [ ] [TASK-001] 설명` 형식으로 fallback합니다.
4. 기준 테스트 → Codex 하드닝 → 테스트 → 실패 시 디버그 → 재테스트 순서로 실행합니다.
5. 테스트가 통과하면 해당 항목을 `[x]`로 바꾸고 다음 태스크로 진행합니다.
6. 실패해도 `AUTO_DEV_CONTINUE_ON_FAILURE=true`이면 실패 기록 후 다음 태스크로 진행합니다. 기본값은 `true`입니다.

주요 환경변수:

| 변수 | 기본값 | 의미 |
|---|---:|---|
| `CODEX_TIMEOUT` 또는 `CLAUDE_TIMEOUT` | `180` | Codex 1회 실행 제한 시간(초) |
| `CODEX_RETRY_COUNT` | `2` | Codex 재시도 횟수 |
| `AUTO_DEV_CONTINUE_ON_FAILURE` | `true` | 재테스트 실패 후 다음 태스크로 계속 진행할지 여부 |
| `AUTO_DEV_BUILD_TAG` | 파일 수정시각 기반 | 로그에 남기는 빌드 식별자 |

**로그와 통계**

새 로그 형식은 통계 파싱을 위해 아래 두 줄을 기준으로 합니다.

```text
2026-05-17 10:00:00,000 [INFO] [START] task=TASK-01 ts=2026-05-17T10:00:00
2026-05-17 10:00:30,000 [INFO] [DONE] task=TASK-01 duration_sec=30.0 status=passed
```

`log_analyzer.py`는 기존 한국어 로그(`📌 태스크:`, `완료 처리`, `실패 후 완료 처리`)도 함께 읽습니다. 통계 카드가 비어 있으면 `dashboard/runner.log` 존재 여부와 위 로그 형식을 확인하세요.

**문제 해결 체크리스트**

| 증상 | 확인할 것 |
|---|---|
| 대시보드가 이전 작업을 다시 시작함 | `dashboard/loop_state.json`의 `running`, `current_stage` 확인 |
| 예약이 실행되지 않음 | `schedule.json`의 `time`, `days`, `enabled`, `project_dir`, `last_run` 확인 |
| 두 프로젝트가 섞여 실행됨 | `queue.json`과 현재 `runner.project_dir` 확인 |
| GitHub Actions 404 | 워크플로우 저장소가 `auto-dev-loop.yml`이 있는 저장소인지 확인 |
| GitHub Actions 401 | `GITHUB_TOKEN` 권한과 만료 여부 확인 |
| 테스트가 계속 실패해도 넘어감 | `AUTO_DEV_CONTINUE_ON_FAILURE` 값 확인 |
| 통계가 0으로 표시됨 | `runner.log`에 `[DONE]` 또는 기존 `완료 처리` 로그가 있는지 확인 |

**관련 검증 명령**

```bash
python -m pytest tests/test_task_scheduler.py tests/test_log_analyzer.py -v
python dashboard/loop_runner.py --self-test
```

---

## GitHub Actions 초기 설정 (1회만)

GitHub 웹사이트에서 설정합니다:

| 항목 | 위치 | 필수 여부 |
|---|---|---|
| `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` | Settings → Secrets → Actions | ⭐ 둘 중 하나 필수 |
| `AUTO_DEV_PAT` | Settings → Secrets → Actions | 선택 (PR 생성용) |
| PR 권한 | Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests" | `AUTO_DEV_PAT` 없을 때 필수 |

> API Key가 없으면 AI가 실제로 코드를 짜지 않고 **mock(가상) 실행**만 합니다.

---

## 주의사항

| 주의 | 이유 |
|---|---|
| `main` 브랜치에 직접 저장하지 않기 | 실수로 지우면 복구가 어렵습니다 |
| API 키를 코드에 적지 않기 | 유출 위험이 있습니다 |
| 같은 실패를 3번 이상 반복하지 않기 | 무한 루프를 방지하기 위함입니다 |
| 자동 merge 금지 | PR은 사람이 직접 검토 후 merge 합니다 |

---

## 프롬프트 생성 (auto_dev_prompt_loop)

```bash
python scripts/auto_dev_prompt_loop.py            # 첫 번째 미처리 할 일(PENDING) → auto_prompt_YYYYMMDD_HHMMSS.md 생성
python scripts/auto_dev_prompt_loop.py --copy     # 생성 후 Windows 클립보드에 복사
python scripts/auto_dev_prompt_loop.py --task-id TASK-003  # 특정 할 일 지정
python scripts/auto_dev_prompt_loop.py --repo D:\other_repo  # 다른 저장소 대상
```
