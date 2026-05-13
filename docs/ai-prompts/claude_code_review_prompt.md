# Claude Code 리뷰 요청 프롬프트

아래 프롬프트 전문을 Claude Code에 붙여넣어 `dashboard/streamlit_app.py` 변경에 대한 리뷰를 요청하세요.

---

## 프롬프트 본문 (복사해서 사용)

```text
당신은 시니어 Python / Streamlit 엔지니어입니다.
아래 변경사항에 대해 코드 리뷰를 수행해주세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 변경 목적
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

기존에는 로컬 자동개발 루프(Flask 기반 server.py)와 GitHub Actions 트리거(Streamlit 기반 streamlit_app.py)가 별개 화면이었습니다.
이번 변경은 streamlit_app.py 한 화면에서 두 기능을 모두 사용할 수 있도록 통합한 것입니다.

- 기존: "🚀 GitHub Actions 실행" 버튼 (원격 Actions 트리거)
- 신규: "▶️ 로컬 루프 시작 / ⏹️ 중단" 버튼 (내 PC에서 직접 loop_runner 제어)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 변경 파일
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- dashboard/streamlit_app.py  (단일 파일만 변경, 최소 변경 원칙 준수)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏗️ 기존 아키텍처
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. dashboard/server.py (Flask)
   - HTML 템플릿(index.html) 렌더링 + JavaScript SSE 스트리밍
   - loop_runner.py의 전역 runner 인스턴스를 import
   - /api/loop/toggle, /api/loop/state, /api/loop/stream, /api/queue 등 제공
   - loop_state.json / queue.json으로 상태/큐 영속화

2. dashboard/streamlit_app.py (Streamlit)
   - 모바일 대시보드용
   - GitHub API로 workflow_dispatch 트리거
   - 실행 현황, PR 목록, TASKS.md 큐 요약 표시

3. dashboard/loop_runner.py
   - LoopRunner 클래스 (싱글톤 패턴, threading.Lock)
   - log_queue (Queue)로 실시간 로그 수집
   - start(project_dir) → daemon Thread 생성 → _run() 실행
   - stop() → running=False + _stop_event.set()

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 이번 변경의 핵심 설계
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 직접 import 제어
   streamlit_app.py 상단에서 loop_runner.runner를 직접 import.
   Flask API를 거치지 않고 runner.start() / runner.stop()을 직접 호출.

2. 상태 파일 공유
   server.py와 동일한 dashboard/loop_state.json, dashboard/queue.json을 읽고 씀.
   Flask ↔ Streamlit 간 상태 연속성 유지.

3. Streamlit 세션 상태에 로그 누적
   st.session_state["local_logs"]에 runner.log_queue를 drain하여 저장.
   최대 500줄만 유지 (메모리 보호).

4. 실시간 갱신
   파일 하단에 if runner.running: time.sleep(2); st.rerun() 추가.
   실행 중일 때 2초마다 페이지 전체가 rerun되며 로그/상태 갱신.

5. UI 구조
   상단: 🖥️ 로컬 자동개발 루프 (시작/중단, 상태 뱃지, 실시간 로그, 프로젝트 큐)
   하단: 🎯 GitHub Actions 개발 목표 (기존 기능 그대로)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 이미 수행한 검증
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- python -m py_compile dashboard/streamlit_app.py → 통과
- AGENTS.md의 "최소 변경 원칙" 준수 (단일 파일 수정)
- AGENTS.md의 "기존 기능 보호" 준수 (GitHub Actions 영역 무 touched)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 리뷰 포인트 (반드시 확인해주세요)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Thread Safety
   - LoopRunner는 클래스 변수 _active_runner와 _runner_lock을 사용하는데,
     Streamlit의 st.rerun()이 2초마다 전체 스크립트를 재실행하면서
     _load_local_state() 난이 was_running일 때 runner.start()를 다시 호출합니다.
   - LoopRunner.start() 난이 이미 실행 중이면 return하는 로직이 있지만,
     혹시 race condition이나 중복 스레드 생성 위험이 있는지 검토해주세요.

2. Streamlit Rerun 성능 / UX
   - time.sleep(2) + st.rerun()이 실행 중일 때 무한히 반복됩니다.
   - 이것이 Streamlit 서버나 브라우저에 과부하를 주지 않는지,
     더 나은 대안(예: st.empty() 단일 요소 업데이트, 콜백, 또는 st.fragment)이 있는지 검토해주세요.

3. 상태 복구 로직
   - _load_local_state()에서 was_running이면 runner.start(project_dir)를 호출하는데,
     이때 프로젝트가 이미 루프를 완료했거나(done) 에러로 멈춘 상태였다면
     의도치 않게 즉시 재시작될 수 있습니다.
   - "done" 상태였을 때의 복구 동작이 적절한지 검토해주세요.

4. 예외 처리 및 사용자 피드백
   - runner.start() 자체는 daemon Thread이므로 예외가 메인 스레드로 전파되지 않습니다.
   - 만약 runner._run() 난이 날 것을 던지면 사용자는 Streamlit UI에서 인지할 수 없습니다.
   - 이 부분을 개선할 수 있는 방법이 있는지 검토해주세요.

5. Queue/State 파일 경로
   - STATE_FILE = Path(__file__).parent / "loop_state.json"
   - QUEUE_FILE = Path(__file__).parent / "queue.json"
   - server.py도 동일 경로를 사용하는지 확인 필요.
   - 만약 server.py와 Streamlit이 동시에 실행 중이라면 파일 쓰기 충돌 가능성이 있는지 검토해주세요.

6. 최소 변경 원칙 재확인
   - 기존 GitHub Actions 기능을 해치지 않았는지,
   - 불필요한 코드 중복이 없는지,
   - 혹시 server.py의 기능을 재구현하는 대신 import/위임할 수 있는 부분이 더 있는지 검토해주세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 리뷰 출력 형식
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

각 항목별로 아래 형식으로 작성해주세요:

- 🔴 Critical: 즉시 수정이 필요한 버그/위험
- 🟡 Warning: 개선하면 좋은 설계/성능 이슈
- 🟢 Suggestion: 참고하면 좋은 best practice
- ✅ OK: 잘 작성된 부분

각 항목에 대해:
  1. 문제/장점 요약
  2. 구체적인 코드 위치 (라인 번호 또는 함수명)
  3. 개선 제안 코드 (가능한 경우)
```

---

## 사용 방법

1. 터미널에서 아래 명령으로 diff를 확인합니다:
   ```powershell
   cd D:\auto_dev
   git diff dashboard/streamlit_app.py
   ```

2. 위 프롬프트 본문을 Claude Code 창에 붙여넣습니다.

3. diff 내용도 함께 첨부하면 더 정확한 라인 번호 기반 리뷰를 받을 수 있습니다.
