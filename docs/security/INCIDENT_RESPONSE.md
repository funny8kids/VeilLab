# Incident Response

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [SECURITY_ARCHITECTURE](SECURITY_ARCHITECTURE.md) · [TESTNET_ONLY_POLICY](TESTNET_ONLY_POLICY.md)

---

## 1. Scope

This plan covers security and safety incidents affecting VeilLab:

- mainnet access or mainnet transaction attempts,
- suspected key or secret compromise,
- signer or gateway compromise,
- agent/tool abuse, prompt injection with impact,
- sandbox escape or network isolation failure,
- malicious or compromised plugin,
- data breach or cross-tenant access,
- supply-chain compromise,
- audit integrity failure,
- extended outage or data loss.

Because VeilLab is testnet-only, financial loss is expected to be zero or test-only. The
priority order is still: **people and safety → containment → evidence → recovery →
learning**.

---

## 2. Severity

| Severity | Definition | Examples | Response |
| --- | --- | --- | --- |
| SEV1 | Critical safety or confidentiality breach | Mainnet transaction attempt, signer compromise, key exfiltration, sandbox escape to host, cross-tenant restricted data | Immediate; stop affected systems |
| SEV2 | Confirmed security impact, contained | Agent tool abuse within testnet, plugin violation, RPC poisoning, audit anomaly | < 1 hour |
| SEV3 | Suspicious activity or limited impact | Repeated capability denials, failed login spike, single wallet policy bypass attempt | < 1 business day |
| SEV4 | Low-impact bug or policy deviation | Misconfigured limit, noisy alert, documentation gap | < 5 business days |

Severity can be raised by the incident commander as understanding improves.

---

## 3. Roles

| Role | Responsibility | v0.1 (single operator) |
| --- | --- | --- |
| Incident Commander (IC) | Owns the incident, decisions, timeline | Operator |
| Security Lead | Technical investigation, containment | Operator + external reviewer if available |
| Scribe | Timeline, evidence log, decisions | Operator (template) |
| Communications | Internal/external updates | Operator, with legal advice if needed |
| Recovery Lead | Restore, validate, re-enable | Operator |

No one investigates and approves their own high-risk recovery alone when a second person is
available. For v0.1, document the conflict and seek external review for SEV1.

---

## 4. Detection sources

- SIEM/alerts from Prometheus/Grafana and OTel.
- Audit log anomalies (denials, privilege changes, signer access).
- Egress proxy denials.
- Chain gateway chain-ID mismatch.
- VeilGuard policy denials and reconciliation failures.
- Model gateway cost/usage anomalies.
- Plugin quarantine events.
- Backup/restore failures.
- Operator or researcher report.
- External notification (provider, researcher, user).

---

## 5. Response phases

```text
Detect → Triage → Contain → Eradicate → Recover → Review
```

### Detect

Record time, source, initial signal, affected systems, and whether any mainnet or key
material is involved.

### Triage

1. Assign severity.
2. Open an incident record (`inc_<ULID>`) with a timeline.
3. Preserve evidence before changing state when safe.
4. Notify according to severity.

### Contain

Choose the smallest action that stops harm:

- disable testnet execution / signer,
- revoke capability tokens and sessions,
- isolate a VM/network,
- disable a plugin or model provider,
- stop a queue or runner,
- rotate a credential,
- block an egress destination.

### Eradicate

Remove the cause: patch, rebuild, rotate, revoke, reconfigure, delete malicious artifacts.

### Recover

Restore from a known-good state, verify integrity, re-run the relevant gate, monitor closely.

### Review

Blameless postmortem within 5 business days for SEV1/SEV2. Track actions to completion.

---

## 6. Playbooks

### 6.1 Mainnet attempt or mainnet configuration

**Triggers:** denylisted chain ID, mainnet hostname, mainnet transaction hash, `kind: mainnet`.

1. Immediately stop `testnet-gateway`, `chain-gateway` and all signing.
2. Disable VeilGuard execution globally.
3. Snapshot logs, audit, registry config and process list.
4. Identify the source: config change, compromised service, dependency, or operator error.
5. Verify no mainnet key exists in any store. If one exists, treat as SEV1 key compromise.
6. Revoke RPC credentials and rotate any exposed secret.
7. Re-run G1 in an isolated environment before re-enabling.
8. Notify the operator/owner; if a transaction was broadcast, consult legal counsel.
9. Postmortem: how did the layered controls fail? Add a regression test.

**Do not** "just remove the URL" and continue without evidence and a gate re-run.

### 6.2 Suspected test wallet key compromise

1. Disable signing for the wallet and chain.
2. Revoke all approvals and capability tokens referencing the wallet.
3. Move remaining test funds to a new wallet (test assets only).
4. Rotate the key: generate a new wallet inside the signer; retire the old one.
5. Review signer audit logs: who requested signatures, from which gateway identity, with
   which approval.
6. Check for policy bypass, replay, nonce manipulation or direct signer access.
7. If the signer host is suspect, rebuild it from a clean image and restore keys only from a
   verified backup (or generate new keys).
8. Update wallet registry and policies; re-run G5.

### 6.3 Signer or gateway compromise

1. Stop the signer and gateway; remove network routes.
2. Preserve memory/disk evidence according to forensic capability; do not destroy logs.
3. Revoke mTLS certificates and all service tokens.
4. Assume all keys on the host are compromised; rotate.
5. Rebuild the host/VM from a trusted image.
6. Verify no mainnet keys or paths exist.
7. Re-run G1, G5, G6 before re-enabling.
8. External review for SEV1.

