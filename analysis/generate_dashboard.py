#!/usr/bin/env python3
"""
Generate a self-contained interactive HTML dashboard for Farish Year 2 analysis.
Output: farish_dashboard.html (in the workspace root)
"""

import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from hobo_calibration import apply_hobo_air_temp_calibration

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Data"
OUT_HTML = ROOT / "farish_dashboard.html"

FEELING_SCORE = {
    "Slightly_Cool": 1, "Cool": 1, "Neutral": 2, "Slightly_Warm": 3,
    "Warm": 4, "Hot": 5, "Very_Hot": 6,
}
COMFORT_SCORE = {
    "Comfortable": 1, "Slightly_Uncomfortable": 2,
    "Uncomfortable": 3, "Very_Uncomfortable": 4,
}
SITE_COLORS = {1: "#1F6B8E", 2: "#C96A1E", 3: "#3E7E50", 4: "#7B4F9E"}
FEELING_ORDER = ["Slightly Cool", "Cool", "Neutral", "Slightly Warm", "Warm", "Hot", "Very Hot"]
COMFORT_ORDER = ["Comfortable", "Slightly Uncomfortable", "Uncomfortable", "Very Uncomfortable"]


def c_to_f(c: pd.Series) -> pd.Series:
    return c * 9 / 5 + 32


def site_num(s: str):
    if not isinstance(s, str):
        return None
    m = re.match(r"Site\s*(\d+)", s.strip(), re.I)
    return int(m.group(1)) if m else None


# ── Load & clean kestrel ──────────────────────────────────────────────────────
def load_kestrel() -> pd.DataFrame:
    path = DATA / "Kestrel" / "Kestrel Data_Farish St_Year 2.xlsx"
    df = pd.read_excel(path, sheet_name="final")
    df["site"] = df["2. Site #"].map(site_num)
    df = df.dropna(subset=["site"])
    df["site"] = df["site"].astype(int)
    df["air_temp_f"] = pd.to_numeric(df["6c. Record the Air Temperature"], errors="coerce")
    df["wbgt_f"] = pd.to_numeric(df["ADJUSTED Record the Wet Bulb Globe Temperature"], errors="coerce")
    df["rh_pct"] = pd.to_numeric(df["6d. Record the Humidity"], errors="coerce")
    df["wind_mph"] = pd.to_numeric(df["6b. Record Wind Speed (mph)"], errors="coerce")
    df["est_temp_f"] = pd.to_numeric(
        df["5. What would you estimate as the current temperature?"], errors="coerce"
    )
    feel = df["3. How would you describe your current feeling of temperature at this site?"].astype(str).str.strip()
    df["feeling_score"] = feel.map(FEELING_SCORE)
    comf = df["4. How would you describe your level of thermal comfort at this site?"].astype(str).str.strip()
    df["comfort_score"] = comf.map(COMFORT_SCORE)
    df["visit_dt"] = pd.to_datetime(df["1. Date & Time of Site Visit"])
    df["visit_date"] = df["visit_dt"].dt.normalize()
    df["period_key"] = df["Period"].astype(str).str.strip()
    df["feeling_label"] = feel.str.replace("_", " ", regex=False)
    df["comfort_label"] = comf.str.replace("_", " ", regex=False)
    df["week_start"] = (
        df["visit_date"] - pd.to_timedelta(df["visit_date"].dt.dayofweek, unit="d")
    )
    return df


# HOBO diurnal window — matches run_farish_analysis.hobo_diurnal(...)
HOBO_DIURNAL_START = "2025-08-16 00:00:00"
HOBO_DIURNAL_END = "2025-09-19 00:00:00"


def hobo_diurnal_profile_records(hdf: pd.DataFrame, start: str, end: str) -> tuple[list[dict], str]:
    """Mean air temp (°F) by site and clock time (fractional hour CDT), same logic as static figure."""
    mask = (hdf["dt"] >= start) & (hdf["dt"] < end)
    d = hdf.loc[mask].copy()
    if d.empty:
        return [], ""
    d["hour"] = d["dt"].dt.hour + d["dt"].dt.minute / 60.0
    prof = d.groupby(["site", "hour"], as_index=False)["temp_f"].mean()
    prof["hour"] = prof["hour"].round(4)
    prof["temp_f"] = prof["temp_f"].round(3)
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) - pd.Timedelta(days=1)
    window_label = (
        f"{start_ts.strftime('%b')} {start_ts.day}, {start_ts.year} – "
        f"{end_ts.strftime('%b')} {end_ts.day}, {end_ts.year}"
    )
    return df_to_records(prof), window_label


def load_hobo() -> pd.DataFrame:
    """Load all HOBO workbooks under Data/HOBO/ and apply air-temp calibration (see hobo_calibration)."""
    frames = []
    for path in sorted(DATA.glob("HOBO/*.xlsx")):
        m = re.search(r"Site\s*(\d+)", path.name, re.I)
        if not m:
            continue
        site = int(m.group(1))
        d = pd.read_excel(path)
        d["dt"] = pd.to_datetime(d["Date-Time (CDT)"])
        d["site"] = site
        d["temp_f"] = c_to_f(pd.to_numeric(d["Temperature , °C"], errors="coerce"))
        d["rh"] = pd.to_numeric(d["RH , %"], errors="coerce")
        frames.append(d)
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return apply_hobo_air_temp_calibration(raw) if not raw.empty else raw


# ── Serialisation helpers ─────────────────────────────────────────────────────
def safe(v):
    """Make a scalar JSON-serialisable."""
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if math.isnan(float(v)) else round(float(v), 4)
    return v


def df_to_records(df: pd.DataFrame) -> list[dict]:
    rows = []
    for row in df.to_dict(orient="records"):
        rows.append({k: safe(v) for k, v in row.items()})
    return rows


def to_json(obj) -> str:
    return json.dumps(obj, default=str)


