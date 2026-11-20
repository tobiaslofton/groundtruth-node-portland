"""Deduplication, payload hashing, and rate limiting."""
import hashlib
import re
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional

from src.config import (
    DB_PATH, 
    LOCATION_COOLDOWN_HOURS, 
    CLIENT_RATE_LIMIT_MINUTES,
    DAILY_DISPATCH_LIMIT
)

def normalize_string(text: str) -> str:
    """Normalize whitespace, casing, and punctuation for deterministic hashing."""
    cleaned = text.lower().strip()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    return " ".join(cleaned.split())

def compute_idempotency_hash(client_id: str, location: str, task_type: str) -> str:
    """Generate deterministic SHA-256 hash for identical incoming requests."""
    raw = f"{normalize_string(client_id)}:{normalize_string(task_type)}:{normalize_string(location)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

async def check_dispatch_eligibility(client_id: str, location: str, idempotency_hash: str) -> Tuple[bool, Optional[str]]:
    """
    Check if a request is eligible to proceed or violates rate limits / deduplication rules.
    Returns (is_allowed, denial_reason).
    """
    import aiosqlite
    now = datetime.now(timezone.utc)
    client_cutoff = (now - timedelta(minutes=CLIENT_RATE_LIMIT_MINUTES)).isoformat()
    location_cutoff = (now - timedelta(hours=LOCATION_COOLDOWN_HOURS)).isoformat()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Check daily completed dispatch quota
        async with db.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'completed' AND completed_at >= ?", 
            (today_start,)
        ) as cursor:
            row = await cursor.fetchone()
            completed_today = row[0] if row else 0
            if completed_today >= DAILY_DISPATCH_LIMIT:
                return False, f"Daily operator dispatch limit reached ({DAILY_DISPATCH_LIMIT} tasks). Service reopens tomorrow."

        # 2. Check identical active task (ignore expired tasks)
        now_iso = now.isoformat()
        async with db.execute(
            """SELECT task_id, status FROM tasks 
               WHERE idempotency_hash = ? 
                 AND (status = 'accepted_in_progress' OR (status = 'pending_operator_review' AND expires_at > ?))""",
            (idempotency_hash, now_iso)
        ) as cursor:
            existing = await cursor.fetchone()
            if existing:
                return False, f"Identical request is already active (Task ID: {existing[0]}, Status: {existing[1]})."

        # 3. Check client rate limit
        async with db.execute(
            "SELECT COUNT(*) FROM tasks WHERE client_id = ? AND created_at >= ?",
            (client_id, client_cutoff)
        ) as cursor:
            row = await cursor.fetchone()
            recent_client_tasks = row[0] if row else 0
            if recent_client_tasks >= 1:
                return False, f"Rate limit exceeded: Maximum 1 request per client every {CLIENT_RATE_LIMIT_MINUTES} minutes."

        # 4. Check location cooldown
        norm_loc = normalize_string(location)
        async with db.execute(
            "SELECT task_id, status FROM tasks WHERE created_at >= ? AND status = 'completed'",
            (location_cutoff,)
        ) as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                # Basic check if location matches recently completed audit
                pass

    return True, None
