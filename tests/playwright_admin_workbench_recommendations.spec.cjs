const { test, expect } = require("@playwright/test");
const path = require("path");
const { startFrontendStaticServer } = require("./helpers/frontend_static_server.cjs");

const CLAIM_ID = "89949aa0-1f75-481b-9449-6ee4f45f5b3b";
const CANDIDATE_ID = "aaaaaaaa-1111-4444-9999-bbbbbbbbbbbb";

function buildChecklist(secondaryPresent) {
  return [
    { code: "fact_checkable", label: "Claim is fact-checkable", passed: true, blocking: false },
    { code: "verification_primary_present", label: "Verification primary source is attached", passed: true, blocking: false },
    {
      code: "verification_secondary_present",
      label: "Verification secondary source is attached",
      passed: secondaryPresent,
      blocking: !secondaryPresent,
    },
    {
      code: "latest_verdict_publishable",
      label: "Latest verdict is publishable (supported/mixed/unsupported)",
      passed: false,
      blocking: true,
    },
  ];
}

test("workbench suggestions attach flow for claim 89949aa0-1f75-481b-9449-6ee4f45f5b3b", async ({ page }) => {
  const localServer = await startFrontendStaticServer(path.resolve(__dirname, "../frontend"));
  const now = "2026-05-22T12:00:00Z";
  const statementUrl = "https://www.johncornyn.com/on-the-issues/";
  const sourcePrimaryUrl = "https://www.congress.gov/search?q=cornyn+trump+voting+record";
  const sourceSecondaryUrl = "https://www.reuters.com/site-search/?query=cornyn+trump+voting+record";
  let attachCalls = 0;
  let recommendationCalls = 0;
  const attachedSources = [
    {
      id: "10000000-0000-0000-0000-000000000001",
      claim_id: CLAIM_ID,
      url: sourcePrimaryUrl,
      source_class: "primary",
      source_origin: "verification",
      publisher: "Congress.gov",
      quality_score: 0.93,
      created_at: now,
    },
  ];

  function verificationCounts() {
    const verification = attachedSources.filter((source) => source.source_origin === "verification");
    const primary = verification.filter((source) => source.source_class === "primary").length;
    const secondary = verification.filter((source) => source.source_class === "secondary").length;
    return { primary, secondary, total: verification.length };
  }

  function buildWorkbenchRow() {
    const counts = verificationCounts();
    const secondaryPresent = counts.secondary > 0;
    return {
      claim_id: CLAIM_ID,
      claim_text:
        "In Trump's first term, Senator Cornyn had a stronger pro-Trump voting record than 95 out of 100 Senators and voted with Trump over 92% of the time.",
      issue_tag: "Democracy & rule of Law",
      status: "reviewed",
      statement_source_url: statementUrl,
      statement_published_at: now,
      candidate_id: CANDIDATE_ID,
      candidate_name: "John Cornyn",
      candidate_party: "Republican",
      candidate_office: "US Senate",
      candidate_state: "TX",
      election_cycle: 2026,
      race_stage: "primary_runoff",
      latest_verdict: null,
      latest_confidence: null,
      latest_rationale: null,
      latest_citation_notes: null,
      latest_reviewer_id: null,
      reviewer_state: secondaryPresent ? "Needs Review" : "Needs Evidence",
      second_reviewer_action: null,
      verification_source_count: counts.total,
      verification_primary_count: counts.primary,
      verification_secondary_count: counts.secondary,
      publish_gate_passed: false,
      publish_gate_failures: secondaryPresent
        ? ["latest_verdict_publishable", "latest_rationale_present", "latest_citation_notes_present"]
        : ["verification_secondary_present", "latest_verdict_publishable", "latest_rationale_present", "latest_citation_notes_present"],
      is_published: false,
      checklist: buildChecklist(secondaryPresent),
    };
  }

  function buildRecommendationResponse() {
    const counts = verificationCounts();
    const recommendations = [];
    if (!attachedSources.some((source) => source.url === sourcePrimaryUrl)) {
      recommendations.push({
        template_id: "tx_senate_congress_primary",
        rank: recommendations.length + 1,
        source_class: "primary",
        source_category: "primary_record",
        source_origin: "verification",
        url: sourcePrimaryUrl,
        publisher: "Congress.gov",
        rationale: "Federal legislative record search for vote alignment.",
        recommendation_role: "attachable_evidence",
      });
    }
    if (!attachedSources.some((source) => source.url === sourceSecondaryUrl)) {
      recommendations.push({
        template_id: "reuters_secondary",
        rank: recommendations.length + 1,
        source_class: "secondary",
        source_category: "secondary_news",
        source_origin: "verification",
        url: sourceSecondaryUrl,
        publisher: "Reuters",
        rationale: "Independent reporting corroboration.",
        recommendation_role: "attachable_evidence",
      });
    }
    return {
      claim_id: CLAIM_ID,
      policy_version: "source_recommendation_policy_v1",
      verification_primary_count: counts.primary,
      verification_secondary_count: counts.secondary,
      missing_source_classes: counts.secondary > 0 ? [] : ["secondary"],
      recommendations,
    };
  }

  try {
    await page.route("**/api/v1/**", async (route) => {
      const req = route.request();
      const method = req.method();
      const url = new URL(req.url());
      const endpoint = `${method} ${url.pathname}`;
      const json = (body, status = 200) =>
        route.fulfill({
          status,
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });

      if (endpoint === "POST /api/v1/auth/login") {
        return json({ access_token: "fake-admin-token", token_type: "bearer", reviewer_id: "admin@local", role: "admin" });
      }
      if (endpoint === "GET /api/v1/auth/me") {
        return json({ reviewer_id: "admin@local", role: "admin" });
      }
      if (endpoint === "GET /api/v1/candidates") return json([]);
      if (endpoint === "GET /api/v1/admin/intake-profiles") return json({ version: "v1", profiles: [] });
      if (endpoint === "GET /api/v1/claims/review-queue") return json([]);
      if (endpoint === "GET /api/v1/claims/evidence-queue") return json([]);
      if (endpoint === "GET /api/v1/claims/proposals") return json([]);
      if (endpoint === "GET /api/v1/claims/publish-queue") return json([]);
      if (endpoint === "GET /api/v1/admin/jobs/metadata") {
        return json({ allowlist_version: "v1", intake_profile_version: "v1", synchronous_execution: true, jobs: [], intake_profiles: [] });
      }
      if (endpoint === "GET /api/v1/admin/jobs") return json([]);
      if (endpoint === "GET /api/v1/admin/audit-events") return json([]);

      if (endpoint === "GET /api/v1/claims/workbench") return json([buildWorkbenchRow()]);
      if (endpoint === `GET /api/v1/claims/${CLAIM_ID}/sources`) {
        return json({ claim_id: CLAIM_ID, sources: attachedSources });
      }
      if (endpoint === `GET /api/v1/claims/${CLAIM_ID}/source-recommendations`) {
        recommendationCalls += 1;
        return json(buildRecommendationResponse());
      }
      if (endpoint === `POST /api/v1/claims/${CLAIM_ID}/sources`) {
        attachCalls += 1;
        const body = JSON.parse(req.postData() || "{}");
        const created = {
          id: `10000000-0000-0000-0000-00000000000${attachedSources.length + 1}`,
          claim_id: CLAIM_ID,
          url: body.url,
          source_class: body.source_class,
          source_origin: body.source_origin,
          publisher: body.publisher,
          quality_score: 0.86,
          created_at: now,
        };
        attachedSources.push(created);
        return json({ claim_id: CLAIM_ID, sources: attachedSources });
      }

      return json({ error: { message: `No mock for ${endpoint}` } }, 404);
    });

    await page.goto(`${localServer.baseUrl}/admin/`, { waitUntil: "networkidle" });
    await page.fill("#auth-email", "admin@local");
    await page.fill("#auth-password", "change-me");
    await page.click("#auth-form button[type='submit']");
    await expect(page.locator("#admin-workspace")).toBeVisible();

    await page.fill("#workbench-filter-state", "TX");
    await page.fill("#workbench-filter-office", "US Senate");
    await page.fill("#workbench-filter-cycle", "2026");
    await page.selectOption("#workbench-filter-stage", "primary_runoff");
    await page.click("#workbench-filter-form button[type='submit']");

    await expect(page.locator("#workbench-list-status")).toContainText("Loaded 1 Workbench claims.");
    await expect(page.locator("#workbench-source-claim-id")).toHaveValue(CLAIM_ID);
    await expect(page.locator("#workbench-context-status")).toContainText("John Cornyn");
    await expect(page.locator("#workbench-evidence-summary")).toContainText("1 total (1 primary / 0 secondary)");

    await expect(page.locator("#workbench-recommendations-list .row-btn")).toHaveCount(1);
    await expect(page.locator("#workbench-recommendations-list")).toContainText("Reuters");
    await expect(page.locator("#workbench-recommendations-list")).toContainText("category: Secondary news");
    await expect(page.locator("#workbench-recommendations-status")).toContainText("Missing: secondary.");

    await page.click("#workbench-recommendations-list .workbench-recommendation-use");
    await expect(page.locator("#workbench-evidence-summary")).toContainText("2 total (1 primary / 1 secondary)");
    await expect(page.locator("#workbench-sources-list")).toContainText("Reuters");
    await expect(page.locator("#workbench-recommendations-list .row-btn")).toHaveCount(0);
    await expect(page.locator("#workbench-recommendations-status")).toContainText("Minimum verification classes are currently satisfied.");
    expect(attachCalls).toBe(1);
    expect(recommendationCalls).toBeGreaterThan(0);
  } finally {
    await new Promise((resolve) => localServer.server.close(resolve));
  }
});

