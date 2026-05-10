# auto_dev

자동 개발 루프 — TASKS.md에 작업을 추가하면 AI가 순차적으로 처리합니다.

## Auto Dev Queue 사용법

1. `TASKS.md`의 `## PENDING` 섹션에 `- TASK-XXX: 작업 설명` 형식으로 작업을 추가한다.
2. GitHub Actions → **Auto Dev Queue** 워크플로우를 수동으로 실행한다.
3. `scripts/auto_dev_queue.py`가 PENDING 목록을 순서대로 처리한다.
4. 처리 결과는 PENDING → RUNNING → DONE/FAILED 순으로 상태가 변경된다.
5. 실패한 작업은 `## FAILED` 섹션에 기록되며 재실행 가능하다.
