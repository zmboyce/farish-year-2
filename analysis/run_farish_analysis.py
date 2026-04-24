#!/usr/bin/env python3
"""
Farish Year 2 — Kestrel + HOBO figures and tables.
Reads Excel under Data/; writes tables and PNGs to analysis/outputs/.
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib.font_manager as fm
from matplotlib.font_manager import FontProperties
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from hobo_calibration import HOBO_AIR_TEMP_OFFSET_F, apply_hobo_air_temp_calibration, offsets_table
from kestrel_calibration import (
    KESTREL_AIR_TEMP_OFFSET_F,
    KESTREL_WBGT_OFFSET_F,
    apply_kestrel_calibrations,
    kestrel_offsets_table,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "Data"
FONTS = ROOT / "fonts"
OUT = Path(__file__).resolve().parent / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

# ── Colour palette ────────────────────────────────────────────────────────────
SITE_COLORS = {
    1: "#1F6B8E",  # steel blue
    2: "#C96A1E",  # warm amber
    3: "#3E7E50",  # forest green
    4: "#7B4F9E",  # muted purple
}
SITE_LABELS = {i: f"Site {i}" for i in SITE_COLORS}

# Sequential shades for exposure threshold bars (light to dark)
THRESH_COLORS = ["#A8C8E0", "#4A90BF", "#1A4F72"]

# ── Categorical scores ────────────────────────────────────────────────────────
FEELING_SCORE = {
    "Slightly_Cool": 1, "Cool": 1, "Neutral": 2, "Slightly_Warm": 3,
    "Warm": 4, "Hot": 5, "Very_Hot": 6,
}
COMFORT_SCORE = {
    "Comfortable": 1, "Slightly_Uncomfortable": 2,
    "Uncomfortable": 3, "Very_Uncomfortable": 4,
}


# ── Font setup ────────────────────────────────────────────────────────────────
def setup_fonts() -> str:
    """Register Avenir Next LT Pro from fonts/ and return family name to use."""
    for p in FONTS.glob("*.otf"):
        fm.fontManager.addfont(str(p))
    available = {f.name for f in fm.fontManager.ttflist}
    for candidate in [
        "Avenir Next LT Pro",
        "AvenirNextLTPro-Cn",
        "Avenir Next LT Pro Condensed",
        "Avenir Next LT Pro Demi Condensed",
    ]:
        if candidate in available:
            return candidate
    # Fallback: pick anything with "Avenir" in the name
    avenir = [n for n in available if "avenir" in n.lower()]
    return avenir[0] if avenir else "DejaVu Sans"


def apply_style(font_family: str) -> None:
    plt.rcParams.update({
        "font.family": font_family,
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": "#e0e0e0",
        "grid.linewidth": 0.7,
        "axes.linewidth": 0.8,
        "axes.edgecolor": "#888888",
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "xtick.color": "#555555",
        "ytick.color": "#555555",
        "axes.labelcolor": "#333333",
        "text.color": "#222222",
        "figure.dpi": 150,
    })


# ── Data loading ──────────────────────────────────────────────────────────────
def site_num_from_cell(s: str) -> int | None:
    if not isinstance(s, str):
        return None
    m = re.match(r"Site\s*(\d+)", s.strip(), re.I)
    return int(m.group(1)) if m else None


def load_kestrel() -> pd.DataFrame:
    path = DATA / "Kestrel" / "Kestrel Data_Farish St_Year 2.xlsx"
    df = pd.read_excel(path, sheet_name="final")
    df["site"] = df["2. Site #"].map(site_num_from_cell)
    df = df.dropna(subset=["site"])
    df["site"] = df["site"].astype(int)
    df["air_temp_f"] = pd.to_numeric(df["6c. Record the Air Temperature"], errors="coerce")
    df["wbgt_f"] = pd.to_numeric(df["ADJUSTED Record the Wet Bulb Globe Temperature"], errors="coerce")
    df["rh_pct"] = pd.to_numeric(df["6d. Record the Humidity"], errors="coerce")
    df["wind_mph"] = pd.to_numeric(df["6b. Record Wind Speed (mph)"], errors="coerce")
    df["est_temp_f"] = pd.to_numeric(df["5. What would you estimate as the current temperature?"], errors="coerce")
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
        df["visit_date"] - pd.to_timedelta(df["visit_date"].dt.dayofweek, unit="D")
    ).dt.normalize()
    return apply_kestrel_calibrations(df)


def c_to_f(c: pd.Series) -> pd.Series:
    return c * 9.0 / 5.0 + 32.0


def load_all_hobo() -> pd.DataFrame:
    frames = []
    for path in sorted(DATA.glob("HOBO/*.xlsx")):
        site_m = re.search(r"Site\s*(\d+)", path.name, re.I)
        if not site_m:
            continue
        site = int(site_m.group(1))
        d = pd.read_excel(path)
        d["dt"] = pd.to_datetime(d["Date-Time (CDT)"])
        d["site"] = site
        d["temp_f"] = c_to_f(pd.to_numeric(d["Temperature , °C"], errors="coerce"))
        d["rh"] = pd.to_numeric(d["RH , %"], errors="coerce")
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _medium_cn_fp(size: float | None = None) -> FontProperties:
    """FontProperties for AvenirNextLTPro-MediumCn (axis title labels)."""
    fp = FontProperties(fname=str(FONTS / "AvenirNextLTPro-MediumCn.otf"))
    if size is not None:
        fp.set_size(size)
    return fp


def clean_ax(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cccccc")
    ax.spines["bottom"].set_color("#cccccc")
    ax.tick_params(length=3, color="#aaaaaa")
    # Apply MediumCn to axis title labels so they visually differ from tick labels
    for label_obj in (ax.xaxis.label, ax.yaxis.label):
        if label_obj.get_text():
            fp = _medium_cn_fp(size=label_obj.get_fontsize())
            label_obj.set_fontproperties(fp)


# ── Kestrel: table + boxplots ─────────────────────────────────────────────────
def kestrel_table_and_boxplots(df: pd.DataFrame) -> None:
    agg = (
        df.groupby("site", sort=True)[["air_temp_f", "wbgt_f", "rh_pct", "wind_mph"]]
        .mean()
        .rename(columns={
            "air_temp_f": "Average Air Temperature (F)",
            "wbgt_f": "Average Wet Bulb Globe Temperature (F)",
            "rh_pct": "Average Relative Humidity (%)",
            "wind_mph": "Average Wind Speed (mph)",
        })
    )
    overall = agg.mean().to_frame().T
    overall.index = ["Average"]
    table = pd.concat([agg, overall])
    table.index.name = "Site #"
    disp = table.copy()
    disp.index = [f"Site {i}" if isinstance(i, int) else i for i in disp.index]
    disp = disp.round(2)
    csv_path = OUT / "kestrel_avg_by_site.csv"
    disp.to_csv(csv_path)
    print("Wrote", csv_path)

    pairs = [
        ("air_temp_f", "Air temperature (°F)"),
        ("wbgt_f", "Wet bulb globe temperature (°F)"),
        ("rh_pct", "Relative humidity (%)"),
        ("wind_mph", "Wind speed (mph)"),
    ]
    sites = sorted(df["site"].unique())

    fig, axes = plt.subplots(2, 2, figsize=(9, 7))
    fig.subplots_adjust(hspace=0.42, wspace=0.32, bottom=0.14, top=0.88)

    for ax, (col, ylabel) in zip(axes.flat, pairs):
        data = [df.loc[df["site"] == s, col].dropna().values for s in sites]
        bp = ax.boxplot(
            data,
            patch_artist=True,
            showmeans=True,
            tick_labels=[f"Site {s}" for s in sites],
            medianprops=dict(color="white", linewidth=2.2, solid_capstyle="butt"),
            meanprops=dict(
                marker="D", markersize=5.5,
                markerfacecolor="white", markeredgecolor="#444444", markeredgewidth=0.8,
            ),
            whiskerprops=dict(color="#888888", linewidth=1.2),
            capprops=dict(color="#888888", linewidth=1.2),
            flierprops=dict(
                marker="o", markersize=4,
                markerfacecolor="none", markeredgewidth=0.6, markeredgecolor="#aaaaaa",
            ),
            boxprops=dict(linewidth=0),
            widths=0.55,
        )
        for patch, site in zip(bp["boxes"], sites):
            patch.set_facecolor(SITE_COLORS[site])
            patch.set_alpha(0.88)
        ax.set_ylabel(ylabel, fontsize=9.5)
        ax.tick_params(axis="x", labelsize=9.5)
        clean_ax(ax)

    fig.suptitle("Kestrel measurements by site (Year 2)", fontsize=12, fontweight="bold", y=0.97)

    # Figure-level legend: anatomy only (sites already labelled on x-axis)
    legend_handles = [
        mpatches.Patch(facecolor="#aaaaaa", edgecolor="none", alpha=0.85, label="IQR (25th–75th percentile)"),
        Line2D([0], [0], color="white", linewidth=2, label="Median",
               path_effects=[__import__("matplotlib.patheffects", fromlist=["withStroke"])
                              .withStroke(linewidth=3, foreground="#888888")]),
        Line2D([0], [0], marker="D", linestyle="none", markersize=5.5,
               markerfacecolor="white", markeredgecolor="#444444", markeredgewidth=0.8,
               label="Mean"),
    ]
    fig.legend(handles=legend_handles, loc="lower center", ncol=3,
               frameon=False, fontsize=9, bbox_to_anchor=(0.5, 0.005))

    p = OUT / "kestrel_boxplots_2x2.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)


# ── Kestrel: scatter estimated vs measured ────────────────────────────────────
def kestrel_scatter_est_vs_measured(df: pd.DataFrame) -> None:
    x = df["est_temp_f"]
    y = df["air_temp_f"]
    sites = df["site"]
    m = x.notna() & y.notna()

    fig, ax = plt.subplots(figsize=(6.5, 6))
    for site in sorted(df["site"].unique()):
        mask = m & (sites == site)
        ax.scatter(
            x[mask], y[mask],
            color=SITE_COLORS[site], alpha=0.80,
            edgecolors="white", linewidths=0.5, s=55,
            label=SITE_LABELS[site], zorder=3,
        )
    lo = float(min(x[m].min(), y[m].min())) - 2
    hi = float(max(x[m].max(), y[m].max())) + 2
    ax.plot([lo, hi], [lo, hi], color="#555555", linestyle="--", lw=1.3,
            label="y = x  (perfect match)", zorder=2)
    ax.set_xlabel("Estimated air temperature (°F)")
    ax.set_ylabel("Kestrel air temperature (°F)")
    ax.set_title("Estimated vs. measured air temperature", fontsize=11, fontweight="bold", pad=10)
    ax.set_aspect("equal", adjustable="box")
    ax.legend(loc="upper left", framealpha=0.9, edgecolor="#dddddd", fontsize=9)
    clean_ax(ax)
    fig.tight_layout()
    p = OUT / "kestrel_estimated_vs_measured.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)


# ── Kestrel: perception bar charts ────────────────────────────────────────────
def kestrel_bars_perception(df: pd.DataFrame) -> None:
    feel = (df.dropna(subset=["feeling_score", "site"])
            .groupby("site")["feeling_score"]
            .agg(["mean", "sem"]))
    comf = (df.dropna(subset=["comfort_score", "site"])
            .groupby("site")["comfort_score"]
            .agg(["mean", "sem"]))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4.8))
    fig.subplots_adjust(wspace=0.38, top=0.78, bottom=0.12)
    w = 0.55

    for ax, data, title, scale_note in [
        (ax1, feel,
         "Air temperature feeling",
         "1 = slightly cool  ·  6 = very hot"),
        (ax2, comf,
         "Thermal comfort",
         "1 = comfortable  ·  4 = very uncomfortable"),
    ]:
        x = np.arange(len(data))
        colors = [SITE_COLORS[s] for s in data.index]
        ax.bar(x, data["mean"], width=w, color=colors, alpha=0.88,
               yerr=data["sem"], capsize=4,
               error_kw=dict(elinewidth=1, ecolor="#555555", capthick=1))
        ax.set_xticks(x)
        ax.set_xticklabels([f"Site {i}" for i in data.index])
        ax.set_ylabel("Mean score")
        # Two-line axis title: bold name, then lighter scale note
        ax.set_title(title, fontsize=10.5, fontweight="bold", pad=18)
        ax.text(0.5, 1.015, scale_note, transform=ax.transAxes,
                ha="center", va="bottom", fontsize=8, color="#777777",
                style="italic")
        clean_ax(ax)

    fig.suptitle("Heat perception scores by site (Year 2)", fontsize=12,
                 fontweight="bold", y=0.98)
    p = OUT / "kestrel_perception_bars_by_site.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)


def _sem(s: pd.Series) -> float:
    s = s.dropna()
    return float(s.sem(ddof=1)) if len(s) > 1 else 0.0


# ── Kestrel: perception over time ─────────────────────────────────────────────
def kestrel_perception_daily_timeseries(df: pd.DataFrame) -> None:
    """Mean feeling / comfort scores by calendar day (all site readings that day)."""
    d = df.dropna(subset=["visit_date", "feeling_score", "comfort_score"])
    daily = (
        d.groupby("visit_date", sort=True)
        .agg(
            feeling_mean=("feeling_score", "mean"),
            feeling_sem=("feeling_score", _sem),
            comfort_mean=("comfort_score", "mean"),
            comfort_sem=("comfort_score", _sem),
            n=("feeling_score", "count"),
        )
        .reset_index()
    )
    daily.to_csv(OUT / "kestrel_perception_daily_summary.csv", index=False)
    print("Wrote", OUT / "kestrel_perception_daily_summary.csv")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5.8), sharex=True)
    fig.subplots_adjust(hspace=0.22, top=0.91)

    x = daily["visit_date"]
    ax1.errorbar(
        x, daily["feeling_mean"], yerr=daily["feeling_sem"],
        fmt="o-", color="#1F6B8E", ecolor="#555555", capsize=3.5,
        markersize=5, lw=1.4, elinewidth=1,
    )
    ax1.set_ylabel("Mean score")
    ax1.set_ylim(0.5, 6.5)
    ax1.set_yticks(range(1, 7))
    ax1.set_title(
        "Air temperature feeling (daily mean across sites)",
        fontsize=10.5, fontweight="bold", loc="left",
    )
    ax1.text(0, 1.02, "1 = slightly cool  ·  6 = very hot", transform=ax1.transAxes,
             fontsize=8, color="#777777", style="italic", va="bottom")
    clean_ax(ax1)

    ax2.errorbar(
        x, daily["comfort_mean"], yerr=daily["comfort_sem"],
        fmt="s-", color="#7B4F9E", ecolor="#555555", capsize=3.5,
        markersize=4.5, lw=1.4, elinewidth=1,
    )
    ax2.set_ylabel("Mean score")
    ax2.set_ylim(0.5, 4.5)
    ax2.set_yticks(range(1, 5))
    ax2.set_xlabel("Visit date (local)")
    ax2.set_title(
        "Thermal comfort (daily mean across sites)",
        fontsize=10.5, fontweight="bold", loc="left",
    )
    ax2.text(0, 1.02, "1 = comfortable  ·  4 = very uncomfortable", transform=ax2.transAxes,
             fontsize=8, color="#777777", style="italic", va="bottom")
    clean_ax(ax2)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax2.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.suptitle(
        "Crew heat perception over the monitoring period (Year 2)",
        fontsize=11.5, fontweight="bold", y=0.98,
    )
    p = OUT / "kestrel_perception_daily_timeseries.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)


def kestrel_perception_by_period_timeseries(df: pd.DataFrame) -> None:
    """2 pm vs 6 pm field blocks: daily mean across the four sites."""
    d = df.dropna(subset=["visit_date", "period_key", "feeling_score", "comfort_score"])
    # Expect labels like "2pm" / "6pm"
    agg = (
        d.groupby(["visit_date", "period_key"], sort=True)
        .agg(
            feeling_mean=("feeling_score", "mean"),
            comfort_mean=("comfort_score", "mean"),
        )
        .reset_index()
    )
    periods = sorted(agg["period_key"].unique())
    period_colors = {"2pm": "#1F6B8E", "6pm": "#C96A1E"}
    markers = {"2pm": "o", "6pm": "s"}

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5.8), sharex=True)
    fig.subplots_adjust(hspace=0.22, top=0.86)

    for per in periods:
        sub = agg[agg["period_key"] == per].sort_values("visit_date")
        kw = dict(
            label=per,
            color=period_colors.get(per, "#333333"),
            marker=markers.get(per, "o"),
            ms=4.5,
            lw=1.4,
        )
        ax1.plot(sub["visit_date"], sub["feeling_mean"], **kw)
        ax2.plot(sub["visit_date"], sub["comfort_mean"], **kw)

    ax1.set_ylabel("Mean score")
    ax1.set_ylim(0.5, 6.5)
    ax1.set_yticks(range(1, 7))
    ax1.set_title("Air temperature feeling by field period", fontsize=10.5, fontweight="bold", loc="left")
    ax1.legend(loc="upper right", framealpha=0.92, edgecolor="#dddddd", fontsize=9)
    clean_ax(ax1)

    ax2.set_ylabel("Mean score")
    ax2.set_ylim(0.5, 4.5)
    ax2.set_yticks(range(1, 5))
    ax2.set_xlabel("Visit date (local)")
    ax2.set_title("Thermal comfort by field period", fontsize=10.5, fontweight="bold", loc="left")
    ax2.legend(loc="upper right", framealpha=0.92, edgecolor="#dddddd", fontsize=9)
    clean_ax(ax2)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax2.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.suptitle(
        "Perception by time of day (daily mean across sites)",
        fontsize=11.5, fontweight="bold", y=0.98,
    )
    p = OUT / "kestrel_perception_by_period_timeseries.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)


def kestrel_perception_vs_environment(df: pd.DataFrame) -> None:
    """Link ordinal perception to measured heat stress (same moment as survey)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4.6))
    fig.subplots_adjust(wspace=0.35, top=0.88)

    for site in sorted(df["site"].unique()):
        m = df["site"] == site
        ax1.scatter(
            df.loc[m, "wbgt_f"],
            df.loc[m, "feeling_score"],
            color=SITE_COLORS[site], alpha=0.82, s=48,
            edgecolors="white", linewidths=0.45,
            label=SITE_LABELS[site], zorder=3,
        )
        ax2.scatter(
            df.loc[m, "air_temp_f"],
            df.loc[m, "comfort_score"],
            color=SITE_COLORS[site], alpha=0.82, s=48,
            edgecolors="white", linewidths=0.45,
            label=SITE_LABELS[site], zorder=3,
        )

    ax1.set_xlabel("Wet bulb globe temperature (°F)")
    ax1.set_ylabel("Temperature feeling score")
    ax1.set_title("Feeling vs. WBGT", fontsize=10.5, fontweight="bold")
    ax1.set_yticks(range(1, 7))
    ax1.legend(loc="lower right", framealpha=0.92, edgecolor="#dddddd", fontsize=8.5)
    clean_ax(ax1)

    ax2.set_xlabel("Air temperature (°F)")
    ax2.set_ylabel("Thermal comfort score")
    ax2.set_title("Comfort vs. air temperature", fontsize=10.5, fontweight="bold")
    ax2.set_yticks(range(1, 5))
    ax2.legend(loc="best", framealpha=0.92, edgecolor="#dddddd", fontsize=8.5)
    clean_ax(ax2)

    fig.suptitle(
        "Perception vs. measured conditions (each point = one site visit)",
        fontsize=11.5, fontweight="bold", y=0.98,
    )
    p = OUT / "kestrel_perception_vs_environment.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)


