"use strict";
const path = require("node:path");
const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: "**/*.spec.cjs",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: "list",
  timeout: 20000,
  expect: { timeout: 7000 },
  use: {
    baseURL: "http://127.0.0.1:8088/",
    trace: "retain-on-failure"
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"], browserName: "chromium" } }
  ],
  webServer: {
    command: "python3 -m http.server 8088 --bind 127.0.0.1 --directory showcase",
    cwd: path.resolve(__dirname, "../.."),
    url: "http://127.0.0.1:8088/",
    timeout: 30000,
    reuseExistingServer: !process.env.CI
  }
});
