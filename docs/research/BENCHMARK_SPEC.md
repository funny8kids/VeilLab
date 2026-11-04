# Benchmark Specification

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [EXPERIMENT_SPEC](EXPERIMENT_SPEC.md) · [REPRODUCIBILITY](REPRODUCIBILITY.md)

---

## 1. Principles

1. **Measure the workload, not the machine's mood.** Control and record the environment.
2. **Measure phases separately.** Compile, prove and verify are different costs.
3. **Keep raw samples.** A median without samples is not evidence.
4. **Compare only what is comparable.** Different hardware or toolchains produce different
   numbers; label them, do not rank them.
5. **Verify the output.** A fast invalid proof is a failed benchmark.
6. **No self-reported times.** The runner measures wall-clock and cgroup counters.

---

## 2. Metrics

| Metric | Unit | Definition | Source |
| --- | --- | --- | --- |
| `compile_ms` | ms | From compiler process start to artifact written and flushed | Runner monotonic clock |
| `prove_ms` | ms | From prover start to proof file written and flushed | Runner |
| `verify_ms` | ms | From verifier start to verdict written | Runner |
| `proof_size_bytes` | bytes | Size of the proof artifact | Filesystem stat |
| `public_input_size_bytes` | bytes | Size of public inputs | Filesystem stat |
| `constraints` | count | Constraint count reported by the compiler | Compiler output parser |
| `peak_rss_mb` | MiB | Peak resident memory of the sandbox | cgroup `memory.peak` |
| `cpu_percent` | % | CPU time delta / wall time × 100 | cgroup `cpu.stat` |
| `gpu_util_percent` | % | Mean GPU utilization over the phase | DCGM/nvidia-smi sampling |
| `gpu_memory_peak_mb` | MiB | Peak GPU memory | DCGM |
| `energy_joules` | J | Optional, if RAPL/GPU telemetry is available | Host telemetry |
| `exit_code` | int | Process exit code | Runner |
| `success` | bool | Verifier accepted the output | Verifier |

### Cost estimate

```
compute_cost = (cpu_hours × cpu_hourly_rate) + (gpu_hours × gpu_hourly_rate)
storage_cost = artifact_gb × storage_gb_month_rate × retention_months
total_estimate = compute_cost + storage_cost
```

Cost is an **estimate**, labeled as such, with the rate card version and currency. It is not
a market price or a token valuation.

---

## 3. Measurement protocol

### 3.1 Setup

- One workload per run; no co-tenant benchmarks on the same CPU/GPU.
- CPU governor `performance`; turbo behavior recorded (on/off/unknown).
- Swap disabled or recorded; memory limit high enough to avoid OOM.
- GPU exclusive; driver and CUDA versions recorded.
- Filesystem warm cache state recorded; inputs preloaded.
- Container image pulled before measurement.
- Clock source monotonic; wall time from the runner, not the workload.

### 3.2 Repetitions

| Phase | Warm-up | Measured | Notes |
| --- | --- | --- | --- |
| Compile | 0 | 3 | Compilation is usually deterministic; 3 samples |
| Prove | 1 | 5 | Increase to 10 if CV > 10% |
| Verify | 1 | 5 | Usually fast; 5 samples |
| End-to-end | 1 | 5 | Only if the workflow is meaningful as a unit |

- Report every sample, including warm-up, labeled.
- Do not silently drop outliers. If a sample is excluded, record the rule and reason.
- Report `n`, median, p50, p95, mean, stdev and coefficient of variation.
- For very fast operations (< 10 ms), increase repetitions to at least 20 and report total
  time / n.

### 3.3 What is excluded

- Image pull, dependency download, dataset download and container startup.
- Input generation outside the declared workload (unless the experiment explicitly measures
  it; then it is a separate metric).
- Artifact upload and verification reporting.

### 3.4 Concurrency

- Latency benchmarks run with concurrency 1.
- Throughput benchmarks declare concurrency, queue depth and duration; they report
  throughput and p95 latency under load separately.
- Never compare a concurrency-1 latency with a throughput run.

---

## 4. Environment fingerprint

Every benchmark records:

```json
{
  "host_id": "research-vm-01",
  "virtualization": "kvm",
  "cpu_model": "AMD EPYC 7B13",
  "physical_cores": 16,
  "logical_threads": 32,
  "memory_gb": 64,
  "gpu_model": null,
  "gpu_driver": null,
  "cuda_version": null,
  "os": "Ubuntu 24.04.1",
  "kernel": "6.8.0",
  "container_runtime": "runc 1.1.12",
  "image_digest": "sha256:...",
  "toolchain": {"circom": "2.1.9", "snarkjs": "0.7.4", "rust": null},
  "compiler_flags": "-O3",
  "cpu_governor": "performance",
  "turbo": "enabled",
  "swap": "disabled",
  "filesystem": "ext4",
  "power_mode": "ac",
  "ambient_c": 22
}
```

The fingerprint is canonicalized (sorted keys) and hashed:

