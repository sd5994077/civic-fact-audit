# Project Status

## Current Position

The software implementation roadmap is complete through Phase 10. The repository has a functioning FastAPI backend, PostgreSQL schema and migrations, reviewer/admin workflows, source-admission controls, audit logging, a public published-claims surface, and a browser-based Workbench. As of 2026-10-01, the verified automated baseline is 453 backend tests and 5 Playwright smoke tests passing. Compose configuration validation also passes.

The release branch includes the later documentation and operating-contract updates plus fixes for all four PR #9 review findings. Fully merged historical branches have been removed. The manual unpublished-claim pilot remains outstanding; branch integration does not replace independent human adjudication.

That is implementation progress, not evidence that the service is ready for public use. There is no demonstrated, maintained corpus of independently reviewed, published claim evaluations; no operating editorial team; and no deployment, monitoring, correction, or governance record suitable for a public civic-information product.

## Recommendation

Do not abandon the repository solely because it did not launch. The core platform is substantially built and testable. Stop expanding its feature set now and run one time-boxed pilot before deciding whether to continue investing.

## Six-Week Pilot

Use one clearly scoped race and a balanced set of factual claims. Two reviewers should independently work a shared sample through capture, evidence attachment, adjudication, second-review approval, and any published correction. Keep candidate-originated material separate from verification evidence, and publish only citation-backed human decisions.

Track these measures each week:

- Number of fact-checkable claims captured, reviewed, and published.
- Median reviewer time from claim to publication.
- Evidence rejection or dead-link rate, including the reason.
- Initial reviewer disagreement rate and time to resolve it.
- Corrections, unpublishes, and their turnaround time.
- Whether the public presentation is understandable to a neutral reader without implying an endorsement.

## Decision Gate

Continue only if the pilot produces a modest but credible public corpus, reviewers can operate the workflow without repeated engineering intervention, and the team has a realistic owner for editorial policy and corrections. If the pilot cannot sustain those conditions, preserve the repository as a well-tested prototype and stop feature investment rather than adding more automation.

## Immediate Engineering Work

Before a pilot, create a clean release branch or pull request from the current commits, deploy a non-production environment, run migrations there, configure distinct reviewer accounts, and conduct a manual end-to-end exercise with a real but unpublished claim. The current automated suite is valuable, but it does not replace this operational test.
