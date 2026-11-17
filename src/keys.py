"""API Key generation, hashing, and authorization management."""
import argparse
import hashlib
import os
import secrets
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import aiosqlite

from src.config import DB_PATH

async def init_keys_table() -> None:
    """Ensure api_keys table exists in SQLite database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id TEXT PRIMARY KEY,
                key_hash TEXT UNIQUE NOT NULL,
                key_prefix TEXT NOT NULL,
                client_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                request_count INTEGER NOT NULL DEFAULT 0,
                last_used_at TEXT
            )
        """)
        await db.commit()

def hash_key(raw_key: str) -> str:
    """Cryptographic hash of raw API key for storage."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()

async def generate_api_key(client_name: str) -> Tuple[str, str]:
    """
    Generate a new API key. Returns (key_id, plain_text_key).
    Plain text key is only shown once upon generation.
    """
    await init_keys_table()
    token = secrets.token_hex(20)
    plain_key = f"gt_live_{token}"
    key_hash = hash_key(plain_key)
    key_id = f"key_{secrets.token_hex(4)}"
    prefix = plain_key[:12] + "..."
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO api_keys (key_id, key_hash, key_prefix, client_name, created_at, is_active, request_count)
            VALUES (?, ?, ?, ?, ?, 1, 0)
        """, (key_id, key_hash, prefix, client_name, now))
        await db.commit()

    return key_id, plain_key

async def validate_api_key(raw_key: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Validate incoming API key against database hash."""
    if not raw_key:
        return False, None
    key_hash = hash_key(raw_key)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1
        """, (key_hash,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False, None

            record = dict(row)
            # Update request count and last used timestamp
            now = datetime.now(timezone.utc).isoformat()
            await db.execute("""
                UPDATE api_keys 
                SET request_count = request_count + 1, last_used_at = ? 
                WHERE key_id = ?
            """, (now, record["key_id"]))
            await db.commit()
            return True, record

async def list_keys() -> None:
    """List all registered API keys in database."""
    await init_keys_table()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key_id, key_prefix, client_name, is_active, request_count, created_at FROM api_keys") as cursor:
            rows = await cursor.fetchall()
            print(f"\nRegistered API Keys ({len(rows)}):")
            print("-" * 75)
            for r in rows:
                status = "ACTIVE" if r["is_active"] else "REVOKED"
                print(f"ID: {r['key_id']} | Client: {r['client_name']:<20} | Prefix: {r['key_prefix']} | Status: {status} | Calls: {r['request_count']}")
            print("-" * 75)

if __name__ == "__main__":
    import asyncio
    parser = argparse.ArgumentParser(description="Manage GroundTruth API Keys")
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser("create", help="Create a new API key")
    create_parser.add_argument("--name", required=True, help="Client or developer name")

    list_parser = subparsers.add_parser("list", help="List all active API keys")

    args = parser.parse_args()

    if args.command == "create":
        key_id, plain_key = asyncio.run(generate_api_key(args.name))
        print(f"\nCreated API Key for '{args.name}':")
        print(f"Key ID: {key_id}")
        print(f"Secret Key: {plain_key}")
        print("Note: Store this key securely; it will not be displayed again.\n")
    elif args.command == "list":
        asyncio.run(list_keys())
    else:
        parser.print_help()
