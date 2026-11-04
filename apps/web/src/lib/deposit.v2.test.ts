import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { DEMO_POOLS } from "./demoData";
import {
  buildDepositIntentRequest,
  buildLocalDepositRequest,
} from "./deposit";
import { generateNoteV2 } from "./note";

const note = await generateNoteV2(DEMO_POOLS[0], 31337);
const intentId = "dep_test_v2_001";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("v2 deposit API boundary", () => {
  it("sends the v2 commitment and never the note or its secrets", async () => {
    const bodies: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        bodies.push(String(init?.body ?? ""));
        if (String(input).endsWith("/api/v1/deposits/intent")) {
          return jsonResponse({
            intent_id: intentId,
            compliance: { decision: "allow" },
          });
        }
        return jsonResponse({
          tx_hash: `0x${"34".repeat(32)}`,
          status: "confirmed",
          block_number: 9,
        });
      }),
    );

    await api.createDepositIntent(
      buildDepositIntentRequest({
        poolId: note.payload.poolId,
        depositorAddress: "0x4d2a8f1c7e9b3a6d0f5c8e2b7a1d4f6c9e3b0a28",
        amount: note.payload.denomination,
        commitment: note.payload.commitment,
      }),
      "idem-v2-intent",
    );
    await api.recordLocalDeposit(
      buildLocalDepositRequest({
        intentId,
        commitment: note.payload.commitment,
      }),
      "idem-v2-local",
    );

    expect(bodies).toHaveLength(2);
    for (const body of bodies) {
      expect(body).not.toContain(note.token);
      expect(body).not.toContain("veilnote2");
      expect(body).not.toContain(note.payload.secret);
      expect(body).not.toContain(note.payload.nullifierSecret);
      expect(JSON.parse(body)).not.toHaveProperty("note");
      expect(JSON.parse(body)).not.toHaveProperty("secret");
      expect(JSON.parse(body)).not.toHaveProperty("nullifierSecret");
    }

    expect(JSON.parse(bodies[0]).commitment).toBe(note.payload.commitment);
    expect(JSON.parse(bodies[1])).toEqual({
      intent_id: intentId,
      commitment: note.payload.commitment,
    });
  });
});
