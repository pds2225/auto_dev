# auto_dev

자동 개발 루프 — TASKS.md에 작업을 추가하면 AI가 순차적으로 처리합니다.

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

**1. 아래 링크 중 하나 클릭**

| 기능 | 설명 | 바로가기 링크 |
|---|---|---|
| **Auto Dev Loop** | 개발 목표 1개를 입력하면 AI가 코드 짜고 PR 생성 | [클릭해서 이동](https://github.com/pds2225/auto_dev/actions/workflows/auto-dev-loop.yml) |
| **Auto Dev Queue** | TASKS.md의 할 일 목록을 순서대로 자동 처리 | [클릭해서 이동](https://github.com/pds2225/auto_dev/actions/workflows/auto-dev-queue.yml) |

**2. 실행하기**
- 링크를 클릭하면 웹페이지가 열립니다
- 화면 중앙의 **Run workflow** 버튼 클릭
- 개발 목적을 입력 (예: "로그인 버튼 디자인 개선")
- **Run workflow** 버튼을 다시 클릭하면 실행 시작

**3. 결과 확인**
- 실행이 끝나면 **자동으로 PR이 생성**됩니다
- Pull Requests 탭에서 생성된 PR을 확인
- 내용을 검토하고 "Merge" 버튼을 누륾면 코드가 적용됩니다

> ⚠️ GitHub Actions를 사용하려면 아래 **초기 설정 1회**가 필요합니다.

---

### 방법 3 — TASKS.md 큐를 자동으로 처리하기

여러 개의 할 일을 한 번에 처리하고 싶을 때:

1. `TASKS.md` 파일을 여러 개의 TASK를 `## PENDING` 아래에 추가
2. GitHub Actions → **"Auto Dev Queue"** 실행
3. AI가 위에서부터 하나씩 자동으로 처리하고, 완료된 것은 `## DONE`으로 옮김
4. 코드 변경이 있으면 **자동으로 PR 생성**

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

아이디어만 있으면 개발 기획서와 태스크 목록을 자동으로 만들어줍니다:

```powershell
python ai_project_scaffold_generator.py
```

입력 예시:
- "배달음식 리뷰 요약 웹사이트"
- "기술스택: React + Python"

결과: `PRD.md`, `TASKS.md`, `AGENTS.md` 등 10개 문서가 **한 번에** 생성됩니다.

---

### 대시보드 보기 (화면으로 보고 싶을 때)

```powershell
cd D:\auto_dev\dashboard
streamlit run streamlit_app.py
```

웹브라우저가 열리면 현재 할 일 목록, 작업 진행 상태, 로그 기록을 **그래픽 화면**으로 볼 수 있습니다.

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
python scripts/auto_dev_prompt_loop.py            # PENDING 첫 TASK → auto_prompt_YYYYMMDD_HHMMSS.md 생성
python scripts/auto_dev_prompt_loop.py --copy     # 생성 후 Windows 클립보드에 복사
python scripts/auto_dev_prompt_loop.py --task-id TASK-003  # 특정 TASK 지정
python scripts/auto_dev_prompt_loop.py --repo D:\other_repo  # 다른 저장소 대상
```

---

## 프롬프트 생성 (auto_dev_prompt_loop)

```bash
python scripts/auto_dev_prompt_loop.py            # PENDING 첫 TASK → auto_prompt_YYYYMMDD_HHMMSS.md 생성
python scripts/auto_dev_prompt_loop.py --copy     # 생성 후 Windows 클립보드에 복사
python scripts/auto_dev_prompt_loop.py --task-id TASK-003  # 특정 TASK 지정
python scripts/auto_dev_prompt_loop.py --repo D:\other_repo  # 다른 저장소 대상
```
