"""Publish a curated, size-budgeted example from the runtime EDA output.

The analysis writes everything to the runtime. This script copies only a
whitelist of small derived artifacts into the skill repository so a pull
request can show the figures and tables without committing raw farm data.

Usage:

    DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime \
        python publish_examples.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from common import output_root, sha256, utc_now

WHITELIST = [
    "figures/*.png",
    "maps/*.png",
    "tables/boundary_metrics.csv",
    "tables/crop_composition.csv",
    "tables/crop_field_summary.csv",
    "tables/weather_seasonal.csv",
    "tables/weather_cell_year.csv",
    "tables/stats_results.csv",
    "tables/stats_results.json",
]

PNG_BUDGET_BYTES = 1_500_000
CSV_BUDGET_BYTES = 200_000
TOTAL_BUDGET_BYTES = 8_000_000


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description="Publish curated EDA examples into the repository")
    parser.add_argument("--source", default=str(output_root()), help="runtime EDA output root")
    parser.add_argument(
        "--dest",
        default=str(Path(__file__).resolve().parents[1] / "examples" / "assignment-2"),
        help="destination inside the repository",
    )
    parser.add_argument("--repo-root", default=str(repo_root), help="repository root for the commit stamp")
    return parser.parse_args()


def _row_count(path: Path) -> int | None:
    if path.suffix == ".csv":
        with path.open("rb") as handle:
            return max(sum(1 for _ in handle) - 1, 0)
    return None


def _git_commit(repo_root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser().resolve()
    dest = Path(args.dest).expanduser().resolve()
    repo_root = Path(args.repo_root).expanduser().resolve()

    if not source.exists():
        raise SystemExit(f"runtime EDA output not found: {source}")

    files: list[Path] = []
    for pattern in WHITELIST:
        files.extend(sorted(source.glob(pattern)))
    files = sorted(set(files))
    if not files:
        raise SystemExit(f"no whitelisted artifacts found under {source}")

    total_bytes = 0
    published = []
    for path in files:
        relative = path.relative_to(source)
        size = path.stat().st_size
        if path.suffix == ".png" and size > PNG_BUDGET_BYTES:
            raise SystemExit(f"PNG over budget ({size:,} > {PNG_BUDGET_BYTES:,}): {relative}")
        if path.suffix == ".csv" and size > CSV_BUDGET_BYTES:
            raise SystemExit(f"CSV over budget ({size:,} > {CSV_BUDGET_BYTES:,}): {relative}")
        total_bytes += size

        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        published.append(
            {
                "path": str(relative),
                "bytes": size,
                "sha256": sha256(target),
                "rows": _row_count(target),
            }
        )

    if total_bytes > TOTAL_BUDGET_BYTES:
        raise SystemExit(f"example over total budget ({total_bytes:,} > {TOTAL_BUDGET_BYTES:,})")

    provenance = {
        "generated_at": utc_now(),
        "skill": "eda-field-level",
        "source": "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-level",
        "skill_commit": _git_commit(repo_root),
        "note": (
            "Derived analysis artifacts only. Raw field boundaries, weather tables, "
            "CDL tables and rasters stay in the runtime and are not committed."
        ),
        "budget": {
            "total_bytes": total_bytes,
            "total_limit_bytes": TOTAL_BUDGET_BYTES,
            "png_limit_bytes": PNG_BUDGET_BYTES,
            "csv_limit_bytes": CSV_BUDGET_BYTES,
        },
        "files": published,
    }
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"published {len(published)} artifacts to {dest}")
    print(f"total size {total_bytes / 1_000_000:.2f} MB (limit {TOTAL_BUDGET_BYTES / 1_000_000:.0f} MB)")
    for item in published:
        print(f"  {item['bytes']:>9,}  {item['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
