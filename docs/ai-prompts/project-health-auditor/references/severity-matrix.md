# Severity Matrix

Use this matrix to rank findings in non-developer terms.

## Severity

### CRITICAL

The project can fail for users, leak secrets, lose data, or block deployment.

Examples:

- API keys, access tokens, or passwords are hardcoded or printed.
- The main app cannot start, login fails for everyone, or production deployment is broken.

### HIGH

Core user workflows can break or produce wrong results.

Examples:

- A payment, booking, export, task creation, or analysis result can fail silently.
- Required environment variables, file paths, or dependencies are missing in normal setup.

### MEDIUM

The product works, but users can get confused, blocked, or receive weak output.

Examples:

- Error messages do not explain what to do next.
- A form allows invalid input and only fails later.

### LOW

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
