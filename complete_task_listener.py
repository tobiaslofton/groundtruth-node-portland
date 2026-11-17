"""Listener to process operator Accept click and photo upload for the simulation."""
import json
import os
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_OPERATOR_CHAT_ID, DB_PATH, PROOF_DIR

def bot_request(method, data=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    if data:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def run_listener():
    print("Listening for operator action on Telegram...")
    offset = None
    accepted = False
    task_id = "pdx_test_001"

    # Set status to accepted if already clicked, else listen for callback
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    while True:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?timeout=5"
        if offset:
            url += f"&offset={offset}"
        
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as resp:
                updates = json.loads(resp.read().decode()).get("result", [])
        except Exception as e:
            print(f"Error fetching updates: {e}")
            time.sleep(2)
            continue

        for u in updates:
            offset = u["update_id"] + 1

            # 1. Handle Accept / Decline Callback
            if "callback_query" in u:
                cb = u["callback_query"]
                data = cb.get("data", "")
                if data == f"accept:{task_id}":
                    accepted = True
                    cursor.execute("UPDATE tasks SET status = 'accepted_in_progress' WHERE task_id = ?", (task_id,))
                    conn.commit()
                    print(f"Operator ACCEPTED {task_id}! Status updated to 'accepted_in_progress'.")
                    
                    # Edit card to confirm
                    bot_request("editMessageText", {
                        "chat_id": TELEGRAM_OPERATOR_CHAT_ID,
                        "message_id": cb["message"]["message_id"],
                        "text": (
                            f"✅ *ACCEPTED: Task `{task_id}`*\n\n"
                            f"📍 *Location:* Powell's City of Books\n\n"
                            f"👉 *Next Step:* Snap any test photo on your phone right now and send it directly in this chat to complete the loop!"
                        ),
                        "parse_mode": "Markdown"
                    })
                elif "decline" in data:
                    print(f"Operator DECLINED {task_id}.")
                    return

            # 2. Handle Photo Upload
            if "message" in u and "photo" in u["message"]:
                msg = u["message"]
                if msg["chat"]["id"] == TELEGRAM_OPERATOR_CHAT_ID:
                    print("Received photo from operator! Downloading...")
                    photo = msg["photo"][-1]
                    file_id = photo["file_id"]

                    # Get file path from Telegram
                    file_info = bot_request("getFile", {"file_id": file_id})
                    file_path = file_info["result"]["file_path"]

                    # Download file
                    img_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                    dest_file = PROOF_DIR / f"{task_id}.jpg"
                    urllib.request.urlretrieve(img_url, dest_file)
                    print(f"Saved proof image to {dest_file} ({dest_file.stat().st_size} bytes).")

                    # Mark task completed in SQLite
                    now_iso = datetime.now(timezone.utc).isoformat()
                    notes = msg.get("caption") or "Burnside entrance active. Store hours verified."
                    answers = json.dumps({
                        "operator_notes": notes,
                        "verified_on_site": True,
                        "has_gps": False
                    })
                    photo_url = f"http://127.0.0.1:8000/proof/{task_id}.jpg"

                    cursor.execute("""
                        UPDATE tasks 
                        SET status = 'completed',
                            completed_at = ?,
                            photo_url = ?,
                            extracted_answers = ?
                        WHERE task_id = ?
                    """, (now_iso, photo_url, answers, task_id))
                    conn.commit()
                    conn.close()

                    # Send confirmation to operator
                    bot_request("sendMessage", {
                        "chat_id": TELEGRAM_OPERATOR_CHAT_ID,
                        "text": (
                            f"🎉 *TASK FULFILLED & LOOP COMPLETED!*\n\n"
                            f"*Task ID:* `{task_id}`\n"
                            f"*Photo Proof:* `{task_id}.jpg`\n"
                            f"*Status:* Delivered to AI Agent.\n\n"
                            f"The full physical actuation cycle is complete!"
                        ),
                        "parse_mode": "Markdown"
                    })
                    print("Simulation loop complete! Exiting listener.")
                    return

        time.sleep(1)

if __name__ == "__main__":
    run_listener()
