const API_COMPARE_URL = "/api/v1/compare?state=TX&office=US%20Senate&election_cycle=2026&limit_issues=8";
const API_CANDIDATES_URL = "/api/v1/candidates";
const API_REVIEW_QUEUE_URL =
  "/api/v1/claims/review-queue?state=TX&office=US%20Senate&election_cycle=2026&require_minimum_evidence=true&limit=50";
const API_EVALUATE_BASE_URL = "/api/v1/claims";
const API_AUTH_LOGIN_URL = "/api/v1/auth/login";
const API_PROPOSALS_BASE_URL = "/api/v1/claims/proposals";

let reviewQueueRows = [];
let proposalQueueRows = [];
let authToken = localStorage.getItem("cfa_auth_token") || "";
let compareState = null;
let compareRawState = null;
let compareAbortController = null;
const DEFAULT_RACE_KEY = "TX|US Senate|2026";
const DEFAULT_RACE_STAGE = "primary_runoff";
let compareFilters = {
  raceKey: DEFAULT_RACE_KEY,
  raceStage: DEFAULT_RACE_STAGE,
  startDate: "",
  endDate: "",
  issueContains: "",
  minConfidence: 0,
  minQuality: 0,
  limitIssues: 8,
};
let raceOptions = [];
let raceStageOptions = new Map();

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

function formatVerdictLabel(verdict) {
  if (verdict === "supported") return "Supported by record";
  if (verdict === "mixed") return "Mixed or incomplete";
  if (verdict === "unsupported") return "Contradicted by record";
  return "Insufficient evidence";
}

function stageLabel(value) {
  if (!value) return "All stages";
  return value.replaceAll("_", " ");
}

function formatSourceOriginLabel(origin) {
  if (!origin) return "Unspecified origin";
  if (origin === "candidate") return "Candidate-originated";
  return "Verification";
}

function formatSourceClassLabel(sourceClass) {
  if (!sourceClass) return "Unclassified";
  return sourceClass === "primary" ? "Primary" : "Secondary";
}

