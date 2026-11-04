import { describe, expect, it } from "vitest";
import { withdrawalIsBlocked, withdrawalSubmitMode } from "./withdraw";

describe("local withdrawal submission gate", () => {
  it("respects the API's submission_available flag", () => {
    expect(withdrawalIsBlocked("mock", "live", false, false)).toBe(true);
    expect(withdrawalIsBlocked("mock", "live", false, true)).toBe(false);
    expect(withdrawalIsBlocked("local", "live", false, false)).toBe(true);
    expect(withdrawalIsBlocked("local", "live", false, true)).toBe(false);
  });

  it("enables the real browser-proof path in local Anvil mode", () => {
    expect(withdrawalSubmitMode("local", "live", false)).toBe("local");
    expect(withdrawalSubmitMode("local", "partial", false)).toBe("local");
    expect(withdrawalSubmitMode("local", "demo", false)).toBe("local");
    expect(withdrawalSubmitMode("local", "live", false, false)).toBe(
      "local-disabled",
    );
  });

  it("stays local even when a local-mode quote fell back to demo", () => {
    expect(withdrawalSubmitMode("local", "live", true)).toBe("local");
  });

  it("keeps the existing mock and demo paths", () => {
    expect(withdrawalSubmitMode("mock", "live", false)).toBe("api");
    expect(withdrawalSubmitMode("mock", "live", true)).toBe("demo");
    expect(withdrawalSubmitMode(null, "demo", true)).toBe("demo");
  });
});
