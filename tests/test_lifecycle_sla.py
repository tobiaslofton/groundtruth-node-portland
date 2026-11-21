"""Automated test suite for task lifecycle persistence, two-tier SLA, and operator commands."""
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.config import OPERATOR_REVIEW_TIMEOUT_MINUTES, FULFILLMENT_TIMEOUT_MINUTES, TELEGRAM_OPERATOR_CHAT_ID
from src.db import (
    init_db,
    create_task,
    get_task,
    update_task_status,
    complete_task,
    sweep_expired_tasks,
    get_current_active_task,
    get_active_task_by_hash,
    is_operator_available,
    set_operator_available,
)
from src.mcp_server import portland_physical_verification
from src.telegram_bot import cmd_pause, cmd_resume, cmd_cancel, cmd_status

@pytest.fixture
def setup_db(initialized_db):
    """Ensure database tables and initial state are ready."""
    return initialized_db

class TestTaskPersistenceAndTransitions:
    """Test SQLite task persistence, field serialization, and status updates."""

    @pytest.mark.asyncio
    async def test_create_and_retrieve_task(self, setup_db):
        now = datetime.now(timezone.utc)
        task_data = {
            "task_id": "pdx_test_001",
            "idempotency_hash": "hash_test_001",
            "task_type": "physical_verification",
            "client_id": "client_qa",
            "location": "1005 W Burnside St, Portland, OR",
            "specific_questions": ["Is storefront open?", "Is parking available?"],
            "stated_purpose": "QA Persistence Test",
            "status": "pending_operator_review",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
        }
        await create_task(task_data)

        retrieved = await get_task("pdx_test_001")
        assert retrieved is not None
        assert retrieved["task_id"] == "pdx_test_001"
        assert retrieved["client_id"] == "client_qa"
        assert retrieved["location"] == "1005 W Burnside St, Portland, OR"
        assert retrieved["status"] == "pending_operator_review"
        assert retrieved["specific_questions"] == ["Is storefront open?", "Is parking available?"]
        assert retrieved["photo_metadata"] is None
        assert retrieved["extracted_answers"] is None

    @pytest.mark.asyncio
    async def test_update_status_to_declined(self, setup_db):
        now = datetime.now(timezone.utc)
        task_data = {
            "task_id": "pdx_test_002",
            "idempotency_hash": "hash_test_002",
            "task_type": "physical_verification",
            "client_id": "client_qa",
            "location": "123 Main St, Beaverton, OR",
            "specific_questions": ["Check signs"],
            "status": "pending_operator_review",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
        }
        await create_task(task_data)
        await update_task_status("pdx_test_002", "declined", decline_reason="Operator declined: Out of scope")

        retrieved = await get_task("pdx_test_002")
        assert retrieved["status"] == "declined"
        assert retrieved["decline_reason"] == "Operator declined: Out of scope"

    @pytest.mark.asyncio
    async def test_complete_task(self, setup_db):
        now = datetime.now(timezone.utc)
        task_data = {
            "task_id": "pdx_test_003",
            "idempotency_hash": "hash_test_003",
            "task_type": "physical_verification",
            "client_id": "client_qa",
            "location": "400 SW 6th Ave, Portland, OR",
            "specific_questions": ["Check hours"],
            "status": "accepted_in_progress",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=90)).isoformat(),
        }
        await create_task(task_data)

        photo_meta = {"has_exif": True, "gps": {"Latitude": "45.5200"}}
        answers = {"operator_notes": "Sign posted: Open 9-5", "verified_on_site": True}
        await complete_task("pdx_test_003", "http://test/proof/pdx_test_003.jpg", photo_meta, answers)

        retrieved = await get_task("pdx_test_003")
        assert retrieved["status"] == "completed"
        assert retrieved["completed_at"] is not None
        assert retrieved["photo_url"] == "http://test/proof/pdx_test_003.jpg"
        assert retrieved["photo_metadata"] == photo_meta
        assert retrieved["extracted_answers"] == answers

    @pytest.mark.asyncio
    async def test_get_current_active_task(self, setup_db):
        # When no active task exists
        assert await get_current_active_task() is None

        # Create pending task (not yet accepted)
        now = datetime.now(timezone.utc)
        await create_task({
            "task_id": "pdx_pending_01",
            "idempotency_hash": "hash_p",
            "task_type": "physical_verification",
            "client_id": "client_qa",
            "location": "Portland, OR",
            "status": "pending_operator_review",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
        })
        assert await get_current_active_task() is None

        # Accept task
        await update_task_status("pdx_pending_01", "accepted_in_progress")
        active = await get_current_active_task()
        assert active is not None
        assert active["task_id"] == "pdx_pending_01"

        # Complete task
        await complete_task("pdx_pending_01", "url", {}, {})
        assert await get_current_active_task() is None

    @pytest.mark.asyncio
    async def test_get_active_task_by_hash(self, setup_db):
        now = datetime.now(timezone.utc)
        await create_task({
            "task_id": "pdx_hash_01",
            "idempotency_hash": "target_hash_123",
            "task_type": "physical_verification",
            "client_id": "client_qa",
            "location": "Portland, OR",
            "status": "pending_operator_review",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
        })
        found = await get_active_task_by_hash("target_hash_123")
        assert found is not None
        assert found["task_id"] == "pdx_hash_01"

        # Non-matching hash
        assert await get_active_task_by_hash("different_hash") is None


