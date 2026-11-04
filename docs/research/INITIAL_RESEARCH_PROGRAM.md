# Initial Research Program

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [EXPERIMENT_SPEC](EXPERIMENT_SPEC.md) · [BENCHMARK_SPEC](BENCHMARK_SPEC.md)

---

## 1. Purpose

This is the first research portfolio. It is chosen to exercise the platform end to end, not
to maximize the number of protocols.

Each target must produce:

- a protocol profile with source commit, architecture, cryptography and trust assumptions,
- at least one reproducible experiment (R2),
- a benchmark with environment fingerprint and raw samples, where applicable,
- a report with an evidence graph and human review.

No target requires mainnet execution. Aztec and Zama work is limited to local sandbox,
public testnet, documentation and source analysis.

---

## 2. Portfolio

| # | Target | Focus | Platform capability exercised |
| --- | --- | --- | --- |
| 1 | Semaphore | Anonymous membership, Merkle, nullifier | ZK, commitments, Merkle, privacy identity |
| 2 | Circom + Noir | Proof system adapters | Crypto Studio, benchmark, verifier |
| 3 | SP1 | zkVM verifiable execution | zkVM adapter, benchmark |
| 4 | RISC Zero | zkVM comparison | zkVM adapter, comparability |
| 5 | OpenFHE | FHE operations and cost | FHE adapter, resource isolation |
| 6 | Zama | FHE engineering and ciphertext compute | FHE research, source analysis |
| 7 | Aztec | Private state and note model | Protocol Observatory, source analysis, local sandbox |
| 8 | MP-SPDZ | MPC baseline | MPC adapter, multi-process sandbox |

Ordering: 1 → 2 → 3/4 → 5/6 → 7 → 8. Semaphore is first because it closes the loop from
circuit to on-chain verifier.

---

## 3. Semaphore

### Research questions

- What exactly does the membership proof prove, and what does it not prove?
- How do tree depth and member count affect proof time and size?
- Is the nullifier derivation context-bound? Can a nullifier be replayed across trees or
  contexts?
- What are the trust assumptions in the verifier contract and admin keys?

### Experiments

| ID | Workload | Metrics | Verification |
| --- | --- | --- | --- |
| SEM-1 | Membership proof, depth 20, 1k members | prove/verify ms, proof size, constraints | proof valid, root match, nullifier derivation |
| SEM-2 | Depth scaling 10/20/30 | prove ms, memory, constraints | proof valid at each depth |
| SEM-3 | Nullifier reuse across contexts | rejection/acceptance behavior | expected verifier result |
| SEM-4 | On-chain verifier gas (local/testnet) | gas used | transaction receipt + event |

### Outputs

- Semaphore protocol profile.
- Circom circuit build and benchmark.
- A reproducibility bundle for SEM-1.
- A report section on nullifier context binding and admin trust.

### Risks

- Circuit/toolchain version drift.
- On-chain verifier differences between versions.
- Gas measurements are testnet-specific and not comparable to mainnet.

---

## 4. Circom and Noir baseline

### Questions

- What is the cost of the same statement in Circom/Groth16 vs Noir/UltraHonk?
- How do constraint counts and proof sizes compare at equal tree depth?
- Which phases dominate: compilation, proving, verification?

### Experiments

- Implement the same membership statement in both frameworks.
- Use identical inputs, tree depth and hardware.
- Measure compile/prove/verify separately, 5 samples with 1 warm-up.
- Verify both proofs with pinned verifiers.

### Outputs

- Two adapter conformance reports.
- A comparable benchmark (same fingerprint, same workload).
- A methodology note on what is and is not comparable.

---

## 5. SP1 and RISC Zero

### Questions

- What is the overhead of proving a simple Rust program in a zkVM?
- How do proof size, prove time and verify time compare on the same workload?
- What is the developer experience cost (toolchain, guest/host boundary)?

### Experiments

- A deterministic program: hash a fixed input, check a Merkle path, emit a public output.
- Same input and output in both zkVMs.
- Measure end-to-end and phase timings; verify the public output.

### Outputs

- zkVM adapter spikes.
- A benchmark labeled by fingerprint; no cross-machine ranking.
- A report on trade-offs, not a "winner" claim.

---

## 6. OpenFHE and Zama

### Questions

- What is the cost of key generation, encryption, multiplication and decryption for a
  bounded parameter set?
- How does noise budget constrain depth?
- What memory and wall-clock limits are needed in a sandbox?

### Experiments

- OpenFHE: CKKS or BFV small parameter set; vector operation with fixed depth.
- Zama: source analysis and, if a local sandbox is available, a bounded TFHE operation.
- Measure each phase; verify decryption result against expected plaintext.
- Record parameter sets, security level and noise budget.

### Outputs

- FHE adapter spike with resource profile.
- A report on engineering cost and parameter trade-offs.
- Clear labeling: research prototype, not production cryptography.

### Risks

- Parameter sets may be insecure if chosen for speed; record and label them.
- FHE runs are memory-heavy; use dedicated queue and limits.

---

## 7. Aztec

### Questions

- How are private notes, nullifiers and state transitions modeled?
- What is the trust boundary between user, sequencer and prover?
- Which parts can be tested in a local sandbox without mainnet?

### Experiments

- Source and documentation analysis; build the protocol profile.
- If a local sandbox/testnet is available, run a private transfer or note test.
- Measure proof generation and verification only if the toolchain is available.
- No mainnet fork, no mainnet RPC.

### Outputs

- Protocol profile with architecture and trust assumptions.
- A threat model draft.
- A feasibility note for a reproducible local experiment.

### Risks

- Rapidly changing toolchain.
- Sandbox requirements may exceed the Research VM; document limits.
- Mainnet-only features cannot be tested; state this explicitly.

---

## 8. MP-SPDZ

### Questions

- What is the baseline cost of a simple MPC computation (e.g. private comparison)?
- How do parties, network model and preprocessing affect runtime?
- Can the run be isolated with no external network?

### Experiments

- Local multi-process run with 3 parties over loopback in one sandbox.
- Fixed input size; measure preprocessing, online phase, communication bytes.
- Verify the output against a plaintext reference.

### Outputs

- MPC adapter spike.
- Resource and isolation profile.
- A note on why network models matter for comparability.

---

## 9. Cross-cutting deliverables

For every target:

1. **Protocol profile** — version, commit, architecture, cryptography, dependencies, trust
   assumptions, admin permissions, upgrade model.
2. **Experiment manifest** — image digest, toolchain, inputs, environment, artifacts.
3. **Verification record** — deterministic verifier output.
4. **Benchmark record** — environment fingerprint, raw samples, comparability.
5. **Report** — claims linked to evidence, limitations, review sign-off.
6. **Threat model** — at least a lightweight STRIDE pass for the target.

---

## 10. Success criteria (first 16 weeks)

| Criterion | Target |
| --- | --- |
| Protocols profiled | 4 (Semaphore, Circom, Noir, one zkVM) |
| Reproducible experiments (R2) | 5 |
| Benchmarks with fingerprint | 5 |
| Security findings with evidence | 2 |
| Reports published with review | 2 |
| Mainnet interactions | 0 |
| Agent key accesses | 0 |

---

## 11. Explicit non-goals

- Declaring a framework "best" from a single workload.
- Comparing timings across different hardware without a label.
- Publishing an exploit before coordinated disclosure.
- Running Aztec or Zama on mainnet.
- Production FHE/MPC parameter recommendations.
- Token, investment or yield research.
