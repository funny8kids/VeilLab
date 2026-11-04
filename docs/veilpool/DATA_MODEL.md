# VeilPool Data Model

**Status:** Current · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [Architecture](ARCHITECTURE.md) · [Compliance](COMPLIANCE.md) · [API Spec](API_SPEC.md)

---

## 1. Core rule

> **Notes are never stored server-side.**

There is no `notes` table, no note column, no note in logs, no note in support tickets and no
note in analytics. The client vault is the only place a note exists at rest.

The server stores public chain facts (commitments, nullifiers, deposits, withdrawals),
compliance decisions and audit records.

---

## 2. PostgreSQL schema

Schema: `veilpool`.

### 2.1 Pools

```sql
CREATE TABLE veilpool.pools (
    id                  text PRIMARY KEY,             -- pool_eth_01
    chain_id            integer NOT NULL,
    asset_symbol        text NOT NULL,
    asset_decimals      smallint NOT NULL,
    denomination_wei    numeric(78,0) NOT NULL,
    tree_depth          smallint NOT NULL,
    maturity_seconds    integer NOT NULL,
    protocol_fee_bps    integer NOT NULL,
    contract_address    text NOT NULL,
    verifier_address    text NOT NULL,
    status              text NOT NULL CHECK (status IN ('active','paused','retired')),
    min_set_size        integer NOT NULL DEFAULT 100,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (chain_id, asset_symbol, denomination_wei)
);
```

### 2.2 Deposits

```sql
CREATE TABLE veilpool.deposits (
    id                  text PRIMARY KEY,             -- dep_<ULID>
    pool_id             text NOT NULL REFERENCES veilpool.pools(id),
    commitment          text NOT NULL,
    leaf_index          bigint NOT NULL,
    tx_hash             text NOT NULL,
    block_number        bigint NOT NULL,
    block_hash          text NOT NULL,
    log_index           integer NOT NULL,
    depositor_address   text,                         -- compliance-only, access-controlled
    compliance_check_id text,
    status              text NOT NULL CHECK (status IN ('pending','confirmed','reorged')),
    is_canonical        boolean NOT NULL DEFAULT true,
    confirmed_at        timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_deposits_canonical_event
    ON veilpool.deposits (tx_hash, log_index)
    WHERE is_canonical;
CREATE UNIQUE INDEX uq_deposits_canonical_leaf
    ON veilpool.deposits (pool_id, leaf_index)
    WHERE is_canonical;

CREATE INDEX ix_deposits_pool_block ON veilpool.deposits (pool_id, block_number DESC);
CREATE INDEX ix_deposits_commitment ON veilpool.deposits (commitment);
```

Notes:

- `commitment` is public via the deposit event.
- `depositor_address` is stored only if compliance requires it; access is restricted and
  audited. It is not linked to the note by the server.
- `status = reorged` rows are retained for audit but excluded from the canonical tree.

### 2.2.1 Deposit intents

```sql
CREATE TABLE veilpool.deposit_intents (
    id                  text PRIMARY KEY,             -- dep_<ULID>
    pool_id             text NOT NULL REFERENCES veilpool.pools(id),
    address_hash        text NOT NULL,
    amount_wei          numeric(78,0) NOT NULL,
    compliance_check_id text,
    status              text NOT NULL CHECK (status IN ('pending','consumed','expired','blocked')),
    expires_at          timestamptz NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_deposit_intents_expiry ON veilpool.deposit_intents (expires_at)
    WHERE status = 'pending';
```

Intents are short-lived and idempotent. They do not contain a note; the commitment is created
client-side and only appears on-chain.

### 2.2.2 Local deposit broadcasts (MVP dev-only)

The local Anvil bridge uses an additional table so a retried request cannot send a second
transaction:

```sql
CREATE TABLE veilpool.local_deposit_broadcasts (
    intent_id     text PRIMARY KEY REFERENCES veilpool.deposit_intents(id),
    tx_hash       text NOT NULL,
    commitment    text NOT NULL,
    block_number  bigint,
    created_at    timestamptz NOT NULL DEFAULT now()
);
```

This table contains only public transaction data. It is a local-development idempotency guard,
not a custody or relayer record. The API never accepts or stores a private key.

### 2.3 Withdrawals

