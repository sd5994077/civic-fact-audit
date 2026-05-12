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
