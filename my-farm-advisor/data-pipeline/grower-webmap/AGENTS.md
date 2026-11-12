# Local Instructions

## Purpose

This folder owns the grower-level interactive web-map subskill for the My Farm Advisor data
pipeline. It documents and routes to a single generator script that turns pipeline boundary
outputs into one lightweight HTML map per grower.

## Safe edit scope

Edits stay in this folder and in `../src/scripts/reporting/render_grower_webmap.py` unless the
user explicitly asks for a broader pipeline change. Do not alter parent `SKILL.md`, sibling
workflows, or root policy from a subskill task.

## Read nearby docs first

Read `README.md` first, then `PROVENANCE.md` before touching basemaps or attribution. For
pipeline runtime rules, read `../AGENTS.md`. For the general Leaflet workflow, read
`../../admin/interactive-web-map/GUIDE.md` (reference only; do not copy code).

## Runtime contract

- `DATA_PIPELINE_DATA_ROOT` is required. Run the generator from the runtime source copy at
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`, using that runtime's `.venv`.
- Read grower data from `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/`.
- Write HTML and manifests to `growers/<grower>/webmap/` under the same data root.
- Never write generated artifacts inside the skill checkout.

## Local validation

Run from the repository root after structural changes:

```bash
./scripts/validate.sh
```

For a functional check, render both seeded growers and confirm each HTML file contains the
expected field count and no embedded raster payloads:

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
cd "$DATA_PIPELINE_DATA_ROOT/data-pipeline/src"
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" \
  scripts/reporting/render_grower_webmap.py
```

## Local-delta-only reminder

This nested AGENTS.md records only instructions that differ from the parent or root files. Do
not duplicate root-wide asset, vendor, or validation policy here.