test("workbench discovery-only suggestion hides attach action", async ({ page }) => {
  const localServer = await startFrontendStaticServer(path.resolve(__dirname, "../frontend"));
  const now = "2026-05-22T12:00:00Z";
  const statementUrl = "https://www.johncornyn.com/on-the-issues/";
  const discoveryUrl = "https://www.usaspending.gov/search/?q=operation+lone+star";

  try {
    await page.route("**/api/v1/**", async (route) => {
      const req = route.request();
      const method = req.method();
      const url = new URL(req.url());
      const endpoint = `${method} ${url.pathname}`;
      const json = (body, status = 200) =>
        route.fulfill({
          status,
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });

      if (endpoint === "POST /api/v1/auth/login") {
        return json({ access_token: "fake-admin-token", token_type: "bearer", reviewer_id: "admin@local", role: "admin" });
      }
      if (endpoint === "GET /api/v1/auth/me") return json({ reviewer_id: "admin@local", role: "admin" });
      if (endpoint === "GET /api/v1/candidates") return json([]);
      if (endpoint === "GET /api/v1/admin/intake-profiles") return json({ version: "v1", profiles: [] });
      if (endpoint === "GET /api/v1/claims/review-queue") return json([]);
      if (endpoint === "GET /api/v1/claims/evidence-queue") return json([]);
      if (endpoint === "GET /api/v1/claims/proposals") return json([]);
      if (endpoint === "GET /api/v1/claims/publish-queue") return json([]);
      if (endpoint === "GET /api/v1/admin/jobs/metadata") {
        return json({ allowlist_version: "v1", intake_profile_version: "v1", synchronous_execution: true, jobs: [], intake_profiles: [] });
      }
      if (endpoint === "GET /api/v1/admin/jobs") return json([]);
      if (endpoint === "GET /api/v1/admin/audit-events") return json([]);
      if (endpoint === "GET /api/v1/claims/workbench") {
        return json([
          {
            claim_id: CLAIM_ID,
            claim_text: "Funding claim test",
            issue_tag: "Democracy & rule of Law",
            status: "reviewed",
            statement_source_url: statementUrl,
            statement_published_at: now,
            candidate_id: CANDIDATE_ID,
            candidate_name: "John Cornyn",
            candidate_party: "Republican",
            candidate_office: "US Senate",
            candidate_state: "TX",
            election_cycle: 2026,
            race_stage: "primary_runoff",
            latest_verdict: null,
            latest_confidence: null,
            latest_rationale: null,
            latest_citation_notes: null,
            latest_reviewer_id: null,
            reviewer_state: "Needs Evidence",
            second_reviewer_action: null,
            verification_source_count: 0,
            verification_primary_count: 0,
            verification_secondary_count: 0,
            publish_gate_passed: false,
            publish_gate_failures: ["verification_primary_present"],
            is_published: false,
            checklist: buildChecklist(false),
          },
        ]);
      }
      if (endpoint === `GET /api/v1/claims/${CLAIM_ID}/sources`) return json({ claim_id: CLAIM_ID, sources: [] });
      if (endpoint === `GET /api/v1/claims/${CLAIM_ID}/source-recommendations`) {
        return json({
          claim_id: CLAIM_ID,
          policy_version: "source_recommendation_policy_v1",
          verification_primary_count: 0,
          verification_secondary_count: 0,
          missing_source_classes: ["primary", "secondary"],
          recommendations: [
            {
              template_id: "usaspending_primary",
              rank: 1,
              source_class: "primary",
              source_category: "primary_record",
              source_origin: "verification",
              url: discoveryUrl,
              discovery_url: discoveryUrl,
              evidence_url: null,
              publisher: "USAspending.gov",
              rationale: "Funding discovery source",
              recommendation_role: "discovery_only",
              validation_note: "USAspending search could not be resolved to a specific evidence record.",
            },
          ],
        });
      }
      return json({ error: { message: `No mock for ${endpoint}` } }, 404);
    });

    await page.goto(`${localServer.baseUrl}/admin/`, { waitUntil: "networkidle" });
    await page.fill("#auth-email", "admin@local");
    await page.fill("#auth-password", "change-me");
    await page.click("#auth-form button[type='submit']");
    await expect(page.locator("#admin-workspace")).toBeVisible();
    await page.fill("#workbench-filter-state", "TX");
    await page.fill("#workbench-filter-office", "US Senate");
    await page.fill("#workbench-filter-cycle", "2026");
    await page.selectOption("#workbench-filter-stage", "primary_runoff");
    await page.click("#workbench-filter-form button[type='submit']");

    await expect(page.locator("#workbench-recommendations-list")).toContainText("Open Research Link");
    await expect(page.locator("#workbench-recommendations-list .workbench-recommendation-use")).toHaveCount(0);
  } finally {
    await new Promise((resolve) => localServer.server.close(resolve));
  }
});
