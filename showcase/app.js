"use strict";

/*
 * Self-contained fictional editorial exhibit.
 * Do not replace with production data or attach privileged API credentials.
 * This script makes NO network requests and stores NO browser state.
 */
const RECORDS = Object.freeze([
  {
    id: "SRC-001", kind: "original", kindLabel: "ORIGINAL / PUBLIC NOTICE",
    source: "Civic Notices Office", date: "08 AUG 2026", dateISO: "2026-08-08",
    title: "Transit corridor notice: draft route and estimate released",
    short: "Original public notice",
    excerpt: "The proposed corridor is listed at 18 kilometres, with a preliminary allocation of 240 units. Both figures remain subject to review.",
    note: "This is the starting document for the fictional case. It provides an origin for the published figures, not independent proof that they are correct.",
    lineage: "Primary document", status: "Original record", badge: "ORIGINAL",
    timeline: "The primary notice is first published with a draft distance and allocation."
  },
  {
    id: "SRC-002", kind: "derived", kindLabel: "FOLLOW-UP / DERIVED REPORT",
    source: "Metro Desk", date: "09 AUG 2026", dateISO: "2026-08-09",
    title: "City desk reports 18 km proposed corridor from public notice",
    short: "Article references initial notice",
    excerpt: "According to the public notice, the draft proposal covers an 18-kilometre corridor and an allocation of 240 units.",
    note: "This fictional article explicitly attributes its figures to the same notice. It is another report, not a second independent source for the numbers.",
    lineage: "Derived from SRC-001", status: "Attribution present", badge: "DERIVED",
    timeline: "A publication summarizes the notice and carries the same original figures."
  },
  {
    id: "SRC-003", kind: "derived", kindLabel: "FOLLOW-UP / SHARED LINEAGE",
    source: "Regional Wire", date: "10 AUG 2026", dateISO: "2026-08-10",
    title: "Regional report repeats corridor estimate without new documentation",
    short: "Repetition of the same source",
    excerpt: "The project could run for 18 kilometres, with a draft 240-unit allocation noted in the announcement.",
    note: "Similar numbers from separate headlines can still originate in a single underlying document. The shared evidence lineage matters more than the publication count.",
    lineage: "Derived from SRC-001", status: "Shared source", badge: "DERIVED",
    timeline: "A second publisher repeats the notice without adding an independent record."
  },
  {
    id: "SRC-004", kind: "revision", kindLabel: "UPDATE / SOURCE REVISION",
    source: "Civic Notices Office", date: "12 AUG 2026", dateISO: "2026-08-12",
    title: "Revised notice adjusts allocation; original capture retained",
    short: "New version of primary record",
    excerpt: "The corridor remains a draft 18 kilometres. The revised preliminary allocation is 215 units, replacing the earlier figure of 240.",
    note: "The revised notice supersedes a figure, but the earlier capture remains important for explaining downstream coverage. A corrected source is not an independently confirmed outcome.",
    lineage: "Revision of SRC-001", status: "Change to review", badge: "REVISION",
    timeline: "The issuing office revises the allocation from 240 to 215 units."
  }
]);

// Synthetic claims illustrate source changes; they are not factual verdicts.
const CLAIMS = Object.freeze([
  {
    id: "CLM-01", title: "Proposed corridor length", before: "18 kilometres",
    after: "18 kilometres", status: "UNCHANGED IN SOURCE", tone: "steady",
    summary: "Both versions of the fictional notice describe an 18-kilometre draft. Reports repeating that source are not additional confirmation.",
    question: "Can the proposed route be checked against an independent planning document?",
    related: "SRC-004", relatedLabel: "Inspect revised notice ↗"
  },
  {
    id: "CLM-02", title: "Preliminary allocation", before: "240 units",
    after: "215 units", status: "REVISED · SUPERSEDED", tone: "revised",
    summary: "The issuing office replaces its initial 240-unit draft figure with 215. The old capture is retained to explain coverage of the earlier amount.",
    question: "When was the revision posted, and which downstream reports still cite 240?",
    related: "SRC-004", relatedLabel: "Compare revision ↗"
  },
  {
    id: "CLM-03", title: "Independent corroboration", before: "1 originating notice",
    after: "2 derived reports", status: "SHARED SOURCE ORIGIN", tone: "shared",
    summary: "The Metro Desk and Regional Wire reports refer back to one invented primary notice. Their repetition does not supply independent evidence for its numbers.",
    question: "Which independent document or firsthand reporting could verify the assertion?",
    related: "SRC-003", relatedLabel: "Inspect derived report ↗"
  }
]);

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {filter: "all", search: "", selected: RECORDS[0].id, view: "analysis", claim: CLAIMS[0].id, lineageSelected: RECORDS[0].id, timelineSelected: RECORDS[0].id, coverageLeft: "SRC-001", coverageRight: "SRC-002"};
const list = $("#record-list");
const count = $("#record-count");
const search = $("#record-search");

