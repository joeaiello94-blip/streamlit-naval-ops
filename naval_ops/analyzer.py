import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


DEFAULT_GUN_RANGE_NM = 13.0  # Mk45 5" (planning factor)


@dataclass
class ScoreBreakdown:
    overall: float
    weather: float
    sea_state: float
    depth: float
    flight_ops: float
    fire_support: float
    distance: float


class NavalOperationsAnalyzer:
    """Score analyzed points for suitability based on mission and user thresholds."""

    def __init__(self, inputs: Dict[str, Any], data: Dict[str, Any]):
        self.inputs = inputs
        self.data = data
        self.scored_points: List[Dict[str, Any]] = []

    def _thresholds(self) -> Dict[str, Any]:
        return self.inputs.get("weather_thresholds", {}) or {}

    def score_weather(self, weather: Optional[Dict[str, Any]]) -> float:
        if not weather:
            return 0.0

        th = self._thresholds()
        max_wind = float(th.get("max_wind_speed_kts", 25))
        min_vis_m = float(th.get("min_visibility_m", 5000))
        max_cloud = float(th.get("max_cloud_cover_pct", 75))

        wind = float(weather.get("wind_speed_10m", 0))
        vis = float(weather.get("visibility", 0))
        cloud = float(weather.get("cloud_cover", 0))
        precip = float(weather.get("precipitation", 0))

        if wind > max_wind:
            return 0.0
        if vis < min_vis_m:
            return 0.0
        if cloud > max_cloud:
            # still possible, but heavily penalize
            cloud_penalty = 40.0
        else:
            cloud_penalty = (cloud / max(1.0, max_cloud)) * 20.0

        score = 100.0
        score -= (wind / max_wind) * 30.0
        score -= cloud_penalty

        if precip > 5:
            score -= 30.0
        elif precip > 0:
            score -= 10.0

        # visibility bonus (cap)
        score += min(10.0, (vis - min_vis_m) / max(1.0, min_vis_m) * 10.0)

        return max(0.0, min(100.0, score))

    def score_sea_state(self, marine: Optional[Dict[str, Any]]) -> float:
        if not marine:
            return 50.0

        th = self._thresholds()
        max_wave = float(th.get("max_wave_height_ft", 6))

        wave = float(marine.get("wave_height", 0) or 0)
        swell = float(marine.get("swell_wave_height", 0) or 0)
        current = float(marine.get("ocean_current_velocity", 0) or 0)

        if wave > max_wave:
            return 0.0

        score = 100.0
        score -= (wave / max_wave) * 40.0

        if swell > 6:
            score -= 20.0
        elif swell > 3:
            score -= 10.0

        if current > 2:
            score -= 15.0

        return max(0.0, min(100.0, score))

    def score_depth(self, bathy: Optional[Dict[str, Any]], vessels: List[Dict[str, Any]]) -> float:
        if not bathy:
            return 50.0
        if not bathy.get("is_ocean", True):
            return 0.0

        depth_ft = float(bathy.get("depth_ft", 0) or 0)
        min_depth_required = max(float(v.get("min_depth_ft", 20) or 20) for v in vessels) if vessels else 20.0

        if depth_ft < min_depth_required:
            return 0.0

        # Ideal band: min_depth_required .. 300ft
        if min_depth_required <= depth_ft <= 300:
            return 100.0
        if depth_ft > 300:
            return 80.0
        # between min and ideal
        return max(0.0, min(100.0, (depth_ft / 50.0) * 100.0))

    def score_flight_ops(self, weather: Optional[Dict[str, Any]], marine: Optional[Dict[str, Any]], vessels: List[Dict[str, Any]]) -> float:
        # If no flight deck in formation, deprioritize but still score environment
        has_flight = any(v.get("has_flight_deck") for v in vessels)
        if not has_flight:
            return 0.0
        if not weather or not marine:
            return 0.0

        wind = float(weather.get("wind_speed_10m", 0) or 0)
        vis = float(weather.get("visibility", 0) or 0)
        cloud = float(weather.get("cloud_cover", 0) or 0)
        precip = float(weather.get("precipitation", 0) or 0)
        wave = float(marine.get("wave_height", 0) or 0)

        score = 100.0

        if wind < 10:
            score -= 20.0
        elif wind <= 25:
            score -= 0.0
        elif wind <= 35:
            score -= 30.0
        else:
            return 0.0

        if vis < 3000:
            return 0.0
        if vis < 5000:
            score -= 30.0

        if cloud > 80:
            score -= 30.0
        elif cloud > 50:
            score -= 15.0

        if wave > 6:
            score -= 40.0
        elif wave > 4:
            score -= 20.0

        if precip > 2:
            score -= 40.0
        elif precip > 0:
            score -= 20.0

        return max(0.0, min(100.0, score))

    def _max_gun_range_nm(self, vessels: List[Dict[str, Any]]) -> float:
        # User may extend later, but default based on presence of 5" gun
        if any(v.get("has_5_inch_gun") for v in vessels):
            return DEFAULT_GUN_RANGE_NM
        return 0.0

    def score_fire_support(self, point: Dict[str, Any], vessels: List[Dict[str, Any]]) -> float:
        # If no gun in formation, return neutral-low
        max_gun = self._max_gun_range_nm(vessels)
        if max_gun <= 0:
            return 0.0

        target = self.data.get("target")
        if not target:
            return 70.0

        dist = float(point.get("distance_from_target_nm", 1e9) or 1e9)
        if dist <= max_gun * 0.7:
            score = 100.0
        elif dist <= max_gun:
            score = 80.0
        else:
            return 0.0

        depth = float(point.get("bathymetry", {}).get("depth_ft", 0) or 0)
        if depth < 30:
            score -= 40.0

        return max(0.0, min(100.0, score))

    def score_distance_constraints(self, point: Dict[str, Any]) -> float:
        # Placeholder: uses distance from center as proxy until shoreline data integrated
        dist = float(point.get("distance_from_center_nm", 0) or 0)
        min_dist = float(self.inputs.get("min_distance_shore_nm", 5) or 5)
        max_dist = float(self.inputs.get("max_distance_shore_nm", 50) or 50)

        if dist < min_dist or dist > max_dist:
            return 20.0
        return 100.0

    def _weights_for_mission(self, mission: str) -> Dict[str, float]:
        # inputs from planner: amphibious_landing, naval_gunfire_support, flight_operations, maritime_interdiction, humanitarian_assistance
        if mission == "amphibious_landing":
            return {"weather": 0.15, "sea_state": 0.25, "depth": 0.15, "flight_ops": 0.20, "fire_support": 0.15, "distance": 0.10}
        if mission == "naval_gunfire_support":
            return {"weather": 0.15, "sea_state": 0.15, "depth": 0.15, "flight_ops": 0.05, "fire_support": 0.40, "distance": 0.10}
        if mission == "flight_operations":
            return {"weather": 0.20, "sea_state": 0.25, "depth": 0.15, "flight_ops": 0.30, "fire_support": 0.05, "distance": 0.05}
        # Default / others
        return {"weather": 0.20, "sea_state": 0.20, "depth": 0.15, "flight_ops": 0.15, "fire_support": 0.20, "distance": 0.10}

    def calculate_scores(self, point: Dict[str, Any]) -> ScoreBreakdown:
        vessels = self.inputs.get("vessels", []) or []

        weather = self.score_weather(point.get("weather"))
        sea = self.score_sea_state(point.get("marine"))
        depth = self.score_depth(point.get("bathymetry"), vessels)
        flight = self.score_flight_ops(point.get("weather"), point.get("marine"), vessels)
        fire = self.score_fire_support(point, vessels)
        dist = self.score_distance_constraints(point)

        mission = self.inputs.get("primary_mission", "balanced")
        w = self._weights_for_mission(mission)

        overall = (
            weather * w["weather"]
            + sea * w["sea_state"]
            + depth * w["depth"]
            + flight * w["flight_ops"]
            + fire * w["fire_support"]
            + dist * w["distance"]
        )

        return ScoreBreakdown(
            overall=round(float(overall), 1),
            weather=round(float(weather), 1),
            sea_state=round(float(sea), 1),
            depth=round(float(depth), 1),
            flight_ops=round(float(flight), 1),
            fire_support=round(float(fire), 1),
            distance=round(float(dist), 1),
        )

    def analyze(self) -> List[Dict[str, Any]]:
        points = self.data.get("analyzed_points", []) or []
        scored: List[Dict[str, Any]] = []

        for p in points:
            scores = self.calculate_scores(p)
            scored.append(
                {
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "scores": scores.__dict__,
                    "weather": p.get("weather"),
                    "marine": p.get("marine"),
                    "bathymetry": p.get("bathymetry"),
                    "distance_from_center_nm": p.get("distance_from_center_nm"),
                    "distance_from_target_nm": p.get("distance_from_target_nm"),
                }
            )

        scored.sort(key=lambda x: x["scores"]["overall"], reverse=True)
        self.scored_points = scored
        return scored

    def export_json(self, path: str = "naval_ops_analysis.json") -> str:
        output = {
            "metadata": {
                "analysis_time": datetime.now().isoformat(),
                "center_location": self.inputs.get("center_location"),
                "mission": self.inputs.get("primary_mission"),
                "vessels": [v.get("type") for v in (self.inputs.get("vessels") or [])],
            },
            "scored_locations": self.scored_points,
        }
        with open(path, "w") as f:
            json.dump(output, f, indent=2)
        return path