def kestrel_correlation_table(df: pd.DataFrame) -> None:
    """Spearman correlation matrix: perception scores vs Kestrel measurements."""
    cols = ["feeling_score", "comfort_score", "air_temp_f", "wbgt_f", "rh_pct", "wind_mph"]
    sub = df[cols].dropna()
    if len(sub) < 5:
        return
    cm = sub.corr(method="spearman").round(3)
    cm.to_csv(OUT / "kestrel_spearman_correlation_matrix.csv")
    print("Wrote", OUT / "kestrel_spearman_correlation_matrix.csv")


# Category order for stacked bars (matches survey wording after underscore → space)
FEELING_LABEL_ORDER = [
    "Slightly Cool", "Cool", "Neutral", "Slightly Warm", "Warm", "Hot", "Very Hot",
]
COMFORT_LABEL_ORDER = [
    "Comfortable", "Slightly Uncomfortable", "Uncomfortable", "Very Uncomfortable",
]


def kestrel_perception_timeseries_by_site(df: pd.DataFrame) -> None:
    """Daily mean feeling and comfort, one line per site (mean if same site visited twice same day)."""
    d = df.dropna(subset=["visit_date", "site", "feeling_score", "comfort_score"])
    ds = (
        d.groupby(["visit_date", "site"], sort=True)
        .agg(feeling=("feeling_score", "mean"), comfort=("comfort_score", "mean"))
        .reset_index()
    )
    sites = sorted(ds["site"].unique())

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5.8), sharex=True)
    fig.subplots_adjust(hspace=0.22, top=0.90)
    for site in sites:
        sub = ds[ds["site"] == site].sort_values("visit_date")
        kw = dict(marker="o", ms=3.5, lw=1.35, label=SITE_LABELS[site], color=SITE_COLORS[site])
        ax1.plot(sub["visit_date"], sub["feeling"], **kw)
        ax2.plot(sub["visit_date"], sub["comfort"], **kw)
    ax1.set_ylabel("Mean score")
    ax1.set_ylim(0.5, 6.5)
    ax1.set_yticks(range(1, 7))
    ax1.set_title("Air temperature feeling", fontsize=10.5, fontweight="bold", loc="left")
    ax1.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.20), frameon=False, fontsize=8.5)
    clean_ax(ax1)
    ax2.set_ylabel("Mean score")
    ax2.set_ylim(0.5, 4.5)
    ax2.set_yticks(range(1, 5))
    ax2.set_xlabel("Visit date (local)")
    ax2.set_title("Thermal comfort", fontsize=10.5, fontweight="bold", loc="left")
    clean_ax(ax2)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax2.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.suptitle("Perception time series by site (Year 2)", fontsize=11.5, fontweight="bold", y=0.985)
    p = OUT / "kestrel_perception_timeseries_by_site.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)