class TestTwoTierSLA:
    """Test two-tier SLA deadlines: 15-minute review window & 90-minute fulfillment window."""

    @pytest.mark.asyncio
    async def test_initial_review_deadline_15_minutes(self, setup_db):
        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.5, "lon": -122.6}, None)):
            res = await portland_physical_verification(
                location="Pioneer Square, Portland, OR",
                specific_questions=["Is fountain running?"],
                client_id="client_sla_1"
            )
            assert res["status"] == "pending_operator_review"
            task_id = res["task_id"]
            deadline_str = res["operator_review_deadline"]

            task = await get_task(task_id)
            assert task is not None
            created = datetime.fromisoformat(task["created_at"])
            expires = datetime.fromisoformat(deadline_str)
            diff_minutes = (expires - created).total_seconds() / 60.0
            assert round(diff_minutes) == OPERATOR_REVIEW_TIMEOUT_MINUTES

    @pytest.mark.asyncio
    async def test_review_timeout_auto_expires_task(self, setup_db):
        # Create a task whose 15-min review deadline is in the past
        past_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        past_expires = datetime.now(timezone.utc) - timedelta(minutes=5)
        await create_task({
            "task_id": "pdx_expired_01",
            "idempotency_hash": "hash_exp_1",
            "task_type": "physical_verification",
            "client_id": "client_sla",
            "location": "Portland, OR",
            "status": "pending_operator_review",
            "created_at": past_time.isoformat(),
            "expires_at": past_expires.isoformat(),
        })

        # get_task evaluates expiration on retrieval
        task = await get_task("pdx_expired_01")
        assert task["status"] == "expired"
        assert "Operator did not review task within review window" in task["decline_reason"]

    @pytest.mark.asyncio
    async def test_sweep_expired_tasks(self, setup_db):
        past_time = datetime.now(timezone.utc) - timedelta(minutes=30)
        past_expires = datetime.now(timezone.utc) - timedelta(minutes=10)
        future_expires = datetime.now(timezone.utc) + timedelta(minutes=10)

        # Create 2 expired tasks and 1 valid task
        await create_task({
            "task_id": "sweep_1",
            "idempotency_hash": "h1",
            "task_type": "physical_verification",
            "client_id": "client_sla",
            "location": "Portland, OR",
            "status": "pending_operator_review",
            "created_at": past_time.isoformat(),
            "expires_at": past_expires.isoformat(),
        })
        await create_task({
            "task_id": "sweep_2",
            "idempotency_hash": "h2",
            "task_type": "physical_verification",
            "client_id": "client_sla",
            "location": "Portland, OR",
            "status": "pending_operator_review",
            "created_at": past_time.isoformat(),
            "expires_at": past_expires.isoformat(),
        })
        await create_task({
            "task_id": "sweep_3_valid",
            "idempotency_hash": "h3",
            "task_type": "physical_verification",
            "client_id": "client_sla",
            "location": "Portland, OR",
            "status": "pending_operator_review",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": future_expires.isoformat(),
        })

        swept_count = await sweep_expired_tasks()
        assert swept_count == 2

        t1 = await get_task("sweep_1")
        t2 = await get_task("sweep_2")
        t3 = await get_task("sweep_3_valid")
        assert t1["status"] == "expired"
        assert t2["status"] == "expired"
        assert t3["status"] == "pending_operator_review"

    @pytest.mark.asyncio
    async def test_operator_acceptance_extends_deadline_to_90_minutes(self, setup_db):
        now = datetime.now(timezone.utc)
        initial_expires = now + timedelta(minutes=15)
        await create_task({
            "task_id": "pdx_sla_extend",
            "idempotency_hash": "hash_sla_ext",
            "task_type": "physical_verification",
            "client_id": "client_sla",
            "location": "Gresham, OR",
            "status": "pending_operator_review",
            "created_at": now.isoformat(),
            "expires_at": initial_expires.isoformat(),
        })

        # Operator accepts: status -> accepted_in_progress
        await update_task_status("pdx_sla_extend", "accepted_in_progress")

        task = await get_task("pdx_sla_extend")
        assert task["status"] == "accepted_in_progress"
        new_expires = datetime.fromisoformat(task["expires_at"])
        remaining_minutes = (new_expires - datetime.now(timezone.utc)).total_seconds() / 60.0
        # Should be ~90 minutes from now (greater than initial 15-minute deadline)
        assert 85 <= remaining_minutes <= 91

    @pytest.mark.asyncio
    async def test_fulfillment_timeout_auto_transitions_to_abandoned(self, setup_db):
        # Create an accepted task whose 90-min fulfillment deadline expired
        past_time = datetime.now(timezone.utc) - timedelta(minutes=120)
        past_expires = datetime.now(timezone.utc) - timedelta(minutes=5)
        await create_task({
            "task_id": "pdx_abandoned_01",
            "idempotency_hash": "hash_aband_1",
            "task_type": "physical_verification",
            "client_id": "client_sla",
            "location": "Clackamas, OR",
            "status": "accepted_in_progress",
            "created_at": past_time.isoformat(),
            "expires_at": past_expires.isoformat(),
        })

        task = await get_task("pdx_abandoned_01")
        assert task["status"] == "abandoned_timeout"
        assert "Operator accepted but failed to upload photo proof" in task["decline_reason"]


