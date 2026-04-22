# Verification Policy

This document defines how Civic Fact Audit captures candidate claims, verifies them, and decides what is eligible for publication.

## Core Rule

The platform may use candidate-controlled channels to capture what a candidate said, but it does not use candidate-controlled content as verification evidence for factual verdicts.

In practice:
- Candidate websites, official campaign social accounts, debates, interviews, speeches, and press releases can be used to identify a claim.
- Factual verdicts must be based on reliable verification sources.
- AI may assist with extraction and preparation, but a verified human reviewer must make the final publishable adjudication.

## Source Categories

### 1) Statement Sources

These sources help establish what the candidate said.

Examples:
- official campaign website
- official campaign social account
- debate transcript or debate video
- interview transcript or recording
- speech transcript or recording
- campaign press release

Rules:
- These sources can establish the wording, timing, and context of a candidate claim.
- These sources do not, by themselves, establish whether the claim is true.
- In product output, these should be labeled as candidate-originated material rather than verification evidence.

### 2) Verification Sources

These sources are used to determine whether a claim is supported, mixed, unsupported, or still insufficient.

Preferred sources:
- government records and agency datasets
- court records, rulings, and filings
- legislative records
- certified election records, audits, and recounts
- regulatory disclosures
- official reports with clear methodology
- independent, reputable reporting used as corroboration

Rules:
- Published factual verdicts should rely on at least one primary record and one independent corroborating source when possible.
- If the underlying record is available, prefer it over commentary about the record.
- If a source is interpretive, summarize it as interpretation rather than treating it as raw fact.
- In product output, these should be labeled separately from candidate-originated sources.

### 3) Disallowed Verification Sources

These sources should not be sufficient for factual adjudication on their own.

Examples:
- candidate campaign content
- candidate-owned social posts
- partisan advocacy content offered as sole evidence
- anonymous posts
- meme accounts, reposts, screenshots without provenance
- unsourced commentary

Rules:
- A candidate social post may be a statement source.
- It is not a verification source for deciding whether the claim is true.

## Publication Standard

Claims should move through these stages:

1. Claim captured
2. Evidence attached
3. Human reviewed
4. Eligible for publication

Only the human-reviewed stage should be treated as publishable fact-check content.

For a result to be publishable, it should have:
- the candidate claim text
- linked verification sources
- a human reviewer verdict
- rationale
- citation notes
- auditable reviewer identity

## Verdict Rules

### Supported

Use when the claim is materially backed by the cited record.

### Mixed

Use when the claim has a factual basis but omits key context, overstates the evidence, or blends true and false elements.

### Unsupported

Use when the cited record materially contradicts the claim.

### Insufficient

Use when the evidence is not strong enough, direct enough, or specific enough to justify a stronger verdict.

## Narrowest Defensible Conclusion

Every review should publish the narrowest defensible conclusion.

That means:
- separate broad rhetoric from specific factual assertions
- distinguish procedural irregularity from outcome-level proof
- distinguish allegation from charge, and charge from conviction
- distinguish commentary from underlying record

If the source only supports a narrower claim, publish the narrower claim.

## When Special Policies Are Needed

Most claims should use this general policy.

Add special-case guidance only for high-risk categories where the general rules are not enough, such as:
- election integrity claims
- criminal and legal status claims
- health or scientific claims
- economic and statistical claims

The goal is not to create a custom policy for every topic. The goal is to use one strong general policy and add narrower rules only where necessary.

## Reviewer Responsibilities

Human reviewers should:
- read the cited sources directly when possible
- verify that the evidence matches the exact claim text
- avoid treating institutional commentary as automatic truth
- record rationale and citation notes clearly
- leave a claim as `insufficient` when the evidence is not good enough

## Public Trust Language

The project should communicate this clearly:

- Candidate-owned channels may be used to capture what was said.
- Published fact reviews are based on documented verification sources.
- No claim should be published as fact-checked solely because a candidate or campaign said it.
- No claim should be published as fact-checked solely because AI suggested a verdict.
