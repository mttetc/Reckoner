import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const fixtures = path.resolve(__dirname, "../../backend/tests/fixtures/pob");
const modern = fs.readFileSync(path.join(fixtures, "slayer_lightning_strike_3_27.txt"), "utf8");
const legacy = fs.readFileSync(path.join(fixtures, "elementalist_bv_2019.txt"), "utf8");
const voidSphere = fs.readFileSync(path.join(fixtures, "void_sphere_pathfinder_3_29.txt"), "utf8");
const minions = fs.readFileSync(path.join(fixtures, "srs_guardian_3_23.txt"), "utf8");
const wowRetail = fs.readFileSync(path.resolve(__dirname, "../../backend/tests/fixtures/wow/simc_warrior_fury_mid2.simc"), "utf8");
const wowClassic = fs.readFileSync(path.resolve(__dirname, "../../backend/tests/fixtures/wow/fury_warrior_classic.json"), "utf8");

async function paste(page: import("@playwright/test").Page, code: string, question = "") {
  await page.goto("/");
  await page.getByTestId("ask-question").fill(`${question} ${code}`.trim());
  await page.getByTestId("ask-submit").click();
  const answer = page.getByTestId("ask-result").last();
  await expect(answer.getByTestId("build-card")).toBeVisible({ timeout: 30_000 });
  return answer;
}

test("pasting a build code in the conversation shows the build with provenance on every value", async ({ page }) => {
  const result = await paste(page, modern, "How strong is this?");
  // The blob never shows: the user bubble says what was attached.
  await expect(page.getByTestId("ask-user-code")).toHaveText("Path of Building code attached");
  await expect(page.getByTestId("ask-user-text")).toContainText("How strong is this?");

  await expect(result.getByTestId("character")).toHaveText("Duelist · Slayer");
  await expect(result.getByTestId("main-skill")).toHaveText("Vaal Lightning Strike");
  await expect(result.getByTestId("patch")).toHaveText("patch 3.27");
  const dps = result.getByTestId("stat-dps.total");
  await expect(dps).toHaveAttribute("data-known", "true");
  await expect(dps.locator(".value")).toHaveText("18.6M");
  await expect(dps.locator(".prov")).toContainText("calculated by Path of Building · patch 3.27");
  await expect(result.getByTestId("stat-life.max").locator(".value")).toHaveText("3,120");
  await expect(result.getByTestId("tree")).toContainText("129 passives");

  const stats = result.locator("[data-testid^='stat-']");
  const n = await stats.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) {
    const s = stats.nth(i);
    const known = await s.getAttribute("data-known");
    if (known === "true") await expect(s.locator(".prov b")).toHaveText(/calculated|observed|estimated|stated/);
    else await expect(s.locator(".prov")).toContainText("unknown —");
  }
  // One honesty line under the answer; sources fold out on demand.
  await expect(result.getByTestId("ask-audit")).toHaveClass(/ok/);
});

test("legacy export: patch unknown, missing values shown as unknown, tree recovered", async ({ page }) => {
  const result = await paste(page, legacy);
  await expect(result.getByTestId("character")).toHaveText("Witch · Elementalist");
  await expect(result.getByTestId("patch")).toHaveText("patch unknown");
  const ehp = result.getByTestId("stat-ehp.total");
  await expect(ehp).toHaveAttribute("data-known", "false");
  await expect(ehp.locator(".prov")).toContainText("not in this export");
  await expect(result.getByTestId("tree")).toContainText("131 passives");
});

test("utility skill left selected: DPS 0 is reported as-is, Full DPS says what it sums", async ({ page }) => {
  const result = await paste(page, voidSphere);
  await expect(result.getByTestId("main-skill")).toHaveText("Withering Step");
  await expect(result.getByTestId("stat-dps.total").locator(".value")).toHaveText("0");
  const full = result.getByTestId("stat-dps.full");
  await expect(full.locator(".value")).toHaveText("19.4M");
  await expect(full.getByTestId("aggregates")).toContainText("Void Sphere of Rending, Shield Charge");
  await expect(result.getByTestId("stat-minion.dps.total")).toHaveCount(0);
});

test("minion build: minion DPS is its own number, player DPS stays 0", async ({ page }) => {
  const result = await paste(page, minions);
  await expect(result.getByTestId("character")).toHaveText("Templar · Guardian");
  await expect(result.getByTestId("stat-dps.total").locator(".value")).toHaveText("0");
  const minion = result.getByTestId("stat-minion.dps.total");
  await expect(minion).toHaveAttribute("data-known", "true");
  await expect(minion.locator(".value")).toHaveText("136.6K");
  await expect(result.getByTestId("row-minion.life.max").locator(".num")).toHaveText("4,285");
});

test("an invalid code is refused, not guessed", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("ask-question").fill("eJyrVgooKUpNzVBQAgAAAAABBBAAAA" + "x".repeat(220));
  await page.getByTestId("ask-submit").click();
  const result = page.getByTestId("ask-result").last();
  await expect(result).toBeVisible({ timeout: 30_000 });
  await expect(result.getByTestId("build-card")).toHaveCount(0);
  await expect(result).toContainText(/could not|refused|not a build code|invalid|does not look like/i);
});

test("one page, one conversation: the composer has focus and nothing technical is on screen", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("ask-question")).toBeFocused();
  // The passive tree sits behind the conversation, decorative and out of the way.
  const backdrop = page.getByTestId("tree-backdrop");
  await expect(backdrop).toBeAttached({ timeout: 30_000 });
  await expect(backdrop).toHaveAttribute("aria-hidden", "true");
  expect(await backdrop.locator("circle").count()).toBeGreaterThan(1000);
  await expect(page.locator("nav")).toHaveCount(0);
  for (const word of ["corpus", "engine", "pipeline", "vector", "embedding", "index"]) {
    await expect(page.locator("body")).not.toContainText(word);
  }
});

