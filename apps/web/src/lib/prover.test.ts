import { describe, expect, it } from "vitest";
import type { ProofPathResponse } from "../types";
import { DEMO_POOLS } from "./demoData";
import {
  generateNote,
  generateNoteV2,
  type NotePayloadV2,
} from "./note";
import {
  DOMAIN_COMMITMENT,
  DOMAIN_NODE,
  DOMAIN_NULLIFIER,
  fieldToHex32,
  hash3,
  hash5,
  hash6,
} from "./poseidon";
import {
  buildWitnessInput,
  encodeProofHex,
  ProverError,
  type Groth16Proof,
} from "./prover";

interface LocalInputFixture {
  chain_id: string;
  pool_id: string;
  root: string;
  nullifier: string;
  recipient: string;
  fee: string;
  secret: string;
  nullifier_secret: string;
  denomination: string;
  pathElements: string[];
  pathIndices: string[];
}

interface LocalProofHexFixture {
  proof: string;
}

/**
 * The circuit build directory is gitignored. Vite's glob makes the fixture
 * imports conditional so a clean checkout skips these tests instead of failing
 * at transform time.
 */
const fixtureModules = import.meta.glob(
  "../../../../circuits/build/*.json",
  { eager: true, import: "default" },
) as Record<string, unknown>;

function readFixture<T>(name: string): T | null {
  const entry = Object.entries(fixtureModules).find(([path]) =>
    path.replace(/\\/g, "/").endsWith(`/build/${name}`),
  );
  return entry ? (entry[1] as T) : null;
}

const localInput = readFixture<LocalInputFixture>("local-input.json");
const localProof = readFixture<Groth16Proof>("local-proof.json");
const localProofHex = readFixture<LocalProofHexFixture>("local-proof-hex.json");

const demoNote = await generateNoteV2(DEMO_POOLS[0], 31337);

function emptySubtreeRoots(): bigint[] {
  const zeros = [0n];
  for (let level = 0; level < 20; level += 1) {
    zeros.push(hash3(DOMAIN_NODE, zeros[level], zeros[level]));
  }
  return zeros;
}

/** A single-leaf path at index 0; local and independent of build artifacts. */
function syntheticPath(note: NotePayloadV2): ProofPathResponse {
  const zeros = emptySubtreeRoots();
  const elements: string[] = [];
  let current = BigInt(note.commitment);
  for (let level = 0; level < 20; level += 1) {
    elements.push(fieldToHex32(zeros[level]));
    current = hash3(DOMAIN_NODE, current, zeros[level]);
  }
  return {
    chain_id: note.chainId,
    pool_key: note.poolId,
    commitment: note.commitment,
    leaf_index: 0,
    leaf_count: 1,
    tree_depth: 20,
    root: fieldToHex32(current),
    path_elements: elements,
    path_indices: new Array<number>(20).fill(0),
  };
}

function expectProverError(fn: () => unknown, code: string): void {
  let caught: unknown;
  try {
    fn();
  } catch (error) {
    caught = error;
  }
  expect(caught).toBeInstanceOf(ProverError);
  expect((caught as ProverError).code).toBe(code);
}

function deployPoolLabel(note: NotePayloadV2): string {
  const field = BigInt(note.poolIdField);
  return `0x${(field << 8n).toString(16).padStart(64, "0")}`;
}

describe("local fixture witness", () => {
  it.skipIf(!localInput)(
    "buildWitnessInput matches circuits/build/local-input.json",
    () => {
      const input = localInput as LocalInputFixture;
      const chainId = Number(input.chain_id);
      const poolIdField = BigInt(input.pool_id);
      const denomination = BigInt(input.denomination);
      const secret = BigInt(input.secret);
      const nullifierSecret = BigInt(input.nullifier_secret);
      const commitment = hash6(
        DOMAIN_COMMITMENT,
        BigInt(chainId),
        poolIdField,
        denomination,
        secret,
        nullifierSecret,
      );
      const nullifier = hash5(
        DOMAIN_NULLIFIER,
        BigInt(chainId),
        poolIdField,
        commitment,
        nullifierSecret,
      );
      const note: NotePayloadV2 = {
        v: 2,
        id: "note_fixture0001",
        chainId,
        poolId: "pool_eth_01",
        poolIdField: fieldToHex32(poolIdField),
        asset: "ETH",
        denomination: "0.1",
        denominationWei: input.denomination,
        secret: fieldToHex32(secret),
        nullifierSecret: fieldToHex32(nullifierSecret),
        commitment: fieldToHex32(commitment),
        nullifier: fieldToHex32(nullifier),
        createdAt: "2026-11-03T00:00:00.000Z",
      };
      const recipient = `0x${BigInt(input.recipient)
        .toString(16)
        .padStart(40, "0")}`;
      const pathIndices = input.pathIndices.map(Number);
      const leafIndex = pathIndices.reduce(
        (total, bit, level) => total + bit * 2 ** level,
        0,
      );
      const path: ProofPathResponse = {
        chain_id: chainId,
        // Live API shape: the deploy label, not the zero-prefixed field.
        pool_id: deployPoolLabel(note),
        pool_key: "pool_eth_01",
        commitment: note.commitment,
        leaf_index: leafIndex,
        leaf_count: leafIndex + 1,
        tree_depth: 20,
        root: fieldToHex32(BigInt(input.root)),
        path_elements: input.pathElements.map((value) =>
          fieldToHex32(BigInt(value)),
        ),
        path_indices: pathIndices,
      };

      expect(buildWitnessInput(note, path, recipient, input.fee)).toEqual(input);
    },
  );

  it.skipIf(!localProof || !localProofHex)(
    "encodeProofHex matches circuits/build/local-proof-hex.json",
    () => {
      const encoded = encodeProofHex(localProof as Groth16Proof);
      expect(encoded).toBe((localProofHex as LocalProofHexFixture).proof);
      expect(encoded).toHaveLength(2 + 256 * 2);
    },
  );
});

