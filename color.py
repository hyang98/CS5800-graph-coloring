"""
Washington map -> adjacency graph -> graph coloring -> compare with a real map.

Layers
  county : 39 WA counties
  cd     : 10 WA congressional districts (119th Congress, 2021 commission map)

Usage
  pip install geopandas networkx matplotlib requests
  python wa_map_coloring.py --layer county --source tiger
  python wa_map_coloring.py --layer cd --source cb
  python wa_map_coloring.py --layer county --reference ref_colors.json
  python wa_map_coloring.py --overlay          # which counties are split across districts

Outputs go to ./out/<layer>_<source>/ :
  edges.csv, graph.graphml, graph.json, map_<algo>.png, graph_overlay.png, report.json
"""

import argparse
import itertools
import json
from pathlib import Path

import networkx as nx

WA_FIPS = "53"
DATA_DIR = Path("data")

# "tiger" = TIGER/Line: full legal boundaries, extends into water (Puget Sound,
#           Columbia River). Island counties touch their neighbours across water.
# "cb"    = Cartographic Boundary 1:500k: clipped to shoreline, generalized.
#           San Juan County becomes an isolated node (no land border).
# If a URL 404s, browse the parent directory on www2.census.gov for the newest vintage.
SOURCES = {
    "county": {
        "tiger": "https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip",
        "cb": "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_500k.zip",
        "id_col": "GEOID",
        "name_col": "NAME",
    },
    "cd": {
        "tiger": "https://www2.census.gov/geo/tiger/TIGER2024/CD/tl_2024_53_cd119.zip",
        "cb": "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_cd119_500k.zip",
        "id_col": "GEOID",
        "name_col": "CD119FP",
    },
}

ALGORITHMS = {
    "largest_first": "largest_first",
    "dsatur": "saturation_largest_first",
    "smallest_last": "smallest_last",
    "independent_set": "independent_set",
}

PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#B279A2", "#9D755D", "#72B7B2"]


# ----------------------------------------------------------------------------
# 1. Fetch
# ----------------------------------------------------------------------------
def fetch_layer(layer: str, source: str):
    import geopandas as gpd
    import requests

    url = SOURCES[layer][source]
    DATA_DIR.mkdir(exist_ok=True)
    local = DATA_DIR / Path(url).name
    if not local.exists():
        print(f"Downloading {url}")
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        local.write_bytes(r.content)
    gdf = gpd.read_file(local)
    gdf = gdf[gdf["STATEFP"] == WA_FIPS].copy()
    if layer == "cd":
        gdf = gdf[gdf["CD119FP"] != "ZZ"]
        gdf["CD119FP"] = "CD-" + gdf["CD119FP"].astype(str).str.lstrip("0")
    # Equal-area projection in metres so shared-border lengths are meaningful
    return gdf.to_crs(5070).reset_index(drop=True)


# ----------------------------------------------------------------------------
# 2. Map -> graph
# ----------------------------------------------------------------------------
def build_graph(gdf, id_col, name_col, mode="rook", min_shared_m=100.0, snap_m=0.0):
    """
    Node = region, edge = regions share a border.
      rook  : must share a border segment >= min_shared_m metres (the map-coloring rule;
              regions meeting at a single point may share a color)
      queen : any contact, including a single point
      snap_m: buffer each polygon by this many metres first, to close digitizing slivers
    """
    geoms = gdf.geometry.buffer(snap_m) if snap_m > 0 else gdf.geometry
    sindex = geoms.sindex
    G = nx.Graph()
    for _, row in gdf.iterrows():
        pt = row.geometry.representative_point()
        G.add_node(row[id_col], name=str(row[name_col]), x=pt.x, y=pt.y)

    ids = gdf[id_col].tolist()
    for i, geom in enumerate(geoms):
        for j in sindex.query(geom, predicate="intersects"):
            if j <= i:
                continue
            shared = gdf.geometry[i].boundary.intersection(gdf.geometry[j].boundary)
            length = shared.length
            if snap_m > 0 and length == 0:
                # with snapping, measure the overlap of the buffered shapes instead
                length = geom.intersection(geoms[j]).area / max(2 * snap_m, 1e-9)
            if mode == "queen" or length >= min_shared_m:
                G.add_edge(ids[i], ids[j], shared_km=round(length / 1000, 3))
    return G