def kestrel_perception_jitter_strip(df: pd.DataFrame) -> None:
    """Each point = one site visit; horizontal jitter by site reveals same-day spread."""
    d = df.dropna(subset=["visit_date", "site", "feeling_score", "comfort_score"]).copy()
    base = mdates.date2num(d["visit_date"])
    offsets = {s: (i - 1.5) * 0.22 for i, s in enumerate(sorted(d["site"].unique()))}
    d["_x"] = base + d["site"].map(offsets)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.2), sharex=True)
    fig.subplots_adjust(hspace=0.22, top=0.91)
    for site in sorted(d["site"].unique()):
        m = d["site"] == site
        c = SITE_COLORS[site]
        ax1.scatter(
            d.loc[m, "_x"], d.loc[m, "feeling_score"],
            s=42, alpha=0.85, color=c, edgecolors="white", linewidths=0.4,
            label=SITE_LABELS[site], zorder=3,
        )
        ax2.scatter(
            d.loc[m, "_x"], d.loc[m, "comfort_score"],
            s=42, alpha=0.85, color=c, edgecolors="white", linewidths=0.4,
            label=SITE_LABELS[site], zorder=3,
        )
    ax1.set_ylabel("Score")
    ax1.set_ylim(0.5, 6.5)
    ax1.set_yticks(range(1, 7))
    ax1.set_title("Air temperature feeling (all visits)", fontsize=10.5, fontweight="bold", loc="left")
    ax1.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.28), frameon=False, fontsize=8.5)
    clean_ax(ax1)
    ax2.set_ylabel("Score")
    ax2.set_ylim(0.5, 4.5)
    ax2.set_yticks(range(1, 5))
    ax2.set_xlabel("Visit date (local)")
    ax2.set_title("Thermal comfort (all visits)", fontsize=10.5, fontweight="bold", loc="left")
    clean_ax(ax2)
    for ax in (ax1, ax2):
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.suptitle(
        "Perception scores by visit (jittered by site within each day)",
        fontsize=11.5, fontweight="bold", y=0.98,
    )
    p = OUT / "kestrel_perception_jitter_by_date.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)


