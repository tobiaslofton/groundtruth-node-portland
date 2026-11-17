"""Geocoding and bounding box validation for Portland Metro area."""
import json
import logging
import urllib.parse
import urllib.request
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger("ground_truth.geofence")

# Portland Metropolitan Bounding Box (Multnomah, Washington, Clackamas counties)
LAT_MIN = 45.20
LAT_MAX = 45.72
LON_MIN = -123.05
LON_MAX = -122.30

async def validate_portland_location(location_str: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Validate that an address or landmark falls within the Portland Metro coverage area.
    Returns (is_valid, geocode_data, error_message).
    """
    encoded_loc = urllib.parse.quote(location_str)
    url = f"https://nominatim.openstreetmap.org/search?q={encoded_loc}&format=json&limit=1&countrycodes=us"
    headers = {"User-Agent": "GroundTruthProtocol-Node001/1.0 (tobias@algernontechnology.com)"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
            if not data:
                # If geocoder can't resolve, check if "portland" or local county is in string
                loc_lower = location_str.lower()
                if any(k in loc_lower for k in ("portland", "beaverton", "hillsboro", "gresham", "tigard", "lake oswego", "milwaukie", "oregon city", "or 97")):
                    return True, {"lat": 45.5152, "lon": -122.6784, "name": location_str, "fallback": True}, None
                return False, None, f"Could not verify location '{location_str}' within the Portland, OR metropolitan area."

            first_match = data[0]
            lat = float(first_match["lat"])
            lon = float(first_match["lon"])

            # Check bounding box
            if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
                return True, {
                    "lat": lat,
                    "lon": lon,
                    "display_name": first_match.get("display_name", location_str)
                }, None
            else:
                return False, None, (
                    f"Location '{location_str}' resolves to coordinates ({lat:.4f}, {lon:.4f}), "
                    "which is outside Node #001's Portland coverage zone. Only Multnomah, Clackamas, and Washington counties are supported."
                )

    except Exception as e:
        logger.warning("Geocoding lookup failed for '%s': %s. Falling back to keyword check.", location_str, e)
        # Fallback to local keyword check on geocoder timeout
        loc_lower = location_str.lower()
        if any(k in loc_lower for k in ("portland", "or", "oregon", "beaverton", "gresham", "clackamas", "972")):
            return True, {"name": location_str, "fallback": True}, None
        return False, None, f"Could not verify location '{location_str}' within Portland coverage zone."
