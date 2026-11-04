"""
Structural metrics for every state's county graph, joined with the coloring benchmark, to
explain what drives each algorithm's runtime.

Usage (from the repo root, after the all-states bench run)
  python -m utils.bench --state all --layer county --source tiger --mode rook --census
  python -m utils.graph_metrics                     # -> results/county_metrics.csv + figures
  python -m utils.graph_metrics --probe-orders 0    # skip the vertex-order probe (faster)
  python -m utils.graph_metrics --family rome       # -> results/rome_metrics.csv (1000 Rome graphs)
  python -m utils.graph_metrics --family ba --probe-limit 10   # -> results/ba_metrics.csv

The Rome and BA graphs are the ones `bench.py --rome 1000 --ba-n ...` colored (same sample,
sizes, m and seeds by default); their runtimes are joined from results/colorings.csv.

Graphs are the same ones bench.py colors: the Census adjacency graph (queen) and the TIGER rook
graph (shared border >= 100 m) for 50 states + DC + PR, relabeled with integer_labels.

Search effort is recorded as counts, which don't depend on the machine:
  exact_nodes_*   backtracking search-tree nodes per k (exact_coloring(stats=...))
  sat_conflicts   SAT solver conflicts summed over all k (sat_coloring(stats=...))
The probe reruns exact_coloring on `--probe-orders` seeded random relabelings (bench.relabeled)
with a short time limit, to measure how much its effort depends on vertex order.
"""

import argparse
import statistics
import time
from pathlib import Path

import networkx as nx
import pandas as pd

import utils.bench as bench
import utils.color as wc

RESULTS = Path("results")
METRICS = RESULTS / "county_metrics.csv"
CORR = RESULTS / "county_runtime_correlations.csv"
FIGS = RESULTS / "figures"

ALGOS = ["largest_first", "dsatur", "smallest_last", "independent_set", "exact", "sat"]
# Categorical slots 1-6 of the dataviz reference palette (validated, light surface). Three
# slots are under 3:1 contrast on white, so every series also gets its own marker + legend.
COLORS = dict(zip(ALGOS, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]))
MARKERS = dict(zip(ALGOS, ["o", "s", "^", "v", "D", "P"]))
INK, MUTED, GRID = "#2b2b2a", "#6b6b66", "#e4e3df"
# graph type -> (label, marker, color); fixed across every figure that compares the two
SOURCES = {"census": ("census (queen)", "o", "#2a78d6"), "tiger": ("tiger rook", "^", "#eb6834")}


# ----------------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------------
def odd_wheel_hubs(G):
    """Hubs whose neighbourhood contains an odd cycle: hub + cycle needs 4 colors."""
    return sum(1 for v in G if not nx.is_bipartite(G.subgraph(G[v])))


def clique_counts(G):
    """(number of maximal cliques, max clique size, number of K4 subgraphs)."""
    maximal = list(nx.find_cliques(G))
    k4 = 0
    for c in nx.enumerate_all_cliques(G):  # yields cliques in increasing size
        if len(c) > 4:
            break
        k4 += len(c) == 4
    return len(maximal), max(map(len, maximal), default=0), k4


def graph_metrics(G):
    n, m = G.number_of_nodes(), G.number_of_edges()
    deg = [d for _, d in G.degree]
    n_max_cliques, omega, k4 = clique_counts(G)
    return {
        "n": n,
        "m": m,
        "density": 2 * m / (n * (n - 1)) if n > 1 else 0.0,
        "components": nx.number_connected_components(G),
        "isolated": nx.number_of_isolates(G),
        "mean_degree": statistics.fmean(deg) if deg else 0.0,
        "max_degree": max(deg, default=0),
        "degeneracy": max(nx.core_number(G).values(), default=0),
        "triangles": sum(nx.triangles(G).values()) // 3,
        "transitivity": nx.transitivity(G),
        "avg_clustering": nx.average_clustering(G) if n else 0.0,
        "omega": omega,
        "maximal_cliques": n_max_cliques,
        "k4_count": k4,
        "odd_wheel_hubs": odd_wheel_hubs(G),
        "planar": nx.check_planarity(G)[0],
    }


