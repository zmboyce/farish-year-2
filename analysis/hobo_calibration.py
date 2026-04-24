"""
HOBO air-temperature calibration (°F).

Offsets are ADDED to the logger air temperature after °C→°F conversion.
Derived from inter-unit mean comparison (HB-001 / HB-012 / HB-009 / HB-004).
"""

from __future__ import annotations

import pandas as pd

# Site index matches filenames like "HOBO Site 1 …"
HOBO_AIR_TEMP_OFFSET_F: dict[int, float] = {
    1: -0.36,  # HB-001: subtract 0.36 °F
    2: -1.04,  # HB-012
    3: 0.46,  # HB-009: add 0.46 °F
    4: 0.93,  # HB-004
}

HOBO_LOGGER_ID: dict[int, str] = {1: "HB-001", 2: "HB-012", 3: "HB-009", 4: "HB-004"}


def apply_hobo_air_temp_calibration(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `df` with `temp_f` adjusted per site. RH and other columns unchanged."""
    out = df.copy()
    for site, delta in HOBO_AIR_TEMP_OFFSET_F.items():
        m = out["site"] == site
        if m.any():
            out.loc[m, "temp_f"] = out.loc[m, "temp_f"] + delta
    return out


def calibration_summary_lines() -> list[str]:
    lines = []
    for site in sorted(HOBO_AIR_TEMP_OFFSET_F):
        d = HOBO_AIR_TEMP_OFFSET_F[site]
        sign = "+" if d >= 0 else "−"
        lines.append(f"Site {site}: {sign}{abs(d):.2f} °F")
    return lines


def offsets_table() -> pd.DataFrame:
    rows = []
    for site in sorted(HOBO_AIR_TEMP_OFFSET_F):
        rows.append({
            "site": site,
            "logger_id": HOBO_LOGGER_ID.get(site, ""),
            "offset_add_to_temp_f": HOBO_AIR_TEMP_OFFSET_F[site],
        })
    return pd.DataFrame(rows)