# ── Prepare datasets ──────────────────────────────────────────────────────────
def prepare(kdf: pd.DataFrame, hdf: pd.DataFrame) -> dict:
    kdf = kdf.copy()

    # --- raw visits ---
    cols = ["site", "visit_date", "period_key", "feeling_label", "feeling_score",
            "comfort_label", "comfort_score", "est_temp_f", "air_temp_f", "wbgt_f", "rh_pct", "wind_mph"]
    visits = kdf[cols].copy()
    visits["visit_date"] = visits["visit_date"].astype(str)
    visits_records = df_to_records(visits)

    def _sem(x):
        return float(x.sem()) if len(x) > 1 else 0.0

    # --- per-site daily ---
    site_daily = (
        kdf.dropna(subset=["visit_date", "site", "feeling_score", "comfort_score"])
        .groupby(["visit_date", "site"], sort=True)
        .agg(feeling=("feeling_score", "mean"), comfort=("comfort_score", "mean"))
        .reset_index()
    )
    site_daily["visit_date"] = site_daily["visit_date"].astype(str)
    site_daily_records = df_to_records(site_daily)

    # --- site averages ---
    site_avgs = (
        kdf.groupby("site", sort=True)
        [["air_temp_f", "wbgt_f", "rh_pct", "wind_mph", "feeling_score", "comfort_score"]]
        .mean()
        .round(2)
        .reset_index()
    )
    site_avgs_records = df_to_records(site_avgs)

    # --- study summary (Overview) ---
    summary = {
        "n_visits": int(len(kdf)),
        "n_unique_days": int(kdf["visit_date"].nunique()) if len(kdf) else 0,
        "first_visit_date": str(kdf["visit_date"].min().date()) if len(kdf) else "",
        "last_visit_date": str(kdf["visit_date"].max().date()) if len(kdf) else "",
        "hobo_calibration_note": (
            "HOBO air temperature (°F) adjusted: Site 1 −0.36, Site 2 −1.04, "
            "Site 3 +0.46, Site 4 +0.93 (offsets added to converted air temp)."
        ),
    }

    # --- mean perception ± SEM by site (matches bar-chart deliverable) ---
    perception_by_site = (
        kdf.dropna(subset=["site"])
        .groupby("site", sort=True)
        .agg(
            feeling_mean=("feeling_score", "mean"),
            feeling_sem=("feeling_score", _sem),
            comfort_mean=("comfort_score", "mean"),
            comfort_sem=("comfort_score", _sem),
            n=("feeling_score", "count"),
        )
        .reset_index()
    )
    perception_by_site_records = df_to_records(perception_by_site.round(4))

    # --- estimated vs Kestrel air (same as kestrel_estimated_vs_measured figure) ---
    m_est = kdf["est_temp_f"].notna() & kdf["air_temp_f"].notna()
    est_vs_measured = df_to_records(
        kdf.loc[m_est, ["site", "est_temp_f", "air_temp_f"]].copy()
    )

    # --- HOBO diurnal profile (same window as hobo_diurnal_profile_by_site.png) ---
    hobo_diurnal_records: list[dict] = []
    diurnal_window = ""
    if not hdf.empty:
        hobo_diurnal_records, diurnal_window = hobo_diurnal_profile_records(
            hdf, HOBO_DIURNAL_START, HOBO_DIURNAL_END
        )

    # --- HOBO exposure hours ---
    if not hdf.empty:
        exposure_rows = []
        for site in sorted(hdf["site"].unique()):
            s = hdf[hdf["site"] == site]["temp_f"].dropna()
            exposure_rows.append({
                "site": int(site),
                "ge_85": round(float((s >= 85).sum()) * 15 / 60, 2),
                "ge_90": round(float((s >= 90).sum()) * 15 / 60, 2),
                "ge_95": round(float((s >= 95).sum()) * 15 / 60, 2),
            })
        exposure = exposure_rows

        # HOBO daily temp by site
        hdf["date"] = hdf["dt"].dt.normalize().astype(str)
        hobo_daily = (
            hdf.groupby(["date", "site"])
            .agg(temp_f=("temp_f", "mean"), rh=("rh", "mean"))
            .round(2)
            .reset_index()
        )
        hobo_daily_records = df_to_records(hobo_daily)
    else:
        exposure = []
        hobo_daily_records = []

    return {
        "visits": visits_records,
        "summary": summary,
        "site_daily": site_daily_records,
        "site_avgs": site_avgs_records,
        "perception_by_site": perception_by_site_records,
        "est_vs_measured": est_vs_measured,
        "hobo_diurnal": hobo_diurnal_records,
        "diurnal_window": diurnal_window,
        "exposure": exposure,
        "hobo_daily": hobo_daily_records,
        "site_colors": SITE_COLORS,
        "feeling_order": FEELING_ORDER,
        "comfort_order": COMFORT_ORDER,
    }


