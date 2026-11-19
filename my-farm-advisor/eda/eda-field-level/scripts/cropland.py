"""CDL/cropland artifacts for ``eda-field-level``.

* ``fig_crop_rotation_heatmap.png`` - dominant crop per field-year.
* ``fig_crop_corn_share.png`` - 2025 corn share by grower.
* statistics - corn share, continuous-corn frequency and rotation diversity.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from common import (
    CROP_COLORS,
    CROP_SHORT,
    GROWER_COLORS,
    STAT_COLUMNS,
    Grower,
    crop_field_summary,
    dominant_crop,
    holm_adjust,
    kruskal_test,
    load_composition,
    load_rotation,
    pairwise_mannwhitney,
    use_agg_backend,
    write_table,
)

METRICS = [
    ("corn_share_2025", "2025 corn share (%)"),
    ("continuous_corn_freq", "continuous-corn frequency"),
    ("crop_diversity", "5-year crop diversity"),
]


def build(growers: list[Grower], dirs: dict[str, Path]) -> tuple[pd.DataFrame, list[dict]]:
    composition_frames = []
    summary_frames = []
    for grower in growers:
        composition = load_composition(grower)
        rotation = load_rotation(grower)
        summary = crop_field_summary(composition, rotation, grower)
        summary_frames.append(summary)
        comp = composition.copy()
        comp.insert(0, "grower", grower.label)
        composition_frames.append(comp)
        print(
            f"  cropland   {grower.label:9s} {len(summary):2d} fields  "
            f"2025 dominant={summary.dominant_2025.value_counts().to_dict()}"
        )

    composition_all = pd.concat(composition_frames, ignore_index=True)
    summary_all = pd.concat(summary_frames, ignore_index=True)

    write_table(
        composition_all[["grower", "field_id", "year", "crop_name", "pct", "crop_source"]]
        if "crop_source" in composition_all.columns
        else composition_all[["grower", "field_id", "year", "crop_name", "pct"]],
        dirs["tables"] / "crop_composition.csv",
    )
    write_table(summary_all, dirs["tables"] / "crop_field_summary.csv")

    plt = use_agg_backend()
    _plot_rotation_heatmap(composition_all, summary_all, growers, dirs["figures"] / "fig_crop_rotation_heatmap.png", plt)
    _plot_corn_share(summary_all, growers, dirs["figures"] / "fig_crop_corn_share.png", plt)

    stats = analyze(summary_all)
    return summary_all, stats


def _crop_categories(composition: pd.DataFrame) -> list[str]:
    present = set(composition["crop_name"].astype(str).unique())
    ordered = [crop for crop in CROP_COLORS if crop in present]
    ordered.extend(sorted(present.difference(ordered)))
    return ordered


def _text_color(hex_color: str) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "white" if luminance < 0.55 else "#1a1a1a"


def _plot_rotation_heatmap(
    composition: pd.DataFrame,
    summary: pd.DataFrame,
    growers: list[Grower],
    path: Path,
    plt,
) -> None:
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    dom = dominant_crop(composition)
    years = sorted(dom["year"].unique())
    categories = _crop_categories(dom)
    code = {crop: index for index, crop in enumerate(categories)}
    cmap = ListedColormap([CROP_COLORS.get(crop, CROP_COLORS["Other"]) for crop in categories])

    fig, axes = plt.subplots(1, len(growers), figsize=(15, 5.8))
    if len(growers) == 1:
        axes = [axes]

    for ax, grower in zip(axes, growers):
        sub = dom.loc[dom["field_id"].isin(summary.loc[summary["grower"] == grower.label, "field_id"])]
        order = (
            summary.loc[summary["grower"] == grower.label]
            .sort_values(["dominant_2025", "field_id"])
            .loc[:, "field_id"]
            .tolist()
        )
        matrix = np.full((len(order), len(years)), np.nan)
        for row_index, field_id in enumerate(order):
            for col_index, year in enumerate(years):
                match = sub.loc[(sub["field_id"] == field_id) & (sub["year"] == year), "crop_name"]
                if len(match):
                    matrix[row_index, col_index] = code.get(str(match.iloc[0]), code.get("Other", 0))

        ax.imshow(matrix, cmap=cmap, vmin=-0.5, vmax=len(categories) - 0.5, aspect="auto")
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels(years)
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels(order, fontsize=7)
        ax.set_title(f"{grower.label} - dominant crop by year", loc="left")
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)

        for row_index, field_id in enumerate(order):
            for col_index, year in enumerate(years):
                match = sub.loc[(sub["field_id"] == field_id) & (sub["year"] == year)]
                if not len(match):
                    continue
                crop = str(match.iloc[0]["crop_name"])
                color = CROP_COLORS.get(crop, CROP_COLORS["Other"])
                ax.text(
                    col_index,
                    row_index,
                    CROP_SHORT.get(crop, "?"),
                    ha="center",
                    va="center",
                    fontsize=7,
                    color=_text_color(color),
                )

    handles = [Patch(facecolor=CROP_COLORS.get(crop, CROP_COLORS["Other"]), label=crop) for crop in categories]
    fig.legend(handles=handles, loc="lower center", ncol=min(4, len(categories)), bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("Crop rotation within each field, 2021-2025 (dominant CDL class per year)", y=1.0, fontsize=12)
    fig.tight_layout(rect=(0, 0.05, 1, 0.98))
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path.name}")


def _plot_corn_share(summary: pd.DataFrame, growers: list[Grower], path: Path, plt) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    rng = np.random.default_rng(20261119)
    data = []
    positions = []
    colors = []

    for index, grower in enumerate(growers, start=1):
        values = summary.loc[summary["grower"] == grower.label, "corn_share_2025"].to_numpy()
        data.append(values)
        positions.append(index)
        colors.append(GROWER_COLORS[grower.label])

    box = ax.boxplot(
        data,
        positions=positions,
        widths=0.5,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "#222222", "linewidth": 1.6},
        whiskerprops={"color": "#555555"},
        capprops={"color": "#555555"},
    )
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.18)
        patch.set_edgecolor(color)

    for index, grower in enumerate(growers, start=1):
        values = summary.loc[summary["grower"] == grower.label, "corn_share_2025"].to_numpy()
        jitter = rng.uniform(-0.16, 0.16, size=len(values))
        ax.scatter(
            index + jitter,
            values,
            s=38,
            color=GROWER_COLORS[grower.label],
            edgecolor="white",
            linewidth=0.6,
            zorder=3,
        )

    pasture = summary.loc[summary["dominant_2025"] == "Grass/Pasture"]
    for _, row in pasture.iterrows():
        index = next(i for i, grower in enumerate(growers, start=1) if grower.label == row["grower"])
        ax.annotate(
            f"{row['field_id']} (pasture)",
            xy=(index, row["corn_share_2025"]),
            xytext=(14, -4),
            textcoords="offset points",
            fontsize=7,
            color="#555555",
            arrowprops={"arrowstyle": "-", "color": "#999999", "linewidth": 0.8},
        )

    ax.set_xticks(positions)
    ax.set_xticklabels([grower.label for grower in growers])
    ax.set_ylabel("Corn share of field pixels, 2025 (%)")
    ax.set_ylim(-4, 104)
    ax.set_title("2025 corn share: Nebraska is corn-dominant, Iowa is soybean-heavy, Illinois is split")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path.name}")


def _row(**kwargs) -> dict:
    row = {column: np.nan for column in STAT_COLUMNS}
    row.update(kwargs)
    return row


def analyze(summary: pd.DataFrame) -> list[dict]:
    labels = list(dict.fromkeys(summary["grower"]))
    pairs = [(a, b) for i, a in enumerate(labels) for b in labels[i + 1:]]
    rows: list[dict] = []
    pairwise_rows: list[dict] = []

    for metric, metric_label in METRICS:
        groups = [summary.loc[summary["grower"] == label, metric].dropna().to_numpy() for label in labels]
        h, p, epsilon_sq = kruskal_test(groups)
        rows.append(
            _row(
                category="cropland",
                analysis="kruskal_wallis",
                metric=metric_label,
                group_a="all growers",
                n_a=int(sum(len(item) for item in groups)),
                median_a=float(summary[metric].median()),
                statistic=h,
                p_value=p,
                p_adjusted=p,
                effect_size=epsilon_sq,
                effect_size_name="epsilon-squared",
                note="10 fields per grower",
            )
        )

        results = pairwise_mannwhitney(summary, metric, "grower", pairs)
        adjusted = holm_adjust([item["p_value"] for item in results])
        for item, p_adj in zip(results, adjusted):
            row = _row(
                category="cropland",
                analysis="mann_whitney",
                metric=metric_label,
                group_a=item["group_a"],
                group_b=item["group_b"],
                n_a=item["n_a"],
                n_b=item["n_b"],
                median_a=item["median_a"],
                median_b=item["median_b"],
                statistic=item["statistic"],
                p_value=item["p_value"],
                p_adjusted=p_adj,
                effect_size=item["effect_size"],
                effect_size_name=item["effect_size_name"],
                note="Holm within metric",
            )
            rows.append(row)
            pairwise_rows.append(row)

    family_adjusted = holm_adjust([row["p_value"] for row in pairwise_rows])
    for row, p_adj in zip(pairwise_rows, family_adjusted):
        row["p_adjusted_family"] = p_adj

    print(f"  cropland analysis: {len(rows)} rows")
    return rows
