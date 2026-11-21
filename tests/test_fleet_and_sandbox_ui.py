"""Unit and integration test suite for Fleet Routing Engine and Sandbox UI Dashboard."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.fleet import (
    determine_zone,
    find_best_operator,
    seed_default_operators,
    DEFAULT_OPERATORS,
    haversine_km,
)
from src.db import (
    init_db,
    upsert_operator,
    get_operator,
    list_operators,
    update_operator_status,
)
from src.safety import validate_task_safety


class TestFleetZoneDeterminationAndRouting:
    """Test zone classification and operator matching by county and coordinates."""

    def test_haversine_km_calculation(self):
        # Distance between downtown Portland and Beaverton is approx 10-12 km
        dist = haversine_km(45.5200, -122.6800, 45.4871, -122.8037)
        assert 8.0 < dist < 15.0

    def test_determine_zone_by_keywords(self):
        assert determine_zone({"name": "Powell's City of Books, Portland, OR"}) == "central_portland"
        assert determine_zone({"location": "Nike World Headquarters, Beaverton, OR"}) == "west_washington"
        assert determine_zone({"display_name": "Gresham Station Shopping Center, Gresham, OR"}) == "east_multnomah"
        assert determine_zone({"address": "Clackamas Town Center, Clackamas, Oregon"}) == "south_clackamas"
        assert determine_zone({"location": "Hillsboro Downtown, Washington County"}) == "west_washington"
        assert determine_zone({"location": "Lake Oswego Millennium Park"}) == "south_clackamas"

    def test_determine_zone_by_coordinates(self):
        # Beaverton coords
        assert determine_zone({"lat": 45.4871, "lon": -122.8037}) == "west_washington"
        # Gresham coords
        assert determine_zone({"lat": 45.4998, "lon": -122.4312}) == "east_multnomah"
        # Clackamas coords
        assert determine_zone({"lat": 45.4076, "lon": -122.5694}) == "south_clackamas"
        # Central Portland coords
        assert determine_zone({"lat": 45.5231, "lon": -122.6816}) == "central_portland"

    @pytest.mark.asyncio
    async def test_seed_and_list_operators(self, initialized_db):
        await seed_default_operators()
        operators = await list_operators()
        assert len(operators) >= 4

        zones = {op["zone"] for op in operators}
        assert "central_portland" in zones
        assert "west_washington" in zones
        assert "east_multnomah" in zones
        assert "south_clackamas" in zones

    @pytest.mark.asyncio
    async def test_find_best_operator_central_portland(self, initialized_db):
        await seed_default_operators()
        geo_data = {
            "name": "Powell's City of Books, Portland, OR",
            "lat": 45.5231,
            "lon": -122.6816
        }
        operator = await find_best_operator(geo_data)
        assert operator is not None
        assert operator["zone"] == "central_portland"
        assert "Tobias" in operator["name"]

    @pytest.mark.asyncio
    async def test_find_best_operator_suburb_west_washington(self, initialized_db):
        await seed_default_operators()
        geo_data = {
            "name": "Nike World Headquarters, Beaverton, OR",
            "lat": 45.4871,
            "lon": -122.8037
        }
        operator = await find_best_operator(geo_data)
        assert operator is not None
        assert operator["zone"] == "west_washington"
        assert "Sarah" in operator["name"]

    @pytest.mark.asyncio
    async def test_find_best_operator_east_multnomah(self, initialized_db):
        await seed_default_operators()
        geo_data = {
            "name": "Gresham Station, Gresham, OR",
            "lat": 45.4998,
            "lon": -122.4312
        }
        operator = await find_best_operator(geo_data)
        assert operator is not None
        assert operator["zone"] == "east_multnomah"
        assert "Marcus" in operator["name"]

    @pytest.mark.asyncio
    async def test_find_best_operator_south_clackamas(self, initialized_db):
        await seed_default_operators()
        geo_data = {
            "name": "Clackamas Town Center, Clackamas, OR",
            "lat": 45.4076,
            "lon": -122.5694
        }
        operator = await find_best_operator(geo_data)
        assert operator is not None
        assert operator["zone"] == "south_clackamas"
        assert "Elena" in operator["name"]

    @pytest.mark.asyncio
    async def test_mock_mode_automatic_operator_binding(self, initialized_db):
        # Set all operators to off_duty
        await seed_default_operators()
        for op in DEFAULT_OPERATORS:
            await update_operator_status(op["operator_id"], "off_duty")

        # In mock mode, find_best_operator should automatically bind to a simulated operator
        with patch("src.fleet.is_mock_mode", return_value=True):
            geo_data = {"name": "Beaverton Library, Beaverton, OR"}
            op = await find_best_operator(geo_data)
            assert op is not None
            assert op["zone"] == "west_washington"
            assert op.get("mock") is True


class TestSafetyPolicyValidation:
    """Test safety heuristics rejecting surveillance and private residence tasks."""

    def test_safe_commercial_verification(self):
        is_safe, reason = validate_task_safety(
            location="1005 W Burnside St, Portland, OR",
            questions=["Is main entrance open?", "Photograph operating hours"],
            stated_purpose="Commercial due diligence"
        )
        assert is_safe is True
        assert reason is None

    def test_reject_private_residence(self):
        is_safe, reason = validate_task_safety(
            location="Private residence on SE Monroe St",
            questions=["Photograph the front door"],
            stated_purpose="Identity check"
        )
        assert is_safe is False
        assert "private resident" in reason.lower()

    def test_reject_license_plate_and_vehicle_tracking(self):
        is_safe, reason = validate_task_safety(
            location="Track blue sedan license plate at private residence",
            questions=["Follow car and report plate numbers"],
            stated_purpose="Surveillance"
        )
        assert is_safe is False
        assert "license plate" in reason.lower() or "surveillance" in reason.lower()


class TestSandboxUIDashboardAndEndpoints:
    """Test /sandbox HTML dashboard and real-time state endpoints."""

    def test_get_sandbox_html_returns_200(self, client: TestClient):
        response = client.get("/sandbox")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        html = response.text
        assert "GroundTruth Protocol" in html
        assert "Interactive Sandbox" in html
        assert "Interactive Dispatch Form" in html
        assert "Visual Task Lifecycle Stepper" in html
        assert "Proof Inspector" in html
        # Preset verifications
        assert "Powell's City of Books" in html
        assert "Nike World Headquarters" in html
        assert "Times Square" in html
        assert "private residence" in html

    def test_get_sandbox_state_endpoint(self, client: TestClient):
        response = client.get("/sandbox/api/state")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert "Node #001" in data["node"]
        assert "operator_count" in data
        assert data["operator_count"] >= 4
        assert "operators" in data
        assert "credit_balance" in data

    def test_get_fleet_operators_endpoint(self, client: TestClient):
        response = client.get("/api/fleet/operators")
        assert response.status_code == 200
        ops = response.json()
        assert isinstance(ops, list)
        assert len(ops) >= 4
        assert any(op["zone"] == "central_portland" for op in ops)
        assert any(op["zone"] == "west_washington" for op in ops)

    def test_sandbox_preset_valid_portland_core(self, client: TestClient):
        payload = {
            "location": "Powell's City of Books, 1005 W Burnside St, Portland, OR",
            "specific_questions": [
                "Confirm if main Burnside entrance doors are unlocked.",
                "Photograph posted store hours plaque."
            ],
            "stated_purpose": "Retail ground truth inspection",
            "client_id": "sandbox_tester_core"
        }
        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.5231, "lon": -122.6816, "name": payload["location"]}, None)):
            response = client.post("/v1/dispatch/verify", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending_operator_review"
            assert data["task_id"].startswith("pdx_")
            assert data["zone"] == "central_portland"
            assert "operator_assigned" in data

    def test_sandbox_preset_valid_suburb_routing(self, client: TestClient):
        payload = {
            "location": "Nike World Headquarters, 1 Bowerman Dr, Beaverton, OR 97005",
            "specific_questions": ["Verify security gate status"],
            "stated_purpose": "Suburban enterprise campus inspection",
            "client_id": "sandbox_tester_suburb"
        }
        with patch("src.geofence.validate_portland_location", return_value=(True, {"lat": 45.4871, "lon": -122.8037, "name": payload["location"]}, None)):
            response = client.post("/v1/dispatch/verify", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending_operator_review"
            assert data["zone"] == "west_washington"

    def test_sandbox_preset_geofence_rejection_triggers_400(self, client: TestClient):
        payload = {
            "location": "Times Square, New York, NY 10036",
            "specific_questions": ["Verify billboard status"],
            "client_id": "sandbox_tester_nyc",
            "strict": True
        }
        with patch("src.geofence.validate_portland_location", return_value=(False, None, "Location outside Portland coverage zone")):
            response = client.post("/v1/dispatch/verify", json=payload)
            assert response.status_code == 400
            assert "outside Portland coverage zone" in response.json()["detail"]

    def test_sandbox_preset_safety_rejection_triggers_400(self, client: TestClient):
        payload = {
            "location": "Track blue sedan license plate at private residence",
            "specific_questions": ["Identify vehicle owner"],
            "stated_purpose": "Surveillance test",
            "client_id": "sandbox_tester_safety"
        }
        response = client.post("/v1/dispatch/verify", json=payload)
        assert response.status_code == 400
        assert "safety policy" in response.json()["detail"].lower()
