"""
Run every coloring algorithm on every map graph and record colors used and runtime.

Usage
  python bench.py                       # all map graphs -> results/colorings.csv
  python bench.py --state CA TX         # other states
  python bench.py --layer county        # only the county graphs
  python bench.py --repeats 51 --orders 200

One row per (graph, algorithm). Rows for the graphs this run covers are replaced; rows for
other graphs (e.g. Rome or BA added later) are kept. Runtime is the coloring call only,
not download or graph construction.

Determinism: networkx breaks some ties by iterating sets, and string node ids (GEOIDs) hash
differently in every Python process, so smallest_last / independent_set could change between
runs. Nodes are therefore relabeled 0..n-1 in sorted-id order before coloring; `colors` is the
result on that labeling. `colors_min/mean/max` cover `orders` seeded random relabelings, which
measures how much each algorithm depends on tie-breaking. `exact` and `sat` are skipped there (orders = 0):
it is optimal on every labeling, and its backtracking time is heavy-tailed in the labeling
(TX counties: ~0.02 s on most orders, 3 s on some), which made the sweep impractically slow.

`sat` is a second, independent exact method (SAT encoding, Glucose 4 via python-sat). The run
fails if it disagrees with `exact` on the chromatic number.
"""

import argparse
import csv
import itertools
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

import utils.color as wc

RESULTS = Path("results") / "colorings.csv"

FIELDS = [
    "graph",
    "family",
    "state",
    "layer",
    "source",
    "mode",
    "min_shared_m",
    "snap_m",
    "n",
    "m",
    "algorithm",
    "colors",
    "chromatic_number",
    "gap",
    "colors_min",
    "colors_mean",
    "colors_max",
    "orders",
    "runtime_ms_median",
    "runtime_ms_min",
    "repeats",
    "run_at",
    "networkx",
]


def timed(fn, repeats):
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        out = fn()
        times.append(time.perf_counter() - t0)
    return out, statistics.median(times), min(times)


def algorithms(G):
    algos = {
        name: (lambda s=s: nx.greedy_color(G, strategy=s))
        for name, s in wc.ALGORITHMS.items()
    }
    algos["exact"] = lambda: wc.exact_coloring(G)[0]
    algos["sat"] = lambda: wc.sat_coloring(G)[0]
    return algos


EXACT = {"exact", "sat"}  # optimal methods: no relabeling sweep, must agree on chi


def relabeled(G, seed):
    """Same graph with node ids randomly permuted, inserted in id order."""
    nodes = list(G)
    perm = random.Random(seed).sample(range(len(nodes)), len(nodes))
    H = nx.relabel_nodes(G, dict(zip(nodes, perm)))
    out = nx.Graph()
    out.add_nodes_from(sorted(H))
    out.add_edges_from(H.edges)
    return out


def count_colors(G, col, label):
    assert not wc.is_proper(G, col), f"{label} produced a conflict"
    return len(set(col.values()))


def bench_graph(G, meta, repeats, orders):
    G = wc.integer_labels(G)
    variants = [relabeled(G, seed) for seed in range(orders)]

    runs = {}
    for name, fn in algorithms(G).items():
        col, med, best = timed(fn, repeats)
        k = count_colors(G, col, f"{meta['graph']}: {name}")
        spread = (
            []
            if name in EXACT
            else [
                count_colors(
                    H, algorithms(H)[name](), f"{meta['graph']}: {name}, order {i}"
                )
                for i, H in enumerate(variants)
            ]
        )
        runs[name] = (k, med, best, spread)

    chi = runs["exact"][0]
    assert runs["sat"][0] == chi, (
        f"{meta['graph']}: exact says chi={chi}, SAT says chi={runs['sat'][0]}"
    )
    run_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return [
        {
            **meta,
            "n": G.number_of_nodes(),
            "m": G.number_of_edges(),
            "algorithm": name,
            "colors": k,
            "chromatic_number": chi,
            "gap": k - chi,
            "colors_min": min(spread, default=k),
            "colors_mean": f"{statistics.fmean(spread):.3f}" if spread else k,
            "colors_max": max(spread, default=k),
            "orders": len(spread),
            "runtime_ms_median": f"{1000 * med:.4f}",
            "runtime_ms_min": f"{1000 * best:.4f}",
            "repeats": repeats,
            "run_at": run_at,
            "networkx": nx.__version__,
        }
        for name, (k, med, best, spread) in runs.items()
    ]


def map_graphs(states, layers, sources, modes, min_shared_m, snap_m):
    for state, layer, source in itertools.product(states, layers, sources):
        cfg = wc.SOURCES[layer]
        gdf = wc.fetch_layer(layer, source, state)
        for mode in modes:
            G = wc.build_graph(
                gdf, cfg["id_col"], cfg["name_col"], mode, min_shared_m, snap_m
            )
            meta = {
                "graph": f"{state.lower()}_{layer}_{source}_{mode}",
                "family": "map",
                "state": state,
                "layer": layer,
                "source": source,
                "mode": mode,
                "min_shared_m": min_shared_m,
                "snap_m": snap_m,
            }
            yield G, meta


def write_results(rows):
    """Replace rows for the graphs in `rows`, keep everything else."""
    done = {r["graph"] for r in rows}
    old = []
    if RESULTS.exists():
        with open(RESULTS, newline="") as f:
            old = [r for r in csv.DictReader(f) if r["graph"] not in done]
    RESULTS.parent.mkdir(exist_ok=True)
    with open(RESULTS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(old + rows, key=lambda r: (r["graph"], r["algorithm"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", choices=sorted(wc.STATES), nargs="+", default=["WA"])
    ap.add_argument(
        "--layer", choices=["county", "cd"], nargs="+", default=["county", "cd"]
    )
    ap.add_argument(
        "--source", choices=["tiger", "cb"], nargs="+", default=["tiger", "cb"]
    )
    ap.add_argument(
        "--mode", choices=["rook", "queen"], nargs="+", default=["rook", "queen"]
    )
    ap.add_argument("--min-shared-m", type=float, default=100.0)
    ap.add_argument("--snap-m", type=float, default=0.0)
    ap.add_argument(
        "--repeats", type=int, default=21, help="timing repeats per algorithm"
    )
    ap.add_argument(
        "--orders", type=int, default=50, help="random relabelings for tie-break spread"
    )
    args = ap.parse_args()

    rows = []
    for G, meta in map_graphs(
        args.state, args.layer, args.source, args.mode, args.min_shared_m, args.snap_m
    ):
        graph_rows = bench_graph(G, meta, args.repeats, args.orders)
        rows += graph_rows
        summary = ", ".join(
            f"{r['algorithm']}={r['colors']}[{r['colors_min']}-{r['colors_max']}]"
            for r in graph_rows
        )
        print(
            f"{meta['graph']:<22} n={G.number_of_nodes():<3} m={G.number_of_edges():<4} {summary}"
        )
    write_results(rows)
    print(f"wrote {len(rows)} rows -> {RESULTS}")


if __name__ == "__main__":
    main()
