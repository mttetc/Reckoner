import { expect, test } from "@playwright/test";

test.describe("conversation (assistant-ui thread; scripted policy — no model in e2e)", () => {
  test("a build question shows traceable numbers, steps and evidence", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("ask-question").fill("Find me a Duelist Lightning Strike build");
    await page.getByTestId("ask-submit").click();
    await expect(page.getByTestId("ask-user")).toContainText("Duelist Lightning Strike");
    const result = page.getByTestId("ask-result").last();
    await expect(result).toBeVisible({ timeout: 20_000 });
    await expect(result.getByTestId("ask-answer")).toContainText("Slayer");
    await expect(result.getByTestId("ask-answer")).toContainText("18,619,973.8 DPS");
    await expect(result.getByTestId("ask-audit")).toHaveClass(/ok/);
    await expect(result.getByTestId("ask-audit")).toHaveText("✓ numbers verified");
    // Live steps stay in the answer once done, in plain words.
    await expect(result.getByTestId("step").first()).toContainText("Searched builds");
    await expect(result.getByTestId("step").first()).toHaveAttribute("data-state", "ok");
    // Follow-ups are offered, feedback and read-aloud are one click away.
    await expect(page.getByTestId("suggestions").getByRole("button").first()).toBeVisible();
    await result.hover();
    await expect(result.getByTestId("feedback-positive")).toBeVisible();
    await result.getByTestId("sources").locator("summary").click();
    await expect(result.getByTestId("sources-list")).toContainText("calculated by Path of Building");
    await expect(result.getByTestId("sources-list")).toContainText("DPS 18,619,974");
    // SPEC § 10: no technical jargon reaches the user.
    for (const word of ["tool call", "RAG", "embedding", "vector", "agent", "pipeline", "corpus", "poe ", "scripted", "offline", "model"]) {
      await expect(result).not.toContainText(word);
    }
  });

  test("a PoE 2 patch question only cites PoE 2 sources, and the thread keeps both turns", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("ask-question").fill("What changed for Lightning Strike in the latest PoE 2 patch?");
    await page.getByTestId("ask-submit").click();
    const result = page.getByTestId("ask-result").last();
    await expect(result).toBeVisible({ timeout: 20_000 });
    await expect(result.getByTestId("ask-answer")).toContainText("poe2 0.5");
    await expect(result.getByTestId("ask-answer")).not.toContainText("3.29");
    await result.getByTestId("sources").locator("summary").click();
    await expect(result.getByTestId("sources-list")).toContainText("stated by the source");
    await expect(result.getByTestId("sources-list")).toContainText("Path of Exile 2");

    await page.getByTestId("ask-question").fill("Find me a Templar build");
    await page.getByTestId("ask-submit").click();
    await expect(page.getByTestId("ask-result")).toHaveCount(2, { timeout: 20_000 });
    await expect(page.getByTestId("ask-result").last().getByTestId("ask-answer")).toContainText("Guardian");
  });

  test("an empty result is stated, not padded", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("ask-question").fill("Find me a Marauder Cyclone build");
    await page.getByTestId("ask-submit").click();
    const result = page.getByTestId("ask-result").last();
    await expect(result.getByTestId("ask-answer")).toContainText("No build matches", { timeout: 20_000 });
    await expect(result.getByTestId("ask-no-evidence")).toBeVisible();
  });

  test("example prompts are one click away", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Which Witch builds/ }).click();
    const result = page.getByTestId("ask-result").last();
    await expect(result).toBeVisible({ timeout: 20_000 });
    await expect(result.getByTestId("ask-answer")).toContainText("Witch");
  });
});
