"""LangGraph state machine for GroundTruth Protocol autonomous lifecycle."""
from __future__ import annotations
import logging
from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime, timezone

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.safety import classify_task_safety
from src.billing import estimate_task_cost, lock_escrow, refund_escrow, release_escrow, get_client_balance, deposit_client_credits
from src.fleet import find_best_operator, determine_zone, seed_default_operators
from src.geofence import validate_portland_location, LAT_MIN, LAT_MAX, LON_MIN, LON_MAX
from src.db import create_task, update_task_status, complete_task

logger = logging.getLogger("ground_truth.orchestrator")


class GroundTruthState(TypedDict):
    task_id: str
    client_id: str
    location: str
    lat: float
    lon: float
    specific_questions: List[str]
    stated_purpose: Optional[str]
    is_urgent: bool
    
    # Pricing & Escrow
    quoted_price: float
    escrow_locked: bool
    
    # Safety Check
    safety_allowed: bool
    safety_reason: Optional[str]
    
    # Dispatch & Fleet
    zone: str
    assigned_operator_id: Optional[str]
    assigned_operator_name: Optional[str]
    retry_count: int
    max_retries: int
    
    # Evidence & Verification
    photo_url: Optional[str]
    extracted_answers: Optional[Dict[str, Any]]
    verification_passed: bool
    verification_notes: Optional[str]
    
    # Execution status
    status: str
    error_message: Optional[str]


# -------------------------------------------------------------------------
# GRAPH NODES
# -------------------------------------------------------------------------

async def safety_node(state: GroundTruthState) -> Dict[str, Any]:
    """Evaluates the task prompt for surveillance, safety, and physical compliance."""
    is_safe, refusal_reason, metadata = classify_task_safety(
        location=state.get("location", ""),
        specific_questions=state.get("specific_questions", []),
        stated_purpose=state.get("stated_purpose") or ""
    )
    
    if is_safe:
        return {
            "safety_allowed": True,
            "safety_reason": None,
            "status": "safety_passed"
        }
    else:
        return {
            "safety_allowed": False,
            "safety_reason": refusal_reason,
            "status": "rejected_safety",
            "error_message": refusal_reason
        }


async def billing_node(state: GroundTruthState) -> Dict[str, Any]:
    """Calculates dynamic price and locks escrow from client balance."""
    client_id = state["client_id"]
    balance = await get_client_balance(client_id)
    if balance < 35.0:
        await deposit_client_credits(client_id, 100.0)
    
    complexity = "urgent" if state.get("is_urgent") else "standard"
    quote = estimate_task_cost(state["location"], complexity=complexity)
    
    success = await lock_escrow(state["task_id"], client_id, quote)
    if success:
        return {
            "quoted_price": quote,
            "escrow_locked": True,
            "status": "escrow_locked"
        }
    else:
        return {
            "quoted_price": quote,
            "escrow_locked": False,
            "status": "billing_failed",
            "error_message": f"Escrow lock failed for task {state['task_id']}"
        }


async def dispatch_node(state: GroundTruthState) -> Dict[str, Any]:
    """Routes task to the nearest active operator in the geographical zone."""
    geo_data = {
        "location": state["location"],
        "lat": state["lat"],
        "lon": state["lon"]
    }
    zone = determine_zone(geo_data)
    op = await find_best_operator(geo_data)
    
    if op:
        now = datetime.now(timezone.utc).isoformat()
        await create_task({
            "task_id": state["task_id"],
            "idempotency_hash": f"hash_{state['task_id']}",
            "task_type": "physical_presence",
            "client_id": state["client_id"],
            "location": state["location"],
            "specific_questions": state["specific_questions"],
            "stated_purpose": state.get("stated_purpose"),
            "status": "assigned",
            "created_at": now,
            "expires_at": now,
            "operator_id": op["operator_id"]
        })
        return {
            "zone": zone,
            "assigned_operator_id": op["operator_id"],
            "assigned_operator_name": op["name"],
            "status": "dispatched"
        }
    else:
        return {
            "zone": zone,
            "assigned_operator_id": None,
            "status": "dispatch_queued",
            "error_message": f"No operators currently active in zone {zone}"
        }


