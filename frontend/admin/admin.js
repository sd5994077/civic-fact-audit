const API_AUTH_LOGIN_URL = "/api/v1/auth/login";
const API_AUTH_ME_URL = "/api/v1/auth/me";
const API_AUTH_APPROVAL_TOKEN_URL = "/api/v1/auth/dual-control-approval-token";
const API_CANDIDATES_URL = "/api/v1/candidates";
const API_ADMIN_INTAKE_PROFILES_URL = "/api/v1/admin/intake-profiles";
const API_ADMIN_JOBS_URL = "/api/v1/admin/jobs";
const API_ADMIN_JOB_METADATA_URL = "/api/v1/admin/jobs/metadata";
const API_ADMIN_AUDIT_URL = "/api/v1/admin/audit-events";
const API_REVIEW_QUEUE_URL = "/api/v1/claims/review-queue";
const API_EVIDENCE_QUEUE_URL = "/api/v1/claims/evidence-queue";
const API_WORKBENCH_URL = "/api/v1/claims/workbench";
const API_EVALUATE_BASE_URL = "/api/v1/claims";
const API_PROPOSALS_URL = "/api/v1/claims/proposals";
const API_PUBLISH_QUEUE_URL = "/api/v1/claims/publish-queue";
const API_BULK_SOURCE_ATTACH_URL = "/api/v1/claims/sources/bulk";
const API_WORKER_HEALTH_URL = "/api/v1/admin/jobs/worker-health";
const AUTH_STORAGE_KEY = "cfa_admin_token";

let authToken = localStorage.getItem(AUTH_STORAGE_KEY) || "";
let identity = null;
let _healthRefreshTimer = null;
let selectedCandidateId = "";
let selectedJobId = "";
let selectedAuditId = "";
let selectedReviewClaimId = "";
let selectedEvidenceClaimId = "";
let selectedWorkbenchClaimId = "";
let selectedProposalId = "";
let selectedPublishClaimId = "";
let selectedWorkbenchSources = [];
let selectedWorkbenchRecommendations = [];
let reviewQueueRows = [];
let evidenceQueueRows = [];
let workbenchRows = [];
let proposalRows = [];
let publishQueueRows = [];
let selectedIntakeProfileId = "";
let intakeProfilesVersion = "";
let intakeProfilesRows = [];
let adminJobMetadata = null;
const ADMIN_ONLY_TABS = new Set(["candidates", "intake-profiles", "bulk-sources", "jobs", "audit"]);

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text ?? "");
  return div.innerHTML;
}

function setStatus(id, message, tone = "") {
  const el = $(id);
  if (!el) return;
  el.textContent = message || "";
  el.classList.remove("status-ok", "status-bad");
  if (tone === "ok") el.classList.add("status-ok");
  if (tone === "bad") el.classList.add("status-bad");
}

function formatDateTime(iso) {
  if (!iso) return "";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return String(iso);
  return dt.toLocaleString();
}

function toInputDatetimeValue(iso) {
  if (!iso) return "";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

function fromInputDatetimeValue(value) {
  if (!value) return null;
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return null;
  return dt.toISOString();
}

function normalizeOptionalText(value) {
  const text = String(value || "").trim();
  return text ? text : null;
}

function normalizeOptionalInt(value) {
  if (value === "" || value == null) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return Math.trunc(parsed);
}

const RACE_STAGE_VALUES = new Set(["primary", "primary_runoff", "general", "special"]);
const SOURCE_CLASS_VALUES = new Set(["primary", "secondary"]);
const SOURCE_ORIGIN_VALUES = new Set(["candidate", "verification"]);
const SOURCE_PROPOSAL_TYPES = new Set(["candidate_source_capture", "verification_source_suggestion"]);
const WORKBENCH_STATE_ORDER = [
  "Needs Evidence",
  "Needs Review",
  "Needs Second Reviewer",
  "Ready to Publish",
  "Published",
  "Insufficient Evidence",
];
const BULK_ATTACH_EXAMPLE = {
  approval_token: "paste-approval-token-here",
  items: [
    {
      claim_id: "00000000-0000-0000-0000-000000000000",
      url: "https://example.gov/report",
      source_class: "primary",
      source_origin: "verification",
      publisher: "Example Government Office",
      quality_score: 0.9,
      is_direct_candidate_quote: false,
    },
  ],
};

function shortId(id) {
  const text = String(id || "");
  if (text.length <= 10) return text;
  return `${text.slice(0, 10)}...`;
}

function verdictClass(verdict) {
  if (verdict === "supported") return "row-tone-ok";
  if (verdict === "mixed") return "row-tone-mixed";
  if (verdict === "unsupported") return "row-tone-bad";
  if (verdict === "insufficient") return "row-tone-low";
  return "row-tone-low";
}

function parseApiError(err, fallback) {
  if (!err) return fallback;
  const payloadMessage = err?.payload?.error?.message;
  if (payloadMessage) return payloadMessage;
  return err.message || fallback;
}

function parseDualControlError(err, expectedCode, defaultAction, defaultMessage) {
  const code = err?.payload?.error?.code;
  if (code !== expectedCode) return null;
  const details = err?.payload?.error?.details || {};
  const approvalReviewerId = details.approval_reviewer_id;
  const applyingReviewerId = details.applying_reviewer_id;
  const dualControlAction = details.action || defaultAction || "mutation";
  const approvalLabel = approvalReviewerId ? `latest approval reviewer is ${approvalReviewerId}` : "approval reviewer could not be resolved";
  const applyingLabel = applyingReviewerId ? `current actor is ${applyingReviewerId}` : "current actor is unknown";
  return `${defaultMessage} for ${dualControlAction}: ${approvalLabel}; ${applyingLabel}. Hand off to a different reviewer/admin and retry.`;
}

function parsePublishDualControlError(err, action) {
  return parseDualControlError(err, "publish_dual_control_required", action || "publish", "Dual-control blocked");
}

function parseCandidateDualControlError(err, action) {
  return parseDualControlError(err, "candidate_dual_control_required", action || "candidate_update", "Dual-control blocked");
}

function parseIntakeProfileDualControlError(err, action) {
  return parseDualControlError(err, "intake_profile_dual_control_required", action || "intake_profile_update", "Dual-control blocked");
}

function parseEvaluationDualControlError(err) {
  return parseDualControlError(
    err,
    "evaluation_overwrite_dual_control_required",
    "evaluate_overwrite",
    "Dual-control blocked"
  );
}

function parseBulkAttachDualControlError(err) {
  return parseDualControlError(
    err,
    "bulk_attach_dual_control_required",
    "bulk_attach_verification_sources",
    "Dual-control blocked"
  );
}

function isUuid(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(value || "").trim());
}

