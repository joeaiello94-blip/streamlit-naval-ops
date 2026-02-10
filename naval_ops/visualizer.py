from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import folium
from folium.plugins import MarkerCluster


def _score_to_color(score: float) -> str:
    # Simple 5-bin scheme
    if score >= 85:
        return "green"
    if score >= 70:
        return "blue"
    if score >= 55:
        return "orange"
    if score >= 40:
        return "red"
    return "darkred"


def build_map(
    inputs: Dict[str, Any],
    scored_points: List[Dict[str, Any]],
    center: Optional[Dict[str, float]] = None,
    max_points: int = 1200,
) -> folium.Map:
    """Return a Folium map for display in Streamlit."""

    if center is None:
        cc = inputs.get("center_coords") or {}
        center = {"lat": float(cc.get("lat", 0.0)), "lon": float(cc.get("lon", 0.0))}

    m = folium.Map(location=[center["lat"], center["lon"]], zoom_start=10, control_scale=True)

    # Center marker
    folium.Marker(
        [center["lat"], center["lon"]],
        popup="Center",
        icon=folium.Icon(icon="home"),
    ).add_to(m)

    # Target marker
    target = inputs.get("target_location")
    if target and isinstance(target, str) and "," in target:
        try:
            lat_s, lon_s = target.split(",")
            tlat, tlon = float(lat_s.strip()), float(lon_s.strip())
            folium.Marker(
                [tlat, tlon],
                popup="Target",
                icon=folium.Icon(color="purple", icon="flag"),
            ).add_to(m)
        except Exception:
            pass

    # Hazards
    for h in inputs.get("known_hazards") or []:
        try:
            folium.Circle(
                location=[h["lat"], h["lon"]],
                radius=float(h.get("radius_nm", 1.0)) * 1852,
                popup=f"Hazard: {h.get('type','Unknown')}",
                color="black",
                fill=True,
                fill_opacity=0.2,
            ).add_to(m)
        except Exception:
            continue

    # Beach lateral limits
    beaches = inputs.get("additional_beaches") or []
    for b in beaches:
        try:
            a = b["lateral_limit_a"]
            c = b["lateral_limit_b"]
            folium.PolyLine(
                locations=[[a["lat"], a["lon"]], [c["lat"], c["lon"]]],
                tooltip=f"Beach: {b.get('name','Beach')}",
                color="cyan",
                weight=4,
            ).add_to(m)
        except Exception:
            continue

    # Points
    cluster = MarkerCluster(name="Scored Points").add_to(m)

    points = scored_points[:max_points] if len(scored_points) > max_points else scored_points

    for p in points:
        s = float(p.get("scores", {}).get("overall", 0))
        color = _score_to_color(s)
        depth = p.get("bathymetry", {}).get("depth_ft")
        popup = f"Score: {s}/100"
        if depth is not None:
            popup += f"<br>Depth: {depth:.0f} ft"
        if p.get("distance_from_center_nm") is not None:
            popup += f"<br>Dist (center): {p['distance_from_center_nm']:.1f} nm"

        folium.CircleMarker(
            location=[p["lat"], p["lon"]],
            radius=4,
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=folium.Popup(popup, max_width=250),
        ).add_to(cluster)

    # Best point
    if scored_points:
        best = scored_points[0]
        folium.Marker(
            [best["lat"], best["lon"]],
            popup=f"Best location: {best['scores']['overall']}/100",
            icon=folium.Icon(color="green", icon="star"),
        ).add_to(m)

    folium.LayerControl().add_to(m)
    return m
