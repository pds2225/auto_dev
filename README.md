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

### 방법 5 — 대시보드에서 실행하고 모니터링하기

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

---

## 🆕 자동개발 하네스 (통합) — 한 줄로 "하다 만 작업" 자동 완료

> 2026-06-14 합의. 트리거 한마디로 여러 repo의 **미완성 작업을 승인 없이 완료**한다. 위 방법 1~5를 흡수·통합하는 상위 하네스.

### 트리거
`자동개발`, `목표:`, `자동 개발`, `auto-dev`

### 실행 (레포 이동 불필요 — 어느 폴더에서나)

| 입력 | 동작 |
|---|---|
| `자동개발` | 지금 폴더 1개 |
| `자동개발 전부` | 등록된 모든 repo **병렬** |
| `자동개발 mail,v_up` | 지정한 것만 |
| `자동개발 목표: <내용>` | 목표 직접 지정 |

### 두 가지 모드
- **세션 즉시 모드**: 지금 클로드 창에서 subagent 병렬 자율개발 (대화형)
- **야간 무인 모드**: Windows 작업스케줄러 + headless `claude -p` 루프 (사람 없이 밤에)

### Q1. 범위 산정 — "미완성 = 완료 대상" 탐지 소스 (확정)

목표를 직접 안 적어도, 각 repo에서 아래 **3가지를 자동 수집**해 할 일 큐를 만든다:

1. **RESUME.md의 "진행 중 / 다음 액션"** 미완료 항목 — 최우선
2. **열린 PR(미병합)** — 끝내고 안 합친 것
3. **실패하는 테스트** — 깨졌거나 미완성

- 우선순위: **실패 테스트 > 열린 PR > RESUME 다음 액션**
- **큐가 빌 때까지** 각 항목을 `구현 → 테스트 통과 → 커밋 → PR → 검증 통과 시 병합`으로 완료
- 막히면 그 항목만 `BLOCKED` 표시하고 다음으로 (멈추지 않음)
- ⚠️ 저장 안 한 변경(dirty)·stash·GOALS/TASKS·TODO 주석은 **이번 범위에서 제외**(참고만, 함부로 건드리지 않음)

### Q2. 대상 repo (등록)

| repo | 용도 |
|---|---|
| `D:\mail` | 정부지원사업 공고 수집 |
| `D:\v_up` | STT 통화/회의 요약 |
| `D:\auto_write` | 문서 품질 개선/사업계획서 |
| `D:\_worklog` | work-cockpit 업무 관제 |
| `D:\DIG` | (용도 미확인) |
| `D:\walk` | (용도 미확인) |
| `D:\auto_shopper` | 쇼핑 대행 |
| `D:\marketgate` | (용도 미확인) |
| `D:\client` | (용도 미확인) |
| `D:\auto_addcalender` | 캘린더 자동 등록 |

### 권한·안전 (무인 실행 가드)

| 허용 | 차단 |
|---|---|
| Read/Edit/Write/Glob/Grep, 제한된 Bash | **파일 삭제** (rm·del·Remove-Item) |
| 파일 **이동·이름변경** (move·git mv) | `git reset --hard`·force push |
| git add/commit/branch/**push/PR/병합** (로컬↔GitHub sync) | **main 직접 push** (작업브랜치→PR만) |
| `gh`·`git` 네트워크 | 임의 네트워크(curl·wget), Secret 출력·커밋 |

- 멈춤 조건: **검증 실패 · Secret 포함 · 되돌리기 어려운 파괴적 변경 · repo 금지사항 위반** → 자동 진행 중단·보고
- Secret 자동 마스킹, 실제 메일 발송 등 외부 부작용은 repo 규칙대로 dry-run

> ⚠️ **정책 차이**: 이 통합 하네스는 "검증 통과 시 자동 병합"을 허용합니다(위 방법 1~5의 "자동 merge 금지"와 다름 — **안전가드를 모두 충족할 때만** 병합).
