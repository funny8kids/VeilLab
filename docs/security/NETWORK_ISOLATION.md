# Network Isolation

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [SECURITY_ARCHITECTURE](SECURITY_ARCHITECTURE.md) · [DEPLOYMENT_ARCHITECTURE](../architecture/DEPLOYMENT_ARCHITECTURE.md)

---

## 1. Principles

1. **Default deny** for ingress and egress.
2. **One purpose per network.** Data, control, research, agent, testnet read and testnet
   sign are separate Layer 2/3 domains.
3. **No transitive trust.** Being able to reach the API does not imply reaching the database.
4. **Egress through a proxy.** Workloads do not resolve or connect to the internet directly.
5. **Identity-bound channels.** Internal service calls use mTLS, not network location alone.
6. **Fail closed.** Missing policy, unknown destination or expired certificate means deny.
7. **Test the denial.** Every "cannot" in this document has a negative test.

---

## 2. Zones

| Zone | Name | Members | Sensitivity |
| --- | --- | --- | --- |
| Z0 | Data | PostgreSQL, ClickHouse, Redis, MinIO, secret store | Highest |
| Z1 | Control | web, api, scheduler, worker, tool gateway | High |
| Z2 | Research | runner-controller, crypto-core, sandboxes | Medium |
| Z3 | Agent | agent-runtime, model-gateway | Low/Medium |
| Z4 | Testnet read | chain-gateway, chain-collector | Medium |
| Z5 | Testnet sign | testnet-gateway, test-signer | Critical |
| Z6 | Admin | operator workstation, Grafana, SSH | High |

Z2, Z3, Z4 and Z5 are mutually unreachable except for the explicitly listed flows.

---

## 3. Allowed flow matrix

Rows initiate; columns accept. `✅` allowed; `—` denied.

| From ↓ / To → | web | api | worker | runner | agent | modelgw | collector | chaingw | txgw | signer | object | data | internet |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| web | — | ✅ | — | — | — | — | — | — | — | — | — | — | — |
| api | — | — | ✅ queue | ✅ mTLS | ✅ mTLS | — | — | ✅ read | ✅ mTLS | — | ✅ | ✅ | — |
| worker | — | ✅ | — | — | — | — | — | — | — | — | ✅ | ✅ | proxy |
| runner | — | ✅ lease | — | — | — | — | — | — | — | — | presigned | — | — |
| agent | — | ✅ tools | — | — | — | ✅ | — | — | — | — | presigned | — | — |
| modelgw | — | — | — | — | — | — | — | — | — | — | — | — | ✅ AI proxy |
| collector | — | — | — | — | — | — | — | ✅ | — | — | ✅ | ✅ insert | — |
| chaingw | — | — | — | — | — | — | — | — | — | — | — | — | ✅ RPC |
| txgw | — | ✅ callback | — | — | — | — | — | ✅ write | — | ✅ local | — | ✅ | — |
| signer | — | — | — | — | — | — | — | — | — | — | — | — | — |
| object | — | — | — | — | — | — | — | — | — | — | — | — | — |
| data | — | — | — | — | — | — | — | — | — | — | — | — | — |

Notes:

- `api → runner`, `api → agent`, `api → txgw` are outbound control calls over mTLS; the
  reverse direction is limited to responses and explicit lease/heartbeat endpoints.
- `runner → object` and `agent → object` are only presigned MinIO URLs; they hold no DB or
  Redis credential and cannot reach `vl-data`.
- `txgw → signer` is a Unix socket or loopback mTLS with a pinned client certificate.
- `signer` has no default gateway and no DNS configuration.
- `worker → internet` is only for data-source fetches through the egress proxy; it is
  disabled for the crypto/benchmark queues.

---

## 4. Per-service network policy

| Service | Ingress | Egress | DNS |
| --- | --- | --- | --- |
| `web` | 443 from LAN/admin | `api` only | internal |
| `api` | 443/8000 from web/admin | data, runner, agent, txgw, chaingw | internal |
| `scheduler` | none | api, Redis | internal |
| `worker` | none | data, api, egress proxy | internal |
| `runner-controller` | api (mTLS) | api, MinIO presigned, sandboxes | internal |
| `crypto-core` | runner only | none | none |
| sandbox | none | none | none |
| `agent-runtime` | api (mTLS) | api, model-gateway, MinIO presigned | internal |
| `model-gateway` | agent only | AI provider proxy | proxy-resolved |
| `chain-gateway` | collector, api, txgw | testnet RPC allowlist | proxy-resolved |
| `chain-collector` | none | chain-gateway, data insert | internal |
| `testnet-gateway` | api (mTLS) | chaingw, signer | internal |
| `test-signer` | txgw (local) | none | none |
| `postgres` | Z1 roles | none | none |
| `clickhouse` | Z1, collector | none | none |
| `redis` | Z1 | none | none |
| `minio` | Z1, Z2/Z3/Z4 (presigned/raw) | none | none |

