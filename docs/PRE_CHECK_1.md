# Pre-Check 1: Before Next Phase

Use this checklist before starting the next roadmap phase. The goal is to confirm the current app still runs, shows the reviewed data correctly, and does not hide evidence sufficiency warnings.

## Command Checks

- [ ] Docker is running.
- [ ] Backend starts without errors.
- [ ] Frontend starts without errors.
- [ ] `node --check frontend/app.js` passes.
- [ ] Backend tests pass, if the test suite is available.
- [ ] Database migrations are current.

## App Smoke Test

- [ ] Open the app in the browser.
- [ ] Race selector loads available races.
- [ ] Selecting the Texas Senate race updates the comparison view.
- [ ] Candidate comparison loads without a blank screen.
- [ ] Issue list loads and allows selecting an issue.
- [ ] Keyboard navigation works in the issue list.
- [ ] Date window filter applies without breaking the page.
- [ ] Issue text filter applies and can be reset.
- [ ] Minimum confidence filter applies and can be reset.
- [ ] Minimum source quality filter applies and can be reset.

## Evidence And Warning Checks

- [ ] Published claims display their verdicts.
- [ ] Each published verdict shows rationale.
- [ ] Each published verdict shows citation notes or source references.
- [ ] Evidence sufficiency labels are visible.
- [ ] Critical evidence warnings appear in the issue summary when present.
- [ ] Item-level evidence warnings appear near the affected claim or evidence item.
- [ ] Source quality and confidence values are visible where expected.
- [ ] Empty states explain whether no data exists or filters removed all results.

## Review And Publish Checks

- [ ] No claim is auto-published without reviewer approval.
- [ ] Reviewer verdicts include `supported`, `mixed`, or `unsupported`.
- [ ] Reviewer rationale is present for published claims.
- [ ] Citation notes are present for published claims.
- [ ] Publish queue report shows no unexpected blocked claims.
- [ ] Publish progress report matches the expected reviewed/published count.

## Multi-Race Readiness Checks

- [ ] App copy does not imply it only supports the Texas Senate race.
- [ ] Race/stage labels are visible in the comparison view.
- [ ] Filters still work when changing races or stages. `Deferred: requires at least one additional race or stage dataset.`
- [ ] Empty race results show a neutral message. `Deferred: verify against a race with no matching claims or no candidates loaded.`

## Deferred Checks

- [ ] Cross-race and cross-stage filter persistence test. `Blocked by single-race dataset.`
- [ ] Empty-race neutral messaging test using true no-data race. `Blocked by single-race dataset.`

## Pass Criteria

- [ ] No blocking runtime errors.
- [ ] No blank or broken comparison view.
- [ ] No hidden critical evidence warnings.
- [ ] Reviewed and published claims are traceable to rationale and citations.
- [ ] Any issues found are documented before moving to the next phase.

## Notes

- Date checked: 05/11/2026
- Checked by: Stephen
- Issues found:
- Follow-up needed: 4