def _ordered_columns_present(order: list[str], cols: pd.Index) -> list[str]:
    return [c for c in order if c in cols]


def kestrel_category_stacked_by_site(df: pd.DataFrame) -> None:
    feel_ct = pd.crosstab(df["site"], df["feeling_label"])
    feel_cols = _ordered_columns_present(FEELING_LABEL_ORDER, feel_ct.columns)
    feel_ct = feel_ct[feel_cols]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.8))
    fig.subplots_adjust(wspace=0.35, top=0.82, bottom=0.25)
    x = np.arange(len(feel_ct.index))
    colors_f = plt.cm.YlOrRd(np.linspace(0.15, 0.88, len(feel_cols)))
    bottom = np.zeros(len(feel_ct.index))
    for j, col in enumerate(feel_cols):
        vals = feel_ct[col].values.astype(float)
        ax1.bar(x, vals, bottom=bottom, label=col, color=colors_f[j], width=0.65, edgecolor="white", linewidth=0.4)
        bottom += vals
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"Site {i}" for i in feel_ct.index])
    ax1.set_ylabel("Number of responses")
    ax1.set_title("Temperature feeling", fontsize=10.5, fontweight="bold")
    ax1.legend(title="Response", bbox_to_anchor=(0.5, -0.22), loc="upper center", ncol=3, fontsize=7.5, frameon=False)
    clean_ax(ax1)

    com_ct = pd.crosstab(df["site"], df["comfort_label"])
    com_cols = _ordered_columns_present(COMFORT_LABEL_ORDER, com_ct.columns)
    com_ct = com_ct[com_cols]
    colors_c = plt.cm.PuBu(np.linspace(0.25, 0.9, len(com_cols)))
    bottom = np.zeros(len(com_ct.index))
    for j, col in enumerate(com_cols):
        vals = com_ct[col].values.astype(float)
        ax2.bar(x[: len(com_ct)], vals, bottom=bottom, label=col, color=colors_c[j], width=0.65, edgecolor="white", linewidth=0.4)
        bottom += vals
    ax2.set_xticks(np.arange(len(com_ct.index)))
    ax2.set_xticklabels([f"Site {i}" for i in com_ct.index])
    ax2.set_ylabel("Number of responses")
    ax2.set_title("Thermal comfort", fontsize=10.5, fontweight="bold")
    ax2.legend(title="Response", bbox_to_anchor=(0.5, -0.18), loc="upper center", ncol=2, fontsize=8, frameon=False)
    clean_ax(ax2)

    fig.suptitle("Survey response counts by site (stacked)", fontsize=11.5, fontweight="bold", y=0.98)
    p = OUT / "kestrel_category_stacked_by_site.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)
    feel_ct.to_csv(OUT / "kestrel_feeling_counts_by_site.csv")
    com_ct.to_csv(OUT / "kestrel_comfort_counts_by_site.csv")
    print("Wrote", OUT / "kestrel_feeling_counts_by_site.csv")
    print("Wrote", OUT / "kestrel_comfort_counts_by_site.csv")


def kestrel_category_stacked_by_week(df: pd.DataFrame) -> None:
    d = df.dropna(subset=["week_start"])
    weeks = sorted(d["week_start"].unique())

    def week_label(ts: pd.Timestamp) -> str:
        return f"{ts:%b %d}"

    feel_ct = pd.crosstab(d["week_start"], d["feeling_label"])
    feel_cols = _ordered_columns_present(FEELING_LABEL_ORDER, feel_ct.columns)
    feel_ct = feel_ct.reindex(weeks).fillna(0).astype(int)[feel_cols]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.0), sharex=True)
    fig.subplots_adjust(hspace=0.35, top=0.90, bottom=0.18)
    x = np.arange(len(feel_ct.index))
    colors_f = plt.cm.YlOrRd(np.linspace(0.15, 0.88, len(feel_cols)))
    bottom = np.zeros(len(feel_ct.index))
    for j, col in enumerate(feel_cols):
        vals = feel_ct[col].values.astype(float)
        ax1.bar(x, vals, bottom=bottom, label=col, color=colors_f[j], width=0.72, edgecolor="white", linewidth=0.35)
        bottom += vals
    ax1.set_ylabel("Count")
    ax1.set_title("Temperature feeling (week of Monday)", fontsize=10.5, fontweight="bold", loc="left")
    ax1.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.32), frameon=False, fontsize=7.5)
    clean_ax(ax1)

    com_ct = pd.crosstab(d["week_start"], d["comfort_label"])
    com_cols = _ordered_columns_present(COMFORT_LABEL_ORDER, com_ct.columns)
    com_ct = com_ct.reindex(weeks).fillna(0).astype(int)[com_cols]
    colors_c = plt.cm.PuBu(np.linspace(0.25, 0.9, len(com_cols)))
    bottom = np.zeros(len(com_ct.index))
    for j, col in enumerate(com_cols):
        vals = com_ct[col].values.astype(float)
        ax2.bar(x, vals, bottom=bottom, label=col, color=colors_c[j], width=0.72, edgecolor="white", linewidth=0.35)
        bottom += vals
    ax2.set_ylabel("Count")
    ax2.set_xlabel("Week starting (Monday, local)")
    ax2.set_title("Thermal comfort (week of Monday)", fontsize=10.5, fontweight="bold", loc="left")
    ax2.set_xticks(x)
    ax2.set_xticklabels([week_label(pd.Timestamp(t)) for t in feel_ct.index], rotation=35, ha="right")
    ax2.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.28), frameon=False, fontsize=8)
    clean_ax(ax2)

    fig.suptitle("Survey response counts by field week (stacked)", fontsize=11.5, fontweight="bold", y=0.98)
    p = OUT / "kestrel_category_stacked_by_week.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)
    feel_ct.to_csv(OUT / "kestrel_feeling_counts_by_week.csv")
    com_ct.to_csv(OUT / "kestrel_comfort_counts_by_week.csv")
    print("Wrote", OUT / "kestrel_feeling_counts_by_week.csv")
    print("Wrote", OUT / "kestrel_comfort_counts_by_week.csv")


