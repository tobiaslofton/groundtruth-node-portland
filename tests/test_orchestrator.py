"""Unit and lifecycle tests for the LangGraph orchestrator."""
import pytest
from src.orchestrator import build_ground_truth_graph
from src.fleet import seed_default_operators
from src.db import init_db


@pytest.mark.asyncio
async def test_langgraph_happy_path(initialized_db):
    await seed_default_operators()
    
    app = build_ground_truth_graph()
    
    initial_state = {
        "task_id": "task_graph_001",
        "client_id": "client_graph_test",
        "location": "Pioneer Courthouse Square, Portland, OR",
        "lat": 45.5188,
        "lon": -122.6793,
        "specific_questions": ["Is the coffee cart open?"],
        "stated_purpose": "Checking foot traffic for local logistics",
        "is_urgent": False,
        "quoted_price": 0.0,
        "escrow_locked": False,
        "safety_allowed": False,
        "safety_reason": None,
        "zone": "",
        "assigned_operator_id": None,
        "assigned_operator_name": None,
        "retry_count": 0,
        "max_retries": 2,
        "photo_url": "https://groundtruth.local/evidence/photo_001.jpg",
        "extracted_answers": {"coffee_cart": "open"},
        "verification_passed": False,
        "verification_notes": None,
        "status": "pending",
        "error_message": None
    }
    
    config = {"configurable": {"thread_id": "thread_graph_001"}}
    result = await app.ainvoke(initial_state, config=config)
    assert result["safety_allowed"] is True
    assert result["escrow_locked"] is True
    assert result["assigned_operator_id"] is not None
    assert result["verification_passed"] is True
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_langgraph_safety_rejection(initialized_db):
    
    app = build_ground_truth_graph()
    
    hostile_state = {
        "task_id": "task_hostile_001",
        "client_id": "client_adversary",
        "location": "Waterfront Park",
        "lat": 45.5152,
        "lon": -122.6720,
        "specific_questions": ["Follow the woman in the red coat and record license plates."],
        "stated_purpose": "Surveillance",
        "is_urgent": False,
        "quoted_price": 0.0,
        "escrow_locked": False,
        "safety_allowed": False,
        "safety_reason": None,
        "zone": "",
        "assigned_operator_id": None,
        "assigned_operator_name": None,
        "retry_count": 0,
        "max_retries": 2,
        "photo_url": None,
        "extracted_answers": None,
        "verification_passed": False,
        "verification_notes": None,
        "status": "pending",
        "error_message": None
    }
    
    config = {"configurable": {"thread_id": "thread_graph_safety_001"}}
    result = await app.ainvoke(hostile_state, config=config)
    assert result["safety_allowed"] is False
    assert result["status"] == "refunded"

