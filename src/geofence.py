"""Geocoding and bounding box validation for Portland Metro area."""
import asyncio
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger("ground_truth.geofence")

# Portland Metropolitan Bounding Box (Multnomah, Washington, Clackamas counties)
LAT_MIN = 45.20
LAT_MAX = 45.72
LON_MIN = -123.05
LON_MAX = -122.30

PORTLAND_METRO_CITIES = {
    "portland", "beaverton", "hillsboro", "gresham", "tigard", "lake oswego", 
    "milwaukie", "oregon city", "tualatin", "west linn", "wilsonville", "clackamas", "happy valley"
}

def is_portland_keyword_match(text: str) -> bool:
    """Validate location using exact city names, Portland zip codes, or county mentions."""
    loc = text.lower()
    # 1. Check known Portland metro municipalities
    if any(city in loc for city in PORTLAND_METRO_CITIES):
        return True
    # 2. Check Portland Metro zip codes (97001–97299)
    if re.search(r"\b97[012]\d{2}\b", loc):
        return True
    # 3. Check exact state mention with a target county
    if re.search(r"\b(or|oregon)\b", loc) and any(county in loc for county in ("multnomah", "clackamas", "washington county")):
        return True
    return False

def _fetch_nominatim_sync(url: str, headers: dict) -> list:
    """Synchronous Nominatim HTTP request."""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())

async def validate_portland_location(location_str: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Validate that an address or landmark falls within the Portland Metro coverage area.
    Returns (is_valid, geocode_data, error_message).
    """
    encoded_loc = urllib.parse.quote(location_str)
    url = f"https://nominatim.openstreetmap.org/search?q={encoded_loc}&format=json&limit=1&countrycodes=us"
    headers = {"User-Agent": "GroundTruthProtocol-Node001/1.0 (tobias@algernontechnology.com)"}

    try:
        data = await asyncio.to_thread(_fetch_nominatim_sync, url, headers)
        if not data:
            if is_portland_keyword_match(location_str):
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
        if is_portland_keyword_match(location_str):
            return True, {"name": location_str, "fallback": True}, None
        return False, None, f"Could not verify location '{location_str}' within Portland coverage zone."
