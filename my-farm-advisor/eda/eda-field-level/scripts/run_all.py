"""Run the full ``eda-field-level`` build.

Usage (from this directory, with the runtime venv active):

    DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime \
        python run_all.py

Outputs land under ``<runtime>/data-pipeline/eda/field-level``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import boundaries
import cropland
import maps
import weather
from common import (
    GDD_BASE_C,
    HEAT_THRESHOLD_C,
    STAT_COLUMNS,
    ensure_output_dirs,
    file_record,
    output_root,
    package_versions,
    resolve_growers,
    runtime_root,
    use_agg_backend,
    utc_now,
    write_json,
    write_table,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Field-level EDA across growers")
    parser.add_argument("--growers", default=None, help="comma-separated grower slugs (default: all)")
    parser.add_argument("--out", default=None, help="override output root")
    parser.add_argument("--skip-maps", action="store_true", help="skip the map render")
    return parser.parse_args()


def _count_rows(path: Path) -> int:
    if path.suffix == ".csv":
        with path.open("rb") as handle:
            return max(sum(1 for _ in handle) - 1, 0)
    if path.suffix == ".geojson":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return len(payload.get("features", []))
    return None


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def main() -> int:
    args = parse_args()
    growers = resolve_growers(args.growers)
    dirs = ensure_output_dirs(Path(args.out).expanduser().resolve() if args.out else None)
    use_agg_backend()

    print("=" * 68)
    print("Field-level EDA")
    print("=" * 68)
    print(f"Runtime root : {runtime_root()}")
    print(f"Output root  : {dirs['root']}")
    print(f"Growers      : {', '.join(grower.label for grower in growers)}")
    print(f"Season       : Apr 1 - Sep 30, GDD base {GDD_BASE_C:.0f} C")
    print()

    boundary_metrics, boundary_stats = boundaries.build(growers, dirs)
    crop_summary, crop_stats = cropland.build(growers, dirs)
    seasonal, cells, weather_stats = weather.build(growers, dirs)

    map_path = None
    if not args.skip_maps:
        map_path = maps.build(growers, dirs)

    stats = pd.DataFrame(boundary_stats + crop_stats + weather_stats)
    for column in STAT_COLUMNS:
        if column not in stats.columns:
            stats[column] = np.nan
    stats = stats[STAT_COLUMNS]
    stats_path = write_table(stats, dirs["tables"] / "stats_results.csv")

    payload = {
        "generated_at": utc_now(),
        "rows": json.loads(stats.to_json(orient="records")),
    }
    write_json(payload, dirs["tables"] / "stats_results.json")

    inputs: list[dict] = []
    for grower in growers:
        farm = Path(runtime_root()) / "data-pipeline" / "growers" / grower.slug / "farms" / grower.farm
        paths = [
            farm / "boundary" / "field_boundaries.geojson",
            farm / "derived" / "tables" / f"{grower.prefix}_weather_2021_2025.csv",
            farm / "derived" / "tables" / f"{grower.prefix}_cdl_2021_2025_full_composition.csv",
            farm / "derived" / "tables" / f"{grower.prefix}_crop_rotation.csv",
        ]
        for year in range(2021, 2026):
            paths.append(farm / "derived" / "tables" / f"{grower.prefix}_{year}_cdl.csv")
        for path in paths:
            if path.exists():
                record = file_record(path, rows=_count_rows(path))
                record["grower"] = grower.label
                inputs.append(record)

    outputs: list[dict] = []
    for subdir in ("tables", "figures", "maps"):
        for path in sorted(dirs[subdir].glob("*")):
            if path.is_file() and path.name != "manifest.json":
                record = file_record(path, rows=_count_rows(path))
                record["kind"] = subdir
                outputs.append(record)

    manifest = {
        "skill": "eda-field-level",
        "generated_at": utc_now(),
        "runtime_root": str(runtime_root()),
        "output_root": str(dirs["root"]),
        "parameters": {
            "season_start": "04-01",
            "season_end": "09-30",
            "gdd_base_c": GDD_BASE_C,
            "heat_threshold_c": HEAT_THRESHOLD_C,
            "statistical_unit_boundaries": "field",
            "statistical_unit_weather": "grid-cell-year",
            "multiple_testing": "Holm step-down",
        },
        "growers": [
            {
                "slug": grower.slug,
                "farm": grower.farm,
                "label": grower.label,
                "state": grower.state,
                "fields": int((boundary_metrics["grower"] == grower.label).sum()),
                "acres": float(boundary_metrics.loc[boundary_metrics["grower"] == grower.label, "area_acres"].sum()),
            }
            for grower in growers
        ],
        "counts": {
            "fields": int(len(boundary_metrics)),
            "field_years_weather": int(len(seasonal)),
            "cell_years_weather": int(len(cells)),
            "crop_field_rows": int(len(crop_summary)),
            "figures": int(len(list(dirs["figures"].glob("*.png")))),
            "maps": int(len(list(dirs["maps"].glob("*.png")))),
            "stat_rows": int(len(stats)),
        },
        "inputs": inputs,
        "outputs": outputs,
        "packages": package_versions(),
    }
    write_json(manifest, dirs["root"] / "manifest.json")

    print()
    print("Summary")
    print(f"  fields              {len(boundary_metrics)}")
    print(f"  weather field-years {len(seasonal)}")
    print(f"  weather cell-years  {len(cells)}")
    print(f"  stats rows          {len(stats)}")
    print(f"  figures             {len(list(dirs['figures'].glob('*.png')))}")
    print(f"  maps                {len(list(dirs['maps'].glob('*.png')))}")
    print(f"  stats table         {stats_path}")
    print(f"  manifest            {dirs['root'] / 'manifest.json'}")
    if map_path:
        print(f"  map                 {map_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