```text
fingerprint_hash = sha256(canonical_json(fingerprint))
```

A benchmark without a fingerprint is `non-comparable` by definition.

---

## 5. Comparability

| Level | Definition | UI label |
| --- | --- | --- |
| `exact` | Same `fingerprint_hash`, same workload, same verifier version | Comparable |
| `normalized` | Same CPU/GPU class and documented normalization; no hardware change | Comparable (normalized) |
| `non-comparable` | Different fingerprint, workload, toolchain or verifier | Not comparable |

Rules:

- The default view groups by `fingerprint_hash` and workload.
- Cross-fingerprint comparisons are allowed only as explicitly labeled "indicative", never
  as a ranking.
- A toolchain upgrade creates a new series; do not splice series.
- A verifier version change is a new series.
- Statistical significance is reported, but practical significance is the researcher's job.

---

## 6. Statistics

For each metric and phase:

```json
{
  "n": 5,
  "samples_ms": [11800, 12010, 11950, 12120, 12030],
  "median_ms": 12010,
  "p50_ms": 12010,
  "p95_ms": 12120,
  "mean_ms": 12022,
  "stdev_ms": 120.4,
  "cv": 0.010,
  "min_ms": 11800,
  "max_ms": 12120,
  "excluded_samples": []
}
```

- Use the median for central tendency; p95 for tail behavior.
- Report CV; if CV > 10%, increase repetitions or investigate.
- Do not report more than three significant digits for noisy metrics.
- Do not claim a difference smaller than the combined measurement uncertainty.

---

## 7. Result schema

```json
{
  "benchmark_id": "bench_01J...",
  "run_id": "run_01J...",
  "experiment_id": "exp_01J...",
  "framework": "circom",
  "framework_version": "2.1.9",
  "proof_system": "groth16",
  "workload": {
    "name": "semaphore-membership",
    "circuit": "membership",
    "tree_depth": 20,
    "constraints": 12345
  },
  "environment": {
    "fingerprint_hash": "sha256:...",
    "cpu_model": "AMD EPYC 7B13",
    "gpu_model": null,
    "image_digest": "sha256:..."
  },
  "metrics": {
    "compile_ms": {"n": 3, "median": 8400, "p95": 8600},
    "prove_ms": {"n": 5, "median": 12010, "p95": 12120, "cv": 0.010},
    "verify_ms": {"n": 5, "median": 41, "p95": 44},
    "proof_size_bytes": 1280,
    "peak_rss_mb": 1820,
    "constraints": 12345
  },
  "verification": {
    "status": "verified",
    "verifier": "circom-groth16",
    "version": "1.0.0"
  },
  "comparability": "exact",
  "cost_estimate": {
    "currency": "USD",
    "compute": 0.42,
    "storage": 0.01,
    "total": 0.43,
    "rate_card": "v1"
  },
  "created_at": "2026-11-02T10:30:00Z"
}
```

---

## 8. Anti-gaming controls

| Risk | Control |
| --- | --- |
| Invalid proof reported as fast | Verifier required; no pass without proof validity |
| Fabricated timing | Runner measures; raw samples retained |
| Hidden precomputation | Source commit + input hash + fresh container |
| Warm cache advantage | Declared cache state; same protocol for all variants |
| Selective reporting | All samples stored; exclusion rule recorded |
| Benchmarking a toy input | Workload parameters recorded; size classes required |
| Toolchain drift | Image digest pinned; version recorded |
| Hardware drift | Fingerprint hash required; grouping enforced |
| Concurrent noise | Exclusive run lock; no co-tenant benchmarks |
| Modified verifier | Verifier pinned by version and image digest |

A benchmark that cannot be verified is a failed experiment, regardless of timing.

---

## 9. Reporting

Benchmark Center views:

- Group by workload → framework → proof system.
- Show environment fingerprint and comparability badge.
- Show sample count and variance; hide rankings across non-comparable groups.
- Link each number to the run manifest and raw artifacts.
- Export JSON/CSV with the fingerprint and verifier version.

Prohibited claims:

- "Framework X is faster than Y" across different fingerprints without a normalized label.
- "Fastest" based on a single sample.
- Cost claims without a rate card version.
- Performance claims for a proof that failed verification.

---

## 10. Acceptance tests

| Test | Expected |
| --- | --- |
| Missing fingerprint | Result rejected |
| Invalid proof | Result `failed`, no metrics published |
| Fewer than required samples | Result `insufficient_samples` |
| CV > threshold without escalation | Warning, not silent |
| Same workload, different image digest | Different series |
| Raw sample count mismatch | Schema validation fails |
| Cost without rate card | Rejected |
| Cross-fingerprint ranking request | UI blocks / labels indicative |

---

## 11. Open questions

- Standard workload suite and size classes per framework.
- GPU telemetry availability across drivers.
- Whether to normalize by constraints or by input size.
- Energy measurement hardware support.
- Statistical test selection for multi-variant comparisons (Mann–Whitney vs bootstrap).
