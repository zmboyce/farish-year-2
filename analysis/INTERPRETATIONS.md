# Farish Year 2 — interpretations (Kestrel + HOBO)

This document accompanies the generated tables and figures in `analysis/outputs/`. Scoring for categorical items matches `Data/outline_year_2.docx` (Year 1 scale): air-temperature feeling 1 (slightly cool)–6 (very hot); thermal comfort 1 (comfortable)–4 (very uncomfortable). The response **Cool** does not appear in that table; it was scored as **1**, same as slightly cool, so averages stay comparable.

**Data location note:** The report outline lives at `Data/outline_year_2.docx` (not the project root). HOBO logger timestamps in the Excel files are **2025**; the outline text mentions **2026** for the diurnal window. All HOBO analyses use **16 August through 18 September** in the **logger year** (2025), which is a **34-day** span with **96** fifteen-minute samples per day per site (no gaps larger than 20 minutes in the full series).

---

## Table: Average Kestrel measurements by site (`kestrel_avg_by_site.csv`)

**What it shows.** For each of the four sites, the mean of air temperature, WBGT, relative humidity, and wind speed across all crew visits in the cleaned sheet (92 site-visits = 23 visit rounds × 4 sites). The last row is the mean of those site means.

**Interpretation.** Air temperatures are similar across sites (about 88–89 °F on average), while **WBGT** shows a slightly wider spread (Site 2 highest mean WBGT, Site 3 and 4 somewhat lower). That pattern is consistent with WBGT integrating humidity, wind, and radiant load: micro-scale differences in shade, surface type, and breeze show up more in WBGT than in dry-bulb air temperature alone. **Relative humidity** is highest on average at Site 3 and lowest at Site 2. **Wind speed** is low at all sites (typical of courtyard-scale measurements); Site 4 has the highest mean wind, which can modestly reduce heat stress for the same air temperature and humidity.

---

## Figure: Box-and-whisker plots — Kestrel by site (`kestrel_boxplots_2x2.png`)

**What it shows.** Distributions (median, quartiles, whiskers, mean marker) for the four continuous Kestrel variables, one panel each, grouped by site.

**Interpretation.** Boxplots complement the table: they show **visit-to-visit variability** and whether one or two hot afternoons drive the means. If WBGT boxes are **wider** or **shifted** relative to air temperature, it supports the idea that radiation and moisture differences across sites matter for perceived heat stress, not only the thermometer reading. Outliers (if any) flag unusual microclimate or measurement conditions worth checking in field notes.

---

## Figure: Estimated vs. Kestrel air temperature (`kestrel_estimated_vs_measured.png`)

**What it shows.** Each point is one site-visit: x = crew estimate before reading the Kestrel, y = Kestrel air temperature. The dashed line is y = x (perfect agreement).

**Interpretation.** For this dataset (n = 92), **Pearson r ≈ 0.75**, **RMSE ≈ 5 °F**, and **mean bias (Kestrel − estimate) ≈ 0 °F**, so estimates track measured conditions reasonably well on average, with typical errors on the order of a few degrees. Points **above** the line mean the instrument read **hotter** than the crew guessed (underestimated heat); points **below** mean the crew guessed **warmer** than measured. Clustering around the line supports using subjective estimates as a coarse check on data entry; systematic offset would suggest training or anchoring effects.

---

## Figure: Perception bar charts (`kestrel_perception_bars_by_site.png`)

**What it shows.** Left: mean **air-temperature feeling** score by site (error bars = standard error of the mean). Right: mean **thermal comfort** score by site.

**Interpretation.** **Site 1** shows the **highest** mean “how hot it feels” score (~4.2 on the 1–6 scale) and among the **least comfortable** mean comfort scores (~2.2 on 1–4, where higher is worse). **Site 2** has the **lowest** mean feeling score (~3.6) and the **lowest** mean discomfort (~2.0). Sites 3 and 4 fall between. These patterns **do not have to mirror** average air temperature exactly: sun exposure, humidity, wind, clothing, and activity all influence perception. Comparing these bars to WBGT and to land-cover context (outline narrative) helps explain **why** a site can feel worse even when air temperature is similar.

---

## Figure: HOBO daily mean temperature (`hobo_daily_mean_temp_timeseries.png`)

**What it shows.** One line per site: **daily mean** air temperature (°F) for every calendar day in the logger deployment (including days outside the strict 34-day analysis window if present).

**Interpretation.** This view emphasizes **synoptic** change: frontal passages, rain, or sustained hot spells show as multi-day ramps or plateaus common to all sites. **Divergence between lines** on the same day indicates **local** differences (shading, pavement, fetch) superimposed on the broader weather. For reporting, call out the hottest week and whether ranking of sites (which is warmest) is stable or flips with weather.

---

## Figure: HOBO average diurnal profile (`hobo_diurnal_profile_by_site.png`)

**What it shows.** For **16 Aug–18 Sep 2025 (CDT)**, mean temperature at each fifteen-minute “time of day,” averaged across all days in that window, by site.

**Interpretation.** Profiles typically peak in **mid-to-late afternoon** and bottom out near **sunrise**, shaped by solar angle, boundary-layer mixing, and local thermal mass. **Spacing between site curves** shows how land cover alters the **daily cycle** (e.g., more shade damping afternoon peak). If one site’s curve is **flatter**, it may have more mixing or less direct sun; a **sharper** peak can indicate strong radiative loading. Use the outline’s site descriptions when narrating.

---

## Extra outputs: exposure duration (`hobo_exposure_hours_by_site.csv`, `hobo_exposure_duration_bars.png`)

**What they show.** Within the same 34-day window, total **hours** with temperature ≥ 85, 90, and 95 °F (each 15-minute row counts as 0.25 h).

**Interpretation.** This answers “how much **time** did conditions exceed uncomfortable thresholds?” rather than “what was the single hottest reading?” In the current run, **Site 2** accumulates the most hours ≥ 90 °F and **Site 4** the fewest among the four loggers—useful for comparing cumulative heat exposure where short peaks matter less than persistent warmth. Thresholds can be adjusted in `run_farish_analysis.py` if the report prefers different cutoffs (e.g., 88 °F).

---

## Methods recap (for reproducibility)

- **Kestrel:** `Data/Kestrel/Kestrel Data_Farish St_Year 2.xlsx`, sheet `final`.
- **HOBO:** `Data/HOBO/*.xlsx`; temperature converted from °C to °F for plots.
- **Regenerate:** `python3 analysis/run_farish_analysis.py`

If you want **raw 15-minute HOBO lines** (instead of daily means) for the time-series figure, or **stacked bar charts of response counts** for Survey categories, say so and we can add them without changing the underlying cleaning logic.
