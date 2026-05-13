const { test, expect } = require("@playwright/test");
const fs = require("fs");
const http = require("http");
const path = require("path");

function contentTypeFor(filePath) {
  if (filePath.endsWith(".html")) return "text/html; charset=utf-8";
  if (filePath.endsWith(".js")) return "application/javascript; charset=utf-8";
  if (filePath.endsWith(".css")) return "text/css; charset=utf-8";
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
  return { server, baseUrl: `http://127.0.0.1:${server.address().port}` };
}

async function signIn(page, baseUrl) {
  await page.goto(`${baseUrl}/admin/`, { waitUntil: "networkidle" });
  await page.fill("#auth-email", "admin@local");
  await page.fill("#auth-password", "change-me");
  await page.click("#auth-form button[type='submit']");
  await expect(page.locator("#admin-workspace")).toBeVisible();
  await page.click("button[data-tab='publish']");
  await expect(page.locator("#tab-publish")).toBeVisible();
}

async function registerBaseRoutes(page, handlers) {
  return page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const method = req.method();
    const url = new URL(req.url());
    const endpoint = `${method} ${url.pathname}`;
    const json = (body, status = 200) =>
      route.fulfill({ status, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

    if (handlers[endpoint]) return handlers[endpoint](route, req, url, json);
    if (endpoint === "POST /api/v1/auth/login") return json({ access_token: "token", token_type: "bearer", reviewer_id: "admin@local", role: "admin" });
    if (endpoint === "GET /api/v1/auth/me") return json({ reviewer_id: "admin@local", role: "admin" });
    if (endpoint === "GET /api/v1/candidates") return json([]);
    if (endpoint === "GET /api/v1/claims/review-queue") return json([]);
    if (endpoint === "GET /api/v1/claims/evidence-queue") return json([]);
    if (endpoint === "GET /api/v1/claims/proposals") return json([]);
    if (endpoint === "GET /api/v1/admin/jobs/metadata") return json({ allowlist_version: "v1", intake_profile_version: "v1", synchronous_execution: true, jobs: [], intake_profiles: [] });
    if (endpoint === "GET /api/v1/admin/jobs") return json([]);
    if (endpoint === "GET /api/v1/admin/audit-events") return json([]);
    return json({ error: { message: `No mock for ${endpoint}` } }, 404);
  });
}

test("publish queue load failure shows error state", async ({ page }) => {
  const localServer = await startFrontendStaticServer(path.resolve(__dirname, "../frontend"));
  try {
    await registerBaseRoutes(page, {
      "GET /api/v1/claims/publish-queue": (_route, _req, _url, json) =>
        json({ error: { message: "Publish queue unavailable" } }, 500),
    });
    await signIn(page, localServer.baseUrl);
    await expect(page.locator("#publish-list-status")).toContainText("Publish queue unavailable");
    await expect(page.locator("#publish-list .row-btn")).toHaveCount(0);
  } finally {
    await new Promise((resolve) => localServer.server.close(resolve));
  }
});

test("publish action blocks stale selected claim", async ({ page }) => {
  const localServer = await startFrontendStaticServer(path.resolve(__dirname, "../frontend"));
  const claimId = "55555555-5555-5555-5555-555555555555";
  let publishQueueCalls = 0;
  let publishPostCalls = 0;
  try {
    await registerBaseRoutes(page, {
      "GET /api/v1/claims/publish-queue": (_route, _req, _url, json) => {
        publishQueueCalls += 1;
        if (publishQueueCalls === 1) {
          return json([
            {
              claim_id: claimId, claim_text: "Claim", issue_tag: "issue", candidate_name: "Candidate", candidate_party: "Independent",
              statement_source_url: "https://example.org", statement_published_at: "2026-05-12T00:00:00Z",
              latest_verdict: "supported", latest_confidence: 0.9, latest_rationale: "R", latest_citation_notes: "C", latest_reviewer_id: "admin@local",
              primary_source_count: 1, secondary_source_count: 1, verification_primary_count: 1, verification_secondary_count: 1,
              publish_gate_passed: true, publish_gate_failures: [], is_published: false, published_at: null, published_by_reviewer_id: null,
            },
          ]);
        }
        return json([]);
      },
      "POST /api/v1/claims/55555555-5555-5555-5555-555555555555/publish": (_route, _req, _url, json) => {
        publishPostCalls += 1;
        return json({ claim_id: claimId, is_published: true, published_at: "2026-05-12T00:00:00Z", published_by_reviewer_id: "admin@local" });
      },
    });
    await signIn(page, localServer.baseUrl);
    await page.click("#publish-list .row-btn");
    await page.click("#publish-refresh");
    await expect(page.locator("#publish-list-status")).toContainText("Loaded 0 publish queue claims.");
    await expect(page.locator("#publish-list")).toContainText("No claims found for publish controls with current filters.");
    await page.evaluate((id) => {
      const input = document.getElementById("publish-claim-id");
      if (input) input.value = id;
    }, claimId);
    await page.evaluate(() => {
      const select = document.getElementById("publish-action");
      if (select) select.value = "publish";
    });
    await expect(page.locator("#publish-claim-id")).toHaveValue(claimId);
    await page.click("#publish-action-form button[type='submit']");
    await expect(page.locator("#publish-action-status")).toContainText(
      "Selected claim is not in the current publish queue. Refresh and reselect."
    );
    expect(publishPostCalls).toBe(0);
  } finally {
    await new Promise((resolve) => localServer.server.close(resolve));
  }
});

