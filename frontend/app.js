const API_COMPARE_URL = "/api/v1/compare?state=TX&office=US%20Senate&limit_issues=8";

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

function formatPct(n) {
  if (!Number.isFinite(n)) return "--%";
  return `${Math.round(n * 100)}%`;
}

function formatAsOf(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "2-digit" });
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
  const candidates = compare.candidates.slice(0, 2);
  if (candidates.length < 2) return;

  const byId = new Map(candidates.map((c) => [c.id, c]));
  const countsByCandidate = tallyVerdicts(compare);

  const [a, b] = candidates;
  const aCounts = countsByCandidate.get(a.id);
  const bCounts = countsByCandidate.get(b.id);

  $("race-label").textContent = `${compare.race.state} ${compare.race.office} (example)`;

  $("candidate-a-name").textContent = a.name;
  // Use an ASCII separator to avoid encoding artifacts in some Windows shells/editors.
  $("candidate-a-role").textContent = `${a.office || compare.race.office} | ${a.state || compare.race.state}`;
  $("candidate-b-name").textContent = b.name;
  $("candidate-b-role").textContent = `${b.office || compare.race.office} | ${b.state || compare.race.state}`;

  const aRate = aCounts && aCounts.total ? aCounts.supported / aCounts.total : NaN;
  const bRate = bCounts && bCounts.total ? bCounts.supported / bCounts.total : NaN;

  $("candidate-a-supported-rate").textContent = formatPct(aRate);
  $("candidate-b-supported-rate").textContent = formatPct(bRate);
  $("candidate-a-supported-note").textContent = "Supported share among the issues shown below.";
  $("candidate-b-supported-note").textContent = "Supported share among the issues shown below.";

  $("candidate-a-supported-n").textContent = aCounts ? String(aCounts.supported) : "--";
  $("candidate-a-mixed-n").textContent = aCounts ? String(aCounts.mixed) : "--";
  $("candidate-a-insufficient-n").textContent = aCounts ? String(aCounts.insufficient) : "--";

  $("candidate-b-supported-n").textContent = bCounts ? String(bCounts.supported) : "--";
  $("candidate-b-mixed-n").textContent = bCounts ? String(bCounts.mixed) : "--";
  $("candidate-b-insufficient-n").textContent = bCounts ? String(bCounts.insufficient) : "--";

  const topTags = compare.issues.map((i) => i.issue_tag).slice(0, 5);
  const aList = $("candidate-a-issue-list");
  const bList = $("candidate-b-issue-list");
  aList.innerHTML = "";
  bList.innerHTML = "";
  for (const tag of topTags) {
    aList.insertAdjacentHTML("beforeend", `<li>${escapeHtml(tag)}</li>`);
    bList.insertAdjacentHTML("beforeend", `<li>${escapeHtml(tag)}</li>`);
  }
}

function renderContrastBand(compare) {
  const candidates = compare.candidates.slice(0, 2);
  if (candidates.length < 2) return;
  const [a, b] = candidates;

  const countsByCandidate = tallyVerdicts(compare);
  const aCounts = countsByCandidate.get(a.id);
  const bCounts = countsByCandidate.get(b.id);
  if (!aCounts || !bCounts) return;

  const safeRate = (num, den) => (den > 0 ? num / den : NaN);
  const supportedRate = (bucket) => safeRate(bucket.supported, bucket.total);
  const contradictedRate = (bucket) => safeRate((bucket.unsupported || 0) + (bucket.insufficient || 0), bucket.total);
  const unverifiedRate = (bucket) => safeRate(bucket.insufficient || 0, bucket.total);

  const mostSupported = supportedRate(aCounts) >= supportedRate(bCounts) ? a : b;
  const mostContradicted = contradictedRate(aCounts) >= contradictedRate(bCounts) ? a : b;
  const mostUnverified = unverifiedRate(aCounts) >= unverifiedRate(bCounts) ? a : b;

  const ms = $("contrast-most-supported");
  if (ms) ms.textContent = mostSupported.name;
  const mc = $("contrast-most-contradicted");
  if (mc) mc.textContent = mostContradicted.name;
  const mu = $("contrast-most-unverified");
  if (mu) mu.textContent = mostUnverified.name;

  let splitTag = "";
  for (const issue of compare.issues || []) {
    const aItem = issue.items?.find((it) => it.candidate_id === a.id);
    const bItem = issue.items?.find((it) => it.candidate_id === b.id);
    if (aItem && bItem && aItem.verdict !== bItem.verdict) {
      splitTag = issue.issue_tag;
      break;
    }
  }

  const ts = $("contrast-tightest-split");
  if (ts) ts.textContent = splitTag || (compare.issues?.[0]?.issue_tag ?? "No issues");
  const tsNote = $("contrast-tightest-split-note");
  if (tsNote) {
    tsNote.textContent = splitTag
      ? `First visible split: ${a.name} vs ${b.name} differ on this issue in the current window.`
      : "Pick an issue below to see the direct, side-by-side record.";
  }
}

function renderIssueList(compare, selectedIndex) {
  const container = $("issue-list");
  const candidates = compare.candidates.slice(0, 2);
  const [a, b] = candidates;

  const rows = compare.issues
    .map((issue, idx) => {
      const isSelected = idx === selectedIndex;
      const aItem = issue.items.find((it) => it.candidate_id === a.id);
      const bItem = issue.items.find((it) => it.candidate_id === b.id);

      const aTag = aItem
        ? `<span class="mini-tag ${verdictClass(aItem.verdict)}">${escapeHtml(shortName(a.name))}: ${escapeHtml(aItem.verdict)}</span>`
        : "";
      const bTag = bItem
        ? `<span class="mini-tag ${verdictClass(bItem.verdict)}">${escapeHtml(shortName(b.name))}: ${escapeHtml(bItem.verdict)}</span>`
        : "";

      return `
        <button class="issue-row ${isSelected ? "is-selected" : ""}" type="button" data-issue="${idx}">
          <span class="issue-name">${escapeHtml(issue.issue_tag)}</span>
          <span class="issue-tags">${aTag}${bTag}</span>
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
  const candidates = compare.candidates.slice(0, 2);
  if (!issue || candidates.length < 2) return;

  $("panel-title").textContent = issue.issue_tag;
  $("panel-summary").textContent = compare.race.disclaimer;
  $("panel-stamp").textContent = `As of ${formatAsOf(compare.race.as_of)}`;

  const html = candidates
    .map((c, idx) => {
      const item = issue.items.find((it) => it.candidate_id === c.id);
      if (!item) {
        return `
          <article class="stance">
            <span class="stance-label">${escapeHtml(idx === 0 ? "Candidate A" : "Candidate B")}</span>
            <p><strong>${escapeHtml(c.name)}</strong></p>
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
          <span class="stance-label">${escapeHtml(idx === 0 ? "Candidate A" : "Candidate B")}</span>
          <p><strong>${escapeHtml(c.name)}</strong></p>
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

async function init() {
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
      "Start the stack with `docker compose up -d --build` and seed data with `docker compose run --rm api python -m app.scripts.seed_tx_us_senate_example`.";
    $("panel-stamp").textContent = "No API response";
  }
}

init();