function formatWarningLabel(code) {
  if (code === "missing_verification_primary") return "Missing verification primary";
  if (code === "missing_verification_secondary") return "Missing verification secondary";
  if (code === "source_class_imbalance_primary") return "Primary-source imbalance";
  if (code === "source_class_imbalance_secondary") return "Secondary-source imbalance";
  if (code === "weak_bundle_stance_links") return "Weak stance bundle";
  if (code === "weak_bundle_verification_links") return "Weak verification bundle";
  return "Evidence warning";
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

  const stage = compare.race.race_stage ? ` | ${stageLabel(compare.race.race_stage)}` : "";
  $("race-label").textContent = `${compare.race.state} ${compare.race.office} ${compare.race.election_cycle ?? ""}${stage}`.trim();

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
              <p class="card-kicker">Candidate profile</p>
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
              <span class="breakdown-label">Contradicted</span>
              <strong>${escapeHtml(String(counts.unsupported))}</strong>
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

function buildCompareUrl() {
  const selectedRace = raceOptions.find((option) => option.key === compareFilters.raceKey) || raceOptions[0];
  const params = new URLSearchParams();
  params.set("state", selectedRace?.state || "TX");
  params.set("office", selectedRace?.office || "US Senate");
  if (selectedRace?.electionCycle != null) {
    params.set("election_cycle", String(selectedRace.electionCycle));
  }
  if (compareFilters.raceStage) {
    params.set("race_stage", compareFilters.raceStage);
  }
  if (compareFilters.startDate) {
    params.set("window_start", `${compareFilters.startDate}T00:00:00Z`);
  }
  if (compareFilters.endDate) {
    params.set("window_end", `${compareFilters.endDate}T23:59:59Z`);
  }
  params.set("limit_issues", String(compareFilters.limitIssues));
  return `/api/v1/compare?${params.toString()}`;
}

function buildCompareExportUrl(format) {
  const selectedRace = raceOptions.find((option) => option.key === compareFilters.raceKey) || raceOptions[0];
  const params = new URLSearchParams();
  params.set("state", selectedRace?.state || "TX");
  params.set("office", selectedRace?.office || "US Senate");
  if (selectedRace?.electionCycle != null) {
    params.set("election_cycle", String(selectedRace.electionCycle));
  }
  if (compareFilters.raceStage) {
    params.set("race_stage", compareFilters.raceStage);
  }
  if (compareFilters.startDate) {
    params.set("window_start", `${compareFilters.startDate}T00:00:00Z`);
  }
  if (compareFilters.endDate) {
    params.set("window_end", `${compareFilters.endDate}T23:59:59Z`);
  }
  if (compareFilters.issueContains) {
    params.set("issue_contains", compareFilters.issueContains);
  }
  params.set("min_confidence", String(compareFilters.minConfidence || 0));
  params.set("min_source_quality", String(compareFilters.minQuality || 0));
  params.set("limit_issues", String(compareFilters.limitIssues));
  params.set("format", format);
  return `/api/v1/compare/export?${params.toString()}`;
}

function buildProposalQueueUrl() {
  const selectedRace = raceOptions.find((option) => option.key === compareFilters.raceKey) || raceOptions[0];
  const params = new URLSearchParams();
  params.set("state", selectedRace?.state || "TX");
  params.set("office", selectedRace?.office || "US Senate");
  if (selectedRace?.electionCycle != null) {
    params.set("election_cycle", String(selectedRace.electionCycle));
  }
  if (compareFilters.raceStage) {
    params.set("race_stage", compareFilters.raceStage);
  }
  params.set("limit", "100");
  return `${API_PROPOSALS_BASE_URL}?${params.toString()}`;
}

function syncCompareFiltersFromForm() {
  compareFilters.raceKey = $("filter-race")?.value || compareFilters.raceKey;
  compareFilters.raceStage = $("filter-stage")?.value || "";
  compareFilters.startDate = $("filter-start")?.value || "";
  compareFilters.endDate = $("filter-end")?.value || "";
  compareFilters.issueContains = $("filter-issue")?.value || "";
  const minConfidence = Number($("filter-min-confidence")?.value || 0);
  const minQuality = Number($("filter-min-quality")?.value || 0);
  compareFilters.minConfidence = Number.isFinite(minConfidence) ? Math.max(0, Math.min(1, minConfidence)) : 0;
  compareFilters.minQuality = Number.isFinite(minQuality) ? Math.max(0, Math.min(1, minQuality)) : 0;
  compareFilters.limitIssues = Number($("filter-limit-issues")?.value || 8);
  if (!Number.isFinite(compareFilters.limitIssues) || compareFilters.limitIssues < 1) compareFilters.limitIssues = 8;
  if (compareFilters.limitIssues > 10) compareFilters.limitIssues = 10;

  const minConfidenceInput = $("filter-min-confidence");
  const minQualityInput = $("filter-min-quality");
  if (minConfidenceInput) minConfidenceInput.value = String(compareFilters.minConfidence);
  if (minQualityInput) minQualityInput.value = String(compareFilters.minQuality);
}

function renderNoCompareState() {
  const cards = $("candidate-cards");
  if (cards) {
    cards.dataset.count = "0";
    cards.innerHTML = `<p class="note-copy">No comparison available for this race/stage selection.</p>`;
  }
  $("race-label").textContent = "Comparison unavailable";
  $("contrast-most-supported").textContent = "Not enough candidates";
  $("contrast-most-contradicted").textContent = "Not enough candidates";
  $("contrast-most-unverified").textContent = "Not enough candidates";
  $("contrast-tightest-split").textContent = "Not enough candidates";
  $("contrast-tightest-split-note").textContent =
    "Select a race with at least two candidates to compare contrast metrics.";
}

function applyClientFilters(compare) {
  const issueNeedle = compareFilters.issueContains.trim().toLowerCase();
  const minConfidenceRaw = Number(compareFilters.minConfidence);
  const minQualityRaw = Number(compareFilters.minQuality);
  const minConfidence = Number.isFinite(minConfidenceRaw) ? Math.max(0, Math.min(1, minConfidenceRaw)) : 0;
  const minQuality = Number.isFinite(minQualityRaw) ? Math.max(0, Math.min(1, minQualityRaw)) : 0;

  const filteredIssues = (compare.issues || [])
    .map((issue) => {
      const tagMatch = !issueNeedle || String(issue.issue_tag || "").toLowerCase().includes(issueNeedle);
      if (!tagMatch) return null;

      const items = (issue.items || []).filter((item) => {
        const confidenceOk = Number(item.confidence || 0) >= minConfidence;
        const sources = item.sources || [];
        const qualityOk = minQuality <= 0 || sources.some((source) => Number(source.quality_score || 0) >= minQuality);
        return confidenceOk && qualityOk;
      });
      if (items.length === 0) return null;
      return { ...issue, items };
    })
    .filter(Boolean)
    .slice(0, compareFilters.limitIssues);

  return { ...compare, issues: filteredIssues };
}

function refreshStageSelectForRace() {
  const stageSelect = $("filter-stage");
  if (!stageSelect) return;

  const stagesForRace = Array.from(raceStageOptions.get(compareFilters.raceKey) || []).sort();
  stageSelect.innerHTML =
    `<option value="">All stages</option>` +
    stagesForRace.map((stage) => `<option value="${escapeHtml(stage)}">${escapeHtml(stageLabel(stage))}</option>`).join("");

  if (compareFilters.raceStage && !stagesForRace.includes(compareFilters.raceStage)) {
    compareFilters.raceStage = "";
  }
  stageSelect.value = compareFilters.raceStage || "";
}

async function loadRaceOptions() {
  try {
    const res = await fetch(API_CANDIDATES_URL, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`candidate list failed: ${res.status}`);
    const rows = await res.json();
    const raceMap = new Map();
    const stageMap = new Map();

    for (const row of rows) {
      const state = row.state || "Unknown";
      const office = row.office || "Unknown Office";
      const electionCycle = row.election_cycle ?? null;
      const key = `${state}|${office}|${electionCycle ?? "none"}`;
      if (!raceMap.has(key)) {
        raceMap.set(key, { key, state, office, electionCycle });
      }
      if (!stageMap.has(key)) stageMap.set(key, new Set());
      if (row.race_stage) stageMap.get(key).add(row.race_stage);
    }

    raceOptions = Array.from(raceMap.values());
    raceStageOptions = stageMap;
    if (raceOptions.length === 0) {
      raceOptions = [{ key: DEFAULT_RACE_KEY, state: "TX", office: "US Senate", electionCycle: 2026 }];
      raceStageOptions = new Map([[DEFAULT_RACE_KEY, new Set([DEFAULT_RACE_STAGE])]]);
    }

    const raceSelect = $("filter-race");
    if (raceSelect) {
      raceSelect.innerHTML = raceOptions
        .map((race) => `<option value="${escapeHtml(race.key)}">${escapeHtml(`${race.state} ${race.office} ${race.electionCycle ?? ""}`.trim())}</option>`)
        .join("");
      const preferred = raceOptions.find((option) => option.key === DEFAULT_RACE_KEY);
      raceSelect.value = preferred ? preferred.key : raceOptions[0].key;
      compareFilters.raceKey = raceSelect.value;
    }

    refreshStageSelectForRace();
    const stagesForRace = Array.from(raceStageOptions.get(compareFilters.raceKey) || []);
    compareFilters.raceStage = stagesForRace.includes(DEFAULT_RACE_STAGE) ? DEFAULT_RACE_STAGE : "";
    const stageSelect = $("filter-stage");
    if (stageSelect) {
      stageSelect.value = compareFilters.raceStage;
    }
  } catch (err) {
    raceOptions = [{ key: DEFAULT_RACE_KEY, state: "TX", office: "US Senate", electionCycle: 2026 }];
    raceStageOptions = new Map([[DEFAULT_RACE_KEY, new Set([DEFAULT_RACE_STAGE])]]);
    const raceSelect = $("filter-race");
    if (raceSelect) {
      raceSelect.innerHTML = `<option value="${DEFAULT_RACE_KEY}">TX US Senate 2026</option>`;
      raceSelect.value = DEFAULT_RACE_KEY;
    }
    compareFilters.raceKey = DEFAULT_RACE_KEY;
    compareFilters.raceStage = DEFAULT_RACE_STAGE;
    refreshStageSelectForRace();
  }
}

function renderContrastBand(compare) {
  const candidates = compare.candidates;
  const ms = $("contrast-most-supported");
  const mc = $("contrast-most-contradicted");
  const mu = $("contrast-most-unverified");
  const ts = $("contrast-tightest-split");
  const tsNote = $("contrast-tightest-split-note");

  if (candidates.length < 2) {
    if (ms) ms.textContent = "Not enough candidates";
    if (mc) mc.textContent = "Not enough candidates";
    if (mu) mu.textContent = "Not enough candidates";
    if (ts) ts.textContent = "Not enough candidates";
    if (tsNote) tsNote.textContent = "Select a race with at least two candidates to compare contrast metrics.";
    return;
  }

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

  if (ms) ms.textContent = mostSupported.name;
  if (mc) mc.textContent = mostContradicted.name;
  if (mu) mu.textContent = mostUnverified.name;

  let splitTag = "";
  for (const issue of compare.issues || []) {
    const verdicts = new Set(issue.items.map((it) => it.verdict));
    if (verdicts.size > 1) {
      splitTag = issue.issue_tag;
      break;
    }
  }

  if (ts) ts.textContent = splitTag || (compare.issues?.[0]?.issue_tag ?? "No issues");
  if (tsNote) {
    tsNote.textContent = splitTag
      ? "At least two candidates diverge on this issue in the current window."
      : "Pick an issue below to see the direct, side-by-side record.";
  }
}

function renderIssueList(compare, selectedIndex) {
  const container = $("issue-list");
  const candidates = compare.candidates;
  const safeSelectedIndex = Math.max(0, Math.min(selectedIndex, Math.max(0, compare.issues.length - 1)));
  container.setAttribute("role", "radiogroup");
  container.setAttribute("aria-label", "Selectable issues");

  const rows = compare.issues
    .map((issue, idx) => {
      const isSelected = idx === safeSelectedIndex;
      const tags = candidates
        .map((candidate) => {
          const item = issue.items.find((it) => it.candidate_id === candidate.id);
          if (!item) return "";
          return `<span class="mini-tag ${verdictClass(item.verdict)}">${escapeHtml(shortName(candidate.name))}: ${escapeHtml(item.verdict)}</span>`;
        })
        .join("");
      const issueWarnings = (issue.warnings || [])
        .map((warning) => `<span class="mini-tag mini-tag-alert">${escapeHtml(formatWarningLabel(warning.code))}</span>`)
        .join("");

      return `
        <button class="issue-row ${isSelected ? "is-selected" : ""}" type="button" data-issue="${idx}" role="radio" aria-checked="${isSelected ? "true" : "false"}" tabindex="${isSelected ? "0" : "-1"}">
          <span class="issue-name">${escapeHtml(issue.issue_tag)}</span>
          <span class="issue-tags">${tags}${issueWarnings}</span>
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
    btn.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp" && event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
        return;
      }
      event.preventDefault();
      const direction = event.key === "ArrowDown" || event.key === "ArrowRight" ? 1 : -1;
      const nextIndex = (Number(btn.dataset.issue) + direction + compare.issues.length) % compare.issues.length;
      const nextButton = container.querySelector(`.issue-row[data-issue="${nextIndex}"]`);
      if (nextButton instanceof HTMLElement) {
        nextButton.focus();
        nextButton.click();
      }
    });
  });
}

function renderSourceLinks(links) {
  if (!links || links.length === 0) {
    return `<div class="source-list-note">No links available.</div>`;
  }
  return links
    .map((link) => {
      const kind = formatSourceClassLabel(link.source_class);
      const kindClass = link.source_class === "primary" ? "source-type-primary" : "source-type-secondary";
      const origin = formatSourceOriginLabel(link.source_origin);
      const originClass = link.source_origin === "candidate" ? "source-origin-candidate" : "source-origin-verification";
      const quality = link.quality_score == null ? "Not scored" : String(link.quality_score);
      return `
        <a class="source-link" href="${escapeHtml(link.url)}" rel="noreferrer">
          <div class="source-badges">
            <span class="source-type ${kindClass}">${escapeHtml(kind)}</span>
            <span class="source-origin ${originClass}">${escapeHtml(origin)}</span>
          </div>
          <strong>${escapeHtml(link.publisher || link.label || "Linked source")}</strong>
          <small>Quality score: ${escapeHtml(quality)}</small>
        </a>
      `;
    })
    .join("");
}

function renderCuratedEvidence(item) {
  const bundle = item.evidence_bundle;
  if (!bundle) {
    return `<div class="source-list">${renderSourceLinks(item.sources || [])}</div>`;
  }
  const stanceCount = (bundle.stance_links || []).length;
  const verificationCount = (bundle.verification_links || []).length;
  return `
    <div class="evidence-sides">
      <div class="evidence-side">
        <details>
          <summary class="eyebrow">Supporting stance links (${escapeHtml(String(stanceCount))})</summary>
          <div class="source-list">${renderSourceLinks(bundle.stance_links || [])}</div>
        </details>
      </div>
      <div class="evidence-side">
        <details>
          <summary class="eyebrow">Rebutting/verification links (${escapeHtml(String(verificationCount))})</summary>
          <div class="source-list">${renderSourceLinks(bundle.verification_links || [])}</div>
        </details>
      </div>
    </div>
  `;
}

function renderExplanationCards(issue, compare) {
  const container = $("panel-explanations");
  if (!container) return;

  const cards = compare.candidates
    .map((candidate, idx) => {
      const item = issue.items.find((entry) => entry.candidate_id === candidate.id);
      if (!item) return "";

      const primaryCount = item.sources.filter((source) => source.source_class === "primary").length;
      const secondaryCount = item.sources.filter((source) => source.source_class !== "primary").length;
      const candidateCount = item.sources.filter((source) => source.source_origin === "candidate").length;
      const verificationCount = item.sources.filter((source) => source.source_origin === "verification").length;
      const citationNotes = item.citation_notes?.trim() || "No reviewer citation notes recorded yet.";
      const warningBadges = (item.warnings || [])
        .map((warning) => `<span class="mini-tag mini-tag-alert">${escapeHtml(formatWarningLabel(warning.code))}</span>`)
        .join("");

      return `
        <article class="explanation-card ${stanceClass(item.verdict)}">
          <div class="explanation-topline">
            <span class="stance-label">${escapeHtml(candidate.party || "Unlisted")}</span>
            <span class="mini-tag ${verdictClass(item.verdict)}">${escapeHtml(formatVerdictLabel(item.verdict))}</span>
          </div>
          <h5>${escapeHtml(candidate.name)}</h5>
          <div class="issue-tags">${warningBadges}</div>
          <p class="explanation-claim">${escapeHtml(item.claim_text)}</p>
          <div class="explanation-grid">
            <div class="csr-card">
              <span class="section-label">Why this verdict</span>
              <p>${escapeHtml(item.rationale)}</p>
            </div>
            <div class="csr-card">
              <span class="section-label">Evidence summary</span>
              <p>${escapeHtml(`${primaryCount} primary, ${secondaryCount} secondary, ${candidateCount} candidate-originated, ${verificationCount} verification, ${Math.round(item.confidence * 100)}% confidence`)}</p>
            </div>
            <div class="csr-card">
              <span class="section-label">Citation notes</span>
              <p>${escapeHtml(citationNotes)}</p>
            </div>
          </div>
        </article>
      `;
    })
    .filter(Boolean)
    .join("");

  container.innerHTML = cards || `<p class="note-copy">No explanation cards available for this issue.</p>`;
}

function renderPanel(compare, issueIndex) {
  const issue = compare.issues[issueIndex];
  const candidates = compare.candidates;
  if (!issue || candidates.length === 0) return;

  $("panel-title").textContent = issue.issue_tag;
  const issueBlockingWarnings = (issue.warnings || []).filter((w) => w.is_confidence_blocking);
  const itemBlockingWarnings = (issue.items || []).flatMap((item) => (item.warnings || []).filter((w) => w.is_confidence_blocking));
  const hasBlockingWarnings = issueBlockingWarnings.length > 0 || itemBlockingWarnings.length > 0;
  $("panel-summary").textContent =
    hasBlockingWarnings
      ? `${compare.race.disclaimer} Warning: parity/evidence gaps are present for this issue view.`
      : compare.race.disclaimer;
  $("panel-stamp").textContent = `As of ${formatAsOf(compare.race.as_of)}`;
  $("panel-side-by-side").style.setProperty("--panel-cols", String(Math.min(candidates.length, 3)));
  $("panel-explanations").style.setProperty("--panel-cols", String(Math.min(candidates.length, 3)));
  renderExplanationCards(issue, compare);

  const html = candidates
    .map((c, idx) => {
      const item = issue.items.find((it) => it.candidate_id === c.id);
      if (!item) {
        return `
          <article class="stance">
            <span class="stance-label">${escapeHtml(c.party || "Unlisted")}</span>
            <p><strong>${escapeHtml(c.name)}</strong></p>
            <small>${escapeHtml(formatCandidateContext(c, compare.race))}</small>
            <p>No evaluated claim available for this issue in the selected window.</p>
          </article>
        `;
      }

      const stmtMeta = item.statement_source_url
        ? `<small>Statement source: <a href="${escapeHtml(item.statement_source_url)}" rel="noreferrer">candidate statement record</a></small>`
        : "";

      const verdictPill = `<span class="mini-tag ${verdictClass(item.verdict)}">${escapeHtml(item.verdict)} | ${Math.round(
        item.confidence * 100
      )}% confidence</span>`;
      const warningPills = (item.warnings || [])
        .map((warning) => `<span class="mini-tag mini-tag-alert">${escapeHtml(formatWarningLabel(warning.code))}</span>`)
        .join("");

      return `
        <article class="stance ${stanceClass(item.verdict)}">
          <span class="stance-label">${escapeHtml(c.party || "Unlisted")}</span>
          <p><strong>${escapeHtml(c.name)}</strong></p>
          <small>${escapeHtml(formatCandidateContext(c, compare.race))}</small>
          <div class="issue-tags">${verdictPill}${warningPills}</div>
          <p>${escapeHtml(item.claim_text)}</p>
          <small>${escapeHtml(item.rationale)}</small>
          ${stmtMeta}
          <div class="source-list-block" style="margin-top:0.9rem">
            <div class="source-list-header">
              <p class="eyebrow">Citations</p>
              <span class="source-list-note">Curated links per side, labeled by source origin and class</span>
            </div>
            ${renderCuratedEvidence(item)}
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
            <small>Candidate-originated ${escapeHtml(String(row.candidate_source_count))} | verification ${escapeHtml(String(row.verification_source_count))}</small>
            <small>${escapeHtml((row.warnings || []).map((w) => formatWarningLabel(w.code)).join(" | "))}</small>
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
  const rationaleInput = $("review-rationale");
  const citationNotesInput = $("review-citation-notes");
  const verdictInput = $("review-verdict");
  const confidenceInput = $("review-confidence");
  const preview = $("review-claim-preview");

  if (claimIdInput) claimIdInput.value = row.claim_id;
  if (verdictInput) verdictInput.value = "supported";
  if (confidenceInput) confidenceInput.value = "0.70";
  if (rationaleInput) rationaleInput.value = "";
  if (citationNotesInput) citationNotesInput.value = "";
  if (preview) {
    preview.textContent = `${row.candidate_name} (${row.candidate_party || "Unlisted"}) | ${row.issue_tag || "Unlabeled issue"} | ${row.claim_text}`;
  }
}

async function submitLogin(event) {
  event.preventDefault();
  const email = $("auth-email")?.value?.trim();
  const password = $("auth-password")?.value || "";
  const status = $("auth-status");

  if (!email || !password) {
    if (status) status.textContent = "Email and password are required.";
    return;
  }

  try {
    if (status) status.textContent = "Signing in...";
    const res = await fetch(API_AUTH_LOGIN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      let message = `Sign-in failed (${res.status})`;
      try {
        const body = await res.json();
        if (body?.error?.message) message = body.error.message;
      } catch (_) {
      }
      throw new Error(message);
    }

    const body = await res.json();
    authToken = body.access_token;
    localStorage.setItem("cfa_auth_token", authToken);
    if (status) status.textContent = `Signed in as ${body.reviewer_id}.`;
    await loadProposalQueue();
  } catch (err) {
    if (status) status.textContent = err instanceof Error ? err.message : "Sign-in failed.";
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
    if (compareAbortController) {
      compareAbortController.abort();
    }
    compareAbortController = new AbortController();
    const res = await fetch(buildCompareUrl(), { headers: { Accept: "application/json" }, signal: compareAbortController.signal });
    if (!res.ok) {
      let apiMessage = "";
      try {
        const errorBody = await res.json();
        apiMessage = errorBody?.error?.message || errorBody?.detail || "";
      } catch (_) {
      }
      const err = new Error(apiMessage || `API request failed: ${res.status}`);
      err.status = res.status;
      throw err;
    }
    const compareRaw = await res.json();
    compareRawState = compareRaw;
    const compare = applyClientFilters(compareRaw);
    compareState = compare;

    if (compare.issues.length === 0) {
      $("panel-title").textContent = "No issues match current filters";
      $("panel-summary").textContent = "Try widening date, confidence, issue, or source-quality filters.";
      $("panel-stamp").textContent = "Filtered result";
      $("issue-list").innerHTML = `<p class="note-copy">No issues returned for the selected filters.</p>`;
      $("panel-explanations").innerHTML = "";
      $("panel-side-by-side").innerHTML = "";
      renderTopCards(compare);
      renderContrastBand(compare);
      return;
    }

    const selected = Number.isFinite(window.__CFA_SELECTED_ISSUE) ? window.__CFA_SELECTED_ISSUE : 0;
    const bounded = Math.max(0, Math.min(selected, compare.issues.length - 1));
    renderTopCards(compare);
    renderContrastBand(compare);
    renderIssueList(compare, bounded);
    renderPanel(compare, bounded);
    renderPublishedClaims(compareRawState);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    if (err && typeof err === "object" && err.status === 404) {
      renderNoCompareState();
      $("panel-title").textContent = "Not enough candidates for this stage";
      $("panel-summary").textContent =
        "This race/stage selection does not currently have enough candidates to run a side-by-side comparison. Try another stage or clear stage filtering.";
      $("panel-stamp").textContent = "Comparison unavailable";
      $("issue-list").innerHTML = `<p class="note-copy">No comparison available for this race/stage selection.</p>`;
      $("panel-explanations").innerHTML = "";
      $("panel-side-by-side").innerHTML = "";
      return;
    }
    $("panel-title").textContent = "API not reachable";
    $("panel-summary").textContent =
      "Start the stack with `docker compose up -d --build` and load the Texas 2026 scripts before opening the compare page.";
    $("panel-stamp").textContent = "No API response";
  }
}

function resetCompareFilters() {
  compareFilters = {
    raceKey: raceOptions.find((option) => option.key === DEFAULT_RACE_KEY)?.key || raceOptions[0]?.key || DEFAULT_RACE_KEY,
    raceStage: DEFAULT_RACE_STAGE,
    startDate: "",
    endDate: "",
    issueContains: "",
    minConfidence: 0,
    minQuality: 0,
    limitIssues: 8,
  };

  const sync = (id, value) => {
    const el = $(id);
    if (!el) return;
    el.value = String(value);
  };

  sync("filter-race", compareFilters.raceKey);
  refreshStageSelectForRace();
  sync("filter-stage", compareFilters.raceStage);
  sync("filter-start", "");
  sync("filter-end", "");
  sync("filter-issue", "");
  sync("filter-min-confidence", "0");
  sync("filter-min-quality", "0");
  sync("filter-limit-issues", "8");
}

function bindCompareControls() {
  const form = $("compare-controls");
  if (!form) return;

  const raceSelect = $("filter-race");
  if (raceSelect) {
    raceSelect.addEventListener("change", () => {
      compareFilters.raceKey = raceSelect.value || compareFilters.raceKey;
      compareFilters.raceStage = "";
      refreshStageSelectForRace();
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    syncCompareFiltersFromForm();
    window.__CFA_SELECTED_ISSUE = 0;
    await loadCompare();
  });

  const resetButton = $("filter-reset");
  if (resetButton) {
    resetButton.addEventListener("click", async () => {
      resetCompareFilters();
      window.__CFA_SELECTED_ISSUE = 0;
      await loadCompare();
    });
  }

  const exportJsonButton = $("filter-export-json");
  if (exportJsonButton) {
    exportJsonButton.addEventListener("click", () => {
      syncCompareFiltersFromForm();
      window.open(buildCompareExportUrl("json"), "_blank", "noopener,noreferrer");
    });
  }
  const exportCsvButton = $("filter-export-csv");
  if (exportCsvButton) {
    exportCsvButton.addEventListener("click", () => {
      syncCompareFiltersFromForm();
      window.open(buildCompareExportUrl("csv"), "_blank", "noopener,noreferrer");
    });
  }
}

async function submitReview(event) {
  event.preventDefault();
  const claimId = $("review-claim-id")?.value?.trim();
  const verdict = $("review-verdict")?.value;
  const confidenceRaw = $("review-confidence")?.value;
  const rationale = $("review-rationale")?.value?.trim();
  const citationNotes = $("review-citation-notes")?.value?.trim();
  const status = $("review-submit-status");

  if (!claimId || !verdict || !confidenceRaw || !rationale) {
    if (status) status.textContent = "Claim, verdict, confidence, and rationale are required.";
    return;
  }
  if (!authToken) {
    if (status) status.textContent = "Sign in before submitting review.";
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
  };

  try {
    if (status) status.textContent = "Submitting review...";
    const res = await fetch(`${API_EVALUATE_BASE_URL}/${encodeURIComponent(claimId)}/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json", Authorization: `Bearer ${authToken}` },
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

function renderProposalQueue(rows) {
  const list = $("proposal-queue-list");
  const meta = $("proposal-queue-meta");
  if (!list || !meta) return;
  meta.textContent = `Proposals: ${rows.length}`;
  list.innerHTML =
    rows
      .map(
        (row) => `
          <button class="review-item" type="button" data-proposal-id="${escapeHtml(row.id)}">
            <span class="mini-tag">${escapeHtml(row.proposal_type)} | ${escapeHtml(row.status)}</span>
            <strong>Claim ${escapeHtml(shortId(row.claim_id))}</strong>
            <p>Proposed by ${escapeHtml(row.proposed_by)}</p>
          </button>
        `
      )
      .join("") || `<p class="note-copy">No proposals currently.</p>`;
  list.querySelectorAll(".review-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      const proposalId = btn.dataset.proposalId;
      if (!proposalId) return;
      populateProposalForm(proposalId);
      list.querySelectorAll(".review-item").forEach((item) => item.classList.remove("is-selected"));
      btn.classList.add("is-selected");
    });
  });
}

function populateProposalForm(proposalId) {
  const row = proposalQueueRows.find((item) => item.id === proposalId);
  if (!row) return;
  const idInput = $("proposal-id");
  const preview = $("proposal-detail-preview");
  if (idInput) idInput.value = row.id;
  if (preview) preview.textContent = `Claim ${row.claim_id} | ${row.proposal_type} | payload ${JSON.stringify(row.proposal_payload)}`;
}

async function loadProposalQueue() {
  try {
    const headers = { Accept: "application/json" };
    if (authToken) headers.Authorization = `Bearer ${authToken}`;
    const res = await fetch(buildProposalQueueUrl(), { headers });
    if (!res.ok) throw new Error(`proposal queue failed: ${res.status}`);
    proposalQueueRows = await res.json();
    renderProposalQueue(proposalQueueRows);
    if (proposalQueueRows[0]) populateProposalForm(proposalQueueRows[0].id);
  } catch (_err) {
    const meta = $("proposal-queue-meta");
    const list = $("proposal-queue-list");
    if (meta) meta.textContent = "Proposals unavailable";
    if (list) list.innerHTML = `<p class="note-copy">Sign in as reviewer/admin to triage proposals.</p>`;
  }
}

async function submitProposalAction(event) {
  event.preventDefault();
  const proposalId = $("proposal-id")?.value?.trim();
  const action = $("proposal-action")?.value;
  const reviewNotes = $("proposal-review-notes")?.value?.trim() || null;
  const status = $("proposal-submit-status");
  if (!proposalId || !action) {
    if (status) status.textContent = "Select a proposal and action.";
    return;
  }
  if (!authToken) {
    if (status) status.textContent = "Sign in before proposal actions.";
    return;
  }
  try {
    const res = await fetch(`/api/v1/claims/proposals/${encodeURIComponent(proposalId)}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json", Authorization: `Bearer ${authToken}` },
      body: JSON.stringify({ review_notes: reviewNotes }),
    });
    if (!res.ok) throw new Error(`proposal action failed: ${res.status}`);
    await loadProposalQueue();
    if (status) status.textContent = "Proposal action saved.";
  } catch (err) {
    if (status) status.textContent = err instanceof Error ? err.message : "Proposal action failed.";
  }
}

// ── Tab switching ─────────────────────────────────────────────────────────────

// Visibility rules per tab. Each entry lists element IDs that should be VISIBLE
// for that tab; everything else in the workspace is hidden.
// "header#compare-hero" is a <header>, not a <section>, so it's handled separately.
const TAB_VISIBILITY = {
  compare: {
    header: true,
    sections: ["candidate-cards", "compare-controls-section", "compare-contrast", "compare-matrix-board"],
  },
  matrix: {
    header: false,
    sections: ["compare-matrix-board"],
  },
  claims: {
    header: false,
    sections: ["published-claims-view"],
  },
  stances: {
    header: false,
    sections: ["stances-view"],
  },
  methods: {
    header: false,
    sections: ["methods-view"],
  },
};

// All section IDs that are ever toggled — used to hide everything not in the active set.
const ALL_MANAGED_SECTIONS = [
  "candidate-cards",
  "compare-controls-section",
  "compare-contrast",
  "compare-matrix-board",
  "published-claims-view",
  "stances-view",
  "methods-view",
];

function setActiveTab(tabName) {
  document.querySelectorAll(".rail-link[data-tab]").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === tabName);
  });

  const rule = TAB_VISIBILITY[tabName] ?? TAB_VISIBILITY.compare;
  const visibleSet = new Set(rule.sections);

  // Toggle hero header
  const hero = $("compare-hero");
  if (hero) hero.hidden = !rule.header;

  // Toggle managed sections
  ALL_MANAGED_SECTIONS.forEach((id) => {
    const el = $(id);
    if (el) el.hidden = !visibleSet.has(id);
  });
}

