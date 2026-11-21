"""Automated unit and integration test suite for Trust & Safety and Economic Clearing/Escrow.

Tests:
1. classify_task_safety against adversarial patterns:
   - Surveillance & Stalking
   - Hazardous Environments
   - Restricted & Sensitive Locations
   - Safe operational requests
2. billing.py ledger and escrow engine:
   - Dynamic dynamic pricing calculations
   - Credit balance tracking and deposits
   - Atomic escrow locking
   - Escrow release upon task completion
   - Escrow refund upon decline, cancellation, or expiration
3. Protocol pipeline integration:
   - Safety rejections return HTTP 400 with status 'rejected_safety_violation'
   - Insufficient credits return status 'rejected_insufficient_credits'
   - Automatic escrow release and refund triggers
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.safety import classify_task_safety, validate_task_safety
from src.billing import (
    estimate_task_cost,
    get_client_balance,
    deposit_client_credits,
    lock_escrow,
    release_escrow,
    refund_escrow,
    get_task_escrow,
    BASE_TASK_COST,
)
from src.db import (
    create_task,
    get_task,
    update_task_status,
    complete_task,
    sweep_expired_tasks,
)
from src.mcp_server import (
    portland_physical_verification,
    request_custom_physical_task,
)
import src.main as main_module


# ==============================================================================
# 1. TRUST & SAFETY INTENT CLASSIFIER UNIT TESTS
# ==============================================================================

class TestSafetyClassifier:
    """Tests for classify_task_safety deterministic heuristic classifier."""

    @pytest.mark.parametrize("location,questions,purpose", [
        (
            "Powell's City of Books, 1005 W Burnside St, Portland, OR",
            ["Is the main entrance accessible?", "Are the posted hours visible?"],
            "Business operating status verification"
        ),
        (
            "Pioneer Courthouse Square, Portland, OR",
            ["Is the weather vane operational?", "Is the visitor center open?"],
            "Public civic asset inspection"
        ),
        (
            "SW 6th & Alder St, Portland, OR",
            ["Are food carts currently active on this block?", "Is seating clear?"],
            "Commercial foot traffic inquiry"
        ),
        (
            "OMSI, 1945 SE Water Ave, Portland, OR",
            ["Is the submarine exhibit open?", "Is public parking full?"],
            "Public cultural institution verification"
        ),
    ])
    def test_benign_tasks_pass(self, location, questions, purpose):
        is_safe, refusal_reason, metadata = classify_task_safety(location, questions, purpose)
        assert is_safe is True
        assert refusal_reason == ""
        assert metadata["violation_category"] is None
        assert metadata["risk_score"] == 0.0

    @pytest.mark.parametrize("location,questions,purpose,violation_kw", [
        (
            "123 Elm St, Portland, OR",
            ["Check the license plate on the silver Toyota", "Photograph license plate #7XYZ89"],
            "Vehicle tracking",
            "license plate"
        ),
        (
            "NW 23rd Ave, Portland, OR",
            ["Find the woman in the yellow jacket and follow her to see where she lives"],
            "Personal inquiry",
            "stalking"
        ),
        (
            "456 Maple St, Portland, OR",
            ["Who is living at this address?", "Identify the resident inside the house"],
            "Identity lookup",
            "identification"
        ),
        (
            "789 Oak St, Portland, OR",
            ["Stakeout the front door and monitor entry and exit of the person"],
            "Personal surveillance",
            "surveillance"
        ),
        (
            "101 Pine St, Portland, OR",
            ["Look through the bedroom window into the private residence"],
            "Residential viewing",
            "window"
        ),
        (
            "202 Cedar St, Portland, OR",
            ["Climb over fence into the residential home backyard"],
            "Property check",
            "backyard"
        ),
    ])
    def test_surveillance_and_stalking_rejections(self, location, questions, purpose, violation_kw):
        is_safe, refusal_reason, metadata = classify_task_safety(location, questions, purpose)
        assert is_safe is False
        assert "Surveillance / Stalking" in refusal_reason
        assert metadata["violation_category"] == "surveillance_stalking"
        assert metadata["risk_score"] >= 0.9

    @pytest.mark.parametrize("location,questions,purpose,violation_kw", [
        (
            "SE Water Ave & Clay St, Portland, OR",
            ["Enter the active construction site and inspect scaffolding without hard hat"],
            "Site check",
            "construction"
        ),
        (
            "NE Columbia Blvd, Portland, OR",
            ["Climb the scaffolding of the communication cell tower"],
            "Tower inspection",
            "scaffolding"
        ),
        (
            "NW St Helens Rd, Portland, OR",
            ["Inspect high-voltage electrical substation power transformer"],
            "Utility check",
            "electrical"
        ),
        (
            "Linnton Industrial Corridor, Portland, OR",
            ["Inspect chemical plant toxic waste storage area"],
            "Industrial check",
            "chemical"
        ),
        (
            "Union Station Railyard, Portland, OR",
            ["Walk on the active train tracks and photograph railroad rails"],
            "Rail check",
            "train tracks"
        ),
        (
            "I-5 Northbound, Portland, OR",
            ["Stand in the freeway median to photograph active traffic lanes"],
            "Traffic count",
            "freeway"
        ),
    ])
    def test_hazardous_environments_rejections(self, location, questions, purpose, violation_kw):
        is_safe, refusal_reason, metadata = classify_task_safety(location, questions, purpose)
        assert is_safe is False
        assert "Hazardous environment" in refusal_reason
        assert metadata["violation_category"] == "hazardous_environment"
        assert metadata["risk_score"] >= 0.9

    @pytest.mark.parametrize("location,questions,purpose,violation_kw", [
        (
            "Lincoln High School, 1750 SW Salmon St, Portland, OR",
            ["Photograph the high school playground with children playing"],
            "School check",
            "school"
        ),
        (
            "Little Sprouts Daycare, Portland, OR",
            ["Observe the kids playing outside the childcare center"],
            "Daycare check",
            "childcare"
        ),
        (
            "Camp Withycombe Military Base, Clackamas, OR",
            ["Photograph perimeter security checkpoint of national guard armory military base"],
            "Facility check",
            "military"
        ),
        (
            "Multnomah County Inverness Jail, Portland, OR",
            ["Photograph the correctional facility detention center perimeter"],
            "Jail check",
            "jail"
        ),
        (
            "Precision Castparts, Portland, OR",
            ["Surveil the defense contractor facility munitions storage depot"],
            "Defense check",
            "defense contractor"
        ),
    ])
    def test_restricted_locations_rejections(self, location, questions, purpose, violation_kw):
        is_safe, refusal_reason, metadata = classify_task_safety(location, questions, purpose)
        assert is_safe is False
        assert "Restricted / Sensitive location" in refusal_reason
        assert metadata["violation_category"] == "restricted_sensitive_location"
        assert metadata["risk_score"] >= 0.9

    def test_validate_task_safety_backward_compatibility(self):
        # Benign check
        safe, err = validate_task_safety(location="1005 W Burnside St, Portland, OR", stated_purpose="Audit")
        assert safe is True
        assert err is None

        # Unsafe check
        safe, err = validate_task_safety(
            location="123 Main St, Portland, OR",
            proposed_action="Track the ex and photograph license plate"
        )
        assert safe is False
        assert "Surveillance" in err


# ==============================================================================
# 2. BILLING & ESCROW ENGINE UNIT TESTS
# ==============================================================================

class TestBillingAndEscrowEngine:
    """Tests for dynamic pricing, client ledgers, and atomic escrow operations."""

    def test_dynamic_pricing_tiers(self):
        # Downtown base standard ($35)
        cost_downtown = estimate_task_cost("1005 W Burnside St, Portland, OR", complexity="standard")
        assert cost_downtown == 35.0

        # Suburban tier (Beaverton) ($35 + $15 = $50)
        cost_beaverton = estimate_task_cost("Central Station, Beaverton, OR", complexity="standard")
        assert cost_beaverton == 50.0

        # Outer metro tier (Gresham / Hillsboro) ($35 + $25 = $60)
        cost_gresham = estimate_task_cost("123 Main St, Gresham, OR", complexity="standard")
        assert cost_gresham == 60.0

        cost_hillsboro = estimate_task_cost("Hillsboro Downtown, Hillsboro, OR", complexity="standard")
        assert cost_hillsboro == 60.0

        # Complexity multipliers
        cost_rush = estimate_task_cost("Pioneer Square, Portland, OR", complexity="rush")
        assert cost_rush == 60.0  # 35 + 25

        cost_custom = estimate_task_cost("Pioneer Square, Portland, OR", complexity="custom")
        assert cost_custom == 50.0  # 35 + 15

        # Outer metro + rush
        cost_outer_rush = estimate_task_cost("Gresham Station, Gresham, OR", complexity="urgent")
        assert cost_outer_rush == 85.0  # 35 + 25 + 25

    @pytest.mark.asyncio
    async def test_client_balance_and_deposits(self, initialized_db):
        client_id = "test_fin_client_01"

        # Initially zero
        bal = await get_client_balance(client_id)
        assert bal == 0.0

        # Deposit credits
        new_bal = await deposit_client_credits(client_id, 100.0)
        assert new_bal == 100.0

        # Verify query matches
        assert await get_client_balance(client_id) == 100.0

        # Additional deposit accumulates
        updated_bal = await deposit_client_credits(client_id, 50.0)
        assert updated_bal == 150.0
        assert await get_client_balance(client_id) == 150.0

        # Negative deposit raises ValueError
        with pytest.raises(ValueError):
            await deposit_client_credits(client_id, -10.0)

    @pytest.mark.asyncio
    async def test_escrow_locking_insufficient_funds(self, initialized_db):
        client_id = "broke_client_01"
        task_id = "task_broke_01"

        # Balance is 0
        success = await lock_escrow(task_id, client_id, 15.0)
        assert success is False
        assert await get_task_escrow(task_id) is None

        # Partial balance (10 < 15)
        await deposit_client_credits(client_id, 10.0)
        success = await lock_escrow(task_id, client_id, 15.0)
        assert success is False
        assert await get_client_balance(client_id) == 10.0

    @pytest.mark.asyncio
    async def test_escrow_lock_release_lifecycle(self, initialized_db):
        client_id = "funded_client_01"
        task_id = "task_lifecycle_01"
        await deposit_client_credits(client_id, 100.0)

        # 1. Lock $25 in escrow
        locked = await lock_escrow(task_id, client_id, 25.0)
        assert locked is True

        # Client balance deducted
        assert await get_client_balance(client_id) == 75.0

        # Escrow record created in 'locked' status
        escrow = await get_task_escrow(task_id)
        assert escrow is not None
        assert escrow["client_id"] == client_id
        assert escrow["amount"] == 25.0
        assert escrow["status"] == "locked"
        assert escrow["operator_id"] is None
        assert escrow["settled_at"] is None

        # Locking same task_id again fails
        assert await lock_escrow(task_id, client_id, 25.0) is False

        # 2. Release escrow to operator
        released = await release_escrow(task_id, operator_id="op_jane_002")
        assert released is True

        # Verify escrow record settled
        escrow = await get_task_escrow(task_id)
        assert escrow["status"] == "released"
        assert escrow["operator_id"] == "op_jane_002"
        assert escrow["settled_at"] is not None

        # Releasing already released escrow returns False
        assert await release_escrow(task_id, operator_id="op_jane_002") is False

    @pytest.mark.asyncio
    async def test_escrow_lock_refund_lifecycle(self, initialized_db):
        client_id = "funded_client_02"
        task_id = "task_refund_01"
        await deposit_client_credits(client_id, 50.0)

        # Lock $20
        locked = await lock_escrow(task_id, client_id, 20.0)
        assert locked is True
        assert await get_client_balance(client_id) == 30.0

        # Refund escrow
        refunded = await refund_escrow(task_id)
        assert refunded is True

        # Balance restored to 50.0
        assert await get_client_balance(client_id) == 50.0

        # Escrow record status updated to 'refunded'
        escrow = await get_task_escrow(task_id)
        assert escrow["status"] == "refunded"
        assert escrow["settled_at"] is not None

        # Refunding again returns False (idempotent protection)
        assert await refund_escrow(task_id) is False
        assert await get_client_balance(client_id) == 50.0


# ==============================================================================
# 3. PROTOCOL PIPELINE & MCP / REST INTEGRATION TESTS
# ==============================================================================

class TestProtocolIntegration:
    """Tests end-to-end safety blocking and economic clearing in MCP & REST API."""

    @pytest.mark.asyncio
    async def test_mcp_safety_violation_rejection(self, initialized_db):
        res = await portland_physical_verification(
            location="123 Oak St, Portland, OR",
            specific_questions=["Check license plate on vehicle parked in driveway"],
            stated_purpose="Surveillance check",
            client_id="test_mcp_client"
        )
        assert res["status"] == "rejected_safety_violation"
        assert "Surveillance / Stalking" in res["error"]
        assert res["safety_metadata"]["violation_category"] == "surveillance_stalking"

    @pytest.mark.asyncio
    async def test_mcp_insufficient_credits_rejection(self, initialized_db):
        # Client has 0 credits
        client_id = "unfunded_mcp_agent"
        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.5, "lon": -122.6}, None)):
            res = await portland_physical_verification(
                location="1005 W Burnside St, Portland, OR",
                specific_questions=["Is the store open?"],
                client_id=client_id
            )
            assert res["status"] == "rejected_insufficient_credits"
            assert "Insufficient credit balance" in res["error"]
            assert res["estimated_cost"] == 35.0
            assert res["current_balance"] == 0.0

    @pytest.mark.asyncio
    async def test_mcp_dispatch_locks_escrow_and_completion_releases(self, initialized_db):
        client_id = "funded_mcp_agent"
        await deposit_client_credits(client_id, 100.0)

        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.5, "lon": -122.6}, None)):
            res = await portland_physical_verification(
                location="1005 W Burnside St, Portland, OR",
                specific_questions=["Is the entrance accessible?"],
                client_id=client_id
            )
            assert res["status"] == "pending_operator_review"
            task_id = res["task_id"]
            assert res["escrow_status"] == "locked"
            assert res["estimated_cost"] == 35.0

            # Client balance reduced from 100 to 65
            assert await get_client_balance(client_id) == 65.0

            # Verify escrow record is locked
            escrow = await get_task_escrow(task_id)
            assert escrow["status"] == "locked"
            assert escrow["amount"] == 35.0

            # Complete task -> auto releases escrow
            await complete_task(
                task_id=task_id,
                photo_url="http://test/proof/pdx_test.jpg",
                photo_metadata={"has_exif": True},
                extracted_answers={"verified": True}
            )

            # Escrow status must now be 'released'
            settled_escrow = await get_task_escrow(task_id)
            assert settled_escrow["status"] == "released"

    @pytest.mark.asyncio
    async def test_mcp_cancellation_auto_refunds_escrow(self, initialized_db):
        client_id = "agent_cancel_refund"
        await deposit_client_credits(client_id, 50.0)

        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.5, "lon": -122.6}, None)):
            res = await portland_physical_verification(
                location="Beaverton, OR",
                specific_questions=["Check storefront"],
                client_id=client_id
            )
            assert res["status"] == "pending_operator_review"
            task_id = res["task_id"]
            cost = res["estimated_cost"]
            assert await get_client_balance(client_id) == 50.0 - cost

            # Operator cancels task
            await update_task_status(task_id, "cancelled_by_operator", decline_reason="Operator unavailable")

            # Escrow must automatically refund
            refunded_escrow = await get_task_escrow(task_id)
            assert refunded_escrow["status"] == "refunded"
            assert await get_client_balance(client_id) == 50.0

    @pytest.mark.asyncio
    async def test_task_expiration_auto_refunds_escrow(self, initialized_db):
        client_id = "agent_expire_refund"
        await deposit_client_credits(client_id, 50.0)

        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.5, "lon": -122.6}, None)):
            res = await portland_physical_verification(
                location="Portland, OR",
                specific_questions=["Check status"],
                client_id=client_id
            )
            task_id = res["task_id"]
            # 50 - 35 = 15.0 remaining
            assert await get_client_balance(client_id) == 15.0

            # Sweep expired tasks
            # Manually backdate expires_at
            import aiosqlite
            from src.config import DB_PATH
            past_iso = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE tasks SET expires_at = ? WHERE task_id = ?", (past_iso, task_id))
                await db.commit()

            swept = await sweep_expired_tasks()
            assert swept == 1

            # Escrow automatically refunded
            escrow = await get_task_escrow(task_id)
            assert escrow["status"] == "refunded"
            assert await get_client_balance(client_id) == 50.0

    def test_rest_api_safety_violation_returns_400(self, client: TestClient):
        payload = {
            "location": "123 Elm St, Portland, OR",
            "specific_questions": ["Check license plate of car parked out front"],
            "stated_purpose": "Stalking individual",
            "client_id": "api_safety_client"
        }
        response = client.post("/v1/dispatch/verify", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "rejected_safety_violation"
        assert "Surveillance / Stalking" in data["error"]

    def test_rest_api_insufficient_credits_rejection(self, client: TestClient):
        payload = {
            "location": "Pioneer Square, Portland, OR",
            "specific_questions": ["Is fountain running?"],
            "client_id": "broke_rest_client"
        }
        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.5, "lon": -122.6}, None)):
            response = client.post("/v1/dispatch/verify", json=payload)
            # Returns 402 Payment Required with rejected_insufficient_credits
            assert response.status_code == 402
            data = response.json()
            assert data["status"] == "rejected_insufficient_credits"
            assert "Insufficient credit balance" in data["error"]
