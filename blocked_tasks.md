# 사람이 먼저 확인해야 하는 할 일

> API 키나 GitHub 권한 같은 외부 설정 문제로 멈춘 할 일 기록입니다. `scripts/auto_dev_queue.py`가 자동으로 기록합니다.
>
> **사람 확인 필요(BLOCKED) 원인 유형:**
> - Secret(API Key) 미등록
> - GitHub Actions PR 생성 권한 부족
> - 최대 재시도 횟수 초과
> - 필수 파일 없음
>
> **처리 방법:**
> 1. 원인을 해결 (Secret 등록, 권한 설정 등)
> 2. TASKS.md의 `PENDING` 섹션에 해당 할 일을 다시 추가
> 3. `auto_dev_state.json`에서 `retry_count` 초기화 후 재실행

<!-- BLOCKED 기록은 아래에 자동 추가됩니다 -->

## NO_TASK: API Key 없음
- 차단 시각: 2026-05-09 07:23:25 UTC
- 사유: OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 등록 필요

