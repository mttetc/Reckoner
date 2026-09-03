import { expect, test } from "@playwright/test";

test.describe("knowledge (seeded with synthetic PoE + PoE 2 patch notes sharing vocabulary)", () => {
  test("a PoE 2 question never surfaces a PoE passage, and vice versa", async ({ page }) => {
    await page.goto("/knowledge");
    await page.getByTestId("kn-game").selectOption("poe2");
    await page.getByTestId("kn-query").fill("Lightning Strike changes");
    await page.getByTestId("kn-search").click();
    const hits = page.getByTestId("kn-hit");
    await expect(hits.first()).toBeVisible();
    const n = await hits.count();
    expect(n).toBeGreaterThan(0);
    for (let i = 0; i < n; i++) await expect(hits.nth(i)).toHaveAttribute("data-game", "poe2");
    await expect(hits.first()).toContainText("patch 0.5");

    await page.getByTestId("kn-game").selectOption("poe");
    await page.getByTestId("kn-search").click();
    await expect(hits.first()).toContainText("patch 3.29");
    const m = await hits.count();
    for (let i = 0; i < m; i++) await expect(hits.nth(i)).toHaveAttribute("data-game", "poe");
  });

  test("every hit cites its source and version", async ({ page }) => {
    await page.goto("/knowledge");
    await page.getByTestId("kn-query").fill("Herald of Ash reservation");
    await page.getByTestId("kn-search").click();
    const first = page.getByTestId("kn-hit").first();
    await expect(first).toBeVisible();
    await expect(first.locator(".prov")).toContainText("3.29.0b");
    await expect(first.locator(".prov")).toContainText("similarity");
    await expect(first.locator(".excerpt")).not.toBeEmpty();
  });
});
