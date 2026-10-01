# Changelog

All notable changes to civic-fact-audit are documented here.

---

## [Unreleased] — 2026-06-12

### AI Review Draft Pipeline — 3-Tier Model Stack

The `review_draft_service.py` has been fully rebuilt around a production-grade 3-tier
model architecture with deterministic safety guardrails and a circuit breaker.

#### Model Stack
- **Primary (default):** `gpt-4o-mini` — structured JSON output via `response_format: json_schema` with `strict: True`. Cost: ~$0.54/1k claims.
- **Escalation (second pass):** `claude-sonnet-4-6` — triggered when primary marks `green_lane_ready=True` or returns zero warnings on a non-supported verdict. Uses Anthropic tool use with `tool_choice: {type: "tool"}` for guaranteed schema compliance.
- **Degraded fallback:** `claude-sonnet-4-6` alone — active when `CIVIC_AI_DEGRADED_MODE=true`. Green-lane is hard-disabled in this mode.

Gemini models were evaluated and dropped from production due to structural schema violations (`evidence_sufficiency` returning values outside 0–1 range) and green-lane false positives on false claims.

#### `_enforce_green_lane` — Server-Side Safety Guardrail (`review_draft_service.py`)
Added a deterministic post-processing step that overrides any model-reported `green_lane_ready=True` when the output contains an unsafe signal:
- `suggested_verdict` is not `supported`
- `warnings` array is non-empty
- `missing_evidence` array is non-empty
- Any subclaim `judgment` is not `supported`

This prevents a model from marking a claim green-lane-ready despite its own warnings or non-supported verdict, regardless of how the model interprets the prompt.

#### `_should_escalate` — Escalation Guard
Triggers a Sonnet second-pass when the primary model returns a response that passes basic validation but exhibits low-confidence patterns (zero warnings on a suspicious verdict, green lane on a borderline claim, etc.).

#### `_merge_escalation` — Conservative Merge
When both primary and escalation models produce outputs, the merge logic takes the more conservative verdict, preserves all warnings from both passes, and uses the lower confidence score.

#### System Prompt — Confidence Calibration and Warning Discipline
Revised system prompt applied to both primary and escalation models:

- **Confidence calibration:** `suggested_confidence` is now defined as confidence in the editorial call, not certainty that a claim is factually wrong. Capped at 0.84 for `unsupported` and `mixed` verdicts (rejecting a claim always requires humility about evidence completeness). Also capped at 0.84 for projections, future-tense statistics, contested methodology, conditional figures, legal interpretation, and statistical framing choices.
- **Warning discipline:** For `supported` claims, warnings are only raised when a source actively contradicts or materially qualifies the claim — not to demonstrate thoroughness. Structured warning codes required: conditional stat presented as certain, outdated figure, misleading terminology, overbroad scope, missing causal context, methodological caveat, projection sensitivity, omitted policy remedy, source contradicting the claim.
- **Green-lane clarity:** `green_lane_ready=True` requires all of: verdict is supported, warnings empty, missing_evidence empty, all subclaim judgments supported.

#### Circuit Breaker — `CIVIC_AI_DEGRADED_MODE`
New environment variable and `Settings` field (`civic_ai_degraded_mode: bool = False`).

When `CIVIC_AI_DEGRADED_MODE=true`:
- Primary model (OpenAI) is bypassed entirely
- All requests go directly to `claude-sonnet-4-6`
- `green_lane_ready` is hard-set to `False` for every response (auto-publishing disabled)

Intended for use after a failed regression health check, before the primary model issue is resolved. Set in `.env`, then restart the API server.

---

### AI Health Check & Regression Runner

#### `backend/app/scripts/health_check.py` (new)
Weekly regression test runner. Executes 4 diagnostic scenarios chosen to maximize failure-mode coverage:

| Scenario | Type | Difficulty | Purpose |
|---|---|---|---|
| `voting_record_false` | false | easy | Worst-case gpt-4o-mini regression scenario |
| `tcja_83pct` | misleading | hard | Projection/methodology complexity trap |
| `inflation_june2022` | truthful | easy | Should never regress; baseline anchor |
| `medicare_bankrupt` | misleading | medium | "Bankruptcy" framing trap |

Pass/fail scored against per-scenario criteria (verdict, confidence, warning codes, green-lane status). Exits `0` on pass, `1` on regression.

Usage:
```bash
python health_check.py                   # run check, print report
python health_check.py --save-baseline   # save current results as new baseline
python health_check.py --threshold 5     # allow up to 5% score drop before alerting
python health_check.py --primary-only    # only test gpt-4o-mini (faster)
```

