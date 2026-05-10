TASKS.md
— auto_dev

> Based on: PRD v0.1
> Status: Factory Refactoring
> Last Updated: 2026-04-24
> 대상 프로젝트: D:/auto_dev

---

## 공통 작업 원칙

### 0. 목표
가장 빠르게 사용자가 실제로 사용가능한 MVP를 만든다.

### 1. 구현 원칙
- 기존 구조를 최대한 유지한다.
- 최소 변경으로 구현한다.
- 단, 코드 효율이 2배 이상 좋아지는 경우 토큰 소모 2배까지는 허용한다.
- 고도화, 리팩토링, 호환성 동기화는 최하위 우선순위로 둔다.
- 우선 지원 기준은 Windows와 Android로 한정한다.
- macOS, iOS, Linux, 전체 브라우저 호환성은 후순위로 둔다.

### 2. 설명 원칙
- 비개발자도 이해할 수 있게 설명한다.
- 최대한 짧고 간단하게 설명한다.
- 이유와 원인은 최소화한다.
- 결과, 해야 할 일, 실행 방법, 검증 방법 중심으로 작성한다.

## Active

- [ ] [AUTO] 대시보드 상단 안내문을 더 짧고 명확하게 수정해줘.
기능은 변경하지 말고 문구만 수정해. (2026-05-09)
- [x] [TASK-35] 주요 오류 유형 확인 및 분류
- [x] [TASK-36] 오류 수정 및 코드 개선
- [x] [TASK-37] 최종 통합 테스트 수행
- [x] [TASK-38] UI 디자인 개선
- [x] [TASK-39] 태스크 목록 데이터 연동
- [x] [TASK-40] 사용자 인터랙션 개선
- [x] [TASK-41] 버그 수정 및 테스트
- [x] [TASK-42] 루프 모드 요구사항 정의
- [x] [TASK-43] 루프 모드 API 설계
- [x] [TASK-44] 루프 모드 구현
- [x] [TASK-45] 루프 모드 테스트
- [x] [TASK-46] 프론트엔드 UI 구현
- [x] [TASK-47] 백엔드와 프론트엔드 통합
- [x] [TASK-48] UI에서 야간 루프 모드 선택 추가
- [x] [TASK-49] 밤샘 루프 관련 API 엔드포인트 개발
- [x] [TASK-50] 밤샘 루프 모드 로직 구현
- [x] [TASK-51] 밤샘 루프 모드 테스트 케이스 작성
- [x] [TASK-52] 밤샘 루프 모드 UI 구현
- [x] [TASK-53] 루프 모드 로직 개발
- [x] [TASK-54] 밤샘 루프 모드 통합 테스트
- [x] [TASK-55] 디버깅 및 오류 수정
- [x] [TASK-56] 밤샘 루프 돌리기 모드 추가
- [x] [TASK-57] 밤샘 루프 돌리기 모드 추가
- [x] [TASK-58] 밤샘 루프 돌리기 모드 추가

- [x] [TASK-59] task추가-루프시작-gitpush 반복할수있는 기능개발
  - 원본 태스크: TASK-59
  - 의존성: 없음
  - 검증: pytest 또는 수동 실행

- [x] [TASK-60] task추가-루프시작-gitpush 반복할수있는 기능개발
  - 원본 태스크: TASK-60
  - 의존성: 없음
  - 검증: pytest 또는 수동 실행

- [x] [TASK-61] task추가-루프시작-gitpush 반복할수있는 기능개발
  - 원본 태스크: TASK-61
  - 의존성: 없음
  - 검증: pytest 또는 수동 실행
## Waiting On

- (없음)

---

## Done

