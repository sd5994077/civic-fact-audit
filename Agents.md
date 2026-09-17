# AGENTS Instructions

Scope: Entire `civic-fact-audit/` tree.

## Mission
Build a transparent, nonpartisan candidate-claim auditing platform where every score is traceable to evidence.

## Operating Rules
1. Never generate candidate endorsements or voting recommendations.
2. Prefer evidence traceability over automation speed.
3. Any claim verdict must include citations.
4. AI can propose extraction/summaries but cannot be sole verifier.
5. Keep reproducible scoring formulas and expose denominators.

## Coding Conventions
- Python: type hints required for new functions.
- Keep business logic in `services/`, not route handlers.
- All endpoints should return structured error objects.
- Add tests for score calculations before modifying formulas.
- Follow existing project conventions
- Do not introduce new libraries unless justified
- Add comments only where they help understanding
- Update docs when behavior changes

## Documentation Rules
- Update `docs/DATA_MODEL.md` when schema changes.
- Update `docs/SCORING.md` when scoring logic changes.
- Update `ROADMAP.md` for milestone/status changes.

## Safety + Product Policy
- Avoid partisan language in generated UI text.
- Clearly label confidence and evidence sufficiency.
- Keep reviewer override actions auditable.
- Never delete large sections without explanation
- Run tests/lint after code changes when possible
- Show a concise summary of what changed

## Source Admission Check (Required Before Adding Sources)
- Verification evidence must prioritize neutral, record-based sources first (government records, court filings, legislative records, certified datasets, official reports with methodology).
- Independent reporting can be used as secondary corroboration, not as the only basis when a primary record exists.
- Partisan or advocacy sources are disallowed as verification evidence.
- Exception: a partisan source is allowed only to capture a direct candidate quote from the candidate's own official social media page/account, and must be marked as candidate-originated material (not verification-originated truth evidence).
- When adding any source, record `source_origin`, `source_class`, `publisher`, and a brief rationale in review notes/proposal notes when applicable.

---

## Build & test commands
Verified 2026-08-28 (see ROADMAP.md "Current Status"): 435 backend tests
passed, 4 Playwright frontend tests passed. Run these before reporting any
change done:
- Backend: `python -m pytest backend/tests`
- Frontend: `npm test` (Playwright suite)
- No lint is configured yet — that is a real gap, not an oversight.

Keep this section in sync with `scripts/Test-Project.ps1` — they must
name the same commands.

## Before you write code
- This repo has real ongoing history (many commits/PRs), not a fresh
  scaffold. Read `ROADMAP.md` and recent commits before assuming the
  current state of a feature.
- Check `docs/DATA_MODEL.md` and `docs/SCORING.md` before touching schema
  or scoring logic — both are required reading under Documentation Rules
  above, not optional context.
- Confirm whether you're asked to BUILD something new or VALIDATE
  existing behavior; don't rewrite working code while investigating a bug.

## While implementing
- Root-cause first: don't patch symptoms in scoring/verification logic.
- Test-first for anything touching score formulas or claim verdicts (this
  repeats the "Add tests for score calculations" rule above because it's
  the highest-consequence code path in this repo).
- Prefer the smallest useful change over a rewrite.
- Run the Build & test commands above before saying a task is complete.

## Boundaries
- No destructive command (see the hook's pattern list in
  `.claude/hooks/Protect-DestructiveAction.ps1`: force-push, hard reset,
  git clean, DROP TABLE/DATABASE, `alembic downgrade`,
  `docker compose down -v`, etc.) without asking first — even outside a
  session where the hook can actually intercept it (Codex cloud tasks and
  Claude Cowork/chat have no local hook enforcement; treat this rule as
  binding there too).
- No commit, push, or PR without explicit authorization.
- The working tree has ~150+ modified/untracked files on top of real
  commit history. Don't assume anything uncommitted is safe to discard,
  stash, or reset past — ask before any operation that could lose it.
- No new library, framework, or skill for a one-off task — only after the
  same need has come up a third time (see Coding Conventions above: don't
  introduce new libraries without justification).

## Model and agent judgment
- Use a model/effort tier adequate to the task; escalate for schema
  changes, scoring-formula changes, or source-policy ambiguity.
- Default to a single session/agent unless a task is genuinely
  parallelizable (e.g., independent frontend/backend work).

## Recording decisions
This repo already has a decision-record convention: `ROADMAP.md`'s
"Current Status" section, plus `docs/DATA_MODEL.md`, `docs/SCORING.md`,
and `Plan.md`. Record material decisions there, in the existing format,
rather than starting a separate `docs/decisions/` folder.

## Claude Code specifics
- `CLAUDE.md` in this repo is new as of 2026-09-17 and imports this file
  (`@AGENTS.md`). Before that, local Claude Code CLI sessions were not
  reading these rules at all — only `Agents.md` (now renamed `AGENTS.md`
  for cross-tool/case-sensitive-filesystem compatibility) existed.
- `.claude/settings.json` adds a `PreToolUse` hook (destructive-command
  confirmation) and a `Stop` hook (`scripts/Test-Project.ps1`, running the
  real pytest + Playwright suites above) — local Claude Code CLI only.