When regression is detected, the report prints remediation steps including instructions to set `CIVIC_AI_DEGRADED_MODE=true`.

#### `backend/app/scripts/health_check_baseline.json` (new)
Baseline scores seeded from the 2026-06-12 confirmed-good run (post prompt-calibration):
- `gpt-4o-mini`: 100.0%
- `gpt-5.4-mini`: 98.3%
- `claude-sonnet-4-6`: 100.0%

#### Scheduled Health Check
A `civic-ai-health-check` scheduled task runs every Monday at 08:00 with `--threshold 5`, providing a weekly regression signal.

---

### Stress Test — 12 Scenario Expansion

#### `backend/app/scripts/stress_test_models.py` (updated)
Expanded from 5 to 12 scenarios across four claim types (false, misleading, truthful, mixed) and three difficulty levels:

| ID | Type | Difficulty |
|---|---|---|
| `ss_bankruptcy` | misleading | medium |
| `tcja_83pct` | misleading | hard |
| `inflation_june2022` | truthful | easy |
| `min_wage_2009` | truthful | medium |
| `medicare_bankrupt` | misleading | medium |
| `violent_crime_1990s` | truthful | medium |
| `voting_record_false` | false | easy |
| `healthcare_spending` | truthful | medium |
| `national_debt_per_capita` | misleading | medium |
| `renewables_2030` | misleading | medium |
| `jobs_pandemic_recovery` | truthful | hard |
| `border_encounters_record` | misleading | hard |

Post-calibration scores (2026-06-12 run):
- `gpt-4o-mini`: 100% (12/12)
- `gpt-5.4-mini`: 98.3% (near-perfect)
- `claude-sonnet-4-6`: 100% (12/12)

Scenario-typed pass criteria functions (`_misleading_criteria`, `_false_criteria`, `_truthful_criteria`) enforce claim-type-appropriate evaluation: misleading claims must be identified as misleading or mixed (not unsupported), false claims must be caught as unsupported with contradicting evidence cited, truthful claims must pass as supported with no false warnings.

---

### Configuration

#### `.env.example`
Added `CIVIC_AI_DEGRADED_MODE=false` with explanatory comment.

#### `backend/app/core/config.py`
Added `civic_ai_degraded_mode: bool = False` to `Settings` with a comment block describing circuit breaker behavior.

---

---

## [Unreleased] — 2026-06-13

### Source Integrity Pipeline

#### URL Reachability Verification (`backend/app/services/source_service.py`)
Added `check_url_reachable()` static method using `httpx` sync client (8s timeout, follows redirects, HEAD with GET fallback for 405 servers).

Behavior by HTTP status:
- **404 / 410 / 451** → hard reject at attach time with `source_url_not_found` error
- **401 / 402 / 403 / 429** → allowed through (paywalled / login-gated); reviewer prompted to paste an excerpt
- **5xx / timeout / network error** → allowed (transient); source is saved and flagged during AI draft generation
- **Social URLs** (Twitter/X, YouTube, etc.) → probe skipped entirely; these rate-limit bots and are reviewer-attested

Probe fires inside `validate_source_admission()` for all non-social, non-partisan URLs. Partisan-rule-matched URLs still go through the probe path (they hit the social check first and exit early if social, otherwise are rejected by the partisan rule before reaching the probe).

#### `GET /claims/url-check?url=...` (new endpoint, `backend/app/api/v1/claims.py`)
Lightweight reachability probe endpoint for frontend pre-checks. Returns `{status, code, message}`. Requires reviewer or admin auth, rate-limited.

#### Frontend Live URL Check (`frontend/admin/admin.js`, `frontend/admin/index.html`, `frontend/admin/admin.css`)
Source URL field auto-probes on blur via the new endpoint. Shows inline badge:
- `✓ Reachable (HTTP 200)` — green
- `⚠ Paywalled / gated (HTTP 403) — paste an excerpt below` — amber
- `✗ URL returned 404 — the page does not exist` — red

#### Key Excerpt Textarea (`frontend/admin/index.html`, `frontend/admin/admin.js`)
Added `content_excerpt` textarea to the Attach Source form (max 4000 chars). Reviewer-pasted excerpts are sent to the backend, stored on the `Source` model, and used as AI context fallback when live fetch returns empty (paywalled or JS-rendered pages). Textarea clears automatically after successful attach.

#### Test Suite Isolation (`backend/tests/conftest.py`) — new file
Created global `conftest.py` with an `autouse` fixture that patches `SourceService.check_url_reachable` to return `ok` for all tests. Prevents live HTTP during the test suite. Individual tests can override the fixture for URL-check-specific coverage.