def kestrel_perception_vs_rh_wind(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 7.8))
    fig.subplots_adjust(wspace=0.32, hspace=0.38, top=0.91)

    for site in sorted(df["site"].unique()):
        m = df["site"] == site
        kw = dict(
            color=SITE_COLORS[site], alpha=0.82, s=44,
            edgecolors="white", linewidths=0.45, label=SITE_LABELS[site], zorder=3,
        )
        axes[0, 0].scatter(df.loc[m, "rh_pct"], df.loc[m, "feeling_score"], **kw)
        axes[0, 1].scatter(df.loc[m, "wind_mph"], df.loc[m, "feeling_score"], **kw)
        axes[1, 0].scatter(df.loc[m, "rh_pct"], df.loc[m, "comfort_score"], **kw)
        axes[1, 1].scatter(df.loc[m, "wind_mph"], df.loc[m, "comfort_score"], **kw)

    axes[0, 0].set_xlabel("Relative humidity (%)")
    axes[0, 0].set_ylabel("Temperature feeling score")
    axes[0, 0].set_yticks(range(1, 7))
    axes[0, 0].set_title("Feeling vs. humidity", fontsize=10, fontweight="bold")
    axes[0, 0].legend(loc="lower right", fontsize=7.5, framealpha=0.92, edgecolor="#dddddd")
    clean_ax(axes[0, 0])

    axes[0, 1].set_xlabel("Wind speed (mph)")
    axes[0, 1].set_ylabel("Temperature feeling score")
    axes[0, 1].set_yticks(range(1, 7))
    axes[0, 1].set_title("Feeling vs. wind", fontsize=10, fontweight="bold")
    clean_ax(axes[0, 1])

    axes[1, 0].set_xlabel("Relative humidity (%)")
    axes[1, 0].set_ylabel("Thermal comfort score")
    axes[1, 0].set_yticks(range(1, 5))
    axes[1, 0].set_title("Comfort vs. humidity", fontsize=10, fontweight="bold")
    clean_ax(axes[1, 0])

    axes[1, 1].set_xlabel("Wind speed (mph)")
    axes[1, 1].set_ylabel("Thermal comfort score")
    axes[1, 1].set_yticks(range(1, 5))
    axes[1, 1].set_title("Comfort vs. wind", fontsize=10, fontweight="bold")
    clean_ax(axes[1, 1])

    fig.suptitle(
        "Perception vs. humidity and wind (each point = one site visit)",
        fontsize=11.5, fontweight="bold", y=0.98,
    )
    p = OUT / "kestrel_perception_vs_rh_wind.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)


def _hobo_daily_mean_all_sites(all_h: pd.DataFrame) -> pd.DataFrame:
    h = all_h.copy()
    h["day"] = h["dt"].dt.normalize()
    return h.groupby("day", as_index=False).agg(
        hobo_temp_f_mean=("temp_f", "mean"),
        hobo_rh_mean=("rh", "mean"),
    )


def kestrel_hobo_daily_context(df: pd.DataFrame, all_h: pd.DataFrame) -> None:
    """Days where both crew visits and HOBO loggers have data: ambient context vs. perception."""
    d = df.dropna(subset=["visit_date", "feeling_score", "comfort_score"])
    crew = (
        d.groupby("visit_date", sort=True)
        .agg(
            feeling_mean=("feeling_score", "mean"),
            comfort_mean=("comfort_score", "mean"),
            n_visits=("feeling_score", "count"),
        )
        .reset_index()
    )
    hobo = _hobo_daily_mean_all_sites(all_h)
    merged = crew.merge(
        hobo,
        left_on="visit_date",
        right_on="day",
        how="inner",
    ).drop(columns=["day"])
    merged.to_csv(OUT / "kestrel_hobo_daily_merged.csv", index=False)
    print("Wrote", OUT / "kestrel_hobo_daily_merged.csv")

    if merged.empty:
        return

    fig, axes = plt.subplots(2, 1, figsize=(10, 5.8), sharex=True)
    fig.subplots_adjust(hspace=0.28, top=0.90)

    x = merged["visit_date"]
    axes[0].fill_between(
        x, merged["hobo_temp_f_mean"], alpha=0.22, color="#555555", step=None,
    )
    axes[0].plot(x, merged["hobo_temp_f_mean"], color="#333333", lw=1.6, marker="s", ms=3.5, label="HOBO daily mean temp (°F, all loggers)")
    ax0b = axes[0].twinx()
    ax0b.plot(x, merged["feeling_mean"], color="#1F6B8E", lw=1.5, marker="o", ms=4, label="Crew mean feeling score")
    axes[0].set_ylabel("HOBO temperature (°F)", color="#333333")
    ax0b.set_ylabel("Feeling score (1-6)", color="#1F6B8E")
    axes[0].set_title("Daily context: logger temperature vs. temperature-feeling", fontsize=10.5, fontweight="bold", loc="left")
    axes[0].tick_params(axis="y", labelcolor="#333333")
    ax0b.tick_params(axis="y", labelcolor="#1F6B8E")
    ax0b.set_ylim(0.5, 6.5)
    h1, l1 = axes[0].get_legend_handles_labels()
    h2, l2 = ax0b.get_legend_handles_labels()
    ax0b.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=8, framealpha=0.92, edgecolor="#dddddd")
    axes[0].spines["top"].set_visible(False)
    ax0b.spines["top"].set_visible(False)

    axes[1].plot(
        x, merged["hobo_rh_mean"], color="#4A90BF", lw=1.5, marker="s", ms=3.5, label="HOBO daily mean RH (%, all loggers)",
    )
    ax1b = axes[1].twinx()
    ax1b.plot(x, merged["comfort_mean"], color="#7B4F9E", lw=1.5, marker="o", ms=4, label="Crew mean comfort score")
    axes[1].set_ylabel("HOBO relative humidity (%)", color="#4A90BF")
    ax1b.set_ylabel("Comfort score (1-4)", color="#7B4F9E")
    axes[1].set_xlabel("Date (calendar day)")
    axes[1].set_title("Daily context: logger humidity vs. thermal comfort", fontsize=10.5, fontweight="bold", loc="left")
    axes[1].tick_params(axis="y", labelcolor="#4A90BF")
    ax1b.tick_params(axis="y", labelcolor="#7B4F9E")
    ax1b.set_ylim(0.5, 4.5)
    h1, l1 = axes[1].get_legend_handles_labels()
    h2, l2 = ax1b.get_legend_handles_labels()
    ax1b.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=8, framealpha=0.92, edgecolor="#dddddd")
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    axes[1].xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
    fig.autofmt_xdate(rotation=30, ha="right")
    for ax in (axes[1], ax1b):
        ax.spines["top"].set_visible(False)
    clean_ax(axes[1])

    fig.suptitle(
        "HOBO daily means vs. crew perception (days with both logger and visit data)",
        fontsize=11.5, fontweight="bold", y=0.98,
    )
    p = OUT / "kestrel_hobo_daily_context.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)


