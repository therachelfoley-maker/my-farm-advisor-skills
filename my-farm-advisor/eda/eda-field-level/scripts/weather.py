"""Weather artifacts for ``eda-field-level``.

* ``fig_weather_gdd_heatmap.png`` - seasonal GDD per field-year.
* ``fig_weather_precip_distribution.png`` - Apr-Sep precipitation by grower.
* statistics - cell-year Kruskal-Wallis / Mann-Whitney plus a within-versus-
  between-grower variance decomposition.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from common import (
    GROWER_COLORS,
    STAT_COLUMNS,
    Grower,
    holm_adjust,
    kruskal_test,
    load_weather,
    pairwise_mannwhitney,
    seasonal_weather,
    use_agg_backend,
    variance_decomposition,
    weather_cell_year,
    write_table,
)


def build(growers: list[Grower], dirs: dict[str, Path]) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    seasonal_frames = []
    cell_frames = []
    for grower in growers:
        weather = load_weather(grower)
        seasonal = seasonal_weather(weather, grower)
        cells = weather_cell_year(weather, grower)
        seasonal_frames.append(seasonal)
        cell_frames.append(cells)
        print(
            f"  weather    {grower.label:9s} {weather.field_id.nunique():2d} fields  "
            f"{len(weather):,d} rows  GDD {seasonal.gdd.min():,.0f}-{seasonal.gdd.max():,.0f}  "
            f"precip {seasonal.precip_mm.min():,.0f}-{seasonal.precip_mm.max():,.0f} mm"
        )

    seasonal_all = pd.concat(seasonal_frames, ignore_index=True)
    cells_all = pd.concat(cell_frames, ignore_index=True)

    write_table(seasonal_all, dirs["tables"] / "weather_seasonal.csv")
    write_table(cells_all, dirs["tables"] / "weather_cell_year.csv")

    plt = use_agg_backend()
    _plot_gdd_heatmap(seasonal_all, growers, dirs["figures"] / "fig_weather_gdd_heatmap.png", plt)
    _plot_precip(seasonal_all, growers, dirs["figures"] / "fig_weather_precip_distribution.png", plt)

    stats = analyze(seasonal_all, cells_all)
    return seasonal_all, cells_all, stats


def _plot_gdd_heatmap(seasonal: pd.DataFrame, growers: list[Grower], path: Path, plt) -> None:
    years = sorted(seasonal["year"].unique())
    vmin = float(seasonal["gdd"].min())
    vmax = float(seasonal["gdd"].max())

    fig, axes = plt.subplots(1, len(growers), figsize=(14.5, 5.6))
    if len(growers) == 1:
        axes = [axes]

    image = None
    for ax, grower in zip(axes, growers):
        sub = seasonal.loc[seasonal["grower"] == grower.label]
        fields = sorted(sub["field_id"].unique())
        matrix = sub.pivot(index="field_id", columns="year", values="gdd").reindex(index=fields, columns=years)
        image = ax.imshow(matrix.to_numpy(), cmap="YlOrRd", vmin=vmin, vmax=vmax, aspect="auto")
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels(years)
        ax.set_yticks(range(len(fields)))
        ax.set_yticklabels(fields, fontsize=7)
        ax.set_title(f"{grower.label} - Apr-Sep GDD", loc="left")
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)

        for row_index in range(matrix.shape[0]):
            for col_index in range(matrix.shape[1]):
                value = matrix.iloc[row_index, col_index]
                if pd.isna(value):
                    continue
                ax.text(
                    col_index,
                    row_index,
                    f"{value:,.0f}",
                    ha="center",
                    va="center",
                    fontsize=6.5,
                    color="white" if value > (vmin + vmax) / 2 else "#1a1a1a",
                )

    fig.suptitle("Seasonal GDD by field and year: fields move together, growers separate", y=1.0, fontsize=12)
    fig.tight_layout(rect=(0, 0, 0.95, 0.98))
    if image is not None:
        colorbar_axis = fig.add_axes([0.955, 0.16, 0.012, 0.68])
        colorbar = fig.colorbar(image, cax=colorbar_axis)
        colorbar.set_label("Growing-season GDD (base 10 C, Apr 1 - Sep 30)")
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path.name}")


def _plot_precip(seasonal: pd.DataFrame, growers: list[Grower], path: Path, plt) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    rng = np.random.default_rng(20261119)
    data = []
    positions = []
    colors = []

    for index, grower in enumerate(growers, start=1):
        values = seasonal.loc[seasonal["grower"] == grower.label, "precip_mm"].to_numpy()
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
        values = seasonal.loc[seasonal["grower"] == grower.label, "precip_mm"].to_numpy()
        jitter = rng.uniform(-0.16, 0.16, size=len(values))
        ax.scatter(
            index + jitter,
            values,
            s=26,
            color=GROWER_COLORS[grower.label],
            alpha=0.75,
            edgecolor="white",
            linewidth=0.4,
            zorder=3,
        )

    ax.set_xticks(positions)
    ax.set_xticklabels([grower.label for grower in growers])
    ax.set_ylabel("Growing-season precipitation (mm, Apr 1 - Sep 30)")
    ax.set_title("Water supply: Iowa spreads widest, Nebraska is tightest and lowest")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path.name}")


def _row(**kwargs) -> dict:
    row = {column: np.nan for column in STAT_COLUMNS}
    row.update(kwargs)
    return row


def analyze(seasonal: pd.DataFrame, cells: pd.DataFrame) -> list[dict]:
    labels = list(dict.fromkeys(seasonal["grower"]))
    pairs = [(a, b) for i, a in enumerate(labels) for b in labels[i + 1:]]
    rows: list[dict] = []
    pairwise_rows: list[dict] = []

    for metric, metric_label, unit in [
        ("gdd", "seasonal GDD", "C-day"),
        ("precip_mm", "seasonal precipitation", "mm"),
    ]:
        groups = [cells.loc[cells["grower"] == label, metric].dropna().to_numpy() for label in labels]
        h, p, epsilon_sq = kruskal_test(groups)
        per_grower = {label: int((cells["grower"] == label).sum()) for label in labels}
        rows.append(
            _row(
                category="weather",
                analysis="kruskal_wallis",
                metric=metric_label,
                group_a="all growers",
                n_a=int(sum(len(group) for group in groups)),
                median_a=float(cells[metric].median()),
                statistic=h,
                p_value=p,
                p_adjusted=p,
                effect_size=epsilon_sq,
                effect_size_name="epsilon-squared",
                note=(
                    "Unit is NASA POWER grid-cell-year, not field-year, because fields "
                    f"inside a grower share cells; n per grower = {per_grower} ({unit})"
                ),
            )
        )

        results = pairwise_mannwhitney(cells, metric, "grower", pairs)
        adjusted = holm_adjust([item["p_value"] for item in results])
        for item, p_adj in zip(results, adjusted):
            row = _row(
                category="weather",
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
                note="Holm within metric; cell-year observations",
            )
            rows.append(row)
            pairwise_rows.append(row)

    family_adjusted = holm_adjust([row["p_value"] for row in pairwise_rows])
    for row, p_adj in zip(pairwise_rows, family_adjusted):
        row["p_adjusted_family"] = p_adj

    for metric, metric_label in [("gdd", "seasonal GDD"), ("precip_mm", "seasonal precipitation")]:
        decomposition = variance_decomposition(seasonal, metric, "grower")
        rows.append(
            _row(
                category="weather",
                analysis="variance_decomposition",
                metric=metric_label,
                group_a="within vs between growers",
                n_a=len(seasonal),
                statistic=decomposition["icc"],
                effect_size=decomposition["icc"],
                effect_size_name="ICC (between / total)",
                note=(
                    f"between={decomposition['between']:.6g}, "
                    f"within={decomposition['within']:.6g}, "
                    "field-year values; within-grower replication is grid-cell driven"
                ),
            )
        )

    print(f"  weather analysis: {len(rows)} rows")
    return rows