---

## 5. Chain access

### 5.1 Single egress point

All testnet RPC traffic goes through `chain-gateway`. No other process has an RPC URL or
RPC credential.

The gateway:

1. Loads the chain registry at startup; refuses unknown chains.
2. Pins `chain_id` per network and verifies `eth_chainId` on connect and periodically.
3. Pins genesis hash for local networks and verifies it.
4. Applies a JSON-RPC method allowlist:
   - read: `eth_chainId`, `eth_blockNumber`, `eth_getBlockByNumber`, `eth_getBlockByHash`,
     `eth_getTransactionByHash`, `eth_getTransactionReceipt`, `eth_getLogs`, `eth_call`,
     `eth_estimateGas`, `eth_getCode`, `eth_getBalance`, `eth_getTransactionCount`,
     `eth_feeHistory`, `eth_maxPriorityFeePerGas`;
   - write: `eth_sendRawTransaction` **only** for mTLS client `testnet-gateway`.
5. Rejects `eth_sendTransaction`, `personal_*`, `admin_*`, `debug_*` (except an explicitly
   approved trace method for simulation), and any method not listed.
6. Enforces response size, timeout and concurrency limits.
7. Logs method, network, caller identity and result status (no raw signed tx by default).
8. Rejects redirects and non-HTTPS endpoints (except loopback local chains).

### 5.2 Mainnet denial

- Registry kind must be `local` or `testnet`.
- Known mainnet chain IDs are explicitly denied.
- Unknown chain IDs are denied.
- Egress allowlist contains only approved testnet hostnames.
- The signer independently rejects any chain ID not in the wallet policy.
- There is no mainnet broadcast method, key or configuration.

See [TESTNET_ONLY_POLICY.md](TESTNET_ONLY_POLICY.md).

### 5.3 Local chains

Anvil and Hardhat both use chain ID `31337`. They are distinguished by **network registry
ID and genesis hash**, not chain ID alone:

```yaml
- id: local-anvil
  chain_id: 31337
  kind: local
  genesis_hash: "0x..."
  rpc: "http://anvil:8545"
- id: local-hardhat
  chain_id: 31337
  kind: local
  genesis_hash: "0x..."
  rpc: "http://hardhat:8545"
```

The gateway verifies the genesis hash before serving requests. A mismatch is a hard failure.

---

## 6. AI provider egress

Only `model-gateway` may reach AI providers.

- Provider base URLs are registry entries, not user input.
- The egress proxy allowlists provider hostnames and TLS SNI.
- Agents receive virtual model IDs; they cannot specify an arbitrary URL.
- Provider keys never leave the gateway.
- Requests are size-limited and redacted according to data classification.
- A provider that requires a non-standard port or protocol requires a security review.

---

## 7. Implementation

### 7.1 Docker networks

```yaml
networks:
  vl-data:
    internal: true
  vl-object:
    internal: true
  vl-observability:
    internal: true
  vl-control:
    driver: bridge
  vl-research:
    internal: true
  vl-agent:
    internal: true
  vl-testnet-read:
    internal: true
  vl-testnet-sign:
    internal: true
```

`internal: true` removes the default gateway. Services that need egress join a dedicated
`vl-egress` network **only** if they are the designated proxy/gateway.

Compose `network_mode` and `cap_add` are forbidden for application services.

### 7.2 Host firewall (nftables example)

```nft
table inet veillab {
  chain forward {
    type filter hook forward priority 0; policy drop;

    # Established/related
    ct state established,related accept

    # web -> api
    iifname "br-web" oifname "br-control" tcp dport 8000 accept

    # api -> data (PostgreSQL, ClickHouse, Redis)
    iifname "br-control" oifname "br-data" tcp dport { 5432, 6379, 8123, 9000 } accept

    # presigned object access (MinIO only)
    iifname "br-control" oifname "br-object" tcp dport 9100 accept
    iifname "br-research" oifname "br-object" tcp dport 9100 accept
    iifname "br-agent" oifname "br-object" tcp dport 9100 accept
    iifname "br-testnet-read" oifname "br-object" tcp dport 9100 accept

    # api -> research / agent / testnet (mTLS)
    iifname "br-control" oifname "br-research" tcp dport 8700 accept
    iifname "br-control" oifname "br-agent" tcp dport { 8710, 8800 } accept
    iifname "br-control" oifname "br-testnet-sign" tcp dport 8601 accept

    # runner -> api lease
    iifname "br-research" oifname "br-control" tcp dport 8000 accept

    # gateway egress to RPC proxy only
    iifname "br-testnet-read" oifname "br-egress" tcp dport 3128 accept

    # everything else denied
  }
}
```