---

### Publish Workflow — Gate Visibility & Clarity

#### Publish Checklist Fix (`frontend/admin/admin.js`)
`buildPublishChecklist()` was missing two gate codes that silently block publish:
- `claim_not_fact_checkable` — claim must be marked fact-checkable
- `latest_verdict_must_be_supported_mixed_or_unsupported` — no completed evaluation or verdict is `pending` / `insufficient_evidence`

Both are now shown as explicit pass/fail items. Removed the redundant "Publish gate passed" summary item (implied by all individual checks passing).

#### Workbench Gate Status Block (`frontend/admin/admin.js`)
Replaced raw JSON array dump of `publish_gate_failures` with a human-readable plain-text block. Example output when blocked:
```
Blocked — incomplete requirements:
  • Evaluation verdict required (supported / mixed / unsupported)
  • Primary verification source must be attached
  • Secondary verification source must be attached
```
Shows `✓ All publish gate checks passed.` when the claim is ready.

#### Dual-Control Notice (`frontend/admin/index.html`)
Added an explicit note above the publish action form explaining that the admin executing publish must be a different account from the reviewer who wrote the evaluation. Previously this only appeared as a tooltip and surprised users with a 409 error.

---

### Public Frontend — Published Claims Tab & Methods Tab

#### Published Claims tab (`frontend/index.html`, `frontend/app.js`, `frontend/styles.css`)
New "Published Claims" nav tab surfaces every published fact-checked claim in a filterable list without requiring a backend change.

Key implementation details:
- `compareRawState` — stores the unfiltered API response so the claims view shows all published claims regardless of the compare-board confidence/issue filters
- `buildClaimsFromCompare()` — flattens `issues[].items[]` into a sorted flat list (unsupported first, then mixed, then supported; alphabetical by candidate within each group)
- `renderPublishedClaims()` — populates the candidate filter dropdown on first render, applies verdict/candidate/issue filters client-side, renders claim cards with collapsible reviewer analysis via `<details>`
- Filter controls: verdict select, candidate select (populated from API data), issue text search (live `input` event)
- Claim cards: left-border colour-coded by verdict (green=supported, amber=mixed, red=contradicted), italic claim quote, expandable rationale + citation notes + source pills + reviewer flags

#### Methods tab (`frontend/index.html`, `frontend/styles.css`)
Full editorial transparency page accessible via the "Methods" nav button. Covers:
- What counts as fact-checkable
- All four verdict definitions with their legend pills
- Source requirements (primary + secondary minimum, candidate-originated sources excluded from verification)
- Confidence score calibration (84% ceiling rule)
- Dual-control enforcement explained in plain language
- What the page is not (no endorsements)
- Corrections policy

#### Policy Stances placeholder (`frontend/index.html`)
`#stances-view` section added with a "coming in a future update" note so the nav tab doesn't show a blank page.

#### Tab routing (`frontend/app.js`)
`DEDICATED_VIEWS` map (`claims`, `stances`, `methods`) drives `setActiveTab()`:
- Dedicated-view tabs show only their section, hide all compare sections
- `compare` and `matrix` tabs show all compare sections, hide all dedicated-view sections
- Works with `:scope > section` selector so the nested `.compare-board` inside `#published-claims-view` is not accidentally hidden

Cache-busters bumped to `v=20260613a` on both `styles.css` and `app.js` references.

#### Claim Matrix tab isolation (`frontend/index.html`, `frontend/app.js`)
"Claim Matrix" now shows only the issue list + evidence panel — no hero, no candidate cards, no contrast band, no filter controls. Added IDs to previously unnamed elements (`compare-hero`, `compare-controls-section`, `compare-contrast`, `compare-matrix-board`) and replaced the old binary `DEDICATED_VIEWS` map with a `TAB_VISIBILITY` table that explicitly lists which element IDs are visible per tab, plus a separate `header` flag for the hero. Unknown tabs fall back to the full compare view.

---

## Prior Sessions

Earlier sessions established:
- FastAPI + PostgreSQL backend with versioned `v1` routes
- Claim workbench adjudication UI at `/admin/`
- Review draft endpoint `POST /v1/claims/{claim_id}/review-draft` wired to `ReviewDraftService`
- Source attach reachability checks, stored `fetch_status`, and reviewer-provided `content_excerpt` fallback
- Background job worker, rate limiting, dual-control approval, audit log
- Texas 2026 U.S. Senate race data ingestion and adjudication pipeline
- 418 automated tests
- Reviewer authentication with signed bearer tokens
- Public read-only API tier with API key management
