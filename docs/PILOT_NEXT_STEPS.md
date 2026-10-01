# Local Pilot: Next Steps

Use this runbook for the current unpublished pilot claim. It preserves the human-review requirement: AI drafts are advisory only and must not be treated as verdicts or publication authority.

## Preconditions

- Local services are running (`http://localhost:3001/admin/`).
- Sign in as `reviewer@local`.
- The independent reviewer account remains available for any dual-control action.

## Repair the Evidence Packet

1. Open the **Workbench** tab.
2. Check **Show terminal states**, then click **Apply**.
3. Select claim `89949aa0-1f75-481b-9449-6ee4f45f5b3b`. It is unpublished and currently marked **Insufficient Evidence**.
4. Under **Attached Sources**, open the primary source in a new tab. Read the original record and select the precise passage relevant to the claim.
5. Copy a short, verbatim excerpt with enough context to assess the factual point. Do not use an AI-generated summary as the excerpt.
6. Record the source's exact URL, publisher, and `primary` source class.
7. Click **Remove** for the existing primary source. Then use **Attach Source** to add the same record back with:
   - the exact original URL;
   - source class `primary`;
   - source origin `verification`;
   - the same publisher; and
   - the verified passage in **Key Excerpt**.
8. Repeat steps 4–7 for the secondary verification source, retaining source class `secondary`.
9. Confirm **Attached Sources** lists one primary and one secondary verification source.

## Advisory Draft Check

1. In **Draft Evidence Review**, click **Generate Draft**.
2. Review the draft, source assessments, warnings, and missing-evidence fields.
3. Do not publish or submit an evaluation based only on the draft.

## Human Adjudication

- A reviewer must decide whether the existing human `insufficient` evaluation remains appropriate after inspecting the evidence.
- Replacing the existing evaluation requires the existing dual-control workflow with a different reviewer.
- Publish only after the evidence, moderation, and dual-control gates pass.

## Source Recommendation Rule

The current six suggested links are all **discovery-only**. They are research leads, not admitted evidence: do not attach them unless a reviewer opens the underlying record, verifies relevance, and adds it through **Attach Source** with the required source metadata and excerpt when needed.
