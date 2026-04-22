# TASKS.md — auto_dev

> 대상 프로젝트: D:/auto_dev
> 생성일: 2026-04-22
> 생성 기준: 코드 전체 정적 분석 (loop_runner.py / server.py / index.html / ai_project_scaffold_generator.py)

---

## Active

### Day 1 - 핵심 버그 수정 (P0 블로킹)

- [x] [TASK-01] scaffold_generator의 render_tasks()와 loop_runner의 TASKS.md 형식 불일치 수정
- [x] [TASK-02] loop_runner._install_deps()의 'omni-sync' 하드코딩 제거 및 범용 서브디렉토리 탐색으로 교체

### Day 2 - 루프 엔진 안정화 (P1)

- [x] [TASK-03] Claude Code 타임아웃 전략 개선 — 90s 고정값을 설정 가능하게 하고 타임아웃 시 재시도 횟수 제한 적용
- [x] [TASK-04] server.py SSE 스트림 빈 이벤트(0.3s 폴링) 제거 및 heartbeat 교체

### Day 3 - 대시보드 기능 보강 (P1)

- [x] [TASK-05] 대시보드에 TASKS.md 실시간 뷰어 추가 — /api/tasks 엔드포인트 + index.html 패널

### Day 4 - 테스트 커버리지 확대 (P2)

- [x] [TASK-06] scaffold_generator 단위 테스트 작성 — render_tasks, append_task_to_tasks_md, get_next_task_id
- [x] [TASK-07] loop_runner 테스트 확장 — _mark_task_done, _find_test_dir 케이스 추가

### Day 5 - 단기 개선 (P1)

- [x] [TASK-08] /api/tasks 취소선(~~text~~) 항목을 pending 대신 cancelled로 분류 — server.py 3줄 수정
- [x] [TASK-09] loop_runner self-test를 pytest로 수집 가능하게 분리 — tests/test_loop_runner.py 신규 작성

### Day 6 - 중기 기능 확장 (P2)

- [x] [TASK-10] 멀티 프로젝트 큐 관리 — dashboard/queue.json + 루프 완료 시 다음 프로젝트 자동 전환
- [x] [TASK-11] 하드닝 효과 측정 로그 — 하드닝 전/후 테스트 결과를 runner.log에 비교 기록

### Day 7 - 장기 아키텍처 (P3)

- [x] [TASK-12] scaffold → loop 원클릭 파이프라인 — scaffold 완료 시 queue.json 자동 등록
- [x] [TASK-13] TASKS.md 없는 프로젝트 자동 생성 모드 — 루프 진입 시 scaffold_generator 자동 실행 후 시작

## Waiting On

- (없음)

## Done

- [x] 루프 엔진 기본 동작 (TASK-32까지 omni-sync 프로젝트 완료, 42 tests passed)

---

## 태스크 상세

### TASK-01 — scaffold_generator TASKS.md 형식 불일치 수정

**심각도:** P0 BLOCK
**파일:** `ai_project_scaffold_generator.py` → `render_tasks()` (line 553)
**의존성:** 없음

**문제:**
`render_tasks()`는 `## TASK-01 — 제목` 형식의 상세 문서를 생성하지만,
`loop_runner._get_active_section()`은 `## Active` 섹션 안의 `- [ ] [TASK-XX]` 체크박스 라인만 파싱한다.
결과: scaffold로 생성된 모든 프로젝트에서 루프를 돌리면 "Active 섹션이 없습니다" 오류 발생.

**수정 방향:**
`write_tasks_document()`에서 상세 문서(현재 형식) 아래에 loop_runner 호환 `## Active` 섹션을 자동 추가한다.
```
## Active

### Auto Dev Queue
- [ ] [TASK-01] 태스크 제목
- [ ] [TASK-02] 태스크 제목
...
```

**수락 기준:**
- [ ] scaffold 실행 후 생성된 TASKS.md에 `## Active` 섹션이 포함된다
- [ ] 각 태스크가 `- [ ] [TASK-XX] 제목` 형식으로 Active에 나열된다
- [ ] loop_runner가 해당 TASKS.md를 읽어 첫 태스크를 올바르게 선택한다
- [ ] 기존 TASKS.md가 있을 때 `append_task_to_tasks_md` 동작은 변경되지 않는다