def search_effort(G, time_limit):
    """Chromatic number plus exact / SAT effort on this labeling."""
    out = {}
    st = {}
    t0 = time.perf_counter()
    try:
        _, chi_exact = wc.exact_coloring(G, time_limit=time_limit, stats=st)
        out["exact_status"] = "ok"
    except TimeoutError:
        chi_exact = None
        out["exact_status"] = "timeout"
    out["exact_ms_once"] = 1000 * (time.perf_counter() - t0)
    nodes = st.get("nodes", {})
    out["exact_nodes"] = sum(nodes.values())
    out["exact_nodes_per_k"] = " ".join(f"{k}:{v}" for k, v in sorted(nodes.items()))

    st = {}
    _, chi_sat = wc.sat_coloring(G, time_limit=time_limit, stats=st)
    per_k = st.get("per_k", {})
    out["sat_conflicts"] = sum(d.get("conflicts", 0) for d in per_k.values())
    out["sat_decisions"] = sum(d.get("decisions", 0) for d in per_k.values())
    out["sat_clauses_final"] = per_k[chi_sat]["clauses"] if per_k else 0

    if chi_exact is not None:
        assert chi_exact == chi_sat, f"exact {chi_exact} != sat {chi_sat}"
    out["chi"] = chi_sat
    out["k_steps"] = len(per_k)  # how many k were tried (1 means clique bound was tight)
    return out


def order_probe(G, orders, time_limit):
    """exact_coloring effort over seeded random relabelings."""
    if orders == 0:
        return {}
    nodes, ms, timeouts = [], [], 0
    for seed in range(orders):
        H = bench.relabeled(G, seed)
        st = {}
        t0 = time.perf_counter()
        try:
            wc.exact_coloring(H, time_limit=time_limit, stats=st)
        except TimeoutError:
            timeouts += 1
        ms.append(1000 * (time.perf_counter() - t0))
        nodes.append(sum(st.get("nodes", {}).values()))
    return {
        "probe_orders": orders,
        "probe_nodes_median": statistics.median(nodes),
        "probe_nodes_max": max(nodes),
        "probe_ms_median": statistics.median(ms),
        "probe_ms_max": max(ms),
        "probe_timeouts": timeouts,
    }


def county_graphs(states):
    yield from bench.census_graphs(states)
    yield from bench.map_graphs(states, ["county"], ["tiger"], ["rook"], 100.0, 0.0)


BA_SIZES = [50, 100, 200, 500, 1000, 2000]


def family_graphs(args):
    if args.family == "county":
        states = list(wc.STATES) if "all" in args.state else args.state
        return county_graphs(states)
    if args.family == "rome":
        return bench.rome_graphs(args.rome, args.rome_seed)
    return bench.ba_graphs(args.ba_n, args.ba_m, args.ba_seeds)


def output_paths(family):
    if family == "county":
        return METRICS, CORR
    return RESULTS / f"{family}_metrics.csv", RESULTS / f"{family}_runtime_correlations.csv"


# ----------------------------------------------------------------------------
# Join with the benchmark + correlations
# ----------------------------------------------------------------------------
def join_runtimes(metrics):
    runs = pd.read_csv(RESULTS / "colorings.csv")
    runs = runs[runs["graph"].isin(metrics["graph"])]
    wide = runs.pivot(index="graph", columns="algorithm", values="runtime_ms_median")
    wide.columns = [f"ms_{a}" for a in wide.columns]
    gap = runs.pivot(index="graph", columns="algorithm", values="gap")
    gap.columns = [f"gap_{a}" for a in gap.columns]
    return metrics.merge(wide, on="graph", how="left").merge(gap, on="graph", how="left")


CORR_METRICS = [
    "n", "m", "density", "mean_degree", "max_degree", "degeneracy", "triangles",
    "omega", "maximal_cliques", "odd_wheel_hubs", "exact_nodes", "sat_conflicts",
]  # fmt: skip


def correlations(df):
    """Spearman rank correlation of each algorithm's median runtime with each metric."""
    d = df[df["n"] >= 5]  # DC (1 node), DE (3) and HI (5, nearly empty) are pure overhead
    rows = {}
    for a in ALGOS:
        col = f"ms_{a}"
        rows[a] = {mt: d[col].corr(d[mt], method="spearman") for mt in CORR_METRICS}
    return pd.DataFrame(rows).T.round(2)


# ----------------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------------
def _style(ax, xlabel, ylabel, title):
    ax.set_xlabel(xlabel, color=MUTED, fontsize=9)
    ax.set_ylabel(ylabel, color=MUTED, fontsize=9)
    ax.set_title(title, color=INK, fontsize=10.5, loc="left")
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)


