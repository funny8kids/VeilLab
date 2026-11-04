# Testnet-Only Policy

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [ADR-002](../adr/ADR-002-TESTNET-ONLY.md) · [NETWORK_ISOLATION](NETWORK_ISOLATION.md)

---

## 1. Policy statement

> VeilLab **MUST NOT** access mainnet RPC endpoints, hold mainnet keys, sign mainnet
> transactions, or broadcast to a mainnet. These capabilities are not disabled by a flag;
> they are absent from the architecture.

All chain interaction is limited to:

- local EVM networks operated by the platform (Anvil, Hardhat, local fork),
- explicitly registered public testnets,
- read-only analysis of public testnet data.

There is no exception process. A requirement that needs mainnet execution is out of scope
for VeilLab and must be built in a different system.

---

## 2. Approved networks

The registry is configuration, reviewed like code. Values MUST be re-verified at P1 and
before each release; chain IDs and RPC availability can change.

| Registry ID | Network | Chain ID | Kind | Native token | Finality model | Write enabled |
| --- | --- | --- | --- | --- | --- | --- |
| `eth-sepolia` | Ethereum Sepolia | `11155111` | testnet | SepoliaETH | Beacon finality (`finalized`) | Yes (policy-gated) |
| `base-sepolia` | Base Sepolia | `84532` | testnet | SepoliaETH | L2 sequencer + L1 finality | Yes (policy-gated) |
| `arbitrum-sepolia` | Arbitrum Sepolia | `421614` | testnet | SepoliaETH | L2 sequencer + L1 finality | Yes (policy-gated) |
| `op-sepolia` | Optimism Sepolia | `11155420` | testnet | SepoliaETH | L2 sequencer + L1 finality | Yes (policy-gated) |
| `polygon-amoy` | Polygon Amoy | `80002` | testnet | POL (test) | PoS checkpoints | Yes (policy-gated) |
| `bnb-testnet` | BNB Smart Chain Testnet | `97` | testnet | tBNB | BFT fast finality + confirmations | Yes (policy-gated) |
| `local-anvil` | Anvil | `31337` | local | test ETH | Instant (local) | Yes (local only) |
| `local-hardhat` | Hardhat Network | `31337` | local | test ETH | Instant (local) | Yes (local only) |

Notes:

- Anvil and Hardhat share chain ID `31337`; they are distinguished by registry ID and
  genesis hash. A chain ID match alone is insufficient.
- L2 finality is modeled as two stages: soft confirmation from the sequencer and hard
  finality via L1. The collector records both; consumers choose the appropriate stage.
- Public testnet values MUST be verified against official documentation during P1 and
  recorded in the registry with a `verified_at` timestamp.
- BNB testnet finality is modeled with explicit confirmation depth; do not assume it equals
  Ethereum finality.

### Explicitly denied (examples, not exhaustive)

| Chain ID | Network |
| --- | --- |
| `1` | Ethereum Mainnet |
| `10` | OP Mainnet |
| `56` | BNB Smart Chain |
| `100` | Gnosis |
| `137` | Polygon |
| `324` | zkSync Era |
| `8453` | Base |
| `42161` | Arbitrum One |
| `43114` | Avalanche C-Chain |
| `59144` | Linea |
| `534352` | Scroll |
| `81457` | Blast |

Unknown chain IDs are denied by default. The denylist is defense in depth, not the primary
control.

---

## 3. Forbidden capabilities

The following MUST NOT exist in code, configuration, deployment or documentation-as-runbook:

- Mainnet RPC URL or API key.
- Mainnet chain ID in the registry.
- `eth_sendTransaction` or `personal_*` RPC methods.
- A generic "sign arbitrary bytes" endpoint.
- A generic "send to any chain" function.
- A wallet that can hold mainnet assets.
- A production key, seed phrase or hardware wallet integration.
- A fallback "if testnet fails, use mainnet" path.
- A user-supplied RPC URL accepted by the gateway.
- A plugin permission for mainnet access.

A grep for mainnet chain IDs in source MUST only find deny-tests, documentation and the
explicit denylist.

---

## 4. Enforcement layers