# ── HTML template ─────────────────────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Farish Street Year 2</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
  :root {
    --c1: #1F6B8E; --c2: #C96A1E; --c3: #3E7E50; --c4: #7B4F9E;
    --bg: #f8f9fb; --card: #ffffff; --border: #e2e6ea;
    --text: #1a1a2e; --muted: #6c757d; --accent: #1F6B8E;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: var(--bg); color: var(--text); font-size: 14px; }

  /* Header */
  header { background: #12253a; color: #fff; padding: 22px 32px; display: flex;
           align-items: baseline; gap: 16px; flex-wrap: wrap; }
  header h1 { font-size: 1.35rem; font-weight: 600; letter-spacing: -0.3px; }
  header span { color: #94a8bc; font-size: 0.85rem; }
  header .header-note { display: block; width: 100%; margin-top: 8px; font-size: 0.8rem;
                         color: #94a8bc; font-weight: 400; line-height: 1.4; max-width: 52rem; }

  /* Tabs */
  .tab-bar { background: #fff; border-bottom: 2px solid var(--border);
             display: flex; padding: 0 28px; gap: 0; position: sticky; top: 0; z-index: 100; }
  .tab-btn { padding: 14px 20px; font-size: 13px; font-weight: 500; color: var(--muted);
             cursor: pointer; border: none; background: none; border-bottom: 2px solid transparent;
             margin-bottom: -2px; transition: color 0.15s, border-color 0.15s; white-space: nowrap; }
  .tab-btn:hover { color: var(--accent); }
  .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab-panel { display: none; padding: 28px 32px; }
  .tab-panel.active { display: block; }

  /* Cards */
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
           gap: 14px; margin-bottom: 24px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px;
          padding: 18px 20px; }
  .card-site { border-top: 4px solid; }
  .card h3 { font-size: 0.78rem; font-weight: 600; text-transform: uppercase;
             letter-spacing: 0.6px; color: var(--muted); margin-bottom: 10px; }
  .card .big { font-size: 1.9rem; font-weight: 700; line-height: 1; }
  .card .metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px;
                   margin-top: 10px; }
  .card .m-label { font-size: 0.75rem; color: var(--muted); }
  .card .m-val { font-size: 0.92rem; font-weight: 600; }

  /* Section headers */
  .section-title { font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
                   letter-spacing: 0.7px; color: var(--muted); margin-bottom: 12px; }
  .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px; }
  .row2-wide { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 24px; }
  @media (max-width: 800px) { .row2, .row2-wide { grid-template-columns: 1fr; } }
  .chart-card { background: var(--card); border: 1px solid var(--border);
                border-radius: 10px; padding: 18px 16px; }

  /* Controls */
  .controls { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px;
              align-items: center; }
  .ctrl-label { font-size: 12px; font-weight: 600; color: var(--muted);
                text-transform: uppercase; letter-spacing: 0.5px; }
  .site-toggle { display: flex; gap: 6px; }
  .site-chip { padding: 5px 12px; border-radius: 20px; border: 1.5px solid;
               font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
  .site-chip.active { color: #fff !important; }
  select.ctrl-select { padding: 6px 10px; border-radius: 6px; border: 1.5px solid var(--border);
                       font-size: 13px; color: var(--text); background: #fff; cursor: pointer; }

  /* Toggle switch */
  .toggle-group { display: flex; background: #f1f3f5; border-radius: 8px; padding: 3px; gap: 2px; }
  .toggle-opt { padding: 5px 14px; border-radius: 6px; font-size: 12px; font-weight: 600;
                cursor: pointer; color: var(--muted); transition: all 0.15s; }
  .toggle-opt.active { background: #fff; color: var(--accent); box-shadow: 0 1px 3px rgba(0,0,0,.12); }

  /* Raw table */
  .table-controls { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; align-items: center; }
  .table-wrap { overflow-x: auto; border-radius: 10px; border: 1px solid var(--border); }
  table { width: 100%; border-collapse: collapse; background: #fff; }
  thead { position: sticky; top: 0; z-index: 10; }
  th { background: #f1f3f6; padding: 10px 14px; text-align: left; font-size: 12px;
       font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px;
       cursor: pointer; user-select: none; white-space: nowrap; border-bottom: 2px solid var(--border); }
  th:hover { background: #e8eaed; }
  th .sort-icon { margin-left: 4px; color: #bbb; }
  th.sort-asc .sort-icon::after { content: " ▲"; color: var(--accent); }
  th.sort-desc .sort-icon::after { content: " ▼"; color: var(--accent); }
  td { padding: 9px 14px; font-size: 13px; border-bottom: 1px solid #f0f2f4; white-space: nowrap; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #f8f9fb; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px;
          font-weight: 600; }
  .badge-1 { background: #dff0fa; color: var(--c1); }
  .badge-2 { background: #fdebd0; color: var(--c2); }
  .badge-3 { background: #d5eddb; color: var(--c3); }
  .badge-4 { background: #ecdff5; color: var(--c4); }
  .feel-hot { background: #ffe0b2; color: #b44a00; }
  .feel-very-hot { background: #ffcdd2; color: #b71c1c; }
  .feel-neutral { background: #e8f5e9; color: #2e7d32; }
  .feel-warm { background: #fff8e1; color: #f57f17; }
  .feel-cool { background: #e3f2fd; color: #1565c0; }
  .comf-ok { background: #e8f5e9; color: #2e7d32; }
  .comf-slight { background: #fff8e1; color: #f57f17; }
  .comf-uncomf { background: #ffe0b2; color: #b44a00; }
  .comf-very { background: #ffcdd2; color: #b71c1c; }

  .export-btn { padding: 7px 14px; background: var(--accent); color: #fff; border: none;
                border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer;
                margin-left: auto; }
  .export-btn:hover { opacity: 0.88; }
  input.filter-input { padding: 7px 10px; border: 1.5px solid var(--border); border-radius: 6px;
                       font-size: 13px; color: var(--text); }
  .stat-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
  .stat-box { background: var(--card); border: 1px solid var(--border); border-radius: 8px;
              padding: 12px 16px; text-align: center; min-width: 100px; }
  .stat-box .n { font-size: 1.5rem; font-weight: 700; color: var(--accent); }
  .stat-box .lbl { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .note { font-size: 12px; color: var(--muted); margin-top: 8px; }
  .ts-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px 18px;
    margin-bottom: 4px;
    align-items: stretch;
  }
  .ts-grid .chart-card { margin-bottom: 0; }
  .ts-chart-h { height: 268px; min-height: 220px; }
  @media (max-width: 920px) {
    .ts-grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>

<header>
  <div>
    <h1>Farish Street Year 2</h1>
    <span class="header-note" id="header-cal"></span>
  </div>
</header>

<nav class="tab-bar">
  <button class="tab-btn active" onclick="showTab('overview')">Overview</button>
  <button class="tab-btn" onclick="showTab('timeseries')">Timeseries</button>
  <button class="tab-btn" onclick="showTab('scatter')">Scatter</button>
  <button class="tab-btn" onclick="showTab('hobo')">HOBO Temps</button>
  <button class="tab-btn" onclick="showTab('rawdata')">Raw Data</button>
</nav>

<!-- TAB: OVERVIEW -->
<div id="tab-overview" class="tab-panel active">
  <div class="stat-row" id="overview-summary" style="margin-bottom:18px"></div>
  <div id="site-cards" class="cards"></div>
  <div class="row2">
    <div class="chart-card">
      <div class="section-title">Hours above temperature thresholds (HOBO)</div>
      <div id="exposure-chart" style="height:340px"></div>
    </div>
    <div class="chart-card">
      <div class="section-title">Mean perception scores by site (± SEM)</div>
      <div id="ov-perc-feel-bar" style="height:200px"></div>
      <div id="ov-perc-comf-bar" style="height:200px"></div>
    </div>
  </div>
  <div class="controls" style="margin-top:8px">
    <span class="ctrl-label">Daily chart — sites</span>
    <div class="site-toggle" id="ov-daily-site-toggle"></div>
  </div>
  <p class="note" style="margin-bottom:12px">Daily means pool only visits from the selected sites (same calendar day). Turn sites on/off to compare.</p>
  <div class="chart-card">
    <div class="section-title">Daily mean perception scores</div>
    <div id="daily-chart" style="height:320px"></div>
  </div>
</div>

<!-- TAB: TIMESERIES -->
<div id="tab-timeseries" class="tab-panel">
  <div class="controls">
    <span class="ctrl-label">Sites</span>
    <div class="site-toggle" id="ts-site-toggle"></div>
  </div>
  <p class="note" style="margin-bottom:14px">Site toggles apply to all four panels below (two per row). Top: HOBO diurnal curve and estimated vs. Kestrel air. Bottom: perception scores by visit date.</p>
  <div class="ts-grid">
    <div class="chart-card">
      <div class="section-title">HOBO: mean diurnal air temperature</div>
      <p class="note" id="ts-diurnal-window" style="margin-bottom:8px"></p>
      <div id="ts-diurnal-chart" class="ts-chart-h"></div>
    </div>
    <div class="chart-card">
      <div class="section-title">Estimated vs. measured air temperature (Kestrel)</div>
      <div id="ts-est-chart" class="ts-chart-h"></div>
    </div>
    <div class="chart-card">
      <div class="section-title">Air temperature feeling score by site</div>
      <div id="ts-feeling-chart" class="ts-chart-h"></div>
    </div>
    <div class="chart-card">
      <div class="section-title">Thermal comfort score by site</div>
      <div id="ts-comfort-chart" class="ts-chart-h"></div>
    </div>
  </div>
  <p class="note" style="margin-top:12px">Score scales: Feeling 1 (Slightly Cool) → 6 (Very Hot) · Comfort 1 (Comfortable) → 4 (Very Uncomfortable). Diurnal curves average HOBO readings by clock time (15‑min cadence) over the deployment window; matches the static diurnal profile figure.</p>
</div>

<!-- TAB: SCATTER -->
<div id="tab-scatter" class="tab-panel">
  <div class="controls">
    <span class="ctrl-label">X axis</span>
    <select class="ctrl-select" id="scatter-x" onchange="drawScatter()">
      <option value="air_temp_f">Kestrel air temperature (°F)</option>
      <option value="wbgt_f">WBGT (°F)</option>
      <option value="rh_pct">Relative Humidity (%)</option>
      <option value="wind_mph">Wind Speed (mph)</option>
      <option value="est_temp_f">Estimated temperature (°F)</option>
    </select>
    <span class="ctrl-label">Y axis</span>
    <select class="ctrl-select" id="scatter-y" onchange="drawScatter()">
      <option value="feeling_score">Feeling Score</option>
      <option value="comfort_score">Comfort Score</option>
    </select>
    <span class="ctrl-label">Sites</span>
    <div class="site-toggle" id="scatter-site-toggle"></div>
  </div>
  <div class="chart-card">
    <div id="scatter-chart" style="height:440px"></div>
  </div>
  <p class="note">Each point is one site visit. Axes use Kestrel readings except <strong>Estimated temperature</strong>, which is the survey response (same question as the estimated vs. measured figure). With only ~90 visits, relationships are exploratory—use Timeseries for clearer site comparisons.</p>
</div>

<!-- TAB: HOBO -->
<div id="tab-hobo" class="tab-panel">
  <div class="controls">
    <span class="ctrl-label">Sites</span>
    <div class="site-toggle" id="hobo-site-toggle"></div>
  </div>
  <div class="chart-card" style="margin-bottom:20px">
    <div class="section-title">Daily mean air temperature (°F) — HOBO logger</div>
    <div id="hobo-temp-chart" style="height:300px"></div>
  </div>
  <div class="chart-card">
    <div class="section-title">Daily mean relative humidity (%) — HOBO logger</div>
    <div id="hobo-rh-chart" style="height:300px"></div>
  </div>
</div>

<!-- TAB: RAW DATA -->
<div id="tab-rawdata" class="tab-panel">
  <div class="table-controls">
    <span class="ctrl-label">Filter</span>
    <input class="filter-input" type="text" id="raw-search" placeholder="Search any column…" oninput="filterTable()">
    <select class="ctrl-select" id="raw-site" onchange="filterTable()">
      <option value="">All sites</option>
      <option value="1">Site 1</option>
      <option value="2">Site 2</option>
      <option value="3">Site 3</option>
      <option value="4">Site 4</option>
    </select>
    <select class="ctrl-select" id="raw-feeling" onchange="filterTable()">
      <option value="">All feelings</option>
    </select>
    <select class="ctrl-select" id="raw-comfort" onchange="filterTable()">
      <option value="">All comfort</option>
    </select>
    <button class="export-btn" onclick="exportCSV()">Export CSV</button>
  </div>
  <div class="stat-row" id="raw-stats"></div>
  <div class="table-wrap" style="max-height:560px; overflow-y:auto">
    <table id="raw-table">
      <thead>
        <tr>
          <th onclick="sortTable('site')">Site<span class="sort-icon"></span></th>
          <th onclick="sortTable('visit_date')">Date<span class="sort-icon"></span></th>
          <th onclick="sortTable('period_key')">Period<span class="sort-icon"></span></th>
          <th onclick="sortTable('feeling_label')">Feeling<span class="sort-icon"></span></th>
          <th onclick="sortTable('feeling_score')">Feel score<span class="sort-icon"></span></th>
          <th onclick="sortTable('comfort_label')">Comfort<span class="sort-icon"></span></th>
          <th onclick="sortTable('comfort_score')">Comf score<span class="sort-icon"></span></th>
          <th onclick="sortTable('est_temp_f')">Estimated (°F)<span class="sort-icon"></span></th>
          <th onclick="sortTable('air_temp_f')">Kestrel air (°F)<span class="sort-icon"></span></th>
          <th onclick="sortTable('wbgt_f')">WBGT (°F)<span class="sort-icon"></span></th>
          <th onclick="sortTable('rh_pct')">RH (%)<span class="sort-icon"></span></th>
          <th onclick="sortTable('wind_mph')">Wind (mph)<span class="sort-icon"></span></th>
        </tr>
      </thead>
      <tbody id="raw-tbody"></tbody>
    </table>
  </div>
  <p class="note" id="raw-count" style="margin-top:10px"></p>
</div>

<script>
// ── Embedded data ─────────────────────────────────────────────────────────────
const DATA = __DATA_JSON__;

// ── Tab management ────────────────────────────────────────────────────────────
const TABS = ['overview','timeseries','scatter','hobo','rawdata'];
let initialised = {};

function showTab(name) {
  TABS.forEach(t => {
    document.getElementById('tab-' + t).classList.toggle('active', t === name);
  });
  document.querySelectorAll('.tab-btn').forEach((b, i) => {
    b.classList.toggle('active', TABS[i] === name);
  });
  if (!initialised[name]) {
    initialised[name] = true;
    initTab(name);
  }
}

function initTab(name) {
  if (name === 'overview') drawOverview();
  else if (name === 'timeseries') initTimeseries();
  else if (name === 'scatter') initScatter();
  else if (name === 'hobo') initHobo();
  else if (name === 'rawdata') initRawData();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const SC = DATA.site_colors;
const SITES = [1,2,3,4];
const SITE_NAMES = {1:'Site 1', 2:'Site 2', 3:'Site 3', 4:'Site 4'};

const PLOTLY_CONFIG = {displayModeBar: true, responsive: true,
  modeBarButtonsToRemove: ['select2d','lasso2d','autoScale2d'],
  toImageButtonOptions: {format:'png', scale:2}};

const BASE_LAYOUT = {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  margin:{t:20, r:20, b:50, l:55},
  font:{family:'-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', size:12, color:'#333'},
  xaxis:{showgrid:false, linecolor:'#ccc', tickcolor:'#ccc'},
  yaxis:{gridcolor:'#ebebeb', linecolor:'#ccc', tickcolor:'#ccc', zeroline:false},
  legend:{bgcolor:'rgba(0,0,0,0)', borderwidth:0},
  hovermode:'closest',
};

function mergeLayout(...objs) {
  return Object.assign({}, BASE_LAYOUT, ...objs);
}

function fmt1(v) { return v == null ? '—' : (+v).toFixed(1); }
function fmt2(v) { return v == null ? '—' : (+v).toFixed(2); }

// ── Site chip builder ─────────────────────────────────────────────────────────
function buildSiteChips(containerId, stateKey, onChange) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';
  SITES.forEach(s => {
    const chip = document.createElement('div');
    chip.className = 'site-chip active';
    chip.textContent = `Site ${s}`;
    chip.style.borderColor = SC[s];
    chip.style.color = SC[s];
    chip.style.backgroundColor = chip.classList.contains('active') ? SC[s] + '22' : 'transparent';
    chip.dataset.site = s;
    chip.onclick = () => {
      chip.classList.toggle('active');
      if (chip.classList.contains('active')) {
        chip.style.backgroundColor = SC[s] + '22';
      } else {
        chip.style.backgroundColor = 'transparent';
      }
      onChange();
    };
    container.appendChild(chip);
  });
}

function getActiveSites(containerId) {
  return Array.from(document.querySelectorAll(`#${containerId} .site-chip.active`))
    .map(c => +c.dataset.site);
}

// ── OVERVIEW ─────────────────────────────────────────────────────────────────
function drawOverview() {
  const sum = DATA.summary || {};
  const sumEl = document.getElementById('overview-summary');
  if (sumEl) {
    sumEl.innerHTML = `
      <div class="stat-box"><div class="n">${sum.n_visits ?? '—'}</div><div class="lbl">Site visits</div></div>
      <div class="stat-box"><div class="n">${sum.n_unique_days ?? '—'}</div><div class="lbl">Unique visit days</div></div>
      <div class="stat-box"><div class="n" style="font-size:1rem">${sum.first_visit_date || '—'}</div><div class="lbl">First visit</div></div>
      <div class="stat-box"><div class="n" style="font-size:1rem">${sum.last_visit_date || '—'}</div><div class="lbl">Last visit</div></div>
    `;
  }

  // Site cards
  const cardsEl = document.getElementById('site-cards');
  cardsEl.innerHTML = '';
  const avgs = DATA.site_avgs;
  avgs.forEach(row => {
    const s = row.site;
    const div = document.createElement('div');
    div.className = 'card card-site';
    div.style.borderTopColor = SC[s];
    div.innerHTML = `
      <h3 style="color:${SC[s]}">Site ${s}</h3>
      <div class="metrics">
        <div><div class="m-label">Air Temp</div><div class="m-val">${fmt1(row.air_temp_f)}°F</div></div>
        <div><div class="m-label">WBGT</div><div class="m-val">${fmt1(row.wbgt_f)}°F</div></div>
        <div><div class="m-label">RH</div><div class="m-val">${fmt1(row.rh_pct)}%</div></div>
        <div><div class="m-label">Wind</div><div class="m-val">${fmt1(row.wind_mph)} mph</div></div>
        <div><div class="m-label">Feeling</div><div class="m-val">${fmt1(row.feeling_score)} / 6</div></div>
        <div><div class="m-label">Comfort</div><div class="m-val">${fmt1(row.comfort_score)} / 4</div></div>
      </div>`;
    cardsEl.appendChild(div);
  });

  // Exposure chart
  const exp = DATA.exposure;
  if (exp.length) {
    const siteLabels = exp.map(r => `Site ${r.site}`);
    const expTraces = [
      {name:'≥ 85°F', x: siteLabels, y: exp.map(r=>r.ge_85), type:'bar',
       marker:{color:'#A8C8E0'}, hovertemplate:'%{x}: %{y:.0f} h<extra>≥85°F</extra>'},
      {name:'≥ 90°F', x: siteLabels, y: exp.map(r=>r.ge_90), type:'bar',
       marker:{color:'#4A90BF'}, hovertemplate:'%{x}: %{y:.0f} h<extra>≥90°F</extra>'},
      {name:'≥ 95°F', x: siteLabels, y: exp.map(r=>r.ge_95), type:'bar',
       marker:{color:'#1A4F72'}, hovertemplate:'%{x}: %{y:.0f} h<extra>≥95°F</extra>'},
    ];
    Plotly.newPlot('exposure-chart', expTraces, mergeLayout({
      barmode:'group',
      margin:{t:10,r:10,b:50,l:55},
      yaxis:{title:{text:'Hours'}},
      legend:{orientation:'h', y:-0.22},
    }), PLOTLY_CONFIG);
  }

  // Mean perception by site (aligned with kestrel_perception_bars_by_site deliverable)
  const pb = DATA.perception_by_site || [];
  const xs = pb.map(r => 'Site ' + r.site);
  if (pb.length) {
    Plotly.newPlot('ov-perc-feel-bar', [{
      type: 'bar',
      x: xs,
      y: pb.map(r => r.feeling_mean),
      marker: { color: pb.map(r => SC[r.site]) },
      error_y: { type: 'data', array: pb.map(r => r.feeling_sem), visible: true, thickness: 1.2, width: 5 },
      hovertemplate: '%{x}<br>Mean feeling: %{y:.2f} ± %{error_y.array:.2f}<extra></extra>',
    }], mergeLayout({
      margin: { t: 8, r: 12, b: 40, l: 48 },
      yaxis: { title: { text: 'Mean feeling (1–6)' }, range: [0, 6.8], dtick: 1 },
      showlegend: false,
    }), PLOTLY_CONFIG);
    Plotly.newPlot('ov-perc-comf-bar', [{
      type: 'bar',
      x: xs,
      y: pb.map(r => r.comfort_mean),
      marker: { color: pb.map(r => SC[r.site]) },
      error_y: { type: 'data', array: pb.map(r => r.comfort_sem), visible: true, thickness: 1.2, width: 5 },
      hovertemplate: '%{x}<br>Mean comfort: %{y:.2f} ± %{error_y.array:.2f}<extra></extra>',
    }], mergeLayout({
      margin: { t: 8, r: 12, b: 40, l: 48 },
      yaxis: { title: { text: 'Mean comfort (1–4)' }, range: [0, 4.5], dtick: 1 },
      showlegend: false,
    }), PLOTLY_CONFIG);
  }

  buildSiteChips('ov-daily-site-toggle', 'ov', drawDailyOverviewChart);
  drawDailyOverviewChart();

  initialised['overview'] = true;
}

function _mean(a) { return a.length ? a.reduce((x, y) => x + y, 0) / a.length : null; }
function _semArr(a) {
  if (a.length <= 1) return 0;
  const m = _mean(a);
  return Math.sqrt(a.reduce((s, x) => s + (x - m) * (x - m), 0) / (a.length * (a.length - 1)));
}

function drawDailyOverviewChart() {
  const active = getActiveSites('ov-daily-site-toggle');
  const visits = DATA.visits || [];
  const byDate = {};
  visits.forEach(r => {
    if (!active.includes(r.site)) return;
    const d = r.visit_date;
    if (!d) return;
    if (!byDate[d]) byDate[d] = { feel: [], comf: [] };
    if (r.feeling_score != null) byDate[d].feel.push(r.feeling_score);
    if (r.comfort_score != null) byDate[d].comf.push(r.comfort_score);
  });
  const dates = Object.keys(byDate).sort();
  if (!dates.length) {
    Plotly.newPlot('daily-chart', [], mergeLayout({
      margin: { t: 40, r: 20, b: 50, l: 55 },
      annotations: [{ text: 'Select at least one site with visits', showarrow: false, x: 0.5, y: 0.5, xref: 'paper', yref: 'paper' }],
    }), PLOTLY_CONFIG);
    return;
  }
  const feeling_mean = dates.map(d => _mean(byDate[d].feel));
  const feeling_sem = dates.map(d => _semArr(byDate[d].feel));
  const comfort_mean = dates.map(d => _mean(byDate[d].comf));
  const comfort_sem = dates.map(d => _semArr(byDate[d].comf));
  const nVis = dates.map(d => byDate[d].feel.length);

  const feelTrace = {
    name: 'Feeling score',
    x: dates,
    y: feeling_mean.map((v, i) => (v == null ? null : v)),
    error_y: { type: 'data', array: feeling_sem, visible: true, color: '#1F6B8E44', thickness: 1.5, width: 4 },
    mode: 'lines+markers',
    line: { color: '#1F6B8E', width: 2 },
    marker: { size: 6, color: '#1F6B8E' },
    hovertemplate: '%{x}<br>Feeling: %{y:.2f} ± %{error_y.array:.2f}<extra></extra>',
  };
  const comfTrace = {
    name: 'Comfort score',
    x: dates,
    y: comfort_mean.map((v) => (v == null ? null : v)),
    error_y: { type: 'data', array: comfort_sem, visible: true, color: '#C96A1E44', thickness: 1.5, width: 4 },
    mode: 'lines+markers',
    line: { color: '#C96A1E', width: 2, dash: 'dot' },
    marker: { size: 6, color: '#C96A1E' },
    hovertemplate: '%{x}<br>Comfort: %{y:.2f} ± %{error_y.array:.2f}<extra></extra>',
    yaxis: 'y2',
  };
  const nTrace = {
    name: '# visits (in selection)',
    x: dates,
    y: nVis,
    type: 'bar',
    marker: { color: '#e0e7ef' },
    yaxis: 'y3',
    showlegend: true,
    hovertemplate: '%{x}: %{y} visits<extra></extra>',
  };
  Plotly.newPlot('daily-chart', [nTrace, feelTrace, comfTrace], mergeLayout({
    margin: { t: 10, r: 60, b: 60, l: 55 },
    xaxis: { title: { text: 'Visit date' } },
    yaxis: { title: { text: 'Feeling (1–6)' }, range: [0, 7] },
    yaxis2: { title: { text: 'Comfort (1–4)' }, overlaying: 'y', side: 'right', range: [0, 5], showgrid: false },
    yaxis3: { title: { text: 'Visits' }, overlaying: 'y', side: 'right', range: [0, 30], showgrid: false, visible: false },
    legend: { orientation: 'h', y: -0.22 },
    hovermode: 'x unified',
  }), PLOTLY_CONFIG);
}

// ── TIMESERIES ────────────────────────────────────────────────────────────────
function drawTimeseriesTab() {
  drawEstVsMeasured();
  drawTimeseries();
  drawDiurnal();
}

function initTimeseries() {
  const dw = document.getElementById('ts-diurnal-window');
  if (dw) {
    dw.textContent = (DATA.diurnal_window)
      ? ('Window: ' + DATA.diurnal_window + ' (CDT) · mean by clock time')
      : '';
  }
  buildSiteChips('ts-site-toggle', 'ts', drawTimeseriesTab);
  drawTimeseriesTab();
}

function drawEstVsMeasured() {
  const active = getActiveSites('ts-site-toggle');
  const raw = DATA.est_vs_measured || [];
  const rows = raw.filter(r => active.includes(r.site));
  const traces = [];
  SITES.filter(s => active.includes(s)).forEach(s => {
    const pts = rows.filter(r => r.site === s);
    traces.push({
      name: 'Site ' + s,
      x: pts.map(r => r.est_temp_f),
      y: pts.map(r => r.air_temp_f),
      mode: 'markers',
      marker: { color: SC[s], size: 7.5, opacity: 0.88, line: { width: 0.5, color: 'white' } },
      hovertemplate: 'Site ' + s + '<br>Estimated: %{x:.1f}°F<br>Kestrel: %{y:.1f}°F<extra></extra>',
    });
  });
  let lo = 70, hi = 105;
  const vals = rows.flatMap(r => [r.est_temp_f, r.air_temp_f]).filter(v => v != null);
  if (vals.length) {
    lo = Math.min(...vals) - 2;
    hi = Math.max(...vals) + 2;
  }
  traces.push({
    type: 'scatter',
    x: [lo, hi],
    y: [lo, hi],
    mode: 'lines',
    line: { color: '#555555', dash: 'dash', width: 1.35 },
    name: 'y = x (perfect match)',
    hoverinfo: 'skip',
  });
  Plotly.newPlot('ts-est-chart', traces, mergeLayout({
    margin: { t: 6, r: 14, b: 44, l: 48 },
    xaxis: { title: { text: 'Estimated (°F)', standoff: 6 }, scaleanchor: 'y', scaleratio: 1, constrain: 'domain', tickfont: { size: 10 } },
    yaxis: { title: { text: 'Kestrel (°F)', standoff: 4 }, tickfont: { size: 10 } },
    legend: { orientation: 'h', y: -0.16, yanchor: 'top', font: { size: 10 } },
    hovermode: 'closest',
  }), PLOTLY_CONFIG);
}

function drawDiurnal() {
  const active = getActiveSites('ts-site-toggle');
  const hd = DATA.hobo_diurnal || [];
  const traces = SITES.filter(s => active.includes(s)).map(s => {
    const rows = hd.filter(r => r.site === s).sort((a, b) => a.hour - b.hour);
    return {
      name: 'Site ' + s,
      x: rows.map(r => r.hour),
      y: rows.map(r => r.temp_f),
      mode: 'lines',
      line: { color: SC[s], width: 2 },
      hovertemplate: 'Site ' + s + '<br>Hour: %{x:.2f}<br>Mean: %{y:.1f}°F<extra></extra>',
    };
  });
  Plotly.newPlot('ts-diurnal-chart', traces, mergeLayout({
    margin: { t: 6, r: 14, b: 48, l: 48 },
    xaxis: { title: { text: 'Hour of day (CDT)' }, range: [0, 24], dtick: 3, tickfont: { size: 10 } },
    yaxis: { title: { text: 'Mean temp (°F)' }, rangemode: 'normal', tickfont: { size: 10 } },
    legend: { orientation: 'h', y: -0.18, yanchor: 'top', font: { size: 10 } },
    hovermode: 'x unified',
  }), PLOTLY_CONFIG);
}

function drawTimeseries() {
  const active = getActiveSites('ts-site-toggle');
  const sd = DATA.site_daily;

  function makeSiteTraces(scoreKey) {
    return SITES.filter(s=>active.includes(s)).map(s => {
      const rows = sd.filter(r=>r.site===s).sort((a,b)=>a.visit_date.localeCompare(b.visit_date));
      return {
        name: `Site ${s}`,
        x: rows.map(r=>r.visit_date),
        y: rows.map(r=>r[scoreKey]),
        mode:'lines+markers',
        line:{color:SC[s], width:2},
        marker:{size:6, color:SC[s]},
        hovertemplate:`Site ${s}<br>%{x}: %{y:.2f}<extra></extra>`,
      };
    });
  }

  const feelLayout = mergeLayout({
    margin:{t:6,r:12,b:44,l:48},
    yaxis:{title:{text:'Score (1–6)'}, range:[0.5,6.5], dtick:1, tickfont:{size:10}},
    xaxis:{title:{text:'Visit date'}, tickfont:{size:10}},
    legend:{orientation:'h', y:-0.18, yanchor:'top', font:{size:10}},
    hovermode:'x unified',
  });
  const comfLayout = mergeLayout({
    margin:{t:6,r:12,b:44,l:48},
    yaxis:{title:{text:'Score (1–4)'}, range:[0.5,4.5], dtick:1, tickfont:{size:10}},
    xaxis:{title:{text:'Visit date'}, tickfont:{size:10}},
    legend:{orientation:'h', y:-0.18, yanchor:'top', font:{size:10}},
    hovermode:'x unified',
  });

  Plotly.newPlot('ts-feeling-chart', makeSiteTraces('feeling'), feelLayout, PLOTLY_CONFIG);
  Plotly.newPlot('ts-comfort-chart', makeSiteTraces('comfort'), comfLayout, PLOTLY_CONFIG);
}

// ── SCATTER ───────────────────────────────────────────────────────────────────
const X_LABELS = {
  air_temp_f: 'Kestrel air temperature (°F)',
  wbgt_f: 'WBGT (°F)',
  rh_pct: 'RH (%)',
  wind_mph: 'Wind speed (mph)',
  est_temp_f: 'Estimated temperature (°F)',
};
const Y_LABELS = {feeling_score:'Feeling Score (1–6)', comfort_score:'Comfort Score (1–4)'};

function initScatter() {
  buildSiteChips('scatter-site-toggle', 'scatter', drawScatter);
  drawScatter();
}

function drawScatter() {
  const xCol = document.getElementById('scatter-x').value;
  const yCol = document.getElementById('scatter-y').value;
  const active = getActiveSites('scatter-site-toggle');
  const visits = DATA.visits.filter(r => r[xCol] != null && r[yCol] != null);

  const traces = SITES.filter(s=>active.includes(s)).map(s => {
    const rows = visits.filter(r=>r.site===s);
    return {
      name:`Site ${s}`,
      x: rows.map(r=>r[xCol]),
      y: rows.map(r=>r[yCol]),
      mode:'markers',
      marker:{color:SC[s], size:8, opacity:0.8, line:{width:0.5, color:'white'}},
      hovertemplate:`Site ${s}<br>${X_LABELS[xCol]}: %{x:.1f}<br>${Y_LABELS[yCol]}: %{y}<extra></extra>`,
    };
  });

  Plotly.newPlot('scatter-chart', traces, mergeLayout({
    margin:{t:20,r:20,b:60,l:60},
    xaxis:{title:{text:X_LABELS[xCol]}},
    yaxis:{title:{text:Y_LABELS[yCol]}, dtick:1},
    legend:{orientation:'h', y:-0.2},
  }), PLOTLY_CONFIG);
}

// ── HOBO ─────────────────────────────────────────────────────────────────────
function initHobo() {
  buildSiteChips('hobo-site-toggle', 'hobo', drawHobo);
  drawHobo();
}

function drawHobo() {
  const active = getActiveSites('hobo-site-toggle');
  const hd = DATA.hobo_daily;

  function makeTrace(s, yKey, yLabel) {
    const rows = hd.filter(r=>r.site===s).sort((a,b)=>a.date.localeCompare(b.date));
    return {
      name:`Site ${s}`,
      x:rows.map(r=>r.date),
      y:rows.map(r=>r[yKey]),
      mode:'lines',
      line:{color:SC[s], width:1.8},
      hovertemplate:`Site ${s}<br>%{x}: %{y:.1f}${yLabel}<extra></extra>`,
    };
  }

  const tempTraces = SITES.filter(s=>active.includes(s)).map(s=>makeTrace(s,'temp_f','°F'));
  const rhTraces   = SITES.filter(s=>active.includes(s)).map(s=>makeTrace(s,'rh','%'));

  const hoboLegend = {orientation:'h', x:0.5, xanchor:'center', y:-0.2, yanchor:'top'};
  Plotly.newPlot('hobo-temp-chart', tempTraces, mergeLayout({
    margin:{t:10,r:20,b:90,l:55},
    xaxis:{title:{text:'Date'}},
    yaxis:{title:{text:'Temperature (°F)'}, rangemode:'normal'},
    legend:hoboLegend,
    hovermode:'x unified',
  }), PLOTLY_CONFIG);

  Plotly.newPlot('hobo-rh-chart', rhTraces, mergeLayout({
    margin:{t:10,r:20,b:90,l:55},
    xaxis:{title:{text:'Date'}},
    yaxis:{title:{text:'Relative Humidity (%)'}, rangemode:'normal'},
    legend:hoboLegend,
    hovermode:'x unified',
  }), PLOTLY_CONFIG);
}

// ── RAW DATA ──────────────────────────────────────────────────────────────────
let rawSortCol = 'visit_date';
let rawSortDir = 1;
let rawFiltered = [];

function initRawData() {
  // Populate filter dropdowns
  const feelSel = document.getElementById('raw-feeling');
  DATA.feeling_order.forEach(f => {
    const o = document.createElement('option');
    o.value = f; o.textContent = f;
    feelSel.appendChild(o);
  });
  const comfSel = document.getElementById('raw-comfort');
  DATA.comfort_order.forEach(c => {
    const o = document.createElement('option');
    o.value = c; o.textContent = c;
    comfSel.appendChild(o);
  });
  filterTable();
}

function feelClass(label) {
  if (!label) return '';
  const l = label.toLowerCase();
  if (l.includes('very hot')) return 'pill feel-very-hot';
  if (l.includes('hot')) return 'pill feel-hot';
  if (l.includes('warm')) return 'pill feel-warm';
  if (l.includes('neutral')) return 'pill feel-neutral';
  if (l.includes('cool')) return 'pill feel-cool';
  return 'pill';
}
function comfClass(label) {
  if (!label) return '';
  const l = label.toLowerCase();
  if (l.includes('very uncomf')) return 'pill comf-very';
  if (l.includes('uncomfortable')) return 'pill comf-uncomf';
  if (l.includes('slightly')) return 'pill comf-slight';
  if (l.includes('comfort')) return 'pill comf-ok';
  return 'pill';
}
function siteBadge(s) {
  return `<span class="pill badge-${s}">Site ${s}</span>`;
}

function filterTable() {
  const search = (document.getElementById('raw-search').value || '').toLowerCase();
  const site   = document.getElementById('raw-site').value;
  const feel   = document.getElementById('raw-feeling').value;
  const comf   = document.getElementById('raw-comfort').value;

  rawFiltered = DATA.visits.filter(r => {
    if (site && String(r.site) !== site) return false;
    if (feel && r.feeling_label !== feel) return false;
    if (comf && r.comfort_label !== comf) return false;
    if (search) {
      const haystack = [r.visit_date, `Site ${r.site}`, r.period_key,
        r.feeling_label, r.comfort_label, String(r.est_temp_f ?? '')].join(' ').toLowerCase();
      if (!haystack.includes(search)) return false;
    }
    return true;
  });

  sortAndRender();
}

function sortTable(col) {
  if (rawSortCol === col) rawSortDir *= -1;
  else { rawSortCol = col; rawSortDir = 1; }
  document.querySelectorAll('#raw-table th').forEach(th => {
    th.classList.remove('sort-asc','sort-desc');
  });
  const cols = ['site','visit_date','period_key','feeling_label','feeling_score',
                'comfort_label','comfort_score','est_temp_f','air_temp_f','wbgt_f','rh_pct','wind_mph'];
  const idx = cols.indexOf(col);
  if (idx >= 0) {
    const th = document.querySelectorAll('#raw-table th')[idx];
    th.classList.add(rawSortDir === 1 ? 'sort-asc' : 'sort-desc');
  }
  sortAndRender();
}

function sortAndRender() {
  const col = rawSortCol, dir = rawSortDir;
  const sorted = [...rawFiltered].sort((a,b) => {
    const av = a[col], bv = b[col];
    if (av == null) return 1; if (bv == null) return -1;
    return (av < bv ? -1 : av > bv ? 1 : 0) * dir;
  });
  renderTable(sorted);
}

function renderTable(rows) {
  const tbody = document.getElementById('raw-tbody');
  const n = rows.length;
  tbody.innerHTML = rows.map(r => `<tr>
    <td>${siteBadge(r.site)}</td>
    <td>${r.visit_date || '—'}</td>
    <td>${r.period_key || '—'}</td>
    <td><span class="${feelClass(r.feeling_label)}">${r.feeling_label || '—'}</span></td>
    <td>${r.feeling_score ?? '—'}</td>
    <td><span class="${comfClass(r.comfort_label)}">${r.comfort_label || '—'}</span></td>
    <td>${r.comfort_score ?? '—'}</td>
    <td>${r.est_temp_f != null ? r.est_temp_f.toFixed(1) : '—'}</td>
    <td>${r.air_temp_f != null ? r.air_temp_f.toFixed(1) : '—'}</td>
    <td>${r.wbgt_f != null ? r.wbgt_f.toFixed(1) : '—'}</td>
    <td>${r.rh_pct != null ? r.rh_pct.toFixed(1) : '—'}</td>
    <td>${r.wind_mph != null ? r.wind_mph.toFixed(1) : '—'}</td>
  </tr>`).join('');

  document.getElementById('raw-count').textContent =
    `Showing ${n} of ${DATA.visits.length} records`;

  // Stats
  const statsEl = document.getElementById('raw-stats');
  const feelAvg = rows.filter(r=>r.feeling_score!=null).reduce((s,r)=>s+r.feeling_score,0) /
                  (rows.filter(r=>r.feeling_score!=null).length || 1);
  const comfAvg = rows.filter(r=>r.comfort_score!=null).reduce((s,r)=>s+r.comfort_score,0) /
                  (rows.filter(r=>r.comfort_score!=null).length || 1);
  const tempAvg = rows.filter(r=>r.air_temp_f!=null).reduce((s,r)=>s+r.air_temp_f,0) /
                  (rows.filter(r=>r.air_temp_f!=null).length || 1);
  statsEl.innerHTML = `
    <div class="stat-box"><div class="n">${n}</div><div class="lbl">Records</div></div>
    <div class="stat-box"><div class="n">${feelAvg.toFixed(1)}</div><div class="lbl">Avg feeling</div></div>
    <div class="stat-box"><div class="n">${comfAvg.toFixed(1)}</div><div class="lbl">Avg comfort</div></div>
    <div class="stat-box"><div class="n">${isFinite(tempAvg)?tempAvg.toFixed(1)+'°F':'—'}</div><div class="lbl">Avg air temp</div></div>
  `;
}

function exportCSV() {
  const cols = ['site','visit_date','period_key','feeling_label','feeling_score',
                'comfort_label','comfort_score','est_temp_f','air_temp_f','wbgt_f','rh_pct','wind_mph'];
  const header = cols.join(',');
  const rows = rawFiltered.map(r => cols.map(c => {
    const v = r[c];
    return v == null ? '' : (typeof v === 'string' && v.includes(',') ? `"${v}"` : v);
  }).join(','));
  const csv = [header, ...rows].join('\n');
  const a = document.createElement('a');
  a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
  a.download = 'farish_year2_visits.csv';
  a.click();
}

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const hn = document.getElementById('header-cal');
  if (hn && DATA.summary && DATA.summary.hobo_calibration_note) {
    hn.textContent = DATA.summary.hobo_calibration_note;
  }
  initialised['overview'] = true;
  drawOverview();
});
</script>
</body>
</html>
"""


def build_html(data: dict) -> str:
    data_json = json.dumps(data, default=str)
    return HTML_TEMPLATE.replace("__DATA_JSON__", data_json)


def main():
    print("Loading Kestrel data…")
    kdf = load_kestrel()
    print(f"  {len(kdf)} records loaded")

    print("Loading HOBO data…")
    hdf = load_hobo()
    print(f"  {len(hdf)} HOBO readings loaded")

    print("Preparing datasets…")
    data = prepare(kdf, hdf)

    print("Building HTML…")
    html = build_html(data)

    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_HTML}  ({len(html)//1024} KB)")


if __name__ == "__main__":
    main()
