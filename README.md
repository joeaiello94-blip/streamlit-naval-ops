# Naval Operations Planner (Streamlit)

This project turns your four-script workflow into a single Streamlit app that:

1. Collects inputs (mission, lateral limits, vessels, connectors, hazards)
2. Builds a 13 nm analysis grid inside the 180° sector
3. Pulls weather and marine data (Open-Meteo)
4. Pulls bathymetry using the GEBCO 2020 dataset via the OpenTopoData API
5. Scores each ocean point based on mission weights
6. Visualizes results on an interactive map and table

## Run locally

```bash
cd streamlit_naval_ops
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

Streamlit Cloud deploys from a GitHub repo.

1. Create a GitHub repo and push this folder
2. In Streamlit Cloud, select the repo and set the main file to `app.py`
3. Ensure `requirements.txt` is in the repo root

If you do not want GitHub:
- You can still share this as a zip for other people to run locally.
- For a hosted deployment without GitHub, consider Hugging Face Spaces (Streamlit) or a small VPS.

## Files

- `app.py` is the Streamlit UI and orchestration
- `naval_ops/` contains the planner, collector, analyzer, and visualizer modules

## Notes and safety

- No API keys are required.
- The app makes network calls to public APIs. If you are using it in a sensitive environment, run it offline with mocked data sources.
- Generated JSON outputs are ignored by `.gitignore` so you do not accidentally publish scenario inputs.