def kestrel_ordinal_models(df: pd.DataFrame) -> None:
    """Proportional-odds ordinal logit (optional dependency: statsmodels)."""
    skip_path = OUT / "kestrel_ordinal_models_note.txt"
    try:
        from statsmodels.miscmodels.ordinal_model import OrderedModel
    except ImportError:
        skip_path.write_text(
            "Ordinal regression was skipped: statsmodels is not installed.\n"
            "Use a virtual environment and run:  pip install statsmodels\n"
            "Then re-run analysis/run_farish_analysis.py\n",
            encoding="utf-8",
        )
        print("Wrote", skip_path, "(statsmodels not available)")
        return

    lines: list[str] = []
    lines.append("Farish Year 2 - ordinal logit models (proportional odds)\n")
    lines.append("Outcome categories are coded 0..K-1 from survey scores 1..K.\n")
    lines.append("Predictors: WBGT (F), RH (%), wind (mph). (No separate intercept;\n")
    lines.append("OrderedModel uses threshold parameters for the cut points.)\n\n")

    exog_cols = ["wbgt_f", "rh_pct", "wind_mph"]

    def fit_one(name: str, y_col: str, sub: pd.DataFrame) -> None:
        y = (sub[y_col].astype(int) - 1).to_numpy()
        X = sub[exog_cols]
        mod = OrderedModel(y, X, distr="logit")
        res = mod.fit(method="bfgs", disp=False)
        lines.append(f"=== {name} ===\n")
        lines.append(res.summary().as_text())
        lines.append("\n\n")

    sub_f = df[["feeling_score", *exog_cols]].dropna()
    sub_c = df[["comfort_score", *exog_cols]].dropna()
    if len(sub_f) >= 20:
        try:
            fit_one("Temperature feeling (6 categories)", "feeling_score", sub_f)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"Feeling model failed to fit: {exc}\n\n")
    else:
        lines.append("Skipping feeling model: insufficient complete rows.\n\n")
    if len(sub_c) >= 20:
        try:
            fit_one("Thermal comfort (4 categories)", "comfort_score", sub_c)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"Comfort model failed to fit: {exc}\n\n")
    else:
        lines.append("Skipping comfort model: insufficient complete rows.\n\n")

    out = OUT / "kestrel_ordinal_models_summary.txt"
    out.write_text("".join(lines), encoding="utf-8")
    print("Wrote", out)


def _hobo_daily_means(all_h: pd.DataFrame) -> pd.DataFrame:
    d = all_h.copy()
    d["date"] = d["dt"].dt.floor("D")
    return d.groupby(["site", "date"], as_index=False)["temp_f"].mean()


def _style_hobo_date_axis(ax: plt.Axes) -> None:
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))


def _hobo_diurnal_profile(all_h: pd.DataFrame, start: str, end: str) -> tuple[pd.DataFrame, str, str]:
    mask = (all_h["dt"] >= start) & (all_h["dt"] < end)
    d = all_h.loc[mask].copy()
    d["hour"] = d["dt"].dt.hour + d["dt"].dt.minute / 60.0
    prof = d.groupby(["site", "hour"], as_index=False)["temp_f"].mean()
    end_label = (pd.Timestamp(end) - pd.Timedelta(days=1)).strftime("%b %-d")
    start_label = pd.Timestamp(start).strftime("%b %-d, %Y")
    return prof, start_label, end_label


# ── HOBO: daily mean time series ──────────────────────────────────────────────
def hobo_time_series(all_h: pd.DataFrame) -> None:
    daily = _hobo_daily_means(all_h)
    sites = sorted(daily["site"].unique())
    y_pad = 1.0
    y_min = float(daily["temp_f"].min() - y_pad)
    y_max = float(daily["temp_f"].max() + y_pad)

    # All sites on one axis (existing)
    fig, ax = plt.subplots(figsize=(10.5, 4.5))
    for site in sites:
        sub = daily[daily["site"] == site].sort_values("date")
        ax.plot(
            sub["date"],
            sub["temp_f"],
            marker="o",
            ms=2.5,
            lw=1.5,
            label=SITE_LABELS[site],
            color=SITE_COLORS[site],
        )
    ax.set_ylabel("Mean daily air temperature (°F)")
    ax.set_xlabel("Date (CDT)")
    ax.set_title("HOBO: daily mean air temperature", fontsize=11, fontweight="bold", pad=10)
    _style_hobo_date_axis(ax)
    fig.autofmt_xdate(rotation=30, ha="right")
    ax.legend(
        ncol=1,
        loc="lower right",
        framealpha=0.9,
        edgecolor="#dddddd",
        fontsize=9,
        handlelength=1.8,
    )
    clean_ax(ax)
    fig.tight_layout()
    p = OUT / "hobo_daily_mean_temp_timeseries.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)

    # One figure per site
    for site in sites:
        fig, ax = plt.subplots(figsize=(8.0, 3.6))
        sub = daily[daily["site"] == site].sort_values("date")
        ax.plot(
            sub["date"],
            sub["temp_f"],
            marker="o",
            ms=2.8,
            lw=1.8,
            color=SITE_COLORS[site],
        )
        ax.set_ylim(y_min, y_max)
        ax.set_ylabel("Mean daily air temperature (°F)")
        ax.set_xlabel("Date (CDT)")
        ax.set_title(
            f"HOBO: daily mean air temperature — {SITE_LABELS[site]}",
            fontsize=11,
            fontweight="bold",
            pad=10,
        )
        _style_hobo_date_axis(ax)
        fig.autofmt_xdate(rotation=30, ha="right")
        clean_ax(ax)
        fig.tight_layout()
        outp = OUT / f"hobo_daily_mean_site_{site}.png"
        fig.savefig(outp, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("Wrote", outp)

    # Four-panel (2×2), shared scales
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.0), sharex=True, sharey=True)
    fig.subplots_adjust(hspace=0.28, wspace=0.12, top=0.90)
    for ax, site in zip(axes.flat, sites):
        sub = daily[daily["site"] == site].sort_values("date")
        ax.plot(
            sub["date"],
            sub["temp_f"],
            marker="o",
            ms=2.2,
            lw=1.5,
            color=SITE_COLORS[site],
        )
        ax.set_ylim(y_min, y_max)
        ax.set_title(SITE_LABELS[site], fontsize=10, fontweight="bold", color="#333333")
        _style_hobo_date_axis(ax)
        clean_ax(ax)
    for ax in axes[1, :]:
        ax.set_xlabel("Date (CDT)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Mean daily air temperature (°F)")
    fig.autofmt_xdate(rotation=30, ha="right")
    fig.suptitle("HOBO: daily mean air temperature by site", fontsize=12, fontweight="bold", y=0.98)
    p4 = OUT / "hobo_daily_mean_4panel.png"
    fig.savefig(p4, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p4)


# ── HOBO: diurnal profile ─────────────────────────────────────────────────────
def hobo_diurnal(all_h: pd.DataFrame, start: str, end: str) -> None:
    prof, start_label, end_label = _hobo_diurnal_profile(all_h, start, end)
    sites = sorted(prof["site"].unique())
    y_pad = 1.0
    y_min = float(prof["temp_f"].min() - y_pad)
    y_max = float(prof["temp_f"].max() + y_pad)
    title_suffix = f"{start_label} – {end_label}"

    # All sites on one axis (existing)
    fig, ax = plt.subplots(figsize=(8.5, 5.75))
    for site in sites:
        sub = prof[prof["site"] == site].sort_values("hour")
        ax.plot(sub["hour"], sub["temp_f"], lw=2, label=SITE_LABELS[site], color=SITE_COLORS[site])
    ax.set_xlabel("Hour of day (CDT)")
    ax.set_ylabel("Mean air temperature (°F)")
    ax.set_title(
        f"HOBO: average diurnal temperature profile  ·  {title_suffix}",
        fontsize=11,
        fontweight="bold",
        pad=12,
    )
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.legend(framealpha=0.9, edgecolor="#dddddd", fontsize=9, loc="upper left")
    clean_ax(ax)
    fig.tight_layout()
    p = OUT / "hobo_diurnal_profile_by_site.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)

    for site in sites:
        fig, ax = plt.subplots(figsize=(7.5, 3.8))
        sub = prof[prof["site"] == site].sort_values("hour")
        ax.plot(sub["hour"], sub["temp_f"], lw=2.2, color=SITE_COLORS[site])
        ax.set_ylim(y_min, y_max)
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 3))
        ax.set_xlabel("Hour of day (CDT)")
        ax.set_ylabel("Mean air temperature (°F)")
        ax.set_title(
            f"HOBO: diurnal profile — {SITE_LABELS[site]}  ·  {title_suffix}",
            fontsize=10.5,
            fontweight="bold",
            pad=10,
        )
        clean_ax(ax)
        fig.tight_layout()
        outp = OUT / f"hobo_diurnal_site_{site}.png"
        fig.savefig(outp, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("Wrote", outp)

    fig, axes = plt.subplots(2, 2, figsize=(9.0, 7.2), sharex=True, sharey=True)
    fig.subplots_adjust(hspace=0.30, wspace=0.12, top=0.90)
    for ax, site in zip(axes.flat, sites):
        sub = prof[prof["site"] == site].sort_values("hour")
        ax.plot(sub["hour"], sub["temp_f"], lw=2, color=SITE_COLORS[site])
        ax.set_ylim(y_min, y_max)
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 3))
        ax.set_title(SITE_LABELS[site], fontsize=10, fontweight="bold", color="#333333")
        clean_ax(ax)
    for ax in axes[1, :]:
        ax.set_xlabel("Hour of day (CDT)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Mean air temperature (°F)")
    fig.suptitle(
        f"HOBO: average diurnal temperature profile  ·  {title_suffix}",
        fontsize=11,
        fontweight="bold",
        y=0.98,
    )
    p4 = OUT / "hobo_diurnal_4panel.png"
    fig.savefig(p4, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p4)


