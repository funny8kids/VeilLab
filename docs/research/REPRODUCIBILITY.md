# Reproducibility Specification

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [EXPERIMENT_SPEC](EXPERIMENT_SPEC.md) · [BENCHMARK_SPEC](BENCHMARK_SPEC.md)

---

## 1. Definition

A result is reproducible when an independent party can recreate the environment, rerun the
workload, and obtain the same *verified* outcome using the recorded inputs and tooling —
without asking the original author what they meant.

Reproducibility is not "the code is on GitHub". It requires:

- exact source and dataset identity,
- exact environment and toolchain identity,
- deterministic or statistically bounded output,
- a deterministic verifier,
- an immutable record.

---

## 2. Levels

| Level | Name | Requirement | Who can reproduce |
| --- | --- | --- | --- |
| **R0** | Documented | Source commit, config and datasources recorded; no successful rerun | Author |
| **R1** | Rerunnable | Same environment, same operator, rerun succeeds | Author |
| **R2** | Reproducible | Independent rebuild and rerun on a matching environment succeeds | Another researcher |
| **R3** | Independently verified | R2 on a different machine/operator, with signed attestation and deterministic checks | Third party/auditor |

Publication defaults:

- Internal draft: R1 acceptable.
- Published benchmark: R2 required.
- Security finding with reproduction: R2 required; R3 for high severity.
- Public report claiming a performance comparison: R2 for every compared series.

R3 is the target for v1.0 research assets.

---

## 3. Requirements matrix

| Artifact | R0 | R1 | R2 | R3 |
| --- | --- | --- | --- | --- |
| Source repository + commit | ✅ | ✅ | ✅ | ✅ |
| License | ✅ | ✅ | ✅ | ✅ |
| Experiment definition | ✅ | ✅ | ✅ | ✅ |
| Container image digest | — | ✅ | ✅ | ✅ |
| Toolchain versions | — | ✅ | ✅ | ✅ |
| Dataset hashes | — | ✅ | ✅ | ✅ |
| Input scalar parameters | ✅ | ✅ | ✅ | ✅ |
| Hardware fingerprint | — | ✅ | ✅ | ✅ |
| Raw samples | — | ✅ | ✅ | ✅ |
| Manifest + artifact hashes | — | ✅ | ✅ | ✅ |
| Verifier version + output | — | ✅ | ✅ | ✅ |
| Independent rerun | — | — | ✅ | ✅ |
| Different machine/operator | — | — | — | ✅ |
| Signed attestation | — | — | — | ✅ |
| Tamper-evident archive | — | — | ✅ | ✅ |

---

## 4. Environment capture

The manifest records enough to rebuild the environment:

- container image reference and digest,
- OS and kernel version,
- CPU model, physical/logical cores, memory,
- GPU model, driver, CUDA/ROCm version,
- container runtime version,
- toolchain versions (compiler, prover, verifier, libraries),
- compiler flags and optimization level,
- dependency lockfile hashes,
- CPU governor, turbo, swap, filesystem,
- network mode (`none` for most experiments),
- timezone and locale (UTC/C.UTF-8),
- random seeds where applicable.

If a field is unknown, record `"unknown"`; do not omit it. Unknown environment fields reduce
the maximum reproducibility level.

---

## 5. Determinism categories

| Category | Examples | Reproducibility criterion |
| --- | --- | --- |
| Bit-identical | Dataset hashes, compiled bytecode (with deterministic builds), manifest | Byte equality |
| Deterministic semantic | Proof validity, public inputs, Merkle root | Verifier accepts + expected values |
| Randomized semantic | Some proof systems with randomness | Proof verifies; public inputs match; proof bytes may differ |
| Statistical | Timing, memory, throughput | Median/p95 within declared tolerance; raw samples retained |
| Heuristic | Fuzzing coverage, static analysis findings | Same corpus/seed and tool version; finding set compared with documented variance |

Never require byte-identical proofs when the proving system is randomized. Never accept a
statistical match as proof validity.

---

## 6. Reproduction procedure

### 6.1 As the reproducer

1. Fetch the reproducibility bundle by manifest hash.
2. Verify the bundle signature and `SHA256SUMS`.
3. Verify the manifest hash and the source commit.
4. Pull the exact image digest; verify its signature.
5. Recreate the declared resource limits and network mode.
6. Run the experiment with the same definition, inputs and seeds.
7. Run the pinned verifier on the new artifacts.
8. Compare:
   - artifact hashes for bit-identical outputs,
   - verifier verdict for semantic outputs,
   - statistics within tolerance for timing.
9. Sign an attestation with machine fingerprint, timestamps, hashes and verdict.
10. Link the new run as a reproduction of the original.

### 6.2 As the platform

- Create a new run with `reproduces_run_id` and type `reproduction`.
- Do not copy artifacts; produce new ones.
- Record the reproducer identity, machine and operator.
- Mark the original experiment `reproducible` only after the verifier and comparison pass.
- Publish both runs and the comparison in the evidence graph.

---

## 7. Tolerance

