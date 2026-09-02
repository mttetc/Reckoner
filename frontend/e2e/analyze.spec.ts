import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const fixtures = path.resolve(__dirname, "../../backend/tests/fixtures/pob");
const modern = fs.readFileSync(path.join(fixtures, "slayer_lightning_strike_3_27.txt"), "utf8");
const legacy = fs.readFileSync(path.join(fixtures, "elementalist_bv_2019.txt"), "utf8");

test("analyses a modern PoB export and shows provenance on every value", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("code-input").fill(modern);
  await page.getByTestId("analyze").click();

  const result = page.getByTestId("result");
  await expect(result).toBeVisible();
  await expect(page.getByTestId("character")).toHaveText("Duelist · Slayer");
  await expect(page.getByTestId("main-skill")).toHaveText("Vaal Lightning Strike");
  await expect(page.getByTestId("patch")).toHaveText("patch 3.27");

  const dps = page.getByTestId("stat-dps.total");
  await expect(dps).toHaveAttribute("data-known", "true");
  await expect(dps.locator(".value")).toHaveText("18.6M");
  await expect(dps.locator(".prov")).toContainText("calculated · Path of Building (version not embedded) · patch 3.27");

  await expect(page.getByTestId("stat-life.max").locator(".value")).toHaveText("3,120");
  await expect(page.getByTestId("tree")).toContainText("129 allocated nodes");

  // Every known value carries a provenance line; every unknown one states a reason.
  const stats = page.locator("[data-testid^='stat-']");
  const n = await stats.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) {
    const s = stats.nth(i);
    const known = await s.getAttribute("data-known");
    if (known === "true") await expect(s.locator(".prov b")).toHaveText(/calculated|observed|estimated|claimed/);
    else await expect(s.locator(".prov")).toContainText("unknown —");
  }
});

test("legacy export: patch unknown, missing metrics shown as unknown, tree recovered", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("code-input").fill(legacy);
  await page.getByTestId("analyze").click();
  await expect(page.getByTestId("result")).toBeVisible();
  await expect(page.getByTestId("character")).toHaveText("Witch · Elementalist");
  await expect(page.getByTestId("patch")).toHaveText("patch unknown");
  const ehp = page.getByTestId("stat-ehp.total");
  await expect(ehp).toHaveAttribute("data-known", "false");
  await expect(ehp).toContainText("not present in this export");
  await expect(page.getByTestId("tree")).toContainText("131 allocated nodes");
});

test("invalid code shows the invalid-code state, not a guess", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("code-input").fill("find me a tanky lightning strike build under 20 divines");
  await page.getByTestId("analyze").click();
  const err = page.getByTestId("error");
  await expect(err).toBeVisible();
  await expect(err).toContainText("[invalid_build_code]");
  await expect(page.getByTestId("result")).toHaveCount(0);
});

test("submit is disabled on empty input and the page is keyboard reachable", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("analyze")).toBeDisabled();
  await page.keyboard.press("Tab");
  await expect(page.getByTestId("code-input")).toBeFocused();
});
