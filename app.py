import json
from typing import Any, Dict, List

import streamlit as st
from streamlit_folium import st_folium

from naval_ops.planner import build_inputs
from naval_ops.collector import NavalDataCollector
from naval_ops.analyzer import NavalOperationsAnalyzer
from naval_ops.visualizer import build_map


st.set_page_config(page_title="Naval Ops Planner", layout="wide")

st.title("Naval Operations Planner")
st.caption("Streamlit-first toolchain: plan → collect → analyze → visualize")


# -------------------------
# Helpers
# -------------------------

def _json_download_button(label: str, data: Dict[str, Any], filename: str):
    st.download_button(
        label,
        data=json.dumps(data, indent=2),
        file_name=filename,
        mime="application/json",
    )


def _parse_latlon(text: str) -> Dict[str, float]:
    lat_s, lon_s = text.split(",")
    return {"lat": float(lat_s.strip()), "lon": float(lon_s.strip())}


# -------------------------
# Sidebar: Inputs
# -------------------------

with st.sidebar:
    st.header("Inputs")

    mission = st.selectbox(
        "Primary mission",
        options=[
            "amphibious_landing",
            "naval_gunfire_support",
            "flight_operations",
            "maritime_interdiction",
            "humanitarian_assistance",
        ],
        index=0,
    )

    st.subheader("Lateral limits")
    st.write("Define Area of Operations left and right boundaries.")

    ll_a = st.text_input("Lateral Limit A (lat, lon)", value="11.8269, 92.5228")
    ll_b = st.text_input("Lateral Limit B (lat, lon)", value="11.5347, 92.5903")

    st.subheader("Target")
    target_location = st.text_input("Target location (optional, lat, lon)", value="11.6689, 92.5916")

    st.subheader("Weather thresholds")
    max_wind = st.number_input("Max wind speed (kts)", min_value=0.0, max_value=80.0, value=25.0, step=1.0)
    max_waves = st.number_input("Max wave height (ft)", min_value=0.0, max_value=30.0, value=6.0, step=0.5)
    min_vis_m = st.number_input("Min visibility (m)", min_value=0.0, max_value=20000.0, value=5000.0, step=500.0)
    max_cloud = st.number_input("Max cloud cover (%)", min_value=0.0, max_value=100.0, value=75.0, step=1.0)

    st.subheader("Analysis grid")
    radius_nm = st.number_input("Radius (nm)", min_value=1.0, max_value=50.0, value=13.0, step=1.0)
    grid_spacing_nm = st.number_input("Grid spacing (nm)", min_value=0.25, max_value=5.0, value=1.0, step=0.25)

    st.subheader("Vessels")
    st.write("Add up to 6 vessels.")

    vessel_presets = {
        "LHA/LHD": {"type": "LHA/LHD", "draft_ft": 27, "min_depth_ft": 65, "length_ft": 844},
        "LPD": {"type": "LPD", "draft_ft": 23, "min_depth_ft": 55, "length_ft": 684},
        "LSD": {"type": "LSD", "draft_ft": 19, "min_depth_ft": 45, "length_ft": 609},
        "DDG": {"type": "DDG", "draft_ft": 20.5, "min_depth_ft": 50, "length_ft": 509},
        "LCS": {"type": "LCS", "draft_ft": 14.5, "min_depth_ft": 35, "length_ft": 388},
    }

    vessel_count = st.number_input("Number of vessels", min_value=1, max_value=6, value=3, step=1)
    vessels: List[Dict[str, Any]] = []

    for i in range(int(vessel_count)):
        st.markdown(f"**Vessel {i+1}**")
        preset = st.selectbox(f"Preset {i+1}", options=list(vessel_presets.keys()) + ["Custom"], index=min(i, len(vessel_presets)-1))
        if preset != "Custom":
            v = vessel_presets[preset].copy()
            v["name"] = st.text_input(f"Name {i+1}", value=preset, key=f"v_name_{i}")
            v["has_flight_deck"] = st.checkbox(f"Flight deck {i+1}", value=preset in ["LHA/LHD", "LPD", "LSD"], key=f"v_fd_{i}")
            v["has_well_deck"] = st.checkbox(f"Well deck {i+1}", value=preset in ["LHA/LHD", "LPD", "LSD"], key=f"v_wd_{i}")
            v["has_5_inch_gun"] = st.checkbox(f"5-inch gun {i+1}", value=preset in ["DDG", "LSD"], key=f"v_gun_{i}")
        else:
            v = {
                "type": st.text_input(f"Type {i+1}", value="Custom", key=f"v_type_{i}"),
                "name": st.text_input(f"Name {i+1}", value=f"Vessel {i+1}", key=f"v_name_{i}"),
                "draft_ft": st.number_input(f"Draft (ft) {i+1}", min_value=0.0, max_value=80.0, value=20.0, key=f"v_draft_{i}"),
                "min_depth_ft": st.number_input(f"Min depth (ft) {i+1}", min_value=0.0, max_value=300.0, value=50.0, key=f"v_mindep_{i}"),
                "length_ft": st.number_input(f"Length (ft) {i+1}", min_value=0.0, max_value=1500.0, value=500.0, key=f"v_len_{i}"),
                "has_flight_deck": st.checkbox(f"Flight deck {i+1}", value=False, key=f"v_fd_{i}"),
                "has_well_deck": st.checkbox(f"Well deck {i+1}", value=False, key=f"v_wd_{i}"),
                "has_5_inch_gun": st.checkbox(f"5-inch gun {i+1}", value=False, key=f"v_gun_{i}"),
            }
        vessels.append(v)

    st.subheader("Known hazards")
    hazard_text = st.text_area(
        "One per line: lat, lon, radius_nm, type",
        value="11.6339, 92.5758, 2, wreck",
        height=90,
    )

    st.subheader("Additional beaches")
    beaches_text = st.text_area(
        "One per line: name, latA, lonA, latB, lonB",
        value="Green, 11.6689, 92.5916, 11.6533, 92.5992\nBlue, 11.62, 92.6089, 11.6083, 92.6058",
        height=90,
    )

    run_button = st.button("Run analysis", type="primary")


