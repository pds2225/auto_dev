# AGENTS.md — AI 자동개발 작업 규칙

> 이 파일은 GitHub Actions 및 AI 에이전트가 이 저장소에서 작업할 때 따라야 하는 규칙을 정의합니다.
> 사람이 직접 설정하거나 변경해야 하는 항목은 별도로 명시합니다.

---

## 1. 기본 원칙

- **최소 변경 원칙**: 목표 달성에 필요한 최소한의 변경만 수행한다.
- **기존 기능 보호**: 작동 중인 기능을 절대 깨뜨리지 않는다.
- **안전 우선**: 검증되지 않은 변경은 실제 파일에 적용하지 않는다.
- **투명한 로그**: 수행한 작업, 실패 이유, 다음 행동을 로그에 명시한다.
- **Secret 보호**: API Key, Token, 비밀번호 값은 절대 출력하지 않는다.

---

## 2. 절대 수정 금지 파일

다음 파일은 어떤 경우에도 AI가 수정할 수 없습니다.

| 파일/경로 | 이유 |
|---|---|
| `.github/workflows/*.yml` | 워크플로우 파일 — 사람만 수정 |
| `scripts/run_auto_dev_once.py` | 실행 스크립트 자기 자신 보호 |
| `scripts/auto_dev_queue.py` | 큐 관리 스크립트 자기 자신 보호 |
| `.env`, `.env.*` | 환경변수/Secret 파일 |
| `AGENTS.md` | 이 규칙 파일 자체 |
| `RULES.md` | 규칙 파일 |

---

## 3. 수정 허용 파일 범위

| 허용 확장자 | 비고 |
|---|---|
| `.py` | py_compile 검증 통과 시만 적용 |
| `.md` | Markdown 파일 |
| `.json` | JSON 구조 유효할 때만 |
| `.yaml`, `.yml` | 워크플로우 외 파일만 |
| `.txt`, `.html`, `.css`, `.js` | 기본 허용 |

---

## 4. 변경 방식 우선순위

1. **patch 방식 (최우선)**: 특정 텍스트를 찾아 최소한으로 교체
   ```json
   {"mode": "patch", "patches": [{"search": "구 텍스트", "replace": "새 텍스트"}]}
   ```

2. **full 방식 (구조 변경 시만)**: 파일 전체를 새로 작성
   - Python 파일은 `py_compile` 통과 필수
   - 파일이 잘리거나 incomplete하면 적용 금지

---

## 5. TASK 처리 규칙

- 1회 실행 시 PENDING TASK 1개만 처리
- 동일 TASK 최대 2회까지만 재시도 (`MAX_RETRIES = 2`)
- BLOCKED TASK는 자동 재시도하지 않음
- TASK 실패가 전체 큐를 멈추게 해선 안 됨

### 실패 유형별 처리

| 실패 유형 | 처리 |
|---|---|
| Secret 누락 | → BLOCKED (사람이 설정 필요) |
| GitHub 권한 부족 | → BLOCKED (사람이 설정 필요) |
| AI 응답 오류 | → FAILED_RETRY (재시도 가능) |
| Python SyntaxError | → FAILED + FIX TASK 자동 생성 |
| 테스트 실패 | → FAILED + FIX TASK 자동 생성 |
| 변경사항 없음 | → DONE (스킵) |
| PR 중복 | → 기존 PR 링크 출력 후 DONE |

---

## 6. Git 규칙

- `main` 브랜치에 직접 push 금지
- 항상 `auto-dev/YYYYMMDD-HHMMSS` 또는 `auto-dev-queue/YYYYMMDD-HHMMSS` 브랜치 사용
- 자동 merge 금지 — PR 생성까지만 수행
- 커밋 메시지 형식: `auto-dev: <목표 요약 72자 이내>`

---

## 7. 사람이 직접 설정해야 하는 항목

| 항목 | 위치 | 필수 여부 |
|---|---|---|
| `OPENAI_API_KEY` | GitHub Secrets | 둘 중 하나 필수 |
| `ANTHROPIC_API_KEY` | GitHub Secrets | 둘 중 하나 필수 |
| `AUTO_DEV_PAT` | GitHub Secrets | 권장 (PR 생성용 PAT) |
| Actions PR 권한 | Settings → Actions → General | AUTO_DEV_PAT 없을 때 필수 |

---

## 8. 검증 기준

모든 Python 파일 변경 전:
```bash
python -m py_compile <파일경로>
```

모든 YAML 파일:
```bash
python -c "import yaml; yaml.safe_load(open('<파일경로>'))"
```

Secret 하드코딩 금지:
```bash
# 아래 패턴이 코드에 없어야 함
grep -rn "sk-" scripts/
grep -rn "ghp_" scripts/
```