test("publish checklist hard-block prevents publish POST", async ({ page }) => {
  const localServer = await startFrontendStaticServer(path.resolve(__dirname, "../frontend"));
  const claimId = "55555555-5555-5555-5555-555555555555";
  let publishPostCalls = 0;
  try {
    await registerBaseRoutes(page, {
      "GET /api/v1/claims/publish-queue": (_route, _req, _url, json) =>
        json([
          {
            claim_id: claimId, claim_text: "Claim", issue_tag: "issue", candidate_name: "Candidate", candidate_party: "Independent",
            statement_source_url: "https://example.org", statement_published_at: "2026-05-12T00:00:00Z",
            latest_verdict: "supported", latest_confidence: 0.9, latest_rationale: "R", latest_citation_notes: "C", latest_reviewer_id: "admin@local",
            primary_source_count: 1, secondary_source_count: 0, verification_primary_count: 1, verification_secondary_count: 0,
            publish_gate_passed: false, publish_gate_failures: ["verification_secondary_source_required"],
            is_published: false, published_at: null, published_by_reviewer_id: null,
          },
        ]),
      "POST /api/v1/claims/55555555-5555-5555-5555-555555555555/publish": (_route, _req, _url, json) => {
        publishPostCalls += 1;
        return json({ claim_id: claimId, is_published: true, published_at: "2026-05-12T00:00:00Z", published_by_reviewer_id: "admin@local" });
      },
    });
    await signIn(page, localServer.baseUrl);
    await page.click("#publish-list .row-btn");
    await expect(page.locator("#publish-list")).toContainText("gate blocked (verification_secondary_source_required)");
    await expect(page.locator("#publish-checklist-status")).toContainText("Checklist incomplete");
    const checklistItems = page.locator("#publish-checklist-items li");
    await expect(checklistItems).toHaveCount(6);
    await expect(page.locator("#publish-checklist-items")).toContainText("Rationale present and review-ready");
    await expect(page.locator("#publish-checklist-items")).toContainText("Citation notes present");
    await expect(page.locator("#publish-checklist-items")).toContainText("Verification primary source attached");
    await expect(page.locator("#publish-checklist-items")).toContainText("Verification secondary source attached");
    await expect(page.locator("#publish-checklist-items")).toContainText("Moderation policy clean");
    await expect(page.locator("#publish-checklist-items")).toContainText("Publish gate passed");
    await expect(page.locator("#publish-action-form button[type='submit']")).toBeDisabled();
    await page.click("#publish-action-form button[type='submit']", { force: true });
    expect(publishPostCalls).toBe(0);
  } finally {
    await new Promise((resolve) => localServer.server.close(resolve));
  }
});

test("publish action surfaces dual-control 409 and does not retry", async ({ page }) => {
  const localServer = await startFrontendStaticServer(path.resolve(__dirname, "../frontend"));
  const claimId = "55555555-5555-5555-5555-555555555555";
  let publishPostCalls = 0;
  try {
    await registerBaseRoutes(page, {
      "GET /api/v1/claims/publish-queue": (_route, _req, _url, json) =>
        json([
          {
            claim_id: claimId, claim_text: "Claim", issue_tag: "issue", candidate_name: "Candidate", candidate_party: "Independent",
            statement_source_url: "https://example.org", statement_published_at: "2026-05-12T00:00:00Z",
            latest_verdict: "supported", latest_confidence: 0.9, latest_rationale: "R", latest_citation_notes: "C", latest_reviewer_id: "admin@local",
            primary_source_count: 1, secondary_source_count: 1, verification_primary_count: 1, verification_secondary_count: 1,
            publish_gate_passed: true, publish_gate_failures: [], is_published: false, published_at: null, published_by_reviewer_id: null,
          },
        ]),
      "POST /api/v1/claims/55555555-5555-5555-5555-555555555555/publish": (_route, _req, _url, json) => {
        publishPostCalls += 1;
        return json(
          {
            error: {
              code: "publish_dual_control_required",
              message: "Publish and unpublish actions require different reviewers for approval and final mutation.",
              details: {
                claim_id: claimId,
                approval_reviewer_id: "admin@local",
                applying_reviewer_id: "admin@local",
                action: "publish",
              },
            },
          },
          409
        );
      },
    });
    await signIn(page, localServer.baseUrl);
    await page.click("#publish-list .row-btn");
    await expect(page.locator("#publish-checklist-status")).toContainText("Checklist complete");
    await page.selectOption("#publish-action", "publish");
    await page.click("#publish-action-form button[type='submit']");
    await expect(page.locator("#publish-action-status")).toContainText("Dual-control blocked for publish");
    expect(publishPostCalls).toBe(1);
  } finally {
    await new Promise((resolve) => localServer.server.close(resolve));
  }
});

