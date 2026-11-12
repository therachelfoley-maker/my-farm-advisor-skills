#!/usr/bin/env python3
# pyright: reportMissingImports=false
"""Render a lightweight, grower-level interactive field map.

Reads the canonical farm boundary GeoJSON files written by the data pipeline and
emits one self-contained HTML page per grower. Field polygons and a small set of
metadata travel inside the page; the satellite basemap is fetched from Esri
World Imagery tiles at view time. No rasters, imagery, or data bundles are
embedded, so the output stays in the low tens of kilobytes.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import mapping

_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_RUNTIME_BASE = _RUNTIME_PATHS.runtime_base
_SCRIPTS = _RUNTIME_PATHS.runtime_scripts
_LIB = _RUNTIME_PATHS.runtime_scripts / "lib"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_LIB))

from lib.paths import (  # noqa: E402
    GROWERS_ROOT,
    farm_boundary_path,
    grower_dir,
)
from lib.us_states import state_abbr  # noqa: E402

CDL_YEAR_RE = re.compile(r"_(\d{4})_cdl\.csv$")
TARGET_CRS = "EPSG:4326"
# Ordered by how far each hue sits from green vegetation (CIE76 dE 74-103 for
# the first four vs 20-31 for the greens they replaced). Orange is last because
# it is only dE 48 from the amber selection colour and would read as a muddy
# highlight if it ever landed on early field slots.
FARM_COLORS = [
    "#D81B60",
    "#1E88E5",
    "#7B1FA2",
    "#C62828",
    "#00897B",
    "#283593",
    "#5D4037",
    "#E65100",
]

BASE_WEIGHT = 2.2
BASE_FILL_OPACITY = 0.22
BASE_CASING_WEIGHT = 4.5
BASE_CASING_OPACITY = 0.55
HOVER_WEIGHT = 3.0
HOVER_FILL_OPACITY = 0.30
HOVER_CASING_WEIGHT = 5.5
HOVER_CASING_OPACITY = 0.70

# Selection is deliberately not a farm colour: farm colour separates farms, amber
# marks the field you picked. The white casing keeps the amber stroke readable
# over green crops, tan residue, and pale bare soil alike. Every unselected field
# also carries a quieter casing, so an outline never depends on the basemap tone.
HIGHLIGHT = {
    "stroke": "#FFB300",
    "fill": "#FFC400",
    "weight": 3.5,
    "fillOpacity": 0.25,
    "casing": "#FFFFFF",
    "casingWeight": 7.5,
    "casingOpacity": 0.85,
    "baseWeight": BASE_WEIGHT,
    "baseFillOpacity": BASE_FILL_OPACITY,
    "baseCasingWeight": BASE_CASING_WEIGHT,
    "baseCasingOpacity": BASE_CASING_OPACITY,
    "hoverWeight": HOVER_WEIGHT,
    "hoverFillOpacity": HOVER_FILL_OPACITY,
    "hoverCasingWeight": HOVER_CASING_WEIGHT,
    "hoverCasingOpacity": HOVER_CASING_OPACITY,
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_json_string_field(path: Path, key: str) -> str | None:
    value = _read_json(path).get(key)
    return value if isinstance(value, str) and value.strip() else None


def _round_coords(value: Any, digits: int) -> Any:
    """Round nested coordinate lists to keep the embedded GeoJSON small."""
    if isinstance(value, (int, float)):
        return round(float(value), digits)
    if isinstance(value, (list, tuple)):
        return [_round_coords(item, digits) for item in value]
    if isinstance(value, dict):
        return {key: _round_coords(item, digits) for key, item in value.items()}
    return value


def _latest_cdl_year(farm_path: Path) -> int | None:
    tables = farm_path / "derived" / "tables"
    if not tables.is_dir():
        return None
    years = [
        int(match.group(1))
        for path in tables.iterdir()
        if path.is_file() and (match := CDL_YEAR_RE.search(path.name))
    ]
    return max(years) if years else None


def _load_crop_lookup(farm_path: Path, year: int | None) -> dict[str, tuple[str, float]]:
    """Map field_id to the dominant CDL class for the requested year."""
    if year is None:
        return {}
    tables = farm_path / "derived" / "tables"
    candidates = sorted(tables.glob(f"*_{year}_cdl.csv"))
    if not candidates:
        return {}
    best: dict[str, tuple[str, float]] = {}
    with candidates[0].open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            field_id = (row.get("field_id") or "").strip()
            crop = (row.get("crop_name") or "").strip()
            if not field_id or not crop:
                continue
            try:
                pct = float(row.get("pct") or 0.0)
            except ValueError:
                continue
            if field_id not in best or pct > best[field_id][1]:
                best[field_id] = (crop, pct)
    return best


def _field_label(field_id: str, display_name: str | None) -> str:
    if display_name and display_name != field_id:
        return display_name
    short = field_id[4:] if field_id.startswith("osm-") else field_id
    return f"Field {short}"


def _collect_grower(grower_slug: str, cdl_year_override: int | None) -> dict[str, Any]:
    grower_path = grower_dir(grower_slug)
    farms_root = grower_path / "farms"
    if not farms_root.is_dir():
        raise FileNotFoundError(f"No farms directory for grower '{grower_slug}'")

    grower_name = _read_json_string_field(grower_path / "grower.json", "display_name") or grower_slug
    farms: list[dict[str, Any]] = []
    all_bounds: list[float] | None = None

    for farm_path in sorted(p for p in farms_root.iterdir() if p.is_dir()):
        farm_slug = farm_path.name
        boundary = farm_boundary_path(grower_slug, farm_slug)
        if not boundary.exists():
            print(f"  skip {grower_slug}/{farm_slug}: no field_boundaries.geojson")
            continue

        gdf = gpd.read_file(boundary)
        if gdf.empty:
            print(f"  skip {grower_slug}/{farm_slug}: boundary file has no features")
            continue
        if gdf.crs is not None and gdf.crs.to_string() != TARGET_CRS:
            gdf = gdf.to_crs(TARGET_CRS)

        farm_name = _read_json_string_field(farm_path / "farm.json", "display_name") or farm_slug
        cdl_year = cdl_year_override or _latest_cdl_year(farm_path)
        crops = _load_crop_lookup(farm_path, cdl_year)

        fields: list[dict[str, Any]] = []
        for _, row in gdf.iterrows():
            nested = row.get("properties")
            props: dict[str, Any] = dict(nested) if isinstance(nested, dict) else {}
            for key in ("field_id", "state_fips", "county_name", "area_acres", "source"):
                value = row.get(key)
                if value is not None and key not in props:
                    props[key] = value
            field_id = str(props.get("field_id") or "").strip()
            if not field_id:
                continue
            field_json = farm_path / "fields" / field_id / "field.json"
            display_name = _read_json_string_field(field_json, "display_name")
            geometry = row.geometry
            if geometry is None or geometry.is_empty:
                continue

            state_fips = str(props.get("state_fips") or "").zfill(2)
            crop = crops.get(field_id)
            fields.append(
                {
                    "slug": field_id,
                    "label": _field_label(field_id, display_name),
                    "field_id": field_id,
                    "area_acres": round(float(props.get("area_acres") or 0.0), 3),
                    "county": str(props.get("county_name") or "").strip() or None,
                    "state": state_abbr(state_fips),
                    "source": str(props.get("source") or "").strip() or None,
                    "crop": {"year": cdl_year, "name": crop[0], "pct": round(crop[1], 1)} if crop else None,
                    "geometry": _round_coords(mapping(geometry), 6),
                }
            )

        if not fields:
            print(f"  skip {grower_slug}/{farm_slug}: no usable field polygons")
            continue

        fields.sort(key=lambda item: item["slug"])
        farms.append({"slug": farm_slug, "name": farm_name, "fields": fields})
        minx, miny, maxx, maxy = gdf.total_bounds
        if all_bounds is None:
            all_bounds = [minx, miny, maxx, maxy]
        else:
            all_bounds = [
                min(all_bounds[0], minx),
                min(all_bounds[1], miny),
                max(all_bounds[2], maxx),
                max(all_bounds[3], maxy),
            ]

    if not farms:
        raise ValueError(f"Grower '{grower_slug}' has no field boundaries to map")

    minx, miny, maxx, maxy = all_bounds  # type: ignore[misc]
    return {
        "grower": {"slug": grower_slug, "name": grower_name},
        "farms": farms,
        "bounds": [[miny, minx], [maxy, maxx]],
        "center": [round((miny + maxy) / 2.0, 6), round((minx + maxx) / 2.0, 6)],
    }


def _build_html(payload: dict[str, Any]) -> str:
    data_json = json.dumps(payload, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    grower_name = html.escape(payload["grower"]["name"])
    field_count = sum(len(farm["fields"]) for farm in payload["farms"])
    total_acres = sum(field["area_acres"] for farm in payload["farms"] for field in farm["fields"])
    subtitle = f"{field_count} fields &middot; {total_acres:,.1f} acres &middot; {len(payload['farms'])} farm(s)"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{grower_name} &mdash; field map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {{ --panel: #ffffff; --ink: #14210f; --muted: #5b6b57; --line: #dfe6da; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: var(--ink); }}
  #app {{ display: flex; height: 100%; }}
  #sidebar {{ width: 320px; flex: 0 0 320px; background: var(--panel); border-right: 1px solid var(--line); display: flex; flex-direction: column; overflow: hidden; }}
  #sidebar header {{ padding: 16px 16px 10px; border-bottom: 1px solid var(--line); }}
  #sidebar h1 {{ margin: 0 0 4px; font-size: 1.15rem; line-height: 1.2; }}
  #sidebar .sub {{ color: var(--muted); font-size: .78rem; }}
  #tools {{ padding: 10px 16px; border-bottom: 1px solid var(--line); }}
  button.fit-all {{ width: 100%; padding: 7px 10px; font-size: .8rem; border: 1px solid var(--line); background: #f4f8f1; border-radius: 6px; cursor: pointer; color: var(--ink); }}
  button.fit-all:hover {{ background: #e8f2e3; }}
  #fields {{ overflow-y: auto; padding: 8px 10px 16px; flex: 1; }}
  .farm-group {{ margin-bottom: 12px; }}
  .farm-group h2 {{ display: flex; align-items: center; gap: 8px; font-size: .74rem; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); margin: 6px 6px 6px; }}
  .chip {{ width: 11px; height: 11px; border-radius: 3px; flex: 0 0 11px; }}
  .field-btn {{ display: block; width: 100%; text-align: left; border: 1px solid transparent; background: none; border-radius: 6px; padding: 7px 8px; cursor: pointer; font: inherit; }}
  .field-btn:hover {{ background: #f4f8f1; border-color: var(--line); }}
  .field-btn.active {{ background: #FFF8E1; border-color: #FFE082; box-shadow: inset 3px 0 0 #FFB300; }}
  .field-btn.active .name {{ font-weight: 600; }}
  .field-btn .name {{ display: block; font-size: .84rem; }}
  .field-btn .meta {{ display: block; color: var(--muted); font-size: .72rem; margin-top: 2px; }}
  #sidebar footer {{ padding: 10px 16px 14px; border-top: 1px solid var(--line); color: var(--muted); font-size: .68rem; line-height: 1.45; }}
  #sidebar footer .legend {{ display: flex; align-items: center; gap: 6px; margin-bottom: 6px; color: var(--ink); font-size: .7rem; }}
  #sidebar footer .legend i {{ width: 15px; height: 10px; flex: 0 0 15px; border: 2px solid #FFB300; border-radius: 2px; background: rgba(255, 196, 0, 0.25); box-shadow: 0 0 0 1px #fff; }}
  #map {{ flex: 1; min-width: 0; }}
  #net-hint {{ display: none; background: #fff4e0; color: #7a4c00; font-size: .72rem; padding: 6px 16px; border-bottom: 1px solid #f0d7ab; }}
  .leaflet-popup-content {{ margin: 10px 12px; font-size: .78rem; line-height: 1.5; }}
  .leaflet-popup-content dl {{ display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; margin: 0; }}
  .leaflet-popup-content dt {{ color: var(--muted); }}
  .leaflet-popup-content dd {{ margin: 0; }}
  .leaflet-popup-content h3 {{ margin: 0 0 6px; font-size: .86rem; }}
  @media (max-width: 760px) {{
    #app {{ flex-direction: column; }}
    #sidebar {{ width: 100%; flex: 0 0 42vh; border-right: 0; border-bottom: 1px solid var(--line); }}
    #map {{ flex: 1; }}
  }}
</style>
</head>
<body>
<div id="app">
  <aside id="sidebar">
    <header>
      <h1>{grower_name}</h1>
      <div class="sub">{subtitle}</div>
    </header>
    <div id="net-hint">Basemap tiles could not load. Field outlines still work; check your internet connection.</div>
    <div id="tools"><button class="fit-all" id="fit-all" type="button">Fit all fields</button></div>
    <div id="fields"></div>
    <footer>
      <div class="legend"><i></i>Amber outline = selected field</div>
      Basemap: Esri World Imagery (internet required). Field polygons from pipeline boundary GeoJSON.
      Crop labels are USDA CDL class shares, not planting records.
    </footer>
  </aside>
  <div id="map"></div>
</div>
<script>
const MAP_DATA = {data_json};
</script>
<script>
(function () {{
  const farms = MAP_DATA.farms;
  const palette = {json.dumps(FARM_COLORS)};
  const HL = {json.dumps(HIGHLIGHT)};

  const map = L.map("map", {{
    zoomControl: true,
    scrollWheelZoom: true,
    doubleClickZoom: true,
    boxZoom: true,
    keyboard: true,
    touchZoom: true,
    preferCanvas: true
  }});
  map.fitBounds(MAP_DATA.bounds, {{ padding: [28, 28] }});

  const imagery = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}",
    {{
      maxNativeZoom: 19,
      maxZoom: 19,
      attribution: "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
    }}
  ).addTo(map);

  const streets = L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
    maxNativeZoom: 19,
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
  }});

  L.control.layers({{ "Satellite (Esri)": imagery, "Streets (OSM)": streets }}, {{}}, {{ position: "topright" }}).addTo(map);
  L.control.scale({{ imperial: true, metric: true }}).addTo(map);

  let tileErrors = 0;
  imagery.on("tileerror", function () {{
    if (++tileErrors === 3) {{ document.getElementById("net-hint").style.display = "block"; }}
  }});

  const layersByKey = new Map();
  const layerFarmColor = new Map();
  const geometryByKey = new Map();
  const casingByKey = new Map();
  let activeKey = null;
  let highlightGroup = null;

  // Every field is drawn twice: a white casing underneath, then the farm-coloured
  // stroke and fill on top. Over dark canopy the casing carries the outline, over
  // pale soil the dark stroke does, so no single basemap tone can swallow a field.
  const casingGroup = L.layerGroup().addTo(map);

  function fieldStyle(key, mode) {{
    const color = layerFarmColor.get(key);
    if (mode === "hover") {{
      return [
        {{ color: color, weight: HL.hoverWeight, fillColor: color, fillOpacity: HL.hoverFillOpacity }},
        {{ color: HL.casing, weight: HL.hoverCasingWeight, opacity: HL.hoverCasingOpacity, fill: false }}
      ];
    }}
    return [
      {{ color: color, weight: HL.baseWeight, fillColor: color, fillOpacity: HL.baseFillOpacity }},
      {{ color: HL.casing, weight: HL.baseCasingWeight, opacity: HL.baseCasingOpacity, fill: false }}
    ];
  }}

  function applyFieldStyle(key, mode) {{
    const styles = fieldStyle(key, mode);
    const layer = layersByKey.get(key);
    if (layer) {{ layer.setStyle(styles[0]); }}
    (casingByKey.get(key) || []).forEach(function (casing) {{ casing.setStyle(styles[1]); }});
  }}

  function esc(value) {{
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {{
      return {{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[ch];
    }});
  }}

  function popupHtml(field, farm) {{
    const rows = [
      ["Grower", esc(MAP_DATA.grower.name)],
      ["Farm", esc(farm.name)],
      ["Field ID", esc(field.field_id)]
    ];
    if (field.area_acres) rows.push(["Area", field.area_acres.toFixed(1) + " acres"]);
    const place = [field.county, field.state].filter(Boolean).map(esc).join(", ");
    if (place) rows.push(["County", place]);
    if (field.crop) rows.push(["Crop (CDL)", esc(field.crop.name) + " &middot; " + field.crop.pct.toFixed(1) + "% (" + field.crop.year + ")"]);
    if (field.source) rows.push(["Boundary", esc(field.source)]);
    return "<h3>" + esc(field.label) + "</h3><dl>" + rows.map(function (row) {{
      return "<dt>" + row[0] + "</dt><dd>" + row[1] + "</dd>";
    }}).join("") + "</dl>";
  }}

  farms.forEach(function (farm, index) {{
    const color = palette[index % palette.length];
    const group = L.featureGroup().addTo(map);
    const geojson = {{ type: "FeatureCollection", features: farm.fields.map(function (field, fieldIndex) {{
      return {{ type: "Feature", properties: {{ key: farm.slug + "/" + field.slug, farmIndex: index, fieldIndex: fieldIndex }}, geometry: field.geometry }};
    }}) }};

    L.geoJSON(geojson, {{
      style: function (feature) {{ return fieldStyle(feature.properties.key, "base")[0]; }},
      onEachFeature: function (feature, layer) {{
        const key = feature.properties.key;
        const field = farms[feature.properties.farmIndex].fields[feature.properties.fieldIndex];
        const casings = [];
        L.geoJSON(feature.geometry, {{
          interactive: false,
          style: function () {{ return fieldStyle(key, "base")[1]; }}
        }}).eachLayer(function (casing) {{
          casing.addTo(casingGroup);
          casings.push(casing);
        }});
        casingByKey.set(key, casings);

        layer.bindPopup(function () {{ return popupHtml(field, farm); }});
        layer.on("click", function () {{ setActive(key); }});
        layer.on("mouseover", function () {{
          if (activeKey !== key) {{ applyFieldStyle(key, "hover"); }}
        }});
        layer.on("mouseout", function () {{
          if (activeKey !== key) {{ applyFieldStyle(key, "base"); }}
        }});
        layersByKey.set(key, layer);
        layerFarmColor.set(key, color);
        geometryByKey.set(key, feature.geometry);
      }}
    }}).addTo(group);
  }});

  function clearHighlight() {{
    if (highlightGroup) {{ map.removeLayer(highlightGroup); highlightGroup = null; }}
  }}

  function setActive(key) {{
    activeKey = key;
    layersByKey.forEach(function (_, layerKey) {{
      applyFieldStyle(layerKey, "base");
    }});

    clearHighlight();
    if (key && geometryByKey.has(key)) {{
      const geometry = geometryByKey.get(key);
      highlightGroup = L.layerGroup().addTo(map);
      // White casing first so the amber stroke survives any basemap tone.
      L.geoJSON(geometry, {{
        interactive: false,
        style: {{ color: HL.casing, weight: HL.casingWeight, opacity: HL.casingOpacity, fill: false }}
      }}).addTo(highlightGroup);
      L.geoJSON(geometry, {{
        interactive: false,
        style: {{
          color: HL.stroke,
          weight: HL.weight,
          opacity: 1,
          fillColor: HL.fill,
          fillOpacity: HL.fillOpacity
        }}
      }}).addTo(highlightGroup);
      highlightGroup.bringToFront();
    }}

    document.querySelectorAll(".field-btn").forEach(function (btn) {{
      btn.classList.toggle("active", btn.dataset.key === key);
    }});
  }}

  const list = document.getElementById("fields");
  farms.forEach(function (farm, index) {{
    const color = palette[index % palette.length];
    const wrap = document.createElement("section");
    wrap.className = "farm-group";
    const heading = document.createElement("h2");
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.style.background = color;
    heading.appendChild(chip);
    heading.appendChild(document.createTextNode(farm.name));
    wrap.appendChild(heading);

    farm.fields.forEach(function (field) {{
      const key = farm.slug + "/" + field.slug;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "field-btn";
      btn.dataset.key = key;
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = field.label;
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = field.area_acres.toFixed(1) + " ac" + (field.crop ? " \\u00b7 " + field.crop.name : "");
      btn.appendChild(name);
      btn.appendChild(meta);
      btn.addEventListener("click", function () {{
        const layer = layersByKey.get(key);
        if (!layer) return;
        setActive(key);
        map.fitBounds(layer.getBounds(), {{ padding: [36, 36], maxZoom: 18 }});
        layer.openPopup();
      }});
      wrap.appendChild(btn);
    }});
    list.appendChild(wrap);
  }});

  document.getElementById("fit-all").addEventListener("click", function () {{
    setActive(null);
    map.fitBounds(MAP_DATA.bounds, {{ padding: [28, 28] }});
  }});
}})();
</script>
</body>
</html>
"""


