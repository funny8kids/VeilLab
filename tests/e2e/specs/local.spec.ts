import { expect, test } from "@playwright/test";

/**
 * Local Anvil smoke test.
 *
 * This spec is skipped by default. Start the local stack first:
 *
 *   anvil --host 127.0.0.1 --port 8545 --chain-id 31337
 *   # deploy + start indexer (infrastructure/anvil-deploy.ps1)
 *   # start the API with VEILPOOL_MODE=local and VEILPOOL_LOCAL_AUTO_DEPOSIT=true
 *   # start the web dev server with VITE_API_BASE_URL=http://127.0.0.1:8000
 *
 * Then:
 *
 *   $env:VEILPOOL_LOCAL_E2E = "1"
 *   npm.cmd test -- local.spec.ts
 *
 * The spec does not deploy contracts and does not sign anything itself. It asserts
 * the browser flow through the API's local Anvil deposit bridge and the no-note
 * network guard.
 */
test.describe("VeilPool local Anvil mode", () => {
  test.skip(
    !process.env.VEILPOOL_LOCAL_E2E,
    "Set VEILPOOL_LOCAL_E2E=1 and start the local Anvil/API stack.",
  );

  test("deposit through the local Anvil bridge without sending the note", async ({
    page,
    request,
  }) => {
    const health = await request.get("http://127.0.0.1:8000/api/v1/health");
    test.skip(!health.ok(), "Local API is not reachable on port 8000.");
    const healthBody = (await health.json()) as { mode?: string };
    test.skip(
      healthBody.mode !== "local",
      "API is not in local mode. Start it with VEILPOOL_MODE=local.",
    );

    const requestBodies: string[] = [];
    page.on("request", (event) => {
      if (event.method() === "POST") {
        requestBodies.push(`${event.url()}\n${event.postData() ?? ""}`);
      }
    });

    await page.goto("/deposit");
    await expect(page.getByRole("heading", { name: "Deposit" })).toBeVisible();

    await page.getByRole("button", { name: /generate secret note/i }).click();
    await expect(page.getByText("Your secret note")).toBeVisible();
    await page.getByLabel(/I saved the note/i).check();

    const confirm = page.getByRole("button", {
      name: /confirm (local )?deposit/i,
    });
    await expect(confirm).toBeEnabled();
    await confirm.click();

    await expect(
      page.getByText(/local deposit confirmed|local deposit submitted/i),
    ).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/ANVIL LOCAL|Local deposit/i).first()).toBeVisible();

    const joined = requestBodies.join("\n");
    expect(joined).toContain("commitment");
    expect(joined).not.toContain("veilnote1");
    expect(joined).not.toContain("nullifierSecret");
    expect(joined).not.toMatch(/"secret"\s*:/);

    // The local deposit bridge must be the endpoint used in local mode.
    expect(joined).toContain("/local/deposits");
  });
});
