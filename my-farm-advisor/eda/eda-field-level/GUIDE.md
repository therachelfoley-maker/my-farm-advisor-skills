---
name: eda-field-level
description: Compare field boundaries, CDL/cropland and weather across growers with two static figures per category, one statistical analysis per category, and one provenance map.
version: 1.0.0
author: Boreal Bytes
tags: [eda, fields, boundaries, cdl, weather, comparison, statistics]
---

# Workflow: eda-field-level

## Description

Field-level exploratory analysis across multiple growers. The workflow reads the
canonical runtime tree, builds two static figures and one statistical analysis
for each of three categories, and renders one map:

| Category | Visualizations | Analysis |
| --- | --- | --- |
| Boundaries | sorted field-size rank chart, Lorenz curve | Kruskal-Wallis, Holm-corrected Mann-Whitney, Gini bootstrap and permutation tests |
| CDL / cropland | field x year rotation heatmap, 2025 corn-share distribution | Kruskal-Wallis and Holm-corrected Mann-Whitney on corn share, continuous corn, diversity |
| Weather | field x year GDD heatmap, seasonal precipitation distribution | cell-year Kruskal-Wallis and Mann-Whitney, within/between-grower variance |
| Map | 2025 dominant crop with boundary provenance | - |

Everything is static: PNG figures, CSV tables, JSON manifest. There is no
dashboard and no report generator. Report prose is assembled separately as a
one-time artifact.

## When to Use This Workflow

- You have two or more growers with field boundaries, weather and cropland
  layers in the canonical runtime tree.
- You need to compare fields within a grower and growers against each other.
- You want a small, reviewable set of figures and tests rather than a dashboard.
- You need to show where boundaries came from (parcel data vs legacy OSM) next
  to the agronomic pattern.

## Comparison Axes

| Axis | Where it appears |
| --- | --- |
| Within a field over time | crop rotation heatmap (5 years), GDD heatmap (5 years) |
| Across fields within a grower | every figure keeps the field as the unit; growers are panels or groups |
| Across growers | distributions, tests, variance decomposition, map panels |

## Growing Season Definition

The analysis window is **April 1 - September 30**, with GDD accumulated from a
**10 C base** using `(T2M_MAX + T2M_MIN) / 2`. This is an agronomic season for
corn and soybean, not a frost-free definition. It sits inside the frost-free
period in the Assignment 2 record and excludes post-maturity October.

Reference values from the Assignment 2 runtime (2021-2025):

| | Illinois | Iowa | Nebraska |
| --- | --- | --- | --- |
| Frost-free days | 174-210 | 164-187 | 181-213 |
| Apr-Sep GDD, base 10 C | 1,782-1,916 | 1,557-1,886 | 1,974-2,196 |
| Apr-Sep precipitation | 417-632 mm | 405-801 mm | 340-585 mm |

Nebraska and Illinois have similar frost-free length; Nebraska's advantage is
summer heat. Northern Iowa is both coolest and shortest.

## Inputs

Paths resolve from `DATA_PIPELINE_DATA_ROOT` (default
`~/my-farm-advisor-runtime`):

```
<runtime>/data-pipeline/growers/<grower>/farms/<farm>/
├── boundary/field_boundaries.geojson
└── derived/tables/
    ├── <prefix>_weather_2021_2025.csv
    ├── <prefix>_<year>_cdl.csv                    # 2021-2025
    ├── <prefix>_cdl_2021_2025_full_composition.csv
    └── <prefix>_crop_rotation.csv
```

The default registry is Illinois `il-grower/illinois-farm`, Iowa
`ia-grower/iowa-farm`, and Nebraska `ne-grower/nebraska-farm`. Override it in
`scripts/common.py` or filter a run with `--growers`.

## Outputs

```
<runtime>/data-pipeline/eda/field-level/
├── tables/
│   ├── boundary_metrics.csv
│   ├── crop_composition.csv
│   ├── crop_field_summary.csv
│   ├── weather_seasonal.csv
│   ├── weather_cell_year.csv
│   ├── stats_results.csv
│   └── stats_results.json
├── figures/
│   ├── fig_boundary_area.png
│   ├── fig_boundary_concentration.png
│   ├── fig_crop_rotation_heatmap.png
│   ├── fig_crop_corn_share.png
│   ├── fig_weather_gdd_heatmap.png
│   └── fig_weather_precip_distribution.png
├── maps/
│   └── map_crop_2025_source.png
└── manifest.json
```

`manifest.json` records input paths, row counts, SHA-256 hashes, output hashes,
analysis parameters and package versions.

## What Each Artifact Tells You

