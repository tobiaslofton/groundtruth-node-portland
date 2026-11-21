"""Shared pytest configuration, fixtures, and mocks."""
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

import src.config as config_module
import src.db as db_module
import src.dedup as dedup_module
import src.keys as keys_module
import src.main as main_module
import src.telegram_bot as telegram_bot_module

def pytest_configure(config):
    """Configure pytest options, suppress known environment warnings."""
    config.addinivalue_line("filterwarnings", "ignore::pytest.PytestDeprecationWarning")
    config.addinivalue_line("filterwarnings", "ignore::DeprecationWarning")
    config.addinivalue_line("filterwarnings", "ignore::pytest.PytestCacheWarning")
    
    # Point cache to tempdir where full filesystem permissions exist on Windows
    if hasattr(config, "cache") and config.cache:
        temp_cache = Path(tempfile.gettempdir()) / "pdx_pytest_cache_v"
        temp_cache.mkdir(parents=True, exist_ok=True)
        config.cache._cachedir = temp_cache

@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """
    Ensure every test runs with an isolated database and proof directory
    in a temporary directory, with Telegram bot calls mocked out.
    """
    temp_data_dir = tmp_path / "data"
    temp_data_dir.mkdir(parents=True, exist_ok=True)
    temp_proof_dir = temp_data_dir / "proof"
    temp_proof_dir.mkdir(parents=True, exist_ok=True)
    temp_db_path = temp_data_dir / "test_tasks.db"
    temp_demand_log = temp_data_dir / "test_demand.jsonl"

    monkeypatch.setattr(config_module, "DATA_DIR", temp_data_dir)
    monkeypatch.setattr(config_module, "PROOF_DIR", temp_proof_dir)
    monkeypatch.setattr(config_module, "DB_PATH", temp_db_path)
    monkeypatch.setattr(config_module, "DEMAND_LOG_PATH", temp_demand_log)

    monkeypatch.setattr(db_module, "DB_PATH", temp_db_path)
    monkeypatch.setattr(db_module, "DEMAND_LOG_PATH", temp_demand_log)
    monkeypatch.setattr(dedup_module, "DB_PATH", temp_db_path)
    monkeypatch.setattr(keys_module, "DB_PATH", temp_db_path)
    monkeypatch.setattr(main_module, "PROOF_DIR", temp_proof_dir)
    monkeypatch.setattr(telegram_bot_module, "PROOF_DIR", temp_proof_dir)

    # Disable mandatory API key requirements for general tests
    monkeypatch.setattr(config_module, "REQUIRE_API_KEY", False)
    monkeypatch.setattr(main_module, "TELEGRAM_BOT_TOKEN", None)
    monkeypatch.setattr(config_module, "TELEGRAM_BOT_TOKEN", None)
    monkeypatch.setattr(config_module, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(main_module, "TELEGRAM_BOT_TOKEN", "")

    # Mock telegram notification to prevent any network calls
    monkeypatch.setattr(
        telegram_bot_module,
        "send_dispatch_notification",
        AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "src.mcp_server.send_dispatch_notification",
        AsyncMock(return_value=None)
    )

    yield {
        "db_path": temp_db_path,
        "proof_dir": temp_proof_dir,
        "data_dir": temp_data_dir,
    }

@pytest.fixture
def initialized_db(isolated_env):
    """Initialize fresh SQLite tables synchronously for tests requiring DB."""
    import asyncio
    from src.billing import deposit_client_credits
    async def _init():
        await db_module.init_db()
        await keys_module.init_keys_table()
        await db_module.set_operator_available(True)
        for cid in [
            "api_test_client_1", "rate_limited_client", "auth_client",
            "storefront_client", "custom_task_client", "client_sla_1",
            "client_sla", "client_qa", "agent_client_default", "rest_client_default",
            "test_agent_client"
        ]:
            await deposit_client_credits(cid, 500.0)
    asyncio.run(_init())
    return isolated_env

@pytest.fixture
def client(initialized_db):
    """FastAPI TestClient with initialized isolated test db."""
    with TestClient(main_module.app) as c:
        yield c
