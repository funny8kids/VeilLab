import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import {
  buildDepositIntentRequest,
  buildLocalDepositRequest,
  buildMockDepositRequest,
  depositRoute,
  describeLocalDepositFailure,
  type LocalDepositFailure,
} from "./deposit";
import { DEMO_POOLS } from "./demoData";
import { generateNote } from "./note";

const note = await generateNote(DEMO_POOLS[0]);
const intentId = "dep_test_local_001";
const commitment = note.payload.commitment;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function expectNoNoteMaterial(bodyText: string): void {
  expect(bodyText).not.toContain("veilnote1");
  expect(bodyText).not.toContain(note.payload.secret);
  expect(bodyText).not.toContain(note.payload.nullifierSecret);
  expect(bodyText).not.toContain("nullifierSecret");
  expect(bodyText).not.toContain("nullifier_secret");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("local deposit routing", () => {
  it("maps health modes to demo, mock and local deposit routes", () => {
    expect(depositRoute(null, "demo")).toBe("demo");
    expect(depositRoute("mock", "live")).toBe("mock");
    expect(depositRoute("local", "live")).toBe("local");
    expect(depositRoute("local", "partial")).toBe("local");
    // A local health response is trusted even while resources are still loading.
    expect(depositRoute("local", "demo")).toBe("local");
  });

  it("uses /mock/deposits in mock mode", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        jsonResponse({
          tx_hash: `0x${"ab".repeat(32)}`,
          status: "confirmed",
          block_number: 7,
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.recordMockDeposit(
      buildMockDepositRequest({ intentId, commitment }),
      "idem-mock",
    );

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/v1/mock/deposits");
    expect(JSON.parse(String(init?.body))).toEqual({
      intent_id: intentId,
      commitment,
    });
    expectNoNoteMaterial(String(init?.body));
  });

  it("uses /local/deposits in local Anvil mode", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        jsonResponse({
          intent_id: intentId,
          local_chain: "ANVIL",
          tx_hash: `0x${"cd".repeat(32)}`,
          status: "confirmed",
          block_number: 42,
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await api.recordLocalDeposit(
      buildLocalDepositRequest({ intentId, commitment }),
      "idem-local",
    );

    expect(response.tx_hash).toBe(`0x${"cd".repeat(32)}`);
    expect(response.block_number).toBe(42);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/v1/local/deposits");
    expect(String(url)).not.toContain("/mock/deposits");
    const bodyText = String(init?.body);
    expect(JSON.parse(bodyText)).toEqual({
      intent_id: intentId,
      commitment,
    });
    expectNoNoteMaterial(bodyText);
    expect(new Headers(init?.headers).get("Idempotency-Key")).toBe(
      "idem-local",
    );
  });

  it("maps a 409 LOCAL_DEPOSIT_DISABLED response to manual instructions", async () => {
    const instruction = {
      contract_address: "0x7a3f9c2d8e1b4a6f0c5d9e2b7a1f3c8d6e4b0a29",
      denomination_wei: "100000000000000000",
      calldata: "0xdeadbeef",
      instruction: "cast send 0x7a3f... 'deposit(bytes32)' 0x...",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          {
            code: "LOCAL_DEPOSIT_DISABLED",
            detail: "Local deposits are disabled.",
            ...instruction,
          },
          409,
        ),
      ),
    );

    let failure: LocalDepositFailure | null = null;
    try {
      await api.recordLocalDeposit(
        buildLocalDepositRequest({ intentId, commitment }),
        "idem-disabled",
      );
    } catch (error) {
      failure = describeLocalDepositFailure(error);
    }

    expect(failure).toMatchObject({
      kind: "disabled",
      instruction: {
        contractAddress: instruction.contract_address,
        denominationWei: instruction.denomination_wei,
        calldata: instruction.calldata,
        instruction: instruction.instruction,
      },
    });
  });

  it("does not treat an indexer timeout as confirmation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          {
            code: "INDEXER_CONFIRMATION_TIMEOUT",
            detail: "The indexer did not confirm the deposit in time.",
            tx_hash: `0x${"ef".repeat(32)}`,
          },
          504,
        ),
      ),
    );

    let failure: LocalDepositFailure | null = null;
    try {
      await api.recordLocalDeposit(
        buildLocalDepositRequest({ intentId, commitment }),
        "idem-timeout",
      );
    } catch (error) {
      failure = describeLocalDepositFailure(error);
    }

    expect(failure).toMatchObject({
      kind: "unconfirmed",
      retryable: true,
      code: "INDEXER_CONFIRMATION_TIMEOUT",
      txHash: `0x${"ef".repeat(32)}`,
    });
  });

  it("keeps note material out of every POST body in both modes", async () => {
    const bodies: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        bodies.push(String(init?.body ?? ""));
        if (url.endsWith("/api/v1/deposits/intent")) {
          return jsonResponse({
            intent_id: intentId,
            compliance: { decision: "allow" },
          });
        }
        return jsonResponse({
          tx_hash: `0x${"12".repeat(32)}`,
          status: "confirmed",
          block_number: 1,
        });
      }),
    );

    await api.createDepositIntent(
      buildDepositIntentRequest({
        poolId: DEMO_POOLS[0].id,
        depositorAddress: "0x4d2a8f1c7e9b3a6d0f5c8e2b7a1d4f6c9e3b0a28",
        amount: DEMO_POOLS[0].denomination,
        commitment,
      }),
      "idem-intent",
    );
    await api.recordMockDeposit(
      buildMockDepositRequest({ intentId, commitment }),
      "idem-mock",
    );
    await api.recordLocalDeposit(
      buildLocalDepositRequest({ intentId, commitment }),
      "idem-local",
    );

    expect(bodies).toHaveLength(3);
    for (const bodyText of bodies) {
      expect(bodyText.length).toBeGreaterThan(0);
      expectNoNoteMaterial(bodyText);
      expect(JSON.parse(bodyText)).not.toHaveProperty("note");
      expect(JSON.parse(bodyText)).not.toHaveProperty("secret");
      expect(JSON.parse(bodyText)).not.toHaveProperty("nullifierSecret");
    }
  });
});
