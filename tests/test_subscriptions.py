"""Unit tests for enterprise subscription memberships and quota billing."""
import pytest
from src.billing import (
    subscribe_client, get_client_subscription, lock_escrow,
    get_client_balance, SUBSCRIPTION_PLANS, get_task_escrow
)


@pytest.mark.asyncio
async def test_subscription_creation_and_quota(initialized_db):
    client_id = "acme_cre_firm"
    sub_res = await subscribe_client(client_id, "pro")
    
    assert sub_res["plan"] == "pro"
    assert sub_res["quota_remaining"] == 25
    assert sub_res["status"] == "active"
    
    status = await get_client_subscription(client_id)
    assert status["plan_tier"] == "pro"
    assert status["quota_remaining"] == 25
    assert status["is_active"] is True


@pytest.mark.asyncio
async def test_escrow_deducts_subscription_quota_first(initialized_db):
    client_id = "bot_with_membership"
    # Subscribe to starter (4 audits included, $0 cash balance)
    await subscribe_client(client_id, "starter")
    
    assert await get_client_balance(client_id) == 0.0
    
    # Task requires $35, should succeed using quota
    locked = await lock_escrow("task_sub_001", client_id, 35.0)
    assert locked is True
    
    status = await get_client_subscription(client_id)
    assert status["quota_remaining"] == 3  # 4 - 1 = 3
    assert await get_client_balance(client_id) == 0.0  # Cash balance untouched
    
    escrow = await get_task_escrow("task_sub_001")
    assert escrow["status"] == "locked"
    assert "subscription_quota" in escrow["notes"]