```sql
CREATE TABLE veilpool.withdrawals (
    id                  text PRIMARY KEY,             -- wdr_<ULID>
    pool_id             text NOT NULL REFERENCES veilpool.pools(id),
    nullifier_hash      text NOT NULL,
    recipient_address   text,                         -- compliance-only, access-controlled
    relayer_id          text REFERENCES veilpool.relayers(id),
    tx_hash             text,
    block_number        bigint,
    block_hash          text,
    log_index           integer,
    protocol_fee_wei    numeric(78,0) NOT NULL,
    relayer_fee_wei     numeric(78,0) NOT NULL,
    gas_cost_wei        numeric(78,0),
    compliance_check_id text,
    status              text NOT NULL CHECK (status IN ('proof_ready','submitted','confirmed','failed','reorged')),
    is_canonical        boolean NOT NULL DEFAULT true,
    failure_code        text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    confirmed_at        timestamptz
);

CREATE UNIQUE INDEX uq_withdrawals_canonical_nullifier
    ON veilpool.withdrawals (pool_id, nullifier_hash)
    WHERE is_canonical;
CREATE UNIQUE INDEX uq_withdrawals_canonical_event
    ON veilpool.withdrawals (tx_hash, log_index)
    WHERE is_canonical;

CREATE INDEX ix_withdrawals_pool_block ON veilpool.withdrawals (pool_id, block_number DESC);
CREATE INDEX ix_withdrawals_status ON veilpool.withdrawals (status, created_at);
```

Notes:

- `nullifier_hash` is public on-chain; uniqueness is the double-spend guard **for canonical
  rows only**.
- `recipient_address` is stored for compliance; access is restricted and audited.
- A `failed` withdrawal does not consume the note unless the nullifier is on-chain.
- A `reorged` row is retained for audit but excluded from canonical uniqueness and from the
  active nullifier set.

### 2.4 Nullifiers

```sql
CREATE TABLE veilpool.nullifiers (
    pool_id         text NOT NULL REFERENCES veilpool.pools(id),
    nullifier_hash  text NOT NULL,
    withdrawal_id   text NOT NULL REFERENCES veilpool.withdrawals(id),
    block_number    bigint NOT NULL,
    spent_at        timestamptz NOT NULL,
    PRIMARY KEY (pool_id, nullifier_hash)
);
```

This table is a projection of on-chain canonical state. It can be rebuilt from events. On a
reorg, nullifiers above the common ancestor are removed before replaying canonical blocks.

### 2.5 Relayers

```sql
CREATE TABLE veilpool.relayers (
    id              text PRIMARY KEY,                 -- rel_01
    name            text NOT NULL,
    endpoint        text NOT NULL,
    fee_bps         integer NOT NULL,
    supported_pools text[] NOT NULL,
    status          text NOT NULL CHECK (status IN ('online','degraded','offline','disabled')),
    uptime_bps      integer NOT NULL DEFAULT 0,
    last_heartbeat  timestamptz,
    compliance_status text NOT NULL DEFAULT 'pending',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE veilpool.relayer_submissions (
    id              text PRIMARY KEY,                 -- rsub_<ULID>
    withdrawal_id   text NOT NULL REFERENCES veilpool.withdrawals(id),
    relayer_id      text NOT NULL REFERENCES veilpool.relayers(id),
    request_hash    text NOT NULL,
    quote_hash      text NOT NULL,
    status          text NOT NULL CHECK (status IN ('received','accepted','rejected','submitted','confirmed','failed')),
    latency_ms      integer,
    error_code      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
```

### 2.6 Compliance

```sql
CREATE TABLE veilpool.compliance_policies (
    version             integer PRIMARY KEY,
    sanctions_source    text NOT NULL,
    sanctions_version   text NOT NULL,
    blocked_jurisdictions text[] NOT NULL,
    daily_deposit_limit   numeric(78,0) NOT NULL,
    daily_withdraw_limit  numeric(78,0) NOT NULL,
    per_tx_limit          numeric(78,0) NOT NULL,
    review_required       boolean NOT NULL DEFAULT true,
    effective_at          timestamptz NOT NULL
);

CREATE TABLE veilpool.compliance_checks (
    id              text PRIMARY KEY,                 -- cmp_<ULID>
    subject_type    text NOT NULL CHECK (subject_type IN ('deposit','withdrawal','relayer')),
    subject_ref     text NOT NULL,
    address_hash    text,                             -- hash, not raw where possible
    pool_id         text,
    amount_wei      numeric(78,0),
    provider        text NOT NULL,
    policy_version  integer NOT NULL,
    decision        text NOT NULL CHECK (decision IN ('allow','review','block')),
    risk_score      integer,
    reasons         jsonb NOT NULL DEFAULT '[]',
    reviewed_by     text,
    reviewed_at     timestamptz,
    expires_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_compliance_review ON veilpool.compliance_checks (decision, created_at)
    WHERE decision = 'review';
```

