"""
Run every coloring algorithm on every map graph and record colors used and runtime.

Usage (from the repo root)
  python -m utils.bench                       # WA map graphs -> results/colorings.csv
  python -m utils.bench --state CA TX         # other states
  python -m utils.bench --layer county        # only the county graphs
  python -m utils.bench --repeats 51 --orders 200
  # every state's counties: Census adjacency graph (queen) + TIGER rook graph
  python -m utils.bench --state all --layer county --source tiger --mode rook --census
  # 1000 Rome graphs (same sample as ../GraphColoring) + Barabasi-Albert graphs, no maps
  python -m utils.bench --no-maps --rome 1000 --ba-n 50 100 200 500 1000 2000 --ba-m 3 \
      --ba-seeds 5 --repeats 5 --orders 10

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
fails if it disagrees with `exact` on the chromatic number. Both run under
`--exact-time-limit`; a run that hits it gets status=timeout and no color count.

`--census` adds one graph per state built straight from the Census County Adjacency File
(source=census, mode=queen). It equals TIGER + queen edge for edge on all 52 county sets.

`--rome N` adds N Rome graphs (family=rome), sampled exactly like ../GraphColoring's
bench/run_rome.py: sorted(random.Random(seed).sample(rome_paths(), N)), so both projects color
the same graphs. `--ba-n` adds Barabasi-Albert graphs nx.barabasi_albert_graph(n, m, seed) for
seeds 0..ba_seeds-1 (family=ba), named ba_n<n>_m<m>_s<seed>.
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
    "status",
]


def timed(fn, repeats):
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        out = fn()
        times.append(time.perf_counter() - t0)
    return out, statistics.median(times), min(times)


def algorithms(G, time_limit=None):
    algos = {
        name: (lambda s=s: nx.greedy_color(G, strategy=s))
        for name, s in wc.ALGORITHMS.items()
    }
    algos["exact"] = lambda: wc.exact_coloring(G, time_limit=time_limit)[0]
    algos["sat"] = lambda: wc.sat_coloring(G, time_limit=time_limit)[0]
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


def bench_graph(G, meta, repeats, orders, time_limit=None):
    G = wc.integer_labels(G)
    variants = [relabeled(G, seed) for seed in range(orders)]

    runs = {}
    for name, fn in algorithms(G, time_limit).items():
        try:
            col, med, best = timed(fn, repeats)
        except TimeoutError:  # only exact / sat take a time limit
            runs[name] = (None, None, None, [], "timeout")
            continue
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
        runs[name] = (k, med, best, spread, "ok")

    k_exact, k_sat = runs["exact"][0], runs["sat"][0]
    if k_exact is not None and k_sat is not None:
        assert k_exact == k_sat, (
            f"{meta['graph']}: exact says chi={k_exact}, SAT says chi={k_sat}"
        )
    chi = k_exact if k_exact is not None else k_sat  # None if both timed out
    run_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return [
        {
            **meta,
            "n": G.number_of_nodes(),
            "m": G.number_of_edges(),
            "algorithm": name,
            "colors": _blank(k),
            "chromatic_number": _blank(chi),
            "gap": "" if k is None or chi is None else k - chi,
            "colors_min": min(spread, default=_blank(k)),
            "colors_mean": f"{statistics.fmean(spread):.3f}" if spread else _blank(k),
            "colors_max": max(spread, default=_blank(k)),
            "orders": len(spread),
            "runtime_ms_median": "" if med is None else f"{1000 * med:.4f}",
            "runtime_ms_min": "" if best is None else f"{1000 * best:.4f}",
            "repeats": repeats if status == "ok" else 0,
            "run_at": run_at,
            "networkx": nx.__version__,
            "status": status,
        }
        for name, (k, med, best, spread, status) in runs.items()
    ]


def _blank(x):
    return "" if x is None else x


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


def census_graphs(states):
    """County graphs straight from the Census County Adjacency File (queen rule, no geometry)."""
    for state in states:
        meta = {
            "graph": f"{state.lower()}_county_census_queen",
            "family": "map",
            "state": state,
            "layer": "county",
            "source": "census",
            "mode": "queen",
            "min_shared_m": 0.0,
            "snap_m": 0.0,
        }
        yield wc.census_county_graph(state), meta


SIBLING_SRC = Path("..") / "GraphColoring" / "src"  # CS 5800 project: owns the Rome loader


def rome_sample(count, seed=0):
    """The same reproducible Rome sample as ../GraphColoring/bench/run_rome.py."""
    import sys

    if str(SIBLING_SRC) not in sys.path:
        sys.path.insert(0, str(SIBLING_SRC))
    from gcolor.loaders import rome_paths

    paths = rome_paths()
    if count >= len(paths):
        return paths
    return sorted(random.Random(seed).sample(paths, count))


def rome_graphs(count, seed=0):
    for path in rome_sample(count, seed):
        G = nx.Graph(nx.read_graphml(path))  # undirected, simple
        G.remove_edges_from(list(nx.selfloop_edges(G)))
        meta = {
            "graph": f"rome_{path.stem}",
            "family": "rome",
            "state": "",
            "layer": "",
            "source": f"rome_sample{count}_seed{seed}",
            "mode": "",
            "min_shared_m": "",
            "snap_m": "",
        }
        yield G, meta


def ba_graphs(sizes, m, seeds):
    for n in sizes:
        for seed in range(seeds):
            meta = {
                "graph": f"ba_n{n}_m{m}_s{seed}",
                "family": "ba",
                "state": "",
                "layer": "",
                "source": f"barabasi_albert_m{m}",
                "mode": "",
                "min_shared_m": "",
                "snap_m": "",
            }
            yield nx.barabasi_albert_graph(n, m, seed=seed), meta


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
    ap.add_argument(
        "--state", choices=["all", *sorted(wc.STATES)], nargs="+", default=["WA"],
        help="'all' = 50 states + DC + PR",
    )
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
    ap.add_argument(
        "--census", action="store_true",
        help="also bench each state's Census adjacency county graph",
    )
    ap.add_argument(
        "--exact-time-limit", type=float, default=60.0,
        help="seconds per exact / sat call; slower runs are recorded as status=timeout",
    )
    ap.add_argument("--no-maps", action="store_true", help="skip the map graphs")
    ap.add_argument("--rome", type=int, default=0, help="number of Rome graphs to sample")
    ap.add_argument("--rome-seed", type=int, default=0)
    ap.add_argument("--ba-n", type=int, nargs="*", default=[], help="Barabasi-Albert sizes")
    ap.add_argument("--ba-m", type=int, default=3, help="edges added per new BA node")
    ap.add_argument("--ba-seeds", type=int, default=5, help="BA graphs per size (seeds 0..k-1)")
    args = ap.parse_args()
    states = list(wc.STATES) if "all" in args.state else args.state

    graphs = iter(()) if args.no_maps else map_graphs(
        states, args.layer, args.source, args.mode, args.min_shared_m, args.snap_m
    )
    if args.census and not args.no_maps:
        graphs = itertools.chain(census_graphs(states), graphs)
    if args.rome:
        graphs = itertools.chain(graphs, rome_graphs(args.rome, args.rome_seed))
    if args.ba_n:
        graphs = itertools.chain(graphs, ba_graphs(args.ba_n, args.ba_m, args.ba_seeds))

    rows = []
    for G, meta in graphs:
        graph_rows = bench_graph(G, meta, args.repeats, args.orders, args.exact_time_limit)
        rows += graph_rows
        summary = ", ".join(
            f"{r['algorithm']}={r['colors']}[{r['colors_min']}-{r['colors_max']}]"
            if r["status"] == "ok"
            else f"{r['algorithm']}=TIMEOUT"
            for r in graph_rows
        )
        print(
            f"{meta['graph']:<24} n={G.number_of_nodes():<4} m={G.number_of_edges():<5} {summary}",
            flush=True,
        )
    write_results(rows)
    print(f"wrote {len(rows)} rows -> {RESULTS}")


if __name__ == "__main__":
    main()