def make_figures(df):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGS.mkdir(parents=True, exist_ok=True)
    census = df[df["source"] == "census"]
    rook = df[df["source"] == "tiger"]

    # 1. runtime vs graph size, every algorithm (census graphs)
    fig, ax = plt.subplots(figsize=(8, 5))
    for a in ALGOS:
        d = census.dropna(subset=[f"ms_{a}"])
        ax.scatter(d["n"], d[f"ms_{a}"], s=26, color=COLORS[a], marker=MARKERS[a],
                   edgecolor="white", linewidth=0.6, label=a, zorder=3)
    callouts = pd.concat([census.nlargest(3, "n"), census.nlargest(1, "ms_exact")])
    for _, r in callouts.drop_duplicates("graph").iterrows():
        ax.annotate(f"{r['state']} (exact)", (r["n"], r["ms_exact"]), xytext=(5, 2),
                    textcoords="offset points", fontsize=7.5, color=INK)
    ax.set_xscale("log"); ax.set_yscale("log")
    _style(ax, "counties (n, log)", "median runtime, ms (log)",
           "Runtime vs. number of counties - Census adjacency graphs")
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper left")
    fig.tight_layout(); fig.savefig(FIGS / "runtime_vs_n.png", dpi=150); plt.close(fig)

    # 2. exact: runtime vs search-tree nodes, and exact vs SAT runtime
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5))
    for d, (src, mk, c) in ((census, SOURCES["census"]), (rook, SOURCES["tiger"])):
        ok = d[d["exact_status"] == "ok"]
        a1.scatter(ok["exact_nodes"], ok["exact_ms_once"], s=26, marker=mk, color=c,
                   edgecolor="white", linewidth=0.6, label=src, zorder=3)
    for _, r in df[df["exact_status"] == "timeout"].iterrows():
        a1.scatter(r["exact_nodes"], r["exact_ms_once"], s=60, marker="X", color=INK, zorder=4)
        a1.annotate(f"{r['state']} {r['mode']}: time limit", (r["exact_nodes"], r["exact_ms_once"]),
                    xytext=(-6, -14), textcoords="offset points", fontsize=7.5, color=INK, ha="right")
    a1.set_xscale("log"); a1.set_yscale("log")
    _style(a1, "search-tree nodes visited (log)", "one exact_coloring call, ms (log)",
           "Exact runtime tracks search-tree size")
    a1.legend(frameon=False, fontsize=8, loc="upper left")

    both = df.dropna(subset=["ms_exact", "ms_sat"])
    lo = min(both["ms_exact"].min(), both["ms_sat"].min()) * 0.7
    hi = max(both["ms_exact"].max(), both["ms_sat"].max()) * 1.4
    a2.plot([lo, hi], [lo, hi], color=MUTED, linewidth=1, linestyle="--", zorder=1)
    a2.text(hi / 1.6, hi / 1.25, "equal", color=MUTED, fontsize=7.5, ha="right")
    for d, (src, mk, c) in ((census, SOURCES["census"]), (rook, SOURCES["tiger"])):
        d = d.dropna(subset=["ms_exact", "ms_sat"])
        a2.scatter(d["ms_exact"], d["ms_sat"], s=26, marker=mk, color=c,
                   edgecolor="white", linewidth=0.6, label=src, zorder=3)
    for _, r in both.nlargest(3, "ms_exact").iterrows():
        a2.annotate(f"{r['state']} {r['mode']}", (r["ms_exact"], r["ms_sat"]), xytext=(4, -10),
                    textcoords="offset points", fontsize=7.5, color=INK)
    a2.set_xscale("log"); a2.set_yscale("log")
    _style(a2, "exact (backtracking) median ms (log)", "sat median ms (log)",
           "Backtracking vs. SAT on the same graph (below the line: SAT faster)")
    a2.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout(); fig.savefig(FIGS / "exact_effort.png", dpi=150); plt.close(fig)

    # 3. vertex-order sensitivity of exact
    if "probe_nodes_max" in df:
        fig, ax = plt.subplots(figsize=(8, 5))
        for d, (src, mk, c) in ((census, SOURCES["census"]), (rook, SOURCES["tiger"])):
            d = d[d["n"] >= 5]
            ratio = d["probe_nodes_max"] / d["probe_nodes_median"]
            ax.scatter(d["n"], ratio, s=26, marker=mk, color=c, edgecolor="white",
                       linewidth=0.6, label=src, zorder=3)
            for _, r in d[(ratio > 20) | (d["probe_timeouts"] > 0)].iterrows():
                nt = int(r["probe_timeouts"])
                t = f" ({nt} timeout{'s' * (nt > 1)})" if nt else ""
                ax.annotate(f"{r['state']}{t}", (r["n"], r["probe_nodes_max"] / r["probe_nodes_median"]),
                            xytext=(4, 2), textcoords="offset points", fontsize=7.5, color=INK)
        ax.set_yscale("log")
        _style(ax, "counties (n)", "worst / median search-tree nodes (log)",
               f"Exact search effort across {int(df['probe_orders'].max())} random vertex orders")
        ax.legend(frameon=False, fontsize=8, loc="upper left")
        fig.tight_layout(); fig.savefig(FIGS / "exact_order_sensitivity.png", dpi=150); plt.close(fig)

    # 4. queen vs rook: colors above chi per heuristic
    heur = ALGOS[:4]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    w = 0.38
    for i, (d, (src, _, c)) in enumerate(((census, SOURCES["census"]), (rook, SOURCES["tiger"]))):
        vals = [(d[f"gap_{a}"] > 0).mean() * 100 for a in heur]
        xs = [j + (i - 0.5) * w for j in range(len(heur))]
        ax.bar(xs, vals, width=w - 0.04, color=c, label=src, zorder=3)
        for x, v in zip(xs, vals):
            ax.text(x, v + 1, f"{v:.0f}%", ha="center", fontsize=7.5, color=INK)
    ax.set_xticks(range(len(heur)), heur)
    _style(ax, "", "states where the heuristic used more than chi colors, %",
           "How often each greedy order misses the chromatic number (52 county maps)")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIGS / "heuristic_misses.png", dpi=150); plt.close(fig)


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", choices=["all", *sorted(wc.STATES)], nargs="+", default=["all"])
    ap.add_argument("--time-limit", type=float, default=60.0, help="exact/sat limit, seconds")
    ap.add_argument("--probe-orders", type=int, default=20)
    ap.add_argument("--probe-limit", type=float, default=2.0, help="seconds per probe run")
    ap.add_argument("--figures-only", action="store_true", help="redraw from the saved CSV")
    ap.add_argument("--family", choices=["county", "rome", "ba"], default="county")
    ap.add_argument("--rome", type=int, default=1000, help="Rome sample size (as in bench)")
    ap.add_argument("--rome-seed", type=int, default=0)
    ap.add_argument("--ba-n", type=int, nargs="+", default=BA_SIZES)
    ap.add_argument("--ba-m", type=int, default=3)
    ap.add_argument("--ba-seeds", type=int, default=5)
    args = ap.parse_args()
    metrics_path, corr_path = output_paths(args.family)
    if args.figures_only:
        make_figures(pd.read_csv(METRICS))
        print(f"figures -> {FIGS}/")
        return

    rows = []
    for G, meta in family_graphs(args):
        G = wc.integer_labels(G)
        row = {**meta, **graph_metrics(G), **search_effort(G, args.time_limit),
               **order_probe(G, args.probe_orders, args.probe_limit)}
        row["omega_lt_chi"] = row["omega"] < row["chi"]
        rows.append(row)
        print(f"{meta['graph']:<24} n={row['n']:<4} m={row['m']:<5} omega={row['omega']} "
              f"chi={row['chi']} exact_nodes={row['exact_nodes']} ({row['exact_status']}) "
              f"sat_conflicts={row['sat_conflicts']}", flush=True)

    df = join_runtimes(pd.DataFrame(rows))
    df.to_csv(metrics_path, index=False, float_format="%.4g")
    corr = correlations(df)
    corr.to_csv(corr_path)
    print(f"\nwrote {metrics_path} ({len(df)} graphs), {corr_path}")
    print("\nSpearman correlation, median runtime vs metric (graphs with n >= 5):")
    print(corr.to_string())
    if args.family == "county":  # the county figures compare census vs rook graphs
        make_figures(df)
        print(f"figures -> {FIGS}/")


if __name__ == "__main__":
    main()
