"""Economic Clearing and Escrow Engine for GroundTruth Protocol.

Manages client credit balances and atomic escrow lifecycle for field verification tasks:
- Balance queries and credit deposits
- Dynamic dynamic pricing based on location tiers and complexity
- Escrow locking at dispatch
- Escrow settlement / release to field operators upon task completion
- Escrow refunds upon task decline, expiration, or cancellation
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import aiosqlite

import src.config as config
from src.config import DB_PATH

logger = logging.getLogger("ground_truth.billing")

BASE_TASK_COST = 35.0  # Enterprise actuation baseline ($35 core, $50 suburban, $65 outer/rush)

# Geographic distance surcharge keywords for Portland Metro
OUTER_METRO_KEYWORDS = (
    "hillsboro", "gresham", "oregon city", "tualatin",
    "west linn", "wilsonville", "clackamas", "troutdale"
)
SUBURBAN_METRO_KEYWORDS = (
    "beaverton", "tigard", "lake oswego", "milwaukie", "happy valley"
)

# Complexity & SLA surcharges
COMPLEXITY_SURCHARGES = {
    "standard": 0.0,
    "complex": 15.0,
    "high": 15.0,
    "rush": 25.0,
    "urgent": 25.0,
    "custom": 15.0,
}


def estimate_task_cost(location: str, complexity: str = "standard") -> float:
    """
    Calculate enterprise dynamic pricing for a physical verification task.

    Base cost: $35.00 (Downtown/Core Foot Patrol)
    Distance tiers:
      - Core/Downtown Portland: +$0.00 ($35 base)
      - Suburban Portland Metro (Beaverton, Lake Oswego): +$15.00 ($50 standard)
      - Outer Metro (Gresham, Hillsboro, Oregon City): +$25.00 ($60 standard)
    Complexity / SLA:
      - Standard: +$0.00
      - Urgent / Rush (<30 min dispatch): +$25.00
      - High / Complex: +$15.00

    Ensures 55% - 65% gross margin while undercutting legacy inspection firms ($125 - $250) by 50%+.
    """
    loc_lower = location.lower()
    distance_surcharge = 0.0

    if any(k in loc_lower for k in OUTER_METRO_KEYWORDS):
        distance_surcharge = 25.0
    elif any(k in loc_lower for k in SUBURBAN_METRO_KEYWORDS):
        distance_surcharge = 15.0

    complexity_key = complexity.lower().strip()
    complexity_surcharge = COMPLEXITY_SURCHARGES.get(complexity_key, 0.0)

    total = BASE_TASK_COST + distance_surcharge + complexity_surcharge
    return round(float(total), 2)


async def get_client_balance(client_id: str) -> float:
    """
    Retrieve current credit balance for client_id.
    Returns 0.0 if client has no ledger entry.
    """
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT balance FROM billing_ledgers WHERE client_id = ?",
            (client_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return float(row[0]) if row else 0.0


async def deposit_client_credits(client_id: str, amount: float) -> float:
    """
    Deposit credits into a client's billing ledger.
    Creates ledger if not existing. Returns new balance.
    """
    if amount <= 0:
        raise ValueError("Deposit amount must be positive.")
    now_iso = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            INSERT INTO billing_ledgers (client_id, balance, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                balance = balance + excluded.balance,
                updated_at = excluded.updated_at
        """, (client_id, amount, now_iso, now_iso))
        await db.commit()

        async with db.execute(
            "SELECT balance FROM billing_ledgers WHERE client_id = ?",
            (client_id,)
        ) as cursor:
            row = await cursor.fetchone()
            new_balance = float(row[0])
            logger.info("Deposited %.2f credits for %s. New balance: %.2f", amount, client_id, new_balance)
            return new_balance


async def lock_escrow(task_id: str, client_id: str, amount: float) -> bool:
    """
    Atomically lock task credits from client's balance into task_escrows.
    Returns True if balance was sufficient and escrow locked, False otherwise.
    """
    if amount <= 0:
        return False

    now_iso = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(config.DB_PATH) as db:
        # Check current balance
        async with db.execute(
            "SELECT balance FROM billing_ledgers WHERE client_id = ?",
            (client_id,)
        ) as cursor:
            row = await cursor.fetchone()
            current_balance = float(row[0]) if row else 0.0

        if current_balance < amount:
            logger.warning(
                "Escrow lock failed for %s on task %s: required %.2f, current balance %.2f",
                client_id, task_id, amount, current_balance
            )
            return False

        # Check if escrow already exists for this task
        async with db.execute(
            "SELECT status FROM task_escrows WHERE task_id = ?",
            (task_id,)
        ) as cursor:
            existing = await cursor.fetchone()
            if existing:
                logger.warning("Escrow already exists for task %s with status %s", task_id, existing[0])
                return False

        # Deduct balance from client
        await db.execute("""
            UPDATE billing_ledgers 
            SET balance = balance - ?, updated_at = ?
            WHERE client_id = ?
        """, (amount, now_iso, client_id))

        # Insert locked escrow record
        await db.execute("""
            INSERT INTO task_escrows (
                task_id, client_id, amount, status, operator_id, locked_at, settled_at, notes
            ) VALUES (?, ?, ?, 'locked', NULL, ?, NULL, NULL)
        """, (task_id, client_id, amount, now_iso))

        await db.commit()
        logger.info("Locked %.2f credits in escrow for task %s (client: %s)", amount, task_id, client_id)
        return True


async def release_escrow(task_id: str, operator_id: str = "node_001_operator") -> bool:
    """
    Release locked escrow funds to operator upon verified task completion.
    Returns True if escrow was successfully released, False if not in locked state.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute("""
            UPDATE task_escrows
            SET status = 'released',
                operator_id = ?,
                settled_at = ?
            WHERE task_id = ? AND status = 'locked'
        """, (operator_id, now_iso, task_id)) as cursor:
            updated = cursor.rowcount > 0

        await db.commit()
        if updated:
            logger.info("Released escrow for task %s to operator %s", task_id, operator_id)
        else:
            logger.warning("Could not release escrow for task %s (not found or not locked)", task_id)
        return updated


async def refund_escrow(task_id: str) -> bool:
    """
    Refund locked escrow funds back to client upon task expiration, decline, or cancellation.
    Returns True if escrow was successfully refunded, False if not in locked state.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT client_id, amount, status FROM task_escrows WHERE task_id = ?",
            (task_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row or row["status"] != "locked":
            logger.debug("Escrow for task %s not refundable (status: %s)", task_id, row["status"] if row else "none")
            return False

        client_id = row["client_id"]
        amount = float(row["amount"])

        # Recredit client
        await db.execute("""
            UPDATE billing_ledgers
            SET balance = balance + ?, updated_at = ?
            WHERE client_id = ?
        """, (amount, now_iso, client_id))

        # Update escrow record
        await db.execute("""
            UPDATE task_escrows
            SET status = 'refunded',
                settled_at = ?
            WHERE task_id = ? AND status = 'locked'
        """, (now_iso, task_id))

        await db.commit()
        logger.info("Refunded %.2f credits for task %s back to client %s", amount, task_id, client_id)
        return True


async def get_task_escrow(task_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve escrow details for a task."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM task_escrows WHERE task_id = ?",
            (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
