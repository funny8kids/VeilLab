# ADR-004 · Unified Cryptography Adapter Layer

**Status:** Accepted · **Date:** 2026-11-02 · **Deciders:** Cryptography, Architecture

---

## Context

VeilLab compares multiple cryptographic systems:

- ZK: Circom, Noir, Halo2,
- zkVM: SP1, RISC Zero,
- FHE: OpenFHE,
- MPC: MP-SPDZ,
- commitments, Merkle trees, identity schemes.

Each has its own CLI, language, build system, proof format, parameters and performance
profile. Direct integration in business modules would:

- couple the research engine to toolchain details,
- make benchmarks incomparable,
- spread version and security policy across the codebase,
- make adding a framework a cross-cutting change,
- create inconsistent verification and artifact handling.

## Decision

Introduce a **unified adapter layer with isolated execution**.

1. `cryptography/interfaces/` defines contracts: `ProofSystem`, `FheSystem`, `MpcSystem`,
   `CommitmentScheme`, `MerkleTree`, `BenchmarkAdapter`.
2. `cryptography/adapters/<framework>/` implements an adapter. Business modules never import
   a concrete adapter; they resolve it through the adapter registry.
3. Each adapter declares:
   - supported operations,
   - toolchain image digest and versions,
   - input/output schemas,
   - resource profile,
   - verifier contract,
   - security class (trusted first-party or untrusted third-party).
4. Execution happens in an **isolated worker/sandbox**:
   - no network,
   - non-root, read-only root,
   - CPU/memory/time/output limits,
   - inputs mounted read-only, outputs on a per-run volume.
5. Heavy primitives shared across adapters (hashing, Merkle, commitments, field ops) live in
   `cryptography/core/` (Rust) behind a gRPC interface, used by the runner—not by business
   modules directly.
6. Every adapter produces standardized artifacts + metrics; the Research Engine, not the
   adapter, decides success via a deterministic verifier.
7. Toolchains are pinned by image digest. Upgrading a toolchain creates a new adapter/
   verifier series; historical results are never rewritten.

### Interface sketch

```python
class ProofSystem(Protocol):
    name: str
    version: str

    def compile(self, source: Source, config: CompileConfig) -> BuildArtifact: ...
    def prove(self, build: BuildArtifact, inputs: ProveInputs) -> ProofArtifact: ...
    def verify(self, proof: ProofArtifact, public_inputs: PublicInputs) -> VerifyResult: ...
    def benchmark(self, plan: BenchmarkPlan) -> BenchmarkResult: ...
```

Adapters are invoked through the runner with a serialized job spec; they do not receive a
database session, secrets or host paths.

## Consequences

### Positive

- One experiment model and one benchmark methodology across frameworks.
- Adding a framework is additive: interface + adapter + tests + verifier.
- Toolchain risk is contained in a sandbox.
- Historical results remain comparable within a pinned series.
- Business modules remain framework-agnostic.

### Negative

- Adapter maintenance is ongoing, especially for fast-moving ZK projects.
- The interface must abstract genuinely different models (proofs vs FHE circuits vs MPC
  protocols); some operations will be optional or lossy.
- Sandboxing adds overhead and complexity.
- Cross-framework comparisons can tempt invalid normalization; the benchmark spec must
  enforce comparability labels.

### Mitigations

- Keep the interface minimal; use capability flags for optional operations.
- Contract tests and golden outputs per adapter.
- A conformance suite every adapter must pass.
- Deprecate adapters explicitly; never silently change behavior.
- Store raw outputs so new verifiers can re-evaluate old artifacts.

## Alternatives rejected

| Alternative | Why rejected |
| --- | --- |
| Direct framework calls in research code | Coupling, inconsistent verification, unsafe builds |
| One "universal" ZK library | Does not exist; would hide important differences |
| WASM-only adapters | Many toolchains are native/GPU-heavy; immature |
| Run everything in the API process | No isolation, resource contention, unsafe |
| Adapter-specific result formats | Incomparable benchmarks, fragmented UI |

## Rules

- A business module MUST NOT import `cryptography.adapters.*`.
- An adapter MUST NOT access the database, Redis, network or secrets.
- An adapter MUST declare its image digest and toolchain versions.
- A verifier MUST be independent of the adapter's success claim.
- A benchmark without a verified output is invalid.
- A new adapter requires a threat review if it runs untrusted build scripts or uses a GPU.

## References

- [SYSTEM_ARCHITECTURE](../architecture/SYSTEM_ARCHITECTURE.md)
- [EXPERIMENT_SPEC](../research/EXPERIMENT_SPEC.md)
- [BENCHMARK_SPEC](../research/BENCHMARK_SPEC.md)
- [PLUGIN_ARCHITECTURE](../architecture/PLUGIN_ARCHITECTURE.md)