| Layer | Mechanism | Failure mode | Test |
| --- | --- | --- | --- |
| L1 Registry schema | `kind` ∈ {local,testnet}; unknown fields rejected | Startup fails | Schema tests |
| L2 Startup validation | Chain ID + genesis + RPC hostname checked against registry | Service refuses to start | G0/G1 |
| L3 Runtime identity | `eth_chainId` + genesis hash pinned; periodic recheck | Connection closed | Gateway tests |
| L4 RPC method allowlist | Read methods restricted; write only for txgw mTLS | 403 | G1 |
| L5 Egress firewall | Only allowlisted testnet hostnames reachable | Connection refused | G6 |
| L6 Transaction policy | Wallet policy + chain allowlist + limits + simulation | Request denied | G1/G5 |
| L7 Signer validation | Independent chain/request/policy check | Signing refused | G5 |
| L8 Code absence | No mainnet broadcast/sign path | Build/test review | G1 |
| L9 CI tests | Mainnet IDs/hosts rejected; spoofing detected | Build fails | G1 |
| L10 UI | Persistent TESTNET badge; chain ID on confirmation | Warning/block | E2E |
| L11 Audit/monitoring | Denials and attempts alert | SEV1 | Operational |

No layer is optional. A missing layer blocks release.

---

## 5. Chain registry

```yaml
# configs/chains.yaml
version: 1
default_policy: deny

networks:
  - id: eth-sepolia
    kind: testnet
    chain_id: 11155111
    name: Ethereum Sepolia
    native_symbol: ETH
    rpc:
      url_ref: secret://rpc/eth-sepolia
      tls_required: true
      allowed_hosts:
        - sepolia.example-rpc.org
    genesis_hash: "0x<expected>"
    finality:
      model: beacon
      tag: finalized
      confirmations: 64
    capabilities:
      read: true
      write: true
      simulation: true
    write_policy: veilguard-default
    verified_at: "2026-11-02T00:00:00Z"

  - id: local-anvil
    kind: local
    chain_id: 31337
    name: Local Anvil
    native_symbol: ETH
    rpc:
      url: "http://anvil:8545"
      tls_required: false
      allowed_hosts: ["anvil"]
    genesis_hash: "0x<expected>"
    finality:
      model: instant
      confirmations: 1
    capabilities:
      read: true
      write: true
      simulation: true
    write_policy: local-only

denylist:
  chain_ids: [1, 10, 56, 100, 137, 324, 8453, 42161, 43114, 59144, 534352, 81457]
  host_patterns:
    - "mainnet"
    - "*.infura.io"
    - "*.alchemy.com"
    - "*.quicknode.com"
```

Rules:

- `kind` MUST be `local` or `testnet`. Anything else is a schema error.
- `chain_id` MUST be an integer and match the denylist check.
- `rpc.url_ref` points to a secret, never an inline key.
- `allowed_hosts` MUST match the resolved host and TLS SNI.
- `genesis_hash` is mandatory for local networks and recommended for testnets.
- `write: true` still requires a wallet policy and, for agents, human approval.
- There is no `mainnet` kind.

---

## 6. RPC validation

At startup and on every reconnect:

1. Resolve the configured host through the proxy; reject IP literals and private ranges
   unless the network is `local`.
2. Require HTTPS for testnets; allow HTTP only for loopback/local.
3. Call `eth_chainId`; require exact match.
4. Call `eth_getBlockByNumber("0x0", false)`; require genesis hash match where configured.
5. Reject redirects.
6. Reject responses above the size limit or with invalid JSON-RPC shape.
7. Record latency and error rate; open the circuit breaker on failure.

Periodic recheck every 5 minutes. A mismatch disables the network for reads and writes and
raises a SEV1 alert.

---

## 7. Transaction guard

The guard runs in VeilGuard **and** is re-checked by `testnet-gateway` and the signer.
Pseudocode:

```python
def authorize(request, policy, chain, wallet, simulation, approval):
    assert chain.kind in {"local", "testnet"}
    assert chain.chain_id not in DENYLIST
    assert request.chain_id == chain.chain_id
    assert wallet.network_allowed(chain.id)
    assert policy.allows_chain(chain.id)
    assert request.to in policy.allowed_recipients or policy.allow_any_recipient
    assert request.selector in policy.allowed_selectors or request.data == b""
    assert request.value <= policy.max_value_wei
    assert request.gas_limit <= policy.max_gas
    assert simulation.success
    assert simulation.request_hash == hash(request)
    assert approval.valid_for(request) or not policy.requires_approval
    assert daily_usage(wallet, chain) + request.value <= policy.daily_value_limit
    assert daily_count(wallet, chain) + 1 <= policy.daily_tx_limit
    assert request.nonce == pending_nonce(wallet, chain)
    return Allow(policy_hash=hash(policy), approval_id=approval.id)
```

Additional rules:

- Contract creation is allowed only for Deployment Wallets with a contract allowlist.
- `delegatecall`-capable admin functions are denied unless explicitly allowlisted.
- Unlimited token approvals are denied.
- Value transfers to EOAs are capped and require approval.
- A failed simulation blocks execution; override requires a human reason and still cannot
  exceed value/chain limits.