def export_graph(G, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    with open(outdir / "edges.csv", "w") as f:
        f.write("source,target,source_name,target_name,shared_km\n")
        for u, v, d in G.edges(data=True):
            f.write(
                f"{u},{v},{G.nodes[u]['name']},{G.nodes[v]['name']},{d.get('shared_km', '')}\n"
            )
    nx.write_graphml(G, outdir / "graph.graphml")
    with open(outdir / "graph.json", "w") as f:
        json.dump(nx.node_link_data(G, edges="links"), f, indent=1)


# ----------------------------------------------------------------------------
# 3. Coloring
# ----------------------------------------------------------------------------
def is_proper(G, coloring):
    return [(u, v) for u, v in G.edges if coloring[u] == coloring[v]]


def heuristic_colorings(G):
    return {name: nx.greedy_color(G, strategy=s) for name, s in ALGORITHMS.items()}


def exact_coloring(G):
    """Minimum coloring by DSatur-ordered backtracking. Fine for maps (< ~200 nodes, planar)."""
    if G.number_of_nodes() == 0:
        return {}, 0
    lower = max(len(c) for c in nx.find_cliques(G))
    for k in range(lower, G.number_of_nodes() + 1):
        sol = _try_k(G, k)
        if sol is not None:
            return sol, k
    raise RuntimeError("unreachable")


def _try_k(G, k):
    colors = {}

    def pick():
        best, key = None, None
        for v in G:
            if v in colors:
                continue
            sat = len({colors[u] for u in G[v] if u in colors})
            cand = (sat, G.degree(v))
            if key is None or cand > key:
                best, key = v, cand
        return best

    def rec():
        v = pick()
        if v is None:
            return True
        used = {colors[u] for u in G[v] if u in colors}
        # symmetry breaking: never open more than one new color at a time
        max_open = max(colors.values(), default=-1) + 1
        for c in range(min(k, max_open + 1)):
            if c not in used:
                colors[v] = c
                if rec():
                    return True
                del colors[v]
        return False

    return dict(colors) if rec() else None


def canonical_partition(coloring):
    classes = {}
    for v, c in coloring.items():
        classes.setdefault(c, set()).add(v)
    return frozenset(frozenset(s) for s in classes.values())


# ----------------------------------------------------------------------------
# 4. Reverse-engineer a reference map's coloring
# ----------------------------------------------------------------------------
def analyze_reference(G, ref, results):
    """
    ref: {node_id_or_name: any color label}  (hex codes, "blue", etc.)
    Reports: is it a proper coloring, how many colors vs. the chromatic number,
    whether any of our algorithms produced the same partition (colors up to relabeling),
    and whether plain greedy reproduces it under some vertex ordering.
    """
    name_to_id = {d["name"]: n for n, d in G.nodes(data=True)}
    ref = {name_to_id.get(k, k): v for k, v in ref.items()}
    missing = [n for n in G if n not in ref]
    if missing:
        return {
            "error": f"reference is missing {len(missing)} regions",
            "missing": missing,
        }

    labels = sorted(set(ref.values()))
    conflicts = is_proper(G, ref)
    report = {
        "num_colors_used": len(labels),
        "chromatic_number": results["exact"]["k"],
        "proper": not conflicts,
        "conflicting_borders": [
            (G.nodes[u]["name"], G.nodes[v]["name"]) for u, v in conflicts
        ],
        "same_partition_as": [
            a
            for a, r in results.items()
            if canonical_partition(r["coloring"]) == canonical_partition(ref)
        ],
    }

    # Greedy reproduces a coloring exactly iff, for some ordering of the color classes,
    # every vertex in class i touches all classes 0..i-1 (a "Grundy" coloring).
    report["greedy_reproducible"] = False
    if not conflicts and len(labels) <= 7:
        for perm in itertools.permutations(labels):
            rank = {lab: i for i, lab in enumerate(perm)}
            order = sorted(G, key=lambda v: rank[ref[v]])
            g = nx.greedy_color(G, strategy=lambda _G, _c: iter(order))
            if all(g[v] == rank[ref[v]] for v in G):
                report["greedy_reproducible"] = True
                report["greedy_class_order"] = list(perm)
                break
    return report


# ----------------------------------------------------------------------------
# 5. Draw
# ----------------------------------------------------------------------------
def draw_map(gdf, id_col, coloring, title, path):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 7))
    gdf.plot(
        color=gdf[id_col].map(lambda i: PALETTE[coloring[i] % len(PALETTE)]),
        edgecolor="white",
        linewidth=0.8,
        ax=ax,
    )
    ax.set_title(title)
    ax.set_axis_off()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def draw_overlay(gdf, G, coloring, path):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 7))
    gdf.plot(color="#eeeeee", edgecolor="#999999", linewidth=0.6, ax=ax)
    pos = {n: (d["x"], d["y"]) for n, d in G.nodes(data=True)}
    nx.draw_networkx_edges(G, pos, ax=ax, width=1.2, edge_color="#333333")
    nx.draw_networkx_nodes(
        G,
        pos,
        ax=ax,
        node_size=140,
        node_color=[PALETTE[coloring[n] % len(PALETTE)] for n in G],
    )
    nx.draw_networkx_labels(
        G, pos, ax=ax, font_size=6, labels={n: d["name"] for n, d in G.nodes(data=True)}
    )
    ax.set_title("Dual graph: regions as nodes, shared borders as edges")
    ax.set_axis_off()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------