### 2.7 Indexer and audit

```sql
CREATE TABLE veilpool.indexer_cursors (
    chain_id        integer NOT NULL,
    stream          text NOT NULL,
    last_block      bigint NOT NULL,
    last_hash       text NOT NULL,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chain_id, stream)
);

CREATE TABLE veilpool.reorg_events (
    id              text PRIMARY KEY,
    chain_id        integer NOT NULL,
    from_block      bigint NOT NULL,
    to_block        bigint NOT NULL,
    orphaned_hashes text[] NOT NULL,
    detected_at     timestamptz NOT NULL,
    resolved_at     timestamptz
);

CREATE TABLE veilpool.audit_log (
    id              text PRIMARY KEY,
    occurred_at     timestamptz NOT NULL,
    actor_type      text NOT NULL,
    actor_id        text,
    action          text NOT NULL,
    resource_type   text NOT NULL,
    resource_id     text,
    project_id      text,
    decision        text,
    reason          text,
    request_id      text,
    trace_id        text,
    metadata        jsonb NOT NULL DEFAULT '{}',
    prev_hash       text,
    hash            text NOT NULL
);
```

Audit is append-only. Application roles have `INSERT`/`SELECT`, no `UPDATE`/`DELETE`.
A daily hash anchor goes to WORM storage.

---

## 3. What is not stored

| Data | Where it lives | Why |
| --- | --- | --- |
| Secret note | Client encrypted vault | The note is the withdrawal credential |
| Note passphrase | Client / user | Never sent to server |
| Raw proof input | Client (memory) | Could reveal note |
| Wallet private key | Wallet | Never touches VeilPool |
| Plaintext sanctions evidence | Compliance store, restricted | Legal/audit |
| Raw prompts (if any AI tooling) | Not part of the mixer | Out of scope |

---

## 4. Data classification

| Class | Examples | Controls |
| --- | --- | --- |
| Public | Pools, commitments, nullifiers, tx hashes | Integrity |
| Internal | Pool config, relayer metrics, indexer cursors | Auth |
| Confidential | Compliance decisions, recipient/depositor addresses | Need-to-know, encryption, audit |
| Restricted | Sanctions evidence, audit anchors | Isolated, encrypted, WORM |

Notes are **client-restricted**; the server has no class for them because it never receives
them.

---

## 5. Retention

| Data | Retention |
| --- | --- |
| Pool config | Life of deployment |
| Deposits/withdrawals (public chain facts) | 2 years, then archive |
| Nullifiers | Life of pool + 2 years |
| Compliance checks | 5 years |
| Audit log | 2 years active, 7 years cold |
| Relayer metrics | 1 year |
| Indexer cursors | Life of deployment |
| Reorg events | 2 years |
| Client notes | User-controlled; deleted when user deletes vault |
| Support tickets | 1 year; never include notes |

---

## 6. Tenant and access rules

- v1 is single-operator; `project_id` is reserved for future multi-tenant.
- API roles: `veilpool_api`, `veilpool_indexer`, `veilpool_compliance`, `veilpool_relayer_gateway`.
- The indexer can write deposits/withdrawals/nullifiers; it cannot read compliance raw data.
- The compliance service can read/write compliance tables; it cannot mutate pool balances.
- The relayer gateway can read relayer config and write submissions; it cannot read notes
  (none exist) or private compliance evidence.
- Admin actions require an audited human role.

---

## 7. Integrity invariants

1. `(pool_id, leaf_index)` unique only for canonical deposits.
2. `(tx_hash, log_index)` unique only for canonical deposits and withdrawals.
3. `(pool_id, nullifier_hash)` unique only for canonical withdrawals.
4. A withdrawal row cannot be `confirmed` without a tx hash and block.
5. A nullifier row cannot exist without a confirmed canonical withdrawal.
6. A deposit marked `reorged` is excluded from tree rebuilds.
7. A compliance block cannot be overridden without an audit record.
8. No table contains a note or note-like secret.
9. A pool balance check must match `deposits - withdrawals - fees`.
10. Audit hash chain verifies.
11. A reorged nullifier can be re-spent by a canonical withdrawal; the old row stays
    non-canonical.
12. A reorged deposit leaf can be reused by a canonical deposit at the same index.
13. A deposit intent is single-use and expires; an expired intent cannot authorize a deposit.

---

## 8. Open data questions

- Raw address retention vs. hash-only compliance: legal review required.
- Whether to store depositor addresses at all, or only risk decisions.
- Sanctions evidence retention and access control.
- Whether activity history should be local-only (preferred) or account-backed.
- Multi-tenant project scoping in v2.