**검증:**
```python
python -m pytest dashboard/loop_runner.py --doctest-modules  # 기존 self-test 통과
# 또는 직접 실행:
python dashboard/loop_runner.py --self-test
```

---

### TASK-02 — _install_deps() 하드코딩 제거

**심각도:** P0 BLOCK
**파일:** `dashboard/loop_runner.py` → `_install_deps()` (line 285)
**의존성:** 없음

**문제:**
```python
for req in [proj / "requirements.txt", proj / "omni-sync" / "requirements.txt"]:
```
`omni-sync`가 하드코딩돼 있어 다른 프로젝트에서는 서브디렉토리 의존성이 설치되지 않는다.

**수정 방향:**
프로젝트 루트와 모든 1단계 서브디렉토리를 순회하며 `requirements.txt`를 탐색한다.
```python
candidates = [proj / "requirements.txt"]
candidates += [d / "requirements.txt" for d in sorted(proj.iterdir()) if d.is_dir()]
for req in candidates:
    if req.exists(): ...
```

**수락 기준:**
- [ ] `omni-sync` 문자열이 코드에서 제거된다
- [ ] 루트 + 모든 1단계 서브디렉토리의 requirements.txt를 자동 탐색한다
- [ ] requirements.txt가 없는 프로젝트에서도 오류 없이 실행된다
- [ ] 기존 self-test 3종이 모두 통과한다

**검증:**
```
python dashboard/loop_runner.py --self-test
```

---

### TASK-03 — Claude Code 타임아웃 전략 개선

**심각도:** P1
**파일:** `dashboard/loop_runner.py` → `_run_claude()`, `_run()` (line 181, 302)
**의존성:** TASK-02

**문제:**
- `CLAUDE_TIMEOUT_SEC = 90` 고정값. 복잡한 하드닝 작업은 90s가 부족해 반복 타임아웃 발생.
- 타임아웃 시 `code=1`을 반환하고 재시도 1회 후 "⚠ 하드닝 실패. 다음 단계로 진행"으로 계속 진행 — 불완전한 하드닝 상태로 테스트를 돌림.

**수정 방향:**
- `CLAUDE_TIMEOUT_SEC`을 환경변수(`CLAUDE_TIMEOUT`)로 오버라이드 가능하게 수정
- 기본값 180초로 상향
- 타임아웃 발생 시 태스크를 `error` 상태로 분류하여 루프 일시 중지 (무한 실패 방지)

**수락 기준:**
- [ ] `CLAUDE_TIMEOUT` 환경변수로 타임아웃 값을 설정할 수 있다
- [ ] 기본값이 180초로 변경된다
- [ ] 타임아웃이 2회 연속 발생하면 루프가 `error` 상태로 멈추고 수동 확인을 요청한다
- [ ] 정상 완료 케이스에서 기존 self-test가 그대로 통과한다

**검증:**
```
python dashboard/loop_runner.py --self-test
```

---

### TASK-04 — SSE 스트림 빈 이벤트 제거

**심각도:** P1
**파일:** `dashboard/server.py` → `stream()` (line 113)
**의존성:** 없음

**문제:**
```python
def event_generator():
    while True:
        if not runner.log_queue.empty():
            msg = runner.log_queue.get()
            yield f"data: {msg}\n\n"
        else:
            yield f"data: \n\n"   # ← 매 0.3초마다 빈 이벤트 전송
        time.sleep(0.3)
```
브라우저가 초당 3회 onmessage 핸들러를 호출하고, 프론트의 `if (e.data)` 가드로 걸러지긴 하나 CPU/네트워크 낭비다.

**수정 방향:**
메시지가 없을 때는 아무것도 yield하지 않고 대기한다. SSE 연결 유지를 위한 heartbeat는 `:` 코멘트 이벤트를 30초 간격으로 전송한다.
```python
yield ": heartbeat\n\n"  # 30초 간격, 연결 유지용
```