# 6. County x district overlay
# ----------------------------------------------------------------------------
def county_district_overlay(source, min_area_km2=1.0):
    import geopandas as gpd

    counties = fetch_layer("county", source)[["NAME", "geometry"]]
    cds = fetch_layer("cd", source)[["CD119FP", "geometry"]]
    pieces = gpd.overlay(counties, cds, how="intersection", keep_geom_type=True)
    pieces["km2"] = pieces.area / 1e6
    pieces = pieces[pieces["km2"] >= min_area_km2]
    split = pieces.groupby("NAME")["CD119FP"].apply(sorted)
    return {c: d for c, d in split.items() if len(d) > 1}


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer", choices=["county", "cd"], default="county")
    ap.add_argument("--source", choices=["tiger", "cb"], default="tiger")
    ap.add_argument("--mode", choices=["rook", "queen"], default="rook")
    ap.add_argument("--min-shared-m", type=float, default=100.0)
    ap.add_argument("--snap-m", type=float, default=0.0)
    ap.add_argument("--reference", help="JSON {region name or GEOID: color label}")
    ap.add_argument("--overlay", action="store_true")
    args = ap.parse_args()

    if args.overlay:
        print(json.dumps(county_district_overlay(args.source), indent=1))
        return

    cfg = SOURCES[args.layer]
    gdf = fetch_layer(args.layer, args.source)
    G = build_graph(
        gdf, cfg["id_col"], cfg["name_col"], args.mode, args.min_shared_m, args.snap_m
    )
    outdir = Path("out") / f"{args.layer}_{args.source}"
    export_graph(G, outdir)

    results = {}
    for name, col in heuristic_colorings(G).items():
        results[name] = {"coloring": col, "k": len(set(col.values()))}
    col, k = exact_coloring(G)
    results["exact"] = {"coloring": col, "k": k}

    report = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "isolated": [G.nodes[n]["name"] for n in nx.isolates(G)],
        "planar": nx.check_planarity(G)[0],
        "max_degree": max(dict(G.degree).values()),
        "colors_by_algorithm": {a: r["k"] for a, r in results.items()},
    }
    for a, r in results.items():
        assert not is_proper(G, r["coloring"]), a
        draw_map(
            gdf,
            cfg["id_col"],
            r["coloring"],
            f"WA {args.layer} — {a} ({r['k']} colors)",
            outdir / f"map_{a}.png",
        )
    draw_overlay(gdf, G, results["exact"]["coloring"], outdir / "graph_overlay.png")

    if args.reference:
        report["reference"] = analyze_reference(
            G, json.loads(Path(args.reference).read_text()), results
        )

    (outdir / "report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
