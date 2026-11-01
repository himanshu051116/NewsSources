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

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {filter: "all", search: "", selected: RECORDS[0].id, view: "analysis"};
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
      renderDetail();
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
function renderComparison() {
  const first = RECORDS[0];
  const selected = RECORDS.find((r) => r.id === state.selected);
  if (!selected) return;
  put("compare-original", first.excerpt);
  put("compare-selected", selected.excerpt);
  put("compare-note", selected.kind === "revision"
    ? "The revised allocation is 215 rather than 240 units; these figures are fictional."
    : selected.id === first.id
      ? "This is the original notice. Select a follow-up or revision to compare different wording."
      : "The language changes, but the quoted figures trace back to the same original notice.");
}
function hideComparison() {
  $("#comparison-panel").hidden = true;
  $("#compare-button").setAttribute("aria-expanded", "false");
}
function setView(view, focusTab = false) {
  if (!["analysis", "lineage", "timeline"].includes(view)) return;
  state.view = view;
  for (const v of ["analysis", "lineage", "timeline"]) {
    const selected = v === view;
    const tab = document.getElementById("tab-" + v);
    document.getElementById("panel-" + v).hidden = !selected;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    tab.classList.toggle("is-current", selected);
  }
  if (focusTab) document.getElementById("tab-" + view).focus();
}
function renderTimeline() {
  const node = $("#demo-timeline");
  node.replaceChildren();
  for (const item of RECORDS) {
    const li = makeElement("li");
    const time = makeElement("time", "", item.date);
    time.dateTime = item.dateISO;
    li.append(time, makeElement("strong", "", item.short), makeElement("p", "", item.timeline));
    node.append(li);
  }
}

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
    const views = ["analysis", "lineage", "timeline"];
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
$("#close-compare").addEventListener("click", hideComparison);
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
renderTimeline();
renderRecordList();
setView("analysis");
