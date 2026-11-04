import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../..");
const apiDir = path.join(repo, "apps", "api");
const webDir = path.join(repo, "apps", "web");
const viteBin = path.join(webDir, "node_modules", "vite", "bin", "vite.js");

export default defineConfig({
  testDir: "./specs",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    channel: process.env.CI ? undefined : "chrome",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `python -m uvicorn veilpool_api.main:app --host 127.0.0.1 --port 8000`,
      cwd: apiDir,
      port: 8000,
      reuseExistingServer: true,
      timeout: 30_000,
      env: {
        VEILPOOL_MODE: "mock",
        VEILPOOL_ADMIN_TOKEN: "dev-admin",
        DATABASE_URL: "sqlite:///./veilpool-e2e.db",
      },
    },
    {
      command: `node "${viteBin}" --host 127.0.0.1 --port 5173`,
      cwd: webDir,
      port: 5173,
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