test.describe("try a change (real headless engine)", () => {
  // Geometry for ~2,900 passives plus a real recalculation: slow on CI runners.
  test.describe.configure({ timeout: 120_000 });

  test("clicking a taken passive recalculates without it; both columns say who computed them", async ({ page }) => {
    const result = await paste(page, modern);
    const tree = result.getByTestId("tree-view");
    await expect(tree).toBeVisible({ timeout: 30_000 });
    await expect(tree.locator(".tree-bar")).toContainText("129 passives");
    await expect(tree.locator(".tree-bar")).toContainText("inside cluster jewels");
    const lethality = tree.locator("circle[data-node-id='41119']");
    await lethality.scrollIntoViewIfNeeded();
    await lethality.hover({ force: true });
    await expect(result.getByTestId("tree-hover")).toContainText("Lethality · notable · taken · click to remove");
    // The thread keeps auto-scrolling while the card grows; skip the "stable" wait, the target is right.
    await lethality.click({ force: true });

    await expect(result.getByTestId("whatif-result")).toBeVisible({ timeout: 30_000 });
    await expect(result.getByTestId("engine-prov")).toContainText("calculated by Path of Building 2.");
    await expect(result.getByTestId("applied")).toContainText("Lethality");
    await expect(result.getByTestId("delta-dps.total")).toHaveClass(/down/);
    await expect(result.getByTestId("delta-dps.total")).toContainText("−");
    await expect(result.getByTestId("delta-life.max")).toHaveClass(/flat/);
    await expect(result.getByTestId("variant-nodes")).toHaveText("128 passives");
    await expect(tree.locator(".tree-bar")).toContainText("−1");
    await expect(tree.locator("circle[data-node-id='41119']")).toHaveClass(/removed/);
    for (const word of ["node id", "baseline", "sha256", "engine_version", "pob:", "corpus"]) {
      await expect(result).not.toContainText(word);
    }
  });

  test("the enemy type can be changed and is recalculated", async ({ page }) => {
    const result = await paste(page, modern);
    await result.getByTestId("mod-kind").selectOption("config.set");
    await result.getByTestId("mod-boss").selectOption("Uber");
    await result.getByTestId("recalc").click();
    await expect(result.getByTestId("whatif-result")).toBeVisible({ timeout: 30_000 });
    await expect(result.getByTestId("applied")).toContainText("Uber");
  });
});

test.describe("other games through the same conversation", () => {
  // Real SimulationCraft: the pasted profile is simulated as-is, its talents decoded by the engine.
  test.describe.configure({ timeout: 120_000 });

  test("a SimulationCraft profile is simulated by SimulationCraft itself, talents drawn from its data", async ({ page }) => {
    const result = await paste(page, wowRetail, "How is this warrior?");
    await expect(page.getByTestId("ask-user-code")).toHaveText("SimulationCraft profile attached");
    await expect(page.getByTestId("ask-user-text")).toContainText("How is this warrior?");
    await expect(result.getByTestId("character")).toHaveText("Warrior · Fury");
    await expect(result.getByTestId("main-skill")).toHaveCount(0);
    const dps = result.getByTestId("stat-dps.total");
    await expect(dps).toHaveAttribute("data-known", "true");
    await expect(dps.locator(".prov")).toContainText("calculated by SimulationCraft");
    await expect(result.getByTestId("patch")).toContainText("patch 12.");
    await expect(result.getByTestId("tree")).toContainText("talents · Warrior · Fury · Slayer");
    const grid = result.getByTestId("talent-grid");
    await expect(grid.getByTestId("talent-tree-spec")).toBeVisible({ timeout: 30_000 });
    await expect(grid).toHaveAttribute("data-source", "engine-grid", { timeout: 30_000 });
    const taken = await grid.locator("circle[data-taken='true']").count();
    const all = await grid.locator("circle").count();
    expect(taken).toBeGreaterThan(60); // 73 talents in this build, as the engine decoded them
    expect(all).toBeGreaterThan(taken + 10); // the grid also shows what the build did not take
    await expect(grid.getByTestId("talent-tree-hero")).toHaveCount(1);
    await expect(result.getByTestId("tree-view")).toHaveCount(0);
  });

  test("a World of Warcraft change is simulated again by the same engine", async ({ page }) => {
    const result = await paste(page, wowRetail);
    await result.getByTestId("mod-kind").selectOption("wow.fight");
    await result.getByTestId("mod-fight").selectOption("DungeonSlice");
    await result.getByTestId("recalc").click();
    await expect(result.getByTestId("whatif-result")).toBeVisible({ timeout: 60_000 });
    await expect(result.getByTestId("engine-prov")).toContainText("calculated by SimulationCraft");
    await expect(result.getByTestId("applied")).toContainText("fight_style → DungeonSlice");
    await expect(result.getByTestId("variant-nodes")).toContainText("talents");
  });

  test("a WoWSims export is read as Classic, kept apart from Retail", async ({ page }) => {
    const result = await paste(page, wowClassic);
    await expect(page.getByTestId("ask-user-code")).toHaveText("WoWSims export attached");
    await expect(result.getByTestId("character")).toHaveText("Warrior · Fury");
    await expect(result.getByTestId("stat-dps.total").locator(".prov")).toContainText("WoWSims");
  });
});
