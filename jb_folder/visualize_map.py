"""Draw the county graph coloring as a filled US county map (needs numpy and matplotlib).

County outlines come from plotly's public county GeoJSON, downloaded once into data/geo/.
"""
import json
import os
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
GEO_DIR = os.path.join(HERE, "data", "geo")
GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
GEOJSON_PATH = os.path.join(GEO_DIR, os.path.basename(GEOJSON_URL))

# Non-continental state FIPS: AK, HI, territories.
EXCLUDED_STATES = {"02", "15", "60", "66", "69", "72", "78"}

# Same county, different FIPS code: graph code -> code in the geometry file.
# Oglala Lakota SD is 46102 in our location data but 46113 (Shannon County) in the outlines.
FIPS_GEOMETRY_ALIASES = {"46102": "46113"}

# Connecticut: our data uses the 9 planning regions (09110-09190) but the outlines use the old
# 8 counties, so those polygons have no color and are drawn light gray (as is 51515, Bedford VA).

# Categorical palette (first five are well separated; index modulo len for larger colorings).
PALETTE = [
    "#4E79A7",  # blue
    "#F28E2B",  # orange
    "#59A14F",  # green
    "#E15759",  # red
    "#B07AA1",  # purple
    "#EDC948",  # yellow
    "#76B7B2",  # teal
    "#FF9DA7",  # pink
    "#9C755F",  # brown
    "#86BCB6",  # light teal
]
UNCOLORED_FACE = "#DDDDDD"
UNCOLORED_EDGE = "#999999"

_geometry_cache = None


def albers_usa(lon, lat):
    """Project lon/lat degrees with the Albers equal-area conic used for US maps."""
    lon = np.radians(np.asarray(lon, dtype=float))
    lat = np.radians(np.asarray(lat, dtype=float))
    phi1, phi2 = np.radians(29.5), np.radians(45.5)
    phi0, lam0 = np.radians(37.5), np.radians(-96.0)
    n = (np.sin(phi1) + np.sin(phi2)) / 2.0
    c = np.cos(phi1) ** 2 + 2 * n * np.sin(phi1)
    rho0 = np.sqrt(c - 2 * n * np.sin(phi0)) / n
    rho = np.sqrt(c - 2 * n * np.sin(lat)) / n
    theta = n * (lon - lam0)
    return rho * np.sin(theta), rho0 - rho * np.cos(theta)


def _download():
    os.makedirs(GEO_DIR, exist_ok=True)
    req = urllib.request.Request(GEOJSON_URL, headers={"User-Agent": "Mozilla/5.0 (county-map-script)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    json.loads(data)  # validate it is JSON before caching
    tmp = GEOJSON_PATH + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, GEOJSON_PATH)


def load_county_geometry():
    """Return {fips: [outline as an (N,2) array, ...]} for continental counties."""
    global _geometry_cache
    if _geometry_cache is not None:
        return _geometry_cache
    if not os.path.exists(GEOJSON_PATH):
        _download()
    with open(GEOJSON_PATH) as f:
        gj = json.load(f)
    geom = {}
    for feat in gj["features"]:
        fips = str(feat["id"]).zfill(5)
        if fips[:2] in EXCLUDED_STATES:
            continue
        g = feat["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        rings = []
        for poly in polys:
            ring = np.asarray(poly[0], dtype=float)
            x, y = albers_usa(ring[:, 0], ring[:, 1])
            rings.append(np.column_stack([x, y]))
        geom[fips] = rings
    _geometry_cache = geom
    return geom


def match_summary(coloring):
    """Return (graph FIPS without polygon, polygon FIPS without coloring)."""
    geom = load_county_geometry()
    resolve = lambda k: k if k in geom else FIPS_GEOMETRY_ALIASES.get(k)
    no_poly = sorted(k for k in coloring if resolve(k) not in geom)
    used = {resolve(k) for k in coloring}
    no_color = sorted(set(geom) - used)
    return no_poly, no_color


def draw_county_map(coloring, title="", output_path=None, show=True):
    """Fill each county polygon with its color; uncolored polygons are light gray."""
    import matplotlib
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from matplotlib.patches import Patch

    geom = load_county_geometry()
    alias_inv = {v: k for k, v in FIPS_GEOMETRY_ALIASES.items()}

    colored_polys, colored_idx, gray_polys = [], [], []
    for fips, rings in geom.items():
        node = fips if fips in coloring else alias_inv.get(fips)
        if node is not None and node in coloring:
            for r in rings:
                colored_polys.append(r)
                colored_idx.append(int(coloring[node]))
        else:
            gray_polys.extend(rings)

    fig, ax = plt.subplots(figsize=(14, 9))
    if gray_polys:
        ax.add_collection(PolyCollection(gray_polys, facecolors=UNCOLORED_FACE,
                                         edgecolors=UNCOLORED_EDGE, linewidths=0.2))
    faces = [PALETTE[i % len(PALETTE)] for i in colored_idx]
    ax.add_collection(PolyCollection(colored_polys, facecolors=faces,
                                     edgecolors="white", linewidths=0.15))

    allpts = np.vstack([r for rings in geom.values() for r in rings])
    ax.set_xlim(allpts[:, 0].min() - 0.01, allpts[:, 0].max() + 0.01)
    ax.set_ylim(allpts[:, 1].min() - 0.01, allpts[:, 1].max() + 0.01)
    ax.set_aspect("equal")
    ax.axis("off")

    counts = {}
    for node, c in coloring.items():
        counts[int(c)] = counts.get(int(c), 0) + 1
    handles = [Patch(facecolor=PALETTE[c % len(PALETTE)], edgecolor="none",
                     label=f"Color {c} ({counts[c]})") for c in sorted(counts)]
    if gray_polys:
        handles.append(Patch(facecolor=UNCOLORED_FACE, edgecolor=UNCOLORED_EDGE,
                             label="No color (no matching graph node)"))
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=9)
    if title:
        ax.set_title(title, fontsize=14)
    fig.tight_layout()
    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)
