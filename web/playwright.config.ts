import { defineConfig, devices } from "@playwright/test";

// Starts the workflow service and Next.js, then drives the app in a real browser.
// Locally, servers that are already running are reused; in CI both start fresh,
// with a production build of the web app.
// PYTHON picks the interpreter for the workflow service (default "python").
// PW_CHANNEL picks an installed browser, for example PW_CHANNEL=msedge on Windows.

const CI = Boolean(process.env.CI);
export const CONNECTOR_TOKEN = process.env.CONNECTOR_TOKEN ?? "connector-token-for-e2e-only-0001";
export const DEMO_PASSWORD = process.env.DEMO_PASSWORD ?? "e2e-demo-password";
export const EXTRACTOR_TOKEN = process.env.EXTRACTOR_TOKEN ?? "extractor-token-for-e2e-only-0001";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  retries: CI ? 1 : 0,
  workers: 1,
  reporter: CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], channel: process.env.PW_CHANNEL || undefined } }],
  webServer: [
    {
      command: `${process.env.PYTHON ?? "python"} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: "../workflow",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !CI,
      timeout: 60_000,
      env: {
        DATABASE_URL: process.env.DATABASE_URL ?? "postgresql+psycopg://postgres@127.0.0.1:5433/priorauth_e2e",
        CONNECTOR_TOKEN,
        EXTRACTOR_TOKEN,
        DEMO_PASSWORD,
        // Cases wait for extraction; the test plays the worker (CI also runs the real one).
        EXTRACTION_MODE: "worker",
        SEED_DEMO_DATA: "1",
        APP_ENV: "dev",
      },
    },
    {
      command: CI ? "npm run build && npm run start" : "npm run dev",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: !CI,
      timeout: 180_000,
    },
  ],
});
