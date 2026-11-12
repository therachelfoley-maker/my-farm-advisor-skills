# Grower Web Map Provenance

This file records where the grower web-map subskill came from and which third-party
components its output depends on.

## Origin

- Added on branch `assignment-1` of the `therachelfoley-maker/my-farm-advisor-skills`
  fork as part of Assignment 1.
- Scope: a grower-level companion to the existing data-pipeline reporting scripts. It reads
  pipeline outputs only; it does not download data, train models, or alter boundaries.
- Code is original to this repository. The general approach follows the repository's
  existing `my-farm-advisor/admin/interactive-web-map/` workflow (Leaflet, CDN-hosted
  libraries, internet basemap, embedded GeoJSON). No code was copied or vendored from that
  workflow, from `folium`, or from any external project.

## Why a Separate Subskill

The farm report (`generate_farm_html.py`) is a self-contained bundle with embedded posters,
soil cards, and charts; it is appropriate for archival but heavy (tens of MB). The data
pipeline had no lightweight, grower-scoped artifact. This subskill fills that gap without
changing the pipeline's 16-step run or its outputs.

## Third-Party Components

### Leaflet 1.9.4

- Role: map rendering, zoom/pan controls, popups, layer switcher.
- Delivery: loaded in the browser from `https://unpkg.com/leaflet@1.9.4/`.
- License: BSD-2-Clause.
- Note: the HTML output depends on the CDN at view time. Offline, the page still renders
  field outlines but not tiles or map controls.

### Esri World Imagery

- Role: default satellite basemap.
- Endpoint used in the page:
  `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`
- Required attribution embedded in the page:
  "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community".
- Terms: subject to Esri's terms of use for ArcGIS Online basemaps. Output is intended for
  internal review and demo use; do not redistribute tile imagery at scale without checking
  those terms.
- No tiles are downloaded or cached by the generator. Only the tile URL template is written
  into the HTML.

### OpenStreetMap Standard Tiles

- Role: optional streets basemap.
- Endpoint: `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png`.
- Attribution: "© OpenStreetMap contributors".
- Terms: OSM tile usage policy applies for heavy or production use. This is an optional
  toggle for orientation, not a bulk rendering path.

### Leaflet CDN

- `unpkg.com` serves the Leaflet distribution. No build step, bundler, or local copy is
  committed.

## Data Provenance

The map adds no new geospatial data. It reuses:

- FIELD BOUNDARIES: `boundary/field_boundaries.geojson` written by the pipeline's
  `download_fields.py` step, whose own provenance (OSM/Overpass or USDA CSB, plus per-farm
  manifests) remains authoritative.
- METADATA: `grower.json`, `farm.json`, `field.json` display names.
- CROP SHARES: the farm CDL tables produced by `download_cdl.py` from USDA NASS Cropland Data
  Layer rasters. The popup labels these as CDL class shares, not planting records.

## Known Data Caveats

- `farm.json` state is now derived from the farm boundary (`state_fips`) when the canonical
  metadata is written, with an explicit override and a preserve-existing fallback. The map
  still reads geography from the boundary so a hand-edited `farm.json` cannot skew it.
- OSM boundaries may carry generic `crop_name: farmland`. The popup therefore uses CDL for
  crop context and falls back to omitting the crop line.
- Field `display_name` often equals the slug; the map shows a readable `Field <id>` label and
  the exact ID alongside it rather than inventing a name.

## Validation

Run from the repository root after changing this package or its generator:

```bash
./scripts/validate.sh
```
