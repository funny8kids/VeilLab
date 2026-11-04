from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..amounts import format_wei, parse_amount_to_wei
from ..config import Settings
from ..deps import (
    get_db,
    get_request_id,
    get_settings,
    require_idempotency_key,
)
from ..errors import ApiError
from ..ids import new_id
from ..models import ComplianceCheck, DepositIntent, Pool, iso_z, utcnow
from ..presenters import deposit_view
from ..schemas import DepositIntentRequest, MockDepositRequest
from ..services.audit import append_audit
from ..services.compliance import (
    compliance_view,
    require_allowed,
    screen_action,
)
from ..services.idempotency import check_replay, remember, replay
from ..services.mock_chain import MockChain

router = APIRouter(tags=["deposits"])


def _get_pool(db: Session, pool_id: str) -> Pool:
    pool = db.get(Pool, pool_id)
    if pool is None:
        raise ApiError(404, "POOL_NOT_FOUND", "Unknown pool id.")
    return pool


@router.post("/deposits/intent")
def create_deposit_intent(
    body: DepositIntentRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    idempotency_key: str = Depends(require_idempotency_key),
):
    payload = body.model_dump(mode="json")
    stored = check_replay(
        db, scope="deposit:intent", key=idempotency_key, payload=payload
    )
    if stored is not None:
        return replay(stored)

    pool = _get_pool(db, body.pool_id)
    if pool.status == "paused":
        raise ApiError(409, "POOL_PAUSED", "This pool is paused.")
    if pool.status == "retired":
        raise ApiError(409, "POOL_RETIRED", "This pool is retired.")

    try:
        amount_wei = parse_amount_to_wei(body.amount, pool.asset_decimals)
    except ValueError as exc:
        raise ApiError(422, "INVALID_AMOUNT", str(exc)) from exc
    if amount_wei != pool.denomination_wei:
        denomination = format_wei(pool.denomination_wei, pool.asset_decimals)
        raise ApiError(
            422,
            "AMOUNT_MISMATCH",
            f"Deposit amount must equal the pool denomination exactly ({denomination}).",
        )

    intent_id = new_id("dep")
    check = screen_action(
        db,
        settings,
        subject_type="deposit",
        subject_ref=intent_id,
        address=body.depositor_address,
        pool=pool,
        amount_wei=amount_wei,
        request_id=request_id,
    )

    if check.decision == "block":
        db.commit()
        raise ApiError(
            403,
            "COMPLIANCE_BLOCKED",
            "The depositor address was blocked by the mock compliance policy.",
            extra={
                "check_id": check.id,
                "decision": "block",
                "reasons": list(check.reasons or []),
                "policy_version": check.policy_version,
            },
        )

    if check.decision == "review":
        db.commit()
        review_body = {
            "code": "COMPLIANCE_REVIEW",
            "decision": "review",
            "review_id": check.id,
            "check_id": check.id,
            "compliance": compliance_view(check),
            "expires_at": iso_z(check.expires_at),
            "mock": settings.mode == "mock",
        }
        if settings.mode == "local":
            review_body.update(
                {
                    "local_chain": True,
                    "warning": (
                        "Manual review is required. No local deposit "
                        "transaction has been prepared or sent."
                    ),
                }
            )
        return JSONResponse(status_code=202, content=review_body)

    expires_at = utcnow() + timedelta(seconds=settings.intent_ttl_seconds)
    if check.expires_at is not None and check.expires_at < expires_at:
        expires_at = check.expires_at

    intent = DepositIntent(
        id=intent_id,
        pool_id=pool.id,
        address_hash=check.address_hash or "",
        amount_wei=amount_wei,
        commitment=body.commitment.lower() if body.commitment else None,
        compliance_check_id=check.id,
        status="pending",
        expires_at=expires_at,
    )
    db.add(intent)
    append_audit(
        db,
        action="deposit.intent.created",
        resource_type="deposit_intent",
        resource_id=intent.id,
        actor_type="client",
        decision="allow",
        request_id=request_id,
        metadata={
            "pool_id": pool.id,
            "amount_wei": str(amount_wei),
            "check_id": check.id,
            "mock": settings.mode == "mock",
            "local_chain": settings.mode == "local",
        },
    )

    response = {
        "intent_id": intent.id,
        "pool_id": pool.id,
        "commitment": intent.commitment,
        "compliance": compliance_view(check),
        "deposit_contract": pool.contract_address,
        "denomination_wei": str(pool.denomination_wei),
        "protocol_fee_bps": pool.protocol_fee_bps,
        "expires_at": iso_z(expires_at),
        "mock": settings.mode == "mock",
    }
    if settings.mode == "local":
        response.update(
            {
                "local_chain": True,
                "chain_source": "indexer",
                "next_step": "POST /api/v1/local/deposits",
                "warning": (
                    "Deposit intent only: no deposit is complete until the "
                    "local Anvil transaction is confirmed by the indexer."
                ),
            }
        )
    else:
        response["mock_chain"] = "MOCK_CHAIN"
    remember(
        db,
        scope="deposit:intent",
        key=idempotency_key,
        payload=payload,
        status_code=200,
        response=response,
        resource_type="deposit_intent",
        resource_id=intent.id,
    )
    db.commit()
    return response


@router.post("/mock/deposits", status_code=201)
@router.post("/deposits/mock", status_code=201, include_in_schema=False)
def mock_deposit(
    body: MockDepositRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    if settings.mode != "mock":
        raise ApiError(
            404, "MOCK_ONLY", "The mock deposit endpoint is only available in mock mode."
        )

    intent = db.get(DepositIntent, body.intent_id)
    if intent is None:
        raise ApiError(404, "INTENT_NOT_FOUND", "Unknown deposit intent id.")
    pool = _get_pool(db, intent.pool_id)

    if pool.status != "active":
        raise ApiError(409, "POOL_PAUSED", "This pool is not active.")

    if intent.status == "consumed":
        raise ApiError(
            409, "INTENT_CONSUMED", "This deposit intent has already been consumed."
        )
    if intent.status in {"expired", "blocked"}:
        raise ApiError(409, "INTENT_EXPIRED", "This deposit intent is no longer usable.")
    if intent.expires_at <= utcnow():
        intent.status = "expired"
        db.commit()
        raise ApiError(409, "INTENT_EXPIRED", "This deposit intent has expired.")

    if intent.commitment is not None and intent.commitment.lower() != body.commitment.lower():
        raise ApiError(
            422,
            "COMMITMENT_MISMATCH",
            "The commitment does not match the deposit intent.",
        )

    check = db.get(ComplianceCheck, intent.compliance_check_id)
    try:
        require_allowed(check, expected_amount_wei=pool.denomination_wei)
    except ApiError as exc:
        if exc.code == "COMPLIANCE_EXPIRED":
            intent.status = "expired"
            db.commit()
        raise

    chain = MockChain(db, settings)
    deposit = chain.record_deposit(
        pool=pool,
        intent=intent,
        commitment=body.commitment.lower(),
        tx_hash=body.tx_hash.lower() if body.tx_hash else None,
        request_id=request_id,
    )
    db.commit()
    result = deposit_view(db, deposit, pool.chain_id)
    result["mock_chain"] = "MOCK_CHAIN"
    return result
