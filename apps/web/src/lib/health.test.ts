import { describe, expect, it } from "vitest";
import {
  INDEXER_LAG_WARN_BLOCKS,
  healthStatusIsFailure,
  indexerLagIsHigh,
  resolveApiMode,
  summarizeHealth,
} from "./health";

describe("API mode detection", () => {
  it("keeps degraded local health connected so the indexer warning can show", () => {
    expect(healthStatusIsFailure("ok")).toBe(false);
    expect(healthStatusIsFailure("degraded")).toBe(false);
    expect(healthStatusIsFailure("error")).toBe(true);
    expect(healthStatusIsFailure("offline")).toBe(true);
  });

  it("reads local and mock modes from health", () => {
    expect(resolveApiMode({ status: "ok", mode: "local" })).toBe("local");
    expect(resolveApiMode({ status: "ok", mode: "mock" })).toBe("mock");
    expect(resolveApiMode({ status: "ok", mode: "anvil" })).toBe("local");
  });

  it("treats a legacy health response as mock and mock:false as local", () => {
    expect(resolveApiMode({ status: "ok" })).toBe("mock");
    expect(resolveApiMode({ status: "ok", mock: false })).toBe("local");
  });
});

describe("local chain health summary", () => {
  it("reads chain id, chain service and indexer lag", () => {
    const summary = summarizeHealth({
      status: "ok",
      mode: "local",
      chain_id: 31337,
      services: { chain: "INDEXER" },
      indexer: { status: "lagging", lag_blocks: 25, last_indexed_block: 120 },
    });

    expect(summary).toMatchObject({
      apiMode: "local",
      chainId: 31337,
      chainService: "INDEXER",
      indexerStatus: "lagging",
      indexerLagBlocks: 25,
      lastIndexedBlock: 120,
    });
    expect(indexerLagIsHigh(summary)).toBe(true);
  });

  it("accepts flat indexer fields and labels low lag as healthy", () => {
    const summary = summarizeHealth({
      status: "ok",
      mode: "local",
      chain_id: 31337,
      indexer_status: "ok",
      indexer_lag_blocks: INDEXER_LAG_WARN_BLOCKS - 1,
    });

    expect(summary.indexerLagBlocks).toBe(
      INDEXER_LAG_WARN_BLOCKS - 1,
    );
    expect(indexerLagIsHigh(summary)).toBe(false);
  });

  it("warns for degraded indexer states even without a numeric lag", () => {
    const summary = summarizeHealth({
      status: "ok",
      mode: "local",
      indexer: { status: "stalled" },
    });
    expect(indexerLagIsHigh(summary)).toBe(true);
  });
});
