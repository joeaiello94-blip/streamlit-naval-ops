import math
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


M_TO_FT = 3.28084


@dataclass
class BathymetryResult:
    """Depth is positive down (bathymetry)."""

    depth_m: Optional[float]
    depth_ft: Optional[float]
    is_ocean: bool
    estimated: bool
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "depth_m": self.depth_m,
            "depth_ft": self.depth_ft,
            "is_ocean": self.is_ocean,
            "estimated": self.estimated,
            "source": self.source,
        }


class BathymetryService:
    """Fetch point bathymetry.

    Default implementation uses OpenTopoData's public endpoint for the GEBCO2020 grid.
    This returns elevation (meters) relative to sea level, where negative values are below sea level.

    Notes:
    - Public endpoints can rate-limit or go down; the service falls back to a conservative estimate.
    - For serious/operational use, plug in a vetted dataset and hosting.
    """

    def __init__(self, timeout_s: int = 15):
        self.timeout_s = timeout_s
        self._cache: Dict[str, BathymetryResult] = {}

    def get_bathymetry(self, lat: float, lon: float) -> Dict[str, Any]:
        key = f"{lat:.5f},{lon:.5f}"
        if key in self._cache:
            return self._cache[key].to_dict()

        # OpenTopoData: https://www.opentopodata.org/
        # Dataset name for GEBCO 2020 is typically "gebco2020".
        url = "https://api.opentopodata.org/v1/gebco2020"
        params = {"locations": f"{lat},{lon}"}

        try:
            r = requests.get(url, params=params, timeout=self.timeout_s)
            r.raise_for_status()
            payload = r.json()
            results = payload.get("results") or []
            if not results:
                raise ValueError("No results")

            elev_m = results[0].get("elevation")
            if elev_m is None or (isinstance(elev_m, float) and math.isnan(elev_m)):
                raise ValueError("No elevation")

            # Convert elevation to depth: negative elevation => depth below sea level.
            if elev_m < 0:
                depth_m = abs(float(elev_m))
                out = BathymetryResult(
                    depth_m=depth_m,
                    depth_ft=depth_m * M_TO_FT,
                    is_ocean=True,
                    estimated=False,
                    source="OpenTopoData GEBCO2020",
                )
            else:
                out = BathymetryResult(
                    depth_m=0.0,
                    depth_ft=0.0,
                    is_ocean=False,
                    estimated=False,
                    source="OpenTopoData GEBCO2020",
                )

        except Exception:
            # Fallback: mark ocean unknown and use a conservative placeholder depth.
            out = BathymetryResult(
                depth_m=50.0,
                depth_ft=50.0 * M_TO_FT,
                is_ocean=True,
                estimated=True,
                source="Fallback estimate",
            )

        self._cache[key] = out
        return out.to_dict()
