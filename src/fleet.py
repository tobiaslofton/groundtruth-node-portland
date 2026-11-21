"""Multi-operator fleet registry and dispatch routing engine for GroundTruth Protocol."""
import math
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from src.config import TELEGRAM_OPERATOR_CHAT_ID
from src.db import upsert_operator, list_operators, get_operator, update_operator_status, count_operators
from src.mock import is_mock_mode

logger = logging.getLogger("ground_truth.fleet")

# Standard regional operating zones in the Portland Metropolitan Area
ZONES = {
    "central_portland": {
        "name": "Central Portland (Multnomah Core)",
        "centroid": (45.5200, -122.6800),
        "keywords": ["portland", "downtown", "pearl", "burnside", "hawthorne", "division", "alberta", "multnomah"]
    },
    "west_washington": {
        "name": "West Metro (Washington County)",
        "centroid": (45.4871, -122.8037),
        "keywords": ["beaverton", "hillsboro", "tigard", "aloha", "tualatin", "washington county", "nike"]
    },
    "east_multnomah": {
        "name": "East Metro (East Multnomah County)",
        "centroid": (45.4998, -122.4312),
        "keywords": ["gresham", "troutdale", "fairview", "wood village", "rockwood", "east multnomah"]
    },
    "south_clackamas": {
        "name": "South Metro (Clackamas County)",
        "centroid": (45.4076, -122.5694),
        "keywords": ["clackamas", "lake oswego", "milwaukie", "oregon city", "happy valley", "west linn", "wilsonville"]
    }
}

DEFAULT_OPERATORS = [
    {
        "operator_id": "op_tobias_001",
        "name": "Tobias Node #001 (Lead / Central)",
        "telegram_id": TELEGRAM_OPERATOR_CHAT_ID or 5081696001,
        "zone": "central_portland",
        "status": "available",
        "rating": 5.0,
        "lat": 45.5231,
        "lon": -122.6816,
    },
    {
        "operator_id": "op_sarah_002",
        "name": "Sarah K. (West Metro / Beaverton / Hillsboro)",
        "telegram_id": 900200002,
        "zone": "west_washington",
        "status": "available",
        "rating": 4.95,
        "lat": 45.4871,
        "lon": -122.8037,
    },
    {
        "operator_id": "op_marcus_003",
        "name": "Marcus T. (East Metro / Gresham)",
        "telegram_id": 900300003,
        "zone": "east_multnomah",
        "status": "available",
        "rating": 4.92,
        "lat": 45.4998,
        "lon": -122.4312,
    },
    {
        "operator_id": "op_elena_004",
        "name": "Elena R. (South Metro / Clackamas / Lake Oswego)",
        "telegram_id": 900400004,
        "zone": "south_clackamas",
        "status": "available",
        "rating": 4.98,
        "lat": 45.4076,
        "lon": -122.5694,
    },
]

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two GPS coordinates in kilometers."""
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c

async def seed_default_operators() -> None:
    """Seed initial protocol operators if none exist in SQLite."""
    count = await count_operators()
    if count == 0:
        logger.info("Seeding initial fleet operators into registry...")
        for op in DEFAULT_OPERATORS:
            await upsert_operator(op)
        logger.info("Seeded %d operators.", len(DEFAULT_OPERATORS))

def determine_zone(geo_data: Optional[Dict[str, Any]] = None) -> str:
    """
    Determine the county zone ('central_portland', 'west_washington', 'east_multnomah', 'south_clackamas')
    from coordinates and location metadata.
    """
    if not geo_data:
        return "central_portland"

    # Explicit override
    if "zone" in geo_data and geo_data["zone"] in ZONES:
        return geo_data["zone"]

    text_blob = ""
    for field in ("name", "display_name", "location", "address"):
        if field in geo_data and geo_data[field]:
            text_blob += f" {geo_data[field].lower()}"

    # 1. Text keyword matching
    if text_blob:
        for zone_key, zone_info in ZONES.items():
            if zone_key == "central_portland":
                continue  # Evaluate specific regional suburbs first
            if any(kw in text_blob for kw in zone_info["keywords"]):
                return zone_key

        if any(kw in text_blob for kw in ZONES["central_portland"]["keywords"]):
            return "central_portland"

    # 2. Nearest centroid coordinate matching
    lat = geo_data.get("lat")
    lon = geo_data.get("lon")
    if lat is not None and lon is not None:
        closest_zone = "central_portland"
        min_dist = float("inf")
        for zone_key, zone_info in ZONES.items():
            c_lat, c_lon = zone_info["centroid"]
            dist = haversine_km(float(lat), float(lon), c_lat, c_lon)
            if dist < min_dist:
                min_dist = dist
                closest_zone = zone_key
        return closest_zone

    return "central_portland"

async def find_best_operator(geo_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Routes an incoming task to the optimal available field operator based on zone and distance.
    In mock mode (is_mock_mode()), automatically binds to simulated field agents.
    """
    target_zone = determine_zone(geo_data)
    target_lat = geo_data.get("lat") if geo_data else None
    target_lon = geo_data.get("lon") if geo_data else None

    # Retrieve available operators
    available_ops = await list_operators(status="available")

    # If no operators in database or all off-duty, handle mock mode binding or auto-seeding
    if not available_ops:
        if is_mock_mode():
            # In mock mode, find matching simulated default operator
            for default_op in DEFAULT_OPERATORS:
                if default_op["zone"] == target_zone:
                    mock_op = dict(default_op)
                    mock_op["status"] = "available"
                    mock_op["mock"] = True
                    return mock_op
            # Fallback to first default operator
            mock_op = dict(DEFAULT_OPERATORS[0])
            mock_op["status"] = "available"
            mock_op["mock"] = True
            return mock_op
        else:
            # Seed and check if Tobias is available
            await seed_default_operators()
            available_ops = await list_operators(status="available")
            if not available_ops:
                return None

    # Prioritize operators in the target zone
    same_zone_ops = [op for op in available_ops if op["zone"] == target_zone]

    def op_score(op: Dict[str, Any]) -> Tuple[int, float, float]:
        # Sort key: (is_same_zone: higher better, -distance: higher better, rating: higher better)
        is_same = 1 if op["zone"] == target_zone else 0
        dist = 0.0
        if target_lat is not None and target_lon is not None and op.get("lat") and op.get("lon"):
            dist = haversine_km(float(target_lat), float(target_lon), float(op["lat"]), float(op["lon"]))
        else:
            # Use centroid distance
            c_lat, c_lon = ZONES[op["zone"]]["centroid"]
            t_lat = float(target_lat) if target_lat is not None else c_lat
            t_lon = float(target_lon) if target_lon is not None else c_lon
            dist = haversine_km(t_lat, t_lon, c_lat, c_lon)

        rating = float(op.get("rating") or 5.0)
        return (is_same, -dist, rating)

    candidate_ops = same_zone_ops if same_zone_ops else available_ops
    ranked_ops = sorted(candidate_ops, key=op_score, reverse=True)
    return ranked_ops[0] if ranked_ops else None
