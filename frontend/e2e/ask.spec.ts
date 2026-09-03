import { expect, test } from "@playwright/test";

test.describe("ask (chat on assistant-ui; scripted policy — no model in e2e)", () => {
  test("a build question shows traceable numbers, steps and evidence", async ({ page }) => {
    await page.goto("/ask");
    await page.getByTestId("ask-question").fill("Find me a Duelist Lightning Strike build");
    await page.getByTestId("ask-submit").click();
    await expect(page.getByTestId("ask-user")).toContainText("Duelist Lightning Strike");
    const result = page.getByTestId("ask-result").last();
    await expect(result).toBeVisible({ timeout: 20_000 });
    await expect(result.getByTestId("ask-answer")).toContainText("Slayer");
    await expect(result.getByTestId("ask-answer")).toContainText("18,619,973.8 DPS");
    await expect(result.getByTestId("ask-meta")).toContainText("offline answer");
    await expect(result.getByTestId("ask-audit")).toHaveClass(/ok/);
    await expect(result.getByTestId("ask-audit")).toContainText("every number here comes from a calculation or a source");
    await result.getByTestId("ask-steps").locator("summary").click();
    await expect(result.getByTestId("ask-steps")).toContainText("Searched builds");
    await result.getByTestId("ask-evidence").locator("summary").click();
    await expect(result.getByTestId("ask-evidence")).toContainText("calculated");
    await expect(result.getByTestId("ask-evidence")).toContainText("Path of Building");
    // SPEC § 10: no technical jargon reaches the user.
    for (const word of ["tool call", "RAG", "embedding", "vector", "agent", "pipeline", "corpus", "poe ", "scripted"]) {
      await expect(result).not.toContainText(word);
    }
  });

  test("a PoE 2 patch question only cites PoE 2 sources, and the thread keeps both turns", async ({ page }) => {
    await page.goto("/ask");
    await page.getByTestId("ask-question").fill("What changed for Lightning Strike in the latest PoE 2 patch?");
    await page.getByTestId("ask-submit").click();
    const result = page.getByTestId("ask-result").last();
    await expect(result).toBeVisible({ timeout: 20_000 });
    await expect(result.getByTestId("ask-answer")).toContainText("poe2 0.5");
    await expect(result.getByTestId("ask-answer")).not.toContainText("3.29");
    await result.getByTestId("ask-evidence").locator("summary").click();
    await expect(result.getByTestId("ask-evidence")).toContainText("stated by the source");
    await expect(result.getByTestId("ask-evidence")).toContainText("Path of Exile 2");

    await page.getByTestId("ask-question").fill("Find me a Templar build");
    await page.getByTestId("ask-submit").click();
    await expect(page.getByTestId("ask-result")).toHaveCount(2, { timeout: 20_000 });
    await expect(page.getByTestId("ask-result").last().getByTestId("ask-answer")).toContainText("Guardian");
  });

  test("an empty result is stated, not padded", async ({ page }) => {
    await page.goto("/ask");
    await page.getByTestId("ask-question").fill("Find me a Marauder Cyclone build");
    await page.getByTestId("ask-submit").click();
    const result = page.getByTestId("ask-result").last();
    await expect(result.getByTestId("ask-answer")).toContainText("No build matches", { timeout: 20_000 });
    await expect(result.getByTestId("ask-no-evidence")).toBeVisible();
  });

  test("example prompts are one click away", async ({ page }) => {
    await page.goto("/ask");
    await page.getByRole("button", { name: /Which Witch builds/ }).click();
    const result = page.getByTestId("ask-result").last();
    await expect(result).toBeVisible({ timeout: 20_000 });
    await expect(result.getByTestId("ask-answer")).toContainText("Witch");
  });
});
