import math
from typing import Any, Dict, List, Tuple


def calculate_midpoint(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
    """Simple arithmetic midpoint."""
    return (lat1 + lat2) / 2.0, (lon1 + lon2) / 2.0


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2 in degrees (0-360)."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    diff_lon = math.radians(lon2 - lon1)

    x = math.sin(diff_lon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - (
        math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(diff_lon)
    )

    initial_bearing = math.degrees(math.atan2(x, y))
    return (initial_bearing + 360.0) % 360.0


def calculate_perpendicular_bearing(bearing: float) -> float:
    """90 degrees clockwise."""
    return (bearing + 90.0) % 360.0


def build_derived_geometry(inputs: Dict) -> Dict:
    """Adds center point, direction of attack, and 180-degree sector to inputs."""
    a = inputs["lateral_limit_a"]
    b = inputs["lateral_limit_b"]

    center_lat, center_lon = calculate_midpoint(a["lat"], a["lon"], b["lat"], b["lon"])
    inputs["center_coords"] = {"lat": center_lat, "lon": center_lon}
    inputs["center_location"] = f"{center_lat:.4f}, {center_lon:.4f}"

    lateral_bearing = calculate_bearing(a["lat"], a["lon"], b["lat"], b["lon"])
    doa = calculate_perpendicular_bearing(lateral_bearing)
    inputs["direction_of_attack"] = doa

    inputs["sector_min_bearing"] = (doa - 90.0) % 360.0
    inputs["sector_max_bearing"] = (doa + 90.0) % 360.0

    return inputs


def build_inputs(
    primary_mission: str,
    lateral_limit_a: Dict[str, float],
    lateral_limit_b: Dict[str, float],
    target_location: str | None,
    additional_beaches: list[Dict],
    known_hazards: list[Dict],
    vessels: list[Dict],
    connectors: list[Dict],
    operation_start_time: str,
    operation_duration_hours: float,
    time_of_day_preference: str,
    weather_thresholds: Dict,
    radius_nm: float = 13.0,
    grid_spacing_nm: float = 1.0,
) -> Dict:
    """Build a complete inputs dict for downstream modules."""
    inputs: Dict[str, Any] = {
        "primary_mission": primary_mission,
        "lateral_limit_a": lateral_limit_a,
        "lateral_limit_b": lateral_limit_b,
        "target_location": target_location or "",
        "additional_beaches": additional_beaches or [],
        "known_hazards": known_hazards or [],
        "vessels": vessels or [],
        "connectors": connectors or [],
        "operation_start_time": operation_start_time,
        "operation_duration_hours": operation_duration_hours,
        "time_of_day_preference": time_of_day_preference,
        "weather_thresholds": weather_thresholds,
        "radius_nm": radius_nm,
        "grid_spacing_nm": grid_spacing_nm,
    }
    inputs = build_derived_geometry(inputs)
    return inputs
