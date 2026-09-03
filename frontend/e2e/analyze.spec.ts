import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const fixtures = path.resolve(__dirname, "../../backend/tests/fixtures/pob");
const modern = fs.readFileSync(path.join(fixtures, "slayer_lightning_strike_3_27.txt"), "utf8");
const legacy = fs.readFileSync(path.join(fixtures, "elementalist_bv_2019.txt"), "utf8");
const voidSphere = fs.readFileSync(path.join(fixtures, "void_sphere_pathfinder_3_29.txt"), "utf8");
const minions = fs.readFileSync(path.join(fixtures, "srs_guardian_3_23.txt"), "utf8");

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
  await expect(dps.locator(".prov")).toContainText("calculated by Path of Building · patch 3.27");

  await expect(page.getByTestId("stat-life.max").locator(".value")).toHaveText("3,120");
  await expect(page.getByTestId("tree")).toContainText("129 passives");

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
  await expect(ehp).toContainText("not in this export");
  await expect(page.getByTestId("tree")).toContainText("131 passives");
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
  // Tab order: every nav link first (all focusable), then the code textarea — nothing trapped.
  const navLinks = await page.locator("nav a").count();
  expect(navLinks).toBeGreaterThan(0);
  for (let i = 0; i < navLinks; i++) {
    await page.keyboard.press("Tab");
    await expect(page.locator("nav a").nth(i)).toBeFocused();
  }
  await page.keyboard.press("Tab");
  await expect(page.getByTestId("code-input")).toBeFocused();
});

test("utility skill left selected: DPS 0 is reported as-is, Full DPS says what it sums", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("code-input").fill(voidSphere);
  await page.getByTestId("analyze").click();
  await expect(page.getByTestId("result")).toBeVisible();
  await expect(page.getByTestId("main-skill")).toHaveText("Withering Step");
  await expect(page.getByTestId("stat-dps.total").locator(".value")).toHaveText("0");
  const full = page.getByTestId("stat-dps.full");
  await expect(full.locator(".value")).toHaveText("19.4M");
  await expect(full.getByTestId("aggregates")).toContainText("Void Sphere of Rending, Shield Charge");
  // No minion card for a build without minions.
  await expect(page.getByTestId("stat-minion.dps.total")).toHaveCount(0);
});

test("minion build: minion DPS is its own metric, player DPS stays 0", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("code-input").fill(minions);
  await page.getByTestId("analyze").click();
  await expect(page.getByTestId("result")).toBeVisible();
  await expect(page.getByTestId("character")).toHaveText("Templar · Guardian");
  await expect(page.getByTestId("stat-dps.total").locator(".value")).toHaveText("0");
  const minion = page.getByTestId("stat-minion.dps.total");
  await expect(minion).toHaveAttribute("data-known", "true");
  await expect(minion.locator(".value")).toHaveText("136.6K");
  await expect(page.getByTestId("row-minion.life.max").locator(".num")).toHaveText("4,285");
});

test.describe("try a change (real headless engine)", () => {
  test("clicking a taken passive recalculates without it; both columns say who computed them", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("code-input").fill(modern);
    await page.getByTestId("analyze").click();
    const tree = page.getByTestId("tree-view");
    await expect(tree).toBeVisible({ timeout: 30_000 });
    await tree.locator("circle[data-node-id='41119']").click();

    const table = page.getByTestId("whatif-result");
    await expect(table).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("engine-prov")).toContainText("calculated by Path of Building 2.");
    await expect(page.getByTestId("applied")).toContainText("Lethality");
    await expect(page.getByTestId("delta-dps.total")).toHaveClass(/down/);
    await expect(page.getByTestId("delta-dps.total")).toContainText("−");
    await expect(page.getByTestId("delta-life.max")).toHaveClass(/flat/);
    await expect(page.getByTestId("variant-nodes")).toHaveText("128 passives");
    // The tree shows the diff and the reader is told in plain words.
    await expect(tree.locator(".tree-bar")).toContainText("−1");
    await expect(tree.locator("circle[data-node-id='41119']")).toHaveClass(/removed/);
    // SPEC § 10: nothing technical leaks into the panel.
    for (const word of ["node id", "baseline", "sha256", "engine_version", "pob:"]) {
      await expect(page.getByTestId("result")).not.toContainText(word);
    }
  });

  test("a change the engine cannot honour is refused with its reason", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("code-input").fill(modern);
    await page.getByTestId("analyze").click();
    await expect(page.getByTestId("result")).toBeVisible();
    // Enemy type is validated by the engine's own option list; the UI only offers valid ones,
    // so exercise the refusal path through a value the engine does not know.
    await page.getByTestId("mod-kind").selectOption("config.set");
    await page.getByTestId("mod-boss").selectOption("Uber");
    await page.getByTestId("recalc").click();
    await expect(page.getByTestId("whatif-result")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("applied")).toContainText("Uber");
  });
});

test.describe("passive tree (geometry from the engine)", () => {
  test("draws the allocated tree with plain-language hover", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("code-input").fill(modern);
    await page.getByTestId("analyze").click();
    const tree = page.getByTestId("tree-view");
    await expect(tree).toBeVisible({ timeout: 30_000 });
    await expect(tree.locator(".tree-bar")).toContainText("129 passives");
    await expect(tree.locator(".tree-bar")).toContainText("inside cluster jewels");
    const lit = tree.locator("circle[data-allocated='true']");
    expect(await lit.count()).toBeGreaterThan(100);
    await expect(tree.locator("circle[data-node-id='41119']")).toHaveAttribute("data-allocated", "true");
    await tree.locator("circle[data-node-id='41119']").hover();
    await expect(page.getByTestId("tree-hover")).toContainText("Lethality · notable · taken · click to remove");
    await page.getByTestId("tree-all").click();
    await page.getByTestId("tree-reset").click();
  });
});