test("candidate update surfaces dual-control 409 and does not retry", async ({ page }) => {
  const localServer = await startFrontendStaticServer(path.resolve(__dirname, "../frontend"));
  const candidateId = "11111111-1111-1111-1111-111111111111";
  let patchCalls = 0;
  try {
    await registerBaseRoutes(page, {
      "GET /api/v1/candidates": (_route, _req, _url, json) =>
        json([
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
        ]),
      "GET /api/v1/candidates/11111111-1111-1111-1111-111111111111": (_route, _req, _url, json) =>
        json({
          id: candidateId,
          name: "Candidate One",
          party: "Independent",
          office: "US Senate",
          state: "TX",
          election_cycle: 2026,
          race_stage: "primary",
          is_active: true,
          roster_status: null,
          roster_source_url: null,
          roster_checked_at: null,
          roster_notes: null,
          created_at: "2026-05-12T00:00:00Z",
        }),
      "PATCH /api/v1/candidates/11111111-1111-1111-1111-111111111111": (_route, _req, _url, json) => {
        patchCalls += 1;
        return json(
          {
            error: {
              code: "candidate_dual_control_required",
              message: "Candidate mutations require different reviewers for approval and final mutation.",
              details: {
                candidate_id: candidateId,
                approval_reviewer_id: "admin@local",
                applying_reviewer_id: "admin@local",
                action: "candidate_update",
              },
            },
          },
          409
        );
      },
    });
    await signIn(page, localServer.baseUrl);
    await page.click("button[data-tab='candidates']");
    await page.click("#candidate-list .row-btn");
    await expect(page.locator("#candidate-edit-status")).toContainText("Loaded Candidate One.");
    await page.fill("#candidate-approval-token", "approval-token-1");
    await page.fill("#candidate-party", "Democratic");
    await page.click("#candidate-edit-form button[type='submit']");
    await expect(page.locator("#candidate-edit-status")).toContainText("Dual-control blocked for candidate_update");
    expect(patchCalls).toBe(1);
  } finally {
    await new Promise((resolve) => localServer.server.close(resolve));
  }
});

test("evaluation overwrite surfaces dual-control 409 and does not retry", async ({ page }) => {
  const localServer = await startFrontendStaticServer(path.resolve(__dirname, "../frontend"));
  const claimId = "55555555-5555-5555-5555-555555555555";
  let evaluatePostCalls = 0;
  try {
    await registerBaseRoutes(page, {
      "GET /api/v1/claims/review-queue": (_route, _req, _url, json) =>
        json([
          {
            claim_id: claimId,
            claim_text: "Claim",
            issue_tag: "issue",
            status: "reviewed",
            statement_source_url: "https://example.org",
            statement_published_at: "2026-05-12T00:00:00Z",
            candidate_id: "11111111-1111-1111-1111-111111111111",
            candidate_name: "Candidate",
            candidate_party: "Independent",
            candidate_office: "US Senate",
            candidate_state: "TX",
            election_cycle: 2026,
            race_stage: "primary",
            primary_source_count: 1,
            secondary_source_count: 1,
            candidate_source_count: 0,
            verification_source_count: 2,
            latest_verdict: "mixed",
            latest_confidence: 0.6,
            latest_rationale: "R",
            latest_citation_notes: "C",
            latest_reviewer_id: "reviewer@local",
            latest_evaluated_at: "2026-05-12T00:00:00Z",
            warnings: [],
          },
        ]),
      "POST /api/v1/claims/55555555-5555-5555-5555-555555555555/evaluate": (_route, _req, _url, json) => {
        evaluatePostCalls += 1;
        return json(
          {
            error: {
              code: "evaluation_overwrite_dual_control_required",
              message: "Evaluation overwrites require different reviewers for approval and final mutation.",
              details: {
                claim_id: claimId,
                approval_reviewer_id: "admin@local",
                applying_reviewer_id: "admin@local",
                action: "evaluate_overwrite",
              },
            },
          },
          409
        );
      },
    });
    await signIn(page, localServer.baseUrl);
    await page.click("button[data-tab='review']");
    await page.click("#review-list .row-btn");
    await page.fill("#review-approval-token", "approval-token-2");
    await page.fill("#review-rationale", "Neutral rationale with enough detail.");
    await page.click("#review-form button[type='submit']");
    await expect(page.locator("#review-submit-status")).toContainText("Dual-control blocked for evaluate_overwrite");
    expect(evaluatePostCalls).toBe(1);
  } finally {
    await new Promise((resolve) => localServer.server.close(resolve));
  }
});