def _write_grower(grower_slug: str, cdl_year: int | None) -> dict[str, Any]:
    payload = _collect_grower(grower_slug, cdl_year)
    document = _build_html(payload)
    if "data:image" in document:
        raise AssertionError("Map output must not embed raster imagery")
    size = len(document.encode("utf-8"))
    if size > 1_000_000:
        raise AssertionError(f"Map output is unexpectedly large ({size} bytes)")

    out_dir = grower_dir(grower_slug) / "webmap"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{grower_slug}_fields_map.html"
    out_path.write_text(document, encoding="utf-8")

    field_count = sum(len(farm["fields"]) for farm in payload["farms"])
    acres = round(sum(field["area_acres"] for farm in payload["farms"] for field in farm["fields"]), 1)
    manifest = {
        "grower_slug": grower_slug,
        "grower_name": payload["grower"]["name"],
        "field_count": field_count,
        "total_acres": acres,
        "farms": [
            {
                "farm_slug": farm["slug"],
                "farm_name": farm["name"],
                "field_count": len(farm["fields"]),
                "field_ids": [field["field_id"] for field in farm["fields"]],
            }
            for farm in payload["farms"]
        ],
        "output": str(out_path.relative_to(_RUNTIME_BASE)),
        "bytes": size,
        "basemap": "Esri World Imagery",
        "boundary_source": "farm boundary GeoJSON (pipeline output)",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _available_growers() -> list[str]:
    if not GROWERS_ROOT.is_dir():
        return []
    return sorted(
        path.name
        for path in GROWERS_ROOT.iterdir()
        if path.is_dir() and (path / "farms").is_dir()
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--grower",
        action="append",
        default=None,
        metavar="SLUG",
        help="Grower slug to render. Repeat for multiple growers. Defaults to all growers.",
    )
    parser.add_argument(
        "--all-growers",
        action="store_true",
        help="Render every grower found under the runtime growers root.",
    )
    parser.add_argument(
        "--cdl-year",
        type=int,
        default=None,
        help="CDL year used for the crop label. Defaults to the newest *_cdl.csv per farm.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    growers = _available_growers() if args.all_growers or not args.grower else args.grower
    if not growers:
        print("No growers with farms found under the runtime data root.", file=sys.stderr)
        return 2

    print("=" * 60)
    print("Grower interactive web map")
    print("=" * 60)
    print(f"Runtime root: {_RUNTIME_BASE}")
    print(f"Growers: {', '.join(growers)}")

    failures = 0
    for slug in growers:
        print(f"\n{slug}")
        try:
            manifest = _write_grower(slug, args.cdl_year)
        except (FileNotFoundError, ValueError) as exc:
            failures += 1
            print(f"  FAILED: {exc}")
            continue
        print(
            f"  ok  {manifest['field_count']} fields / {manifest['total_acres']:,} acres"
            f" -> {manifest['output']} ({manifest['bytes'] / 1024:.1f} KB)"
        )

    if failures:
        print(f"\n{failures} grower(s) failed", file=sys.stderr)
        return 1
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