### 6.4 Agent/tool abuse or prompt injection

1. Revoke the task capability token and pause the agent.
2. Cancel running tasks and revoke model gateway virtual keys for the agent.
3. Preserve tool-call logs, prompts (if retained), model responses and artifacts.
4. Identify the untrusted source and the tool sequence.
5. Check whether any action exceeded policy: testnet requests, data reads, artifact writes.
6. If a transaction was requested, verify approval and simulation; stop execution if needed.
7. Add the fixture to the prompt-injection eval suite.
8. Tighten capability defaults if the task had more access than needed.

### 6.5 Sandbox escape or isolation failure

1. Stop the runner and all sandboxes; isolate the Research VM network.
2. Preserve the container, image digest, runtime logs and host logs.
3. Assume host compromise if escape is confirmed: rebuild the VM.
4. Rotate any credential reachable from the runner (should be none).
5. Review seccomp/capabilities/mounts and the adapter that triggered it.
6. Re-run G6 with the escape fixture.
7. Consider gVisor/microVM for that workload class.

### 6.6 Malicious or compromised plugin

1. Quarantine the plugin; cancel its jobs; revoke invocation tokens.
2. Preserve bundle, digest, signature and outputs.
3. Check network/secret access attempts and artifact integrity.
4. Notify the vendor/maintainer if appropriate.
5. Remove from the registry; add the digest to the revocation list.
6. Re-run plugin security tests and review the permission model.

### 6.7 Data breach or cross-tenant access

1. Identify the data class, subjects and volume.
2. Contain the access path (revoke session/token, fix query/policy).
3. Preserve audit evidence; do not delete affected records.
4. Assess notification obligations with legal counsel.
5. Notify affected parties per policy and law.
6. Add a cross-tenant regression test.
7. Review RLS coverage and repository scoping.

### 6.8 Supply-chain compromise

1. Stop deployments and image pulls from the affected source.
2. Identify affected images/SBOMs and running containers.
3. Revoke signing keys and registry credentials if exposed.
4. Rebuild from pinned, verified sources; compare digests.
5. Scan for persistence and unexpected network destinations.
6. Re-run G7.

### 6.9 RPC poisoning or chain data corruption

1. Disable the affected network for writes.
2. Preserve raw blocks and collector logs.
3. Compare against a second provider or a known checkpoint.
4. Roll back derived data to the last verified block.
5. Re-collect; verify parent hashes and finality.
6. Review the provider and allowlist.

### 6.10 Audit integrity failure

1. Stop audit writers if tampering is suspected.
2. Compare the hash chain and daily anchors in MinIO.
3. Restore the audit log from the last valid anchor and backup.
4. Identify who had write access; rotate credentials.
5. Treat as SEV1 if privileged actions cannot be attributed.

---

## 7. Evidence preservation

Collect, with timestamps and hashes:

- audit log export and hash-chain verification output,
- application/worker/gateway logs,
- container and image digests,
- network flow logs and proxy denials,
- chain registry and policy snapshots,
- signer audit records and socket state,
- approval tokens/records (not raw keys),
- relevant artifacts and manifests,
- operator timeline and decisions.

Store evidence in a restricted bucket with object lock. Do not place secrets in the incident
ticket. Record chain of custody.

---

## 8. Communication

### Internal update template

```text
Incident: inc_...
Severity: SEVn
Status: investigating | contained | recovering | resolved
Impact: <systems/data/users>
Current action: <what is happening now>
Next update: <time>
Request ID / trace: <id>
```

### External notification

Only after legal/owner approval. Do not speculate, do not disclose exploit details before
coordinated disclosure, and do not claim "no impact" before verification.

---

## 9. Recovery criteria

Before resuming:

- Root cause is understood or safely mitigated.
- Affected credentials are rotated.
- Affected systems are rebuilt or verified.
- Relevant gates (G1/G5/G6/G7/G8) pass.
- Monitoring shows normal behavior for an agreed observation window.
- The incident record and evidence are complete.
- An owner and deadline exist for follow-up actions.

---

## 10. Postmortem

Template:

```text
Title, incident ID, severity, dates
Summary (3 sentences)
Impact (users, data, systems, duration)
Timeline (UTC, actor, action)
Root cause (technical and organizational)
What went well / what failed
Detection and response gaps
Action items (owner, due date, verification)
Policy/doc changes
```

Rules:

- Blameless for individuals; accountable for systems.
- Every SEV1/SEV2 produces at least one test or control change.
- Action items are tracked in the roadmap and reviewed at the next gate.
- Postmortems are stored with the incident record and linked from the audit log.

---

## 11. Drills

| Drill | Frequency | Evidence |
| --- | --- | --- |
| Mainnet-attempt tabletop | Before v0.1 release | Scenario, decisions, gaps |
| Signer isolation test | Quarterly | G5 output |
| Sandbox escape test | Quarterly | G6 output |
| Backup restore | Quarterly (v0.1) / monthly (v1.0) | G8 report |
| Prompt-injection adversarial run | Each agent release | Eval results |
| Key rotation | Quarterly | Rotation log |
| Kill switch | Before each release | Timing + audit record |

---

## 12. Contacts

| Role | Name | Contact | Backup |
| --- | --- | --- | --- |
| Incident Commander | TBD | TBD | TBD |
| Security Lead | TBD | TBD | TBD |
| Platform Owner | TBD | TBD | TBD |
| Legal/Privacy | TBD | TBD | TBD |
| Hosting Provider | TBD | TBD | TBD |

Contacts are stored in the operator runbook, not in the public repository.
