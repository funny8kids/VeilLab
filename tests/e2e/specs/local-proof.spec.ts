import { expect, test } from "@playwright/test";

/**
 * Full local Groth16 flow: note v2 -> local Anvil deposit -> browser proof ->
 * local withdrawal.
 *
 * This spec is skipped by default. It requires the local stack:
 *   - Anvil 31337 with `DeployPoseidon.s.sol` deployed (maturity 0)
 *   - indexer with INDEXER_VERIFIER_KIND=groth16
 *   - API with VEILPOOL_MODE=local, LOCAL_AUTO_DEPOSIT=true,
 *     LOCAL_AUTO_WITHDRAW=true, LOCAL_VERIFIER_KIND=groth16
 *   - web dev server
 *   - `node circuits/scripts/export-web-artifacts.mjs` has copied the wasm/zkey
 *
 * Run:
 *   $env:VEILPOOL_LOCAL_E2E = "1"
 *   npm.cmd test -- local-proof.spec.ts
 */
test.describe("VeilPool local Groth16 withdrawal", () => {
  test.skip(
    !process.env.VEILPOOL_LOCAL_E2E,
    "Set VEILPOOL_LOCAL_E2E=1 and start the local Anvil/indexer/API/web stack.",
  );

  test("deposit, prove in the browser, and withdraw without leaking the note", async ({
    page,
    request,
  }) => {
    test.setTimeout(180_000);

    const health = await request.get("http://127.0.0.1:8000/api/v1/health");
    test.skip(!health.ok(), "Local API is not reachable on port 8000.");
    const healthBody = (await health.json()) as {
      mode?: string;
      verifier_kind?: string;
    };
    test.skip(
      healthBody.mode !== "local",
      "API is not in local mode.",
    );
    test.skip(
      healthBody.verifier_kind !== "groth16-poseidon",
      "API is not configured for the Groth16 verifier.",
    );

    const posts: string[] = [];
    page.on("request", (event) => {
      if (event.method() === "POST") {
        posts.push(`${event.url()}\n${event.postData() ?? ""}`);
      }
    });

    // 1. Deposit a v2 note through the local Anvil bridge.
    await page.goto("/deposit");
    await expect(page.getByRole("heading", { name: "Deposit" })).toBeVisible();
    await page.getByRole("button", { name: /generate secret note/i }).click();
    await expect(page.getByText("Your secret note")).toBeVisible();
    await expect(page.getByText(/^veilnote2/)).toBeVisible();
    await page.getByLabel(/I saved the note/i).check();

    const confirmDeposit = page.getByRole("button", {
      name: /confirm local deposit/i,
    });
    await expect(confirmDeposit).toBeEnabled();
    await confirmDeposit.click();
    await expect(
      page.getByText(/local deposit confirmed/i),
    ).toBeVisible({ timeout: 30_000 });

    // 2. Select the unspent note and make a local quote.
    await page.goto("/withdraw");
    await expect(page.getByRole("heading", { name: "Withdraw" })).toBeVisible();

    const choose = page.getByRole("button", { name: /choose from vault/i }).first();
    await choose.click();
    const noteOption = page.getByRole("button", { name: /ETH · 0.1|pool_eth_01/i }).first();
    await expect(noteOption).toBeVisible({ timeout: 15_000 });
    await noteOption.click();

    await page
      .getByLabel("Recipient address")
      .fill("0x4444444444444444444444444444444444444444");

    const quoteButton = page.getByRole("button", {
      name: /get quote & screen/i,
    });
    if (await quoteButton.isVisible().catch(() => false)) {
      await quoteButton.click();
    }
    await expect(
      page.getByText(/quote (ready|locked until)/i),
    ).toBeVisible({ timeout: 20_000 });

    // 3. Prove locally and submit the proof.
    const proveButton = page.getByRole("button", {
      name: /prove & withdraw locally/i,
    });
    await expect(proveButton).toBeEnabled({ timeout: 15_000 });
    await proveButton.click();

    await expect(
      page.getByText(/withdrawal confirmed on local anvil/i),
    ).toBeVisible({ timeout: 150_000 });

    // 4. Only public proof data may leave the browser.
    const joined = posts.join("\n");
    expect(joined).toContain("commitment");
    expect(joined).toContain("/local/deposits");
    expect(joined).toContain("/local/withdrawals");
    expect(joined).not.toContain("veilnote2");
    expect(joined).not.toContain("nullifierSecret");
    expect(joined).not.toContain("nullifier_secret");
    expect(joined).not.toMatch(/"secret"\s*:/);
  });
});