function filteredRecords() {
  return RECORDS.filter((r) => {
    const filterMatch = state.filter === "all" || r.kind === state.filter;
    const query = state.search.trim().toLocaleLowerCase();
    const textMatch = !query || [r.title, r.source, r.id, r.kindLabel].join(" ").toLocaleLowerCase().includes(query);
    return filterMatch && textMatch;
  });
}
function makeElement(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function renderRecordList() {
  const records = filteredRecords();
  if (records.length && !records.some((r) => r.id === state.selected)) {
    state.selected = records[0].id;
    hideComparison();
  }
  count.textContent = records.length + (records.length === 1 ? " record" : " records");
  list.replaceChildren();
  if (!records.length) {
    hideComparison();
    list.append(makeElement("p", "record-empty", "No matching records. Try another source or clear the filter."));
    state.selected = null;
    renderDetail();
    return;
  }
  for (const r of records) {
    const button = makeElement("button", "record-item" + (r.id === state.selected ? " is-selected" : ""));
    button.type = "button";
    button.setAttribute("aria-pressed", String(r.id === state.selected));
    button.setAttribute("aria-label", "Inspect " + r.source + ": " + r.title);
    const top = makeElement("div", "record-item__top");
    top.append(makeElement("span", "", r.source), makeElement("span", "record-item__tag", r.badge));
    button.append(top, makeElement("h4", "", r.title));
    const bottom = makeElement("div", "record-item__bottom");
    bottom.append(makeElement("span", "", r.id), makeElement("span", "", r.date));
    button.append(bottom);
    button.addEventListener("click", () => {
      state.selected = r.id;
      hideComparison();
      renderRecordList();
    });
    list.append(button);
  }
  renderDetail();
}
function put(id, text) {
  const node = document.getElementById(id);
  if (node) node.textContent = text;
}
function renderDetail() {
  const r = RECORDS.find((record) => record.id === state.selected);
  const fields = {
    "detail-kind": r?.kindLabel || "NO MATCHES",
    "detail-date": r?.date || "—",
    "detail-title": r?.title || "No matching source records",
    "detail-source": r?.source || "—",
    "detail-id": r?.id || "—",
    "detail-excerpt": r?.excerpt || "Clear the search or change the record filter to explore the fictional case.",
    "detail-note": r?.note || "No record is selected.",
    "detail-lineage": r?.lineage || "—",
    "detail-status": r?.status || "—"
  };
  for (const [key, value] of Object.entries(fields)) put(key, value);
  const compare = $("#compare-button");
  compare.disabled = !r;
  compare.setAttribute("aria-expanded", String(!$("#comparison-panel").hidden));
  if (r && !$("#comparison-panel").hidden) renderComparison();
}
// Highlight only the known fictional allocation change. Never interpolate article text as HTML.
function renderMarkedExcerpt(id, passage, needle) {
  const element = document.getElementById(id);
  element.replaceChildren();
  if (!needle || !passage.includes(needle)) {
    element.textContent = passage;
    return;
  }
  const position = passage.indexOf(needle);
  const highlight = makeElement("mark", "changed-figure", needle);
  element.append(
    document.createTextNode(passage.slice(0, position)),
    highlight,
    document.createTextNode(passage.slice(position + needle.length))
  );
}
function renderComparison() {
  const first = RECORDS[0];
  const selected = RECORDS.find((r) => r.id === state.selected);
  if (!selected) return;
  const revised = selected.kind === "revision";
  renderMarkedExcerpt("compare-original", first.excerpt, revised ? "240" : null);
  renderMarkedExcerpt("compare-selected", selected.excerpt, revised ? "215" : null);
  put("compare-note", revised
    ? "Recorded change: 240 → 215 units. Both amounts are fictional; the highlight indicates a version difference, not verification."
    : selected.id === first.id
      ? "This is the original notice. Select a derived report or revision to compare wording."
      : "Wording changes, but the figures still trace to the same original notice.");
}
function hideComparison() {
  $("#comparison-panel").hidden = true;
  $("#compare-button").setAttribute("aria-expanded", "false");
}
// Expose a consistent path from the guided tour, lineage diagram and timeline.
function selectRecord(id, {compare = false, focus = false} = {}) {
  const selected = RECORDS.find((r) => r.id === id);
  if (!selected) return;
  // Reset filters when a tour link points to an otherwise hidden record.
  if (!filteredRecords().some((r) => r.id === id)) {
    state.filter = "all";
    state.search = "";
    search.value = "";
    $$("[data-filter]").forEach((button) => {
      const active = button.dataset.filter === "all";
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }
  state.selected = id;
  state.lineageSelected = id;
  state.timelineSelected = id;
  renderLineageInspector();
  renderTimelineInspector();
  hideComparison();
  setView("analysis");
  renderRecordList();
  if (compare) {
    $("#comparison-panel").hidden = false;
    $("#compare-button").setAttribute("aria-expanded", "true");
    renderComparison();
  }
  if (focus) {
    const target = compare ? $("#comparison-panel") : $("#panel-analysis");
    target.focus({preventScroll:true});
    target.scrollIntoView({behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block:"nearest"});
  }
}
function setView(view, focusTab = false) {
  if (!["analysis", "lineage", "timeline", "audit", "coverage"].includes(view)) return;
  state.view = view;
  for (const v of ["analysis", "lineage", "timeline", "audit", "coverage"]) {
    const selected = v === view;
    const tab = document.getElementById("tab-" + v);
    document.getElementById("panel-" + v).hidden = !selected;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    tab.classList.toggle("is-current", selected);
  }
  if (focusTab) document.getElementById("tab-" + view).focus();
}
function renderLineageInspector() {
  const record = RECORDS.find((item) => item.id === state.lineageSelected) || RECORDS[0];
  $$("[data-lineage-record]").forEach((button) => {
    const chosen = button.dataset.lineageRecord === record.id;
    button.classList.toggle("is-selected", chosen);
    button.setAttribute("aria-pressed", String(chosen));
  });
  put("lineage-detail-kind", record.kindLabel);
  put("lineage-detail-id", record.id);
  put("lineage-detail-title", record.title);
  put("lineage-detail-source", record.source);
  put("lineage-detail-note", record.note);
  put("lineage-open-record", record.kind === "revision" ? "Compare revision with original ↗" : "Inspect selected passage ↗");
}

function renderClaim() {
  const claim = CLAIMS.find((item) => item.id === state.claim) || CLAIMS[0];
  $$("[data-claim]").forEach((button) => {
    const active = button.dataset.claim === claim.id;
    button.classList.toggle("is-current", active);
    button.setAttribute("aria-pressed", String(active));
  });
  put("audit-title", claim.title);
  put("audit-before", claim.before);
  put("audit-after", claim.after);
  put("audit-status", claim.status);
  put("audit-summary", claim.summary);
  put("audit-review", claim.question);
  put("audit-related", claim.relatedLabel);
  $("#audit-status").className = "audit-state audit-state--" + claim.tone;
}

function renderTimelineInspector() {
  const index = Math.max(0, RECORDS.findIndex((record) => record.id === state.timelineSelected));
  const record = RECORDS[index];
  $$("[data-timeline-record]").forEach((button) => {
    const active = button.dataset.timelineRecord === record.id;
    button.classList.toggle("is-current", active);
    button.setAttribute("aria-pressed", String(active));
  });
  put("timeline-detail-index", String(index + 1).padStart(2, "0") + " / " + String(RECORDS.length).padStart(2, "0"));
  put("timeline-detail-kind", record.kindLabel);
  put("timeline-detail-date", record.date);
  $("#timeline-detail-date").dateTime = record.dateISO;
  put("timeline-detail-title", record.title);
  put("timeline-detail-text", record.timeline);
  put("timeline-detail-source", record.source);
  put("timeline-detail-lineage", record.lineage);
  put("timeline-detail-note", record.note);
  put("timeline-open", record.kind === "revision" ? "Compare correction ↗" : "Inspect passage ↗");
  $("#timeline-prev").disabled = index === 0;
  $("#timeline-next").disabled = index === RECORDS.length - 1;
  $("#timeline-detail-kind").className = "chronology__kind chronology__kind--" + record.kind;
}

function chooseTimelineRecord(id) {
  if (!RECORDS.some((record) => record.id === id)) return;
  state.timelineSelected = id;
  renderTimelineInspector();
}

function stepTimeline(direction) {
  const currentIndex = RECORDS.findIndex((record) => record.id === state.timelineSelected);
  const targetIndex = currentIndex + direction;
  if (targetIndex >= 0 && targetIndex < RECORDS.length) {
    chooseTimelineRecord(RECORDS[targetIndex].id);
  }
}

function renderTimeline() {
  const node = $("#demo-timeline");
  node.replaceChildren();
  for (const record of RECORDS) {
    const li = makeElement("li", "chronology__item chronology__item--" + record.kind);
    const button = makeElement("button", "timeline-select chronology__event");
    button.type = "button";
    button.dataset.timelineRecord = record.id;
    button.setAttribute("aria-pressed", "false");
    button.setAttribute("aria-label", "Preview " + record.source + ": " + record.short);
    const time = makeElement("time", "chronology__event-date", record.date);
    time.dateTime = record.dateISO;
    button.append(
      time,
      makeElement("span", "chronology__event-kind", record.badge),
      makeElement("strong", "chronology__event-title", record.short),
      makeElement("span", "chronology__event-id", record.id)
    );
    button.addEventListener("click", () => chooseTimelineRecord(record.id));
    li.append(button);
    node.append(li);
  }
  renderTimelineInspector();
}

$("#timeline-prev").addEventListener("click", () => stepTimeline(-1));
$("#timeline-next").addEventListener("click", () => stepTimeline(1));
$("#timeline-open").addEventListener("click", () => {
  const record = RECORDS.find((item) => item.id === state.timelineSelected);
  if (record) selectRecord(record.id, {compare: record.kind === "revision", focus:true});
});

// Coverage comparisons are editorial annotations over the four invented captures.
// Identical wording or common attribution never implies independently verified facts.
function renderCoverage() {
  const left = RECORDS.find((record) => record.id === state.coverageLeft) || RECORDS[0];
  const right = RECORDS.find((record) => record.id === state.coverageRight) || RECORDS[1];
  $("#coverage-left").value = left.id;
  $("#coverage-right").value = right.id;
  for (const [side, record] of [["left", left], ["right", right]]) {
    put("coverage-" + side + "-id", record.id);
    put("coverage-" + side + "-kind", record.kindLabel);
    put("coverage-" + side + "-title", record.title);
    put("coverage-" + side + "-source", record.source + " · " + record.date);
    put("coverage-" + side + "-lineage", record.lineage);
  }

  const sameRecord = left.id === right.id;
  const includesRevision = left.kind === "revision" || right.kind === "revision";
  // Highlight an explicitly recorded change, not an inferred truthfulness score.
  renderMarkedExcerpt("coverage-left-excerpt", left.excerpt,
    !sameRecord && includesRevision ? (left.kind === "revision" ? "215" : "240") : null);
  renderMarkedExcerpt("coverage-right-excerpt", right.excerpt,
    !sameRecord && includesRevision ? (right.kind === "revision" ? "215" : "240") : null);

  let heading, explanation, label;
  if (sameRecord) {
    heading = "Same capture selected twice";
    explanation = "Both panels show " + left.id + ". Select a different record to compare reporting or revisions. A duplicate capture provides no new corroboration.";
    label = "SAME RECORD";
  } else if (includesRevision) {
    heading = "A revised figure; the same originating source";
    explanation = "The fictional issuing office changed the draft allocation from 240 to 215 units. Both captures trace to the same originating notice; older reports may still cite 240. This change does not independently verify the proposal.";
    label = "REVISION";
  } else if (left.kind === "derived" && right.kind === "derived") {
    heading = "Two reports; one originating document";
    explanation = "Metro Desk and Regional Wire repeat the same invented public notice. These are separate publications, not two independent confirmations of the figures.";
    label = "SHARED ORIGIN";
  } else {
    heading = "Shared originating notice";
    explanation = "The follow-up report attributes its figures to the same original public notice. Its existence is not a second independent source for the claim.";
    label = "SHARED ORIGIN";
  }
  put("coverage-relationship", heading);
  put("coverage-interpretation", explanation);
  put("coverage-class", label);
  $("#coverage-class").className = "coverage-finding__chip coverage-finding__chip--" +
    (sameRecord ? "same" : includesRevision ? "revision" : "shared");
}

$("#coverage-left").addEventListener("change", (event) => {
  if (!RECORDS.some((record) => record.id === event.target.value)) return;
  state.coverageLeft = event.target.value;
  renderCoverage();
});
$("#coverage-right").addEventListener("change", (event) => {
  if (!RECORDS.some((record) => record.id === event.target.value)) return;
  state.coverageRight = event.target.value;
  renderCoverage();
});
$("#coverage-swap").addEventListener("click", () => {
  const priorLeft = state.coverageLeft;
  state.coverageLeft = state.coverageRight;
  state.coverageRight = priorLeft;
  renderCoverage();
});
$("#coverage-open-left").addEventListener("click", () => {
  const record = RECORDS.find((item) => item.id === state.coverageLeft);
  if (record) selectRecord(record.id, {compare: record.kind === "revision", focus:true});
});
$("#coverage-open-right").addEventListener("click", () => {
  const record = RECORDS.find((item) => item.id === state.coverageRight);
  if (record) selectRecord(record.id, {compare: record.kind === "revision", focus:true});
});

// Claim selection only changes local labels and actions; no network or browser state.
$$("[data-claim]").forEach((button) => {
  button.addEventListener("click", () => {
    state.claim = button.dataset.claim;
    renderClaim();
  });
});
$("#audit-original").addEventListener("click", () => selectRecord("SRC-001", {focus:true}));
$("#audit-related").addEventListener("click", () => {
  const claim = CLAIMS.find((item) => item.id === state.claim);
  if (claim) selectRecord(claim.related, {compare: claim.related === "SRC-004" && claim.id === "CLM-02", focus:true});
});

// Text-only DOM operations avoid interpolating search input into HTML.
$$("[data-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    state.filter = button.dataset.filter;
    $$("[data-filter]").forEach((other) => {
      const active = other === button;
      other.classList.toggle("is-active", active);
      other.setAttribute("aria-pressed", String(active));
    });
    renderRecordList();
  });
});
search.addEventListener("input", (event) => {
  state.search = event.target.value;
  renderRecordList();
});
search.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    search.value = "";
    state.search = "";
    renderRecordList();
  }
});
$$("[data-view]").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
  button.addEventListener("keydown", (event) => {
    const views = ["analysis", "lineage", "timeline", "audit", "coverage"];
    const current = views.indexOf(button.dataset.view);
    let next = current;
    if (event.key === "ArrowRight") next = (current + 1) % views.length;
    else if (event.key === "ArrowLeft") next = (current + views.length - 1) % views.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = views.length - 1;
    else return;
    event.preventDefault();
    setView(views[next], true);
  });
});
$("#compare-button").addEventListener("click", () => {
  const panel = $("#comparison-panel");
  panel.hidden = !panel.hidden;
  $("#compare-button").setAttribute("aria-expanded", String(!panel.hidden));
  if (!panel.hidden) renderComparison();
});
$("#close-compare").addEventListener("click", () => {
  hideComparison();
  $("#compare-button").focus();
});
$$("[data-lineage-record]").forEach((button) => {
  button.addEventListener("click", () => {
    state.lineageSelected = button.dataset.lineageRecord;
    renderLineageInspector();
  });
});
$("#lineage-open-record").addEventListener("click", () => {
  const selected = state.lineageSelected;
  selectRecord(selected, {compare: selected === "SRC-004", focus:true});
});
$$("[data-jump]").forEach((button) => {
  button.addEventListener("click", () => selectRecord(button.dataset.jump, {
    compare: button.dataset.compare === "true", focus:true
  }));
});
$("#reset-workbench").addEventListener("click", () => {
  state.filter = "all";
  state.search = "";
  search.value = "";
  state.selected = RECORDS[0].id;
  state.claim = CLAIMS[0].id;
  state.lineageSelected = RECORDS[0].id;
  state.timelineSelected = RECORDS[0].id;
  state.coverageLeft = "SRC-001";
  state.coverageRight = "SRC-002";
  renderCoverage();
  renderClaim();
  renderLineageInspector();
  renderTimelineInspector();
  $$("[data-filter]").forEach((button) => {
    const active = button.dataset.filter === "all";
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  hideComparison();
  setView("analysis");
  renderRecordList();
});
const menu = $("#menu-toggle");
const nav = $("#primary-nav");
menu.addEventListener("click", () => {
  const opened = menu.getAttribute("aria-expanded") !== "true";
  menu.setAttribute("aria-expanded", String(opened));
  nav.classList.toggle("is-open", opened);
});
nav.querySelectorAll("a").forEach((a) => {
  a.addEventListener("click", () => {
    nav.classList.remove("is-open");
    menu.setAttribute("aria-expanded", "false");
  });
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && nav.classList.contains("is-open")) {
    nav.classList.remove("is-open");
    menu.setAttribute("aria-expanded", "false");
    menu.focus();
  }
});
$("#site-year").textContent = String(new Date().getFullYear());
renderCoverage();
renderClaim();
renderLineageInspector();
renderTimeline();
renderRecordList();
setView("analysis");