| Metric | Tolerance | Rule |
| --- | --- | --- |
| Proof validity | Exact | Verifier must accept |
| Public inputs / roots | Exact | Hash equality |
| Constraints | Exact | Compiler output equality for same toolchain |
| Proof size | Exact for same system/params | Byte equality |
| Compile time | ±15% or within CV | Report both; flag if outside |
| Prove time | ±20% or within CV | Report both; flag if outside |
| Verify time | ±25% or within CV | Fast operations are noisy |
| Peak memory | ±10% | Flag if outside |
| Dataset content | Exact | SHA-256 equality |

Tolerances are defaults; an experiment may declare tighter bounds. A result outside tolerance
is `reproduced_with_variance`, not silently accepted.

For cross-machine R3, timing tolerance may be relaxed only with a normalized label; proof
validity and artifact hashes remain exact.

---

## 8. Bundle format

```text
bundle/
├── manifest.json
├── SHA256SUMS
├── README.md
├── definition.yaml
├── inputs/
│   ├── dataset.manifest.json
│   └── params.json
├── artifacts/
│   ├── proof.json
│   ├── public.json
│   └── metrics.json
├── logs/
│   ├── runner.log
│   └── verifier.log
├── environment/
│   ├── fingerprint.json
│   └── lockfiles/
├── verification/
│   └── verdict.json
└── SIGNATURE
```

Rules:

- `SHA256SUMS` covers every file except itself and `SIGNATURE`.
- `SIGNATURE` is a detached signature over `SHA256SUMS` by the platform key.
- The bundle is stored in MinIO with object lock for the retention period.
- `README.md` explains how to rerun in plain language.
- Large datasets are referenced by hash and source; the bundle includes a manifest and, if
  legally allowed, the data or a retrieval recipe.
- No secrets, keys, tokens or restricted data in the bundle.

---

## 9. Evidence graph

A research report links claims to evidence:

```text
Claim C1 "Semaphore membership proof verifies in < 15 ms"
  ├── Benchmark result bench_...
  │     ├── Run run_... (manifest_hash)
  │     ├── Verifier verdict (proof_valid)
  │     └── Environment fingerprint
  ├── Source commit
  └── Reproduction run run_... (R2)
```

Rules:

- Every quantitative claim has a benchmark/run reference.
- Every qualitative security claim has a finding/reproduction reference.
- Interpretations are labeled and not presented as measured facts.
- A claim without evidence is rejected by the publication checklist.

---

## 10. Tamper evidence

- Artifact and manifest hashes are recorded at creation.
- MinIO object lock/retention protects published bundles.
- The manifest is signed by the control plane.
- The audit log records publication, review and any correction.
- A daily audit anchor is written to WORM storage.
- Reproduction verifies hashes before running; a mismatch aborts.

A hash recorded after the fact is not tamper evidence. Hashes are captured by the runner and
recomputed by the verifier at completion time.

---

## 11. Common failure modes

| Failure | Symptom | Handling |
| --- | --- | --- |
| Image tag moved | Different digest | Reject; require digest |
| Toolchain drift | Different constraints/output | Pin toolchain; new series |
| Missing dataset | Cannot reproduce | Dataset retention violation; flag |
| Nondeterministic build | Byte differences | Use semantic verification; document |
| Hardware difference | Timing variance | Normalize or label non-comparable |
| Random seed omitted | Different output | Require seed in definition |
| Verifier upgraded | Different verdict semantics | Pin verifier version |
| Clock/timer change | Timing shift | Record monotonic source |
| Thermal throttling | Slower prove time | Record power/thermal state |
| Network use | Non-reproducible dependency | Deny network; vendor inputs |

---

## 12. Acceptance (G4)

G4 passes when:

1. Three experiments across at least two frameworks are reproduced on a clean Research VM.
2. The reproducer has no access to the original runner or operator notes.
3. The bundle verifies (signature + hashes) before execution.
4. Proof verification and artifact hashes match exactly where required.
5. Timing is within declared tolerance or flagged with variance.
6. A tampered artifact is detected and the run fails.
7. The original experiment is marked `reproducible` only after the comparison passes.
8. Evidence is attached to the release gate.

G4 is a release blocker.

---

## 13. Publication checklist

- [ ] Source commit and license recorded.
- [ ] Image digest and toolchain versions pinned.
- [ ] Dataset hashes and retrieval method recorded.
- [ ] Manifest hash signed and archived.
- [ ] Verifier output attached.
- [ ] At least R2 reproduction for quantitative claims.
- [ ] Environment fingerprint present.
- [ ] Raw samples retained.
- [ ] Claims linked to evidence IDs.
- [ ] Limitations and conflicts of interest stated.
- [ ] Human reviewer signed the report.
- [ ] Corrections create a new version, not an edit.

---

## 14. Anti-patterns

| Anti-pattern | Why it fails |
| --- | --- |
| "Works on my machine" | No environment capture |
| Screenshot of a terminal | No hash, no rerun |
| Average without samples | No variance, cannot verify |
| Branch instead of commit | Source can change |
| `latest` image | Digest changes silently |
| Agent-written success claim | Not a deterministic verifier |
| Proof time without verification | Invalid proof may be fast |
| Cross-hardware ranking | Not comparable |
| Deleting raw artifacts | Cannot audit or reproduce |
| Manual "reproduced" label | No independent run |
