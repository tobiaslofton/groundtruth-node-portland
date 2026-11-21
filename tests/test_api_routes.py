"""Automated test suite for FastAPI REST API routes using TestClient."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import src.config as config_module
from src.db import create_task, complete_task, set_operator_available
from src.keys import generate_api_key

class TestHealthAndDiscoveryRoutes:
    """Test /health, /llms.txt, and root landing page."""

    def test_get_health(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "portland_ground_truth_pilot"
        assert "bot_active" in data

    def test_get_root_landing(self, client: TestClient):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "GroundTruth Protocol" in response.text
        assert "/llms.txt" in response.text

    def test_get_llms_txt(self, client: TestClient):
        response = client.get("/llms.txt")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert len(response.text) > 0


class TestDispatchVerifyRoute:
    """Test POST /v1/dispatch/verify with valid, invalid, duplicate, and paused states."""

    def test_dispatch_verify_success(self, client: TestClient):
        payload = {
            "location": "1005 W Burnside St, Portland, OR",
            "specific_questions": [
                "Is the main entrance accessible?",
                "Is there an open sign illuminated?"
            ],
            "stated_purpose": "REST API route validation",
            "client_id": "api_test_client_1"
        }
        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.523, "lon": -122.681}, None)):
            response = client.post("/v1/dispatch/verify", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending_operator_review"
            assert data["task_id"].startswith("pdx_")
            assert "operator_review_deadline" in data
            assert "fulfillment_deadline" in data
            assert data["poll_interval_seconds"] == 30

    def test_dispatch_verify_out_of_coverage(self, client: TestClient):
        payload = {
            "location": "Times Square, New York, NY 10036",
            "specific_questions": ["Check billboard"],
            "client_id": "api_test_client_nyc"
        }
        with patch("src.geofence.validate_portland_location", return_value=(False, None, "Location is outside Portland zone")):
            response = client.post("/v1/dispatch/verify", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "rejected_out_of_coverage"
            assert "outside Portland zone" in data["error"]
            assert data["can_retry"] is False

    def test_dispatch_verify_operator_paused_503(self, client: TestClient):
        # Pause operator
        import asyncio
        asyncio.run(set_operator_available(False))

        payload = {
            "location": "Pioneer Square, Portland, OR",
            "specific_questions": ["Is it busy?"],
            "client_id": "api_test_client_pause"
        }
        response = client.post("/v1/dispatch/verify", json=payload)
        assert response.status_code == 503
        assert "currently off-duty or paused" in response.json()["detail"]

    def test_dispatch_verify_rate_limit_429(self, client: TestClient):
        payload = {
            "location": "123 Main St, Gresham, OR",
            "specific_questions": ["Check store hours"],
            "client_id": "rate_limited_client"
        }
        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.49, "lon": -122.43}, None)):
            # First request succeeds
            r1 = client.post("/v1/dispatch/verify", json=payload)
            assert r1.status_code == 200

            # Immediate second request from same client triggers rate limit
            payload2 = {
                "location": "456 2nd St, Beaverton, OR",
                "specific_questions": ["Check store hours"],
                "client_id": "rate_limited_client"
            }
            r2 = client.post("/v1/dispatch/verify", json=payload2)
            assert r2.status_code == 429
            assert "Rate limit exceeded" in r2.json()["detail"]


class TestTaskStatusRoute:
    """Test GET /v1/tasks/{task_id} for not found, pending, and completed states."""

    def test_get_task_not_found(self, client: TestClient):
        response = client.get("/v1/tasks/pdx_nonexistent_999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Task not found"

    def test_get_task_pending(self, client: TestClient):
        import asyncio
        now = datetime.now(timezone.utc)
        task_id = "pdx_status_test_01"
        asyncio.run(create_task({
            "task_id": task_id,
            "idempotency_hash": "hash_status_01",
            "task_type": "physical_verification",
            "client_id": "client_status_test",
            "location": "Beaverton, OR",
            "specific_questions": ["Is shop open?"],
            "status": "pending_operator_review",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
        }))

        response = client.get(f"/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["status"] == "pending_operator_review"
        assert data["location"] == "Beaverton, OR"

    def test_get_task_completed_with_photo_url_rewriting(self, client: TestClient):
        import asyncio
        now = datetime.now(timezone.utc)
        task_id = "pdx_status_completed_01"
        asyncio.run(create_task({
            "task_id": task_id,
            "idempotency_hash": "hash_completed_01",
            "task_type": "physical_verification",
            "client_id": "client_status_test",
            "location": "Clackamas, OR",
            "specific_questions": ["Check parking"],
            "status": "accepted_in_progress",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=90)).isoformat(),
        }))
        asyncio.run(complete_task(
            task_id=task_id,
            photo_url="http://internal-host:8000/proof/test_proof.jpg",
            photo_metadata={"has_exif": True, "gps": {"lat": 45.4}},
            extracted_answers={"operator_notes": "Lots of open spots", "verified_on_site": True}
        ))

        # Test request with custom Host header
        response = client.get(
            f"/v1/tasks/{task_id}",
            headers={"Host": "api.groundtruth.test", "X-Forwarded-Proto": "https"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["completed_at"] is not None
        assert data["has_gps_metadata"] is True
        assert data["extracted_answers"]["verified_on_site"] is True
        # Verify photo_url rewriting using caller host
        assert data["photo_url"] == "https://api.groundtruth.test/proof/test_proof.jpg"


class TestTaskPhotoRoute:
    """Test GET /v1/tasks/{task_id}/photo streaming."""

    def test_get_photo_task_not_found(self, client: TestClient):
        response = client.get("/v1/tasks/pdx_missing_photo_task/photo")
        assert response.status_code == 404
        assert "Photo not available" in response.json()["detail"]

    def test_get_photo_no_photo_uploaded_yet(self, client: TestClient):
        import asyncio
        now = datetime.now(timezone.utc)
        task_id = "pdx_no_photo_01"
        asyncio.run(create_task({
            "task_id": task_id,
            "idempotency_hash": "hash_no_photo",
            "task_type": "physical_verification",
            "client_id": "client_test",
            "location": "Portland, OR",
            "status": "pending_operator_review",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
        }))

        response = client.get(f"/v1/tasks/{task_id}/photo")
        assert response.status_code == 404
        assert "Photo not available" in response.json()["detail"]

    def test_get_photo_file_missing_on_disk(self, client: TestClient):
        import asyncio
        now = datetime.now(timezone.utc)
        task_id = "pdx_missing_file_01"
        asyncio.run(create_task({
            "task_id": task_id,
            "idempotency_hash": "hash_miss_file",
            "task_type": "physical_verification",
            "client_id": "client_test",
            "location": "Portland, OR",
            "status": "completed",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
        }))
        asyncio.run(complete_task(
            task_id=task_id,
            photo_url="http://test/proof/non_existent_file.jpg",
            photo_metadata={},
            extracted_answers={}
        ))

        response = client.get(f"/v1/tasks/{task_id}/photo")
        assert response.status_code == 404
        assert "Photo file not found on disk" in response.json()["detail"]

    def test_get_photo_success_streaming(self, client: TestClient, isolated_env):
        import asyncio
        now = datetime.now(timezone.utc)
        task_id = "pdx_photo_success_01"
        proof_filename = f"{task_id}_proof.jpg"
        proof_path = isolated_env["proof_dir"] / proof_filename

        # Create a valid minimal test JPEG image on disk
        img = Image.new("RGB", (64, 64), color=(30, 144, 255))
        img.save(proof_path, format="JPEG")
        assert proof_path.exists()

        asyncio.run(create_task({
            "task_id": task_id,
            "idempotency_hash": "hash_photo_success",
            "task_type": "physical_verification",
            "client_id": "client_test",
            "location": "Portland, OR",
            "status": "completed",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
        }))
        asyncio.run(complete_task(
            task_id=task_id,
            photo_url=f"http://test/proof/{proof_filename}",
            photo_metadata={"has_exif": True},
            extracted_answers={"verified_on_site": True}
        ))

        response = client.get(f"/v1/tasks/{task_id}/photo")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert len(response.content) == proof_path.stat().st_size
        assert response.content == proof_path.read_bytes()


class TestSecurityAndAdditionalEndpoints:
    """Test API key enforcement, /v1/dispatch/storefront, and /v1/dispatch/custom."""

    def test_api_key_enforcement(self, client: TestClient, monkeypatch):
        import asyncio
        monkeypatch.setattr(config_module, "REQUIRE_API_KEY", True)

        payload = {
            "location": "Portland, OR",
            "specific_questions": ["Check door"],
            "client_id": "auth_client"
        }

        # 1. Missing API Key
        r1 = client.post("/v1/dispatch/verify", json=payload)
        assert r1.status_code == 401
        assert "Missing required X-API-Key header" in r1.json()["detail"]

        # 2. Invalid API Key
        r2 = client.post(
            "/v1/dispatch/verify",
            json=payload,
            headers={"X-API-Key": "gt_invalid_key_12345"}
        )
        assert r2.status_code == 403
        assert "Invalid or revoked API key" in r2.json()["detail"]

        # 3. Valid Generated API Key
        key_id, raw_key = asyncio.run(generate_api_key("test_agent_client"))
        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.5, "lon": -122.6}, None)):
            r3 = client.post(
                "/v1/dispatch/verify",
                json=payload,
                headers={"X-API-Key": raw_key}
            )
            assert r3.status_code == 200
            assert r3.json()["status"] == "pending_operator_review"

    def test_storefront_audit_endpoint(self, client: TestClient):
        payload = {
            "business_name": "Powell's City of Books",
            "address": "1005 W Burnside St",
            "specific_questions": ["Is the main entrance clear?"],
            "stated_purpose": "Commercial storefront audit",
            "client_id": "storefront_client"
        }
        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.523, "lon": -122.681}, None)):
            response = client.post("/v1/dispatch/storefront", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending_operator_review"
            assert data["task_id"].startswith("pdx_")

    def test_custom_physical_task_endpoint(self, client: TestClient):
        payload = {
            "location": "Pioneer Courthouse Square, Portland, OR",
            "proposed_action": "Count number of food trucks open at lunchtime",
            "stated_purpose": "Foot traffic research",
            "client_id": "custom_task_client"
        }
        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.518, "lon": -122.678}, None)):
            response = client.post("/v1/dispatch/custom", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending_operator_review"
            assert data["task_id"].startswith("cust_")
            assert "Custom physical task submitted" in data["instruction"]
