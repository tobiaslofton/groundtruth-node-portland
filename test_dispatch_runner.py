"""Test script to dispatch a live simulation task to the operator's Telegram using standard library."""
import json
import sqlite3
import urllib.request
from datetime import datetime, timezone, timedelta

from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_OPERATOR_CHAT_ID, DB_PATH

def dispatch_simulation():
    # 1. Initialize SQLite table if needed using built-in sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            idempotency_hash TEXT NOT NULL,
            task_type TEXT NOT NULL,
            client_id TEXT NOT NULL,
            location TEXT NOT NULL,
            specific_questions TEXT NOT NULL,
            stated_purpose TEXT,
            status TEXT NOT NULL,
            decline_reason TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            completed_at TEXT,
            photo_url TEXT,
            photo_metadata TEXT,
            extracted_answers TEXT
        )
    """)
    conn.commit()

    task_id = "pdx_test_001"
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(minutes=15)).isoformat()

    task_payload = {
        "task_id": task_id,
        "idempotency_hash": "simulation_hash_001",
        "task_type": "storefront_audit",
        "client_id": "test_agent_claude",
        "location": "Powell's City of Books, 1005 W Burnside St, Portland, OR",
        "specific_questions": [
            "Confirm if the main Burnside entrance doors are unlocked and active.",
            "Photograph the posted store hours plaque beside the entrance."
        ],
        "stated_purpose": "Commercial real estate and foot-traffic due diligence simulation",
        "status": "pending_operator_review",
        "created_at": now.isoformat(),
        "expires_at": expires_at
    }

    # Upsert task into SQLite
    cursor.execute("""
        INSERT OR REPLACE INTO tasks (
            task_id, idempotency_hash, task_type, client_id, location,
            specific_questions, stated_purpose, status, decline_reason,
            created_at, expires_at, completed_at, photo_url, photo_metadata, extracted_answers
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        task_payload["task_id"],
        task_payload["idempotency_hash"],
        task_payload["task_type"],
        task_payload["client_id"],
        task_payload["location"],
        json.dumps(task_payload["specific_questions"]),
        task_payload["stated_purpose"],
        task_payload["status"],
        None,
        task_payload["created_at"],
        task_payload["expires_at"],
        None, None, None, None
    ))
    conn.commit()
    conn.close()
    print(f"Task {task_id} successfully stored in SQLite ({DB_PATH}).")

    # 2. Send interactive Telegram dispatch card
    card_text = (
        f"🚨 *NEW AGENT DISPATCH REQUEST*\n\n"
        f"*Task ID:* `{task_id}`\n"
        f"*Type:* Storefront Audit\n"
        f"*Location:* {task_payload['location']}\n\n"
        f"*Questions / Checklist:*\n"
        f"  • {task_payload['specific_questions'][0]}\n"
        f"  • {task_payload['specific_questions'][1]}\n\n"
        f"*Stated Purpose:* {task_payload['stated_purpose']}\n"
        f"*Expires:* in 15 minutes"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Accept Task", "callback_data": f"accept:{task_id}"}
            ],
            [
                {"text": "❌ Decline (Scope)", "callback_data": f"decline_scope:{task_id}"},
                {"text": "🚫 Decline (Unsafe)", "callback_data": f"decline_unsafe:{task_id}"}
            ]
        ]
    }

    payload = {
        "chat_id": TELEGRAM_OPERATOR_CHAT_ID,
        "text": card_text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    }

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode())
        print(f"Dispatched to Telegram! Message ID: {res['result']['message_id']}")

if __name__ == "__main__":
    dispatch_simulation()
