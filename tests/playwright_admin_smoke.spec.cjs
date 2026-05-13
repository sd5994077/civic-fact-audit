const { test, expect } = require("@playwright/test");
const fs = require("fs");
const http = require("http");
const path = require("path");

function contentTypeFor(filePath) {
  if (filePath.endsWith(".html")) return "text/html; charset=utf-8";
  if (filePath.endsWith(".js")) return "application/javascript; charset=utf-8";
  if (filePath.endsWith(".css")) return "text/css; charset=utf-8";
  if (filePath.endsWith(".svg")) return "image/svg+xml";
  if (filePath.endsWith(".png")) return "image/png";
  return "application/octet-stream";
}

async function startFrontendStaticServer(frontendRoot) {
  const server = http.createServer((req, res) => {
    const urlPath = (req.url || "/").split("?")[0];
    let relativePath = decodeURIComponent(urlPath);
    if (relativePath === "/") relativePath = "/index.html";
    if (relativePath === "/admin") relativePath = "/admin/index.html";
    if (relativePath === "/admin/") relativePath = "/admin/index.html";

    const fullPath = path.resolve(frontendRoot, `.${relativePath}`);
    const normalizedRoot = path.resolve(frontendRoot);
    if (!fullPath.startsWith(normalizedRoot)) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }

    fs.readFile(fullPath, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end("Not found");
        return;
      }
      res.writeHead(200, { "Content-Type": contentTypeFor(fullPath) });
      res.end(data);
    });
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  return {
    server,
    baseUrl: `http://127.0.0.1:${address.port}`,
  };
}