function bindTabNav() {
  document.querySelectorAll(".rail-link[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
  });
}

// ── Published Claims list ─────────────────────────────────────────────────────

function buildClaimsFromCompare(compare) {
  if (!compare) return [];
  const candidateMap = new Map((compare.candidates || []).map((c) => [c.id, c]));
  const claims = [];
  for (const issue of compare.issues || []) {
    for (const item of issue.items || []) {
      const candidate = candidateMap.get(item.candidate_id);
      claims.push({
        claim_id: item.claim_id,
        candidate_id: item.candidate_id,
        candidate_name: candidate?.name ?? "Unknown",
        candidate_party: candidate?.party ?? "",
        issue_tag: issue.issue_tag,
        claim_text: item.claim_text,
        verdict: item.verdict,
        confidence: item.confidence,
        rationale: item.rationale,
        citation_notes: item.citation_notes,
        sources: item.sources || [],
        warnings: item.warnings || [],
      });
    }
  }
  const ORDER = { unsupported: 0, mixed: 1, supported: 2 };
  claims.sort((a, b) => {
    const vDiff = (ORDER[a.verdict] ?? 3) - (ORDER[b.verdict] ?? 3);
    return vDiff !== 0 ? vDiff : (a.candidate_name ?? "").localeCompare(b.candidate_name ?? "");
  });
  return claims;
}

