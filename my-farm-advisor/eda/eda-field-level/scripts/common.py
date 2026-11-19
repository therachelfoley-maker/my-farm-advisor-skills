"""Shared helpers for the ``eda-field-level`` subskill.

Every path resolves from ``DATA_PIPELINE_DATA_ROOT`` (default
``~/my-farm-advisor-runtime``). The skill reads canonical farm outputs and
writes only static analysis artifacts under
``<runtime>/data-pipeline/eda/field-level``. Nothing here writes inside the
skill repository.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Analysis constants
# ---------------------------------------------------------------------------

SEASON_START_MD = 401  # April 1
SEASON_END_MD = 930  # September 30
GDD_BASE_C = 10.0
HEAT_THRESHOLD_C = 30.0
BOOTSTRAP_REPS = 2000
PERMUTATION_REPS = 10000
RANDOM_SEED = 20261119
ACRES_PER_M2 = 4046.8564224

# ---------------------------------------------------------------------------
# Visual vocabulary
# ---------------------------------------------------------------------------

GROWER_COLORS = {
    "Illinois": "#1f6fb4",
    "Iowa": "#2f8f4e",
    "Nebraska": "#c4452f",
}

SOURCE_COLORS = {
    "USDA CSB": "#2b2b2b",
    "OpenStreetMap": "#b07a1e",
}

CROP_COLORS = {
    "Corn": "#f0c24b",
    "Soybeans": "#4f9d69",
    "Grass/Pasture": "#9aa86a",
    "Alfalfa": "#7fa7c9",
    "Winter Wheat": "#c98f5a",
    "Forest": "#4a6b52",
    "Fallow/Idle": "#cfc7b0",
    "Other": "#b8b8b8",
}

CROP_SHORT = {
    "Corn": "C",
    "Soybeans": "S",
    "Grass/Pasture": "P",
    "Alfalfa": "A",
    "Winter Wheat": "W",
    "Forest": "F",
    "Fallow/Idle": "I",
    "Other": "O",
}


@dataclass(frozen=True)
class Grower:
    """One grower/farm pair known to the canonical runtime tree."""

    slug: str
    farm: str
    prefix: str
    label: str
    state: str


DEFAULT_GROWERS: tuple[Grower, ...] = (
    Grower("il-grower", "illinois-farm", "illinois", "Illinois", "IL"),
    Grower("ia-grower", "iowa-farm", "iowa", "Iowa", "IA"),
    Grower("ne-grower", "nebraska-farm", "nebraska", "Nebraska", "NE"),
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def runtime_root() -> Path:
    """Return the runtime root (``DATA_PIPELINE_DATA_ROOT``)."""

    raw = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / "my-farm-advisor-runtime").resolve()


def pipeline_root() -> Path:
    return runtime_root() / "data-pipeline"


def farm_root(grower: Grower) -> Path:
    return pipeline_root() / "growers" / grower.slug / "farms" / grower.farm


def tables_dir(grower: Grower) -> Path:
    return farm_root(grower) / "derived" / "tables"


def output_root() -> Path:
    return pipeline_root() / "eda" / "field-level"


def ensure_output_dirs(root: Path | None = None) -> dict[str, Path]:
    base = root or output_root()
    dirs = {
        "root": base,
        "tables": base / "tables",
        "figures": base / "figures",
        "maps": base / "maps",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def resolve_growers(slugs: str | list[str] | None = None) -> list[Grower]:
    """Filter the default registry by grower slug (comma list accepted)."""

    if not slugs:
        return list(DEFAULT_GROWERS)
    if isinstance(slugs, str):
        wanted = [part.strip() for part in slugs.split(",") if part.strip()]
    else:
        wanted = [part.strip() for part in slugs if part.strip()]
    by_slug = {g.slug: g for g in DEFAULT_GROWERS}
    missing = [slug for slug in wanted if slug not in by_slug]
    if missing:
        raise SystemExit(f"unknown grower slug(s): {', '.join(missing)}")
    return [by_slug[slug] for slug in wanted]


# ---------------------------------------------------------------------------
# Loaders and validation
# ---------------------------------------------------------------------------


def _require(path: Path, label: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def load_boundaries(grower: Grower):
    import geopandas as gpd

    path = _require(farm_root(grower) / "boundary" / "field_boundaries.geojson", "field boundaries")
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")
    if "field_id" not in gdf.columns:
        raise ValueError(f"boundary file has no field_id column: {path}")
    if gdf["field_id"].duplicated().any():
        dupes = gdf.loc[gdf["field_id"].duplicated(), "field_id"].tolist()
        raise ValueError(f"duplicate field_id values in {path}: {dupes}")
    return gdf


def load_weather(grower: Grower) -> pd.DataFrame:
    path = _require(tables_dir(grower) / f"{grower.prefix}_weather_2021_2025.csv", "weather table")
    df = pd.read_csv(path, parse_dates=["date"])
    required = {"field_id", "date", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "lat", "lon"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"weather table missing columns {sorted(missing)}: {path}")
    if df[["T2M_MAX", "T2M_MIN", "PRECTOTCORR"]].isna().any().any():
        raise ValueError(f"weather table contains null values: {path}")
    if df.duplicated(["field_id", "date"]).any():
        raise ValueError(f"weather table has duplicate (field_id, date) rows: {path}")
    counts = df.groupby("field_id").size()
    if counts.nunique() != 1:
        raise ValueError(f"weather table has uneven day counts per field: {path}")
    return df


def load_composition(grower: Grower) -> pd.DataFrame:
    path = _require(
        tables_dir(grower) / f"{grower.prefix}_cdl_2021_2025_full_composition.csv",
        "CDL composition table",
    )
    df = pd.read_csv(path)
    required = {"field_id", "year", "crop_name", "pct"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"composition table missing columns {sorted(missing)}: {path}")
    return df


def load_rotation(grower: Grower) -> pd.DataFrame:
    path = _require(tables_dir(grower) / f"{grower.prefix}_crop_rotation.csv", "crop rotation table")
    df = pd.read_csv(path)
    required = {"field_id", "crop_diversity", "corn_years", "soybean_years"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"rotation table missing columns {sorted(missing)}: {path}")
    return df


# ---------------------------------------------------------------------------
# Derived metrics
# ---------------------------------------------------------------------------


def boundary_metrics(gdf, grower: Grower) -> pd.DataFrame:
    """Per-field geometry metrics plus provenance and share of farm acres."""

    g = gdf.copy()
    proj = g.to_crs("EPSG:5070")
    area_m2 = proj.geometry.area.to_numpy(dtype=float)
    perimeter_m = proj.geometry.length.to_numpy(dtype=float)
    computed_acres = area_m2 / ACRES_PER_M2

    if "area_acres" in g.columns:
        declared = pd.to_numeric(g["area_acres"], errors="coerce").to_numpy(dtype=float)
    else:
        declared = np.full(len(g), np.nan)
    acres = np.where(np.isfinite(declared) & (declared > 0), declared, computed_acres)

    source = g["source"].astype(str) if "source" in g.columns else pd.Series("unknown", index=g.index)
    crop = g["crop_name"].astype(str) if "crop_name" in g.columns else pd.Series("Unknown", index=g.index)
    source_class = np.where(source.str.lower().str.contains("csb"), "USDA CSB", "OpenStreetMap")

    centroid = proj.geometry.centroid.to_crs("EPSG:4326")
    label_point = proj.geometry.representative_point().to_crs("EPSG:4326")

    out = pd.DataFrame(
        {
            "grower": grower.label,
            "grower_slug": grower.slug,
            "farm": grower.farm,
            "state": grower.state,
            "field_id": g["field_id"].astype(str).to_numpy(),
            "source": source.to_numpy(),
            "source_class": source_class,
            "crop_name": crop.to_numpy(),
            "area_acres": acres,
            "area_ha": acres * ACRES_PER_M2 / 10000.0,
            "perimeter_m": perimeter_m,
            "compactness": 4.0 * np.pi * area_m2 / np.square(perimeter_m),
            "centroid_lat": centroid.y.to_numpy(),
            "centroid_lon": centroid.x.to_numpy(),
            "label_lat": label_point.y.to_numpy(),
            "label_lon": label_point.x.to_numpy(),
        }
    )
    total = out["area_acres"].sum()
    out["share_of_grower_acres"] = out["area_acres"] / total if total else np.nan
    out["rank_in_grower"] = out["area_acres"].rank(ascending=False, method="first").astype(int)
    return out


def add_gdd(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["gdd"] = ((out["T2M_MAX"] + out["T2M_MIN"]) / 2.0 - GDD_BASE_C).clip(lower=0.0)
    return out


def season_mask(dates: pd.Series) -> pd.Series:
    md = dates.dt.month * 100 + dates.dt.day
    return (md >= SEASON_START_MD) & (md <= SEASON_END_MD)


def seasonal_weather(df: pd.DataFrame, grower: Grower) -> pd.DataFrame:
    """Field-year growing-season aggregates (Apr 1 - Sep 30)."""

    work = add_gdd(df)
    work["year"] = work["date"].dt.year
    season = work.loc[season_mask(work["date"])].copy()
    agg = (
        season.groupby(["field_id", "year"], as_index=False)
        .agg(
            gdd=("gdd", "sum"),
            precip_mm=("PRECTOTCORR", "sum"),
            heat_days=("T2M_MAX", lambda s: int((s > HEAT_THRESHOLD_C).sum())),
            days=("date", "size"),
        )
        .sort_values(["field_id", "year"])
    )
    agg.insert(0, "grower", grower.label)
    agg.insert(1, "grower_slug", grower.slug)
    return agg


def weather_cell_year(df: pd.DataFrame, grower: Grower) -> pd.DataFrame:
    """Cell-year weather aggregates.

    Fields inside a grower usually share a NASA POWER grid cell, so field-year
    rows are pseudo-replicates. The CSV stores field centroids, not cell
    centres, so cells are identified by identical daily temperature series.
    """

    work = add_gdd(df)
    work["year"] = work["date"].dt.year

    pivot = work.pivot_table(index="date", columns="field_id", values="T2M").sort_index()
    signatures: dict[tuple, str] = {}
    field_to_cell: dict[str, str] = {}
    for field_id in pivot.columns:
        key = tuple(np.round(pivot[field_id].to_numpy(dtype=float), 3))
        if key not in signatures:
            signatures[key] = f"cell{len(signatures) + 1}"
        field_to_cell[field_id] = signatures[key]

    work["cell_id"] = work["field_id"].map(field_to_cell)
    fields_per_cell = work.groupby("cell_id")["field_id"].nunique()
    representatives = work.drop_duplicates("cell_id")["field_id"]
    cells = work.loc[work["field_id"].isin(representatives)].copy()

    season = cells.loc[season_mask(cells["date"])]
    agg = (
        season.groupby(["cell_id", "year"], as_index=False)
        .agg(
            gdd=("gdd", "sum"),
            precip_mm=("PRECTOTCORR", "sum"),
            heat_days=("T2M_MAX", lambda s: int((s > HEAT_THRESHOLD_C).sum())),
            days=("date", "size"),
            lat=("lat", "first"),
            lon=("lon", "first"),
            representative_field=("field_id", "first"),
        )
        .sort_values(["cell_id", "year"])
    )
    agg["fields_in_cell"] = agg["cell_id"].map(fields_per_cell).astype(int)
    agg.insert(0, "grower", grower.label)
    agg.insert(1, "grower_slug", grower.slug)
    return agg


def dominant_crop(composition: pd.DataFrame) -> pd.DataFrame:
    ordered = composition.sort_values(["field_id", "year", "pct"], ascending=[True, True, False])
    return ordered.groupby(["field_id", "year"], as_index=False).first()


def crop_field_summary(composition: pd.DataFrame, rotation: pd.DataFrame, grower: Grower) -> pd.DataFrame:
    """One row per field: 2025 composition, rotation intensity, diversity."""

    dom = dominant_crop(composition)
    corn_2025 = (
        composition.loc[(composition["year"] == 2025) & (composition["crop_name"] == "Corn")]
        .groupby("field_id")["pct"]
        .sum()
    )

    rows: list[dict] = []
    for field_id, sub in dom.sort_values("year").groupby("field_id"):
        sub = sub.sort_values("year")
        sequence = sub["crop_name"].astype(str).tolist()
        years = sub["year"].astype(int).tolist()
        transitions = list(zip(sequence[:-1], sequence[1:]))
        continuous = (
            sum(1 for a, b in transitions if a == "Corn" and b == "Corn") / len(transitions)
            if transitions
            else np.nan
        )
        changes = sum(1 for a, b in transitions if a != b)
        last = sub.loc[sub["year"].idxmax()]
        rows.append(
            {
                "grower": grower.label,
                "grower_slug": grower.slug,
                "field_id": field_id,
                "rotation_sequence": " -> ".join(sequence),
                "rotation_years": f"{min(years)}-{max(years)}",
                "n_crop_changes": changes,
                "continuous_corn_freq": continuous,
                "dominant_2025": str(last["crop_name"]),
                "dominant_2025_pct": float(last["pct"]),
                "corn_share_2025": float(corn_2025.get(field_id, 0.0)),
            }
        )

    out = pd.DataFrame(rows)
    keep = [
        "field_id",
        "rotation_sequence",
        "crop_diversity",
        "corn_years",
        "soybean_years",
        "predicted_next_crop",
    ]
    available = [col for col in keep if col in rotation.columns]
    if available:
        out = out.merge(rotation[available], on="field_id", how="left")
    if "crop_diversity" not in out.columns:
        out["crop_diversity"] = out["rotation_sequence"].str.count(" -> ") + 1
    return out


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

STAT_COLUMNS = [
    "category",
    "analysis",
    "metric",
    "group_a",
    "group_b",
    "n_a",
    "n_b",
    "median_a",
    "median_b",
    "statistic",
    "p_value",
    "p_adjusted",
    "p_adjusted_family",
    "effect_size",
    "effect_size_name",
    "ci_low",
    "ci_high",
    "note",
]


def kruskal_test(groups: list[np.ndarray]) -> tuple[float, float, float]:
    """Kruskal-Wallis H, p, and epsilon-squared effect size."""

    from scipy import stats

    cleaned = [np.asarray(group, dtype=float) for group in groups if len(group)]
    h, p = stats.kruskal(*cleaned)
    n = sum(len(group) for group in cleaned)
    k = len(cleaned)
    epsilon_sq = (h - k + 1) / (n - k) if n > k else np.nan
    return float(h), float(p), float(np.clip(epsilon_sq, 0.0, 1.0))


def pairwise_mannwhitney(
    frame: pd.DataFrame, value_col: str, group_col: str, pairs: list[tuple[str, str]]
) -> list[dict]:
    """Two-sided Mann-Whitney U for each pair, with rank-biserial effect size."""

    from scipy import stats

    results: list[dict] = []
    for a, b in pairs:
        x = frame.loc[frame[group_col] == a, value_col].dropna().to_numpy(dtype=float)
        y = frame.loc[frame[group_col] == b, value_col].dropna().to_numpy(dtype=float)
        if len(x) == 0 or len(y) == 0:
            continue
        u, p = stats.mannwhitneyu(x, y, alternative="two-sided", method="asymptotic")
        rank_biserial = 2.0 * u / (len(x) * len(y)) - 1.0
        results.append(
            {
                "group_a": a,
                "group_b": b,
                "n_a": len(x),
                "n_b": len(y),
                "median_a": float(np.median(x)),
                "median_b": float(np.median(y)),
                "statistic": float(u),
                "p_value": float(p),
                "effect_size": float(rank_biserial),
                "effect_size_name": "rank-biserial",
            }
        )
    return results


def holm_adjust(p_values: list[float]) -> list[float]:
    """Holm step-down adjusted p-values (monotone, capped at 1)."""

    p = np.asarray(p_values, dtype=float)
    m = len(p)
    if m == 0:
        return []
    order = np.argsort(p)
    adjusted = np.empty(m, dtype=float)
    running = 0.0
    for rank, idx in enumerate(order):
        candidate = (m - rank) * p[idx]
        running = max(running, candidate)
        adjusted[idx] = min(1.0, running)
    return adjusted.tolist()


def gini(values) -> float:
    x = np.sort(np.asarray(values, dtype=float))
    n = len(x)
    if n == 0 or x.sum() <= 0:
        return float("nan")
    index = np.arange(1, n + 1)
    return float((2.0 * np.sum(index * x)) / (n * x.sum()) - (n + 1) / n)


def bootstrap_gini(values, reps: int = BOOTSTRAP_REPS, seed: int = RANDOM_SEED) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    x = np.asarray(values, dtype=float)
    draws = [gini(rng.choice(x, size=len(x), replace=True)) for _ in range(reps)]
    return gini(x), float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def permutation_gini_diff(
    a, b, reps: int = PERMUTATION_REPS, seed: int = RANDOM_SEED
) -> tuple[float, float]:
    """Two-sided permutation test for a difference in Gini coefficients."""

    rng = np.random.default_rng(seed)
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    observed = gini(a) - gini(b)
    pool = np.concatenate([a, b])
    n_a = len(a)
    extreme = 0
    for _ in range(reps):
        rng.shuffle(pool)
        diff = gini(pool[:n_a]) - gini(pool[n_a:])
        if abs(diff) >= abs(observed) - 1e-12:
            extreme += 1
    return float(observed), float((extreme + 1) / (reps + 1))


def variance_decomposition(frame: pd.DataFrame, value_col: str, group_col: str) -> dict:
    """Within- versus between-grower variance for a field-level metric."""

    groups = [g[value_col].dropna().to_numpy(dtype=float) for _, g in frame.groupby(group_col)]
    groups = [g for g in groups if len(g) > 1]
    if len(groups) < 2:
        return {"between": np.nan, "within": np.nan, "total": np.nan, "icc": np.nan}
    means = np.array([g.mean() for g in groups])
    within = float(np.mean([g.var(ddof=1) for g in groups]))
    between = float(means.var(ddof=1))
    total = between + within
    return {
        "between": between,
        "within": within,
        "total": total,
        "icc": between / total if total else np.nan,
    }


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def write_table(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format="%.6g")
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, rows: int | None = None) -> dict:
    record = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }
    if rows is not None:
        record["rows"] = int(rows)
    return record


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in ("pandas", "numpy", "scipy", "matplotlib", "seaborn", "geopandas", "shapely"):
        try:
            module = __import__(name)
            versions[name] = getattr(module, "__version__", "unknown")
        except Exception:  # pragma: no cover - optional dependency
            versions[name] = "missing"
    return versions


def write_json(payload: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Plot setup
# ---------------------------------------------------------------------------


def use_agg_backend():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "figure.dpi": 200,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linewidth": 0.6,
            "legend.frameon": False,
            "legend.fontsize": 8,
        }
    )
    return plt