This is illustrative. The authoritative rules live in
`infrastructure/network_policy/` and are applied by the deployment playbook. They MUST be
covered by tests that attempt each denied flow.

### 7.3 Egress proxy

- Squid/Envoy with explicit hostname allowlist.
- Deny CONNECT to IP literals and non-allowlisted SNI.
- Resolve DNS at the proxy; return no resolver to workloads.
- Log destination, bytes and identity; alert on denied attempts.
- Separate allowlists for data sources (worker) and AI providers (model gateway).
- No generic HTTP proxy credential for agents or sandboxes.

### 7.4 mTLS

- Internal CA issues short-lived certs (30–90 days).
- SAN encodes service identity, e.g. `spiffe://veillab/api`.
- Services verify the expected peer identity, not just "signed by CA".
- Revocation list is checked at connection; compromised certs are rotated immediately.
- The signer pins the gateway certificate fingerprint in addition to CA validation.

---

## 8. Signer isolation

The signer is the highest-value component. Its network namespace:

- Has **no default route** and **no DNS**.
- Listens only on a Unix socket or `127.0.0.1:8602`.
- Accepts a connection only from the gateway process (same pod/VM or pinned mTLS).
- Has no HTTP client, no RPC client and no package manager.
- Holds keys in memory only after decrypting an encrypted keystore.
- Writes an audit record for every sign request and result.
- Refuses to sign if policy reference, chain ID, nonce, recipient, value or data hash does
  not match the approved request.

A signer that can reach the internet is a design failure, not a configuration issue.

---

## 9. Verification tests

These tests are mandatory in CI and in the G1/G5/G6 gate suite.

### Positive

- web → api 200.
- api → postgres 5432.
- runner → api lease endpoint 200.
- agent → tool gateway 200 with valid capability.
- collector → chain-gateway `eth_blockNumber` 200.
- txgw → signer sign request 200 with valid approval.

### Negative

| Test | Expected |
| --- | --- |
| agent → postgres:5432 | timeout / refused |
| agent → testnet RPC | DNS failure / refused |
| agent → signer:8602 | refused |
| runner → internet:443 | refused |
| sandbox → any network | refused |
| collector → AI provider | refused |
| model gateway → RPC | refused |
| signer → internet | no route |
| unknown RPC host via chain-gateway | 403 |
| mainnet chain ID via registry | startup failure |
| `eth_sendTransaction` via gateway | 403 |
| `eth_sendRawTransaction` without txgw mTLS | 403 |
| agent capability for `wallet.private_key.read` | 403 + audit |
| expired capability token | 401 + audit |
| cross-tenant object read | 404/403 + audit |

Tests run from inside the relevant network namespace. A test executed from the host is not
evidence of isolation.

---

## 10. Development caveat

On a single Windows/macOS Docker Desktop host:

- All containers share a VM and often a host network; `internal: true` is logical.
- The operator can `docker exec` into any container.
- The host can reach all published ports.

Therefore:

- Development MAY use the logical topology for convenience.
- Security gates MUST run on the four-VM Linux reference topology.
- Documentation and UI MUST NOT claim physical isolation for a dev deployment.
- `docker exec` into signer or production-like data containers is disabled or audited in
  the reference topology.

---

## 11. Operations

### Adding a destination

1. Security review with business justification.
2. Add to the registry/allowlist with owner and expiry.
3. Add a positive and a negative test.
4. Deploy proxy rules, then application config.
5. Verify logs show the expected traffic and no unexpected destinations.
6. Record in the audit log.

### Detecting drift

- Weekly comparison of running firewall rules versus `infrastructure/network_policy/`.
- Alert on any denied egress attempt from Z2, Z3, or Z5.
- Alert on any new listening port in a zone.
- Alert on signer process network sockets (should be local only).
- Quarterly isolation test with evidence attached to G6.

### Failure behavior

| Failure | Behavior |
| --- | --- |
| Proxy unavailable | Data-source jobs fail; no direct fallback |
| Chain gateway unavailable | Chain sync pauses; signing disabled |
| mTLS expired | Service calls fail closed; alert |
| Unknown RPC host | Deny + security event |
| Signer unreachable | Transactions fail; no alternate signer |
| Firewall rule missing | Startup self-test fails; deployment blocked |
