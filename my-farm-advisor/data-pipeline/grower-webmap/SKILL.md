---
name: grower-webmap
description: >
  Grower-level interactive field map for My Farm Advisor. Use when someone asks for a
  shareable HTML map of every field a grower operates, a quick visual check of seeded
  demo farms, or a lightweight alternative to the full farm report bundle.
license: Apache-2.0
metadata:
  author: My Farm Advisor assignment-1 (therachelfoley-maker fork)
  version: "0.1.0"
  skill-author: My Farm Advisor assignment-1 (therachelfoley-maker fork)
  skill-version: "0.1.0"
---

# Grower Web Map

Use this nested skill when the request is a **grower-level interactive map** — one HTML page per grower showing every field across every farm, over a satellite basemap, with click-through metadata. It is the right tool after the data pipeline has seeded a grower, and the wrong tool for producing report PDFs, rasters, or per-field imagery.

## Start Here

- Read [README.md](README.md) for inputs, outputs, flags, and sizing guarantees.
- Read [PROVENANCE.md](PROVENANCE.md) before changing basemap providers or attribution.
- Read [INDEX.md](INDEX.md) for file-level navigation.
- Run the generator from the installed runtime source copy:
  `src/scripts/reporting/render_grower_webmap.py`.

## When to Invoke

- "Make a map of my grower's fields", "show both demo growers on a map".
- Verifying that seeded boundaries, farm names, and field metadata are coherent.
- Sharing a single portable HTML file with a collaborator.

Do not use it for:

- Replacing the farm report (`generate_farm_html.py`) — that embeds posters and is tens of MB.
- Publishing imagery or rasters — this map embeds none.
- Editing boundaries, crops, or agronomic data.

## Run It

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
cd "$DATA_PIPELINE_DATA_ROOT/data-pipeline/src"

# every grower with farms
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" \
  scripts/reporting/render_grower_webmap.py

# one grower
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" \
  scripts/reporting/render_grower_webmap.py --grower il-grower
```

Outputs, per grower:

```text
growers/<grower>/webmap/<grower>_fields_map.html
growers/<grower>/webmap/manifest.json
```

## Map Contract

- Basemap: **Esri World Imagery** via `server.arcgisonline.com`, with an
  OpenStreetMap streets alternative. Both load from the internet; the page
  itself stays portable.
- Interactions: native Leaflet zoom/pan/pinch/box-zoom, fit-to-all, a field
  list that zooms to each field and opens its popup.
- Popup metadata: grower, farm, field label, field ID, acres, county/state,
  boundary source, and the dominant USDA CDL class with its share (when a CDL
  table exists).
- Payload: simplified field polygons plus metadata only. No rasters, no
  imagery, no base64. Target output is low tens of kilobytes.

## Boundaries

- Generated HTML and manifests are runtime artifacts. Keep them under
  `$DATA_PIPELINE_DATA_ROOT`; never commit them.
- Do not change the parent `SKILL.md` or sibling workflows for this subskill.
