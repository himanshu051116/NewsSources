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
  await expect(page.locator("#tab-audit")).toBeFocused();
  await expect(page.locator("#tab-audit")).toHaveAttribute("aria-selected", "true");
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