- Nonce gaps and replacements require reconciliation; no blind retry.
- Daily limits are reserved transactionally in PostgreSQL before signing.
- A request ID is single-use; duplicate submissions return the original result.

---

## 8. Signer rules

- Only `testnet-gateway` can connect, over a local pinned channel.
- The signer validates:
  - chain ID is in the wallet's policy and not denylisted;
  - request hash matches the approved request;
  - approval token signature, expiry, `jti` and one-time use;
  - nonce, recipient, value, data hash, gas limit;
  - policy hash and daily limits reference.
- The signer returns a signed raw transaction; it never broadcasts.
- The signer has no network egress and no generic signing method.
- The signer refuses to sign if any field is missing or inconsistent.

---

## 9. Adding a network

Checklist (all required):

1. Confirm it is a testnet or local network, not a mainnet or "devnet with real value".
2. Obtain official chain ID, genesis hash, RPC documentation and finality model.
3. Add a registry entry with `verified_at` and source URL.
4. Add the RPC host to the egress allowlist (security review).
5. Add a chain adapter test with a known block and receipt.
6. Add a chain-ID/genesis negative test (spoofed ID).
7. Add a wallet policy template and default limits (write disabled initially).
8. Verify finality behavior with a real testnet transaction.
9. Run G1 and G2; attach evidence.
10. Enable read; enable write only after a successful simulation and approval drill.

A network without a finality model and negative tests is not approved.

---

## 10. CI test suite (G1)

| Test ID | Scenario | Expected |
| --- | --- | --- |
| G1-01 | Registry contains chain ID 1 | Schema/startup failure |
| G1-02 | Registry contains unknown chain ID | Startup failure |
| G1-03 | RPC returns a different chain ID | Connection closed, alert |
| G1-04 | Local genesis hash mismatch | Connection closed |
| G1-05 | RPC host not in allowlist | Denied before connect |
| G1-06 | HTTP (non-TLS) testnet RPC | Rejected |
| G1-07 | RPC redirect | Rejected |
| G1-08 | `eth_sendTransaction` via gateway | 403 |
| G1-09 | `eth_sendRawTransaction` without txgw identity | 403 |
| G1-10 | Agent calls gateway directly | Network denied |
| G1-11 | Wallet policy chain mismatch | Denied + audit |
| G1-12 | Value above cap | Denied + audit |
| G1-13 | Simulation failure | Denied |
| G1-14 | Approval replay | Denied |
| G1-15 | Signer receives denylisted chain ID | Refuses |
| G1-16 | Signer receives mismatched request hash | Refuses |
| G1-17 | Source grep for mainnet broadcast path | No match outside tests/docs |
| G1-18 | Config with `kind: mainnet` | Schema error |

G1 must pass on the reference topology, not only in unit tests.

---

## 11. Operational checks

Daily:

- Review chain-identity recheck logs.
- Review policy denials and any unknown chain attempts.
- Verify no new RPC hosts or listening ports in Z4/Z5.
- Check signer has no egress sockets.

Weekly:

- Compare running firewall rules to `infrastructure/network_policy/`.
- Review wallet daily usage against caps.
- Verify registry `verified_at` freshness.

Per release:

- Run G1 and G2.
- Re-verify chain IDs and RPC endpoints.
- Review the denylist for new mainnets.

---

## 12. Audit and evidence

Every chain access records:

- network registry ID and chain ID,
- caller service identity,
- RPC method,
- request hash (not raw signed tx by default),
- result status, latency,
- policy/approval reference for writes.

Evidence for G1:

- CI logs with each test ID,
- startup rejection logs,
- firewall rule export,
- signer socket listing,
- registry validation report.

---

## 13. UI requirements

- Persistent `TESTNET` badge in the top bar and on every chain page.
- Chain ID displayed next to the network name on transaction confirmations.
- A red warning panel for any write action: "Testnet only. No real funds."
- Approval screen shows simulation result, value, recipient, data and policy limits.
- No UI path to add an RPC URL or a network; networks are operator-managed config.
- Error messages for denied actions include the policy reason and request ID.

---

## 14. Violations

Any of the following is a SEV1 incident:

- a mainnet RPC endpoint is configured or contacted,
- a mainnet chain ID is accepted,
- a mainnet key is found,
- a transaction is broadcast to a mainnet,
- the signer is reachable from an unauthorized process,
- the egress allowlist includes a mainnet host.

Response: stop all chain gateways and signing, revoke credentials, preserve evidence,
follow [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md), and do not resume until G1 passes again.
