import { describe, expect, it } from "vitest";
import {
  buildDepositIntentRequest,
  canConfirmDeposit,
} from "./deposit";

describe("deposit backup gate", () => {
  it("stays closed without a note", () => {
    expect(
      canConfirmDeposit({ notePresent: false, backupConfirmed: true }),
    ).toBe(false);
  });

  it("stays closed until the user confirms the backup", () => {
    expect(
      canConfirmDeposit({ notePresent: true, backupConfirmed: false }),
    ).toBe(false);
  });

  it("opens only when the note exists and the backup is confirmed", () => {
    expect(
      canConfirmDeposit({ notePresent: true, backupConfirmed: true }),
    ).toBe(true);
  });

  it("stays closed while submitting", () => {
    expect(
      canConfirmDeposit({
        notePresent: true,
        backupConfirmed: true,
        submitting: true,
      }),
    ).toBe(false);
  });
});

describe("deposit intent payload", () => {
  it("contains only the pool, depositor, amount and commitment", () => {
    expect(
      buildDepositIntentRequest({
        poolId: "pool_eth_01",
        depositorAddress: "0x4d2a8f1c7e9b3a6d0f5c8e2b7a1d4f6c9e3b0a28",
        amount: "0.1",
        commitment: `0x${"ab".repeat(32)}`,
      }),
    ).toEqual({
      pool_id: "pool_eth_01",
      depositor_address: "0x4d2a8f1c7e9b3a6d0f5c8e2b7a1d4f6c9e3b0a28",
      amount: "0.1",
      commitment: `0x${"ab".repeat(32)}`,
    });
  });
});
