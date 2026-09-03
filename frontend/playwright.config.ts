import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const backendDir = path.resolve(__dirname, "../backend");
const python = path.join(backendDir, ".venv/bin/python");

export default defineConfig({
  testDir: "./e2e",
  // CI runners compile the dev bundle on first load and share one headless engine: give them room.
  timeout: process.env.CI ? 90_000 : 30_000,
  expect: { timeout: process.env.CI ? 20_000 : 5_000 },
  retries: process.env.CI ? 1 : 0,
  fullyParallel: true,
  // Engine-backed tests share one headless PoB process and draw ~2,900 SVG nodes each; keep CI calm.
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: [
    {
      // Seed the corpus with the fixtures so the /builds pages have something honest to show.
      command: `${python} scripts/db_init.py --reset && ${python} scripts/ingest_files.py tests/fixtures/pob/*.txt && ${python} scripts/knowledge_seed.py && ${python} -m uvicorn app.main:app --port 8000`,
      cwd: backendDir,
      env: {
        ...process.env,
        // A dedicated database: e2e assertions count rows, the dev corpus must not leak in.
        RECKONER_DATABASE_URL: process.env.RECKONER_E2E_DATABASE_URL ?? "postgresql+asyncpg://reckoner:reckoner@localhost:5432/reckoner_e2e",
        RECKONER_EMBEDDER: "hash", // deterministic, no model download; e2e asserts isolation, not ranking
        RECKONER_LLM: "scripted", // no model in e2e: the loop, trace, evidence and audit are what we test
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
