"""GroundTruth Protocol: Offline Developer Mock Demo.

Demonstrates an end-to-end agent physical verification loop in offline mock mode.
Runs locally in ~3-5 seconds with:
- Zero environment variables required
- Zero API keys required
- Zero Telegram bot setup required
- Fully automated mock field operator fulfillment
"""
import os
import sys
from pathlib import Path

# 1. Force offline mock operator mode before loading app configs
os.environ["MOCK_OPERATOR_MODE"] = "1"

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
from src.db import init_db
from src.mcp_server import portland_physical_verification, check_task_status

async def main():
    print("=" * 70, flush=True)
    print("GROUNDTRUTH PROTOCOL: NODE #001 (PORTLAND, OR)", flush=True)
    print("OFFLINE DEVELOPER VERIFICATION LOOP (MOCK MODE)", flush=True)
    print("=" * 70, flush=True)

    # 1. Initialize local SQLite database
    print("\n[1] Initializing local database...", flush=True)
    await init_db()
    print("    Database ready.", flush=True)

    # 2. Dispatch physical verification task
    target_location = "Powell's City of Books, Portland, OR"
    questions = [
        "Are the main Burnside entrance doors open?",
        "Is there any public notice or leasing sign posted?",
        "Is there a line or crowd outside the entrance?"
    ]

    print(f"\n[2] Dispatching agent verification request to: {target_location}", flush=True)
    print(f"    Checklist:", flush=True)
    for q in questions:
        print(f"      - {q}", flush=True)

    dispatch_result = await portland_physical_verification(
        location=target_location,
        specific_questions=questions,
        stated_purpose="Autonomous commercial storefront status audit",
        client_id="offline_demo_agent"
    )

    task_id = dispatch_result.get("task_id")
    status = dispatch_result.get("status")
    print(f"\n    [+] Task Dispatched Successfully!", flush=True)
    print(f"        Task ID: {task_id}", flush=True)
    print(f"        Initial Status: {status}", flush=True)
    print("    Waiting for mock field operator to accept and fulfill...", flush=True)

    # 3. Poll task status until completion
    print("\n[3] Polling check_task_status...", flush=True)
    max_polls = 20
    completed_task = None

    for i in range(1, max_polls + 1):
        await asyncio.sleep(0.5)
        status_info = await check_task_status(task_id)
        current_status = status_info.get("status")
        print(f"    [Poll #{i:02d}] Status: {current_status}", flush=True)

        if current_status == "completed":
            completed_task = status_info
            break
        elif current_status == "declined":
            print(f"\n[!] Task declined: {status_info.get('decline_reason')}", flush=True)
            return

    if not completed_task:
        print("\n[!] Polling timed out before task reached 'completed'.", flush=True)
        sys.exit(1)

    # 4. Print verified ground truth results
    print("\n" + "=" * 70, flush=True)
    print("GROUND TRUTH VERIFICATION COMPLETE", flush=True)
    print("=" * 70, flush=True)
    print(f"Task ID:         {completed_task.get('task_id')}", flush=True)
    print(f"Target Location: {completed_task.get('location')}", flush=True)
    print(f"Completed At:    {completed_task.get('completed_at')}", flush=True)
    print(f"Proof Photo URL: {completed_task.get('photo_url')}", flush=True)
    print(f"Has GPS EXIF:    {completed_task.get('has_gps_metadata')}", flush=True)

    extracted = completed_task.get("extracted_answers", {})
    vision = extracted.get("vision_analysis", {})

    print(f"\nOperator Notes:  {extracted.get('operator_notes')}", flush=True)
    print(f"Vision Summary:  {vision.get('summary')}", flush=True)
    print(f"Posted Notices:  {vision.get('posted_notices_text')}", flush=True)
    print("\nChecklist Findings:", flush=True)
    for item in vision.get("checklist_results", []):
        print(f"  * Q: {item.get('question')}", flush=True)
        print(f"    A: {item.get('answer')}", flush=True)
        print(f"    Evidence: {item.get('evidence_visible')}", flush=True)

    print("\n" + "=" * 70, flush=True)
    print("Demo completed cleanly with verified proof!", flush=True)
    print("=" * 70, flush=True)

if __name__ == "__main__":
    asyncio.run(main())
