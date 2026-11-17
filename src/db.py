"""Database operations and demand logging."""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import aiosqlite

from src.config import DB_PATH, DEMAND_LOG_PATH

logger = logging.getLogger("ground_truth.db")

async def init_db() -> None:
    """Initialize SQLite database with required tables and indexes."""
    async with aiosqlite.connect(DB_PATH) as db:
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
    """Retrieve a single task by task_id."""
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
            return data

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
    """Update task lifecycle state."""
    async with aiosqlite.connect(DB_PATH) as db:
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
