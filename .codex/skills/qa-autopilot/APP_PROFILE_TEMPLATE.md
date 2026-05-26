# QA Autopilot App Profile Template

Use this template to adapt `qa-autopilot` to a new app without changing the core protocol.

## App identity
- App name: `<app-name>`
- Repo root: `<absolute-path>`
- Primary stack: `<docker-compose | local scripts | cloud preview>`

## Runtime config
- `WEB_BASE_URL`: `<default-url>`
- `API_BASE_URL`: `<default-url>`
- `ADMIN_PATH`: `<path or blank>`
- `HEALTH_PATH`: `<path>`
- `SMOKE_CMD`: `<command>`

## Boot / migration commands
```powershell
# Example only; replace with app-specific commands
docker compose up -d
<migration command>
```

## Required health checks
- Web health expectation: `<status and endpoint>`
- API health expectation: `<status and endpoint>`
- Max retry window: `90s` (change only when justified)

## Critical browser flows
List only high-value, user-visible flows.
1. `<path + expected visible state>`
2. `<path + expected interaction>`
3. `<path + expected mutation or response>`

## Policy / domain guardrails
- Non-negotiable behavior constraints:
  - `<guardrail 1>`
  - `<guardrail 2>`
- Expected rejection behaviors:
  - `<error code + when expected>`

## Failure artifact requirements
For every failure capture:
- URL and step name
- Screenshot (or trace)
- Console error lines
- Network request method/path/status and error snippet

## Fix boundaries
- In-scope areas: `<paths/modules>`
- Out-of-scope areas requiring escalation: `<infra/external dependencies>`
- Max fix loops: `2`

## Report contract
Always return:
1. `Status`: pass/fail
2. `Checks run`
3. `Failures` with severity tags (`sev1_blocking`, `sev2_major`, `sev3_minor`, `flaky`)
4. `Fixes applied`
5. `Re-test result`
6. `Next action`
