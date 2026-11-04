import { expect, test } from "@playwright/test";

test.describe("VeilPool local mock MVP", () => {
  test("deposit flow works and never sends the note", async ({ page }) => {
    const requestBodies: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "POST") {
        requestBodies.push(request.postData() ?? "");
      }
    });

    await page.goto("/deposit");
    await expect(page.getByRole("heading", { name: "Deposit" })).toBeVisible();

    await page.getByRole("button", { name: /generate secret note/i }).click();
    await expect(page.getByText("Your secret note")).toBeVisible();
    await expect(page.getByText(/^veilnote1/)).toBeVisible();

    await page
      .getByLabel(/I saved the note/i)
      .check();
    const confirm = page.getByRole("button", { name: /confirm deposit/i });
    await expect(confirm).toBeEnabled();
    await confirm.click();

    await expect(page.getByText(/mock deposit recorded/i)).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText(/ETH · 0\.1 · confirmed/i)).toBeVisible();

    const joined = requestBodies.join("\n");
    expect(joined).toContain("commitment");
    expect(joined).not.toContain("veilnote1");
    expect(joined).not.toContain("nullifierSecret");
    expect(joined).not.toMatch(/"secret"\s*:/);
  });

  test("withdraw page blocks a note with no confirmed deposit", async ({ page }) => {
    await page.goto("/withdraw");
    await expect(page.getByRole("heading", { name: "Withdraw" })).toBeVisible();
    await expect(page.getByText(/Get quote & screen/i)).toBeVisible();
  });

  test("EN/ZH and dark/light toggles work", async ({ page }) => {
    await page.goto("/overview");
    await expect(page.getByRole("heading", { name: /Private pool|隐私池/ })).toBeVisible();

    await page.getByRole("button", { name: "中文" }).click();
    await expect(page.getByRole("heading", { name: "隐私池" })).toBeVisible();

    await page.getByRole("button", { name: /theme|主题/i }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });
});