### Boundaries

- **`fig_boundary_area.png`** - fields ranked by size within each grower on a
  linear acre axis, colored by boundary source. Illinois and Iowa are bimodal:
  three legacy OSM fields plus large CSB blocks. Nebraska is ten near-equal
  parcels. Field size is not comparable across growers without naming the
  source.
- **`fig_boundary_concentration.png`** - Lorenz curve of acreage. Illinois and
  Iowa hold about half their acres in three fields (Gini about 0.32); Nebraska
  is close to even (Gini about 0.06). This is an equipment-sizing and
  harvest-logistics story.
- **Analysis** - Kruskal-Wallis on area, Holm-corrected Mann-Whitney pairs,
  bootstrap Gini intervals, permutation tests on Gini differences, and a
  CSB-only sensitivity run. If the area gap survives dropping legacy fields, it
  is structural; if it collapses, it was a source artifact.

### CDL / cropland

- **`fig_crop_rotation_heatmap.png`** - dominant CDL class per field-year.
  Nebraska is largely corn-on-corn; Illinois and Iowa alternate corn and
  soybean; the Illinois pasture field never rotates.
- **`fig_crop_corn_share.png`** - 2025 corn share per field. Nebraska is
  corn-dominant, Iowa is soybean-heavy, Illinois is split and bimodal.
- **Analysis** - Kruskal-Wallis and Holm-corrected Mann-Whitney on 2025 corn
  share, continuous-corn frequency and 5-year crop diversity. Continuous corn
  is the sharpest separation: Nebraska about 55% mean, Illinois 0%, Iowa about
  10% (one field).

### Weather

- **`fig_weather_gdd_heatmap.png`** - seasonal GDD per field-year. Each row is
  a field, each column a year, so one field can be followed across the record.
  Fields inside a grower are near-identical because they share NASA POWER grid
  cells; grower blocks separate.
- **`fig_weather_precip_distribution.png`** - Apr-Sep precipitation per
  field-year. Iowa spreads widest, Nebraska is tightest and lowest.
- **Analysis** - tests use **grid-cell-year** observations, not field-year,
  because fields within a grower are pseudo-replicates. A variance
  decomposition reports the within/between-grower ICC. GDD separates growers;
  precipitation does not.

### Map

- **`map_crop_2025_source.png`** - 2025 dominant crop as fill, legacy OSM
  boundaries as a dashed outline, field IDs labelled for legacy polygons.
  Nebraska has no dashed polygons, which is itself the provenance message: part
  of the cross-grower boundary difference is a data-lineage difference.

## How to Run

Use the runtime virtual environment so geopandas, scipy and matplotlib match
the pipeline:

```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
cd my-farm-advisor/eda/eda-field-level/scripts
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" run_all.py
```

Options:

```bash
python run_all.py --growers il-grower,ne-grower   # subset
python run_all.py --out /tmp/eda-check            # alternate output root
python run_all.py --skip-maps                     # tables and figures only
```

## Publishing an Example

Analysis output stays in the runtime. To put a curated, size-budgeted example
in the repository for review or a pull request:

```bash
python publish_examples.py
```

It copies only the six figures, the map, five small derived tables and the
stats JSON into `examples/assignment-2/`, enforces per-file and total size
budgets, and writes `provenance.json` with source paths, hashes and the skill
commit. Raw boundaries, weather tables, CDL tables and rasters are never
copied.

## Interpretation Rules

- **Weather is grid-cell weather.** In the Assignment 2 data Illinois and Iowa
  each collapse to two temperature series and Nebraska to one. Field-to-field
  weather differences inside a grower are largely cell artifacts. Use the
  grower axis.
- **CDL is modeled, not ground truth.** 30 m labels; five years is enough for
  descriptive rotation, not for a management verdict.
- **Ten fields per grower is exploratory.** Report effect sizes and adjusted
  p-values with the sample size; do not treat any single test as confirmatory.
- **Boundary sources differ.** Illinois and Iowa mix CSB parcels with legacy
  OSM polygons; Nebraska is all CSB. Always show or state the source when
  comparing area or shape.
- **No soil analysis.** This workflow does not read SSURGO, gNATSGO or
  SoilGrids.

## Requirements

- Python 3.9+ with pandas, numpy, scipy, matplotlib, seaborn, geopandas and
  shapely. The runtime venv already provides them.
- No statsmodels dependency; tests are rank-based and permutation-based.

## Extending

Add a grower by appending a `Grower` entry to `DEFAULT_GROWERS` in
`scripts/common.py`. The grower needs the canonical boundary, weather,
composition and rotation outputs listed under Inputs.
