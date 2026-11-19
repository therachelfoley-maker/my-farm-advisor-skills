# Assignment 2 - field-level EDA example

Curated output from the `eda-field-level` subskill, published from the local
runtime so the pull request can show the figures without committing raw farm
data.

- Runtime source: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level`
- Growers: Illinois (`il-grower`), Iowa (`ia-grower`), Nebraska (`ne-grower`)
- Fields: 30 (10 per grower), 9,775 acres total
- Period: 2021-2025; growing season April 1 - September 30, GDD base 10 C
- Raw boundaries, weather tables, CDL tables and rasters stay in the runtime.
  See `provenance.json` for hashes and row counts.

## Figures

| Figure | Story |
| --- | --- |
| [Field size ranking](figures/fig_boundary_area.png) | Illinois and Iowa are bimodal - three legacy OSM fields plus large CSB blocks. Nebraska is ten near-equal parcels. |
| [Acreage concentration](figures/fig_boundary_concentration.png) | Illinois and Iowa hold about half their acres in three fields (Gini 0.32-0.33). Nebraska is nearly even (Gini 0.06). |
| [Crop rotation heatmap](figures/fig_crop_rotation_heatmap.png) | Nebraska is largely corn-on-corn; Illinois and Iowa alternate corn and soybean; one Illinois field is permanent pasture. |
| [2025 corn share](figures/fig_crop_corn_share.png) | 2025 is 10/10 corn-dominant in Nebraska, 8/10 soybean-dominant in Iowa, and split in Illinois (5 corn, 4 soybean, 1 pasture). |
| [Seasonal GDD heatmap](figures/fig_weather_gdd_heatmap.png) | Each row is a field, each column a year. Fields inside a grower move together; grower blocks separate. |
| [Seasonal precipitation](figures/fig_weather_precip_distribution.png) | Iowa spreads widest (405-801 mm), Nebraska is tightest and lowest (340-585 mm), Illinois is mid (417-632 mm). |
| [Crop and provenance map](maps/map_crop_2025_source.png) | 2025 crop pattern with legacy OSM boundaries dashed. Nebraska has no dashed polygons, which is the provenance caveat. |

## Headline results

**Boundaries.** Pooled Kruskal-Wallis across all 30 fields is not significant
(p = 0.107) because the legacy OSM fields mask the gap. Restricting to CSB
fields makes it significant (p = 0.0002): Illinois and Iowa CSB blocks are
larger than Nebraska parcels (median 424 and 401 ac vs 244 ac). Gini
differences separate Nebraska from both Illinois (permutation p = 0.010) and
Iowa (p = 0.0028).

**Cropland.** Continuous-corn frequency separates growers cleanly
(Kruskal-Wallis p = 1.8e-5; Nebraska vs Illinois Holm-adjusted p = 0.00017,
Nebraska vs Iowa 0.0025). Nebraska averages 55% continuous corn, Illinois 0%,
Iowa 10% (one field). Five-year crop diversity does not differ (p = 0.757);
nearly every field carries two crops.

**Weather.** Seasonal GDD separates growers (p = 0.0007; Illinois and Iowa each
differ from Nebraska at Holm-adjusted p = 0.008). Seasonal precipitation does
not (p = 0.234). The variance decomposition makes the reason explicit: 82% of
GDD variance is between growers, but only 23% of precipitation variance is.
Illinois and Iowa each collapse to two NASA POWER temperature series and
Nebraska to one, so field-to-field weather differences inside a grower are
mostly grid-cell artifacts.

## Tables

| Table | Contents |
| --- | --- |
| [`boundary_metrics.csv`](tables/boundary_metrics.csv) | 30 fields: area, perimeter, compactness, source, share of grower acres |
| [`crop_composition.csv`](tables/crop_composition.csv) | long CDL composition by field-year |
| [`crop_field_summary.csv`](tables/crop_field_summary.csv) | one row per field: rotation sequence, corn share, continuous corn, diversity |
| [`weather_seasonal.csv`](tables/weather_seasonal.csv) | 150 field-years: GDD, precipitation, heat days |
| [`weather_cell_year.csv`](tables/weather_cell_year.csv) | 25 grid-cell-years: the unit used in the weather tests |
| [`stats_results.csv`](tables/stats_results.csv) | every test with raw and Holm-adjusted p-values and effect sizes |
| [`stats_results.json`](tables/stats_results.json) | same results in JSON |

## Regenerate

```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
cd my-farm-advisor/eda/eda-field-level/scripts
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" run_all.py
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" publish_examples.py
```

## Caveats

- Ten fields per grower: every test is exploratory. Read effect sizes and
  adjusted p-values, not significance alone.
- CDL is a 30 m modeled label, not ground truth; five years supports
  descriptive rotation only.
- Weather is NASA POWER grid-cell weather. Do not read field-level weather
  differences inside a grower as microclimate.
- Illinois and Iowa mix USDA CSB parcels with legacy OpenStreetMap polygons;
  Nebraska is all CSB. Boundary comparisons report source and include a
  CSB-only sensitivity run.
- No soil analysis is part of this workflow.
- This directory is an artifact example, not the report. Report prose is
  assembled separately.
