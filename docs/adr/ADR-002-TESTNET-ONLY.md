# ADR-002 · Testnet-Only Architecture

**Status:** Accepted · **Date:** 2026-11-02 · **Deciders:** Security, Architecture, Product

---

## Context

VeilLab executes transactions, deploys contracts and tests wallets. Any mainnet capability
would create custody, legal and safety risk far beyond the research value. A feature flag or
a UI warning is not sufficient: misconfiguration, compromised credentials or a malicious
agent could enable real-value transactions.

The project principle is absolute: **Testnet Only**.

## Decision

Mainnet execution is **not a disabled feature; it is absent from the architecture**.

1. The chain registry schema permits only `kind: local` or `kind: testnet`. There is no
   `mainnet` kind and no generic RPC URL field.
2. Unknown chain IDs and known mainnet chain IDs are denied. A denylist is defense in depth.
3. No mainnet RPC endpoint, API key, wallet, signer or broadcast method exists in code or
   configuration.
4. `chain-gateway` is the only RPC egress point. It pins chain ID and, for local chains,
   genesis hash; it allowlists methods and restricts `eth_sendRawTransaction` to
   `testnet-gateway` over mTLS.
5. The signer independently validates chain ID, policy and request hash; it has no network
   egress and no generic signing API.
6. Egress firewalls allow only approved testnet hosts. Unknown destinations fail closed.
7. CI tests attempt mainnet chain IDs, hosts and methods and require denial. G1 and G5 are
   release blockers.
8. There is no exception process. A mainnet requirement is out of scope for VeilLab.

## Consequences

### Positive

- No real funds at risk from agents, plugins or operator mistakes.
- Simpler incident response and legal posture.
- Clear product boundary and user expectation.
- Security effort concentrates on research integrity and isolation.

### Negative

- Cannot validate mainnet-only behavior, gas markets or production finality.
- Some protocols depend on mainnet state; they can only be studied via source, testnet
  deployments or local simulations, not mainnet forks.
- Researchers may need a separate, out-of-scope environment for mainnet work.
- Some tooling assumes a mainnet chain ID and needs adaptation.

### Mitigations

- Support local Anvil/Hardhat and testnet forks of **testnets only**.
- Document testnet limitations in reports.
- Use source-level analysis and testnet deployments for protocol research.
- Provide clear UI labels and docs so users do not expect mainnet parity.

## Alternatives rejected

| Alternative | Why rejected |
| --- | --- |
| Feature flag for mainnet | A flag can be flipped by mistake or compromise |
| "Read-only mainnet" RPC | Still creates a mainnet data dependency and egress path; excluded for now |
| Separate mainnet deployment | Out of scope; would need a different security and legal model |
| User-supplied RPC URL | Bypasses registry and chain identity controls |
| Mainnet fork for research | Requires mainnet RPC; violates the principle |

If read-only mainnet analytics is ever required, it must be a separate product with its own
ADR, network zone and explicit approval — not a configuration toggle in VeilLab.

## Verification

- G1: registry, RPC, method, policy and signer denial tests.
- G5: agent cannot reach keys, signer or mainnet.
- G6: network isolation tests.
- Source review: no mainnet broadcast path outside tests/docs.
- Audit: any mainnet attempt is SEV1.

## References

- [TESTNET_ONLY_POLICY](../security/TESTNET_ONLY_POLICY.md)
- [NETWORK_ISOLATION](../security/NETWORK_ISOLATION.md)
- [THREAT_MODEL](../security/THREAT_MODEL.md)
