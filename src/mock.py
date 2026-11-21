"""Offline Developer Mock Runner for Portland Ground-Truth Pilot.

Allows external developers and agents to run a complete physical verification
loop locally in ~3-5 seconds without API keys, Telegram credentials, or external network.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from PIL import Image, ImageDraw, ImageFont

from src.config import PROOF_DIR, BASE_PUBLIC_URL, MOCK_OPERATOR_MODE
from src.db import update_task_status, complete_task

logger = logging.getLogger("ground_truth.mock")

# Keep strong references to background asyncio tasks to prevent garbage collection
_active_mock_tasks: Set[asyncio.Task] = set()

def is_mock_mode() -> bool:
    """Return True if offline developer mock operator mode is enabled."""
    return MOCK_OPERATOR_MODE or os.getenv("MOCK_OPERATOR_MODE", "false").lower() in ("true", "1", "yes")

def generate_mock_proof_image(
    file_path: Path, 
    task_id: str, 
    location: str, 
    questions: Optional[List[str]] = None
) -> Path:
    """
    Generate a clean mock physical verification placard image with timestamp and location.
    Saves the image to file_path as a JPEG.
    """
    width, height = 800, 600
    # Background matching GroundTruth theme: deep void #06090e
    img = Image.new("RGB", (width, height), color=(6, 9, 14))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Outer border: sky blue #38bdf8
    draw.rectangle([(16, 16), (width - 16, height - 16)], outline=(56, 189, 248), width=3)
    # Inner subtle border: slate #1e293b
    draw.rectangle([(24, 24), (width - 24, height - 24)], outline=(30, 41, 59), width=1)

    # Header
    draw.text((40, 36), "GROUNDTRUTH PROTOCOL - NODE #001 (PORTLAND, OR)", fill=(56, 189, 248), font=font)
    draw.text((40, 56), "OFFLINE DEVELOPER MOCK FIELD VERIFICATION PLACARD", fill=(148, 163, 184), font=font)

    # Divider
    draw.line([(40, 80), (width - 40, 80)], fill=(30, 41, 59), width=2)

    # Core metadata
    now_iso = datetime.now(timezone.utc).isoformat()
    y = 100
    items = [
        ("TASK ID:", task_id, (52, 211, 153)),
        ("TARGET LOCATION:", location, (241, 245, 249)),
        ("SIMULATED AT:", now_iso, (148, 163, 184)),
        ("VERIFICATION STATUS:", "ON-SITE INSPECTION CONFIRMED", (52, 211, 153)),
        ("COORDINATES:", "45.5231 N, 122.6816 W (Portland Metro)", (148, 163, 184))
    ]

    for label, val, color in items:
        draw.text((40, y), label, fill=(100, 116, 139), font=font)
        draw.text((220, y), val, fill=color, font=font)
        y += 28

    # Checklist / Questions section
    y += 12
    draw.line([(40, y), (width - 40, y)], fill=(30, 41, 59), width=1)
    y += 16
    draw.text((40, y), "VERIFIED CHECKLIST QUESTIONS:", fill=(56, 189, 248), font=font)
    y += 26

    q_list = questions or ["General physical presence and operational status"]
    for q in q_list[:6]:
        draw.text((50, y), f"[x] {q}", fill=(226, 232, 240), font=font)
        y += 24

    # Footer note
    footer_text = "OFFLINE DEVELOPER MOCK TEST IMAGE - 0 EXTERNAL DEPENDENCIES - 2026 ALGERNON TECHNOLOGY"
    draw.text((40, height - 44), footer_text, fill=(71, 85, 105), font=font)

    file_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(file_path, format="JPEG", quality=90)
    return file_path

async def run_mock_operator_lifecycle(task_payload: Dict[str, Any]) -> None:
    """
    Simulates the human field operator lifecycle:
    1. Wait 1-2 seconds in 'pending_operator_review'.
    2. Transition task to 'accepted_in_progress'.
    3. Wait 1-2 seconds simulating arrival & photo capture.
    4. Generate mock proof image and save to PROOF_DIR.
    5. Complete task with structured mock vision findings.
    """
    task_id = task_payload["task_id"]
    location = task_payload.get("location", "Portland, OR")
    questions = task_payload.get("specific_questions", [])

    logger.info("[MockOperator] Task %s received. Simulating review...", task_id)
    # 1. Wait 1.0 second before operator acceptance
    await asyncio.sleep(1.0)

    # 2. Accept task
    await update_task_status(task_id, "accepted_in_progress")
    logger.info("[MockOperator] Task %s transitioned to 'accepted_in_progress'. Simulating on-site fulfillment...", task_id)

    # 3. Wait 1.2 seconds before completing
    await asyncio.sleep(1.2)

    # 4. Generate clean mock proof placard
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{task_id}_{timestamp_str}_mock.jpg"
    dest_path = PROOF_DIR / filename
    generate_mock_proof_image(dest_path, task_id, location, questions)

    photo_url = f"{BASE_PUBLIC_URL}/proof/{filename}"
    photo_metadata = {
        "has_exif": True,
        "mock_operator": True,
        "device": "GroundTruth MockCam v1.0",
        "gps": {
            "latitude": 45.5231,
            "longitude": -122.6816,
            "mock": True
        }
    }

    checklist_results = [
        {
            "question": q,
            "answer": "Verified affirmatively on-site by field operator.",
            "evidence_visible": f"Visual confirmation on-site for '{q}'."
        }
        for q in questions
    ]

    extracted_answers = {
        "operator_notes": f"Simulated field operator inspected {location}. Physical site accessible.",
        "verified_on_site": True,
        "has_gps": True,
        "vision_analysis": {
            "automated_vision": True,
            "photo_matches_location": True,
            "summary": f"Mock physical audit verified for {location}. Main entrance accessible, premises active.",
            "checklist_results": checklist_results,
            "posted_notices_text": "Public operating notice: Standard operational hours active."
        }
    }

    # 5. Complete task in database
    await complete_task(task_id, photo_url, photo_metadata, extracted_answers)
    logger.info("[MockOperator] Task %s completed successfully with mock proof photo.", task_id)

def trigger_mock_operator(task_payload: Dict[str, Any]) -> Optional[asyncio.Task]:
    """
    Schedules the mock operator lifecycle task in the running asyncio loop.
    Returns the Task object, or None if not in mock mode or no event loop is running.
    """
    if not is_mock_mode():
        return None

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("[MockOperator] No running asyncio loop to schedule mock runner.")
        return None

    task = loop.create_task(run_mock_operator_lifecycle(task_payload))
    _active_mock_tasks.add(task)
    task.add_done_callback(_active_mock_tasks.discard)
    return task