# -------------------------
# Build inputs dict
# -------------------------

def _parse_hazards(text: str) -> List[Dict[str, Any]]:
    hazards: List[Dict[str, Any]] = []
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        hazards.append(
            {
                "lat": float(parts[0]),
                "lon": float(parts[1]),
                "radius_nm": float(parts[2]),
                "type": parts[3],
                "source": "User Input",
            }
        )
    return hazards


def _parse_beaches(text: str) -> List[Dict[str, Any]]:
    beaches: List[Dict[str, Any]] = []
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        name = parts[0]
        beaches.append(
            {
                "name": name,
                "lateral_limit_a": {"lat": float(parts[1]), "lon": float(parts[2])},
                "lateral_limit_b": {"lat": float(parts[3]), "lon": float(parts[4])},
            }
        )
    return beaches


inputs: Dict[str, Any] = {}

try:
    inputs = build_inputs(
        primary_mission=mission,
        lateral_limit_a=_parse_latlon(ll_a),
        lateral_limit_b=_parse_latlon(ll_b),
        target_location=target_location.strip() or None,
        additional_beaches=_parse_beaches(beaches_text),
        known_hazards=_parse_hazards(hazard_text),
        vessels=vessels,
        connectors=[],
        operation_start_time="now",
        operation_duration_hours=10.0,
        time_of_day_preference="any",
        weather_thresholds={
            "max_wind_speed_kts": float(max_wind),
            "max_wave_height_ft": float(max_waves),
            "min_visibility_m": float(min_vis_m),
            "max_cloud_cover_pct": float(max_cloud),
        },
        radius_nm=float(radius_nm),
        grid_spacing_nm=float(grid_spacing_nm),
    )
except Exception as e:
    st.error(f"Input error: {e}")


# -------------------------
# Main panel
# -------------------------

tab1, tab2, tab3 = st.tabs(["Plan", "Run", "Results"])

with tab1:
    st.subheader("Calculated geometry")
    if inputs:
        st.json(
            {
                "center": inputs.get("center_coords"),
                "direction_of_attack_deg": inputs.get("direction_of_attack"),
                "sector_min_bearing": inputs.get("sector_min_bearing"),
                "sector_max_bearing": inputs.get("sector_max_bearing"),
            }
        )
        _json_download_button("Download inputs JSON", inputs, "naval_ops_inputs.json")

with tab2:
    st.subheader("Collection and analysis")

    if run_button:
        st.session_state.pop("collected", None)
        st.session_state.pop("scored", None)

        progress = st.progress(0)
        status = st.empty()

        def progress_cb(done: int, total: int, stats: Dict[str, Any]):
            pct = int((done / max(1, total)) * 100)
            progress.progress(pct)
            status.write(
                f"Points: {done}/{total} | Ocean: {stats.get('ocean_points', 0)} | Land filtered: {stats.get('land_points', 0)}"
            )

        with st.spinner("Collecting data..."):
            collector = NavalDataCollector(inputs)
            data = collector.collect_all_data()

        st.success(
            f"Collected {len(data.get('analyzed_points', []))} ocean points (land filtered out: {data.get('stats', {}).get('land_points', 0)})"
        )
        st.session_state["collected"] = data

        with st.spinner("Analyzing..."):
            analyzer = NavalOperationsAnalyzer(inputs, data)
            scored = analyzer.analyze_all_points()

        st.success(f"Scored {len(scored)} points")
        st.session_state["scored"] = scored

with tab3:
    if st.session_state.get("collected") and st.session_state.get("scored"):
        data = st.session_state["collected"]
        scored = st.session_state["scored"]

        st.subheader("Top recommendations")
        top_n = st.slider("Show top N", min_value=5, max_value=50, value=10, step=5)
        top = scored[:top_n]
        st.dataframe(
            [
                {
                    "rank": i + 1,
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "score": p["scores"]["overall"],
                    "depth_ft": p.get("bathymetry", {}).get("depth_ft"),
                    "dist_center_nm": p.get("distance_from_center_nm"),
                    "dist_target_nm": p.get("distance_from_target_nm"),
                }
                for i, p in enumerate(top)
            ]
        )

        col_a, col_b = st.columns(2)
        with col_a:
            _json_download_button("Download collected data JSON", data, "naval_ops_data.json")
        with col_b:
            _json_download_button(
                "Download analysis JSON",
                {
                    "metadata": {
                        "analysis_time": "generated_in_app",
                        "center_location": inputs.get("center_location"),
                        "mission": inputs.get("primary_mission"),
                    },
                    "scored_locations": scored,
                },
                "naval_ops_analysis.json",
            )

        st.subheader("Map")
        m = build_map(inputs, scored)
        st_folium(m, use_container_width=True, height=650)
    else:
        st.info("Run the analysis to see results.")