describe("witness validation", () => {
  it("accepts the live path pool_id deploy label and pool_key", () => {
    const path = {
      ...syntheticPath(demoNote.payload),
      pool_id: deployPoolLabel(demoNote.payload),
      pool_key: "pool_eth_01",
    };
    const witness = buildWitnessInput(
      demoNote.payload,
      path,
      "0x2222222222222222222222222222222222222222",
      "240000000000000",
    );
    expect(witness.chain_id).toBe("31337");
    expect(witness.pathElements).toHaveLength(20);
    expect(witness.pathIndices).toHaveLength(20);
  });

  it("accepts the deploy label when pool_key is absent", () => {
    const path = {
      ...syntheticPath(demoNote.payload),
      pool_id: deployPoolLabel(demoNote.payload),
    };
    delete path.pool_key;
    expect(() =>
      buildWitnessInput(
        demoNote.payload,
        path,
        "0x2222222222222222222222222222222222222222",
        "1",
      ),
    ).not.toThrow();
  });

  it("rejects a mismatched pool_key", () => {
    const path = {
      ...syntheticPath(demoNote.payload),
      pool_key: "pool_eth_1",
    };
    expectProverError(
      () =>
        buildWitnessInput(
          demoNote.payload,
          path,
          "0x2222222222222222222222222222222222222222",
          "1",
        ),
      "PATH_INVALID",
    );
  });

  it("rejects a Merkle path with the wrong depth", () => {
    const path = syntheticPath(demoNote.payload);
    path.path_elements = path.path_elements.slice(0, 19);
    expectProverError(
      () =>
        buildWitnessInput(
          demoNote.payload,
          path,
          "0x2222222222222222222222222222222222222222",
          "1",
        ),
      "PATH_INVALID",
    );
  });

  it("rejects a path whose commitment does not match the note", () => {
    const path = {
      ...syntheticPath(demoNote.payload),
      commitment: fieldToHex32(1n),
    };
    expectProverError(
      () =>
        buildWitnessInput(
          demoNote.payload,
          path,
          "0x2222222222222222222222222222222222222222",
          "1",
        ),
      "PATH_INVALID",
    );
  });

  it("rejects a path that does not hash to the supplied root", () => {
    const path = { ...syntheticPath(demoNote.payload), root: fieldToHex32(1n) };
    expectProverError(
      () =>
        buildWitnessInput(
          demoNote.payload,
          path,
          "0x2222222222222222222222222222222222222222",
          "1",
        ),
      "PATH_INVALID",
    );
  });

  it("rejects a v1 note as not a ZK note", async () => {
    const v1 = await generateNote(DEMO_POOLS[0]);
    let caught: unknown;
    try {
      buildWitnessInput(
        v1.payload as unknown as NotePayloadV2,
        syntheticPath(demoNote.payload),
        "0x2222222222222222222222222222222222222222",
        "1",
      );
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(ProverError);
    expect((caught as ProverError).code).toBe("NOTE_NOT_V2");
    expect((caught as Error).message).toBe(
      "This note is not a ZK note. Regenerate it in local mode.",
    );
  });

  it("rejects an invalid recipient and an out-of-range fee", () => {
    const path = syntheticPath(demoNote.payload);
    expectProverError(
      () => buildWitnessInput(demoNote.payload, path, "0x1234", "1"),
      "INPUT_INVALID",
    );
    expectProverError(
      () =>
        buildWitnessInput(
          demoNote.payload,
          path,
          "0x2222222222222222222222222222222222222222",
          (1n << 64n).toString(),
        ),
      "INPUT_INVALID",
    );
  });
});