function renderPublishedClaims(compare) {
  const listEl = $("claims-list");
  const countEl = $("claims-count");
  const candidateSelect = $("claims-filter-candidate");
  if (!listEl) return;

  const allClaims = buildClaimsFromCompare(compare);

  if (candidateSelect && candidateSelect.options.length === 1) {
    const names = [...new Map(allClaims.map((c) => [c.candidate_id, c.candidate_name])).entries()];
    names.sort((a, b) => a[1].localeCompare(b[1]));
    names.forEach(([id, name]) => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = name;
      candidateSelect.appendChild(opt);
    });
  }

  const verdictFilter = $("claims-filter-verdict")?.value ?? "";
  const candidateFilter = $("claims-filter-candidate")?.value ?? "";
  const issueFilter = ($("claims-filter-issue")?.value ?? "").trim().toLowerCase();

  const filtered = allClaims.filter((c) => {
    if (verdictFilter && c.verdict !== verdictFilter) return false;
    if (candidateFilter && c.candidate_id !== candidateFilter) return false;
    if (issueFilter && !String(c.issue_tag ?? "").toLowerCase().includes(issueFilter)) return false;
    return true;
  });

  if (countEl) countEl.textContent = `${filtered.length} claim${filtered.length !== 1 ? "s" : ""}`;

  if (filtered.length === 0) {
    listEl.innerHTML = `<p class="note-copy">No published claims match the current filters.</p>`;
    return;
  }

  listEl.innerHTML = filtered.map((c) => {
    const vClass = verdictClass(c.verdict);
    const vLabel = formatVerdictLabel(c.verdict);
    const pct = Number.isFinite(c.confidence) ? `${Math.round(c.confidence * 100)}%` : "";
    const rationale = c.rationale?.trim() || "No rationale recorded.";
    const citationNotes = c.citation_notes?.trim() || "";
    let sourceLinksHtml = "";
    for (const s of c.sources || []) {
      if (!s.url) continue;
      let hostname = s.url;
      try { hostname = new URL(s.url).hostname.replace(/^www\./, ""); } catch (_) {}
      const label = s.publisher || hostname;
      const cls = s.source_class === "primary" ? "source-primary" : "source-secondary";
      sourceLinksHtml += `<a class="source-link ${cls}" href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>`;
    }
    const warningPills = (c.warnings || []).filter((w) => w.code)
      .map((w) => `<span class="mini-tag mini-tag-alert">${escapeHtml(w.code)}</span>`).join("");

    return `
      <article class="claim-card ${stanceClass(c.verdict)}">
        <header class="claim-card-header">
          <div class="claim-card-meta">
            <span class="claim-candidate">${escapeHtml(c.candidate_name)}${c.candidate_party ? ` <span class="claim-party">(${escapeHtml(c.candidate_party)})</span>` : ""}</span>
            <span class="claim-issue-tag">${escapeHtml(c.issue_tag)}</span>
          </div>
          <div class="claim-verdict-row">
            <span class="mini-tag ${vClass}">${escapeHtml(vLabel)}</span>
            ${pct ? `<span class="claim-confidence">${pct} confidence</span>` : ""}
          </div>
        </header>
        <p class="claim-text">&ldquo;${escapeHtml(c.claim_text)}&rdquo;</p>
        <details class="claim-details">
          <summary>Reviewer analysis &amp; sources</summary>
          <div class="claim-details-body">
            <p class="claim-section-label">Why this verdict</p>
            <p class="claim-rationale">${escapeHtml(rationale)}</p>
            ${citationNotes ? `<p class="claim-section-label">Citation notes</p><p class="claim-rationale">${escapeHtml(citationNotes)}</p>` : ""}
            ${sourceLinksHtml ? `<p class="claim-section-label">Sources</p><div class="claim-sources">${sourceLinksHtml}</div>` : ""}
            ${warningPills ? `<p class="claim-section-label">Reviewer flags</p><div class="claim-warnings">${warningPills}</div>` : ""}
          </div>
        </details>
      </article>`;
  }).join("");
}

function bindClaimsFilters() {
  ["claims-filter-verdict", "claims-filter-candidate"].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener("change", () => renderPublishedClaims(compareRawState));
  });
  const issueInput = $("claims-filter-issue");
  if (issueInput) issueInput.addEventListener("input", () => renderPublishedClaims(compareRawState));
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  await loadRaceOptions();
  bindTabNav();
  bindCompareControls();
  bindClaimsFilters();
  await loadCompare();
}

init();
