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

function registerBaseRoutes(page, handlers) {
  return page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const method = req.method();
    const url = new URL(req.url());
    const endpoint = `${method} ${url.pathname}`;
    const json = (body, status = 200) =>
      route.fulfill({ status, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

    if (endpoint === "POST /api/v1/auth/login") return json({ access_token: "token", token_type: "bearer", reviewer_id: "admin@local", role: "admin" });
    if (endpoint === "GET /api/v1/auth/me") return json({ reviewer_id: "admin@local", role: "admin" });
    if (endpoint === "GET /api/v1/candidates") return json([]);
    if (endpoint === "GET /api/v1/claims/review-queue") return json([]);
    if (endpoint === "GET /api/v1/claims/evidence-queue") return json([]);
    if (endpoint === "GET /api/v1/claims/proposals") return json([]);
    if (endpoint === "GET /api/v1/admin/jobs/metadata") return json({ allowlist_version: "v1", intake_profile_version: "v1", synchronous_execution: true, jobs: [], intake_profiles: [] });
    if (endpoint === "GET /api/v1/admin/jobs") return json([]);
    if (endpoint === "GET /api/v1/admin/audit-events") return json([]);
    if (handlers[endpoint]) return handlers[endpoint](route, req, url, json);
    return json({ error: { message: `No mock for ${endpoint}` } }, 404);
  });
}

test("publish queue load failure shows error state", async ({ page }) => {
  const localServer = await startFrontendStaticServer(path.resolve(__dirname, "../frontend"));
  try {
    registerBaseRoutes(page, {
      "GET /api/v1/claims/publish-queue": (_route, _req, _url, json) =>
        json({ error: { message: "Publish queue unavailable" } }, 500),
    });
    await signIn(page, localServer.baseUrl);
    await expect(page.locator("#publish-list-status")).toContainText("Publish queue unavailable");
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
    registerBaseRoutes(page, {
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
    registerBaseRoutes(page, {
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
    await expect(page.locator("#publish-checklist-status")).toContainText("Checklist incomplete");
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
    registerBaseRoutes(page, {
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
    await page.selectOption("#publish-action", "publish");
    await page.click("#publish-action-form button[type='submit']");
    await expect(page.locator("#publish-action-status")).toContainText("Dual-control blocked for publish");
    expect(publishPostCalls).toBe(1);
  } finally {
    await new Promise((resolve) => localServer.server.close(resolve));
  }
});
