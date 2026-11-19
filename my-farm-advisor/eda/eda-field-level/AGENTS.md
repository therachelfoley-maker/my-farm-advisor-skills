# Local Instructions

## Purpose

This folder owns the field-level, cross-grower EDA workflow: boundary
comparison, CDL/cropland comparison, weather comparison, and the provenance
map. It writes static PNG/CSV/JSON artifacts only.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly
asks for a broader skill change. Do not change parent `SKILL.md`, sibling EDA
workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first. If routing context is needed, read `../INDEX.md` and
`../../SKILL.md`. Reuse the statistical vocabulary in `../eda-compare/GUIDE.md`
and `../eda-correlate/GUIDE.md` rather than inventing a new one.

## Output rules

- Analysis output goes to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level`.
- Never write raw boundaries, weather tables, CDL tables or rasters into this
  repository.
- `publish_examples.py` is the only path from runtime to
  `examples/assignment-2/`; it enforces the size budget and writes provenance.
- Do not add report generation here. Report prose is a separate one-time
  artifact.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes.
Then run the smallest real check available:

```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
cd my-farm-advisor/eda/eda-field-level/scripts
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" run_all.py
```

Confirm the summary reports 30 fields, 150 field-years, 25 cell-years, six
figures and one map. Inspect the PNGs for blank panels, clipped legends and
colliding labels before publishing.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or
root files. Do not duplicate root-wide asset, vendor, or validation policy here
except this pointer to `../../../AGENTS.md`.
