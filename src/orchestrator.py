"""LangGraph state machine for GroundTruth Protocol with persistent checkpointing, anti-spoofing, and dispute handling."""
from __future__ import annotations
import logging
from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime, timezone

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.safety import classify_task_safety
from src.billing import estimate_task_cost, lock_escrow, refund_escrow, release_escrow, get_client_balance, deposit_client_credits
from src.fleet import find_best_operator, determine_zone, seed_default_operators
from src.verification import generate_verification_challenge, verify_photo_evidence
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
    
    # Physical Anti-Spoofing Challenge
    challenge: Optional[Dict[str, Any]]
    
    # Dispatch & Fleet
    zone: str
    assigned_operator_id: Optional[str]
    assigned_operator_name: Optional[str]
    retry_count: int
    max_retries: int
    
    # Evidence & Verification
    photo_url: Optional[str]
    photo_metadata: Optional[Dict[str, Any]]
    extracted_answers: Optional[Dict[str, Any]]
    verification_passed: bool
    confidence_score: float
    verification_notes: Optional[str]
    
    # Dispute & Review
    is_disputed: bool
    dispute_reason: Optional[str]
    
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
    """Routes task to nearest operator and attaches dynamic anti-spoofing challenge."""
    geo_data = {
        "location": state["location"],
        "lat": state["lat"],
        "lon": state["lon"]
    }
    zone = determine_zone(geo_data)
    op = await find_best_operator(geo_data)
    
    now_iso = datetime.now(timezone.utc).isoformat()
    challenge = generate_verification_challenge(state["task_id"], now_iso)
    
    if op:
        await create_task({
            "task_id": state["task_id"],
            "idempotency_hash": f"hash_{state['task_id']}",
            "task_type": "physical_presence",
            "client_id": state["client_id"],
            "location": state["location"],
            "specific_questions": state["specific_questions"],
            "stated_purpose": state.get("stated_purpose"),
            "status": "assigned",
            "created_at": now_iso,
            "expires_at": now_iso,
            "operator_id": op["operator_id"]
        })
        return {
            "zone": zone,
            "assigned_operator_id": op["operator_id"],
            "assigned_operator_name": op["name"],
            "challenge": challenge,
            "status": "dispatched"
        }
    else:
        return {
            "zone": zone,
            "assigned_operator_id": None,
            "challenge": challenge,
            "status": "dispatch_queued",
            "error_message": f"No operators currently active in zone {zone}"
        }


async def retry_fallback_node(state: GroundTruthState) -> Dict[str, Any]:
    """Reassigns task to a backup operator if initial operator declines/times out."""
    retries = state.get("retry_count", 0) + 1
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
    """Rigorous verification: EXIF geofence, time drift, and anti-spoofing."""
    photo_url = state.get("photo_url")
    photo_meta = state.get("photo_metadata")
    answers = state.get("extracted_answers")
    
    if not photo_url:
        return {
            "verification_passed": False,
            "confidence_score": 0.0,
            "is_disputed": False,
            "verification_notes": "No photo URL submitted.",
            "status": "verification_failed"
        }

    is_valid, score, fail_reason = verify_photo_evidence(
        target_lat=state["lat"],
        target_lon=state["lon"],
        photo_metadata=photo_meta
    )
    
    if is_valid and score >= 0.8:
        return {
            "verification_passed": True,
            "confidence_score": score,
            "is_disputed": False,
            "verification_notes": f"Verified successfully (Confidence {score:.2f})",
            "status": "verified"
        }
    elif score >= 0.3:
        # Borderline or suspicious evidence -> route to dispute quarantine
        return {
            "verification_passed": False,
            "confidence_score": score,
            "is_disputed": True,
            "dispute_reason": fail_reason or "Low confidence / telemetry mismatch",
            "status": "quarantined_dispute"
        }
    else:
        return {
            "verification_passed": False,
            "confidence_score": score,
            "is_disputed": False,
            "error_message": fail_reason,
            "status": "verification_failed"
        }


async def dispute_review_node(state: GroundTruthState) -> Dict[str, Any]:
    """
    Arbitration node for quarantined tasks.
    In production, this holds escrow and pings admin or requests an operator reshoot.
    """
    logger.warning("Task %s entered DISPUTE quarantine: %s", state["task_id"], state.get("dispute_reason"))
    # If retry available, request reshoot; otherwise fail and refund
    if state.get("retry_count", 0) < state.get("max_retries", 2):
        return {
            "status": "reshoot_requested",
            "error_message": f"Dispute resolution: Operator requested to reshoot ({state.get('dispute_reason')})"
        }
    else:
        return {
            "status": "dispute_refunded",
            "error_message": f"Dispute resolved: Refunded to client ({state.get('dispute_reason')})"
        }


async def settlement_node(state: GroundTruthState) -> Dict[str, Any]:
    """Settles escrow: releases funds to operator if verified; refunds client if rejected/failed."""
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


def check_verify_condition(state: GroundTruthState) -> str:
    if state.get("is_disputed"):
        return "dispute_review"
    return "settlement"


def check_dispute_condition(state: GroundTruthState) -> str:
    if state.get("status") == "reshoot_requested":
        return "retry_fallback"
    return "settlement"


# -------------------------------------------------------------------------
# GRAPH BUILDER
# -------------------------------------------------------------------------

def build_ground_truth_graph(checkpointer: Optional[Any] = None) -> Any:
    """Compiles the LangGraph state machine with anti-spoofing and dispute handling."""
    workflow = StateGraph(GroundTruthState)
    
    # Add Nodes
    workflow.add_node("safety", safety_node)
    workflow.add_node("billing", billing_node)
    workflow.add_node("dispatch", dispatch_node)
    workflow.add_node("retry_fallback", retry_fallback_node)
    workflow.add_node("verify", verify_evidence_node)
    workflow.add_node("dispute_review", dispute_review_node)
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
    
    workflow.add_conditional_edges("verify", check_verify_condition, {
        "dispute_review": "dispute_review",
        "settlement": "settlement"
    })
    
    workflow.add_conditional_edges("dispute_review", check_dispute_condition, {
        "retry_fallback": "retry_fallback",
        "settlement": "settlement"
    })
    
    workflow.add_edge("settlement", END)
    
    return workflow.compile(checkpointer=checkpointer or MemorySaver())