# ── HOBO: exposure duration ───────────────────────────────────────────────────
def hobo_exposure_hours(
    all_h: pd.DataFrame,
    start: str,
    end: str,
    thresholds: tuple[float, ...] = (85, 90, 95),
) -> None:
    mask = (all_h["dt"] >= start) & (all_h["dt"] < end)
    d = all_h.loc[mask]
    rows = []
    interval_h = 15 / 60.0
    for site in sorted(d["site"].unique()):
        t = d.loc[d["site"] == site, "temp_f"]
        row = {"site": site, "n_intervals": len(t)}
        for th in thresholds:
            row[f"hours_ge_{th}F"] = (t >= th).sum() * interval_h
        rows.append(row)
    exp = pd.DataFrame(rows)
    exp.to_csv(OUT / "hobo_exposure_hours_by_site.csv", index=False)
    print("Wrote", OUT / "hobo_exposure_hours_by_site.csv")

    n = len(exp)
    x = np.arange(n)
    total_w = 0.72
    w = total_w / len(thresholds)
    offsets = np.linspace(-(total_w - w) / 2, (total_w - w) / 2, len(thresholds))

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for i, (th, color) in enumerate(zip(thresholds, THRESH_COLORS)):
        ax.bar(x + offsets[i], exp[f"hours_ge_{th}F"], width=w,
               color=color, label=f"≥ {th} °F")
    ax.set_xticks(x)
    ax.set_xticklabels([f"Site {s}" for s in exp["site"]])
    ax.set_ylabel("Hours (15-min intervals)")
    end_label = (pd.Timestamp(end) - pd.Timedelta(days=1)).strftime("%b %-d")
    start_label = pd.Timestamp(start).strftime("%b %-d, %Y")
    fig.suptitle(
        "Cumulative hours at or above temperature thresholds",
        fontsize=11,
        fontweight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.925,
        f"{start_label} – {end_label}",
        ha="center",
        va="top",
        fontsize=8.5,
        color="#555555",
    )
    ax.legend(framealpha=0.9, edgecolor="#dddddd", fontsize=9)
    clean_ax(ax)
    fig.tight_layout(rect=[0, 0, 1, 0.86])
    fig.savefig(OUT / "hobo_exposure_duration_bars.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", OUT / "hobo_exposure_duration_bars.png")


def hobo_calibration_reference_plot() -> None:
    """Bar chart of applied °F offsets (added to raw air temp)."""
    sites = sorted(HOBO_AIR_TEMP_OFFSET_F.keys())
    vals = [HOBO_AIR_TEMP_OFFSET_F[s] for s in sites]
    colors = [SITE_COLORS[s] for s in sites]
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    x = np.arange(len(sites))
    ax.bar(x, vals, color=colors, width=0.55, edgecolor="white", linewidth=0.6)
    ax.axhline(0, color="#888888", lw=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels([f"Site {s}" for s in sites])
    ax.set_ylabel("Offset added to HOBO air temp (°F)")
    ax.set_title(
        "HOBO inter-logger calibration offsets (applied to all analyses)",
        fontsize=11,
        fontweight="bold",
        pad=10,
    )
    clean_ax(ax)
    fig.tight_layout()
    p = OUT / "hobo_calibration_offsets_bars.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)


def hobo_calibration_before_after_plots(
    h_uncal: pd.DataFrame,
    h_cal: pd.DataFrame,
    diurnal_start: str,
    diurnal_end: str,
) -> None:
    """Daily mean and diurnal profiles: raw vs calibrated (same y-scale within figure)."""
    daily_u = _hobo_daily_means(h_uncal)
    daily_c = _hobo_daily_means(h_cal)
    sites = sorted(set(daily_u["site"].unique()) | set(daily_c["site"].unique()))
    y_pad = 1.0
    y_min = float(min(daily_u["temp_f"].min(), daily_c["temp_f"].min()) - y_pad)
    y_max = float(max(daily_u["temp_f"].max(), daily_c["temp_f"].max()) + y_pad)

    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.0), sharex=True, sharey=True)
    fig.subplots_adjust(hspace=0.28, wspace=0.12, top=0.88)
    for ax, site in zip(axes.flat, sites):
        su = daily_u[daily_u["site"] == site].sort_values("date")
        sc = daily_c[daily_c["site"] == site].sort_values("date")
        c = SITE_COLORS[site]
        ax.plot(
            su["date"],
            su["temp_f"],
            ls="--",
            lw=1.35,
            color=c,
            alpha=0.55,
            label="Before calibration",
        )
        ax.plot(sc["date"], sc["temp_f"], ls="-", lw=1.85, color=c, label="After calibration")
        ax.set_ylim(y_min, y_max)
        ax.set_title(SITE_LABELS[site], fontsize=10, fontweight="bold", color="#333333")
        _style_hobo_date_axis(ax)
        clean_ax(ax)
    for ax in axes[1, :]:
        ax.set_xlabel("Date (CDT)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Mean daily air temperature (°F)")
    fig.autofmt_xdate(rotation=30, ha="right")
    handles = [
        Line2D([0], [0], color="#555555", ls="--", lw=1.4, label="Before calibration"),
        Line2D([0], [0], color="#555555", ls="-", lw=1.8, label="After calibration"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 0.995))
    fig.suptitle(
        "HOBO daily mean air temperature: before vs after calibration",
        fontsize=12,
        fontweight="bold",
        y=1.02,
    )
    p = OUT / "hobo_daily_mean_before_after_calibration.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", p)

    prof_u, start_label, end_label = _hobo_diurnal_profile(h_uncal, diurnal_start, diurnal_end)
    prof_c, _, _ = _hobo_diurnal_profile(h_cal, diurnal_start, diurnal_end)
    title_suffix = f"{start_label} – {end_label}"
    y_pad_d = 1.0
    yd_min = float(min(prof_u["temp_f"].min(), prof_c["temp_f"].min()) - y_pad_d)
    yd_max = float(max(prof_u["temp_f"].max(), prof_c["temp_f"].max()) + y_pad_d)

    fig2, axes2 = plt.subplots(2, 2, figsize=(9.0, 7.2), sharex=True, sharey=True)
    fig2.subplots_adjust(hspace=0.30, wspace=0.12, top=0.88)
    for ax, site in zip(axes2.flat, sites):
        su = prof_u[prof_u["site"] == site].sort_values("hour")
        sc = prof_c[prof_c["site"] == site].sort_values("hour")
        c = SITE_COLORS[site]
        ax.plot(su["hour"], su["temp_f"], ls="--", lw=1.6, color=c, alpha=0.55, label="Before")
        ax.plot(sc["hour"], sc["temp_f"], ls="-", lw=2.0, color=c, label="After")
        ax.set_ylim(yd_min, yd_max)
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 3))
        ax.set_title(SITE_LABELS[site], fontsize=10, fontweight="bold", color="#333333")
        clean_ax(ax)
    for ax in axes2[1, :]:
        ax.set_xlabel("Hour of day (CDT)")
    for ax in axes2[:, 0]:
        ax.set_ylabel("Mean air temperature (°F)")
    fig2.legend(handles=handles, loc="upper center", ncol=2, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 0.995))
    fig2.suptitle(
        f"HOBO diurnal profile: before vs after calibration  ·  {title_suffix}",
        fontsize=11,
        fontweight="bold",
        y=1.02,
    )
    p2 = OUT / "hobo_diurnal_before_after_calibration.png"
    fig2.savefig(p2, dpi=150, bbox_inches="tight")
    plt.close(fig2)
    print("Wrote", p2)


