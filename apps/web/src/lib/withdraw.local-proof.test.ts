import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { buildLocalWithdrawalRequest } from "./prover";
import { withdrawalIsBlocked, withdrawalSubmitMode } from "./withdraw";

const PROOF = `0x${"ab".repeat(256)}`;
const ROOT = `0x${"11".repeat(32)}`;
const NULLIFIER = `0x${"22".repeat(32)}`;
const RECIPIENT = "0x3333333333333333333333333333333333333333";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("local quote proof mode", () => {
  it("selects local proof mode only when submission_available is true", () => {
    expect(withdrawalSubmitMode("local", "live", false, true)).toBe("local");
    expect(withdrawalIsBlocked("local", "live", false, true)).toBe(false);

    expect(withdrawalSubmitMode("local", "live", false, false)).toBe(
      "local-disabled",
    );
    expect(withdrawalIsBlocked("local", "live", false, false)).toBe(true);
  });

  it("never selects mock or demo mode for a local quote", () => {
    expect(withdrawalSubmitMode("local", "live", true, true)).toBe("local");
    expect(withdrawalSubmitMode("local", "partial", true, true)).toBe("local");
    expect(withdrawalSubmitMode("local", "demo", true, true)).toBe("local");
  });
});

describe("local withdrawal request whitelist", () => {
  it("emits only the six public fields and drops note material", () => {
    const untrusted = {
      quoteId: "quote_local_001",
      proof: PROOF,
      root: ROOT,
      nullifier: NULLIFIER,
      recipient: RECIPIENT,
      feeWei: "240000000000000",
      note: "veilnote2secret",
      secret: "0xdeadbeef",
      nullifier_secret: "0xfeedface",
    } as unknown as Parameters<typeof buildLocalWithdrawalRequest>[0];

    const request = buildLocalWithdrawalRequest(untrusted);

    expect(request).toEqual({
      quote_id: "quote_local_001",
      proof: PROOF,
      root: ROOT,
      nullifier: NULLIFIER,
      recipient: RECIPIENT,
      relayer_fee_wei: "240000000000000",
    });
    expect(Object.keys(request)).toEqual([
      "quote_id",
      "proof",
      "root",
      "nullifier",
      "recipient",
      "relayer_fee_wei",
    ]);
    const serialized = JSON.stringify(request);
    expect(serialized).not.toContain("veilnote2");
    expect(serialized).not.toContain("secret");
    expect(serialized).not.toContain("nullifier_secret");
  });

  it("posts proof and public signals only to /local/withdrawals", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        jsonResponse({
          withdrawal_id: "wdr_local_001",
          status: "confirmed",
          tx_hash: `0x${"44".repeat(32)}`,
          block_number: 12,
          nullifier: NULLIFIER,
          recipient: RECIPIENT,
          fee_wei: "240000000000000",
          local_chain: "ANVIL",
          verifier_kind: "groth16-poseidon",
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = buildLocalWithdrawalRequest({
      quoteId: "quote_local_001",
      proof: PROOF,
      root: ROOT,
      nullifier: NULLIFIER,
      recipient: RECIPIENT,
      feeWei: "240000000000000",
    });
    const response = await api.submitLocalWithdrawal(request);

    expect(response.status).toBe("confirmed");
    expect(response.tx_hash).toBe(`0x${"44".repeat(32)}`);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/v1/local/withdrawals");
    const bodyText = String(init?.body);
    const body = JSON.parse(bodyText) as Record<string, unknown>;
    expect(body).toEqual(request);
    expect(Object.keys(body)).toHaveLength(6);
    expect(bodyText).not.toContain("veilnote2");
    expect(bodyText).not.toContain("secret");
    expect(bodyText).not.toContain("nullifier_secret");
    expect(body).not.toHaveProperty("note");
    expect(body).not.toHaveProperty("witness");
  });
});