test("admin workspace smoke", async ({ page }) => {
  let localServer = null;
  const webUrl = process.env.CFA_WEB_URL || "";
  if (!webUrl) {
    localServer = await startFrontendStaticServer(path.resolve(__dirname, "../frontend"));
  }
  const baseUrl = webUrl || localServer.baseUrl;
  const candidateId = "11111111-1111-1111-1111-111111111111";
  const createdCandidateId = "22222222-2222-2222-2222-222222222222";
  const jobId = "33333333-3333-3333-3333-333333333333";
  const auditId = "44444444-4444-4444-4444-444444444444";
  const claimId = "55555555-5555-5555-5555-555555555555";
  const proposalId = "66666666-6666-6666-6666-666666666666";
  const candidateProposalId = "77777777-7777-7777-7777-777777777777";

  let bulkAttachPostCalls = 0;
  let lastBulkAttachPayload = null;
  let lastJobPayload = null;
  let evidenceGetCalls = 0;
  let jobsGetCalls = 0;
  let auditGetCalls = 0;
  const evidenceQueries = [];

  try {
    await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const method = req.method();
    const url = new URL(req.url());
    const path = url.pathname;

    const json = (body, status = 200) =>
      route.fulfill({
        status,
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });

    if (path === "/api/v1/auth/login" && method === "POST") {
      return json({
        access_token: "fake-admin-token",
        token_type: "bearer",
        reviewer_id: "admin@local",
        role: "admin",
      });
    }

    if (path === "/api/v1/auth/me" && method === "GET") {
      return json({ reviewer_id: "admin@local", role: "admin" });
    }

    if (path === "/api/v1/candidates" && method === "GET") {
      return json([
        {
          id: candidateId,
          name: "Candidate One",
          party: "Independent",
          office: "US Senate",
          state: "TX",
          election_cycle: 2026,
          race_stage: "primary",
          created_at: "2026-05-12T00:00:00Z",
        },
      ]);
    }

    if (path === `/api/v1/candidates/${candidateId}` && method === "GET") {
      return json({
        id: candidateId,
        name: "Candidate One",
        party: "Independent",
        office: "US Senate",
        state: "TX",
        election_cycle: 2026,
        race_stage: "primary",
        is_active: true,
        roster_status: "runoff_reported",
        roster_source_url: "https://example.org/roster",
        roster_checked_at: "2026-05-12T00:00:00Z",
        roster_notes: "Roster verified",
        created_at: "2026-05-12T00:00:00Z",
      });
    }

    if (path === "/api/v1/candidates" && method === "POST") {
      return json({
        id: createdCandidateId,
        name: "Candidate Two",
        party: "Democratic",
        office: "US Senate",
        state: "TX",
        election_cycle: 2026,
        race_stage: "primary_runoff",
        is_active: true,
        roster_status: null,
        roster_source_url: null,
        roster_checked_at: null,
        roster_notes: null,
        created_at: "2026-05-12T00:00:00Z",
      });
    }

    if (path.startsWith("/api/v1/candidates/") && method === "PATCH") {
      const body = JSON.parse(req.postData() || "{}");
      return json({
        id: candidateId,
        name: body.name,
        party: body.party,
        office: body.office,
        state: body.state,
        election_cycle: body.election_cycle,
        race_stage: body.race_stage,
        is_active: body.is_active,
        roster_status: body.roster_status,
        roster_source_url: body.roster_source_url,
        roster_checked_at: body.roster_checked_at,
        roster_notes: body.roster_notes,
        created_at: "2026-05-12T00:00:00Z",
      });
    }

    if (path === "/api/v1/claims/review-queue" && method === "GET") {
      return json([
        {
          claim_id: claimId,
          claim_text: "Candidate says bill X lowers costs by 20%.",
          issue_tag: "health care",
          status: "reviewed",
          statement_source_url: "https://example.org/statement",
          statement_published_at: "2026-05-12T00:00:00Z",
          candidate_id: candidateId,
          candidate_name: "Candidate One",
          candidate_party: "Independent",
          candidate_office: "US Senate",
          candidate_state: "TX",
          election_cycle: 2026,
          race_stage: "primary",
          primary_source_count: 1,
          secondary_source_count: 1,
          candidate_source_count: 1,
          verification_source_count: 1,
          latest_verdict: "mixed",
          latest_confidence: 0.62,
          latest_rationale: "Prior evidence exists",
          latest_citation_notes: null,
          latest_reviewer_id: "reviewer@local",
          latest_evaluated_at: "2026-05-12T00:00:00Z",
          warnings: [],
        },
      ]);
    }

    if (path === "/api/v1/claims/evidence-queue" && method === "GET") {
      evidenceGetCalls += 1;
      evidenceQueries.push(url.searchParams.toString());
      return json([
        {
          claim_id: claimId,
          claim_text: "Candidate says bill X lowers costs by 20%.",
          issue_tag: "health care",
          status: "reviewed",
          statement_source_url: "https://example.org/statement",
          statement_published_at: "2026-05-12T00:00:00Z",
          candidate_id: candidateId,
          candidate_name: "Candidate One",
          candidate_party: "Independent",
          candidate_office: "US Senate",
          candidate_state: "TX",
          election_cycle: 2026,
          race_stage: "primary",
          primary_source_count: 1,
          secondary_source_count: 0,
          candidate_source_count: 1,
          verification_source_count: 0,
          missing_source_classes: ["secondary"],
        },
      ]);
    }

    if (path === "/api/v1/claims/sources/bulk" && method === "POST") {
      bulkAttachPostCalls += 1;
      lastBulkAttachPayload = JSON.parse(req.postData() || "{}");
      return json({
        bulk_operation_id: "bulk-op-1",
        total: 2,
        attached: 1,
        failed: 1,
        results: [
          {
            claim_id: claimId,
            url: "https://example.gov/record",
            source_class: "primary",
            source_origin: "verification",
            status: "attached",
            error: null,
          },
          {
            claim_id: claimId,
            url: "https://invalid.example/dup",
            source_class: "secondary",
            source_origin: "verification",
            status: "failed",
            error: {
              code: "duplicate_source",
              message: "Source already attached for claim.",
              details: {},
            },
          },
        ],
      });
    }

    if (path === `/api/v1/claims/${claimId}/evaluate` && method === "POST") {
      const body = JSON.parse(req.postData() || "{}");
      return json({
        id: "88888888-8888-8888-8888-888888888888",
        claim_id: claimId,
        verdict: body.verdict || "supported",
        confidence: body.confidence || 0.7,
        rationale: body.rationale || "Reviewed",
        citation_notes: body.citation_notes || null,
        reviewer_id: "admin@local",
        created_at: "2026-05-12T00:00:00Z",
      });
    }

    if (path === "/api/v1/claims/proposals" && method === "GET") {
      return json([
        {
          id: proposalId,
          claim_id: claimId,
          proposal_type: "verification_source_suggestion",
          status: "proposed",
          proposed_by: "agent:triage",
          reviewed_by: null,
          reviewed_at: null,
          proposal_payload: {
            url: "https://example.org/source",
            source_class: "primary",
            source_origin: "verification",
            publisher: "Example Government Office",
            quality_score: 0.91,
          },
          claim_context: {
            verification_primary_count: 1,
            verification_secondary_count: 0,
            missing_source_classes: ["secondary"],
            verification_evidence_sufficient: false,
            latest_verdict: "mixed",
            latest_confidence: 0.62,
            latest_rationale: "Prior evidence exists",
            latest_citation_notes: "Source packet A",
            latest_reviewer_id: "reviewer@local",
            latest_evaluated_at: "2026-05-12T00:00:00Z",
          },
          review_notes: null,
          created_at: "2026-05-12T00:00:00Z",
          updated_at: "2026-05-12T00:00:00Z",
        },
        {
          id: candidateProposalId,
          claim_id: claimId,
          proposal_type: "candidate_source_capture",
          status: "proposed",
          proposed_by: "agent:triage",
          reviewed_by: null,
          reviewed_at: null,
          proposal_payload: {
            url: "https://example.org/candidate-source",
            source_class: "primary",
            source_origin: "verification",
            publisher: "Candidate One Campaign",
            quality_score: 0.73,
          },
          claim_context: {
            verification_primary_count: 1,
            verification_secondary_count: 0,
            missing_source_classes: ["secondary"],
            verification_evidence_sufficient: false,
            latest_verdict: "mixed",
            latest_confidence: 0.62,
            latest_rationale: "Prior evidence exists",
            latest_citation_notes: "Source packet A",
            latest_reviewer_id: "reviewer@local",
            latest_evaluated_at: "2026-05-12T00:00:00Z",
          },
          review_notes: null,
          created_at: "2026-05-12T00:00:00Z",
          updated_at: "2026-05-12T00:00:00Z",
        },
      ]);
    }

    if (path === `/api/v1/claims/proposals/${proposalId}/approve` && method === "POST") {
      return json({
        id: proposalId,
        claim_id: claimId,
        proposal_type: "verification_source_suggestion",
        status: "approved",
        proposed_by: "agent:triage",
        reviewed_by: "admin@local",
        reviewed_at: "2026-05-12T00:00:00Z",
        proposal_payload: { source_origin: "verification" },
        review_notes: "Looks valid",
        created_at: "2026-05-12T00:00:00Z",
        updated_at: "2026-05-12T00:00:00Z",
      });
    }

    if (path === "/api/v1/claims/publish-queue" && method === "GET") {
      return json([
        {
          claim_id: claimId,
          claim_text: "Candidate says bill X lowers costs by 20%.",
          issue_tag: "health care",
          candidate_name: "Candidate One",
          candidate_party: "Independent",
          statement_source_url: "https://example.org/statement",
          statement_published_at: "2026-05-12T00:00:00Z",
          latest_verdict: "supported",
          latest_confidence: 0.91,
          latest_rationale: "Verified against record.",
          latest_citation_notes: "Source A/B",
          latest_reviewer_id: "admin@local",
          primary_source_count: 1,
          secondary_source_count: 1,
          verification_primary_count: 1,
          verification_secondary_count: 1,
          publish_gate_passed: true,
          publish_gate_failures: [],
          is_published: false,
          published_at: null,
          published_by_reviewer_id: null,
        },
      ]);
    }

    if (path === `/api/v1/claims/${claimId}/publish` && method === "POST") {
      return json({
        claim_id: claimId,
        is_published: true,
        published_at: "2026-05-12T00:00:00Z",
        published_by_reviewer_id: "admin@local",
        publish_note: null,
      });
    }

    if (path === `/api/v1/claims/${claimId}/unpublish` && method === "POST") {
      return json({
        claim_id: claimId,
        is_published: false,
        published_at: null,
        published_by_reviewer_id: null,
        publish_note: "Unpublished by admin@local",
      });
    }

    if (path === "/api/v1/admin/jobs/metadata" && method === "GET") {
      return json({
        allowlist_version: "admin_jobs_allowlist_v2_2026_05_12",
        intake_profile_version: "intake_profiles_v1_2026_05_12",
        synchronous_execution: true,
        jobs: [
          {
            job_type: "ingest_candidate_roster",
            description: "Roster intake",
            input_schema: {
              required_fields: ["profile_id"],
              allowed_fields: ["profile_id"],
              field_types: { profile_id: "string" },
              allowed_values: { profile_id: ["tx_2026_senate", "tx_2026_ag_runoff"] },
              supports_dry_run: false,
            },
          },
          {
            job_type: "ingest_statement_batch",
            description: "Statement batch intake",
            input_schema: {
              required_fields: ["profile_id", "statement_batch"],
              allowed_fields: ["profile_id", "statement_batch"],
              field_types: { profile_id: "string", statement_batch: "string" },
              allowed_values: { profile_id: ["tx_2026_senate", "tx_2026_ag_runoff"] },
              supports_dry_run: false,
            },
          },
          {
            job_type: "extract_claims_batch",
            description: "Extract claims",
            input_schema: {
              required_fields: [],
              allowed_fields: [],
              field_types: {},
              allowed_values: {},
              supports_dry_run: false,
            },
          },
          {
            job_type: "backfill_claim_reviewability",
            description: "Backfill reviewability",
            input_schema: {
              required_fields: [],
              allowed_fields: [],
              field_types: {},
              allowed_values: {},
              supports_dry_run: false,
            },
          },
          {
            job_type: "map_issue_frames",
            description: "Map issue frames",
            input_schema: {
              required_fields: [],
              allowed_fields: [],
              field_types: {},
              allowed_values: {},
              supports_dry_run: false,
            },
          },
          {
            job_type: "generate_publish_queue_report",
            description: "Publish queue report",
            input_schema: {
              required_fields: [],
              allowed_fields: [],
              field_types: {},
              allowed_values: {},
              supports_dry_run: false,
            },
          },
          {
            job_type: "generate_publish_progress_report",
            description: "Publish progress report",
            input_schema: {
              required_fields: [],
              allowed_fields: [],
              field_types: {},
              allowed_values: {},
              supports_dry_run: false,
            },
          },
        ],
        intake_profiles: [
          {
            profile_id: "tx_2026_senate",
            label: "Texas 2026 U.S. Senate",
            state: "TX",
            office: "US Senate",
            election_cycle: 2026,
            race_stage: "primary",
            statement_batches: ["starter", "round2", "round3"],
          },
          {
            profile_id: "tx_2026_ag_runoff",
            label: "Texas 2026 Attorney General Runoff",
            state: "TX",
            office: "Attorney General",
            election_cycle: 2026,
            race_stage: "primary_runoff",
            statement_batches: ["starter"],
          },
        ],
      });
    }

    if (path === "/api/v1/admin/jobs" && method === "GET") {
      jobsGetCalls += 1;
      return json([
        {
          id: jobId,
          job_type: "generate_publish_queue_report",
          status: "succeeded",
          requested_by_reviewer_id: "admin@local",
          input_payload: { dry_run: false },
          started_at: "2026-05-12T00:00:00Z",
          finished_at: "2026-05-12T00:00:05Z",
          result_summary: { return_code: 0 },
          error_details: null,
          created_at: "2026-05-12T00:00:00Z",
          updated_at: "2026-05-12T00:00:05Z",
        },
      ]);
    }

    if (path === "/api/v1/admin/jobs" && method === "POST") {
      lastJobPayload = JSON.parse(req.postData() || "{}");
      return json({
        id: jobId,
        job_type: lastJobPayload.job_type || "generate_publish_queue_report",
        status: "succeeded",
        requested_by_reviewer_id: "admin@local",
        input_payload: lastJobPayload.input_payload || { dry_run: false },
        started_at: "2026-05-12T00:00:00Z",
        finished_at: "2026-05-12T00:00:05Z",
        result_summary: { return_code: 0 },
        error_details: null,
        created_at: "2026-05-12T00:00:00Z",
        updated_at: "2026-05-12T00:00:05Z",
      });
    }

    if (path === `/api/v1/admin/jobs/${jobId}` && method === "GET") {
      return json({
        id: jobId,
        job_type: "generate_publish_queue_report",
        status: "succeeded",
        requested_by_reviewer_id: "admin@local",
        input_payload: { dry_run: false },
        started_at: "2026-05-12T00:00:00Z",
        finished_at: "2026-05-12T00:00:05Z",
        result_summary: { return_code: 0 },
        error_details: null,
        created_at: "2026-05-12T00:00:00Z",
        updated_at: "2026-05-12T00:00:05Z",
      });
    }

    if (path === "/api/v1/admin/audit-events" && method === "GET") {
      auditGetCalls += 1;
      return json([
        {
          id: auditId,
          actor_reviewer_id: "admin@local",
          action: "candidate_updated",
          entity_type: "candidate",
          entity_id: candidateId,
          before_payload: { party: "Independent" },
          after_payload: { party: "Democratic" },
          metadata: { source: "api" },
          created_at: "2026-05-12T00:00:00Z",
          updated_at: "2026-05-12T00:00:00Z",
        },
      ]);
    }

    if (path === `/api/v1/admin/audit-events/${auditId}` && method === "GET") {
      return json({
        id: auditId,
        actor_reviewer_id: "admin@local",
        action: "candidate_updated",
        entity_type: "candidate",
        entity_id: candidateId,
        before_payload: { party: "Independent" },
        after_payload: { party: "Democratic" },
        metadata: { source: "api" },
        created_at: "2026-05-12T00:00:00Z",
        updated_at: "2026-05-12T00:00:00Z",
      });
    }

    return json({ error: { message: `No mock for ${method} ${path}` } }, 404);
    });

  await page.goto(`${baseUrl}/admin/`, { waitUntil: "networkidle" });

  await expect(page.locator("#auth-form")).toBeVisible();
  await page.fill("#auth-email", "admin@local");
  await page.fill("#auth-password", "change-me");
  await page.click("#auth-form button[type=\"submit\"]");
  await expect(page.locator("#admin-workspace")).toBeVisible();
  await expect(page.locator("#identity-label")).toContainText("admin@local");

  await expect(page.locator("#candidate-list .row-btn")).toHaveCount(1);

  await page.click("button[data-tab=\"review\"]");
  await expect(page.locator("#tab-review")).toBeVisible();
  await expect(page.locator("#review-list .row-btn")).toHaveCount(1);
  await page.click("#review-list .row-btn");
  await page.fill("#review-rationale", "Evidence supports the claim with caveats.");
  await page.click("#review-form button[type=\"submit\"]");
  await expect(page.locator("#review-submit-status")).toContainText("Evaluation saved");

  await page.click("button[data-tab=\"evidence\"]");
  await expect(page.locator("#tab-evidence")).toBeVisible();
  await expect(page.locator("#evidence-list .row-btn")).toHaveCount(1);
  await page.click("#evidence-list .row-btn");
  await expect(page.locator("#evidence-claim-id")).toHaveValue(claimId);
  await page.fill("#evidence-filter-state", "TX");
  await page.fill("#evidence-filter-office", "US Senate");
  await page.fill("#evidence-filter-cycle", "2026");
  await page.selectOption("#evidence-filter-stage", "primary");
  await page.fill("#evidence-filter-limit", "25");
  await page.click("#evidence-filter-form button[type=\"submit\"]");
  await expect(page.locator("#evidence-list-status")).toContainText("Loaded 1 queue items");
  expect(evidenceQueries.some((query) => query.includes("state=TX"))).toBeTruthy();
  expect(evidenceQueries.some((query) => query.includes("office=US+Senate"))).toBeTruthy();
  expect(evidenceQueries.some((query) => query.includes("election_cycle=2026"))).toBeTruthy();
  expect(evidenceQueries.some((query) => query.includes("race_stage=primary"))).toBeTruthy();
  expect(evidenceQueries.some((query) => query.includes("limit=25"))).toBeTruthy();

  await page.click("button[data-tab=\"bulk-sources\"]");
  await expect(page.locator("#tab-bulk-sources")).toBeVisible();
  await expect(page.locator("#bulk-attach-json")).toHaveValue(/claim_id/);
  await page.fill("#bulk-approval-reviewer-id", "approver@local");

  await page.fill("#bulk-attach-json", "{");
  await page.click("#bulk-validate-json");
  await expect(page.locator("#bulk-attach-status")).toContainText("not valid JSON");
  expect(bulkAttachPostCalls).toBe(0);

  await page.fill(
    "#bulk-attach-json",
    JSON.stringify(
      {
        approval_reviewer_id: "approver@local",
        items: [
          {
            claim_id: claimId,
            url: "https://example.gov/record",
            source_class: "tertiary",
            source_origin: "verification",
            quality_score: 0.7,
          },
        ],
      },
      null,
      2
    )
  );
  await page.click("#bulk-validate-json");
  await expect(page.locator("#bulk-attach-status")).toContainText("source_class must be one of");
  expect(bulkAttachPostCalls).toBe(0);

  const evidenceCallsBeforeBulkSubmit = evidenceGetCalls;
  const auditCallsBeforeBulkSubmit = auditGetCalls;
  await page.fill(
    "#bulk-attach-json",
    JSON.stringify(
      {
        approval_reviewer_id: "approver@local",
        items: [
          {
            claim_id: claimId,
            url: "https://example.gov/record",
            source_class: "primary",
            source_origin: "verification",
            publisher: "Example Government Office",
            quality_score: 0.9,
            is_direct_candidate_quote: false,
          },
          {
            claim_id: claimId,
            url: "https://invalid.example/dup",
            source_class: "secondary",
            source_origin: "verification",
            quality_score: 0.4,
          },
        ],
      },
      null,
      2
    )
  );
  await page.click("#bulk-attach-form button[type=\"submit\"]");
  await expect(page.locator("#bulk-attach-status")).toContainText("completed");
  await expect(page.locator("#bulk-attach-summary")).toContainText("Total: 2 | Attached: 1 | Failed: 1");
  await expect(page.locator("#bulk-attach-results .row-btn")).toHaveCount(2);
  expect(bulkAttachPostCalls).toBe(1);
  expect(lastBulkAttachPayload.approval_reviewer_id).toBe("approver@local");
  expect(Array.isArray(lastBulkAttachPayload.items)).toBeTruthy();
  expect(lastBulkAttachPayload.items.length).toBe(2);
  expect(evidenceGetCalls).toBeGreaterThan(evidenceCallsBeforeBulkSubmit);
  expect(auditGetCalls).toBeGreaterThan(auditCallsBeforeBulkSubmit);

  await page.click("button[data-tab=\"proposals\"]");
  await expect(page.locator("#tab-proposals")).toBeVisible();
  await expect(page.locator("#proposal-list .row-btn")).toHaveCount(2);
  await page.locator("#proposal-list .row-btn").first().click();
  await expect(page.locator("#proposal-power-admin-status")).toContainText("Power-admin source/bundle review");
  await expect(page.locator("#proposal-power-admin-items li")).toHaveCount(5);
  await expect(page.locator("#proposal-power-admin-items")).toContainText("source_origin recorded: verification");
  await expect(page.locator("#proposal-power-admin-items")).toContainText(
    "source_origin matches proposal type (verification)"
  );
  await expect(page.locator("#proposal-power-admin-items")).toContainText("source_class recorded: primary");
  await expect(page.locator("#proposal-power-admin-items")).toContainText("publisher recorded: Example Government Office");
  await expect(page.locator("#proposal-power-admin-items")).toContainText("quality_score recorded: 0.91");
  await expect(page.locator("#proposal-claim-context")).toBeVisible();
  await expect(page.locator("#proposal-claim-context-status")).toContainText("currently missing required class coverage");
  await expect(page.locator("#proposal-claim-context-evidence li")).toHaveCount(4);
  await expect(page.locator("#proposal-claim-context-evidence")).toContainText("verification primary count: 1");
  await expect(page.locator("#proposal-claim-context-evidence")).toContainText("verification secondary count: 0");
  await expect(page.locator("#proposal-claim-context-evidence")).toContainText("missing source classes: secondary");
  await expect(page.locator("#proposal-claim-context-evidence")).toContainText("evidence sufficiency gate: blocked");
  await expect(page.locator("#proposal-claim-context-evaluation li")).toHaveCount(6);
  await expect(page.locator("#proposal-claim-context-evaluation")).toContainText("latest verdict: mixed");
  await expect(page.locator("#proposal-claim-context-evaluation")).toContainText("latest confidence: 0.62");
  await expect(page.locator("#proposal-claim-context-evaluation")).toContainText("latest reviewer: reviewer@local");
  await expect(page.locator("#proposal-claim-context-evaluation")).toContainText("latest evaluated at:");
  await expect(page.locator("#proposal-claim-context-evaluation")).toContainText(
    "latest rationale: Prior evidence exists"
  );
  await expect(page.locator("#proposal-claim-context-evaluation")).toContainText("latest citation notes: Source packet A");
  await page.locator("#proposal-list .row-btn").nth(1).click();
  await expect(page.locator("#proposal-detail-json")).toContainText("candidate_source_capture");
  await expect(page.locator("#proposal-power-admin-items li")).toHaveCount(5);
  await expect(page.locator("#proposal-power-admin-items")).toContainText("source_origin recorded: verification");
  await expect(page.locator("#proposal-power-admin-items")).toContainText(
    "source_origin matches proposal type (candidate)"
  );
  await expect(page.locator("#proposal-power-admin-items")).toContainText("source_class recorded: primary");
  await expect(page.locator("#proposal-power-admin-items")).toContainText("publisher recorded: Candidate One Campaign");
  await expect(page.locator("#proposal-power-admin-items")).toContainText("quality_score recorded: 0.73");
  await page.locator("#proposal-list .row-btn").first().click();
  await page.selectOption("#proposal-action", "approve");
  await page.fill("#proposal-review-notes", "Looks valid");
  await page.click("#proposal-action-form button[type=\"submit\"]");
  await expect(page.locator("#proposal-action-status")).toContainText("Proposal action saved");

  await page.click("button[data-tab=\"publish\"]");
  await expect(page.locator("#tab-publish")).toBeVisible();
  await expect(page.locator("#publish-list .row-btn")).toHaveCount(1);
  await page.click("#publish-list .row-btn");
  await page.selectOption("#publish-action", "publish");
  await page.click("#publish-action-form button[type=\"submit\"]");
  await expect(page.locator("#publish-action-status")).toContainText("completed");

  await page.click("button[data-tab=\"jobs\"]");
  await expect(page.locator("#tab-jobs")).toBeVisible();
  await expect(page.locator("#job-type")).toHaveValue("ingest_candidate_roster");
  await expect(page.locator("#job-profile-field")).toBeVisible();
  await expect(page.locator("#job-input-payload")).toHaveValue(/"profile_id": "tx_2026_senate"/);
  await page.selectOption("#job-type", "ingest_statement_batch");
  await expect(page.locator("#job-type")).toHaveValue("ingest_statement_batch");
  await expect(page.locator("#job-statement-batch-field")).toBeVisible();
  await expect(page.locator("#job-input-payload")).toHaveValue(/"statement_batch": "starter"/);
  await page.selectOption("#job-profile-id", "tx_2026_senate");
  await page.selectOption("#job-statement-batch", "round3");
  await expect(page.locator("#job-input-payload")).toHaveValue(/"statement_batch": "round3"/);
  await page.fill("#job-input-payload", JSON.stringify({ profile_id: "tx_2026_senate" }, null, 2));
  await page.click("#job-create-form button[type=\"submit\"]");
  await expect(page.locator("#job-create-status")).toContainText("missing required fields");
  expect(lastJobPayload).toBeNull();
  await page.fill(
    "#job-input-payload",
    JSON.stringify({ profile_id: "tx_2026_senate", statement_batch: "round3" }, null, 2)
  );
  const jobsGetCallsBeforeRun = jobsGetCalls;
  const auditGetCallsBeforeRun = auditGetCalls;
  await page.click("#job-create-form button[type=\"submit\"]");
  await expect(page.locator("#job-create-status")).toContainText("Job finished with status succeeded");
  expect(lastJobPayload.job_type).toBe("ingest_statement_batch");
  expect(lastJobPayload.input_payload.profile_id).toBe("tx_2026_senate");
  expect(lastJobPayload.input_payload.statement_batch).toBe("round3");
  expect(jobsGetCalls).toBeGreaterThan(jobsGetCallsBeforeRun);
  expect(auditGetCalls).toBeGreaterThan(auditGetCallsBeforeRun);

  await page.click("button[data-tab=\"audit\"]");
  await expect(page.locator("#tab-audit")).toBeVisible();
  await expect(page.locator("#audit-list .row-btn")).toHaveCount(1);
  await page.click("#audit-list .row-btn");
    await expect(page.locator("#audit-detail-json")).toContainText("candidate_updated");
  } finally {
    if (localServer?.server) {
      await new Promise((resolve) => localServer.server.close(resolve));
    }
  }
});