- [x] 루프 엔진 기본 동작 (TASK-32까지 omni-sync 프로젝트 완료, 42 tests passed)
- [x] [TASK-01] scaffold_generator의 render_tasks()와 loop_runner의 TASKS.md 형식 불일치 수정
- [x] [TASK-02] loop_runner._install_deps()의 'omni-sync' 하드코딩 제거 및 범용 서브디렉토리 탐색으로 교체
- [x] [TASK-03] Claude Code 타임아웃 전략 개선 — 90s 고정값을 설정 가능하게 하고 타임아웃 시 재시도 횟수 제한 적용
- [x] [TASK-04] server.py SSE 스트림 빈 이벤트(0.3s 폴링) 제거 및 heartbeat 교체
- [x] [TASK-05] 대시보드에 TASKS.md 실시간 뷰어 추가 — /api/tasks 엔드포인트 + index.html 패널
- [x] [TASK-06] scaffold_generator 단위 테스트 작성 — render_tasks, append_task_to_tasks_md, get_next_task_id
- [x] [TASK-07] loop_runner 테스트 확장 — _mark_task_done, _find_test_dir 케이스 추가
- [x] [TASK-08] /api/tasks 취소선(~~text~~) 항목을 pending 대신 cancelled로 분류 — server.py 3줄 수정
- [x] [TASK-09] loop_runner self-test를 pytest로 수집 가능하게 분리 — tests/test_loop_runner.py 신규 작성
- [x] [TASK-10] 멀티 프로젝트 큐 관리 — dashboard/queue.json + 루프 완료 시 다음 프로젝트 자동 전환
- [x] [TASK-11] 하드닝 효과 측정 로그 — 하드닝 전/후 테스트 결과를 runner.log에 비교 기록
- [x] [TASK-12] scaffold → loop 원클릭 파이프라인 — scaffold 완료 시 queue.json 자동 등록
- [x] [TASK-13] TASKS.md 없는 프로젝트 자동 생성 모드 — 루프 진입 시 scaffold_generator 자동 실행 후 시작
- [x] [TASK-19] 로그 로테이션 — runner.log가 무한히 커지지 않게 관리하기
- [x] [TASK-20] Git 상태 연동 복구 — 대시보드에서 변경된 파일 목록 보이게 하기
- [x] [TASK-21] AI CLI 존재 여부 체크 — Codex 없어도 루프가 멈추지 않게 하기
- [x] [TASK-22] 자기 자신 수정 안전 모드 — auto_dev가 auto_dev를 망가뜨리지 않게 하기
- [x] [TASK-23] 완료 프로젝트 아카이브 — 모든 태스크 끝나면 결과물 자동 정리
- [x] [TASK-24] 프롬프트 효과 측정 — 어떤 AI 지시서가 더 잘 먹히는지 기록
- [x] [TASK-25] 루프 시작 전 GitHub 자동 백업 — AI 작업 전에 안전하게 커밋·푸시하기
---
TASK-26 — 루프 실행 이력 통계 대시보드
문제:
지금 runner.log가 317KB나 쌓여 있는데, "어제 몇 개 완료했는지, 평균 소요 시간은 얼마인지"를 알려면 로그를 직접 뒤져야 합니다.
목표:
runner.log를 파싱해서 일별 완료 태스크 수, 평균 소요 시간, 실패율을 계산
대시보드에 "이번 주 완료: 12개 / 평균 8분" 표시
TASK-27 — 태스크 의존성 자동 검증
문제:
TASK-15가 "TASK-14 선행 권장"이라고 적혀 있는데, TASK-14가 아직 [ ]인데도 TASK-15가 실행될 수 있습니다.
목제:
TASKS.md의 의존성: 필드를 파싱
현재 선택된 태스크의 의존 태스크가 [x]가 아니면 "선행 태스크 미완료" 경고 후 대기
대시보드에 의존성 그래프(화살표) 표시
TASK-28 — AI 응답 품질 필터 (가드레일)
문제:
Codex가 이상한 코드를 짜도 일단 파일에 써버립니다.
예: import os를 improt os로 오타내거나, 존재하지 않는 API를 호출하는 코드.
목표:
AI가 수정한 파일을 자동으로 문법 체크 (Python은 py_compile, JS는 기본 린트)
문법 오류가 있으면 "AI 응답 품질 불량"으로 기록하고 해당 수정을 폐기(rollback)
3회 연속 품질 불량이면 "AI 모델 교체 권고" 알림
TASK-29 — 대시보드 모바일 반응형
문제:
Streamlit 대시보드는 PC 화면 기준으로 넓게 펼쳐져 있습니다. 핸드폰으로 보면 버튼이 짤리거나 글씨가 작게 보입니다.
목표:
Streamlit st.columns 사용을 모바일 friendly로 조정
사이드바를 기본적으로 접어두기 (initial_sidebar_state="collapsed")
핵심 정보(현재 태스크, 단계, 시작/중단 버튼)를 상단에 고정
TASK-30 — 자동 문서화 동기화
문제:
코드를 고치면서 PRD.md, FUNCTION_SPECS.md, DATA_MODEL.md는 그대로 낡은 내용을 유지합니다.
코드와 문서가 어긋나면 나중에 "이게 맞는 건가?" 혼란이 생깁니다.
목표:
루프가 태스크를 완료할 때, 변경된 파일 목록을 FUNCTION_SPECS.md에 자동 반영
새 함수가 추가되면 FUNCTION_SPECS.md에 함수명, 입력, 출력을 AI가 자동으로 추출해서 기록
문서와 코드 차이가 10줄 이상 나면 "문서 동기화 필요" 알림
### TASK-31 — 루프 스케줄 실행 (예약 자동화)