function isHttpUrl(value) {
  try {
    const parsed = new URL(String(value || "").trim());
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch (_err) {
    return false;
  }
}

async function apiRequest(path, { method = "GET", body = null, requireAuth = true } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== null) headers["Content-Type"] = "application/json";
  if (requireAuth && authToken) headers.Authorization = `Bearer ${authToken}`;

  const response = await fetch(path, {
    method,
    headers,
    body: body !== null ? JSON.stringify(body) : undefined,
  });

  let payload = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    payload = await response.json();
  }

  if (!response.ok) {
    const message = payload?.error?.message || `${method} ${path} failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

function showWorkspace(show) {
  const workspace = $("admin-workspace");
  if (workspace) workspace.hidden = !show;
}

function showSignedInControls(show) {
  const authForm = $("auth-form");
  const approvalPanel = $("approval-panel");
  if (authForm) authForm.hidden = show;
  if (approvalPanel) approvalPanel.hidden = !show;
}

function syncWorkbenchPublishVisibility() {
  const publishForm = $("workbench-publish-form");
  if (publishForm) {
    publishForm.hidden = !isAdminIdentity();
  }
  if (!isAdminIdentity()) {
    setStatus("workbench-publish-status", "Publish actions are admin-only. Reviewers can complete evidence and evaluation steps.");
    return;
  }
  if (($("workbench-publish-status")?.textContent || "").includes("admin-only")) {
    setStatus("workbench-publish-status", "");
  }
}

function clearSession() {
  authToken = "";
  identity = null;
  stopWorkerHealthAutoRefresh();
  localStorage.removeItem(AUTH_STORAGE_KEY);
  showSignedInControls(false);
  showWorkspace(false);
  const approvalReviewerId = $("approval-reviewer-id");
  if (approvalReviewerId) approvalReviewerId.value = "";
  const approvalExpiresAt = $("approval-expires-at");
  if (approvalExpiresAt) approvalExpiresAt.value = "";
  const approvalTokenValue = $("approval-token-value");
  if (approvalTokenValue) approvalTokenValue.value = "";
  setTabVisibilityForRole("admin");
  syncWorkbenchPublishVisibility();
  setStatus("approval-token-status", "");
  setStatus("auth-status", "Signed out.");
}

function setTabVisibilityForRole(role) {
  const isAdmin = role === "admin";
  const tabs = Array.from(document.querySelectorAll(".tab"));
  tabs.forEach((tab) => {
    const tabName = tab.dataset.tab || "";
    tab.hidden = !isAdmin && ADMIN_ONLY_TABS.has(tabName);
  });
}

function getWorkspaceLoadersForRole(role) {
  const sharedLoaders = [loadWorkbench, loadReviewQueue, loadEvidenceQueue, loadProposalList, loadPublishQueue];
  if (role === "admin") {
    return [loadCandidateList, loadIntakeProfiles, ...sharedLoaders, loadJobsList, loadAuditList];
  }
  return sharedLoaders;
}

async function verifyAdminIdentity() {
  if (!authToken) return false;
  const me = await apiRequest(API_AUTH_ME_URL, { requireAuth: true });
  identity = me;
  setTabVisibilityForRole(me?.role || "reviewer");
  syncWorkbenchPublishVisibility();
  showSignedInControls(true);
  const label = $("identity-label");
  const role = $("identity-role");
  if (label) label.textContent = `Signed in as ${me?.reviewer_id || "reviewer"}`;
  if (role) role.textContent = me?.role || "unknown";
  showWorkspace(true);
  const activeTab = document.querySelector(".tab.is-active");
  if (!activeTab || activeTab.hidden) {
    const firstVisibleTab = document.querySelector(".tab:not([hidden])");
    if (firstVisibleTab) {
      setActiveTab(firstVisibleTab.dataset.tab || "workbench");
    }
  }
  return true;
}

async function copyApprovalToken() {
  const token = $("approval-token-value")?.value.trim() || "";
  if (!token) {
    setStatus("approval-token-status", "No approval token is available to copy.", "bad");
    return;
  }

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(token);
    } else {
      const field = $("approval-token-value");
      if (field) {
        field.select();
        document.execCommand("copy");
      }
    }
    setStatus("approval-token-status", "Approval token copied.", "ok");
  } catch (_err) {
    setStatus("approval-token-status", "Clipboard copy failed. Copy the token manually from the field.", "bad");
  }
}

async function requestApprovalToken(event) {
  event.preventDefault();
  if (!authToken) {
    setStatus("approval-token-status", "Sign in first to request an approval token.", "bad");
    return;
  }

  const action = "intake_profile_mutation";
  try {
    setStatus("approval-token-status", "Requesting approval token...");
    const response = await apiRequest(API_AUTH_APPROVAL_TOKEN_URL, {
      method: "POST",
      body: { action },
      requireAuth: true,
    });
    const reviewerField = $("approval-reviewer-id");
    if (reviewerField) reviewerField.value = response?.approval_reviewer_id || "";
    const expiresField = $("approval-expires-at");
    if (expiresField) expiresField.value = response?.expires_at || "";
    const token = response?.approval_token || "";
    const tokenField = $("approval-token-value");
    if (tokenField) tokenField.value = token;
    setStatus(
      "approval-token-status",
      `Issued for ${response?.approval_reviewer_id || "the signed-in reviewer"}; expires ${formatDateTime(response?.expires_at) || "soon"}.`,
      "ok"
    );
  } catch (err) {
    setStatus("approval-token-status", parseApiError(err, "Failed to request approval token."), "bad");
  }
}

function setActiveTab(tabName) {
  document.querySelectorAll(".tab").forEach((button) => {
    const isActive = button.dataset.tab === tabName;
    button.classList.toggle("is-active", isActive);
  });

  ["candidates", "intake-profiles", "workbench", "review", "evidence", "bulk-sources", "proposals", "publish", "jobs", "audit"].forEach((name) => {
    const panel = $(`tab-${name}`);
    if (panel) panel.hidden = name !== tabName;
  });

  if (tabName === "jobs") {
    startWorkerHealthAutoRefresh();
  } else {
    stopWorkerHealthAutoRefresh();
  }

  if (tabName === "workbench") {
    syncWorkbenchPublishVisibility();
  }
}

function _fmtAge(seconds) {
  if (seconds === null || seconds === undefined) return "\u2014";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}

function renderWorkerHealth(data) {
  const stats = $("worker-health-stats");
  const failures = $("worker-health-failures");
  if (!stats || !failures) return;

  const workerEl = $("health-worker-alive");
  const queueEl = $("health-queue-depth");
  const dueEl = $("health-due-depth");
  const retryEl = $("health-retry-depth");
  const runningEl = $("health-running");
  const oldestDueEl = $("health-oldest-due");
  const terminalEl = $("health-terminal-count");

  function _setTile(el, text, tone) {
    if (!el) return;
    el.textContent = text;
    el.className = "health-stat-value" + (tone ? ` is-${tone}` : "");
  }

  _setTile(workerEl, data.worker_alive ? "alive" : "dead", data.worker_alive ? "ok" : "bad");
  _setTile(queueEl, String(data.queue_depth), data.queue_depth > 0 ? "warn" : null);
  _setTile(dueEl, String(data.due_depth), data.due_depth > 0 ? "warn" : null);
  _setTile(retryEl, String(data.retry_queue_depth), data.retry_queue_depth > 0 ? "warn" : null);
  _setTile(runningEl, String(data.running_count), null);
  _setTile(oldestDueEl, _fmtAge(data.oldest_due_age_seconds), data.oldest_due_age_seconds > 300 ? "bad" : data.oldest_due_age_seconds > 60 ? "warn" : null);
  _setTile(terminalEl, String(data.terminal_failure_count), data.terminal_failure_count > 0 ? "bad" : null);

  stats.hidden = false;

  const list = $("worker-health-failures-list");
  const recent = data.recent_terminal_failures || [];
  if (list && recent.length) {
    list.innerHTML = recent
      .map((f) => {
        const age = f.finished_at ? formatDateTime(f.finished_at) : "\u2014";
        return `<div class="row-btn" style="cursor:default;"><strong>${escapeHtml(f.job_type)}</strong><span class="row-meta">attempts ${escapeHtml(String(f.attempt_count))}/${escapeHtml(String(f.max_attempts))} | ${escapeHtml(f.last_error_code || "\u2014")} | finished ${escapeHtml(age)}</span></div>`;
      })
      .join("");
    failures.hidden = false;
  } else {
    failures.hidden = true;
  }
}

async function loadWorkerHealth() {
  try {
    setStatus("worker-health-status", "Loading...");
    const data = await apiRequest(API_WORKER_HEALTH_URL);
    renderWorkerHealth(data);
    setStatus("worker-health-status", `Updated ${formatDateTime(data.checked_at)}.`, "ok");
  } catch (err) {
    setStatus("worker-health-status", parseApiError(err, "Failed to load worker health."), "bad");
  }
}

function startWorkerHealthAutoRefresh() {
  if (_healthRefreshTimer !== null) return;
  loadWorkerHealth();
  _healthRefreshTimer = setInterval(loadWorkerHealth, 30000);
}

function stopWorkerHealthAutoRefresh() {
  if (_healthRefreshTimer === null) return;
  clearInterval(_healthRefreshTimer);
  _healthRefreshTimer = null;
}

function renderJsonDetail(preId, emptyId, payload) {
  const pre = $(preId);
  const empty = $(emptyId);
  if (!pre || !empty) return;
  if (!payload) {
    pre.hidden = true;
    empty.hidden = false;
    return;
  }
  pre.textContent = JSON.stringify(payload, null, 2);
  pre.hidden = false;
  empty.hidden = true;
}

function buildRaceFilterParams(prefix, extra = {}) {
  const params = new URLSearchParams();
  const state = normalizeOptionalText($(`${prefix}-state`)?.value);
  const office = normalizeOptionalText($(`${prefix}-office`)?.value);
  const cycle = normalizeOptionalInt($(`${prefix}-cycle`)?.value);
  const stage = normalizeOptionalText($(`${prefix}-stage`)?.value);
  if (state) params.set("state", state);
  if (office) params.set("office", office);
  if (cycle !== null) params.set("election_cycle", String(cycle));
  if (stage) params.set("race_stage", stage);
  Object.entries(extra).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") return;
    params.set(key, String(value));
  });
  return params;
}

function renderCandidateList(rows) {
  const list = $("candidate-list");
  if (!list) return;
  if (!rows.length) {
    list.innerHTML = `<p class="status-text">No candidates found for current filters.</p>`;
    return;
  }

  list.innerHTML = rows
    .map((row) => {
      const selected = row.id === selectedCandidateId ? "is-selected" : "";
      const stage = row.race_stage || "none";
      return `
        <button type="button" class="row-btn ${selected}" data-candidate-id="${escapeHtml(row.id)}">
          <strong>${escapeHtml(row.name)}</strong>
          <span class="row-meta">${escapeHtml(row.party || "Unlisted")} | ${escapeHtml(row.office || "Unspecified office")} | ${escapeHtml(row.state || "?")} | ${escapeHtml(stage)}</span>
        </button>
      `;
    })
    .join("");

  list.querySelectorAll(".row-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.candidateId;
      if (!id) return;
      selectedCandidateId = id;
      await loadCandidateDetail(id);
      renderCandidateList(rows);
    });
  });
}

function populateCandidateForm(candidate) {
  $("candidate-id").value = candidate.id || "";
  $("candidate-approval-token").value = "";
  $("candidate-name").value = candidate.name || "";
  $("candidate-party").value = candidate.party || "";
  $("candidate-office").value = candidate.office || "";
  $("candidate-state").value = candidate.state || "";
  $("candidate-cycle").value = candidate.election_cycle ?? "";
  $("candidate-stage").value = candidate.race_stage || "";
  $("candidate-active").checked = !!candidate.is_active;
  $("candidate-roster-status").value = candidate.roster_status || "";
  $("candidate-roster-url").value = candidate.roster_source_url || "";
  $("candidate-roster-checked-at").value = toInputDatetimeValue(candidate.roster_checked_at);
  $("candidate-roster-notes").value = candidate.roster_notes || "";
}

async function loadCandidateList() {
  try {
    setStatus("candidate-list-status", "Loading candidates...");
    const params = buildRaceFilterParams("candidate-filter");
    const url = params.toString() ? `${API_CANDIDATES_URL}?${params.toString()}` : API_CANDIDATES_URL;
    const rows = await apiRequest(url, { requireAuth: false });
    renderCandidateList(rows || []);
    setStatus("candidate-list-status", `Loaded ${rows.length} candidates.`, "ok");
  } catch (err) {
    renderCandidateList([]);
    setStatus("candidate-list-status", parseApiError(err, "Failed to load candidates."), "bad");
  }
}

async function loadCandidateDetail(candidateId) {
  try {
    setStatus("candidate-edit-status", "Loading candidate detail...");
    const row = await apiRequest(`${API_CANDIDATES_URL}/${encodeURIComponent(candidateId)}`, { requireAuth: true });
    populateCandidateForm(row);
    setStatus("candidate-edit-status", `Loaded ${row.name}.`, "ok");
  } catch (err) {
    setStatus("candidate-edit-status", parseApiError(err, "Failed to load candidate detail."), "bad");
  }
}

function buildCandidatePayload(prefix) {
  return {
    approval_token: normalizeOptionalText($(`${prefix}-approval-token`).value) || "",
    name: normalizeOptionalText($(`${prefix}-name`).value) || "",
    party: normalizeOptionalText($(`${prefix}-party`).value),
    office: normalizeOptionalText($(`${prefix}-office`).value),
    state: normalizeOptionalText($(`${prefix}-state`).value),
    election_cycle: normalizeOptionalInt($(`${prefix}-cycle`).value),
    race_stage: normalizeOptionalText($(`${prefix}-stage`).value),
    is_active: !!$(`${prefix}-active`).checked,
    roster_status: normalizeOptionalText($(`${prefix}-roster-status`).value),
    roster_source_url: normalizeOptionalText($(`${prefix}-roster-url`).value),
    roster_checked_at: fromInputDatetimeValue($(`${prefix}-roster-checked-at`).value),
    roster_notes: normalizeOptionalText($(`${prefix}-roster-notes`).value),
  };
}

async function saveCandidate(event) {
  event.preventDefault();
  if (!selectedCandidateId) {
    setStatus("candidate-edit-status", "Select a candidate first.", "bad");
    return;
  }

  try {
    const payload = buildCandidatePayload("candidate");
    if (!payload.approval_token) {
      setStatus("candidate-edit-status", "Approval token is required.", "bad");
      return;
    }
    setStatus("candidate-edit-status", "Saving candidate...");
    const row = await apiRequest(`${API_CANDIDATES_URL}/${encodeURIComponent(selectedCandidateId)}`, {
      method: "PATCH",
      body: payload,
      requireAuth: true,
    });
    populateCandidateForm(row);
    setStatus("candidate-edit-status", "Candidate saved.", "ok");
    await loadCandidateList();
  } catch (err) {
    const dualControlMessage = parseCandidateDualControlError(err, "candidate_update");
    setStatus("candidate-edit-status", dualControlMessage || parseApiError(err, "Failed to save candidate."), "bad");
  }
}

async function createCandidate(event) {
  event.preventDefault();
  try {
    const payload = buildCandidatePayload("create");
    if (!payload.approval_token) {
      setStatus("candidate-create-status", "Approval token is required.", "bad");
      return;
    }
    setStatus("candidate-create-status", "Creating candidate...");
    const row = await apiRequest(API_CANDIDATES_URL, {
      method: "POST",
      body: payload,
      requireAuth: true,
    });

    setStatus("candidate-create-status", `Created ${row.name}.`, "ok");
    selectedCandidateId = row.id;
    await loadCandidateList();
    await loadCandidateDetail(row.id);
  } catch (err) {
    const dualControlMessage = parseCandidateDualControlError(err, "candidate_create");
    setStatus("candidate-create-status", dualControlMessage || parseApiError(err, "Failed to create candidate."), "bad");
  }
}

function formatIntakeProfileBatchList(profile) {
  const batches = Array.isArray(profile?.statement_batches) ? profile.statement_batches : [];
  return batches.length ? batches.join(", ") : "none";
}

function formatJsonObject(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "{}";
  return JSON.stringify(value, null, 2);
}

function parseJsonObjectField(text, fieldName) {
  const raw = String(text || "").trim();
  if (!raw) return { value: {}, error: null };
  const parsed = parseJsonTextarea(raw, fieldName);
  if (parsed.error) return parsed;
  if (!parsed.value || typeof parsed.value !== "object" || Array.isArray(parsed.value)) {
    return { value: null, error: `${fieldName} must be a JSON object.` };
  }
  return { value: parsed.value, error: null };
}

function renderIntakeProfileList(rows) {
  const list = $("intake-profiles-list");
  if (!list) return;
  if (!rows.length) {
    list.innerHTML = `<p class="status-text">No race profiles found.</p>`;
    return;
  }

  list.innerHTML = rows
    .map((row) => {
      const selected = row.profile_id === selectedIntakeProfileId ? "is-selected" : "";
      return `
        <button type="button" class="row-btn ${selected}" data-intake-profile-id="${escapeHtml(row.profile_id)}">
          <strong>${escapeHtml(row.label)}</strong>
          <span class="row-meta">${escapeHtml(row.profile_id)} | ${escapeHtml(row.state)} | ${escapeHtml(row.office)} | ${escapeHtml(row.race_stage)}</span>
          <span class="row-meta">statement batches: ${escapeHtml(formatIntakeProfileBatchList(row))}</span>
        </button>
      `;
    })
    .join("");

  list.querySelectorAll(".row-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.intakeProfileId;
      if (!id) return;
      selectedIntakeProfileId = id;
      populateIntakeProfileForm(intakeProfilesRows.find((row) => row.profile_id === id) || null);
      renderIntakeProfileList(rows);
      setStatus("intake-profiles-status", `Selected ${id}.`, "ok");
    });
  });
}

function clearIntakeProfileForm() {
  [
    "intake-profile-id",
    "intake-profile-approval-token",
    "intake-profile-label",
    "intake-profile-state",
    "intake-profile-office",
    "intake-profile-cycle",
    "intake-profile-stage",
    "intake-profile-roster-module",
    "intake-profile-statement-batches",
    "intake-profile-admin-jobs",
  ].forEach((id) => {
    const el = $(id);
    if (!el) return;
    if (el.type === "checkbox") {
      el.checked = false;
    } else {
      el.value = "";
    }
  });
}

function populateIntakeProfileForm(profile) {
  if (!profile) {
    clearIntakeProfileForm();
    return;
  }
  $("intake-profile-id").value = profile.profile_id || "";
  $("intake-profile-approval-token").value = "";
  $("intake-profile-label").value = profile.label || "";
  $("intake-profile-state").value = profile.state || "";
  $("intake-profile-office").value = profile.office || "";
  $("intake-profile-cycle").value = profile.election_cycle ?? "";
  $("intake-profile-stage").value = profile.race_stage || "";
  $("intake-profile-roster-module").value = profile.roster_seed_module || "";
  $("intake-profile-statement-batches").value = formatJsonObject(profile.statement_batch_modules);
  $("intake-profile-admin-jobs").value = formatJsonObject(profile.admin_job_modules);
}

async function loadIntakeProfiles() {
  try {
    setStatus("intake-profiles-status", "Loading race profiles...");
    const response = await apiRequest(API_ADMIN_INTAKE_PROFILES_URL);
    intakeProfilesVersion = response?.version || "";
    intakeProfilesRows = Array.isArray(response?.profiles) ? response.profiles : [];
    setStatus(
      "intake-profiles-version",
      intakeProfilesVersion ? `Config version: ${intakeProfilesVersion}` : "Config version unavailable.",
      intakeProfilesVersion ? "ok" : ""
    );
    renderIntakeProfileList(intakeProfilesRows);
    if (intakeProfilesRows.length) {
      const selected = intakeProfilesRows.find((row) => row.profile_id === selectedIntakeProfileId) || intakeProfilesRows[0];
      selectedIntakeProfileId = selected.profile_id;
      populateIntakeProfileForm(selected);
      setStatus("intake-profiles-status", `Loaded ${intakeProfilesRows.length} race profiles.`, "ok");
    } else {
      selectedIntakeProfileId = "";
      clearIntakeProfileForm();
      setStatus("intake-profiles-status", "No race profiles found.", "bad");
    }
  } catch (err) {
    intakeProfilesRows = [];
    selectedIntakeProfileId = "";
    renderIntakeProfileList([]);
    clearIntakeProfileForm();
    setStatus("intake-profiles-status", parseApiError(err, "Failed to load race profiles."), "bad");
  }
}

function buildIntakeProfilePayload(prefix, { includeProfileId = false } = {}) {
  const payload = {
    approval_token: normalizeOptionalText($(`${prefix}-approval-token`).value) || "",
    label: normalizeOptionalText($(`${prefix}-label`).value) || "",
    state: normalizeOptionalText($(`${prefix}-state`).value) || "",
    office: normalizeOptionalText($(`${prefix}-office`).value) || "",
    election_cycle: normalizeOptionalInt($(`${prefix}-cycle`).value),
    race_stage: normalizeOptionalText($(`${prefix}-stage`).value) || "",
    roster_seed_module: normalizeOptionalText($(`${prefix}-roster-module`).value) || "",
  };
  if (includeProfileId) {
    payload.profile_id = normalizeOptionalText($(`${prefix}-id`).value) || "";
  }

  const statementBatches = parseJsonObjectField($(`${prefix}-statement-batches`).value, "Statement Batch Modules");
  if (statementBatches.error) return { payload: null, error: statementBatches.error };
  const adminJobs = parseJsonObjectField($(`${prefix}-admin-jobs`).value, "Admin Job Modules");
  if (adminJobs.error) return { payload: null, error: adminJobs.error };

  payload.statement_batch_modules = statementBatches.value;
  payload.admin_job_modules = adminJobs.value;
  return { payload, error: null };
}

async function saveIntakeProfile(event) {
  event.preventDefault();
  if (!selectedIntakeProfileId) {
    setStatus("intake-profile-edit-status", "Select a race profile first.", "bad");
    return;
  }

  const parsed = buildIntakeProfilePayload("intake-profile");
  if (parsed.error) {
    setStatus("intake-profile-edit-status", parsed.error, "bad");
    return;
  }
  if (!parsed.payload.approval_token) {
    setStatus("intake-profile-edit-status", "Approval token is required.", "bad");
    return;
  }
  const requiredFields = ["label", "state", "office", "race_stage", "roster_seed_module"];
  for (const field of requiredFields) {
    if (!parsed.payload[field]) {
      setStatus("intake-profile-edit-status", `${field.replace(/_/g, " ")} cannot be empty.`, "bad");
      return;
    }
  }
  if (!parsed.payload.election_cycle) {
    setStatus("intake-profile-edit-status", "Election cycle cannot be empty.", "bad");
    return;
  }

  try {
    setStatus("intake-profile-edit-status", "Saving race profile...");
    const response = await apiRequest(`${API_ADMIN_INTAKE_PROFILES_URL}/${encodeURIComponent(selectedIntakeProfileId)}`, {
      method: "PATCH",
      body: parsed.payload,
    });
    intakeProfilesVersion = response?.version || intakeProfilesVersion;
    intakeProfilesRows = Array.isArray(response?.profiles) ? response.profiles : intakeProfilesRows;
    const selected = intakeProfilesRows.find((row) => row.profile_id === selectedIntakeProfileId) || null;
    populateIntakeProfileForm(selected);
    renderIntakeProfileList(intakeProfilesRows);
    setStatus("intake-profile-edit-status", "Race profile saved.", "ok");
    await loadAdminJobMetadata();
  } catch (err) {
    const dualControlMessage = parseIntakeProfileDualControlError(err, "intake_profile_update");
    setStatus("intake-profile-edit-status", dualControlMessage || parseApiError(err, "Failed to save race profile."), "bad");
  }
}

async function createIntakeProfile(event) {
  event.preventDefault();
  const parsed = buildIntakeProfilePayload("intake-profile-create", { includeProfileId: true });
  if (parsed.error) {
    setStatus("intake-profile-create-status", parsed.error, "bad");
    return;
  }
  if (!parsed.payload.approval_token) {
    setStatus("intake-profile-create-status", "Approval token is required.", "bad");
    return;
  }

  try {
    setStatus("intake-profile-create-status", "Creating race profile...");
    const response = await apiRequest(API_ADMIN_INTAKE_PROFILES_URL, {
      method: "POST",
      body: parsed.payload,
    });
    intakeProfilesVersion = response?.version || intakeProfilesVersion;
    intakeProfilesRows = Array.isArray(response?.profiles) ? response.profiles : intakeProfilesRows;
    selectedIntakeProfileId = parsed.payload.profile_id;
    populateIntakeProfileForm(intakeProfilesRows.find((row) => row.profile_id === selectedIntakeProfileId) || null);
    renderIntakeProfileList(intakeProfilesRows);
    setStatus("intake-profile-create-status", `Created ${parsed.payload.profile_id}.`, "ok");
    await loadAdminJobMetadata();
  } catch (err) {
    const dualControlMessage = parseIntakeProfileDualControlError(err, "intake_profile_create");
    setStatus("intake-profile-create-status", dualControlMessage || parseApiError(err, "Failed to create race profile."), "bad");
  }
}

function renderJobsList(rows) {
  const list = $("jobs-list");
  if (!list) return;
  if (!rows.length) {
    list.innerHTML = `<p class="status-text">No jobs found.</p>`;
    return;
  }
  list.innerHTML = rows
    .map((row) => {
      const selected = row.id === selectedJobId ? "is-selected" : "";
      return `
        <button type="button" class="row-btn ${selected}" data-job-id="${escapeHtml(row.id)}">
          <strong>${escapeHtml(row.job_type)}</strong>
          <span class="row-meta">${escapeHtml(row.status)} | ${escapeHtml(row.requested_by_reviewer_id)} | ${escapeHtml(formatDateTime(row.created_at))}</span>
        </button>
      `;
    })
    .join("");

  list.querySelectorAll(".row-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.jobId;
      if (!id) return;
      selectedJobId = id;
      await loadJobDetail(id);
      renderJobsList(rows);
    });
  });
}

async function loadJobsList() {
  try {
    setStatus("jobs-list-status", "Loading jobs...");
    const params = new URLSearchParams();
    const status = normalizeOptionalText($("jobs-filter-status")?.value);
    const jobType = normalizeOptionalText($("jobs-filter-type")?.value);
    const limit = normalizeOptionalInt($("jobs-filter-limit")?.value) || 100;
    if (status) params.set("status", status);
    if (jobType) params.set("job_type", jobType);
    params.set("limit", String(limit));

    const rows = await apiRequest(`${API_ADMIN_JOBS_URL}?${params.toString()}`);
    renderJobsList(rows || []);
    setStatus("jobs-list-status", `Loaded ${rows.length} jobs.`, "ok");
  } catch (err) {
    renderJobsList([]);
    setStatus("jobs-list-status", parseApiError(err, "Failed to load jobs."), "bad");
  }
}

async function loadJobDetail(jobId) {
  try {
    const row = await apiRequest(`${API_ADMIN_JOBS_URL}/${encodeURIComponent(jobId)}`);
    renderJsonDetail("job-detail-json", "job-detail-empty", row);
    setStatus("job-create-status", `Loaded job ${jobId}.`, "ok");
  } catch (err) {
    renderJsonDetail("job-detail-json", "job-detail-empty", null);
    setStatus("job-create-status", parseApiError(err, "Failed to load job detail."), "bad");
  }
}

function setJobPayloadTextarea(value) {
  const el = $("job-input-payload");
  if (!el) return;
  el.value = value;
}

function getAdminJobList() {
  const jobs = adminJobMetadata?.jobs;
  return Array.isArray(jobs) ? jobs : [];
}

function getIntakeProfiles() {
  const profiles = adminJobMetadata?.intake_profiles;
  return Array.isArray(profiles) ? profiles : [];
}

function getJobInputSchema(jobType) {
  const jobs = getAdminJobList();
  const found = jobs.find((item) => item?.job_type === jobType);
  const schema = found?.input_schema;
  if (!schema || typeof schema !== "object") {
    return {
      required_fields: [],
      allowed_fields: [],
      field_types: {},
      allowed_values: {},
      supports_dry_run: false,
    };
  }
  return {
    required_fields: Array.isArray(schema.required_fields) ? schema.required_fields : [],
    allowed_fields: Array.isArray(schema.allowed_fields) ? schema.allowed_fields : [],
    field_types: typeof schema.field_types === "object" && schema.field_types ? schema.field_types : {},
    allowed_values: typeof schema.allowed_values === "object" && schema.allowed_values ? schema.allowed_values : {},
    supports_dry_run: !!schema.supports_dry_run,
  };
}

function getIntakeProfile(profileId) {
  return getIntakeProfiles().find((item) => item.profile_id === profileId) || null;
}

function getAllowedProfileIdsForJob(jobType) {
  const schema = getJobInputSchema(jobType);
  const values = schema?.allowed_values?.profile_id;
  return Array.isArray(values) ? values.map((item) => String(item)) : [];
}

function getJobInputPayloadText(payload) {
  return JSON.stringify(payload, null, 2);
}

function renderJobTypeOptions() {
  const select = $("job-type");
  if (!select) return;
  const jobs = getAdminJobList();
  if (!jobs.length) return;
  const previous = String(select.value || "");
  select.innerHTML = jobs
    .map((job) => `<option value="${escapeHtml(job.job_type)}">${escapeHtml(job.job_type)}</option>`)
    .join("");
  const hasPrevious = jobs.some((job) => job.job_type === previous);
  select.value = hasPrevious ? previous : jobs[0].job_type;
}

function populateJobProfileOptions(jobType) {
  const select = $("job-profile-id");
  if (!select) return;
  const activeJobType = String(jobType || $("job-type")?.value || "").trim();
  const allowedProfileIds = getAllowedProfileIdsForJob(activeJobType);
  const profiles = getIntakeProfiles();
  const filteredProfiles =
    allowedProfileIds.length > 0
      ? profiles.filter((profile) => allowedProfileIds.includes(profile.profile_id))
      : profiles;
  if (!profiles.length) {
    select.innerHTML = "";
    return;
  }
  const previous = String(select.value || "");
  select.innerHTML = filteredProfiles
    .map((profile) => `<option value="${escapeHtml(profile.profile_id)}">${escapeHtml(profile.label)} (${escapeHtml(profile.profile_id)})</option>`)
    .join("");
  const hasPrevious = filteredProfiles.some((profile) => profile.profile_id === previous);
  select.value = hasPrevious ? previous : filteredProfiles[0]?.profile_id || "";
}

async function loadAdminJobMetadata() {
  const metadata = await apiRequest(API_ADMIN_JOB_METADATA_URL);
  adminJobMetadata = metadata;
  renderJobTypeOptions();
  populateJobProfileOptions(String($("job-type")?.value || "").trim());
  refreshJobTypeSpecificControls();
}

function populateJobStatementBatchOptions(profileId) {
  const select = $("job-statement-batch");
  if (!select) return;
  const intakeProfiles = getIntakeProfiles();
  const profile = getIntakeProfile(profileId) || intakeProfiles[0] || null;
  const batches = Array.isArray(profile?.statement_batches) ? profile.statement_batches : [];
  const previousValue = String(select.value || "");
  select.innerHTML = batches
    .map((batchKey) => `<option value="${escapeHtml(batchKey)}">${escapeHtml(batchKey)}</option>`)
    .join("");
  if (batches.includes(previousValue)) {
    select.value = previousValue;
  } else if (batches.length) {
    select.value = batches[0];
  }
}

function buildTypedJobPayload(jobType) {
  const schema = getJobInputSchema(jobType);
  const allowedFields = new Set(Array.isArray(schema.allowed_fields) ? schema.allowed_fields : []);
  const payload = {};
  if (allowedFields.has("profile_id")) {
    payload.profile_id = String($("job-profile-id")?.value || "").trim();
  }
  if (allowedFields.has("statement_batch")) {
    payload.statement_batch = String($("job-statement-batch")?.value || "").trim();
  }
  if (schema.supports_dry_run) {
    payload.dry_run = !!$("job-dry-run")?.checked;
  }
  return payload;
}

function syncJobPayloadFromTypedControls() {
  const jobType = String($("job-type")?.value || "").trim();
  setJobPayloadTextarea(getJobInputPayloadText(buildTypedJobPayload(jobType)));
}

function refreshJobTypeSpecificControls() {
  const jobType = String($("job-type")?.value || "").trim();
  const schema = getJobInputSchema(jobType);
  const allowedFields = new Set(Array.isArray(schema.allowed_fields) ? schema.allowed_fields : []);
  const showProfile = allowedFields.has("profile_id");
  const showStatementBatch = allowedFields.has("statement_batch");
  const allowedProfileIds = getAllowedProfileIdsForJob(jobType);

  if ($("job-profile-field")) $("job-profile-field").hidden = !showProfile;
  if ($("job-statement-batch-field")) $("job-statement-batch-field").hidden = !showStatementBatch;
  if ($("job-dry-run-field")) $("job-dry-run-field").hidden = !schema.supports_dry_run;

  if (showProfile) {
    populateJobProfileOptions(jobType);
  }
  const selectedProfileId = String($("job-profile-id")?.value || "");
  if (showProfile && !selectedProfileId) {
    const fallbackProfileId = allowedProfileIds[0] || "";
    $("job-profile-id").value = fallbackProfileId;
  }
  if (showStatementBatch) {
    populateJobStatementBatchOptions(String($("job-profile-id")?.value || ""));
  }
  syncJobPayloadFromTypedControls();
}

function parseAndValidateJobPayload(jobType) {
  if (!adminJobMetadata) {
    return { payload: null, error: "Job metadata is unavailable. Refresh and sign in again." };
  }

  const raw = $("job-input-payload")?.value || "{}";
  const parsed = parseJsonTextarea(raw, "Job input_payload");
  if (parsed.error) return { payload: null, error: parsed.error };
  if (!parsed.value || typeof parsed.value !== "object" || Array.isArray(parsed.value)) {
    return { payload: null, error: "Job input_payload must be a JSON object." };
  }

  const schema = getJobInputSchema(jobType);
  const allowedFields = new Set(schema.allowed_fields || []);
  if (schema.supports_dry_run) allowedFields.add("dry_run");
  const requiredFields = Array.isArray(schema.required_fields) ? schema.required_fields : [];
  const unsupportedFields = Object.keys(parsed.value).filter((key) => !allowedFields.has(key));
  const missingFields = requiredFields.filter((field) => {
    const rawValue = parsed.value[field];
    return rawValue == null || (typeof rawValue === "string" && rawValue.trim() === "");
  });
  if (missingFields.length || unsupportedFields.length) {
    const details = [];
    if (missingFields.length) details.push(`missing required fields: ${missingFields.join(", ")}`);
    if (unsupportedFields.length) details.push(`unsupported fields: ${unsupportedFields.join(", ")}`);
    return {
      payload: null,
      error: `Job input payload is invalid (${details.join("; ")}).`,
    };
  }

  const normalized = {};
  for (const fieldName of allowedFields) {
    if (!(fieldName in parsed.value)) {
      if (fieldName === "dry_run" && schema.supports_dry_run) normalized.dry_run = false;
      continue;
    }
    const expectedType = schema.field_types?.[fieldName];
    const value = parsed.value[fieldName];
    if (expectedType === "string") {
      if (typeof value !== "string" || !value.trim()) {
        return { payload: null, error: `${fieldName} must be a non-empty string.` };
      }
      normalized[fieldName] = value.trim();
      continue;
    }
    if (expectedType === "boolean" || fieldName === "dry_run") {
      if (typeof value !== "boolean") {
        return { payload: null, error: `${fieldName} must be a boolean when provided.` };
      }
      normalized[fieldName] = value;
      continue;
    }
    normalized[fieldName] = value;
  }

  if (!schema.supports_dry_run && "dry_run" in parsed.value) {
    return {
      payload: null,
      error: "dry_run is not supported for the selected job type.",
    };
  }

  if ("profile_id" in normalized) {
    const profileIds = getAllowedProfileIdsForJob(jobType);
    if (profileIds.length > 0 && !profileIds.includes(normalized.profile_id)) {
      return {
        payload: null,
        error: `profile_id must be one of ${profileIds.join(", ")}.`,
      };
    }
  }

  if (jobType === "ingest_statement_batch") {
    const profile = getIntakeProfile(normalized.profile_id);
    const allowedBatches = Array.isArray(profile?.statement_batches) ? profile.statement_batches : [];
    if (!allowedBatches.includes(normalized.statement_batch)) {
      return {
        payload: null,
        error: `statement_batch must be one of ${allowedBatches.join(", ")} for profile_id ${normalized.profile_id}.`,
      };
    }
  }

  return { payload: normalized, error: null };
}

async function runJob(event) {
  event.preventDefault();
  const jobType = $("job-type").value;
  const parsed = parseAndValidateJobPayload(jobType);
  if (parsed.error) {
    setStatus("job-create-status", parsed.error, "bad");
    return;
  }

  try {
    setStatus("job-create-status", "Running job...");
    const payload = {
      job_type: jobType,
      input_payload: parsed.payload,
    };
    const row = await apiRequest(API_ADMIN_JOBS_URL, {
      method: "POST",
      body: payload,
    });
    selectedJobId = row.id;
    renderJsonDetail("job-detail-json", "job-detail-empty", row);
    setStatus("job-create-status", `Job finished with status ${row.status}.`, row.status === "succeeded" ? "ok" : "bad");
    await Promise.all([loadJobsList(), loadAuditList()]);
  } catch (err) {
    setStatus("job-create-status", parseApiError(err, "Failed to run job."), "bad");
  }
}

function renderAuditList(rows) {
  const list = $("audit-list");
  if (!list) return;
  if (!rows.length) {
    list.innerHTML = `<p class="status-text">No audit events found.</p>`;
    return;
  }

  list.innerHTML = rows
    .map((row) => {
      const selected = row.id === selectedAuditId ? "is-selected" : "";
      return `
        <button type="button" class="row-btn ${selected}" data-audit-id="${escapeHtml(row.id)}">
          <strong>${escapeHtml(row.action)}</strong>
          <span class="row-meta">${escapeHtml(row.entity_type)}:${escapeHtml(row.entity_id)} | ${escapeHtml(row.actor_reviewer_id)}</span>
          <span class="row-meta">${escapeHtml(formatDateTime(row.created_at))}</span>
        </button>
      `;
    })
    .join("");

  list.querySelectorAll(".row-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.auditId;
      if (!id) return;
      selectedAuditId = id;
      await loadAuditDetail(id);
      renderAuditList(rows);
    });
  });
}

async function loadAuditList() {
  try {
    setStatus("audit-list-status", "Loading audit events...");
    const params = new URLSearchParams();
    const action = normalizeOptionalText($("audit-filter-action")?.value);
    const entityType = normalizeOptionalText($("audit-filter-entity-type")?.value);
    const entityId = normalizeOptionalText($("audit-filter-entity-id")?.value);
    const actor = normalizeOptionalText($("audit-filter-actor")?.value);
    const limit = normalizeOptionalInt($("audit-filter-limit")?.value) || 100;
    if (action) params.set("action", action);
    if (entityType) params.set("entity_type", entityType);
    if (entityId) params.set("entity_id", entityId);
    if (actor) params.set("actor_reviewer_id", actor);
    params.set("limit", String(limit));

    const rows = await apiRequest(`${API_ADMIN_AUDIT_URL}?${params.toString()}`);
    renderAuditList(rows || []);
    setStatus("audit-list-status", `Loaded ${rows.length} audit events.`, "ok");
  } catch (err) {
    renderAuditList([]);
    setStatus("audit-list-status", parseApiError(err, "Failed to load audit events."), "bad");
  }
}

async function loadAuditDetail(eventId) {
  try {
    const row = await apiRequest(`${API_ADMIN_AUDIT_URL}/${encodeURIComponent(eventId)}`);
    renderJsonDetail("audit-detail-json", "audit-detail-empty", row);
  } catch (err) {
    renderJsonDetail("audit-detail-json", "audit-detail-empty", null);
    setStatus("audit-list-status", parseApiError(err, "Failed to load audit detail."), "bad");
  }
}

function _workbenchRowTone(row) {
  if (row.is_published) return "row-tone-ok";
  if (row.reviewer_state === "Insufficient Evidence") return "row-tone-low";
  if (row.publish_gate_passed) return "row-tone-ok";
  if (row.reviewer_state === "Needs Evidence") return "row-tone-bad";
  return "row-tone-mixed";
}

function renderWorkbenchList(rows) {
  const list = $("workbench-list");
  if (!list) return;
  if (!rows.length) {
    list.innerHTML = `<p class="status-text">No Workbench claims matched the current filters.</p>`;
    return;
  }

  const grouped = new Map();
  WORKBENCH_STATE_ORDER.forEach((state) => grouped.set(state, []));
  rows.forEach((row) => {
    const state = String(row.reviewer_state || "");
    if (!grouped.has(state)) grouped.set(state, []);
    grouped.get(state).push(row);
  });

  list.innerHTML = Array.from(grouped.entries())
    .filter((entry) => entry[1].length > 0)
    .map(([state, stateRows]) => {
      const items = stateRows
        .map((row) => {
          const selected = String(row.claim_id) === selectedWorkbenchClaimId ? "is-selected" : "";
          const verdict = row.latest_verdict || "none";
          const tone = _workbenchRowTone(row);
          return `
            <button type="button" class="row-btn ${selected}" data-claim-id="${escapeHtml(row.claim_id)}">
              <strong>${escapeHtml(row.issue_tag || "Unlabeled issue")}</strong>
              <span class="row-meta ${tone}">${escapeHtml(row.candidate_name)} | ${escapeHtml(verdict)} | claim ${escapeHtml(shortId(row.claim_id))}</span>
              <span class="row-meta">Verification P/S ${escapeHtml(String(row.verification_primary_count))}/${escapeHtml(String(row.verification_secondary_count))} | publish gate ${row.publish_gate_passed ? "passed" : "blocked"}</span>
            </button>
          `;
        })
        .join("");
      return `<section class="workbench-state-group"><h4 class="workbench-state-heading">${escapeHtml(state)} (${stateRows.length})</h4>${items}</section>`;
    })
    .join("");

  list.querySelectorAll(".row-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const claimId = btn.dataset.claimId;
      if (!claimId) return;
      selectWorkbenchClaim(claimId);
      renderWorkbenchList(rows);
    });
  });
}

function renderWorkbenchChecklist(row) {
  const itemsEl = $("workbench-checklist-items");
  if (!itemsEl) return;
  const checklist = Array.isArray(row?.checklist) ? row.checklist : [];
  itemsEl.innerHTML = checklist
    .map((item) => {
      const state = item.passed ? "pass" : item.blocking ? "blocked" : "informational";
      const tone = item.passed ? "ok" : item.blocking ? "bad" : "";
      return `<li class="${tone}">${escapeHtml(state)}: ${escapeHtml(item.label)} (${escapeHtml(item.code)})</li>`;
    })
    .join("");
}

function renderWorkbenchRawFailures(row) {
  const show = !!$("workbench-show-raw-failures")?.checked;
  const pre = $("workbench-raw-failures");
  if (!pre) return;
  if (!show) {
    pre.hidden = true;
    pre.textContent = "";
    return;
  }
  pre.hidden = false;
  pre.textContent = JSON.stringify(row?.publish_gate_failures || [], null, 2);
}

function _workbenchHandoffGuidance(row) {
  if (!row) return "";
  if (row.second_reviewer_action === "publish_handoff") {
    return "Publish handoff required: a different reviewer/admin must execute publish/unpublish than the reviewer tied to approval.";
  }
  if (row.second_reviewer_action === "overwrite_handoff") {
    return "Evaluation overwrite path requires a second reviewer/admin approval token.";
  }
  return "No second-reviewer handoff is currently indicated.";
}

function isAdminIdentity() {
  return identity?.role === "admin";
}

function renderWorkbenchDetail(row) {
  const detail = $("workbench-detail");
  const empty = $("workbench-detail-empty");
  if (!detail || !empty) return;
  if (!row) {
    detail.hidden = true;
    empty.hidden = false;
    selectedWorkbenchSources = [];
    selectedWorkbenchRecommendations = [];
    renderWorkbenchSourcesList([]);
    renderWorkbenchRecommendationsList([]);
    setStatus("workbench-sources-list-status", "");
    setStatus("workbench-recommendations-status", "");
    return;
  }

  detail.hidden = false;
  empty.hidden = true;
  setStatus(
    "workbench-context-status",
    `${row.candidate_name} (${row.candidate_party || "Unlisted"}) | ${row.candidate_office || "Unspecified office"} | ${row.reviewer_state}`
  );
  setStatus("workbench-claim-text", row.claim_text || "");
  const statementLink = $("workbench-statement-link");
  if (statementLink) {
    statementLink.href = row.statement_source_url || "#";
    statementLink.textContent = row.statement_source_url || "open source link";
  }
  setStatus(
    "workbench-evidence-summary",
    `Verification sources: ${row.verification_source_count} total (${row.verification_primary_count} primary / ${row.verification_secondary_count} secondary).`
  );
  const insufficientLabel = row.reviewer_state === "Insufficient Evidence"
    ? "Review complete: insufficient evidence verdict is recorded and this claim is not publish-eligible."
    : `Current reviewer-facing state: ${row.reviewer_state}.`;
  setStatus("workbench-outcome-status", insufficientLabel, row.reviewer_state === "Insufficient Evidence" ? "ok" : "");
  setStatus("workbench-handoff-status", _workbenchHandoffGuidance(row));

  $("workbench-source-claim-id").value = String(row.claim_id);
  $("workbench-review-claim-id").value = String(row.claim_id);
  $("workbench-publish-claim-id").value = String(row.claim_id);
  $("workbench-publish-action").value = row.is_published ? "unpublish" : "publish";
  syncWorkbenchPublishVisibility();

  renderWorkbenchChecklist(row);
  renderWorkbenchRawFailures(row);
  const claimId = String(row.claim_id);
  void Promise.all([loadWorkbenchSources(claimId), loadWorkbenchSourceRecommendations(claimId)]);
}

function selectWorkbenchClaim(claimId) {
  const row = workbenchRows.find((item) => String(item.claim_id) === String(claimId));
  if (!row) return;
  selectedWorkbenchClaimId = String(claimId);
  renderWorkbenchDetail(row);
}

async function loadWorkbench() {
  try {
    setStatus("workbench-list-status", "Loading Workbench...");
    const includeNonFactCheckable = !!$("workbench-filter-include-non-fact-checkable")?.checked;
    const workbenchState = normalizeOptionalText($("workbench-filter-reviewer-state")?.value);
    const limit = normalizeOptionalInt($("workbench-filter-limit")?.value) || 200;
    const params = buildRaceFilterParams("workbench-filter", {
      include_non_fact_checkable: includeNonFactCheckable,
      workbench_state: workbenchState,
      limit,
    });
    const rows = await apiRequest(`${API_WORKBENCH_URL}?${params.toString()}`);
    workbenchRows = rows || [];
    renderWorkbenchList(workbenchRows);
    if (workbenchRows.length) {
      const keepSelected = workbenchRows.some((row) => String(row.claim_id) === selectedWorkbenchClaimId);
      selectedWorkbenchClaimId = keepSelected ? selectedWorkbenchClaimId : String(workbenchRows[0].claim_id);
      selectWorkbenchClaim(selectedWorkbenchClaimId);
      renderWorkbenchList(workbenchRows);
    } else {
      selectedWorkbenchClaimId = "";
      renderWorkbenchDetail(null);
    }
    setStatus("workbench-list-status", `Loaded ${workbenchRows.length} Workbench claims.`, "ok");
  } catch (err) {
    workbenchRows = [];
    selectedWorkbenchClaimId = "";
    renderWorkbenchList([]);
    renderWorkbenchDetail(null);
    setStatus("workbench-list-status", parseApiError(err, "Failed to load Workbench."), "bad");
  } finally {
    syncWorkbenchPublishVisibility();
  }
}

function parseSourceAdmissionError(err) {
  const code = err?.payload?.error?.code;
  if (code !== "source_admission_policy_violation") return null;
  const details = err?.payload?.error?.details || {};
  const rejectionField = details.rejection_field ? `field ${details.rejection_field}` : "source admission policy";
  return `Source rejected by admission policy (${rejectionField}).`;
}

function parseSourceDeleteError(err) {
  const code = err?.payload?.error?.code;
  if (code === "source_delete_not_allowed_for_published_claim") {
    return "Source removal is blocked: published claims cannot have sources deleted.";
  }
  if (code === "source_not_found") {
    return "Source not found for this claim. Refresh and retry.";
  }
  return null;
}

function renderWorkbenchSourcesList(sources) {
  const list = $("workbench-sources-list");
  if (!list) return;
  if (!sources.length) {
    list.innerHTML = `<p class="status-text">No attached sources for this claim.</p>`;
    return;
  }

  list.innerHTML = sources
    .map((source) => {
      const sourceId = String(source.id || "");
      const sourceClass = source.source_class || "unknown";
      const sourceOrigin = source.source_origin || "unknown";
      const publisher = source.publisher || "Unspecified publisher";
      const url = source.url || "";
      return `
        <div class="row-btn" style="cursor:default;">
          <strong>${escapeHtml(sourceClass)} / ${escapeHtml(sourceOrigin)}</strong>
          <span class="row-meta">publisher: ${escapeHtml(publisher)} | source ${escapeHtml(shortId(sourceId))}</span>
          <span class="row-meta"><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a></span>
          <div class="action-row" style="margin-top:0.5rem;">
            <button type="button" class="ghost-btn workbench-source-remove" data-source-id="${escapeHtml(sourceId)}">Remove</button>
          </div>
        </div>
      `;
    })
    .join("");

  list.querySelectorAll(".workbench-source-remove").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const sourceId = btn.dataset.sourceId;
      if (!sourceId || !isUuid(sourceId)) return;
      await removeWorkbenchSource(sourceId);
    });
  });
}

function renderWorkbenchRecommendationsList(recommendations) {
  const list = $("workbench-recommendations-list");
  if (!list) return;
  if (!recommendations.length) {
    list.innerHTML = `<p class="status-text">No recommendations available for this claim yet.</p>`;
    return;
  }

  list.innerHTML = recommendations
    .map((item, index) => {
      const sourceClass = item.source_class || "unknown";
      const publisher = item.publisher || "Unspecified publisher";
      const url = item.url || "";
      const rationale = item.rationale || "";
      return `
        <div class="row-btn" style="cursor:default;">
          <strong>#${index + 1} ${escapeHtml(sourceClass)} verification</strong>
          <span class="row-meta">publisher: ${escapeHtml(publisher)} | template ${escapeHtml(item.template_id || "n/a")}</span>
          <span class="row-meta"><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a></span>
          <span class="row-meta">${escapeHtml(rationale)}</span>
          <div class="action-row" style="margin-top:0.5rem;">
            <button type="button" class="ghost-btn workbench-recommendation-use" data-recommendation-index="${index}">Attach This Source</button>
          </div>
        </div>
      `;
    })
    .join("");

  list.querySelectorAll(".workbench-recommendation-use").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const index = Number(btn.dataset.recommendationIndex);
      if (!Number.isInteger(index) || index < 0 || index >= selectedWorkbenchRecommendations.length) return;
      const recommendation = selectedWorkbenchRecommendations[index];
      await attachWorkbenchRecommendedSource(recommendation);
    });
  });
}

async function loadWorkbenchSources(claimId) {
  if (!claimId || !isUuid(claimId)) {
    selectedWorkbenchSources = [];
    renderWorkbenchSourcesList([]);
    setStatus("workbench-sources-list-status", "");
    return;
  }

  try {
    setStatus("workbench-sources-list-status", "Loading attached sources...");
    const payload = await apiRequest(`${API_EVALUATE_BASE_URL}/${encodeURIComponent(claimId)}/sources`);
    const selectedClaimId = String($("workbench-source-claim-id")?.value || "");
    if (String(claimId) !== selectedClaimId) {
      return;
    }
    selectedWorkbenchSources = payload?.sources || [];
    renderWorkbenchSourcesList(selectedWorkbenchSources);
    setStatus("workbench-sources-list-status", `Loaded ${selectedWorkbenchSources.length} sources.`, "ok");
  } catch (err) {
    selectedWorkbenchSources = [];
    renderWorkbenchSourcesList([]);
    setStatus("workbench-sources-list-status", parseApiError(err, "Failed to load sources."), "bad");
  }
}

async function loadWorkbenchSourceRecommendations(claimId) {
  if (!claimId || !isUuid(claimId)) {
    selectedWorkbenchRecommendations = [];
    renderWorkbenchRecommendationsList([]);
    setStatus("workbench-recommendations-status", "");
    return;
  }

  try {
    setStatus("workbench-recommendations-status", "Loading suggested verification links...");
    const payload = await apiRequest(`${API_EVALUATE_BASE_URL}/${encodeURIComponent(claimId)}/source-recommendations`);
    const selectedClaimId = String($("workbench-source-claim-id")?.value || "");
    if (String(claimId) !== selectedClaimId) {
      return;
    }
    selectedWorkbenchRecommendations = payload?.recommendations || [];
    renderWorkbenchRecommendationsList(selectedWorkbenchRecommendations);
    const missingClasses = payload?.missing_source_classes || [];
    const coverageMessage = `Coverage now: ${payload?.verification_primary_count ?? 0} primary / ${payload?.verification_secondary_count ?? 0} secondary.`;
    const missingMessage = missingClasses.length
      ? ` Missing: ${missingClasses.join(", ")}.`
      : " Minimum verification classes are currently satisfied.";
    setStatus(
      "workbench-recommendations-status",
      `Loaded ${selectedWorkbenchRecommendations.length} suggestions. ${coverageMessage}${missingMessage}`,
      "ok"
    );
  } catch (err) {
    selectedWorkbenchRecommendations = [];
    renderWorkbenchRecommendationsList([]);
    setStatus("workbench-recommendations-status", parseApiError(err, "Failed to load recommendations."), "bad");
  }
}

async function attachWorkbenchRecommendedSource(recommendation) {
  const claimId = $("workbench-source-claim-id")?.value?.trim();
  if (!claimId || !isUuid(claimId)) {
    setStatus("workbench-recommendations-status", "Select a valid claim first.", "bad");
    return;
  }
  const url = String(recommendation?.url || "").trim();
  const sourceClass = recommendation?.source_class;
  const publisher = recommendation?.publisher || null;
  if (!isHttpUrl(url) || !SOURCE_CLASS_VALUES.has(sourceClass)) {
    setStatus("workbench-recommendations-status", "Recommendation payload is invalid. Refresh suggestions and retry.", "bad");
    return;
  }
  try {
    setStatus("workbench-recommendations-status", "Attaching suggested source...");
    await apiRequest(`${API_EVALUATE_BASE_URL}/${encodeURIComponent(claimId)}/sources`, {
      method: "POST",
      body: {
        url,
        source_class: sourceClass,
        source_origin: "verification",
        publisher,
        is_direct_candidate_quote: false,
      },
    });
    setStatus("workbench-recommendations-status", "Suggested source attached.", "ok");
    await Promise.all([
      loadWorkbench(),
      loadEvidenceQueue(),
      loadWorkbenchSources(claimId),
      loadWorkbenchSourceRecommendations(claimId),
    ]);
  } catch (err) {
    const policyMessage = parseSourceAdmissionError(err);
    setStatus(
      "workbench-recommendations-status",
      policyMessage || parseApiError(err, "Failed to attach suggested source."),
      "bad"
    );
  }
}

async function removeWorkbenchSource(sourceId) {
  const claimId = $("workbench-source-claim-id")?.value?.trim();
  if (!claimId || !isUuid(claimId)) {
    setStatus("workbench-sources-list-status", "Select a valid claim first.", "bad");
    return;
  }

  try {
    setStatus("workbench-sources-list-status", "Removing source...");
    const payload = await apiRequest(
      `${API_EVALUATE_BASE_URL}/${encodeURIComponent(claimId)}/sources/${encodeURIComponent(sourceId)}`,
      { method: "DELETE" }
    );
    selectedWorkbenchSources = payload?.sources || [];
    renderWorkbenchSourcesList(selectedWorkbenchSources);
    setStatus("workbench-sources-list-status", "Source removed.", "ok");
    await Promise.all([loadWorkbench(), loadEvidenceQueue()]);
  } catch (err) {
    const deleteMessage = parseSourceDeleteError(err);
    setStatus("workbench-sources-list-status", deleteMessage || parseApiError(err, "Source removal failed."), "bad");
  }
}

async function submitWorkbenchSourceAttach(event) {
  event.preventDefault();
  const claimId = $("workbench-source-claim-id")?.value?.trim();
  const url = $("workbench-source-url")?.value?.trim();
  const sourceClass = $("workbench-source-class")?.value;
  const sourceOrigin = $("workbench-source-origin")?.value;
  const publisher = $("workbench-source-publisher")?.value?.trim();
  const isDirectQuote = !!$("workbench-source-direct-quote")?.checked;

  if (!claimId || !isUuid(claimId)) {
    setStatus("workbench-source-status", "Select a valid claim first.", "bad");
    return;
  }
  if (!url || !isHttpUrl(url)) {
    setStatus("workbench-source-status", "A valid source URL is required.", "bad");
    return;
  }
  if (!SOURCE_CLASS_VALUES.has(sourceClass)) {
    setStatus("workbench-source-status", "Source class must be primary or secondary.", "bad");
    return;
  }
  if (!SOURCE_ORIGIN_VALUES.has(sourceOrigin)) {
    setStatus("workbench-source-status", "Source origin must be candidate or verification.", "bad");
    return;
  }

  try {
    setStatus("workbench-source-status", "Attaching source...");
    await apiRequest(`${API_EVALUATE_BASE_URL}/${encodeURIComponent(claimId)}/sources`, {
      method: "POST",
      body: {
        url,
        source_class: sourceClass,
        source_origin: sourceOrigin,
        publisher: publisher || null,
        is_direct_candidate_quote: isDirectQuote,
      },
    });
    setStatus("workbench-source-status", "Source attached.", "ok");
    await Promise.all([loadWorkbench(), loadEvidenceQueue(), loadWorkbenchSources(claimId), loadWorkbenchSourceRecommendations(claimId)]);
  } catch (err) {
    const policyMessage = parseSourceAdmissionError(err);
    setStatus("workbench-source-status", policyMessage || parseApiError(err, "Source attach failed."), "bad");
  }
}

async function submitWorkbenchReview(event) {
  event.preventDefault();
  const claimId = $("workbench-review-claim-id")?.value?.trim();
  const verdict = $("workbench-review-verdict")?.value;
  const confidenceRaw = $("workbench-review-confidence")?.value;
  const rationale = $("workbench-review-rationale")?.value?.trim();
  const citationNotes = $("workbench-review-citation-notes")?.value?.trim();
  const approvalToken = $("workbench-review-approval-token")?.value?.trim();

  if (!claimId || !verdict || !confidenceRaw || !rationale) {
    setStatus("workbench-review-submit-status", "Claim, verdict, confidence, and rationale are required.", "bad");
    return;
  }
  const confidence = Number(confidenceRaw);
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    setStatus("workbench-review-submit-status", "Confidence must be between 0 and 1.", "bad");
    return;
  }

  try {
    setStatus("workbench-review-submit-status", "Submitting evaluation...");
    await apiRequest(`${API_EVALUATE_BASE_URL}/${encodeURIComponent(claimId)}/evaluate`, {
      method: "POST",
      body: {
        verdict,
        confidence,
        rationale,
        citation_notes: citationNotes || null,
        approval_token: approvalToken || null,
      },
    });
    setStatus("workbench-review-submit-status", "Evaluation saved.", "ok");
    await Promise.all([loadWorkbench(), loadReviewQueue(), loadPublishQueue()]);
  } catch (err) {
    const dualControlMessage = parseEvaluationDualControlError(err);
    setStatus("workbench-review-submit-status", dualControlMessage || parseApiError(err, "Evaluation failed."), "bad");
  }
}

async function submitWorkbenchPublishAction(event) {
  event.preventDefault();
  if (!isAdminIdentity()) {
    setStatus("workbench-publish-status", "Publish actions are admin-only.", "bad");
    return;
  }
  const claimId = $("workbench-publish-claim-id")?.value?.trim();
  const action = $("workbench-publish-action")?.value;
  if (!claimId || !action) {
    setStatus("workbench-publish-status", "Select a claim and publish action first.", "bad");
    return;
  }
  const selectedRow = workbenchRows.find((item) => String(item.claim_id) === String(claimId));
  if (!selectedRow) {
    setStatus(
      "workbench-publish-status",
      "Selected claim is not in the current Workbench queue. Refresh and reselect.",
      "bad"
    );
    return;
  }

  try {
    setStatus("workbench-publish-status", "Submitting publish action...");
    await apiRequest(`${API_EVALUATE_BASE_URL}/${encodeURIComponent(claimId)}/${encodeURIComponent(action)}`, {
      method: "POST",
    });
    setStatus("workbench-publish-status", `Claim ${action} action completed.`, "ok");
    await Promise.all([loadWorkbench(), loadPublishQueue(), loadAuditList()]);
  } catch (err) {
    const dualControlMessage = parsePublishDualControlError(err, action);
    setStatus("workbench-publish-status", dualControlMessage || parseApiError(err, "Publish action failed."), "bad");
  }
}

function renderReviewList(rows) {
  const list = $("review-list");
  if (!list) return;
  if (!rows.length) {
    list.innerHTML = `<p class="status-text">No review-ready claims matched the current filters.</p>`;
    return;
  }

  list.innerHTML = rows
    .map((row) => {
      const selected = String(row.claim_id) === selectedReviewClaimId ? "is-selected" : "";
      const verdict = row.latest_verdict || "none";
      const tone = verdictClass(verdict);
      return `
        <button type="button" class="row-btn ${selected}" data-claim-id="${escapeHtml(row.claim_id)}">
          <strong>${escapeHtml(row.issue_tag || "Unlabeled issue")}</strong>
          <span class="row-meta ${tone}">${escapeHtml(row.candidate_name)} | latest ${escapeHtml(verdict)} | claim ${escapeHtml(shortId(row.claim_id))}</span>
          <span class="row-meta">Primary ${escapeHtml(String(row.primary_source_count))} | Secondary ${escapeHtml(String(row.secondary_source_count))} | Verification ${escapeHtml(String(row.verification_source_count))}</span>
        </button>
      `;
    })
    .join("");

  list.querySelectorAll(".row-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const claimId = btn.dataset.claimId;
      if (!claimId) return;
      selectReviewClaim(claimId);
      renderReviewList(rows);
    });
  });
}

function selectReviewClaim(claimId) {
  const row = reviewQueueRows.find((item) => String(item.claim_id) === String(claimId));
  if (!row) return;
  selectedReviewClaimId = String(claimId);
  $("review-claim-id").value = String(row.claim_id);
  $("review-verdict").value = "supported";
  $("review-confidence").value = "0.70";
  $("review-rationale").value = "";
  $("review-citation-notes").value = "";
  const latestAt = row.latest_evaluated_at ? ` | latest ${formatDateTime(row.latest_evaluated_at)}` : "";
  setStatus(
    "review-preview",
    `${row.candidate_name} (${row.candidate_party || "Unlisted"}) | ${row.issue_tag || "Unlabeled issue"}${latestAt}\n${row.claim_text}`
  );
}

async function loadReviewQueue() {
  try {
    setStatus("review-list-status", "Loading review queue...");
    const limit = normalizeOptionalInt($("review-filter-limit")?.value) || 200;
    const requireMinimumEvidence = !!$("review-filter-require-min-evidence")?.checked;
    const params = buildRaceFilterParams("review-filter", {
      require_minimum_evidence: requireMinimumEvidence,
      limit,
    });
    const rows = await apiRequest(`${API_REVIEW_QUEUE_URL}?${params.toString()}`, { requireAuth: false });
    reviewQueueRows = rows || [];
    renderReviewList(reviewQueueRows);
    if (reviewQueueRows.length) {
      const keepSelected = reviewQueueRows.some((row) => String(row.claim_id) === selectedReviewClaimId);
      selectReviewClaim(keepSelected ? selectedReviewClaimId : String(reviewQueueRows[0].claim_id));
      renderReviewList(reviewQueueRows);
    } else {
      selectedReviewClaimId = "";
      $("review-claim-id").value = "";
      setStatus("review-preview", "Select a claim from the queue to evaluate.");
    }
    setStatus("review-list-status", `Loaded ${reviewQueueRows.length} queue items.`, "ok");
  } catch (err) {
    reviewQueueRows = [];
    renderReviewList([]);
    setStatus("review-list-status", parseApiError(err, "Failed to load review queue."), "bad");
  }
}

async function submitReview(event) {
  event.preventDefault();
  const claimId = $("review-claim-id")?.value?.trim();
  const verdict = $("review-verdict")?.value;
  const confidenceRaw = $("review-confidence")?.value;
  const rationale = $("review-rationale")?.value?.trim();
  const citationNotes = $("review-citation-notes")?.value?.trim();
  const approvalToken = $("review-approval-token")?.value?.trim();

  if (!claimId || !verdict || !confidenceRaw || !rationale) {
    setStatus("review-submit-status", "Claim, verdict, confidence, and rationale are required.", "bad");
    return;
  }

  const confidence = Number(confidenceRaw);
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    setStatus("review-submit-status", "Confidence must be between 0 and 1.", "bad");
    return;
  }

  try {
    setStatus("review-submit-status", "Submitting evaluation...");
    await apiRequest(`${API_EVALUATE_BASE_URL}/${encodeURIComponent(claimId)}/evaluate`, {
      method: "POST",
      body: {
        verdict,
        confidence,
        rationale,
        citation_notes: citationNotes || null,
        approval_token: approvalToken || null,
      },
    });
    setStatus("review-submit-status", "Evaluation saved.", "ok");
    await Promise.all([loadReviewQueue(), loadPublishQueue()]);
  } catch (err) {
    const dualControlMessage = parseEvaluationDualControlError(err);
    setStatus("review-submit-status", dualControlMessage || parseApiError(err, "Review submission failed."), "bad");
  }
}

function renderEvidenceQueueList(rows) {
  const list = $("evidence-list");
  if (!list) return;
  if (!rows.length) {
    list.innerHTML = `<p class="status-text">No claims found for current evidence filters.</p>`;
    return;
  }

  list.innerHTML = rows
    .map((row) => {
      const selected = String(row.claim_id) === selectedEvidenceClaimId ? "is-selected" : "";
      const missing = (row.missing_source_classes || []).join(", ") || "none";
      return `
        <button type="button" class="row-btn ${selected}" data-claim-id="${escapeHtml(row.claim_id)}">
          <strong>${escapeHtml(row.issue_tag || "Unlabeled issue")}</strong>
          <span class="row-meta">${escapeHtml(row.candidate_name)} (${escapeHtml(row.candidate_party || "Unlisted")}) | claim ${escapeHtml(shortId(row.claim_id))}</span>
          <span class="row-meta">Primary ${escapeHtml(String(row.primary_source_count))} | Secondary ${escapeHtml(String(row.secondary_source_count))} | Candidate ${escapeHtml(String(row.candidate_source_count))} | Verification ${escapeHtml(String(row.verification_source_count))}</span>
          <span class="row-meta">Missing source classes: ${escapeHtml(missing)}</span>
        </button>
      `;
    })
    .join("");

  list.querySelectorAll(".row-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const claimId = btn.dataset.claimId;
      if (!claimId) return;
      selectEvidenceClaim(claimId);
      renderEvidenceQueueList(rows);
    });
  });
}

function selectEvidenceClaim(claimId) {
  const row = evidenceQueueRows.find((item) => String(item.claim_id) === String(claimId));
  if (!row) return;
  selectedEvidenceClaimId = String(claimId);
  $("evidence-claim-id").value = String(row.claim_id);
  renderJsonDetail("evidence-detail-json", "evidence-detail-empty", row);
  setStatus("evidence-copy-status", "");
}

async function loadEvidenceQueue() {
  try {
    setStatus("evidence-list-status", "Loading evidence queue...");
    const includeOnlyMissing = !!$("evidence-filter-include-only-missing")?.checked;
    const limit = normalizeOptionalInt($("evidence-filter-limit")?.value) || 200;
    const params = buildRaceFilterParams("evidence-filter", {
      include_only_missing: includeOnlyMissing,
      limit,
    });
    const rows = await apiRequest(`${API_EVIDENCE_QUEUE_URL}?${params.toString()}`, { requireAuth: false });
    evidenceQueueRows = rows || [];
    renderEvidenceQueueList(evidenceQueueRows);
    if (evidenceQueueRows.length) {
      const keepSelected = evidenceQueueRows.some((row) => String(row.claim_id) === selectedEvidenceClaimId);
      selectedEvidenceClaimId = keepSelected ? selectedEvidenceClaimId : String(evidenceQueueRows[0].claim_id);
      selectEvidenceClaim(selectedEvidenceClaimId);
      renderEvidenceQueueList(evidenceQueueRows);
    } else {
      selectedEvidenceClaimId = "";
      $("evidence-claim-id").value = "";
      renderJsonDetail("evidence-detail-json", "evidence-detail-empty", null);
      setStatus("evidence-copy-status", "");
    }
    setStatus("evidence-list-status", `Loaded ${evidenceQueueRows.length} queue items.`, "ok");
  } catch (err) {
    evidenceQueueRows = [];
    renderEvidenceQueueList([]);
    renderJsonDetail("evidence-detail-json", "evidence-detail-empty", null);
    setStatus("evidence-list-status", parseApiError(err, "Failed to load evidence queue."), "bad");
  }
}

async function copyEvidenceClaimId() {
  const claimId = $("evidence-claim-id")?.value?.trim();
  if (!claimId) {
    setStatus("evidence-copy-status", "Select a claim row first.", "bad");
    return;
  }

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(claimId);
    } else {
      $("evidence-claim-id")?.select();
      document.execCommand("copy");
    }
    setStatus("evidence-copy-status", "Claim ID copied.", "ok");
  } catch (_err) {
    setStatus("evidence-copy-status", "Clipboard copy failed. Copy manually from the field.", "bad");
  }
}

function getBulkAttachExampleText() {
  return JSON.stringify(BULK_ATTACH_EXAMPLE, null, 2);
}

function parseJsonTextarea(text, fieldName) {
  try {
    return { value: JSON.parse(text), error: null };
  } catch (err) {
    return { value: null, error: `${fieldName} is not valid JSON: ${err.message}` };
  }
}

function validateBulkSourceAttachItems(items) {
  const errors = [];
  if (!Array.isArray(items)) {
    errors.push("Payload.items must be a JSON array.");
    return errors;
  }

  items.forEach((item, index) => {
    const prefix = `Item ${index + 1}`;
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      errors.push(`${prefix}: must be an object.`);
      return;
    }

    if (!isUuid(item.claim_id)) errors.push(`${prefix}: claim_id must be a valid UUID.`);
    if (!isHttpUrl(item.url)) errors.push(`${prefix}: url must be an http/https URL.`);
    if (!SOURCE_CLASS_VALUES.has(item.source_class)) {
      errors.push(`${prefix}: source_class must be one of ${Array.from(SOURCE_CLASS_VALUES).join(", ")}.`);
    }
    if (!SOURCE_ORIGIN_VALUES.has(item.source_origin)) {
      errors.push(`${prefix}: source_origin must be one of ${Array.from(SOURCE_ORIGIN_VALUES).join(", ")}.`);
    }
    if (typeof item.quality_score !== "number" || item.quality_score < 0 || item.quality_score > 1) {
      errors.push(`${prefix}: quality_score must be a number between 0 and 1.`);
    }
    if (item.publisher != null && String(item.publisher).length > 255) {
      errors.push(`${prefix}: publisher must be 255 characters or fewer.`);
    }
    if (item.is_direct_candidate_quote != null && typeof item.is_direct_candidate_quote !== "boolean") {
      errors.push(`${prefix}: is_direct_candidate_quote must be boolean when provided.`);
    }
  });

  return errors;
}

function renderBulkAttachResults(response) {
  const summary = $("bulk-attach-summary");
  const list = $("bulk-attach-results");
  if (!summary || !list) return;
  if (!response) {
    summary.textContent = "Run a bulk attach request to view result summary.";
    summary.classList.remove("status-ok", "status-bad");
    list.innerHTML = "";
    return;
  }

  const tone = response.failed > 0 ? "bad" : "ok";
  setStatus(
    "bulk-attach-summary",
    `Total: ${response.total} | Attached: ${response.attached} | Failed: ${response.failed}`,
    tone
  );

  const results = Array.isArray(response.results) ? response.results : [];
  if (!results.length) {
    list.innerHTML = `<p class="status-text">No result items returned.</p>`;
    return;
  }

  list.innerHTML = results
    .map((item) => {
      const statusTone = item.status === "attached" ? "row-tone-ok" : "row-tone-bad";
      const errorText = item.error?.message ? ` | ${item.error.message}` : "";
      return `
        <div class="row-btn">
          <strong class="${statusTone}">${escapeHtml(item.status || "unknown")}</strong>
          <span class="row-meta">claim ${escapeHtml(shortId(item.claim_id))} | ${escapeHtml(item.source_origin || "unknown")} ${escapeHtml(item.source_class || "unknown")}</span>
          <span class="row-meta">${escapeHtml(item.url || "")}${escapeHtml(errorText)}</span>
        </div>
      `;
    })
    .join("");
}

function validateBulkAttachTextarea() {
  const raw = $("bulk-attach-json")?.value || "";
  const approvalToken = normalizeOptionalText($("bulk-approval-token")?.value);
  if (!approvalToken) {
    setStatus("bulk-attach-status", "Approval token is required.", "bad");
    return null;
  }
  const parsed = parseJsonTextarea(raw, "Attach payload");
  if (parsed.error) {
    setStatus("bulk-attach-status", parsed.error, "bad");
    return null;
  }
  if (!parsed.value || typeof parsed.value !== "object" || Array.isArray(parsed.value)) {
    setStatus("bulk-attach-status", "Validation failed: Payload must be an object with approval_token and items.", "bad");
    return null;
  }
  const approvalInPayload = normalizeOptionalText(parsed.value.approval_token);
  const items = parsed.value.items;
  if (!approvalInPayload) {
    setStatus("bulk-attach-status", "Validation failed: approval_token is required in payload.", "bad");
    return null;
  }
  const errors = validateBulkSourceAttachItems(items);
  if (errors.length) {
    setStatus("bulk-attach-status", `Validation failed: ${errors[0]}`, "bad");
    return null;
  }
  if (approvalInPayload !== approvalToken) {
    setStatus(
      "bulk-attach-status",
      "Validation failed: form Approval Token must match payload approval_token.",
      "bad"
    );
    return null;
  }
  setStatus("bulk-attach-status", `Validation passed for ${items.length} item(s).`, "ok");
  return parsed.value;
}

async function submitBulkAttach(event) {
  event.preventDefault();
  const payload = validateBulkAttachTextarea();
  if (!payload) return;

  try {
    setStatus("bulk-attach-status", "Submitting bulk attach...");
    const response = await apiRequest(API_BULK_SOURCE_ATTACH_URL, {
      method: "POST",
      body: payload,
    });
    renderBulkAttachResults(response);
    const tone = response.failed > 0 ? "bad" : "ok";
    setStatus("bulk-attach-status", "Bulk attach request completed.", tone);
    await Promise.all([loadEvidenceQueue(), loadAuditList()]);
  } catch (err) {
    renderBulkAttachResults(null);
    const dualControlMessage = parseBulkAttachDualControlError(err);
    setStatus("bulk-attach-status", dualControlMessage || parseApiError(err, "Bulk attach request failed."), "bad");
  }
}

function renderProposalList(rows) {
  const list = $("proposal-list");
  if (!list) return;
  if (!rows.length) {
    list.innerHTML = `<p class="status-text">No proposals found for current filters.</p>`;
    return;
  }

  list.innerHTML = rows
    .map((row) => {
      const selected = String(row.id) === selectedProposalId ? "is-selected" : "";
      return `
        <button type="button" class="row-btn ${selected}" data-proposal-id="${escapeHtml(row.id)}">
          <strong>${escapeHtml(row.proposal_type)}</strong>
          <span class="row-meta">${escapeHtml(row.status)} | claim ${escapeHtml(shortId(row.claim_id))} | ${escapeHtml(row.proposed_by)}</span>
          <span class="row-meta">${escapeHtml(formatDateTime(row.created_at))}</span>
        </button>
      `;
    })
    .join("");

  list.querySelectorAll(".row-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const proposalId = btn.dataset.proposalId;
      if (!proposalId) return;
      selectedProposalId = proposalId;
      renderProposalList(rows);
      loadProposalDetail(proposalId);
    });
  });
}

function renderPowerAdminProposalReview(row) {
  const container = $("proposal-power-admin");
  const status = $("proposal-power-admin-status");
  const itemsEl = $("proposal-power-admin-items");
  const guidance = $("proposal-power-admin-guidance");
  if (!container || !status || !itemsEl || !guidance) return;

  if (!row || !SOURCE_PROPOSAL_TYPES.has(String(row.proposal_type || ""))) {
    container.hidden = true;
    return;
  }

  container.hidden = false;
  const payload = row.proposal_payload || {};
  const sourceOrigin = String(payload.source_origin || "").trim() || "missing";
  const sourceClass = String(payload.source_class || "").trim() || "missing";
  const proposalType = String(row.proposal_type || "").trim();
  const expectedOrigin = proposalType === "verification_source_suggestion" ? "verification" : "candidate";
  const publisher = normalizeOptionalText(payload.publisher);
  const quality = typeof payload.quality_score === "number" ? payload.quality_score : null;
  const claimContext = `claim ${shortId(row.claim_id)} | status ${row.status}`;

  const checks = [
    { ok: sourceOrigin !== "missing", label: `source_origin recorded: ${sourceOrigin}` },
    { ok: sourceOrigin === expectedOrigin, label: `source_origin matches proposal type (${expectedOrigin})` },
    { ok: sourceClass !== "missing", label: `source_class recorded: ${sourceClass}` },
    { ok: !!publisher, label: `publisher recorded${publisher ? `: ${publisher}` : ""}` },
    { ok: quality != null, label: `quality_score recorded${quality != null ? `: ${quality}` : ""}` },
  ];

  status.textContent = `Power-admin source/bundle review for ${claimContext}.`;
  itemsEl.innerHTML = checks
    .map((item) => `<li class="${item.ok ? "ok" : "bad"}">${item.ok ? "pass" : "needs review"}: ${escapeHtml(item.label)}</li>`)
    .join("");

  guidance.textContent =
    "Action guidance: approve after payload review, reject when admission fields are incomplete, apply only after independent approval and policy readiness.";
}

function renderProposalClaimContext(row) {
  const container = $("proposal-claim-context");
  const statusEl = $("proposal-claim-context-status");
  const evidenceEl = $("proposal-claim-context-evidence");
  const evaluationEl = $("proposal-claim-context-evaluation");
  if (!container || !statusEl || !evidenceEl || !evaluationEl) return;

  const context = row?.claim_context;
  if (!context) {
    container.hidden = true;
    return;
  }
  container.hidden = false;

  const primary = Number(context.verification_primary_count || 0);
  const secondary = Number(context.verification_secondary_count || 0);
  const missing = Array.isArray(context.missing_source_classes) ? context.missing_source_classes : [];
  const sufficient = !!context.verification_evidence_sufficient;
  const verdict = context.latest_verdict || "none";
  const confidence = context.latest_confidence == null ? "n/a" : String(context.latest_confidence);
  const reviewer = context.latest_reviewer_id || "unassigned";
  const evaluatedAt = context.latest_evaluated_at ? formatDateTime(context.latest_evaluated_at) : "n/a";

  statusEl.textContent = sufficient
    ? "Verification evidence snapshot is sufficient for primary and secondary classes."
    : "Verification evidence snapshot is currently missing required class coverage.";
  statusEl.classList.remove("status-ok", "status-bad");
  statusEl.classList.add(sufficient ? "status-ok" : "status-bad");

  evidenceEl.innerHTML = [
    `verification primary count: ${primary}`,
    `verification secondary count: ${secondary}`,
    `missing source classes: ${missing.length ? missing.join(", ") : "none"}`,
    `evidence sufficiency gate: ${sufficient ? "passed" : "blocked"}`,
  ]
    .map((line) => `<li>${escapeHtml(line)}</li>`)
    .join("");

  evaluationEl.innerHTML = [
    `latest verdict: ${verdict}`,
    `latest confidence: ${confidence}`,
    `latest reviewer: ${reviewer}`,
    `latest evaluated at: ${evaluatedAt}`,
    `latest rationale: ${context.latest_rationale || "none"}`,
    `latest citation notes: ${context.latest_citation_notes || "none"}`,
  ]
    .map((line) => `<li>${escapeHtml(line)}</li>`)
    .join("");
}

function loadProposalDetail(proposalId) {
  const row = proposalRows.find((item) => String(item.id) === String(proposalId));
  if (!row) {
    renderJsonDetail("proposal-detail-json", "proposal-detail-empty", null);
    renderPowerAdminProposalReview(null);
    renderProposalClaimContext(null);
    return;
  }
  $("proposal-id").value = String(row.id);
  renderJsonDetail("proposal-detail-json", "proposal-detail-empty", row);
  renderPowerAdminProposalReview(row);
  renderProposalClaimContext(row);
}

async function loadProposalList() {
  try {
    setStatus("proposal-list-status", "Loading proposals...");
    const status = normalizeOptionalText($("proposal-filter-status")?.value);
    const proposalType = normalizeOptionalText($("proposal-filter-type")?.value);
    const limit = normalizeOptionalInt($("proposal-filter-limit")?.value) || 200;
    const params = buildRaceFilterParams("proposal-filter", {
      status,
      proposal_type: proposalType,
      limit,
    });
    const rows = await apiRequest(`${API_PROPOSALS_URL}?${params.toString()}`);
    proposalRows = rows || [];
    renderProposalList(proposalRows);
    if (proposalRows.length) {
      const keepSelected = proposalRows.some((row) => String(row.id) === selectedProposalId);
      selectedProposalId = keepSelected ? selectedProposalId : String(proposalRows[0].id);
      loadProposalDetail(selectedProposalId);
      renderProposalList(proposalRows);
    } else {
      selectedProposalId = "";
      $("proposal-id").value = "";
      renderJsonDetail("proposal-detail-json", "proposal-detail-empty", null);
      renderPowerAdminProposalReview(null);
      renderProposalClaimContext(null);
    }
    setStatus("proposal-list-status", `Loaded ${proposalRows.length} proposals.`, "ok");
  } catch (err) {
    proposalRows = [];
    renderProposalList([]);
    renderJsonDetail("proposal-detail-json", "proposal-detail-empty", null);
    renderPowerAdminProposalReview(null);
    renderProposalClaimContext(null);
    setStatus("proposal-list-status", parseApiError(err, "Failed to load proposals."), "bad");
  }
}

async function submitProposalAction(event) {
  event.preventDefault();
  const proposalId = $("proposal-id")?.value?.trim();
  const action = $("proposal-action")?.value;
  const reviewNotes = $("proposal-review-notes")?.value?.trim() || null;
  if (!proposalId || !action) {
    setStatus("proposal-action-status", "Select a proposal and action.", "bad");
    return;
  }

  try {
    setStatus("proposal-action-status", "Submitting proposal action...");
    await apiRequest(`${API_PROPOSALS_URL}/${encodeURIComponent(proposalId)}/${encodeURIComponent(action)}`, {
      method: "POST",
      body: { review_notes: reviewNotes },
    });
    setStatus("proposal-action-status", "Proposal action saved.", "ok");
    await Promise.all([loadProposalList(), loadAuditList()]);
  } catch (err) {
    setStatus("proposal-action-status", parseApiError(err, "Proposal action failed."), "bad");
  }
}

function buildPublishChecklist(row) {
  const failures = Array.isArray(row?.publish_gate_failures) ? row.publish_gate_failures : [];
  const hasFailure = (code) => failures.includes(code);
  return [
    { ok: !hasFailure("latest_rationale_required"), label: "Rationale present and review-ready" },
    { ok: !hasFailure("latest_citation_notes_required"), label: "Citation notes present" },
    { ok: !hasFailure("verification_primary_source_required"), label: "Verification primary source attached" },
    { ok: !hasFailure("verification_secondary_source_required"), label: "Verification secondary source attached" },
    { ok: !hasFailure("latest_evaluation_moderation_policy_violation"), label: "Moderation policy clean" },
    { ok: !!row?.publish_gate_passed, label: "Publish gate passed" },
  ];
}

function renderPublishChecklist(row) {
  const container = $("publish-checklist");
  const itemsEl = $("publish-checklist-items");
  const status = $("publish-checklist-status");
  const actionSelect = $("publish-action");
  const actionButton = document.querySelector("#publish-action-form button[type='submit']");
  if (!container || !itemsEl || !status || !actionSelect || !actionButton) return;

  if (!row) {
    container.hidden = true;
    actionButton.disabled = false;
    return;
  }

  container.hidden = false;
  const checklist = buildPublishChecklist(row);
  itemsEl.innerHTML = checklist
    .map((item) => `<li class="${item.ok ? "ok" : "bad"}">${item.ok ? "pass" : "blocked"}: ${escapeHtml(item.label)}</li>`)
    .join("");
  const allPassed = checklist.every((item) => item.ok);
  const publishSelected = actionSelect.value === "publish";
  const publishBlocked = publishSelected && !allPassed;
  actionButton.disabled = publishBlocked;
  status.textContent = allPassed
    ? "Checklist complete. Publish signoff can proceed."
    : "Checklist incomplete. Finish required review items before publish.";
  status.classList.remove("status-ok", "status-bad");
  status.classList.add(allPassed ? "status-ok" : "status-bad");
}

function renderPublishList(rows) {
  const list = $("publish-list");
  if (!list) return;
  if (!rows.length) {
    list.innerHTML = `<p class="status-text">No claims found for publish controls with current filters.</p>`;
    return;
  }

  list.innerHTML = rows
    .map((row) => {
      const selected = String(row.claim_id) === selectedPublishClaimId ? "is-selected" : "";
      const gate = row.publish_gate_passed ? "gate passed" : `gate blocked (${(row.publish_gate_failures || []).join(", ") || "unknown"})`;
      const state = row.is_published ? "published" : "not published";
      return `
        <button type="button" class="row-btn ${selected}" data-claim-id="${escapeHtml(row.claim_id)}">
          <strong>${escapeHtml(row.issue_tag || "Unlabeled issue")}</strong>
          <span class="row-meta">${escapeHtml(row.candidate_name)} | claim ${escapeHtml(shortId(row.claim_id))} | ${escapeHtml(state)}</span>
          <span class="row-meta">${escapeHtml(gate)}</span>
        </button>
      `;
    })
    .join("");

  list.querySelectorAll(".row-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const claimId = btn.dataset.claimId;
      if (!claimId) return;
      selectedPublishClaimId = claimId;
      renderPublishList(rows);
      loadPublishDetail(claimId);
    });
  });
}

function loadPublishDetail(claimId) {
  const row = publishQueueRows.find((item) => String(item.claim_id) === String(claimId));
  if (!row) {
    renderJsonDetail("publish-detail-json", "publish-detail-empty", null);
    renderPublishChecklist(null);
    return;
  }
  $("publish-claim-id").value = String(row.claim_id);
  $("publish-action").value = row.is_published ? "unpublish" : "publish";
  renderJsonDetail("publish-detail-json", "publish-detail-empty", row);
  renderPublishChecklist(row);
}

async function loadPublishQueue() {
  try {
    setStatus("publish-list-status", "Loading publish queue...");
    const includePublished = !!$("publish-filter-include-published")?.checked;
    const onlyGatePassed = !!$("publish-filter-only-gate-passed")?.checked;
    const limit = normalizeOptionalInt($("publish-filter-limit")?.value) || 200;
    const params = buildRaceFilterParams("publish-filter", {
      include_already_published: includePublished,
      only_gate_passed: onlyGatePassed,
      limit,
    });
    const rows = await apiRequest(`${API_PUBLISH_QUEUE_URL}?${params.toString()}`);
    publishQueueRows = rows || [];
    renderPublishList(publishQueueRows);
    if (publishQueueRows.length) {
      const keepSelected = publishQueueRows.some((row) => String(row.claim_id) === selectedPublishClaimId);
      selectedPublishClaimId = keepSelected ? selectedPublishClaimId : String(publishQueueRows[0].claim_id);
      loadPublishDetail(selectedPublishClaimId);
      renderPublishList(publishQueueRows);
    } else {
      selectedPublishClaimId = "";
      $("publish-claim-id").value = "";
      renderJsonDetail("publish-detail-json", "publish-detail-empty", null);
      renderPublishChecklist(null);
    }
    setStatus("publish-list-status", `Loaded ${publishQueueRows.length} publish queue claims.`, "ok");
  } catch (err) {
    publishQueueRows = [];
    selectedPublishClaimId = "";
    if ($("publish-claim-id")) $("publish-claim-id").value = "";
    renderPublishList([]);
    renderJsonDetail("publish-detail-json", "publish-detail-empty", null);
    renderPublishChecklist(null);
    setStatus("publish-list-status", parseApiError(err, "Failed to load publish queue."), "bad");
  }
}

async function submitPublishAction(event) {
  event.preventDefault();
  const claimId = $("publish-claim-id")?.value?.trim();
  const action = $("publish-action")?.value;
  if (!claimId || !action) {
    setStatus("publish-action-status", "Select a claim and action first.", "bad");
    return;
  }
  const selectedRow = publishQueueRows.find((item) => String(item.claim_id) === String(claimId));
  if (!selectedRow) {
    setStatus(
      "publish-action-status",
      "Selected claim is not in the current publish queue. Refresh and reselect.",
      "bad"
    );
    return;
  }

  try {
    setStatus("publish-action-status", "Submitting publish action...");
    await apiRequest(`${API_EVALUATE_BASE_URL}/${encodeURIComponent(claimId)}/${encodeURIComponent(action)}`, {
      method: "POST",
    });
    setStatus("publish-action-status", `Claim ${action} action completed.`, "ok");
    await Promise.all([loadPublishQueue(), loadAuditList()]);
  } catch (err) {
    const dualControlMessage = parsePublishDualControlError(err, action);
    setStatus("publish-action-status", dualControlMessage || parseApiError(err, "Publish action failed."), "bad");
  }
}

async function handleSignIn(event) {
  event.preventDefault();
  try {
    setStatus("auth-status", "Signing in...");
    const email = $("auth-email").value.trim();
    const password = $("auth-password").value;

    const login = await apiRequest(API_AUTH_LOGIN_URL, {
      method: "POST",
      body: { email, password },
      requireAuth: false,
    });
    authToken = login.access_token;
    localStorage.setItem(AUTH_STORAGE_KEY, authToken);

    const ok = await verifyAdminIdentity();
    if (!ok) return;

    const role = identity?.role || "reviewer";
    setStatus("auth-status", `${role === "admin" ? "Admin" : "Reviewer"} sign-in successful.`, "ok");
    if (role === "admin") {
      await loadAdminJobMetadata();
    } else {
      adminJobMetadata = null;
    }
    const loaders = getWorkspaceLoadersForRole(role);
    await Promise.all(loaders.map((loader) => loader()));
  } catch (err) {
    setStatus("auth-status", parseApiError(err, "Sign in failed."), "bad");
  }
}

function bindEvents() {
  $("auth-form")?.addEventListener("submit", handleSignIn);
  $("approval-token-form")?.addEventListener("submit", requestApprovalToken);
  $("approval-token-copy")?.addEventListener("click", copyApprovalToken);
  $("sign-out")?.addEventListener("click", () => clearSession());

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => setActiveTab(tab.dataset.tab || "candidates"));
  });

  $("candidate-filters")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadCandidateList();
  });
  $("reload-candidates")?.addEventListener("click", async () => loadCandidateList());
  $("candidate-edit-form")?.addEventListener("submit", saveCandidate);
  $("candidate-create-form")?.addEventListener("submit", createCandidate);

  $("intake-profiles-refresh")?.addEventListener("click", async () => loadIntakeProfiles());
  $("intake-profile-edit-form")?.addEventListener("submit", saveIntakeProfile);
  $("intake-profile-create-form")?.addEventListener("submit", createIntakeProfile);

  $("workbench-filter-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadWorkbench();
  });
  $("workbench-refresh")?.addEventListener("click", async () => loadWorkbench());
  $("workbench-show-raw-failures")?.addEventListener("change", () => {
    const row = workbenchRows.find((item) => String(item.claim_id) === String(selectedWorkbenchClaimId));
    renderWorkbenchRawFailures(row || null);
  });
  $("workbench-source-form")?.addEventListener("submit", submitWorkbenchSourceAttach);
  $("workbench-recommendations-refresh")?.addEventListener("click", async () => {
    const claimId = $("workbench-source-claim-id")?.value?.trim();
    await loadWorkbenchSourceRecommendations(claimId || "");
  });
  $("workbench-review-form")?.addEventListener("submit", submitWorkbenchReview);
  $("workbench-publish-form")?.addEventListener("submit", submitWorkbenchPublishAction);

  $("review-filter-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadReviewQueue();
  });
  $("review-refresh")?.addEventListener("click", async () => loadReviewQueue());
  $("review-form")?.addEventListener("submit", submitReview);

  $("evidence-filter-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadEvidenceQueue();
  });
  $("evidence-refresh")?.addEventListener("click", async () => loadEvidenceQueue());
  $("evidence-copy-claim-id")?.addEventListener("click", copyEvidenceClaimId);

  $("bulk-load-example")?.addEventListener("click", () => {
    const textarea = $("bulk-attach-json");
    if (textarea) textarea.value = getBulkAttachExampleText();
    setStatus("bulk-attach-status", "Loaded bulk attach example payload.", "ok");
  });
  $("bulk-validate-json")?.addEventListener("click", () => validateBulkAttachTextarea());
  $("bulk-clear-json")?.addEventListener("click", () => {
    const textarea = $("bulk-attach-json");
    if (textarea) textarea.value = "";
    renderBulkAttachResults(null);
    setStatus("bulk-attach-status", "Cleared bulk attach payload.", "ok");
  });
  $("bulk-attach-form")?.addEventListener("submit", submitBulkAttach);

  $("proposal-filter-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadProposalList();
  });
  $("proposal-refresh")?.addEventListener("click", async () => loadProposalList());
  $("proposal-action-form")?.addEventListener("submit", submitProposalAction);

  $("publish-filter-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadPublishQueue();
  });
  $("publish-refresh")?.addEventListener("click", async () => loadPublishQueue());
  $("publish-action-form")?.addEventListener("submit", submitPublishAction);
  $("publish-action")?.addEventListener("change", () => {
    const row = publishQueueRows.find((item) => String(item.claim_id) === String(selectedPublishClaimId));
    renderPublishChecklist(row || null);
  });

  $("job-type")?.addEventListener("change", () => refreshJobTypeSpecificControls());
  $("job-profile-id")?.addEventListener("change", () => refreshJobTypeSpecificControls());
  $("job-statement-batch")?.addEventListener("change", () => syncJobPayloadFromTypedControls());
  $("job-dry-run")?.addEventListener("change", () => syncJobPayloadFromTypedControls());
  $("job-create-form")?.addEventListener("submit", runJob);
  $("jobs-filter-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadJobsList();
  });
  $("jobs-refresh")?.addEventListener("click", async () => loadJobsList());
  $("job-detail-refresh")?.addEventListener("click", async () => {
    if (selectedJobId) await loadJobDetail(selectedJobId);
  });
  $("worker-health-refresh")?.addEventListener("click", async () => loadWorkerHealth());

  $("audit-filter-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadAuditList();
  });
  $("audit-refresh")?.addEventListener("click", async () => loadAuditList());
  $("audit-detail-refresh")?.addEventListener("click", async () => {
    if (selectedAuditId) await loadAuditDetail(selectedAuditId);
  });
}

async function init() {
  const bulkAttachField = $("bulk-attach-json");
  if (bulkAttachField && !bulkAttachField.value.trim()) {
    bulkAttachField.value = getBulkAttachExampleText();
  }
  renderBulkAttachResults(null);

  bindEvents();
  setActiveTab("workbench");
  showSignedInControls(false);
  showWorkspace(false);

  if (!authToken) return;
  try {
    const ok = await verifyAdminIdentity();
    if (!ok) return;
    const role = identity?.role || "reviewer";
    if (role === "admin") {
      await loadAdminJobMetadata();
    } else {
      adminJobMetadata = null;
    }
    const loaders = getWorkspaceLoadersForRole(role);
    await Promise.all(loaders.map((loader) => loader()));
  } catch (_err) {
    clearSession();
    setStatus("auth-status", "Saved token is invalid. Sign in again.", "bad");
  }
}

init();
