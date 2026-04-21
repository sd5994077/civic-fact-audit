const API_COMPARE_URL = "/api/v1/compare?state=TX&office=US%20Senate&election_cycle=2026&limit_issues=8";
const API_REVIEW_QUEUE_URL =
  "/api/v1/claims/review-queue?state=TX&office=US%20Senate&election_cycle=2026&require_minimum_evidence=true&limit=50";
const API_EVALUATE_BASE_URL = "/api/v1/claims";

let reviewQueueRows = [];

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text ?? "");
  return div.innerHTML;
}

function verdictClass(verdict) {
  if (verdict === "supported") return "mini-tag-supported";
  if (verdict === "mixed") return "mini-tag-mixed";
  return "mini-tag-alert";
}

function stanceClass(verdict) {
  if (verdict === "supported") return "stance-supported";
  if (verdict === "mixed") return "stance";
  return "stance-alert";
}

function shortName(full) {
  const name = String(full || "").trim();
  if (!name) return "Candidate";
  const parts = name.split(/\s+/);
  return parts[0];
}

function formatCandidateContext(candidate, race) {
  const party = candidate.party || "Unlisted";
  const stage = candidate.race_stage ? String(candidate.race_stage).replaceAll("_", " ") : "current stage";
  const office = candidate.office || race.office;
  const state = candidate.state || race.state;
  return `${party} | ${office} | ${state} | ${stage}`;
}

function initials(full) {
  const name = String(full || "").trim();
  if (!name) return "C";
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
}

function formatPct(n) {
  if (!Number.isFinite(n)) return "--%";
  return `${Math.round(n * 100)}%`;
}

