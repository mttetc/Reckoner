import { expect, test } from "@playwright/test";

test.describe("ask (scripted policy — no model in e2e)", () => {
  test("a build question shows traceable numbers, steps and evidence", async ({ page }) => {
    await page.goto("/ask");
    await page.getByTestId("ask-question").fill("Find me a Duelist Lightning Strike build");
    await page.getByTestId("ask-submit").click();
    await expect(page.getByTestId("ask-result")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("ask-answer")).toContainText("Slayer");
    await expect(page.getByTestId("ask-answer")).toContainText("18,619,973.8 DPS");
    await expect(page.getByTestId("ask-meta")).toContainText("scripted");
    await expect(page.getByTestId("ask-audit")).toHaveClass(/ok/);
    await expect(page.getByTestId("ask-audit")).toContainText("all traceable");
    await page.getByTestId("ask-steps").locator("summary").click();
    await expect(page.getByTestId("ask-steps")).toContainText("search_builds");
    await page.getByTestId("ask-evidence").locator("summary").click();
    await expect(page.getByTestId("ask-evidence")).toContainText("calculated");
    await expect(page.getByTestId("ask-evidence")).toContainText("Path of Building");
  });

  test("a PoE 2 patch question only cites PoE 2 sources", async ({ page }) => {
    await page.goto("/ask");
    await page.getByTestId("ask-question").fill("What changed for Lightning Strike in the latest PoE 2 patch?");
    await page.getByTestId("ask-submit").click();
    await expect(page.getByTestId("ask-result")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("ask-answer")).toContainText("poe2 0.5");
    await expect(page.getByTestId("ask-answer")).not.toContainText("3.29");
    await page.getByTestId("ask-evidence").locator("summary").click();
    await expect(page.getByTestId("ask-evidence")).toContainText("claimed");
  });

  test("an empty result is stated, not padded", async ({ page }) => {
    await page.goto("/ask");
    await page.getByTestId("ask-question").fill("Find me a Marauder Cyclone build");
    await page.getByTestId("ask-submit").click();
    await expect(page.getByTestId("ask-answer")).toContainText("0 build(s)", { timeout: 20_000 });
  });
});
