"""
Kestrel inter-unit calibration (°F) for recorded air temperature and WBGT.

Offsets are ADDED to the values loaded from the Year 2 Kestrel spreadsheet
(per site, matched to "Site 1"–"Site 4"). RH, wind, and estimated temperature
are unchanged.
"""

from __future__ import annotations

import pandas as pd

# Adjustments in °F to add (negative = subtract). From inter-logger / network mean.
KESTREL_AIR_TEMP_OFFSET_F: dict[int, float] = {
    1: -0.88,
    2: -0.60,
    3: 0.53,
    4: 0.95,
}

KESTREL_WBGT_OFFSET_F: dict[int, float] = {
    1: -0.58,
    2: -0.31,
    3: 0.03,
    4: 0.86,
}

# Serial numbers (for documentation / export only)
KESTREL_K_ID_BY_SITE: dict[int, str] = {
    1: "2963395",
    2: "2954508",
    3: "2957438",
    4: "2963360",
}


def apply_kestrel_calibrations(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with `air_temp_f` and `wbgt_f` adjusted per `site` where present."""
    out = df.copy()
    for site, delta in KESTREL_AIR_TEMP_OFFSET_F.items():
        m = out["site"] == site
        if m.any() and "air_temp_f" in out.columns:
            out.loc[m, "air_temp_f"] = out.loc[m, "air_temp_f"] + delta
    for site, delta in KESTREL_WBGT_OFFSET_F.items():
        m = out["site"] == site
        if m.any() and "wbgt_f" in out.columns:
            out.loc[m, "wbgt_f"] = out.loc[m, "wbgt_f"] + delta
    return out


def kestrel_offsets_table() -> pd.DataFrame:
    rows = []
    for site in sorted(KESTREL_AIR_TEMP_OFFSET_F):
        rows.append(
            {
                "site": site,
                "kestrel_id": KESTREL_K_ID_BY_SITE.get(site, ""),
                "air_temp_add_f": KESTREL_AIR_TEMP_OFFSET_F[site],
                "wbgt_add_f": KESTREL_WBGT_OFFSET_F[site],
            }
        )
    return pd.DataFrame(rows)


def kestrel_calibration_summary_lines() -> list[str]:
    def _line(title: str, d: dict[int, float]) -> str:
        parts = [f"Site {s} {K:+.2f}" for s, K in sorted(d.items())]
        return title + ", ".join(parts)

    return [
        _line("Kestrel air temp (°F) offsets added: ", KESTREL_AIR_TEMP_OFFSET_F),
        _line("Kestrel WBGT (°F) offsets added: ", KESTREL_WBGT_OFFSET_F),
    ]