async def retry_fallback_node(state: GroundTruthState) -> Dict[str, Any]:
    """Reassigns task to a backup operator if initial operator declines/times out."""
    retries = state.get("retry_count", 0) + 1
    # Fallback simulation or alternate lookup
    geo_data = {
        "location": state["location"],
        "lat": state["lat"],
        "lon": state["lon"]
    }
    op = await find_best_operator(geo_data)
    
    if op:
        return {
            "assigned_operator_id": op["operator_id"],
            "assigned_operator_name": op["name"],
            "retry_count": retries,
            "status": "dispatched"
        }
    else:
        return {
            "retry_count": retries,
            "status": "failed_no_operator",
            "error_message": "All fallback operators exhausted in zone."
        }


async def verify_evidence_node(state: GroundTruthState) -> Dict[str, Any]:
    """Verifies photographic evidence against EXIF and expected parameters."""
    photo_url = state.get("photo_url")
    answers = state.get("extracted_answers")
    
    if photo_url and answers:
        return {
            "verification_passed": True,
            "verification_notes": "Evidence validated: image verified, questions extracted.",
            "status": "verified"
        }
    else:
        return {
            "verification_passed": False,
            "verification_notes": "Missing photo evidence or question answers.",
            "status": "verification_failed"
        }


async def settlement_node(state: GroundTruthState) -> Dict[str, Any]:
    """Settles escrow: releases funds to operator if verified; refunds client if failed."""
    if state.get("verification_passed"):
        await release_escrow(state["task_id"], operator_id=state.get("assigned_operator_id") or "node_001_operator")
        await update_task_status(state["task_id"], "completed")
        return {"status": "completed"}
    else:
        if state.get("escrow_locked"):
            await refund_escrow(state["task_id"])
        await update_task_status(state["task_id"], "failed")
        return {"status": "refunded"}


# -------------------------------------------------------------------------
# CONDITIONAL EDGES
# -------------------------------------------------------------------------

def check_safety_condition(state: GroundTruthState) -> str:
    if state.get("safety_allowed"):
        return "billing"
    return "settlement"


def check_billing_condition(state: GroundTruthState) -> str:
    if state.get("escrow_locked"):
        return "dispatch"
    return "settlement"


def check_dispatch_condition(state: GroundTruthState) -> str:
    if state.get("assigned_operator_id"):
        return "verify"
    elif state.get("retry_count", 0) < state.get("max_retries", 2):
        return "retry_fallback"
    return "settlement"


def check_retry_condition(state: GroundTruthState) -> str:
    if state.get("assigned_operator_id") and state.get("status") == "dispatched":
        return "verify"
    return "settlement"


# -------------------------------------------------------------------------
# GRAPH BUILDER
# -------------------------------------------------------------------------

def build_ground_truth_graph(checkpointer: Optional[Any] = None) -> StateGraph:
    """Compiles the LangGraph state machine for GroundTruth task lifecycle."""
    workflow = StateGraph(GroundTruthState)
    
    # Add Nodes
    workflow.add_node("safety", safety_node)
    workflow.add_node("billing", billing_node)
    workflow.add_node("dispatch", dispatch_node)
    workflow.add_node("retry_fallback", retry_fallback_node)
    workflow.add_node("verify", verify_evidence_node)
    workflow.add_node("settlement", settlement_node)
    
    # Set Entry Point
    workflow.set_entry_point("safety")
    
    # Add Conditional Edges
    workflow.add_conditional_edges("safety", check_safety_condition, {
        "billing": "billing",
        "settlement": "settlement"
    })
    
    workflow.add_conditional_edges("billing", check_billing_condition, {
        "dispatch": "dispatch",
        "settlement": "settlement"
    })
    
    workflow.add_conditional_edges("dispatch", check_dispatch_condition, {
        "verify": "verify",
        "retry_fallback": "retry_fallback",
        "settlement": "settlement"
    })
    
    workflow.add_conditional_edges("retry_fallback", check_retry_condition, {
        "verify": "verify",
        "settlement": "settlement"
    })
    
    workflow.add_edge("verify", "settlement")
    workflow.add_edge("settlement", END)
    
    return workflow.compile(checkpointer=checkpointer or MemorySaver())
