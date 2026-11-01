"use strict";
const { test, expect } = require("@playwright/test");

test.beforeEach(async ({ page }) => {
  page.__showcaseErrors = [];
  page.on("pageerror", (error) => page.__showcaseErrors.push(error.message));
  await page.goto("/");
  await expect(page.locator("#record-count")).toHaveText("4 records");
});

test.afterEach(async ({ page }) => {
  expect(page.__showcaseErrors, "Uncaught JavaScript errors in the showcase").toEqual([]);
});

test("initializes the reader and lists four fictional captures", async ({ page }) => {
  await expect(page.locator("#record-list .record-item")).toHaveCount(4);
  await expect(page.locator("#detail-id")).toHaveText("SRC-001");
  await expect(page.locator("#tab-analysis")).toHaveAttribute("aria-selected", "true");
});

test("search, filter, escape and reset work together", async ({ page }) => {
  await page.locator("#record-search").fill("metro");
  await expect(page.locator("#record-count")).toHaveText("1 record");
  await expect(page.locator("#record-list .record-item")).toHaveCount(1);
  await page.locator("#record-search").fill("this source does not exist");
  await expect(page.locator("#record-count")).toHaveText("0 records");
  await page.locator("#record-search").press("Escape");
  await expect(page.locator("#record-count")).toHaveText("4 records");

  await page.locator('[data-filter="derived"]').click();
  await expect(page.locator("#record-count")).toHaveText("2 records");
  await page.locator('[data-jump="SRC-004"]').click();
  await expect(page.locator("#record-count")).toHaveText("4 records");
  await expect(page.locator("#detail-id")).toHaveText("SRC-004");
  await expect(page.locator("#comparison-panel")).toBeVisible();

  await page.locator("#reset-workbench").click();
  await expect(page.locator("#detail-id")).toHaveText("SRC-001");
  await expect(page.locator("#comparison-panel")).toBeHidden();
  await expect(page.locator("#record-count")).toHaveText("4 records");
});

test("claim audit updates evidence and drills down to the revision", async ({ page }) => {
  await page.locator("#tab-audit").click();
  await expect(page.locator("#panel-audit")).toBeVisible();
  await page.locator('[data-claim="CLM-02"]').click();
  await expect(page.locator("#audit-before")).toHaveText("240 units");
  await expect(page.locator("#audit-after")).toHaveText("215 units");
  await expect(page.locator('[data-claim="CLM-02"]')).toHaveAttribute("aria-pressed", "true");
  await page.locator("#audit-related").click();
  await expect(page.locator("#tab-analysis")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#detail-id")).toHaveText("SRC-004");
  await expect(page.locator("#comparison-panel")).toBeVisible();
  await expect(page.locator("#compare-original mark")).toHaveText("240");
  await expect(page.locator("#compare-selected mark")).toHaveText("215");
});

test("lineage nodes preview relationships and open the selected source", async ({ page }) => {
  await page.locator("#tab-lineage").click();
  await expect(page.locator("#panel-lineage")).toBeVisible();
  await page.locator('[data-lineage-record="SRC-003"]').click();
  await expect(page.locator("#lineage-detail-id")).toHaveText("SRC-003");
  await expect(page.locator('[data-lineage-record="SRC-003"]')).toHaveAttribute("aria-pressed", "true");
  await page.locator("#lineage-open-record").click();
  await expect(page.locator("#detail-id")).toHaveText("SRC-003");
  await expect(page.locator("#tab-analysis")).toHaveAttribute("aria-selected", "true");

  await page.locator("#tab-lineage").click();
  await page.locator('[data-lineage-record="SRC-004"]').click();
  await expect(page.locator("#lineage-open-record")).toContainText("Compare revision");
  await page.locator("#lineage-open-record").click();
  await expect(page.locator("#comparison-panel")).toBeVisible();
  await expect(page.locator("#compare-selected mark")).toHaveText("215");
});

test("keyboard tab navigation supports arrows, Home and End", async ({ page }) => {
  await page.locator("#tab-analysis").focus();
  await page.keyboard.press("End");
  await expect(page.locator("#tab-review")).toBeFocused();
  await expect(page.locator("#tab-review")).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Home");
  await expect(page.locator("#tab-analysis")).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#tab-lineage")).toBeFocused();
  await expect(page.locator("#panel-lineage")).toBeVisible();
});

test("shows mobile navigation and keeps source links local", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.locator("#menu-toggle")).toBeVisible();
  await page.locator("#menu-toggle").click();
  await expect(page.locator("#menu-toggle")).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("#primary-nav")).toBeVisible();
  await page.locator('#primary-nav a[href="#demo"]').click();
  await expect(page.locator("#menu-toggle")).toHaveAttribute("aria-expanded", "false");
  await page.locator("#tab-lineage").click();
  await expect(page.locator("#lineage-open-record")).toBeVisible();
});

