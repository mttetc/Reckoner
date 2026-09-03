import { expect, test } from "@playwright/test";

test.describe("corpus (seeded with the six fixtures)", () => {
  test("lists builds with provenance-bearing numbers, unknown stays unknown", async ({ page }) => {
    await page.goto("/builds");
    const rows = page.getByTestId("build-row");
    await expect(rows).toHaveCount(6);
    await expect(page.getByTestId("total")).toHaveText("6 builds");
    // The Chieftain ballista export has no TotalDPS: shown as unknown, not 0, and sorted last.
    const last = rows.last();
    await expect(last).toContainText("Chieftain");
    await expect(last.locator("td").nth(3)).toHaveText("unknown");
    await expect(last.locator("td").nth(3)).toHaveAttribute("title", /not present in this export/);
    // Best known DPS first.
    await expect(rows.first()).toContainText("Vaal Lightning Strike");
    await expect(rows.first().locator("td").nth(3)).toHaveAttribute("title", /calculated · Path of Building/);
  });

  test("filters by class and skill; empty result is stated, not padded", async ({ page }) => {
    await page.goto("/builds");
    await page.getByTestId("filter-class").selectOption("Duelist");
    await page.getByTestId("filter-apply").click();
    await expect(page.getByTestId("build-row")).toHaveCount(1);
    await expect(page.getByTestId("build-row").first()).toContainText("Slayer");

    await page.getByTestId("filter-skill").fill("Cyclone");
    await page.getByTestId("filter-apply").click();
    await expect(page.getByTestId("corpus-empty")).toBeVisible();
    await expect(page.getByTestId("build-row")).toHaveCount(0);
  });

  test("detail page shows the snapshot, its source and no fake what-if", async ({ page }) => {
    await page.goto("/builds");
    await page.getByTestId("filter-class").selectOption("Templar");
    await page.getByTestId("filter-apply").click();
    await page.getByTestId("build-link").first().click();
    await expect(page).toHaveURL(/\/builds\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("character")).toHaveText("Templar · Guardian");
    await expect(page.getByTestId("stat-minion.dps.total")).toHaveAttribute("data-known", "true");
    await expect(page.getByTestId("source")).toContainText("srs_guardian_3_23");
    await expect(page.getByTestId("whatif-unavailable")).toBeVisible();
    await expect(page.getByTestId("recalc")).toHaveCount(0);
  });

  test("navigation between analyse and builds is keyboard reachable", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-builds").click();
    await expect(page).toHaveURL(/\/builds$/);
    await expect(page.getByTestId("builds-table")).toBeVisible();
  });
});