# ── Main ──────────────────────────────────────────────────────────────────────
def hobo_departure_from_mean(all_h: pd.DataFrame) -> None:
    """Daily temperature departure of each site from the network daily mean."""
    daily = _hobo_daily_means(all_h)
    # Network mean per date
    net_mean = daily.groupby("date")["temp_f"].mean().rename("mean_temp")
    daily = daily.join(net_mean, on="date")
    daily["departure"] = daily["temp_f"] - daily["mean_temp"]

    sites = sorted(daily["site"].unique())
    fig, ax = plt.subplots(figsize=(10.5, 4.5))
    for site in sites:
        sub = daily[daily["site"] == site].sort_values("date")
        ax.plot(
            sub["date"], sub["departure"],
            marker="o", ms=3, lw=1.8,
            label=SITE_LABELS[site], color=SITE_COLORS[site],
        )
    ax.axhline(0, color="#666", lw=1, linestyle="--", zorder=1)
    ax.set_ylabel("Departure from network mean (°F)")
    ax.set_xlabel("Date (CDT)")
    ax.set_title(
        "HOBO: daily temperature departure from network mean",
        fontsize=13, fontweight="bold", pad=10, loc="center",
    )
    _style_hobo_date_axis(ax)
    fig.autofmt_xdate(rotation=30, ha="right")
    ax.legend(ncol=1, loc="upper right", fontsize=8.5)
    clean_ax(ax)
    fig.tight_layout()
    out = OUT / "hobo_departure_from_mean.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", out)


def kestrel_departure_from_mean(df: pd.DataFrame) -> None:
    """Per-visit air temperature departure of each site from the same-window network mean."""
    cols = ["visit_date", "period_key", "site", "air_temp_f"]
    sub = df[cols].dropna(subset=["air_temp_f"]).copy()
    # Network mean per (visit_date, period_key)
    win_mean = (
        sub.groupby(["visit_date", "period_key"])["air_temp_f"]
        .mean()
        .rename("mean_temp")
    )
    sub = sub.join(win_mean, on=["visit_date", "period_key"])
    sub["departure"] = sub["air_temp_f"] - sub["mean_temp"]
    sub["window"] = sub["visit_date"].astype(str) + " " + sub["period_key"]

    sites = sorted(sub["site"].unique())
    # Pivot for grouped bar chart
    windows = sub["window"].unique()
    windows_sorted = sorted(windows)
    x = np.arange(len(windows_sorted))
    bar_w = 0.18
    offsets = np.linspace(-(len(sites)-1)*bar_w/2, (len(sites)-1)*bar_w/2, len(sites))

    # Aggregate departure per (window, site) in case of duplicates
    site_dep_map = (
        sub.groupby(["window", "site"])["departure"].mean().unstack("site")
    )

    fig, ax = plt.subplots(figsize=(12, 5))
    for i, site in enumerate(sites):
        heights = [
            float(site_dep_map.loc[w, site]) if w in site_dep_map.index and site in site_dep_map.columns else np.nan
            for w in windows_sorted
        ]
        ax.bar(
            x + offsets[i], heights, width=bar_w * 0.9,
            color=SITE_COLORS[site], label=SITE_LABELS[site], zorder=3,
        )
    ax.axhline(0, color="#666", lw=1, linestyle="--", zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels(windows_sorted, rotation=35, ha="right", fontsize=8)
    ax.set_xlabel("Visit window", fontsize=9, color="#555555", labelpad=6)
    ax.set_ylabel("Departure from mean (°F)")
    ax.set_title(
        "Kestrel: air temperature departure from same-visit network mean",
        fontsize=13, fontweight="bold", pad=10, loc="center",
    )
    ax.legend(ncol=1, loc="upper right", fontsize=8.5)
    clean_ax(ax)
    fig.tight_layout()
    out = OUT / "kestrel_departure_from_mean.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print("Wrote", out)


def main() -> None:
    font_family = setup_fonts()
    apply_style(font_family)
    print(f"Using font family: {font_family!r}")

    k = load_kestrel()
    kestrel_table_and_boxplots(k)
    kestrel_scatter_est_vs_measured(k)
    kestrel_bars_perception(k)
    kestrel_perception_daily_timeseries(k)
    kestrel_perception_by_period_timeseries(k)
    kestrel_perception_vs_environment(k)
    kestrel_correlation_table(k)
    kestrel_perception_timeseries_by_site(k)
    kestrel_perception_jitter_strip(k)
    kestrel_category_stacked_by_site(k)
    kestrel_category_stacked_by_week(k)
    kestrel_perception_vs_rh_wind(k)

    hobo_start = "2025-08-16 00:00:00"
    hobo_end = "2025-09-19 00:00:00"
    h_uncal = load_all_hobo()
    all_h = apply_hobo_air_temp_calibration(h_uncal)
    offsets_table().to_csv(OUT / "hobo_calibration_offsets.csv", index=False)
    print("Wrote", OUT / "hobo_calibration_offsets.csv")
    kestrel_offsets_table().to_csv(OUT / "kestrel_calibration_offsets.csv", index=False)
    print("Wrote", OUT / "kestrel_calibration_offsets.csv")
    hobo_calibration_reference_plot()
    hobo_calibration_before_after_plots(h_uncal, all_h, hobo_start, hobo_end)
    kestrel_hobo_daily_context(k, all_h)
    kestrel_ordinal_models(k)

    hobo_time_series(all_h)
    hobo_diurnal(all_h, hobo_start, hobo_end)
    hobo_exposure_hours(all_h, hobo_start, hobo_end)
    hobo_departure_from_mean(all_h)
    kestrel_departure_from_mean(k)

    meta = {
        "kestrel_rows": len(k),
        "kestrel_visits": int(k["Visit #"].nunique()),
        "hobo_window": f"{hobo_start} .. exclusive {hobo_end}",
        "font_family": font_family,
        "hobo_air_temp_calibration_f": str(HOBO_AIR_TEMP_OFFSET_F),
        "kestrel_air_temp_offset_f": str(KESTREL_AIR_TEMP_OFFSET_F),
        "kestrel_wbgt_offset_f": str(KESTREL_WBGT_OFFSET_F),
        "note": "HOBO timestamps 2025; outline text references 2026 — uses logger calendar.",
    }
    pd.Series(meta).to_csv(OUT / "run_metadata.csv")
    print("Done.")


if __name__ == "__main__":
    main()
