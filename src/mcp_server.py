"""Model Context Protocol (MCP) Server for Portland Ground-Truth Pilot."""
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from mcp.server.fastmcp import FastMCP

from src.config import TASK_EXPIRATION_MINUTES
from src.db import create_task, get_task, log_demand_research
from src.dedup import compute_idempotency_hash, check_dispatch_eligibility
from src.geofence import validate_portland_location
from src.telegram_bot import create_telegram_app, send_dispatch_notification

# Initialize FastMCP Server
mcp = FastMCP("portland_ground_truth")

# Shared Telegram App reference for dispatch pushes
_telegram_app = None

def set_telegram_app(app):
    global _telegram_app
    _telegram_app = app

@mcp.tool()
async def portland_storefront_audit(
    business_name: str,
    address: str,
    specific_questions: List[str],
    stated_purpose: Optional[str] = "Commercial ground truth verification",
    client_id: Optional[str] = "agent_client_default"
) -> Dict[str, Any]:
    """
    Dispatches a human field inspector in the Portland, OR metropolitan area to verify
    physical ground truth of a commercial storefront or building (e.g. checking if open,
    verifying posted hours, photographing lease/eviction notices, checking retail stock).
    
    Do NOT use for private residences or general web-searchable queries.
    """
    full_loc = f"{business_name.strip()}, {address.strip()}"
    task_hash = compute_idempotency_hash(client_id, full_loc, "storefront_audit")

    # 1. Geofencing check (Portland Metro boundary)
    is_in_bounds, geo_data, geo_error = await validate_portland_location(full_loc)
    if not is_in_bounds:
        return {
            "status": "rejected_out_of_coverage",
            "error": geo_error,
            "can_retry": False
        }

    # 2. Deduplication and rate limit check
    is_allowed, reason = await check_dispatch_eligibility(client_id, full_loc, task_hash)
    if not is_allowed:
        return {
            "status": "rejected_by_policy",
            "error": reason,
            "can_retry": False
        }

    # 3. Build task record
    task_id = f"pdx_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(minutes=TASK_EXPIRATION_MINUTES)).isoformat()

    task_payload = {
        "task_id": task_id,
        "idempotency_hash": task_hash,
        "task_type": "storefront_audit",
        "client_id": client_id,
        "location": full_loc,
        "specific_questions": specific_questions,
        "stated_purpose": stated_purpose,
        "status": "pending_operator_review",
        "created_at": now.isoformat(),
        "expires_at": expires_at
    }

    # 3. Store task and demand log
    await create_task(task_payload)
    log_demand_research({
        "event": "new_storefront_audit_request",
        "task_id": task_id,
        "client_id": client_id,
        "location": full_loc,
        "questions": specific_questions
    })

    # 4. Push alert to Telegram operator
    if _telegram_app:
        try:
            await send_dispatch_notification(_telegram_app, task_payload)
        except Exception as e:
            pass

    return {
        "status": "pending_operator_review",
        "task_id": task_id,
        "expires_at": expires_at,
        "poll_interval_seconds": 30,
        "instruction": "Verification request dispatched to local Portland operator. Poll check_task_status with task_id to retrieve proof and answers."
    }

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
    # 1. Geofencing check
    is_in_bounds, geo_data, geo_error = await validate_portland_location(location)
    if not is_in_bounds:
        return {"status": "rejected_out_of_coverage", "error": geo_error}

    task_hash = compute_idempotency_hash(client_id, location, "custom_task")
    is_allowed, reason = await check_dispatch_eligibility(client_id, location, task_hash)
    if not is_allowed:
        return {"status": "rejected_by_policy", "error": reason}

    task_id = f"cust_{uuid.uuid4().hex[:8]}"
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

    if _telegram_app:
        try:
            await send_dispatch_notification(_telegram_app, task_payload)
        except Exception:
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