test("evaluation first-write succeeds without approval reviewer", async ({ page }) => {
  const localServer = await startFrontendStaticServer(path.resolve(__dirname, "../frontend"));
  const claimId = "55555555-5555-5555-5555-555555555555";
  let evaluatePostCalls = 0;
  let postedApprovalToken = "unexpected";
  try {
    await registerBaseRoutes(page, {
      "GET /api/v1/claims/review-queue": (_route, _req, _url, json) =>
        json([
          {
            claim_id: claimId,
            claim_text: "Claim",
            issue_tag: "issue",
            status: "draft",
            statement_source_url: "https://example.org",
            statement_published_at: "2026-05-12T00:00:00Z",
            candidate_id: "11111111-1111-1111-1111-111111111111",
            candidate_name: "Candidate",
            candidate_party: "Independent",
            candidate_office: "US Senate",
            candidate_state: "TX",
            election_cycle: 2026,
            race_stage: "primary",
            primary_source_count: 1,
            secondary_source_count: 1,
            candidate_source_count: 0,
            verification_source_count: 2,
            latest_verdict: null,
            latest_confidence: null,
            latest_rationale: null,
            latest_citation_notes: null,
            latest_reviewer_id: null,
            latest_evaluated_at: null,
            warnings: [],
          },
        ]),
      "POST /api/v1/claims/55555555-5555-5555-5555-555555555555/evaluate": (_route, req, _url, json) => {
        evaluatePostCalls += 1;
        const body = JSON.parse(req.postData() || "{}");
        postedApprovalToken = body.approval_token;
        return json({
          id: "88888888-8888-8888-8888-888888888888",
          claim_id: claimId,
          verdict: body.verdict || "supported",
          confidence: body.confidence || 0.8,
          rationale: body.rationale || "Neutral rationale with enough detail.",
          citation_notes: body.citation_notes || null,
          reviewer_id: "admin@local",
          created_at: "2026-05-12T00:00:00Z",
        });
      },
    });
    await signIn(page, localServer.baseUrl);
    await page.click("button[data-tab='review']");
    await page.click("#review-list .row-btn");
    await page.fill("#review-rationale", "Neutral rationale with enough detail.");
    await page.click("#review-form button[type='submit']");
    await expect(page.locator("#review-submit-status")).toContainText("Evaluation saved");
    expect(evaluatePostCalls).toBe(1);
    expect(postedApprovalToken).toBeNull();
  } finally {
    await new Promise((resolve) => localServer.server.close(resolve));
  }
});

test("bulk attach surfaces dual-control 409 and does not retry", async ({ page }) => {
  const localServer = await startFrontendStaticServer(path.resolve(__dirname, "../frontend"));
  const claimId = "55555555-5555-5555-5555-555555555555";
  let bulkPostCalls = 0;
  try {
    await registerBaseRoutes(page, {
      "POST /api/v1/claims/sources/bulk": (_route, _req, _url, json) => {
        bulkPostCalls += 1;
        return json(
          {
            error: {
              code: "bulk_attach_dual_control_required",
              message: "Verification-source bulk attach operations require different reviewers for approval and final mutation.",
              details: {
                bulk_operation_id: "bulk-op-1",
                approval_reviewer_id: "admin@local",
                applying_reviewer_id: "admin@local",
                action: "bulk_attach_verification_sources",
              },
            },
          },
          409
        );
      },
    });
    await signIn(page, localServer.baseUrl);
    await page.click("button[data-tab='bulk-sources']");
    await page.fill("#bulk-approval-token", "approval-token-3");
    await page.fill(
      "#bulk-attach-json",
      JSON.stringify(
        {
          approval_token: "approval-token-3",
          items: [
            {
              claim_id: claimId,
              url: "https://example.gov/record",
              source_class: "primary",
              source_origin: "verification",
              quality_score: 0.95,
            },
          ],
        },
        null,
        2
      )
    );
    await page.click("#bulk-attach-form button[type='submit']");
    await expect(page.locator("#bulk-attach-status")).toContainText(
      "Dual-control blocked for bulk_attach_verification_sources"
    );
    expect(bulkPostCalls).toBe(1);
  } finally {
    await new Promise((resolve) => localServer.server.close(resolve));
  }
});
