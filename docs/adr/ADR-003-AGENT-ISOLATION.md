# ADR-003 · Agent Isolation and Capability Model

**Status:** Accepted · **Date:** 2026-11-02 · **Deciders:** Security, Architecture, AI

---

## Context

VeilLab uses AI agents to discover protocols, analyze source, propose experiments, run
benchmarks and draft reports. Agents process untrusted content: repositories, papers, web
pages, RPC metadata and model output. Prompt injection is expected, not hypothetical.

A conventional design gives an agent a service account, API token and tool access. That
creates three problems:

1. A token often has broad standing permissions.
2. The agent process may hold provider keys, database credentials or wallet access.
3. A successful injection can turn research automation into an exfiltration or transaction
   tool.

## Decision

Agents are **capability-scoped, isolated research workers**.

1. **Separate zone/VM.** `agent-runtime` runs in Z3 with no route to databases, Redis,
   testnet RPC or the signer.
2. **No standing permissions.** Each task receives a short-lived capability JWT bound to
   task, project, audience, resources, quotas and expiry (default 15 minutes, max 1 hour).
3. **No secrets.** Agents never receive provider keys, wallet keys, DB credentials or
   session tokens. The model gateway holds provider keys; the signer holds wallet keys.
4. **Tool gateway.** All actions go through typed tools with JSON Schema validation,
   capability checks, quotas and audit. There is no shell, SQL, arbitrary HTTP or file tool.
5. **Human approval** for deploy, execute, publish, policy changes and capability escalation.
   The approver sees the exact payload, not an agent summary.
6. **Model gateway.** Agents use virtual model IDs; provider base URLs and keys are registry
   controlled.
7. **Prompt-injection defenses.** Untrusted content is provenance-labeled and treated as
   data; tool policy is enforced independently of model intent.
8. **Kill switch and revocation.** Tokens can be revoked by `jti`; the runtime and testnet
   execution can be disabled globally.

## Consequences

### Positive

- A prompt injection can waste effort or produce bad drafts, but cannot directly move funds
  or read keys.
- Least privilege is explicit and auditable per task.
- Agents can be tested adversarially with a bounded blast radius.
- The same model supports future multi-agent workflows without granting more access.

### Negative

- More moving parts: token issuance, tool gateway, model gateway, quotas.
- Agents are less autonomous; some workflows need human approval.
- Capability design requires discipline; an overly broad default defeats the model.
- Added latency for token and tool checks.

### Mitigations

- Default capability sets are narrow and reviewed.
- Approval UX shows the concrete action and policy result.
- Automated tests cover forbidden capabilities and injection fixtures.
- Capability catalog is versioned with the API.

## Alternatives rejected

| Alternative | Why rejected |
| --- | --- |
| Agent with a project service account | Standing broad permissions; hard to bound blast radius |
| Role-based permissions only | Roles are too coarse and long-lived for tasks |
| Agent with wallet access but "testnet only" | Violates "Agent Never Owns Funds"; one policy bug becomes key exposure |
| Agent in the API process | No isolation; prompt injection reaches credentials and DB |
| No tools, chat-only | Cannot perform research workflows |

## Review triggers

- A new tool with network, filesystem or value impact.
- A new model provider with different data retention.
- Multi-agent delegation (agent-to-agent capability transfer is currently forbidden).
- Any proposal to let an agent publish or deploy without human approval.

## References

- [AGENT_PERMISSION_MODEL](../security/AGENT_PERMISSION_MODEL.md)
- [THREAT_MODEL](../security/THREAT_MODEL.md)
- [NETWORK_ISOLATION](../security/NETWORK_ISOLATION.md)
