"""GroundTruth Protocol: Python Quickstart Client Example.

Dispatches a physical verification audit and polls for completed on-site proof.
"""
import time
import requests

# Base URL (Replace with live public tunnel or localhost)
BASE_URL = "http://127.0.0.1:8000"
API_KEY = "gt_live_demo"  # Optional during pilot phase

headers = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

def run_physical_audit():
    print("[1] Dispatching physical audit request...")
    payload = {
        "business_name": "Powell's City of Books",
        "address": "1005 W Burnside St, Portland, OR",
        "specific_questions": [
            "Are the main Burnside entrance doors open?",
            "Is there any public notice or leasing sign posted?"
        ],
        "stated_purpose": "Real-world commercial verification",
        "client_id": "python_quickstart_agent"
    }

    # 1. Dispatch Request
    resp = requests.post(f"{BASE_URL}/v1/dispatch/storefront", json=payload, headers=headers)
    if resp.status_code != 200:
        print(f"Error dispatching task ({resp.status_code}):", resp.text)
        return

    data = resp.json()
    task_id = data["task_id"]
    print(f"Task Dispatched! Task ID: {task_id}")
    print(f"Status: {data['status']}")
    print("Waiting for local field operator in Portland to review and fulfill...\n")

    # 2. Poll for Completion
    max_checks = 20
    for i in range(max_checks):
        time.sleep(10)
        status_resp = requests.get(f"{BASE_URL}/v1/tasks/{task_id}", headers=headers)
        if status_resp.status_code != 200:
            continue
        
        status_data = status_resp.json()
        current_status = status_data["status"]
        print(f"[{i+1}/{max_checks}] Current Status: {current_status}")

        if current_status == "completed":
            print("\n🎉 TASK COMPLETED & GROUND TRUTH RETRIEVED!")
            print(f"Verified Location: {status_data['location']}")
            print(f"Completed At: {status_data['completed_at']}")
            print(f"Proof Photo URL: {status_data['photo_url']}")
            print(f"AI Vision Findings:\n", status_data.get("extracted_answers", {}))
            return
        elif current_status == "declined":
            print(f"\n❌ Task was declined by operator: {status_data.get('decline_reason')}")
            return

    print("\nPolling timed out before operator completed task.")

if __name__ == "__main__":
    run_physical_audit()
