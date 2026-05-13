# Severity Matrix

Use this matrix to rank findings in non-developer terms.

## Severity

### CRITICAL

> 사용자 관점: 지금 이 상태로 배포하거나 공유하면 금전 피해, 데이터 유출, 또는 서비스 중단이 발생할 수 있음

The project can fail for users, leak secrets, lose data, or block deployment.

Examples:

- API keys, access tokens, or passwords are hardcoded or printed.
- The main app cannot start, login fails for everyone, or production deployment is broken.

### HIGH

> 사용자 관점: 주요 기능이 작동하지 않거나 잘못된 결과를 내서 사용자가 신뢰를 잃을 수 있음

Core user workflows can break or produce wrong results.

Examples:

- A payment, booking, export, task creation, or analysis result can fail silently.
- Required environment variables, file paths, or dependencies are missing in normal setup.

### MEDIUM

> 사용자 관점: 제품은 돌아가지만 사용자가 혼란스럽거나 불편을 느낄 수 있음

The product works, but users can get confused, blocked, or receive weak output.

Examples:

- Error messages do not explain what to do next.
- A form allows invalid input and only fails later.

### LOW

> 사용자 관점: 당장 문제는 없지만 방치하면 나중에 고치기 어려워질 수 있음

Quality, polish, or maintainability issue with limited immediate user impact.

Examples:

- Minor layout spacing issue on one screen.
- Duplicate helper code that is not yet causing bugs.

## Difficulty

### Easy

Usually 5-15 minutes. One small file or one small behavior change. Low test burden.

### Medium

Usually 15-45 minutes. A few files, a small test update, or a UI flow adjustment.

### Hard

Usually 45 minutes or more. Cross-module behavior, DB/API contract, auth, payments, deployment, or broad regression risk.

## Priority Matrix

| Severity | Easy | Medium | Hard |
|---|---|---|---|
| CRITICAL | P0 | P0 | P0, but split into a safe first fix |
| HIGH | P0 | P1 | P1, reduce scope first |
| MEDIUM | P1 | P2 | P3 unless blocking a near-term release |
| LOW | P2 | P3 | P3 or backlog |

## Tie Breakers

- Prefer user-visible breakage over internal cleanup.
- Prefer fixes that unblock running, testing, or deployment.
- Prefer one narrow change over a broad refactor.
- Defer improvements that require unclear product decisions.
