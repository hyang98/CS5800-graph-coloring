"""
Draw every state's county map colored by each of 8 algorithms, one PNG per (state, algorithm).

Usage (from the repo root)
  python -m utils.state_maps                 # all states in STATES (50 + DC + PR)
  python -m utils.state_maps --state WA TX   # a subset

Graph: Census County Adjacency File (2024), i.e. queen contiguity (counties touching at a
  corner are neighbours), relabeled with `integer_labels` so results are reproducible.
Geometry: TIGER/Line 2024 county boundaries (the graph Census adjacency equals on all 52 maps).
  Drawn in EPSG:5070, except AK (3338), HI (32604) and PR (32161) so they aren't distorted.
  The projection only affects the picture, not the graph.

Algorithms (the 7 distinct networkx greedy strategies + an exact optimum):
  largest_first, random_sequential (seed 0), smallest_last, independent_set,
  connected_sequential_bfs, connected_sequential_dfs, saturation_largest_first (DSATUR),
  exact (exact_coloring, falling back to sat_coloring if it hits --time-limit)

Writes
  results/state_maps/<ST>/<ST>_<algorithm>_map.png   e.g. AL/AL_largest_first_map.png
  results/state_maps/colors.csv                 state, algorithm, colors, chi, method of chi
"""

import argparse
import csv
from pathlib import Path

import networkx as nx

from utils import color as wc

OUT = Path("results") / "state_maps"
TIGER_URL = wc.SOURCES["county"]["tiger"]
DISPLAY_CRS = {"AK": 3338, "HI": 32604, "PR": 32161}
PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#B279A2",
           "#EECA3B", "#72B7B2", "#9D755D", "#FF9DA6", "#79706E"]  # fmt: skip
INK, MUTED = "#222222", "#666666"


def _random_sequential(G, colors):
    return nx.coloring.strategy_random_sequential(G, colors, seed=0)


GREEDY = {
    "largest_first": "largest_first",
    "random_sequential": _random_sequential,
    "smallest_last": "smallest_last",
    "independent_set": "independent_set",
    "connected_sequential_bfs": "connected_sequential_bfs",
    "connected_sequential_dfs": "connected_sequential_dfs",
    "saturation_largest_first": "saturation_largest_first",
}
ALGORITHMS = [*GREEDY, "exact"]
LABEL = {"saturation_largest_first": "saturation_largest_first (DSATUR)",
         "random_sequential": "random_sequential (seed 0)"}  # fmt: skip


def load_tiger():
    """All US counties from the cached TIGER shapefile (read once, filtered per state)."""
    import geopandas as gpd

    local = wc.DATA_DIR / Path(TIGER_URL).name
    if not local.exists():
        wc.fetch_layer("county", "tiger", "WA")  # downloads into DATA_DIR
    return gpd.read_file(local)[["STATEFP", "GEOID", "NAME", "geometry"]]


def colorings(G, time_limit):
    """{algorithm: coloring} on integer-labelled G, plus chi and how chi was found."""
    out = {a: nx.greedy_color(G, strategy=s) for a, s in GREEDY.items()}
    try:
        out["exact"], chi = wc.exact_coloring(G, time_limit=time_limit)
        how = "exact"
    except TimeoutError:
        print(f"  exact_coloring timed out after {time_limit}s; using sat_coloring")
        out["exact"], chi = wc.sat_coloring(G, time_limit=time_limit)
        how = "sat"
    for a, col in out.items():
        bad = wc.is_proper(G, col)
        assert not bad, f"{a} is not a proper coloring: {bad[:3]}"
    return out, chi, how


def draw(gdf, coloring, state, algo, k, chi, path):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    if k > len(PALETTE):
        raise ValueError(f"{state} {algo}: {k} colors but palette has {len(PALETTE)}")
    cls = gdf["GEOID"].map(coloring)
    fig, ax = plt.subplots(figsize=(10, 7.5))
    gdf.plot(color=cls.map(lambda c: PALETTE[c]), edgecolor="white", linewidth=0.5, ax=ax)
    ax.set_axis_off()
    ax.set_aspect("equal")

    gap = k - chi
    verdict = "optimal" if gap == 0 else f"{gap} above χ"
    ax.set_title(f"{state} counties: {LABEL.get(algo, algo)}", loc="left", fontsize=13,
                 color=INK, pad=22)
    ax.text(0, 1.01, f"{k} colors, χ = {chi} ({verdict}) · {len(gdf)} counties · "
            "Census adjacency (queen), TIGER 2024 boundaries",
            transform=ax.transAxes, fontsize=9, color=MUTED, va="bottom")

    counts = cls.value_counts()
    handles = [Patch(facecolor=PALETTE[c], edgecolor="none",
                     label=f"color {c + 1}: {counts.get(c, 0)} "
                     + ("county" if counts.get(c, 0) == 1 else "counties"))
               for c in range(k)]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False,
              fontsize=9, title="color class", title_fontsize=9, alignment="left")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--state", nargs="+", default=list(wc.STATES),
                   help="state abbreviations (default: every key of STATES)")
    p.add_argument("--time-limit", type=float, default=60.0,
                   help="seconds for exact_coloring before falling back to SAT")
    args = p.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    OUT.mkdir(parents=True, exist_ok=True)
    tiger = load_tiger()
    rows = []
    for state in args.state:
        fips = wc.STATES[state]
        gdf = tiger[tiger["STATEFP"] == fips].to_crs(DISPLAY_CRS.get(state, 5070))
        G = wc.integer_labels(wc.census_county_graph(state))
        geoid = nx.get_node_attributes(G, "geoid")
        missing = set(gdf["GEOID"]) ^ set(geoid.values())
        assert not missing, f"{state}: TIGER and Census disagree on counties {sorted(missing)}"

        cols, chi, how = colorings(G, args.time_limit)
        (OUT / state).mkdir(exist_ok=True)
        for algo in ALGORITHMS:
            by_geoid = {geoid[n]: c for n, c in cols[algo].items()}
            k = max(by_geoid.values()) + 1 if by_geoid else 0
            draw(gdf, by_geoid, state, algo, k, chi, OUT / state / f"{state}_{algo}_map.png")
            rows.append({"state": state, "algorithm": algo, "colors": k, "chi": chi,
                         "chi_method": how, "n": G.number_of_nodes(),
                         "m": G.number_of_edges()})
        ks = " ".join(f"{a}={max(cols[a].values()) + 1}" for a in ALGORITHMS)
        print(f"{state}: n={G.number_of_nodes()} chi={chi} | {ks}")

    # keep other states' rows so a --state subset run doesn't drop them
    path = OUT / "colors.csv"
    if path.exists():
        with open(path, newline="") as f:
            done = set(args.state)
            rows = [r for r in csv.DictReader(f) if r["state"] not in done] + rows
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(args.state) * len(ALGORITHMS)} maps to {OUT}/<state>/")


if __name__ == "__main__":
    main()
