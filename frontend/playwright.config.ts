import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const backendDir = path.resolve(__dirname, "../backend");
const python = path.join(backendDir, ".venv/bin/python");

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: true,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: [
    {
      // Seed the corpus with the fixtures so the /builds pages have something honest to show.
      command: `${python} scripts/db_init.py --reset && ${python} scripts/ingest_files.py tests/fixtures/pob/*.txt && ${python} -m uvicorn app.main:app --port 8000`,
      cwd: backendDir,
      env: {
        ...process.env,
        // A dedicated database: e2e assertions count rows, the dev corpus must not leak in.
        RECKONER_DATABASE_URL: process.env.RECKONER_E2E_DATABASE_URL ?? "postgresql+asyncpg://reckoner:reckoner@localhost:5432/reckoner_e2e",
      },
      url: "http://localhost:8000/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "pnpm dev --port 3000",
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { NEXT_PUBLIC_API_URL: "http://localhost:8000" },
    },
  ],
});
