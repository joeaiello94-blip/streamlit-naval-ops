import json
import math
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import requests

from .bathymetry import BathymetryService


@dataclass
class CollectorStats:
    ocean_points: int = 0
    land_points: int = 0
    total_points: int = 0
    bathy_sources: Dict[str, int] = None

    def __post_init__(self):
        if self.bathy_sources is None:
            self.bathy_sources = {}


class NavalDataCollector:
    """Collect weather, marine, astronomical, and bathymetry data for a grid."""

    def __init__(
        self,
        inputs: Dict[str, Any],
        timeout_s: int = 15,
        bathy_service: Optional[BathymetryService] = None,
    ):
        self.inputs = inputs
        self.timeout_s = timeout_s
        self.bathy_service = bathy_service or BathymetryService(timeout_s=timeout_s)

    @staticmethod
    def geocode_location(location: str, timeout_s: int = 15) -> Optional[Dict[str, Any]]:
        """Convert location name to lat/lon, or parse coordinates."""
        if ',' in location:
            try:
                parts = location.split(',')
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                return {
                    'lat': lat,
                    'lon': lon,
                    'name': f"Custom Location ({lat:.4f}, {lon:.4f})",
                }
            except Exception:
                pass

        try:
            geo_url = "https://geocoding-api.open-meteo.com/v1/search"
            response = requests.get(
                geo_url,
                params={"name": location, "count": 1},
                timeout=timeout_s,
            )
            response.raise_for_status()
            data = response.json()
            if data.get('results'):
                r0 = data['results'][0]
                return {'lat': r0['latitude'], 'lon': r0['longitude'], 'name': r0['name']}
            return None
        except Exception:
            return None

    @staticmethod
    def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        diff_lon = math.radians(lon2 - lon1)

        x = math.sin(diff_lon) * math.cos(lat2_rad)
        y = math.cos(lat1_rad) * math.sin(lat2_rad) - (
            math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(diff_lon)
        )

        initial_bearing = math.degrees(math.atan2(x, y))
        return (initial_bearing + 360) % 360

    def _is_in_sector(
        self,
        point_lat: float,
        point_lon: float,
        center_lat: float,
        center_lon: float,
        min_bearing: float,
        max_bearing: float,
    ) -> bool:
        bearing_to_point = self.calculate_bearing(center_lat, center_lon, point_lat, point_lon)
        if min_bearing > max_bearing:
            return bearing_to_point >= min_bearing or bearing_to_point <= max_bearing
        return min_bearing <= bearing_to_point <= max_bearing

    def generate_grid_points(
        self,
        center_lat: float,
        center_lon: float,
        radius_nm: float,
        grid_spacing_nm: float,
    ) -> List[Dict[str, float]]:
        """Generate 1nm grid within radius and within configured sector."""
        radius_deg = radius_nm * 1.0 / 60.0
        spacing_deg = grid_spacing_nm * 1.0 / 60.0

        min_sector = float(self.inputs.get('sector_min_bearing', 0))
        max_sector = float(self.inputs.get('sector_max_bearing', 360))

        points: List[Dict[str, float]] = []
        lat = center_lat - radius_deg
        while lat <= center_lat + radius_deg:
            lon = center_lon - radius_deg
            while lon <= center_lon + radius_deg:
                distance = math.sqrt((lat - center_lat) ** 2 + (lon - center_lon) ** 2)
                if distance <= radius_deg and self._is_in_sector(
                    lat, lon, center_lat, center_lon, min_sector, max_sector
                ):
                    points.append({'lat': lat, 'lon': lon})
                lon += spacing_deg
            lat += spacing_deg

        return points

    def get_regional_weather(self, lat: float, lon: float) -> Dict[str, Any]:
        """Weather at or near point (Open-Meteo)."""
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": (
                "temperature_2m,relative_humidity_2m,precipitation,weather_code,"
                "cloud_cover,visibility,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
            ),
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "knots",
        }

        # Try exact + offsets if needed
        offsets = [(0, 0), (0.5, 0), (-0.5, 0), (0, 0.5), (0, -0.5)]
        for dlat, dlon in offsets:
            try:
                r = requests.get(
                    url,
                    params={**params, "latitude": lat + dlat, "longitude": lon + dlon},
                    timeout=self.timeout_s,
                )
                r.raise_for_status()
                data = r.json()
                if data.get('current'):
                    return data['current']
            except Exception:
                continue

        # Conservative defaults
        return {
            'temperature_2m': 82,
            'relative_humidity_2m': 75,
            'precipitation': 0,
            'weather_code': 1,
            'cloud_cover': 40,
            'visibility': 10000,
            'wind_speed_10m': 15,
            'wind_direction_10m': 90,
            'wind_gusts_10m': 20,
        }

    def get_marine_data(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        url = "https://marine-api.open-meteo.com/v1/marine"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": (
                "wave_height,wave_direction,wave_period,wind_wave_height,"
                "swell_wave_height,ocean_current_velocity,ocean_current_direction"
            ),
            "length_unit": "imperial",
        }
        try:
            r = requests.get(url, params=params, timeout=self.timeout_s)
            r.raise_for_status()
            data = r.json()
            return data.get('current')
        except Exception:
            return None

    def get_astronomical_data(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "daily": "sunrise,sunset",
                "timezone": "auto",
                "start_date": today,
                "end_date": today,
            }
            r = requests.get(url, params=params, timeout=self.timeout_s)
            r.raise_for_status()
            data = r.json()
            if data.get('daily'):
                return {'sunrise': data['daily']['sunrise'][0], 'sunset': data['daily']['sunset'][0]}
            return None
        except Exception:
            return None

    @staticmethod
    def calculate_distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 3440.065
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        return R * c

    def collect(
        self,
        progress: Optional[Callable[[int, int, CollectorStats], None]] = None,
        rate_limit_s: float = 0.25,
    ) -> Dict[str, Any]:
        """Collect data. progress(i, n, stats) called during loop."""
        center = self.geocode_location(self.inputs['center_location'], timeout_s=self.timeout_s)
        if not center:
            raise ValueError("Could not process center_location")

        data: Dict[str, Any] = {"center": center}

        if self.inputs.get('target_location'):
            target = self.geocode_location(self.inputs['target_location'], timeout_s=self.timeout_s)
            if target:
                data['target'] = target

        region_weather = self.get_regional_weather(center['lat'], center['lon'])

        grid_points = self.generate_grid_points(
            center['lat'],
            center['lon'],
            float(self.inputs.get('radius_nm', 13)),
            float(self.inputs.get('grid_spacing_nm', 1.0)),
        )
        data['grid_points'] = grid_points

        stats = CollectorStats(total_points=len(grid_points))
        analyzed_points: List[Dict[str, Any]] = []

        for i, point in enumerate(grid_points):
            marine = self.get_marine_data(point['lat'], point['lon'])
            bathy = self.bathy_service.get_bathymetry(point['lat'], point['lon'])

            stats.bathy_sources[bathy.get('source', 'Unknown')] = stats.bathy_sources.get(
                bathy.get('source', 'Unknown'), 0
            ) + 1

            if not bathy.get('is_ocean', True):
                stats.land_points += 1
                if progress:
                    progress(i + 1, len(grid_points), stats)
                time.sleep(rate_limit_s)
                continue

            stats.ocean_points += 1

            point_data: Dict[str, Any] = {
                'lat': point['lat'],
                'lon': point['lon'],
                'weather': region_weather,
                'marine': marine,
                'bathymetry': bathy,
                'distance_from_center_nm': self.calculate_distance_nm(
                    center['lat'], center['lon'], point['lat'], point['lon']
                ),
            }

            if data.get('target'):
                point_data['distance_from_target_nm'] = self.calculate_distance_nm(
                    data['target']['lat'],
                    data['target']['lon'],
                    point['lat'],
                    point['lon'],
                )

            analyzed_points.append(point_data)

            if progress:
                progress(i + 1, len(grid_points), stats)

            # Gentle pacing for public APIs
            time.sleep(rate_limit_s)

        data['analyzed_points'] = analyzed_points

        astro = self.get_astronomical_data(center['lat'], center['lon'])
        if astro:
            data['astronomical'] = astro

        data['metadata'] = {
            "collected_at": datetime.now().isoformat(),
            "points_total": stats.total_points,
            "points_ocean": stats.ocean_points,
            "points_land": stats.land_points,
            "bathymetry_sources": stats.bathy_sources,
        }

        return data

    @staticmethod
    def save_json(path: str, payload: Dict[str, Any]) -> None:
        with open(path, 'w') as f:
            json.dump(payload, f, indent=2)
