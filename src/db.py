"""Database operations and demand logging."""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import aiosqlite

from src.config import DB_PATH, DEMAND_LOG_PATH

logger = logging.getLogger("ground_truth.db")

async def init_db() -> None:
    """Initialize SQLite database with required tables, indexes, and concurrency pragmas."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("""
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS node_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_hash ON tasks(idempotency_hash)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_client ON tasks(client_id, created_at)")
        await db.commit()
    logger.info("Database initialized at %s", DB_PATH)

async def create_task(task_data: Dict[str, Any]) -> None:
    """Insert a new task into the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO tasks (
                task_id, idempotency_hash, task_type, client_id, location,
                specific_questions, stated_purpose, status, decline_reason,
                created_at, expires_at, completed_at, photo_url, photo_metadata, extracted_answers
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_data["task_id"],
            task_data["idempotency_hash"],
            task_data["task_type"],
            task_data["client_id"],
            task_data["location"],
            json.dumps(task_data.get("specific_questions", [])),
            task_data.get("stated_purpose", ""),
            task_data["status"],
            task_data.get("decline_reason"),
            task_data["created_at"],
            task_data["expires_at"],
            None, None, None, None
        ))
        await db.commit()

async def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single task by task_id and evaluate expiration."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            data["specific_questions"] = json.loads(data["specific_questions"])
            if data["photo_metadata"]:
                data["photo_metadata"] = json.loads(data["photo_metadata"])
            if data["extracted_answers"]:
                data["extracted_answers"] = json.loads(data["extracted_answers"])

            # Evaluate task expiration
            now_iso = datetime.now(timezone.utc).isoformat()
            if data["status"] == "pending_operator_review" and data["expires_at"] <= now_iso:
                await db.execute("""
                    UPDATE tasks 
                    SET status = 'expired', decline_reason = 'Operator did not review task within review window.'
                    WHERE task_id = ?
                """, (task_id,))
                await db.commit()
                data["status"] = "expired"
                data["decline_reason"] = "Operator did not review task within review window."
            elif data["status"] == "accepted_in_progress" and data["expires_at"] <= now_iso:
                await db.execute("""
                    UPDATE tasks 
                    SET status = 'abandoned_timeout', decline_reason = 'Operator accepted but failed to upload photo proof within fulfillment window.'
                    WHERE task_id = ?
                """, (task_id,))
                await db.commit()
                data["status"] = "abandoned_timeout"
                data["decline_reason"] = "Operator accepted but failed to upload photo proof within fulfillment window."

            return data

async def sweep_expired_tasks() -> int:
    """Transition pending tasks past expires_at to 'expired'."""
    now_iso = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            UPDATE tasks 
            SET status = 'expired', decline_reason = 'Task expired before operator review.'
            WHERE status = 'pending_operator_review' AND expires_at <= ?
        """, (now_iso,)) as cursor:
            count = cursor.rowcount
        await db.commit()
        return count

async def get_node_state(key: str, default: str = "") -> str:
    """Read a key from persistent node_state table."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM node_state WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_node_state(key: str, value: str) -> None:
    """Set a key in persistent node_state table."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO node_state (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        await db.commit()

async def is_operator_available() -> bool:
    """Check if the human operator is currently on-duty and accepting dispatches."""
    val = await get_node_state("operator_paused", "0")
    return val != "1"

async def set_operator_available(available: bool) -> None:
    """Toggle operator on-duty / off-duty status."""
    await set_node_state("operator_paused", "0" if available else "1")

async def get_active_task_by_hash(idempotency_hash: str) -> Optional[Dict[str, Any]]:
    """Check if an active/pending task with the same hash exists."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM tasks 
            WHERE idempotency_hash = ? 
              AND status IN ('pending_operator_review', 'accepted_in_progress')
            ORDER BY created_at DESC LIMIT 1
        """, (idempotency_hash,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_task_status(task_id: str, status: str, decline_reason: Optional[str] = None) -> None:
    """Update task lifecycle state. When accepted, automatically extend expires_at by fulfillment window."""
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    from src.config import FULFILLMENT_TIMEOUT_MINUTES
    async with aiosqlite.connect(DB_PATH) as db:
        if status == "accepted_in_progress":
            new_expires = (now + timedelta(minutes=FULFILLMENT_TIMEOUT_MINUTES)).isoformat()
            await db.execute("""
                UPDATE tasks 
                SET status = ?, decline_reason = ?, expires_at = ? 
                WHERE task_id = ?
            """, (status, decline_reason, new_expires, task_id))
        else:
            await db.execute("""
                UPDATE tasks 
                SET status = ?, decline_reason = ? 
                WHERE task_id = ?
            """, (status, decline_reason, task_id))
        await db.commit()

async def complete_task(
    task_id: str, 
    photo_url: str, 
    photo_metadata: Dict[str, Any], 
    extracted_answers: Dict[str, Any]
) -> None:
    """Mark task as completed with photo proof and extracted data."""
    now_iso = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE tasks 
            SET status = 'completed', 
                completed_at = ?,
                photo_url = ?,
                photo_metadata = ?,
                extracted_answers = ?
            WHERE task_id = ?
        """, (
            now_iso, 
            photo_url, 
            json.dumps(photo_metadata), 
            json.dumps(extracted_answers), 
            task_id
        ))
        await db.commit()

async def get_current_active_task() -> Optional[Dict[str, Any]]:
    """Retrieve the single currently accepted in-progress task for the operator."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM tasks 
            WHERE status = 'accepted_in_progress' 
            ORDER BY created_at DESC LIMIT 1
        """) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

def log_demand_research(payload: Dict[str, Any]) -> None:
    """Append-only logging of all agent requests for market validation."""
    record = {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        **payload
    }
    with open(DEMAND_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
