"""Automated test suite for Portland Metro geofencing and keyword validation."""
from unittest.mock import patch
import pytest

from src.geofence import (
    is_portland_keyword_match,
    validate_portland_location,
    LAT_MIN,
    LAT_MAX,
    LON_MIN,
    LON_MAX,
)

class TestPortlandKeywordMatch:
    """Test is_portland_keyword_match with valid and invalid locations."""

    @pytest.mark.parametrize("location", [
        "1005 W Burnside St, Portland, OR",
        "Pioneer Courthouse Square, Portland, Oregon",
        "SW 5th Ave, Portland, OR 97204",
        "Beaverton Central Station, Beaverton, OR",
        "Nike World Headquarters, 1 Bowerman Dr, Beaverton, OR 97005",
        "Gresham Station Shopping Center, Gresham, OR",
        "123 Main St, Gresham, Oregon 97030",
        "Clackamas Town Center, Clackamas, OR",
        "Sunnyside Rd, Clackamas, Oregon",
        "Hillsboro Downtown, Hillsboro, OR 97124",
        "Tigard City Hall, Tigard, OR 97223",
        "Millennium Plaza Park, Lake Oswego, OR 97034",
        "Main St, Milwaukie, OR 97222",
        "Willamette Riverwalk, Oregon City, OR 97045",
        "Nyberg Woods, Tualatin, OR 97062",
        "Historic District, West Linn, OR 97068",
        "Town Center Loop, Wilsonville, OR 97070",
        "Sunnyside Rd, Happy Valley, OR 97086",
        # Zip codes in range 97001-97299
        "1000 Broadway, 97201",
        "Walker Rd, 97006",
        "Burnside St, 97214",
        # Oregon + Target county mentions
        "Multnomah County, OR",
        "Clackamas County, Oregon",
        "Washington County, OR",
    ])
    def test_valid_portland_metro_keywords(self, location: str):
        assert is_portland_keyword_match(location) is True, f"Expected '{location}' to match Portland metro"

    @pytest.mark.parametrize("location", [
        # Explicitly requested out-of-bounds locations
        "Times Square, New York, NY 10036",
        "Ocean Drive, South Beach, Miami, FL 33139",
        "6th Street, Downtown, Austin, TX 78701",
        "Pike Place Market, Seattle, WA 98101",
        "Oregon State Capitol, 900 Court St NE, Salem, OR 97301",
        # Other outside locations
        "Millennium Park, Chicago, IL 60601",
        "Fisherman's Wharf, San Francisco, CA 94133",
        "Space Needle, Seattle, WA",
        "Broadway, Nashville, TN",
        "Eugene Downtown, Eugene, OR 97401",
        "Bend Old Mill, Bend, OR 97702",
        "Medford, OR 97501",
    ])
    def test_rejection_of_out_of_bounds_keywords(self, location: str):
        assert is_portland_keyword_match(location) is False, f"Expected '{location}' to be rejected"


class TestValidatePortlandLocation:
    """Test validate_portland_location with geocoding responses, bounding box checks, and fallbacks."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("location_name,lat,lon", [
        ("Portland Downtown", 45.5152, -122.6784),
        ("Beaverton Central", 45.4871, -122.8037),
        ("Gresham Station", 45.4998, -122.4312),
        ("Clackamas Town Center", 45.4076, -122.5694),
        ("Hillsboro", 45.5229, -122.9898),
        ("Lake Oswego", 45.4207, -122.6706),
        # Exact bounding box boundaries
        ("Min Bounding Point", LAT_MIN, -122.65),
        ("Max Bounding Point", LAT_MAX, -122.65),
        ("West Bounding Point", 45.50, LON_MIN),
        ("East Bounding Point", 45.50, LON_MAX),
    ])
    async def test_valid_in_bounds_geocodes(self, location_name: str, lat: float, lon: float):
        mock_resp = [{
            "lat": str(lat),
            "lon": str(lon),
            "display_name": f"{location_name}, Oregon, USA"
        }]
        with patch("src.geofence._fetch_nominatim_sync", return_value=mock_resp):
            is_valid, geo_data, error_msg = await validate_portland_location(location_name)
            assert is_valid is True
            assert error_msg is None
            assert geo_data is not None
            assert geo_data["lat"] == lat
            assert geo_data["lon"] == lon

    @pytest.mark.asyncio
    @pytest.mark.parametrize("location_name,lat,lon", [
        ("New York, NY", 40.7128, -74.0060),
        ("Miami, FL", 25.7617, -80.1918),
        ("Austin, TX", 30.2672, -97.7431),
        ("Seattle, WA", 47.6062, -122.3321),
        ("Salem, OR", 44.9429, -123.0351),
        # Points just outside the bounding box
        ("Just North", LAT_MAX + 0.05, -122.65),
        ("Just South", LAT_MIN - 0.05, -122.65),
        ("Just West", 45.50, LON_MIN - 0.05),
        ("Just East", 45.50, LON_MAX + 0.05),
    ])
    async def test_rejection_of_out_of_bounds_geocodes(self, location_name: str, lat: float, lon: float):
        mock_resp = [{
            "lat": str(lat),
            "lon": str(lon),
            "display_name": f"{location_name}, USA"
        }]
        with patch("src.geofence._fetch_nominatim_sync", return_value=mock_resp):
            is_valid, geo_data, error_msg = await validate_portland_location(location_name)
            assert is_valid is False
            assert geo_data is None
            assert error_msg is not None
            assert "outside Node #001's Portland coverage zone" in error_msg

    @pytest.mark.asyncio
    async def test_empty_nominatim_with_portland_keyword_fallback(self):
        """When Nominatim returns empty, fallback should accept valid Portland keyword."""
        with patch("src.geofence._fetch_nominatim_sync", return_value=[]):
            is_valid, geo_data, error_msg = await validate_portland_location("Powell's City of Books, Portland, OR")
            assert is_valid is True
            assert error_msg is None
            assert geo_data is not None
            assert geo_data.get("fallback") is True

    @pytest.mark.asyncio
    async def test_empty_nominatim_with_non_portland_rejection(self):
        """When Nominatim returns empty, non-Portland location must be rejected."""
        with patch("src.geofence._fetch_nominatim_sync", return_value=[]):
            is_valid, geo_data, error_msg = await validate_portland_location("Statue of Liberty, New York, NY")
            assert is_valid is False
            assert geo_data is None
            assert "Could not verify location" in error_msg

    @pytest.mark.asyncio
    async def test_nominatim_network_exception_fallback(self):
        """When Nominatim fails (offline/timeout), fallback handles gracefully."""
        with patch("src.geofence._fetch_nominatim_sync", side_effect=OSError("Network unreachable")):
            # Valid Portland keyword should pass via fallback
            is_valid, geo_data, error_msg = await validate_portland_location("Beaverton Town Square, Beaverton, OR")
            assert is_valid is True
            assert geo_data.get("fallback") is True
            assert error_msg is None

            # Out of bounds should fail
            is_valid, geo_data, error_msg = await validate_portland_location("Pike Place, Seattle, WA")
            assert is_valid is False
            assert geo_data is None
            assert "Could not verify location" in error_msg
