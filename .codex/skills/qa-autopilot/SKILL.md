---
name: qa-autopilot
description: "Run a reusable Autonoma-style QA loop after frontend changes: preflight environment checks, test execution, browser verification, failure triage, bounded fix/retest cycles, and a concise regression report."
---

# QA Autopilot

Use this skill when the user asks for automated QA, regression checks, smoke testing, or "test like Autonoma" after UI/frontend changes.
The skill is designed to be reusable across apps via an app profile.

## Reuse model
Operate in two layers:
1. Core QA protocol (this file): preflight, execute, triage, fix/retest, report.
2. App profile: app-specific routes, commands, and guardrails.

For new apps, copy [APP_PROFILE_TEMPLATE.md](/C:/Users/steph/Documents/civic-fact-audit/.codex/skills/qa-autopilot/APP_PROFILE_TEMPLATE.md) and fill it before first QA run.

## Runtime config
Use environment overrides when available (cross-app defaults):
- `WEB_BASE_URL` (default: `http://localhost:3001`)
- `API_BASE_URL` (default: `http://localhost:8000`)
- `ADMIN_PATH` (default: `/admin/`)
- `SMOKE_CMD` (default: `npm run test:smoke`)
- `HEALTH_PATH` (default: `/health`)

Derived defaults:
- Public app: `${WEB_BASE_URL}/`
- Admin Workbench: `${WEB_BASE_URL}${ADMIN_PATH}`
- API health: `${API_BASE_URL}${HEALTH_PATH}`
- Smoke suite: `${SMOKE_CMD}`

## Core execution loop
1. Run preflight checks and confirm local stack is healthy.
2. Run smoke tests first.
3. Run browser QA pass on affected flows.
4. Inspect errors (console/network/UI regressions).
5. If failures are deterministic and in-scope, patch and re-run (bounded loop).
6. Return a concise pass/fail report with changed files and residual risk.

## Preflight checks (required)
From repo root (adjust for app profile):

```powershell
docker compose ps
docker compose up -d db api web
docker compose run --rm api alembic upgrade head
```

Health probes with retries (max 90s per service):
- API: `GET ${API_BASE_URL}${HEALTH_PATH}` returns `200`.
- Web: `GET ${WEB_BASE_URL}/` returns `200` or `304`.

If health checks fail after retries, stop and report as `blocked_environment` with failing endpoint and last status/error.

## Commands
Default commands for this app profile (`civic-fact-audit`):

```powershell
docker compose up -d db api web
docker compose run --rm api alembic upgrade head
${SMOKE_CMD}
```

If services are already up, skip restart and run only checks.

Checks-only mode (no code changes):
```powershell
${SMOKE_CMD}
```

Fix mode:
- Run full loop, patch deterministic in-scope regressions, then re-run all touched checks.

## Browser verification checklist
Validate app-profile critical paths in browser checks.
For civic-fact-audit, always validate:
- `/` loads and renders candidate comparison shell.
- `/admin/` loads and auth form is visible.
- Workbench panel renders claim list and detail sections.
- Source attach form renders expected fields and submit button.
- No blocking console errors on load or key interactions.

For changes touching evidence/review workflow:
- Verify Workbench source attach UI still functions.
- Verify attached-sources list renders.
- If remove-source UI is present, verify remove action result and error handling copy.

Pass criteria:
- No blocking console errors on target flows.
- No failed network requests on core flow actions unless explicitly expected by policy guardrails.
- Smoke suite exits with code `0`.

## Failure handling rules
- On selector drift: update selector in tests to stable semantics (id/name/text role) and avoid brittle nth-child selectors.
- On console/network failures: include URL, failing request, status code, and error text in the report.
- On policy-related expected rejections (e.g., partisan verification source), mark as `expected_guardrail_behavior` not regression.
- Do not weaken source-admission policy to make tests pass.
- Save failure artifacts: screenshot (or trace), console error lines, and network failure details for each failing step.
- If flake is suspected, run one controlled retry. If behavior diverges, label `flaky` with reproduction notes and do not claim fixed.
- Prioritize stable selectors (`data-testid`, role/name, id) before textual fallback selectors.

## Stop conditions
- Maximum fix loop: 2 iterations per run.
- Stop immediately and escalate when:
  - failure depends on external outage/secrets/third-party infra,
  - required scope exceeds the requested change area,
  - behavior is non-deterministic after retry.

## Reporting format
Return:
1. `Status`: pass/fail
2. `Checks run`: command list + browser checks
3. `Failures`: exact failing step(s) with evidence
4. `Fixes applied`: file list and rationale
5. `Re-test result`: what now passes/fails
6. `Next action`: smallest safe follow-up

## Severity labels
Use consistent severity tags in failures:
- `sev1_blocking`: prevents core flow or app load.
- `sev2_major`: major feature broken; workaround exists.
- `sev3_minor`: non-blocking defect or polish regression.
- `flaky`: inconsistent reproduction after controlled retry.

## Guardrails
- Keep behavior nonpartisan and citation-first.
- Keep business logic in `backend/app/services/`.
- Add/update tests for behavior changes.
- Do not silently ignore flaky failures; label as flaky with reproduction notes.
- Keep source-admission guardrails intact; never bypass policy checks to force green QA.
