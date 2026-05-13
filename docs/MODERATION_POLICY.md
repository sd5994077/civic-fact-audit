# Moderation Policy

This document defines legal/ethical output boundaries for Civic Fact Audit moderation and publish gating.

## Policy Scope

Applies to:
- reviewer-authored and AI-draft rationale/citation text used in claim evaluations
- publish gating for claim verdict records
- public compare/export response language

## Prohibited Output Classes

The platform must reject or block content that includes:
- candidate endorsements or voting recommendations
- directive voting language (`vote for`, `vote against`, or equivalent prescriptions)
- unverifiable allegations stated as established fact
- targeted harassment, threats, or violent directives
- doxxing or private personal data exposure
- explicit defamatory framing without cited record evidence

## Required Output Controls

- Neutral language only: no partisan persuasion or electoral directives.
- Evidence traceability: claim verdicts require linked evidence and citations.
- Uncertainty labeling: insufficient evidence must be stated clearly.
- Human-review gate: AI can draft suggestions but cannot publish final claim verdicts.

## Enforcement Boundaries

Config-backed moderation rules are loaded from:
- `backend/app/config/moderation_policy_v1.json`

Current policy version: `moderation_policy_v2_2026_05_13`. Matching mode: `regex`.

### Rule groups

| Rule ID | Violation type | Description |
|---|---|---|
| `endorsement_vote_for` | `endorsement_or_recommendation` | Vote-for directives |
| `endorsement_vote_against` | `endorsement_or_recommendation` | Vote-against directives |
| `directive_recommendation` | `endorsement_or_recommendation` | Prescriptive electoral language |
| `violence_threats` | `violence_or_threat` | Violent directives or threats against persons |
| `harassment_doxxing` | `harassment_or_doxxing` | Private data exposure or location stalking |
| `defamatory_framing` | `defamatory_framing` | Serious unverified allegations stated as fact |
| `prompt_injection` | `prompt_injection_attempt` | Adversarial AI prompt override patterns |

### Enforced paths
- `POST /v1/claims/{id}/evaluate`
- `POST /v1/claims/{id}/publish` (publish gate includes moderation check)
- Draft-verdict proposal validation (`proposal_payload.rationale`, `proposal_payload.citation_notes`) — violations are logged to the audit event log
- Statement text before AI claim extraction — prompt injection attempts are blocked and logged with actor `system:extraction_pipeline`

Violation responses return structured `422` errors:
- `error.code = moderation_policy_violation` (evaluation/proposal paths)
- `error.code = statement_text_rejected` (extraction prompt injection path)
- `error.code = publish_gate_moderation_failure` (publish path)
- `error.details` includes: `rejection_field`, `matched_rule`, `policy_version`, `violation_type`

## Reviewer/Admin Escalation and Override Audit

- Moderation-blocked evaluations are not committed.
- Publish-gate moderation failures are returned in `publish_gate_failures` and must be resolved before publish.
- Reviewer/admin actions remain auditable via existing reviewer identity and claim/proposal workflow metadata.
- **Violation audit logging:** Moderation violations in proposal and extraction paths are written to `AdminAuditEvent` with `action=moderation_violation`, `entity_type=moderation_rule`. Metadata includes `rejection_field`, `violation_type`, `matched_pattern`, `policy_version`, and a 200-char `text_preview`.
- **Moderation risk endpoint:** `GET /v1/admin/moderation-risk?window_days=N` (admin-only) returns per-reviewer violation counts and last violation timestamp for the given window. Used to identify reviewers triggering repeated moderation blocks.

## Appeals and Corrections

- Published claim records should support correction through the existing unpublish/re-review workflow.
- Corrections should preserve auditability:
  - who requested correction
  - what evidence changed
  - which rationale/citation content was replaced
  - when the revised publish decision occurred

## Follow-On Scope

Phase 0 closes policy definition plus high-risk enforcement.
Broader NLP moderation, abuse heuristics, and adversarial hardening are tracked in Phase 5 security work.