**수락 기준:**
- [ ] 빈 `data: \n\n` 이벤트가 전송되지 않는다
- [ ] 루프 실행 중 로그가 지연 없이 프론트에 도달한다
- [ ] 서버 재시작 후 SSE 연결이 자동으로 재연결된다
- [ ] `/api/loop/stream` 엔드포인트가 Flask 테스트 클라이언트로 응답을 반환한다

**검증:**
브라우저 DevTools → Network → EventStream 탭에서 빈 이벤트가 없음을 확인.

---

### TASK-05 — 대시보드 TASKS.md 실시간 뷰어 추가

**심각도:** P1
**파일:** `dashboard/server.py`, `dashboard/templates/index.html`
**의존성:** TASK-01

**문제:**
현재 대시보드에서 어떤 태스크가 남아있고, 어떤 것이 완료됐는지 볼 수 없다.
루프 상태(running/idle)와 현재 태스크명만 표시되며 전체 진행률을 알 수 없다.

**수정 방향:**
- `GET /api/tasks` 엔드포인트 추가: 현재 `project_dir`의 TASKS.md를 파싱해 완료/미완료 태스크 목록을 JSON으로 반환
- `index.html`에 태스크 목록 패널 추가: 완료된 태스크는 취소선, 현재 실행 중인 태스크는 하이라이트

**수락 기준:**
- [ ] `GET /api/tasks` 가 `{"done": [...], "pending": [...], "total": N}` 형식을 반환한다
- [ ] TASKS.md가 없을 때 `{"done": [], "pending": [], "total": 0}` 을 반환한다 (오류 아님)
- [ ] 대시보드에 태스크 목록 패널이 표시된다
- [ ] 현재 실행 중인 태스크가 목록에서 시각적으로 구분된다
- [ ] 진행률(N/M 완료)이 표시된다

**검증:**
`python dashboard/server.py` 실행 후 `http://localhost:5000` 접속하여 태스크 패널 확인.

---

### TASK-06 — scaffold_generator 단위 테스트 작성

**심각도:** P2
**파일:** 신규 `dashboard/tests/test_scaffold_generator.py` (또는 프로젝트 루트 `tests/`)
**의존성:** TASK-01

**문제:**
2157줄짜리 핵심 파일 `ai_project_scaffold_generator.py`에 자동화 테스트가 전혀 없다.
`render_tasks`, `append_task_to_tasks_md`, `get_next_task_id`는 loop_runner와 직접 연동되는 함수로 회귀 위험이 높다.

**수락 기준:**
- [ ] `render_tasks()` 출력에 `## Active` 섹션과 `- [ ] [TASK-XX]` 라인이 포함되는지 검증
- [ ] `append_task_to_tasks_md()`: Active 섹션 없을 때 생성, 있을 때 추가 — 두 케이스 모두 테스트
- [ ] `get_next_task_id()`: 기존 TASK-05까지 있으면 TASK-06을 반환하는지 검증
- [ ] `pytest` 실행 시 모두 통과

**검증:**
```
python -m pytest tests/test_scaffold_generator.py -v
```

---

### TASK-07 — loop_runner 테스트 확장

**심각도:** P2
**파일:** `dashboard/loop_runner.py` → `run_self_tests()` (line 407)
**의존성:** TASK-02

**문제:**
현재 `run_self_tests()`는 `_get_next_task_selection` 3개 케이스만 검증한다.
`_mark_task_done`, `_find_test_dir`은 테스트가 없어 회귀 시 즉각 발견이 어렵다.

**수락 기준:**
- [ ] `_mark_task_done()`: 체크박스 `[ ]` → `[x]` 변환 및 TASKS.md 저장 검증
- [ ] `_find_test_dir()`: 루트에 tests/ 있을 때 vs 서브디렉토리에만 있을 때 두 케이스 검증
- [ ] `_install_deps()`: requirements.txt 없을 때 오류 없이 통과 검증 (TASK-02 이후)
- [ ] `python dashboard/loop_runner.py --self-test` 실행 시 모두 통과

**검증:**
```
python dashboard/loop_runner.py --self-test
```
