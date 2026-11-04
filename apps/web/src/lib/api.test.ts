import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { buildMockDepositRequest } from "./deposit";
import { generateNote } from "./note";
import { DEMO_POOLS } from "./demoData";
import type { LocalWithdrawalRequest } from "../types";

const note = await generateNote(DEMO_POOLS[0]);
const payload = buildMockDepositRequest({
  intentId: "dep_test_001",
  commitment: note.payload.commitment,
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("mock deposit API call", () => {
  it("posts intent_id and commitment and no note material", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(
          JSON.stringify({
            tx_hash: `0x${"ab".repeat(32)}`,
            status: "confirmed",
            leaf_index: 7,
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.recordMockDeposit(payload, "idem-test-key");
    expect(result.status).toBe("confirmed");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/v1/mock/deposits");
    const bodyText = String(init?.body);
    const body = JSON.parse(bodyText) as Record<string, unknown>;
    expect(body).toEqual({
      intent_id: "dep_test_001",
      commitment: note.payload.commitment,
    });
    expect(bodyText).not.toContain("veilnote1");
    expect(bodyText).not.toContain(note.payload.secret);
    expect(bodyText).not.toContain(note.payload.nullifierSecret);
    expect(body).not.toHaveProperty("note");
    expect(body).not.toHaveProperty("secret");
    expect(body).not.toHaveProperty("nullifierSecret");
    expect(
      new Headers(init?.headers).get("Idempotency-Key"),
    ).toBe("idem-test-key");
  });
});

describe("proof path API call", () => {
  it("fetches the public Merkle path for a pool and commitment", async () => {
    const commitment = `0x${"12".repeat(32)}`;
    const pathBody = {
      chain_id: 31337,
      pool_id: `0x${"70".repeat(32)}`,
      pool_key: "pool_eth_01",
      commitment,
      leaf_index: 2,
      leaf_count: 3,
      tree_depth: 20,
      root: `0x${"34".repeat(32)}`,
      path_elements: new Array(20).fill(`0x${"00".repeat(32)}`),
      path_indices: new Array(20).fill(0),
    };
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify(pathBody), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.proofPath("pool_eth_01", commitment);

    expect(result.root).toBe(pathBody.root);
    expect(result.pool_key).toBe("pool_eth_01");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(
      `/api/v1/pools/pool_eth_01/path/${encodeURIComponent(commitment)}`,
    );
    expect(init?.method).toBeUndefined();
  });
});

describe("local withdrawal API call", () => {
  it("posts exactly the six public fields and no note material", async () => {
    const payload: LocalWithdrawalRequest = {
      quote_id: "quote_local_001",
      proof: `0x${"ab".repeat(256)}`,
      root: `0x${"11".repeat(32)}`,
      nullifier: `0x${"22".repeat(32)}`,
      recipient: "0x3333333333333333333333333333333333333333",
      relayer_fee_wei: "240000000000000",
    };
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(
          JSON.stringify({
            withdrawal_id: "wdr_local_001",
            status: "confirmed",
            tx_hash: `0x${"44".repeat(32)}`,
            block_number: 12,
            nullifier: payload.nullifier,
            recipient: payload.recipient,
            fee_wei: payload.relayer_fee_wei,
            local_chain: "ANVIL",
            verifier_kind: "groth16-poseidon",
          }),
          {
            status: 201,
            headers: { "Content-Type": "application/json" },
          },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.submitLocalWithdrawal(payload);

    expect(result.status).toBe("confirmed");
    expect(result.tx_hash).toBe(`0x${"44".repeat(32)}`);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/v1/local/withdrawals");
    const bodyText = String(init?.body);
    expect(JSON.parse(bodyText)).toEqual(payload);
    expect(Object.keys(JSON.parse(bodyText))).toHaveLength(6);
    expect(bodyText).not.toContain("veilnote2");
    expect(bodyText).not.toContain("secret");
    expect(bodyText).not.toContain("nullifier_secret");
  });
});