**심각도:** P3  
**파일:** `dashboard/task_scheduler.py`, `dashboard/streamlit_app.py`  
**의존성:** TASK-15 (Streamlit 통합)

**문제:**  
지금은 대시보드에서 "시작" 버튼을 직접 눌러야 루프가 돕니다.  
밤에 자러 가기 전 버튼 누르고 아침에 확인하는 수동 방식입니다.

**수정 방향:**  
1. `task_scheduler.py` 신규 작성 — `schedule.json`에 시간/요일/프로젝트 경로 저장  
2. 대시보드 "⏰ 예약 설정" 탭 추가:  
   - 시간 선택 (`st.time_input`)  
   - 요일 체크박스 (월~일)  
   - 대상 프로젝트 경로  
   - 활성화/비활성화 토글  
3. 백그라운드 스레드가 1분마다 예약 시간 체크 → 시간 맞으면 루프 자동 시작  
4. Windows에서는 `taskschd.msc` 또는 시작 프로그램 폴더에 등록하면 부팅 시 자동 실행

**수락 기준:**
- [ ] 대시보드에서 시간과 요일을 설정할 수 있다
- [ ] 설정한 시간이 되면 루프가 자동으로 시작된다
- [ ] 예약 설정은 `dashboard/schedule.json`에 저장된다
- [ ] Streamlit을 재시작해도 예약 설정이 유지된다
- [ ] Windows 시작 프로그램에 등록하는 가이드가 README에 추가된다

**검증 방법:**
```powershell
# 1. 예약 설정: 1분 뒤로 설정
# 2. 대시보드에서 저장
# 3. 1분 후 루프가 자동 시작되는지 로그 확인
# 4. schedule.json 내용 확인
Get-Content D:\auto_dev\dashboard\schedule.json | ConvertFrom-Json

---

## Auto Dev Queue

> 방치형 자동개발 큐 — `scripts/auto_dev_queue.py`로 자동 관리됩니다.
> 수동으로 TASK를 추가하고 GitHub Actions를 실행하면 순차 처리됩니다.
>
> **사용법**: PENDING 섹션에 `- TASK-XXX: 작업 설명` 형식으로 추가

## PENDING
- TASK-TEST-001: Auto Dev Queue mock 실행 결과를 Streamlit 대시보드에 한 줄 상태 카드로 표시한다.
- TASK-002: GitHub Actions Summary에 다음 TASK 표시 추가- TASK-001: Streamlit 대시보드의 Auto Dev Queue 상태 카드 제목을 더 짧게 수정한다. 기능은 변경하지 않는다.


## RUNNING

## DONE
- TASK-001: README에 Auto Dev Queue 사용법 5줄 추가

## FAILED

## BLOCKED