function formatAsOf(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

function shortId(id) {
  const text = String(id || "");
  if (text.length <= 8) return text;
  return `${text.slice(0, 8)}...`;
}

function tallyVerdicts(compare) {
  const counts = new Map();
  for (const c of compare.candidates) {
    counts.set(c.id, { supported: 0, mixed: 0, unsupported: 0, insufficient: 0, total: 0 });
  }
  for (const issue of compare.issues) {
    for (const item of issue.items) {
      const bucket = counts.get(item.candidate_id);
      if (!bucket) continue;
      bucket.total += 1;
      if (bucket[item.verdict] !== undefined) bucket[item.verdict] += 1;
    }
  }
  return counts;
}

function renderTopCards(compare) {
  const candidates = compare.candidates;
  if (candidates.length === 0) return;
  const countsByCandidate = tallyVerdicts(compare);

  const topTags = compare.issues.map((i) => i.issue_tag).slice(0, 5);
  const cards = $("candidate-cards");
  cards.dataset.count = String(candidates.length);

  $("race-label").textContent = `${compare.race.state} ${compare.race.office} ${compare.race.election_cycle ?? ""}`.trim();

  cards.innerHTML = candidates
    .map((candidate, idx) => {
      const counts = countsByCandidate.get(candidate.id) || { supported: 0, mixed: 0, unsupported: 0, insufficient: 0, total: 0 };
      const supportedRate = counts.total ? counts.supported / counts.total : NaN;
      const contradictedRate = counts.total ? ((counts.unsupported || 0) + (counts.insufficient || 0)) / counts.total : NaN;
      const scoreTone = idx === 0 ? "truth-score-strong" : idx === 1 ? "truth-score-alert" : "truth-score-neutral";
      const portraitTone = ["portrait-a", "portrait-b", "portrait-c", "portrait-d"][idx % 4];
      const topLine = idx === 0 ? "Most supported claims" : idx === 1 ? "Most contradicted or unverified" : "Current reviewed share";
      const topValue = idx <= 1 ? (idx === 0 ? formatPct(supportedRate) : formatPct(contradictedRate)) : formatPct(supportedRate);
      const note =
        idx === 0
          ? "Supported share among the issues shown below."
          : idx === 1
            ? "Contradicted or unverified share among the issues shown below."
            : "Supported share among currently reviewed claims in this view.";

      return `
        <article class="candidate-card ${idx === 1 ? "candidate-card-alert" : ""}">
          <div class="candidate-topline">
            <div class="portrait ${portraitTone}">${escapeHtml(initials(candidate.name))}</div>
            <div>
              <p class="card-kicker">Candidate ${escapeHtml(String.fromCharCode(65 + idx))}</p>
              <h3>${escapeHtml(candidate.name)}</h3>
              <p class="candidate-role">${escapeHtml(formatCandidateContext(candidate, compare.race))}</p>
            </div>
          </div>

          <div class="truth-score ${scoreTone}">
            <span>${escapeHtml(topLine)}</span>
            <strong>${escapeHtml(topValue)}</strong>
            <small>${escapeHtml(note)}</small>
          </div>

          <div class="score-breakdown">
            <div>
              <span class="breakdown-label">Supported</span>
              <strong>${escapeHtml(String(counts.supported))}</strong>
            </div>
            <div>
              <span class="breakdown-label">Misleading</span>
              <strong>${escapeHtml(String(counts.mixed))}</strong>
            </div>
            <div>
              <span class="breakdown-label">Unverified</span>
              <strong>${escapeHtml(String(counts.insufficient))}</strong>
            </div>
          </div>

          <div class="policy-block">
            <span class="section-label">Top issues in this view</span>
            <ul>${topTags.map((tag) => `<li>${escapeHtml(tag)}</li>`).join("")}</ul>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderContrastBand(compare) {
  const candidates = compare.candidates;
  if (candidates.length < 2) return;

  const countsByCandidate = tallyVerdicts(compare);
  const safeRate = (num, den) => (den > 0 ? num / den : NaN);
  const supportedRate = (bucket) => safeRate(bucket?.supported || 0, bucket?.total || 0);
  const contradictedRate = (bucket) => safeRate((bucket?.unsupported || 0) + (bucket?.insufficient || 0), bucket?.total || 0);
  const unverifiedRate = (bucket) => safeRate(bucket?.insufficient || 0, bucket?.total || 0);

  const mostSupported = candidates.reduce((best, candidate) =>
    supportedRate(countsByCandidate.get(candidate.id)) >= supportedRate(countsByCandidate.get(best.id)) ? candidate : best
  );
  const mostContradicted = candidates.reduce((best, candidate) =>
    contradictedRate(countsByCandidate.get(candidate.id)) >= contradictedRate(countsByCandidate.get(best.id)) ? candidate : best
  );
  const mostUnverified = candidates.reduce((best, candidate) =>
    unverifiedRate(countsByCandidate.get(candidate.id)) >= unverifiedRate(countsByCandidate.get(best.id)) ? candidate : best
  );

  const ms = $("contrast-most-supported");
  if (ms) ms.textContent = mostSupported.name;
  const mc = $("contrast-most-contradicted");
  if (mc) mc.textContent = mostContradicted.name;
  const mu = $("contrast-most-unverified");
  if (mu) mu.textContent = mostUnverified.name;

  let splitTag = "";
  for (const issue of compare.issues || []) {
    const verdicts = new Set(issue.items.map((it) => it.verdict));
    if (verdicts.size > 1) {
      splitTag = issue.issue_tag;
      break;
    }
  }

  const ts = $("contrast-tightest-split");
  if (ts) ts.textContent = splitTag || (compare.issues?.[0]?.issue_tag ?? "No issues");
  const tsNote = $("contrast-tightest-split-note");
  if (tsNote) {
    tsNote.textContent = splitTag
      ? "At least two candidates diverge on this issue in the current window."
      : "Pick an issue below to see the direct, side-by-side record.";
  }
}

function renderIssueList(compare, selectedIndex) {
  const container = $("issue-list");
  const candidates = compare.candidates;

  const rows = compare.issues
    .map((issue, idx) => {
      const isSelected = idx === selectedIndex;
      const tags = candidates
        .map((candidate) => {
          const item = issue.items.find((it) => it.candidate_id === candidate.id);
          if (!item) return "";
          return `<span class="mini-tag ${verdictClass(item.verdict)}">${escapeHtml(shortName(candidate.name))}: ${escapeHtml(item.verdict)}</span>`;
        })
        .join("");

      return `
        <button class="issue-row ${isSelected ? "is-selected" : ""}" type="button" data-issue="${idx}">
          <span class="issue-name">${escapeHtml(issue.issue_tag)}</span>
          <span class="issue-tags">${tags}</span>
        </button>
      `;
    })
    .join("");

  container.innerHTML = rows || `<p class="note-copy">No issues returned for this window.</p>`;

  container.querySelectorAll(".issue-row").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.issue);
      window.__CFA_SELECTED_ISSUE = idx;
      renderIssueList(compare, idx);
      renderPanel(compare, idx);
    });
  });
}

function renderSources(sources) {
  if (!sources || sources.length === 0) {
    return `<div class="source-list-note">No sources attached.</div>`;
  }

  return sources
    .map((s) => {
      const kind = s.source_class === "primary" ? "Primary" : "Secondary";
      const kindClass = s.source_class === "primary" ? "source-type-primary" : "source-type-secondary";
      return `
        <a class="source-link" href="${escapeHtml(s.url)}" target="_blank" rel="noreferrer">
          <span class="source-type ${kindClass}">${escapeHtml(kind)}</span>
          <strong>${escapeHtml(s.publisher || "Linked source")}</strong>
          <small>Quality score: ${escapeHtml(String(s.quality_score))}</small>
        </a>
      `;
    })
    .join("");
}

function renderPanel(compare, issueIndex) {
  const issue = compare.issues[issueIndex];
  const candidates = compare.candidates;
  if (!issue || candidates.length === 0) return;

  $("panel-title").textContent = issue.issue_tag;
  $("panel-summary").textContent = compare.race.disclaimer;
  $("panel-stamp").textContent = `As of ${formatAsOf(compare.race.as_of)}`;
  $("panel-side-by-side").style.setProperty("--panel-cols", String(Math.min(candidates.length, 3)));

  const html = candidates
    .map((c, idx) => {
      const item = issue.items.find((it) => it.candidate_id === c.id);
      if (!item) {
        return `
          <article class="stance">
            <span class="stance-label">${escapeHtml(c.party || `Candidate ${String.fromCharCode(65 + idx)}`)}</span>
            <p><strong>${escapeHtml(c.name)}</strong></p>
            <small>${escapeHtml(formatCandidateContext(c, compare.race))}</small>
            <p>No evaluated claim available for this issue in the selected window.</p>
          </article>
        `;
      }

      const stmtMeta = item.statement_source_url
        ? `<small>Statement source: <a href="${escapeHtml(item.statement_source_url)}" target="_blank" rel="noreferrer">link</a></small>`
        : "";

      const verdictPill = `<span class="mini-tag ${verdictClass(item.verdict)}">${escapeHtml(item.verdict)} | ${Math.round(
        item.confidence * 100
      )}% confidence</span>`;

      return `
        <article class="stance ${stanceClass(item.verdict)}">
          <span class="stance-label">${escapeHtml(c.party || `Candidate ${String.fromCharCode(65 + idx)}`)}</span>
          <p><strong>${escapeHtml(c.name)}</strong></p>
          <small>${escapeHtml(formatCandidateContext(c, compare.race))}</small>
          <div class="issue-tags">${verdictPill}</div>
          <p>${escapeHtml(item.claim_text)}</p>
          <small>${escapeHtml(item.rationale)}</small>
          ${stmtMeta}
          <div class="source-list-block" style="margin-top:0.9rem">
            <div class="source-list-header">
              <p class="eyebrow">Citations</p>
              <span class="source-list-note">Primary and secondary sources</span>
            </div>
            <div class="source-list">
              ${renderSources(item.sources)}
            </div>
          </div>
        </article>
      `;
    })
    .join("");

  $("panel-side-by-side").innerHTML = html;
}

function renderReviewQueue(rows) {
  const list = $("review-queue-list");
  const meta = $("review-queue-meta");
  if (!list || !meta) return;

  const byCandidate = new Map();
  for (const row of rows) {
    const key = row.candidate_name;
    byCandidate.set(key, (byCandidate.get(key) || 0) + 1);
  }

  meta.textContent = `Review-ready claims: ${rows.length}`;
  list.innerHTML =
    rows
      .map((row) => {
        const latest = row.latest_verdict || "none";
        return `
          <button class="review-item" type="button" data-claim-id="${escapeHtml(row.claim_id)}">
            <span class="mini-tag ${verdictClass(latest)}">${escapeHtml(row.candidate_name)} | ${escapeHtml(latest)}</span>
            <strong>${escapeHtml(row.issue_tag || "Unlabeled issue")}</strong>
            <p>${escapeHtml(row.claim_text)}</p>
            <small>Claim ${escapeHtml(shortId(row.claim_id))} | primary ${escapeHtml(String(row.primary_source_count))} | secondary ${escapeHtml(String(row.secondary_source_count))}</small>
          </button>
        `;
      })
      .join("") || `<p class="note-copy">No review-ready claims found.</p>`;

  list.querySelectorAll(".review-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      const claimId = btn.dataset.claimId;
      if (!claimId) return;
      populateReviewForm(claimId);
      list.querySelectorAll(".review-item").forEach((item) => item.classList.remove("is-selected"));
      btn.classList.add("is-selected");
    });
  });

  const firstClaimId = rows[0]?.claim_id;
  if (firstClaimId) {
    populateReviewForm(firstClaimId);
    const firstItem = list.querySelector(".review-item");
    if (firstItem) firstItem.classList.add("is-selected");
  }
}

function populateReviewForm(claimId) {
  const row = reviewQueueRows.find((item) => item.claim_id === claimId);
  if (!row) return;

  const claimIdInput = $("review-claim-id");
  const reviewerInput = $("reviewer-id");
  const rationaleInput = $("review-rationale");
  const citationNotesInput = $("review-citation-notes");
  const verdictInput = $("review-verdict");
  const confidenceInput = $("review-confidence");
  const preview = $("review-claim-preview");

  if (claimIdInput) claimIdInput.value = row.claim_id;
  if (verdictInput) verdictInput.value = "supported";
  if (confidenceInput) confidenceInput.value = "0.70";
  if (reviewerInput && !reviewerInput.value) reviewerInput.value = "tx_2026_human_reviewer";
  if (rationaleInput) rationaleInput.value = "";
  if (citationNotesInput) citationNotesInput.value = "";
  if (preview) {
    preview.textContent = `${row.candidate_name} (${row.candidate_party || "Unlisted"}) | ${row.issue_tag || "Unlabeled issue"} | ${row.claim_text}`;
  }
}

async function loadReviewQueue() {
  try {
    const res = await fetch(API_REVIEW_QUEUE_URL, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`review queue failed: ${res.status}`);
    reviewQueueRows = await res.json();
    renderReviewQueue(reviewQueueRows);
  } catch (err) {
    const meta = $("review-queue-meta");
    const list = $("review-queue-list");
    if (meta) meta.textContent = "Review queue not reachable";
    if (list) list.innerHTML = `<p class="note-copy">Start API and load Texas scripts, then refresh.</p>`;
  }
}

async function loadCompare() {
  try {
    const res = await fetch(API_COMPARE_URL, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`API request failed: ${res.status}`);
    const compare = await res.json();

    const selected = Number.isFinite(window.__CFA_SELECTED_ISSUE) ? window.__CFA_SELECTED_ISSUE : 0;
    renderTopCards(compare);
    renderContrastBand(compare);
    renderIssueList(compare, selected);
    renderPanel(compare, selected);
  } catch (err) {
    $("panel-title").textContent = "API not reachable";
    $("panel-summary").textContent =
      "Start the stack with `docker compose up -d --build` and load the Texas 2026 scripts before opening the compare page.";
    $("panel-stamp").textContent = "No API response";
  }
}

async function submitReview(event) {
  event.preventDefault();
  const claimId = $("review-claim-id")?.value?.trim();
  const verdict = $("review-verdict")?.value;
  const confidenceRaw = $("review-confidence")?.value;
  const rationale = $("review-rationale")?.value?.trim();
  const citationNotes = $("review-citation-notes")?.value?.trim();
  const reviewerId = $("reviewer-id")?.value?.trim();
  const status = $("review-submit-status");

  if (!claimId || !verdict || !confidenceRaw || !rationale || !reviewerId) {
    if (status) status.textContent = "Claim, verdict, confidence, rationale, and reviewer ID are required.";
    return;
  }

  const confidence = Number(confidenceRaw);
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    if (status) status.textContent = "Confidence must be between 0 and 1.";
    return;
  }

  const payload = {
    verdict,
    confidence,
    rationale,
    citation_notes: citationNotes || null,
    reviewer_id: reviewerId,
  };

  try {
    if (status) status.textContent = "Submitting review...";
    const res = await fetch(`${API_EVALUATE_BASE_URL}/${encodeURIComponent(claimId)}/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let message = `Review submission failed (${res.status})`;
      try {
        const body = await res.json();
        if (body?.error?.message) message = body.error.message;
      } catch (_) {
      }
      throw new Error(message);
    }

    if (status) status.textContent = "Review saved. Refreshing compare and queue...";
    await loadReviewQueue();
    await loadCompare();
    if (status) status.textContent = "Review saved successfully.";
  } catch (err) {
    if (status) status.textContent = err instanceof Error ? err.message : "Review submission failed.";
  }
}

async function init() {
  const form = $("review-form");
  if (form) {
    form.addEventListener("submit", submitReview);
  }
  await Promise.all([loadCompare(), loadReviewQueue()]);
}

init();