class TestOperatorCancellationAndCommands:
    """Test operator /cancel, /pause, /resume commands and availability state."""

    @pytest.mark.asyncio
    async def test_operator_task_cancellation_releases_lock(self, setup_db):
        now = datetime.now(timezone.utc)
        await create_task({
            "task_id": "pdx_cancel_test",
            "idempotency_hash": "hash_can",
            "task_type": "physical_verification",
            "client_id": "client_qa",
            "location": "Beaverton, OR",
            "status": "accepted_in_progress",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=90)).isoformat(),
        })
        assert (await get_current_active_task())["task_id"] == "pdx_cancel_test"

        # Cancel the task
        reason = "Operator cancelled in-progress verification (site inaccessible or abandoned)."
        await update_task_status("pdx_cancel_test", "cancelled_by_operator", decline_reason=reason)

        task = await get_task("pdx_cancel_test")
        assert task["status"] == "cancelled_by_operator"
        assert task["decline_reason"] == reason
        # Active lock must be released
        assert await get_current_active_task() is None

    @pytest.mark.asyncio
    async def test_telegram_cmd_cancel(self, setup_db):
        # Case 1: Cancel when no active task
        mock_msg = AsyncMock()
        mock_update = MagicMock()
        mock_update.effective_chat.id = TELEGRAM_OPERATOR_CHAT_ID
        mock_update.message = mock_msg

        await cmd_cancel(mock_update, MagicMock())
        mock_msg.reply_text.assert_called_once()
        assert "no accepted in-progress task to cancel" in mock_msg.reply_text.call_args[0][0]

        # Case 2: Cancel active task
        now = datetime.now(timezone.utc)
        await create_task({
            "task_id": "pdx_tg_cancel",
            "idempotency_hash": "hash_tg_c",
            "task_type": "physical_verification",
            "client_id": "client_qa",
            "location": "Portland, OR",
            "status": "accepted_in_progress",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=90)).isoformat(),
        })

        mock_msg.reset_mock()
        await cmd_cancel(mock_update, MagicMock())
        assert "CANCELLED Task `pdx_tg_cancel`" in mock_msg.reply_text.call_args[0][0]
        assert await get_current_active_task() is None

    @pytest.mark.asyncio
    async def test_operator_pause_and_resume_state(self, setup_db):
        # Default is available
        assert await is_operator_available() is True

        # Pause
        await set_operator_available(False)
        assert await is_operator_available() is False

        # Resume
        await set_operator_available(True)
        assert await is_operator_available() is True

    @pytest.mark.asyncio
    async def test_telegram_cmd_pause_and_resume(self, setup_db):
        mock_msg = AsyncMock()
        mock_update = MagicMock()
        mock_update.effective_chat.id = TELEGRAM_OPERATOR_CHAT_ID
        mock_update.message = mock_msg

        # Execute /pause
        await cmd_pause(mock_update, MagicMock())
        assert await is_operator_available() is False
        assert "PAUSED (Off-Duty)" in mock_msg.reply_text.call_args[0][0]

        # Execute /resume
        mock_msg.reset_mock()
        await cmd_resume(mock_update, MagicMock())
        assert await is_operator_available() is True
        assert "RESUMED (Active)" in mock_msg.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_dispatch_rejection_when_operator_paused(self, setup_db):
        # Put operator on pause
        await set_operator_available(False)

        res = await portland_physical_verification(
            location="1005 W Burnside St, Portland, OR",
            specific_questions=["Check status"],
            client_id="client_paused_test"
        )
        assert res["status"] == "rejected_operator_unavailable"
        assert res["can_retry"] is True
        assert "currently off-duty or paused" in res["error"]
