"""Boundary-category artifacts for ``eda-field-level``.

Two figures and one analysis block:

* ``fig_boundary_area.png`` - sorted field-size rank chart, linear acres.
* ``fig_boundary_concentration.png`` - Lorenz curve of acreage per grower.
* statistics - Kruskal-Wallis, Holm-corrected Mann-Whitney, Gini bootstrap and
  permutation tests, plus a CSB-only sensitivity run.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from common import (
    GROWER_COLORS,
    SOURCE_COLORS,
    STAT_COLUMNS,
    Grower,
    bootstrap_gini,
    boundary_metrics,
    gini,
    holm_adjust,
    kruskal_test,
    load_boundaries,
    pairwise_mannwhitney,
    permutation_gini_diff,
    use_agg_backend,
    write_table,
)


def build(growers: list[Grower], dirs: dict[str, Path]) -> tuple[pd.DataFrame, list[dict]]:
    frames = []
    for grower in growers:
        gdf = load_boundaries(grower)
        metrics = boundary_metrics(gdf, grower)
        frames.append(metrics)
        print(
            f"  boundaries {grower.label:9s} {len(metrics):2d} fields  "
            f"{metrics.area_acres.sum():8,.1f} ac  "
            f"{metrics.source_class.value_counts().to_dict()}"
        )

    metrics = pd.concat(frames, ignore_index=True)
    write_table(metrics, dirs["tables"] / "boundary_metrics.csv")

    plt = use_agg_backend()
    _plot_size_rank(metrics, growers, dirs["figures"] / "fig_boundary_area.png", plt)
    _plot_lorenz(metrics, growers, dirs["figures"] / "fig_boundary_concentration.png", plt)

    stats = analyze(metrics)
    return metrics, stats


def _plot_size_rank(metrics: pd.DataFrame, growers: list[Grower], path: Path, plt) -> None:
    fig, axes = plt.subplots(1, len(growers), figsize=(15, 5.6), sharex=True)
    if len(growers) == 1:
        axes = [axes]
    xmax = metrics["area_acres"].max() * 1.12

    handles = [
        plt.Line2D([], [], marker="o", linestyle="", color=color, label=label, markersize=6)
        for label, color in SOURCE_COLORS.items()
    ]

    for ax, grower in zip(axes, growers):
        sub = metrics.loc[metrics["grower"] == grower.label].sort_values("area_acres")
        positions = np.arange(1, len(sub) + 1)
        for source_class, color in SOURCE_COLORS.items():
            mask = (sub["source_class"] == source_class).to_numpy()
            if not mask.any():
                continue
            ax.hlines(
                positions[mask],
                0,
                sub.loc[mask, "area_acres"],
                color=color,
                linewidth=1.3,
                alpha=0.75,
            )
            ax.scatter(
                sub.loc[mask, "area_acres"],
                positions[mask],
                color=color,
                s=42,
                zorder=3,
                edgecolor="white",
                linewidth=0.6,
            )

        ax.set_yticks(positions)
        ax.set_yticklabels(sub["field_id"], fontsize=6.5)
        ax.set_ylim(0.3, len(sub) + 0.7)
        ax.set_xlim(0, xmax)
        ax.set_xlabel("Field area (acres, linear scale)", fontsize=8)
        source_counts = sub["source_class"].value_counts()
        source_bits = " / ".join(
            f"{int(source_counts.get(key, 0))} {short}"
            for key, short in (("USDA CSB", "CSB"), ("OpenStreetMap", "OSM"))
            if source_counts.get(key, 0)
        )
        ax.set_title(
            f"{grower.label} - {sub.area_acres.sum():,.0f} ac\n{len(sub)} fields - {source_bits}",
            loc="left",
        )
        ax.grid(axis="y", visible=False)

        for position, (_, row) in enumerate(sub.iterrows(), start=1):
            if row["area_acres"] >= 25:
                continue
            ax.annotate(
                f"{row['area_acres']:.1f} ac",
                xy=(row["area_acres"], position),
                xytext=(10, 0),
                textcoords="offset points",
                va="center",
                fontsize=6,
                color="#555555",
            )

    fig.legend(handles=handles, loc="lower center", ncol=2, bbox_to_anchor=(0.5, 0.01))
    fig.suptitle("Field sizes ranked within each grower", y=1.0, fontsize=12)
    fig.tight_layout(rect=(0, 0.06, 1, 0.98))
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path.name}")


def _plot_lorenz(metrics: pd.DataFrame, growers: list[Grower], path: Path, plt) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    ax.plot([0, 1], [0, 1], linestyle="--", color="#888888", linewidth=1, label="Perfect equality")

    for grower in growers:
        values = np.sort(metrics.loc[metrics["grower"] == grower.label, "area_acres"].to_numpy())
        total = values.sum()
        cumulative = np.concatenate([[0.0], np.cumsum(values) / total])
        x = np.linspace(0.0, 1.0, len(cumulative))
        top3 = values[-3:].sum() / total
        ax.plot(
            x,
            cumulative,
            marker="o",
            markersize=4,
            linewidth=1.8,
            color=GROWER_COLORS[grower.label],
            label=f"{grower.label} - Gini {gini(values):.2f} - top 3 = {top3:.0%}",
        )

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.set_xlabel("Cumulative share of fields (smallest to largest)")
    ax.set_ylabel("Cumulative share of grower acres")
    ax.set_title("Acreage concentration: Illinois and Iowa hold half their acres in three fields")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path.name}")


def _row(**kwargs) -> dict:
    row = {column: np.nan for column in STAT_COLUMNS}
    row.update(kwargs)
    return row


def _pairwise_rows(
    frame: pd.DataFrame,
    value_col: str,
    labels: list[str],
    category: str,
    metric: str,
    analysis: str,
    note_prefix: str,
) -> list[dict]:
    pairs = [(a, b) for i, a in enumerate(labels) for b in labels[i + 1:]]
    results = pairwise_mannwhitney(frame, value_col, "grower", pairs)
    adjusted = holm_adjust([item["p_value"] for item in results])
    rows = []
    for item, p_adj in zip(results, adjusted):
        rows.append(
            _row(
                category=category,
                analysis=analysis,
                metric=metric,
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
                note=note_prefix,
            )
        )
    return rows


def analyze(metrics: pd.DataFrame) -> list[dict]:
    labels = list(dict.fromkeys(metrics["grower"]))
    rows: list[dict] = []

    groups = [metrics.loc[metrics["grower"] == label, "area_acres"].to_numpy() for label in labels]
    h, p, epsilon_sq = kruskal_test(groups)
    rows.append(
        _row(
            category="boundaries",
            analysis="kruskal_wallis",
            metric="field_area_acres",
            group_a="all growers",
            n_a=len(metrics),
            median_a=float(metrics["area_acres"].median()),
            statistic=h,
            p_value=p,
            p_adjusted=p,
            effect_size=epsilon_sq,
            effect_size_name="epsilon-squared",
            note="All 10 fields per grower, legacy OSM included",
        )
    )
    rows.extend(
        _pairwise_rows(
            metrics,
            "area_acres",
            labels,
            category="boundaries",
            metric="field_area_acres",
            analysis="mann_whitney",
            note_prefix="Holm within the 3 grower pairs",
        )
    )

    for label in labels:
        values = metrics.loc[metrics["grower"] == label, "area_acres"].to_numpy()
        g, low, high = bootstrap_gini(values)
        rows.append(
            _row(
                category="boundaries",
                analysis="gini",
                metric="field_area_acres",
                group_a=label,
                n_a=len(values),
                statistic=g,
                effect_size=g,
                effect_size_name="gini",
                ci_low=low,
                ci_high=high,
                note="2000 bootstrap resamples, 95% percentile interval",
            )
        )

    pairs = [(a, b) for i, a in enumerate(labels) for b in labels[i + 1:]]
    perm_results = []
    for a, b in pairs:
        left = metrics.loc[metrics["grower"] == a, "area_acres"].to_numpy()
        right = metrics.loc[metrics["grower"] == b, "area_acres"].to_numpy()
        delta, p_value = permutation_gini_diff(left, right)
        perm_results.append((a, b, len(left), len(right), delta, p_value))
    adjusted = holm_adjust([item[5] for item in perm_results])
    for (a, b, n_a, n_b, delta, p_value), p_adj in zip(perm_results, adjusted):
        rows.append(
            _row(
                category="boundaries",
                analysis="permutation_gini_difference",
                metric="field_area_acres",
                group_a=a,
                group_b=b,
                n_a=n_a,
                n_b=n_b,
                statistic=delta,
                p_value=p_value,
                p_adjusted=p_adj,
                effect_size=delta,
                effect_size_name="delta-gini",
                note="10000 permutations, two-sided, Holm across 3 pairs",
            )
        )

    csb = metrics.loc[metrics["source_class"] == "USDA CSB"].copy()
    csb_labels = [label for label in labels if (csb["grower"] == label).any()]
    csb_groups = [csb.loc[csb["grower"] == label, "area_acres"].to_numpy() for label in csb_labels]
    h, p, epsilon_sq = kruskal_test(csb_groups)
    rows.append(
        _row(
            category="boundaries",
            analysis="kruskal_wallis_csb_only",
            metric="field_area_acres",
            group_a="CSB fields only",
            n_a=len(csb),
            median_a=float(csb["area_acres"].median()),
            statistic=h,
            p_value=p,
            p_adjusted=p,
            effect_size=epsilon_sq,
            effect_size_name="epsilon-squared",
            note=f"n per grower: {csb.groupby('grower').size().to_dict()}",
        )
    )
    rows.extend(
        _pairwise_rows(
            csb,
            "area_acres",
            csb_labels,
            category="boundaries",
            metric="field_area_acres",
            analysis="mann_whitney_csb_only",
            note_prefix="Sensitivity: legacy OSM fields removed",
        )
    )

    print(f"  boundaries analysis: {len(rows)} rows")
    return rows
