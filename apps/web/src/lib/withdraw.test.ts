import { describe, expect, it } from "vitest";
import type { LocalActivityRecord } from "../types";
import {
  canRequestQuote,
  canSubmitWithdrawal,
  noteDepositGate,
} from "./withdraw";

const deposit = (matureAt?: string): LocalActivityRecord => ({
  id: "act_1",
  kind: "deposit",
  poolId: "pool_eth_01",
  asset: "ETH",
  denomination: "0.1",
  status: "confirmed",
  noteId: "note_abc12345",
  createdAt: "2026-11-03T00:00:00Z",
  matureAt,
  demo: false,
});

describe("withdraw deposit gate", () => {
  it("blocks a note with no matching confirmed deposit", () => {
    expect(noteDepositGate([], "note_abc12345").state).toBe("missing");
  });

  it("blocks a deposit that is still maturing", () => {
    const gate = noteDepositGate(
      [deposit("2026-11-03T01:00:00Z")],
      "note_abc12345",
      new Date("2026-11-03T00:30:00Z").getTime(),
    );
    expect(gate.state).toBe("maturing");
  });

  it("allows a matured deposit", () => {
    const gate = noteDepositGate(
      [deposit("2026-11-03T01:00:00Z")],
      "note_abc12345",
      new Date("2026-11-03T01:00:01Z").getTime(),
    );
    expect(gate.state).toBe("matured");
  });

  it("does not count failed deposits", () => {
    const failed = { ...deposit(), status: "failed" as const };
    expect(noteDepositGate([failed], "note_abc12345").state).toBe("missing");
  });

  it("requires depositReady before quote or submission", () => {
    expect(
      canRequestQuote({
        noteParsed: true,
        depositReady: false,
        recipientValid: true,
        relayerSelected: true,
        busy: false,
      }),
    ).toBe(false);
    expect(
      canSubmitWithdrawal({
        noteParsed: true,
        depositReady: false,
        recipientValid: true,
        relayerSelected: true,
        quoteReady: true,
        busy: false,
      }),
    ).toBe(false);
  });
});
