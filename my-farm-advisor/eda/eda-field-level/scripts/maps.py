"""Map artifacts for ``eda-field-level``.

One composite map: 2025 dominant crop as fill, legacy OpenStreetMap boundaries
as a dashed outline, field IDs and acreage labelled. One panel per grower.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from common import CROP_COLORS, Grower, load_boundaries, use_agg_backend


def build(growers: list[Grower], dirs: dict[str, Path]) -> Path:
    summary = pd.read_csv(dirs["tables"] / "crop_field_summary.csv")
    frames = []
    for grower in growers:
        gdf = load_boundaries(grower).to_crs("EPSG:5070")
        lookup = summary.loc[summary["grower"] == grower.label, ["field_id", "dominant_2025"]]
        gdf = gdf.merge(lookup, on="field_id", how="left")
        if "area_acres" not in gdf.columns:
            gdf["area_acres"] = gdf.geometry.area / 4046.8564224
        gdf["source_class"] = np.where(
            gdf["source"].astype(str).str.lower().str.contains("csb"),
            "USDA CSB",
            "OpenStreetMap",
        )
        frames.append((grower, gdf))

    plt = use_agg_backend()
    path = dirs["maps"] / "map_crop_2025_source.png"
    _plot(frames, path, plt)
    return path


def _plot(frames, path: Path, plt) -> None:
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    categories = sorted({crop for _, gdf in frames for crop in gdf["dominant_2025"].dropna().unique()})
    categories = [crop for crop in CROP_COLORS if crop in categories] + [
        crop for crop in categories if crop not in CROP_COLORS
    ]

    fig, axes = plt.subplots(1, len(frames), figsize=(16, 6.2))
    if len(frames) == 1:
        axes = [axes]

    for ax, (grower, gdf) in zip(axes, frames):
        for crop in categories:
            sub = gdf.loc[gdf["dominant_2025"] == crop]
            if sub.empty:
                continue
            sub.plot(
                ax=ax,
                color=CROP_COLORS.get(crop, CROP_COLORS["Other"]),
                edgecolor="white",
                linewidth=0.7,
            )

        osm = gdf.loc[gdf["source_class"] == "OpenStreetMap"]
        if not osm.empty:
            osm.boundary.plot(ax=ax, color="#111111", linewidth=2.4, linestyle=(0, (4, 2)), zorder=4)

        # Label legacy OSM polygons only. Labelling every CSB block would collide
        # in the compact Illinois cluster; the tables carry the full field list.
        offsets = [(20, 16), (20, -24), (-20, 16), (-20, -24)]
        for position, (_, row) in enumerate(osm.iterrows()):
            point = row.geometry.representative_point()
            offset = offsets[position % len(offsets)]
            label = row["field_id"]
            if row["area_acres"] < 10:
                label = f"{row['field_id']}\n{row['area_acres']:,.1f} ac"
            ax.annotate(
                label,
                xy=(point.x, point.y),
                xytext=offset,
                textcoords="offset points",
                ha="left" if offset[0] > 0 else "right",
                va="bottom" if offset[1] > 0 else "top",
                fontsize=6.5,
                color="#1a1a1a",
                zorder=5,
                arrowprops={"arrowstyle": "-", "color": "#555555", "linewidth": 0.7},
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
            )

        minx, miny, maxx, maxy = gdf.total_bounds
        width = maxx - minx
        height = maxy - miny
        pad = 0.06 * max(width, height)
        ax.set_xlim(minx - pad, maxx + pad)
        ax.set_ylim(miny - pad, maxy + pad)
        ax.set_aspect("equal")
        ax.set_axis_off()
        ax.set_title(
            f"{grower.label} ({grower.state}) - {gdf['area_acres'].sum():,.0f} ac\n"
            f"{int((gdf['source_class'] == 'USDA CSB').sum())} USDA CSB, "
            f"{int((gdf['source_class'] == 'OpenStreetMap').sum())} OpenStreetMap",
            loc="left",
        )
        _scale_bar(ax, minx, miny, maxx, maxy)

    handles = [Patch(facecolor=CROP_COLORS.get(crop, CROP_COLORS["Other"]), label=crop) for crop in categories]
    handles.append(Line2D([], [], color="#111111", linewidth=2.0, linestyle="--", label="OpenStreetMap legacy boundary"))
    fig.legend(handles=handles, loc="lower center", ncol=min(5, len(handles)), bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("2025 dominant crop and boundary provenance", y=1.0, fontsize=12)
    fig.tight_layout(rect=(0, 0.05, 1, 0.98))
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path.name}")


def _scale_bar(ax, minx: float, miny: float, maxx: float, maxy: float, length_m: float = 1000.0) -> None:
    width = maxx - minx
    height = maxy - miny
    x_start = maxx - 0.06 * width - length_m
    y_start = miny + 0.05 * height
    ax.plot([x_start, x_start + length_m], [y_start, y_start], color="#222222", linewidth=3, solid_capstyle="butt", zorder=6)
    ax.text(
        x_start + length_m / 2.0,
        y_start + 0.02 * height,
        "1 km",
        ha="center",
        va="bottom",
        fontsize=6.5,
        color="#222222",
        zorder=6,
    )
