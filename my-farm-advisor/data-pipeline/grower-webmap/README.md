# Grower Web Map

A lightweight, grower-level interactive field map generator for the My Farm Advisor data
pipeline. It reads the field boundaries the pipeline already produced and writes one
self-contained HTML page per grower, with all of that grower's fields drawn over a
satellite basemap.

This is deliberately **not** the farm report. `generate_farm_html.py` embeds posters and
cards and lands around 50–70 MB per farm. This map embeds polygons and a few attributes and
lands in the low tens of kilobytes, because the basemap is fetched from the internet at view
time instead of being baked in.

## What it shows

For every grower found under `growers/`, the generator walks every farm and draws each field
polygon from the canonical `boundary/field_boundaries.geojson`:

- All fields for the grower, color-coded per farm.
- **Every field carries a white casing** under its farm-coloured outline, so an edge never
  depends on the basemap tone: the casing reads over dark canopy, the farm stroke over pale
  soil. Farm hues lead with magenta, blue, and purple, which sit 74–103 ΔE from green
  vegetation; the old palette led with `#1B5E20`, only 20–31 ΔE from the crop.
- **Selected field in amber.** Farm colour only separates farms; selection gets its own
  accent — a white casing under a 3.5 px `#FFB300` outline and a light `#FFC400` wash — so it
  stays visible over green crops, tan residue, and pale bare soil alike. Hover is a softer
  cue in the field's own colour, so hover and selection no longer look alike. The sidebar
  mirrors the same amber accent and the footer shows a legend swatch.
- Zoom and pan: wheel, double-click, pinch, `+ / −`, and box-zoom (`Shift` + drag).
- A "Fit all fields" reset, plus a sidebar field list that zooms to a single field and opens
  its popup.
- Popups with grower, farm, field label, field ID, acres, county/state, boundary source, and
  the dominant USDA CDL class share for the newest available CDL year.
- Basemap switcher: **Esri World Imagery** (default) and OpenStreetMap streets, with the
  required Esri/Maxar attribution.
- A banner that appears if tiles cannot load, so an offline open does not look broken.

Geography comes from the boundary features (`state_fips`, `county_name`). `farm.json` is used
for the display name only; the map does not trust its `state` value, so it cannot drift from
the geometry even if metadata is hand-edited.

## Inputs

| Input | Path (relative to runtime) | Use |
| --- | --- | --- |
| Field boundaries | `growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson` | Polygons + `field_id`, acres, county, state, source |
| Grower metadata | `growers/<grower>/grower.json` | Display name |
| Farm metadata | `growers/<grower>/farms/<farm>/farm.json` | Display name |
| Field metadata | `growers/<grower>/farms/<farm>/fields/<field>/field.json` | Optional display name |
| Crop history | `growers/<grower>/farms/<farm>/derived/tables/*_<year>_cdl.csv` | Dominant CDL class per field |

The crop line is a **CDL class share**, not a planting record. It is omitted when no CDL
table exists. Use `--cdl-year` to pin a year; the default is the newest table per farm.

## Outputs

```text
growers/<grower>/webmap/<grower>_fields_map.html
growers/<grower>/webmap/manifest.json
```

The manifest records grower/farm/field counts, total acres, output path and byte size,
basemap provider, and a generation timestamp. The HTML itself carries no timestamp, so
regenerating from unchanged inputs produces byte-identical output.

Both files are runtime artifacts and stay outside Git.

## Usage

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
cd "$DATA_PIPELINE_DATA_ROOT/data-pipeline/src"

# Every grower with a farms/ directory
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" \
  scripts/reporting/render_grower_webmap.py

# Selected growers
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" \
  scripts/reporting/render_grower_webmap.py --grower il-grower --grower ia-grower

# Pin the CDL year
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" \
  scripts/reporting/render_grower_webmap.py --grower il-grower --cdl-year 2024
```

Exit codes: `0` all requested growers rendered, `1` at least one grower failed (reported on
stderr), `2` no growers with farms were found.

## Guarantees

- No new Python dependency: `geopandas` + the standard library only.
- No raster, imagery, or base64 payloads in the HTML; the generator asserts this.
- Output size guard: the generator fails if a page exceeds 1 MB.
- Deterministic data ordering and a timestamp-free document body.

## Notes and limits

- Tile requests need internet access. The field outlines and metadata still render offline.
- This map is for internal review and demo use. Esri World Imagery has its own terms of use;
  do not republish tile imagery at scale without checking them.
- The map is grower-level by design. Per-field agronomic figures stay with the existing
  field poster and NDVI card generators.
