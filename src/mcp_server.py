"""Model Context Protocol (MCP) Server for Portland Ground-Truth Pilot."""
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from mcp.server.fastmcp import FastMCP

from src.config import OPERATOR_REVIEW_TIMEOUT_MINUTES, FULFILLMENT_TIMEOUT_MINUTES, TASK_EXPIRATION_MINUTES
from src.db import create_task, get_task, log_demand_research, is_operator_available
from src.dedup import compute_idempotency_hash, check_dispatch_eligibility
import src.geofence as geofence
from src.safety import classify_task_safety, validate_task_safety
from src.billing import estimate_task_cost, get_client_balance, lock_escrow, deposit_client_credits
from src.fleet import find_best_operator
from src.telegram_bot import create_telegram_app, send_dispatch_notification
from src.mock import is_mock_mode, trigger_mock_operator

# Initialize FastMCP Server
mcp = FastMCP("portland_ground_truth")

# Shared Telegram App reference for dispatch pushes
_telegram_app = None

def set_telegram_app(app):
    global _telegram_app
    _telegram_app = app

@mcp.tool()
async def portland_physical_verification(
    location: str,
    specific_questions: List[str],
    stated_purpose: Optional[str] = "Physical reality verification",
    client_id: Optional[str] = "agent_client_default"
) -> Dict[str, Any]:
    """
    Dispatches a human field operator in the Portland, OR metropolitan area to verify
    physical ground truth of any real-world location (e.g. checking accessibility,
    verifying posted notices or operating status, inspecting equipment/chargers/infrastructure,
    checking event crowds/lines, or photographing physical assets).
    
    Do NOT use for private residences or general web-searchable queries.
    """
    full_loc = location.strip()
    questions_list = specific_questions or []
    purpose_str = stated_purpose or ""

    # 1. Trust & Safety Intent Classifier check
    is_safe, refusal_reason, safety_meta = classify_task_safety(
        location=full_loc,
        specific_questions=questions_list,
        stated_purpose=purpose_str
    )
    if not is_safe:
        return {
            "status": "rejected_safety_violation",
            "error": refusal_reason,
            "safety_metadata": safety_meta,
            "can_retry": False
        }

    # 2. Check operator availability (pause / off-duty mode)
    if not await is_operator_available() and not is_mock_mode():
        return {
            "status": "rejected_operator_unavailable",
            "error": "GroundTruth Node #001 operator is currently off-duty or paused. Operating hours: 9 AM - 8 PM PST.",
            "can_retry": True
        }

    task_hash = compute_idempotency_hash(client_id, full_loc, "physical_verification")

    # 3. Geofencing check (Portland Metro boundary)
    is_in_bounds, geo_data, geo_error = await geofence.validate_portland_location(full_loc)
    if not is_in_bounds:
        return {
            "status": "rejected_out_of_coverage",
            "error": geo_error,
            "can_retry": False
        }

    # 4. Deduplication and rate limit check
    is_allowed, reason = await check_dispatch_eligibility(client_id, full_loc, task_hash)
    if not is_allowed:
        return {
            "status": "rejected_by_policy",
            "error": reason,
            "can_retry": False
        }

    # 5. Economic Clearing: Balance check
    estimated_cost = estimate_task_cost(full_loc, complexity="standard")
    client_balance = await get_client_balance(client_id)
    if (is_mock_mode() or client_id.startswith("sandbox_")) and client_balance < estimated_cost:
        await deposit_client_credits(client_id, 1000.0)
        client_balance = await get_client_balance(client_id)
    if client_balance < estimated_cost:
        return {
            "status": "rejected_insufficient_credits",
            "error": f"Insufficient credit balance ({client_balance:.2f} credits). Estimated task cost is {estimated_cost:.2f} credits.",
            "estimated_cost": estimated_cost,
            "current_balance": client_balance,
            "can_retry": False
        }

    # 6. Fleet routing: assign optimal available field operator
    assigned_op = None
    try:
        assigned_op = await find_best_operator(geo_data)
    except Exception:
        pass
    operator_id = assigned_op.get("operator_id") if assigned_op else "op_tobias_001"
    zone = assigned_op.get("zone") if assigned_op else "central_portland"

    # 7. Lock Escrow and build task record
    task_id = f"pdx_{uuid.uuid4().hex[:8]}"
    escrow_locked = await lock_escrow(task_id, client_id, estimated_cost)
    if not escrow_locked:
        return {
            "status": "rejected_insufficient_credits",
            "error": f"Failed to lock {estimated_cost:.2f} credits in escrow. Insufficient balance.",
            "can_retry": False
        }

    now = datetime.now(timezone.utc)
    review_expires_at = (now + timedelta(minutes=OPERATOR_REVIEW_TIMEOUT_MINUTES)).isoformat()
    fulfillment_expires_at = (now + timedelta(minutes=FULFILLMENT_TIMEOUT_MINUTES)).isoformat()

    task_payload = {
        "task_id": task_id,
        "idempotency_hash": task_hash,
        "task_type": "physical_verification",
        "client_id": client_id,
        "location": full_loc,
        "specific_questions": specific_questions,
        "stated_purpose": stated_purpose,
        "status": "pending_operator_review",
        "operator_id": operator_id,
        "zone": zone,
        "created_at": now.isoformat(),
        "expires_at": review_expires_at
    }

    # Store task and demand log
    await create_task(task_payload)
    log_demand_research({
        "event": "new_physical_verification_request",
        "task_id": task_id,
        "client_id": client_id,
        "location": full_loc,
        "questions": specific_questions
    })

    # Dispatch to mock operator or Telegram operator
    if is_mock_mode():
        trigger_mock_operator(task_payload)
    else:
        try:
            await send_dispatch_notification(_telegram_app, task_payload)
        except Exception:
            pass

    return {
        "status": "pending_operator_review",
        "task_id": task_id,
        "operator_id": operator_id,
        "operator_assigned": assigned_op.get("name") if assigned_op else "Tobias Node #001",
        "zone": zone,
        "estimated_cost": estimated_cost,
        "escrow_status": "locked",
        "operator_review_deadline": review_expires_at,
        "fulfillment_deadline": fulfillment_expires_at,
        "poll_interval_seconds": 30,
        "instruction": "Verification request dispatched to local Portland operator. Operator has 15 minutes to review and accept. Once accepted, fulfillment window extends to 90 minutes. Poll check_task_status with task_id to track lifecycle and retrieve verified proof."
    }

