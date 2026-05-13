# auto_dev

자동 개발 루프 — TASKS.md에 작업을 추가하면 AI가 순차적으로 처리합니다.

## Auto Dev Queue 사용법

1. `TASKS.md`의 `## PENDING` 섹션에 `- TASK-XXX: 작업 설명` 형식으로 작업을 추가한다.
2. GitHub Actions → **Auto Dev Queue** 워크플로우를 수동으로 실행한다.
3. `scripts/auto_dev_queue.py`가 PENDING 목록을 순서대로 처리한다.
4. 처리 결과는 PENDING → RUNNING → DONE/FAILED 순으로 상태가 변경된다.
5. 실패한 작업은 `## FAILED` 섹션에 기록되며 재실행 가능하다.

## 프롬프트 생성 (auto_dev_prompt_loop)

```bash
python scripts/auto_dev_prompt_loop.py            # PENDING 첫 TASK → auto_prompt_YYYYMMDD_HHMMSS.md 생성
python scripts/auto_dev_prompt_loop.py --copy     # 생성 후 Windows 클립보드에 복사
python scripts/auto_dev_prompt_loop.py --task-id TASK-003  # 특정 TASK 지정
python scripts/auto_dev_prompt_loop.py --repo D:\other_repo  # 다른 저장소 대상
```

## Codex ↔ Claude 파일 기반 왕복 루프

사람이 결과 파일만 저장하면 다음 AI에게 넘길 프롬프트를 자동 생성합니다.

1. Claude 결과를 `D:\walk\claude_result.md` 로 저장
2. 아래 명령 실행
   ```bash
   python scripts/auto_dev_handoff_loop.py --repo D:\walk --from claude --input D:\walk\claude_result.md --copy
   ```
3. 복사된 프롬프트를 Codex에 붙여넣기
4. Codex 결과를 `D:\walk\codex_result.md` 로 저장
5. 아래 명령 실행
   ```bash
   python scripts/auto_dev_handoff_loop.py --repo D:\walk --from codex --input D:\walk\codex_result.md --copy
   ```
6. 복사된 프롬프트를 Claude에 붙여넣기

생성 파일: `codex_handoff_YYYYMMDD_HHMMSS.md` 또는 `claude_handoff_YYYYMMDD_HHMMSS.md` (--repo 경로 안에 저장)