test("does not request a remote publisher or service", async ({ page }) => {
  const remoteRequests = [];
  page.on("request", (request) => {
    if (!request.url().startsWith("http://127.0.0.1:8088/")) {
      remoteRequests.push(request.url());
    }
  });
  await page.reload();
  await expect(page.locator("#record-count")).toHaveText("4 records");
  expect(remoteRequests).toEqual([]);
});

test("timeline previews captures before an explicit evidence drilldown", async ({ page }) => {
  await page.locator("#tab-timeline").click();
  await expect(page.locator("#panel-timeline")).toBeVisible();
  await expect(page.locator("[data-timeline-record]")).toHaveCount(4);
  await expect(page.locator("#timeline-detail-index")).toHaveText("01 / 04");
  await expect(page.locator("#timeline-prev")).toBeDisabled();
  await page.locator("#timeline-next").click();
  await expect(page.locator("#timeline-detail-index")).toHaveText("02 / 04");
  await expect(page.locator("#timeline-detail-source")).toHaveText("Metro Desk");
  await expect(page.locator("#tab-timeline")).toHaveAttribute("aria-selected", "true");

  await page.locator('[data-timeline-record="SRC-004"]').click();
  await expect(page.locator('[data-timeline-record="SRC-004"]')).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#timeline-detail-index")).toHaveText("04 / 04");
  await expect(page.locator("#timeline-next")).toBeDisabled();
  await expect(page.locator("#timeline-open")).toContainText("Compare correction");
  await page.locator("#timeline-open").click();
  await expect(page.locator("#tab-analysis")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#detail-id")).toHaveText("SRC-004");
  await expect(page.locator("#compare-original mark")).toHaveText("240");
  await expect(page.locator("#compare-selected mark")).toHaveText("215");
});

test("timeline keyboard selection and reset retain consistent state", async ({ page }) => {
  await page.locator("#tab-timeline").click();
  await page.locator('[data-timeline-record="SRC-003"]').focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#timeline-detail-index")).toHaveText("03 / 04");
  await expect(page.locator("#timeline-detail-lineage")).toHaveText("Derived from SRC-001");
  await page.locator("#timeline-prev").click();
  await expect(page.locator("#timeline-detail-index")).toHaveText("02 / 04");
  await page.locator("#reset-workbench").click();
  await page.locator("#tab-timeline").click();
  await expect(page.locator("#timeline-detail-index")).toHaveText("01 / 04");
  await expect(page.locator('[data-timeline-record="SRC-001"]')).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#timeline-prev")).toBeDisabled();
});


test("coverage compares inherited reporting and swapping captures", async ({ page }) => {
  await page.locator("#tab-coverage").click();
  await expect(page.locator("#panel-coverage")).toBeVisible();
  await expect(page.locator("#coverage-left-id")).toHaveText("SRC-001");
  await expect(page.locator("#coverage-right-id")).toHaveText("SRC-002");
  await expect(page.locator("#coverage-class")).toHaveText("SHARED ORIGIN");

  await page.locator("#coverage-left").selectOption("SRC-002");
  await page.locator("#coverage-right").selectOption("SRC-003");
  await expect(page.locator("#coverage-relationship")).toHaveText("Two reports; one originating document");
  await expect(page.locator("#coverage-left-lineage")).toHaveText("Derived from SRC-001");
  await expect(page.locator("#coverage-right-lineage")).toHaveText("Derived from SRC-001");
  await expect(page.locator("#coverage-left-excerpt")).toContainText("240");
  await expect(page.locator("#coverage-right-excerpt")).toContainText("240");

  await page.locator("#coverage-swap").click();
  await expect(page.locator("#coverage-left").locator("option:checked")).toHaveAttribute("value", "SRC-003");
  await expect(page.locator("#coverage-right").locator("option:checked")).toHaveAttribute("value", "SRC-002");
  await expect(page.locator("#coverage-relationship")).toHaveText("Two reports; one originating document");
});

test("coverage highlights a revision and opens its supporting passage", async ({ page }) => {
  await page.locator("#tab-coverage").click();
  await page.locator("#coverage-right").selectOption("SRC-004");
  await expect(page.locator("#coverage-class")).toHaveText("REVISION");
  await expect(page.locator("#coverage-left-excerpt mark")).toHaveText("240");
  await expect(page.locator("#coverage-right-excerpt mark")).toHaveText("215");
  await expect(page.locator("#coverage-interpretation")).toContainText("same originating");
  await page.locator("#coverage-open-right").click();
  await expect(page.locator("#tab-analysis")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#detail-id")).toHaveText("SRC-004");
  await expect(page.locator("#compare-original mark")).toHaveText("240");
  await expect(page.locator("#compare-selected mark")).toHaveText("215");

  await page.locator("#tab-coverage").click();
  await expect(page.locator("#coverage-right")).toHaveValue("SRC-004");
  await page.locator("#reset-workbench").click();
  await page.locator("#tab-coverage").click();
  await expect(page.locator("#coverage-left")).toHaveValue("SRC-001");
  await expect(page.locator("#coverage-right")).toHaveValue("SRC-002");
  await expect(page.locator("#coverage-class")).toHaveText("SHARED ORIGIN");
});

test("coverage explains duplicate selection and keeps mobile controls usable", async ({ page }) => {
  await page.setViewportSize({width:375,height:812});
  await page.locator("#tab-coverage").click();
  await page.locator("#coverage-left").selectOption("SRC-003");
  await page.locator("#coverage-right").selectOption("SRC-003");
  await expect(page.locator("#coverage-class")).toHaveText("SAME RECORD");
  await expect(page.locator("#coverage-relationship")).toHaveText("Same capture selected twice");
  await expect(page.locator("#coverage-left-excerpt mark")).toHaveCount(0);
  await expect(page.locator("#coverage-right-excerpt mark")).toHaveCount(0);
  await expect(page.locator("#coverage-open-left")).toBeVisible();
  await expect(page.locator("#coverage-open-right")).toBeVisible();
  await page.locator("#coverage-open-left").click();
  await expect(page.locator("#detail-id")).toHaveText("SRC-003");
});

test("review desk keeps independent session notes per claim and tracks follow-ups", async ({ page }) => {
  await page.locator("#tab-review").click();
  await expect(page.locator("#panel-review")).toBeVisible();
  await expect(page.locator("#review-claim-id")).toHaveText("CLM-01");
  await expect(page.locator("#review-notes-count")).toHaveText("0");
  await expect(page.locator("#review-followups-count")).toHaveText("0");
  await page.locator("#review-note").fill("Check the route with independent plans.");
  await page.locator("#review-status").selectOption("follow-up");
  await expect(page.locator("#review-notes-count")).toHaveText("1");
  await expect(page.locator("#review-followups-count")).toHaveText("1");
  await page.locator('[data-review-claim="CLM-02"]').click();
  await expect(page.locator("#review-note")).toHaveValue("");
  await page.locator("#review-note").fill("Find the original publication timestamp.");
  await page.locator("#review-status").selectOption("editorial-review");
  await expect(page.locator("#review-notes-count")).toHaveText("2");
  await expect(page.locator("#review-followups-count")).toHaveText("1");
  await page.locator('[data-review-claim="CLM-01"]').click();
  await expect(page.locator("#review-note")).toHaveValue("Check the route with independent plans.");
  await expect(page.locator("#review-status")).toHaveValue("follow-up");
  await page.locator("#review-clear-note").click();
  await expect(page.locator("#review-notes-count")).toHaveText("1");
  await expect(page.locator("#review-followups-count")).toHaveText("1");
  await page.locator("#reset-workbench").click();
  await page.locator("#tab-review").click();
  await expect(page.locator("#review-notes-count")).toHaveText("0");
  await expect(page.locator("#review-followups-count")).toHaveText("0");
  await expect(page.locator("#review-status")).toHaveValue("unreviewed");
  await expect(page.locator("#review-note")).toHaveValue("");
});

test("audit handoff opens reviewer desk and traces the revised claim to its source", async ({ page }) => {
  await page.locator("#tab-audit").click();
  await page.locator('[data-claim="CLM-02"]').click();
  await page.locator("#audit-open-review").click();
  await expect(page.locator("#tab-review")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#review-claim-id")).toHaveText("CLM-02");
  await expect(page.locator("#review-claim-summary")).toContainText("215");
  await expect(page.locator("#review-open-primary")).toContainText("SRC-001");
  await expect(page.locator("#review-open-related")).toContainText("SRC-004");
  await page.locator("#review-open-related").click();
  await expect(page.locator("#tab-analysis")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#detail-id")).toHaveText("SRC-004");
  await expect(page.locator("#compare-selected mark")).toHaveText("215");
  await page.locator("#tab-review").click();
  await page.locator("#review-open-lineage").click();
  await expect(page.locator("#tab-lineage")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#lineage-detail-id")).toHaveText("SRC-001");
});

test("notes are never transmitted or persisted after reload", async ({ page }) => {
  const external = [];
  page.on("request", (request) => {
    if (!request.url().startsWith("http://127.0.0.1:8088/")) external.push(request.url());
  });
  await page.locator("#tab-review").click();
  await page.locator("#review-note").fill("A local draft only, not a published conclusion.");
  await page.locator("#review-status").selectOption("follow-up");
  await page.locator("#tab-coverage").click();
  await page.locator("#tab-review").click();
  await expect(page.locator("#review-note")).toHaveValue("A local draft only, not a published conclusion.");
  await page.reload();
  await page.locator("#tab-review").click();
  await expect(page.locator("#review-note")).toHaveValue("");
  await expect(page.locator("#review-status")).toHaveValue("unreviewed");
  await expect(page.locator("#review-followups-count")).toHaveText("0");
  expect(external).toEqual([]);
});

test("mobile reviewer queue remains keyboard usable and bounds typed notes", async ({ page }) => {
  await page.setViewportSize({width:375,height:812});
  await page.locator("#tab-review").click();
  await page.locator('[data-review-claim="CLM-03"]').focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#review-claim-id")).toHaveText("CLM-03");
  await expect(page.locator("#review-source-context")).toContainText("SRC-001");
  await expect(page.locator("#review-open-primary")).toContainText("SRC-002");
  await expect(page.locator("#review-open-related")).toContainText("SRC-003");
  await page.locator("#review-note").fill("x".repeat(650));
  await expect(page.locator("#review-note-count")).toHaveText("600 / 600");
  await expect(page.locator("#review-note")).toHaveValue("x".repeat(600));
  await page.locator("#review-open-primary").click();
  await expect(page.locator("#detail-id")).toHaveText("SRC-002");
});