@mcp.tool()
async def portland_storefront_audit(
    business_name: str,
    address: str,
    specific_questions: List[str],
    stated_purpose: Optional[str] = "Commercial ground truth verification",
    client_id: Optional[str] = "agent_client_default"
) -> Dict[str, Any]:
    """Compatibility alias for portland_physical_verification."""
    full_loc = f"{business_name.strip()}, {address.strip()}"
    return await portland_physical_verification(
        location=full_loc,
        specific_questions=specific_questions,
        stated_purpose=stated_purpose,
        client_id=client_id
    )

@mcp.tool()
async def request_custom_physical_task(
    location: str,
    proposed_action: str,
    stated_purpose: str,
    client_id: Optional[str] = "agent_client_default"
) -> Dict[str, Any]:
    """
    Propose a custom, physical human task in the Portland, OR metro area not covered by standard
    storefront audits. The operator will review your proposal and either accept or decline.
    All custom requests are logged for capability planning.
    """
    # 1. Trust & Safety Intent Classifier check
    is_safe, refusal_reason, safety_meta = classify_task_safety(
        location=location,
        specific_questions=[f"Custom Action: {proposed_action}"],
        stated_purpose=stated_purpose or ""
    )
    if not is_safe:
        return {
            "status": "rejected_safety_violation",
            "error": refusal_reason,
            "safety_metadata": safety_meta,
            "can_retry": False
        }

    # 2. Check operator availability (pause / off-duty mode)
    if not await is_operator_available() and not is_mock_mode():
        return {
            "status": "rejected_operator_unavailable",
            "error": "GroundTruth Node #001 operator is currently off-duty or paused. Operating hours: 9 AM - 8 PM PST.",
            "can_retry": True
        }

    # 3. Geofencing check
    is_in_bounds, geo_data, geo_error = await geofence.validate_portland_location(location)
    if not is_in_bounds:
        return {"status": "rejected_out_of_coverage", "error": geo_error}

    task_hash = compute_idempotency_hash(client_id, location, "custom_task")
    is_allowed, reason = await check_dispatch_eligibility(client_id, location, task_hash)
    if not is_allowed:
        return {"status": "rejected_by_policy", "error": reason}

    # 4. Economic Clearing: Balance check
    estimated_cost = estimate_task_cost(location, complexity="custom")
    client_balance = await get_client_balance(client_id)
    if client_balance < estimated_cost:
        return {
            "status": "rejected_insufficient_credits",
            "error": f"Insufficient credit balance ({client_balance:.2f} credits). Estimated custom task cost is {estimated_cost:.2f} credits.",
            "estimated_cost": estimated_cost,
            "current_balance": client_balance,
            "can_retry": False
        }

    task_id = f"cust_{uuid.uuid4().hex[:8]}"
    escrow_locked = await lock_escrow(task_id, client_id, estimated_cost)
    if not escrow_locked:
        return {
            "status": "rejected_insufficient_credits",
            "error": f"Failed to lock {estimated_cost:.2f} credits in escrow. Insufficient balance.",
            "can_retry": False
        }

    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(minutes=TASK_EXPIRATION_MINUTES)).isoformat()

    task_payload = {
        "task_id": task_id,
        "idempotency_hash": task_hash,
        "task_type": "custom_task_inquiry",
        "client_id": client_id,
        "location": location,
        "specific_questions": [f"Custom Action: {proposed_action}"],
        "stated_purpose": stated_purpose,
        "status": "pending_operator_review",
        "created_at": now.isoformat(),
        "expires_at": expires_at
    }

    await create_task(task_payload)
    log_demand_research({
        "event": "custom_task_inquiry",
        "task_id": task_id,
        "client_id": client_id,
        "location": location,
        "action": proposed_action,
        "purpose": stated_purpose
    })

    if is_mock_mode():
        trigger_mock_operator(task_payload)
    else:
        try:
            await send_dispatch_notification(_telegram_app, task_payload)
        except Exception as e:
            pass

    return {
        "status": "pending_operator_review",
        "task_id": task_id,
        "instruction": "Custom physical task submitted to operator for review. Poll check_task_status with task_id."
    }

@mcp.tool()
async def check_task_status(task_id: str) -> Dict[str, Any]:
    """
    Checks the status of an ongoing or completed physical verification task in Portland.
    Returns status: 'pending_operator_review', 'accepted_in_progress', 'declined', or 'completed'.
    """
    task = await get_task(task_id)
    if not task:
        return {"status": "not_found", "error": f"No task found with ID: {task_id}"}

    res = {
        "task_id": task["task_id"],
        "status": task["status"],
        "location": task["location"],
        "created_at": task["created_at"],
    }

    if task["status"] == "declined":
        res["decline_reason"] = task["decline_reason"]
    elif task["status"] == "completed":
        res["completed_at"] = task["completed_at"]
        res["photo_url"] = task["photo_url"]
        res["extracted_answers"] = task["extracted_answers"]
        res["has_gps_metadata"] = bool(task.get("photo_metadata", {}).get("gps"))

    return res

if __name__ == "__main__":
    mcp.run()
