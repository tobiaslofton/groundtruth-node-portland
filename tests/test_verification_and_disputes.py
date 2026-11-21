"""Comprehensive tests for anti-spoofing, dispute quarantine, and SQLite persistence."""
import pytest
from src.orchestrator import build_ground_truth_graph
from src.fleet import seed_default_operators
from src.verification import generate_verification_challenge, verify_photo_evidence


def test_verification_challenge_generation():
    challenge = generate_verification_challenge("task_test_123", "2026-11-20T17:00:00Z")
    assert "instruction" in challenge
    assert len(challenge["challenge_id"]) == 6
    assert challenge["requires_physical_token"] is True


def test_anti_spoofing_distance_rejection():
    # Target downtown Portland
    target_lat, target_lon = 45.5188, -122.6793
    # Photo taken 5 km away
    spoofed_meta = {
        "lat": 45.4800,
        "lon": -122.7500,
        "timestamp": "2026-11-20T17:00:00Z"
    }
    is_valid, score, reason = verify_photo_evidence(target_lat, target_lon, spoofed_meta)
    assert is_valid is False
    assert "exceeds" in reason
    assert score < 0.5


def test_anti_spoofing_tampered_software():
    target_lat, target_lon = 45.5188, -122.6793
    photoshop_meta = {
        "lat": target_lat,
        "lon": target_lon,
        "software": "Adobe Photoshop 2026"
    }
    is_valid, score, reason = verify_photo_evidence(target_lat, target_lon, photoshop_meta)
    assert is_valid is False
    assert "desktop software" in reason.lower() or "quarantined" in reason.lower()


@pytest.mark.asyncio
async def test_langgraph_dispute_quarantine_flow(initialized_db):
    await seed_default_operators()
    app = build_ground_truth_graph()
    
    # Target downtown Portland, photo 600m away (triggers dispute quarantine score >= 0.3, < 0.8)
    disputed_state = {
        "task_id": "task_dispute_001",
        "client_id": "client_dispute_test",
        "location": "Pioneer Courthouse Square, Portland, OR",
        "lat": 45.5188,
        "lon": -122.6793,
        "specific_questions": ["Is the food cart open?"],
        "stated_purpose": "Logistics verification",
        "is_urgent": False,
        "quoted_price": 0.0,
        "escrow_locked": False,
        "safety_allowed": False,
        "safety_reason": None,
        "challenge": None,
        "zone": "",
        "assigned_operator_id": None,
        "assigned_operator_name": None,
        "retry_count": 0,
        "max_retries": 2,
        "photo_url": "https://groundtruth.local/evidence/dispute_shot.jpg",
        "photo_metadata": {
            "lat": 45.5138,  # ~550m away
            "lon": -122.6793,
            "timestamp": "2026-11-20T17:00:00Z"
        },
        "extracted_answers": {"cart": "open"},
        "verification_passed": False,
        "confidence_score": 0.0,
        "verification_notes": None,
        "is_disputed": False,
        "dispute_reason": None,
        "status": "pending",
        "error_message": None
    }
    
    config = {"configurable": {"thread_id": "thread_dispute_001"}}
    result = await app.ainvoke(disputed_state, config=config)
    assert result["is_disputed"] is True
    # The dispute review caught it and either requested reshoot or settled as refunded
    assert result["status"] in ("reshoot_requested", "refunded", "dispute_refunded")


@pytest.mark.asyncio
async def test_langgraph_valid_evidence_settlement(initialized_db):
    await seed_default_operators()
    app = build_ground_truth_graph()
    
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    valid_state = {
        "task_id": "task_valid_001",
        "client_id": "client_valid_test",
        "location": "Pioneer Courthouse Square, Portland, OR",
        "lat": 45.5188,
        "lon": -122.6793,
        "specific_questions": ["Is the food cart open?"],
        "stated_purpose": "Logistics verification",
        "is_urgent": False,
        "quoted_price": 0.0,
        "escrow_locked": False,
        "safety_allowed": False,
        "safety_reason": None,
        "challenge": None,
        "zone": "",
        "assigned_operator_id": None,
        "assigned_operator_name": None,
        "retry_count": 0,
        "max_retries": 2,
        "photo_url": "https://groundtruth.local/evidence/valid_shot.jpg",
        "photo_metadata": {
            "lat": 45.5188,
            "lon": -122.6793,
            "timestamp": now_iso,
            "mock": True
        },
        "extracted_answers": {"cart": "open"},
        "verification_passed": False,
        "confidence_score": 0.0,
        "verification_notes": None,
        "is_disputed": False,
        "dispute_reason": None,
        "status": "pending",
        "error_message": None
    }
    
    config = {"configurable": {"thread_id": "thread_valid_001"}}
    result = await app.ainvoke(valid_state, config=config)
    assert result["verification_passed"] is True
    assert result["status"] == "completed"
    assert result["challenge"] is not None
