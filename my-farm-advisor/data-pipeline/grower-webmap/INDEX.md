# Grower Web Map Index

Use this package for grower-level interactive HTML field maps. Start with the file that
matches the task.

## Routing and Human Docs

- [SKILL.md](SKILL.md) — compact routing entrypoint for agents.
- [README.md](README.md) — inputs, outputs, flags, guarantees, limits.
- [PROVENANCE.md](PROVENANCE.md) — origin of the subskill, basemap terms, attribution.
- [AGENTS.md](AGENTS.md) — local edit and validation rules.

## Implementation

The generator ships inside the data-pipeline source tree so the installer copies it with the
rest of the pipeline:

- `../src/scripts/reporting/render_grower_webmap.py` — CLI and HTML builder.
  - `_collect_grower()` reads boundary GeoJSON, grower/farm/field JSON, and CDL tables.
  - `_build_html()` emits the single-file Leaflet document.
  - `_write_grower()` writes the HTML plus `manifest.json` and enforces the size/raster
    guards.

## Runtime Outputs

Per grower, under the data root (never in this checkout):

- `growers/<grower>/webmap/<grower>_fields_map.html`
- `growers/<grower>/webmap/manifest.json`

## Related Workflows

- `../../admin/interactive-web-map/GUIDE.md` — the general Leaflet workflow this subskill
  follows in spirit; no code is shared or copied.
- `../../src/scripts/reporting/generate_farm_html.py` — the heavyweight farm report, which
  embeds posters and soil cards.
- `../references/field-map-frame.md` — static figure frame rules; not applicable to the
  interactive map, which uses Web Mercator tiles.

## Output Boundary

Do not commit generated HTML, manifests, or screenshots. This package documents the
subskill; the artifacts belong under `$DATA_PIPELINE_DATA_ROOT`.
