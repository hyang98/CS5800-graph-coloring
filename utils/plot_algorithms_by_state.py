"""
Plot results/algorithms_by_state.csv (networkx greedy strategies per state, made by
stateNotebooks/country_notebook.ipynb) next to each state's graph size and chromatic number.

Usage (from the repo root)
  python -m utils.plot_algorithms_by_state

Reads
  results/algorithms_by_state.csv  State, Algorithm, Colors Used, Runtime (seconds, one run)
  results/county_metrics.csv       n, m, omega, chi of the Census adjacency graph (queen)
Writes
  results/figures/algorithms_by_state.png

Each state's graph is built from the Census County Adjacency File (2024), the same graph as
the census rows of county_metrics.csv. Runtimes are one timed run on string county IDs.
DSATUR is an alias of saturation_largest_first and connected_sequential of
  connected_sequential_bfs; aliases are folded after checking the colors agree.
"""

from pathlib import Path

import pandas as pd

from utils.graph_metrics import FIGS, GRID, INK, METRICS, MUTED

CSV = Path("results") / "algorithms_by_state.csv"
OUT = FIGS / "algorithms_by_state.png"
ALIASES = {"DSATUR": "saturation_largest_first", "connected_sequential": "connected_sequential_bfs"}
# shared algorithms keep their colours from the other figures (utils.graph_metrics.COLORS)
ALGOS = ["largest_first", "random_sequential", "smallest_last", "independent_set",
         "connected_sequential_bfs", "connected_sequential_dfs", "saturation_largest_first"]
COLORS = {"largest_first": "#2a78d6", "saturation_largest_first": "#eb6834",
          "smallest_last": "#1baf7a", "independent_set": "#eda100",
          "random_sequential": "#008300", "connected_sequential_bfs": "#6250d6",
          "connected_sequential_dfs": "#e34948"}
MARKERS = {"largest_first": "o", "saturation_largest_first": "s", "smallest_last": "^",
           "independent_set": "v", "random_sequential": "P", "connected_sequential_bfs": "D",
           "connected_sequential_dfs": "X"}
SHORT = {"saturation_largest_first": "DSATUR", "connected_sequential_bfs": "conn_seq_bfs",
         "connected_sequential_dfs": "conn_seq_dfs"}
GAP_FILL = {0: "#ffffff", 1: "#fbd9a5", 2: "#f0a04b", 3: "#c86a1e"}


def load():
    d = pd.read_csv(CSV, index_col=0)
    d = d.rename(columns={"State": "state", "Algorithm": "algorithm",
                          "Colors Used": "colors", "Runtime": "runtime_s"})
    wide = d.pivot(index="state", columns="algorithm", values="colors")
    for alias, name in ALIASES.items():
        bad = wide.index[wide[alias] != wide[name]].tolist()
        if bad:
            print(f"warning: {alias} and {name} disagree on colors for {bad}; keeping both")
            ALGOS.append(alias)
        else:
            d = d[d["algorithm"] != alias]
    m = pd.read_csv(METRICS)
    m = m[m["source"] == "census"][["state", "n", "m", "omega", "chi"]]
    d = d.merge(m, on="state", how="left")
    d["runtime_ms"] = d["runtime_s"] * 1000
    return d


def plot(d):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, NullLocator

    states = d.drop_duplicates("state").sort_values(["n", "m"]).reset_index(drop=True)
    row = {s: i for i, s in enumerate(states["state"])}
    d = d.assign(y=d["state"].map(row))
    nrows = len(states)
    algos = [a for a in ALGOS if a in set(d["algorithm"])]

    fig, (a_size, a_time, a_col) = plt.subplots(
        1, 3, figsize=(17, 0.28 * nrows + 2.8), sharey=True,
        gridspec_kw={"width_ratios": [1.3, 3.0, 2.4], "wspace": 0.05})

    for ax in (a_size, a_time):
        for i in range(0, nrows, 2):
            ax.axhspan(i - 0.5, i + 0.5, color="#f4f3ef", zorder=0, linewidth=0)

    # 1. graph size (Census adjacency graph of the state)
    h = 0.36
    a_size.barh(states.index + h / 2, states["m"], height=h, color="#9cc3ef",
                label="edges (m)", zorder=2)
    a_size.barh(states.index - h / 2, states["n"], height=h, color="#2a78d6",
                label="counties (n)", zorder=2)
    labels = [f"{r.state}  n={int(r.n)} m={int(r.m)} ω={int(r.omega)}"
              for r in states.itertuples()]
    a_size.set_yticks(range(nrows), labels, fontsize=7.5, color=INK)
    a_size.tick_params(axis="y", length=0, pad=6)
    a_size.set_title("graph size (Census adjacency)", loc="left", fontsize=9.5, color=INK,
                     pad=28)
    a_size.legend(loc="lower right", frameon=False, fontsize=8)

    # 2. runtime
    for a in algos:
        s = d[d["algorithm"] == a]
        a_time.scatter(s["runtime_ms"], s["y"], s=34, color=COLORS[a], marker=MARKERS[a],
                       edgecolor="white", linewidth=0.6, label=SHORT.get(a, a), zorder=3)
    a_time.set_xscale("log")
    ticks = [0.001, 0.01, 0.1, 1, 10, 100, 1000]
    a_time.xaxis.set_major_locator(FixedLocator(ticks))
    a_time.set_xticklabels(["0.001 ms", "0.01 ms", "0.1 ms", "1 ms", "10 ms", "100 ms", "1 s"])
    a_time.xaxis.set_minor_locator(NullLocator())
    a_time.set_xlim(d["runtime_ms"].min() / 2, d["runtime_ms"].max() * 2)
    a_time.tick_params(axis="y", length=0)
    a_time.set_title("runtime of one coloring (log scale, one run)",
                     loc="left", fontsize=9.5, color=INK, pad=28)
    a_time.legend(loc="upper center", bbox_to_anchor=(0.5, -0.035), ncol=4, frameon=False,
                  fontsize=8)

    # 3. colors used vs chi
    cols = ["chi", *algos]
    colors = d.set_index(["state", "algorithm"])["colors"]
    for j, a in enumerate(cols):
        for r in states.itertuples():
            y = row[r.state]
            if a == "chi":
                v, fill, weight = int(r.chi), "#eeedea", "bold"
            else:
                v = int(colors[(r.state, a)])
                gap = v - int(r.chi)
                fill = GAP_FILL.get(gap, GAP_FILL[3])
                weight = "normal"
            a_col.add_patch(plt.Rectangle((j - 0.46, y - 0.44), 0.92, 0.88, facecolor=fill,
                                          edgecolor="none", zorder=1))
            a_col.text(j, y, str(v), ha="center", va="center", fontsize=7.5,
                       color=INK,
                       fontweight=weight, zorder=2)
    a_col.set_xlim(-0.5, len(cols) - 0.5)
    a_col.set_xticks(range(len(cols)),
                     ["χ"] + [SHORT.get(a, a).replace("_", "\n", 1) for a in algos],
                     fontsize=7, color=INK)
    a_col.xaxis.set_ticks_position("top")
    a_col.tick_params(axis="both", length=0)
    a_col.set_title("colors used (shade = colors above χ)", loc="left", fontsize=9.5,
                    color=INK, pad=28)
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=GAP_FILL[g], edgecolor=GRID)
               for g in (0, 1, 2, 3)]
    a_col.legend(handles, ["= χ", "χ + 1", "χ + 2", "χ + 3"], loc="upper center",
                 bbox_to_anchor=(0.5, -0.004), ncol=4, frameon=False, fontsize=8)

    for ax in (a_size, a_time, a_col):
        for s in ("top", "right", "left", "bottom"):
            ax.spines[s].set_visible(False)
    for ax in (a_size, a_time):
        ax.grid(True, axis="x", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(axis="x", colors=MUTED, labelsize=8)
        ax.spines["bottom"].set_visible(True)
        ax.spines["bottom"].set_color(GRID)
    a_size.set_ylim(-0.7, nrows - 0.3)

    H = fig.get_figheight()
    fig.suptitle("networkx greedy strategies by state (results/algorithms_by_state.csv)",
                 y=1 - 0.25 / H, x=0.01, ha="left", fontsize=13, color=INK)
    fig.text(0.01, 1 - 0.7 / H,
             "States sorted by number of counties. n, m, ω (largest clique) and χ come from "
             "county_metrics.csv (Census adjacency, the same graph the CSV colored). "
             "One timed run per cell.",
             ha="left", fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.13, right=0.99, top=1 - 1.3 / H, bottom=1.0 / H)
    fig.savefig(OUT, dpi=150)
    plt.close(fig)


def main():
    FIGS.mkdir(parents=True, exist_ok=True)
    d = load()
    plot(d)
    print(f"wrote {OUT} ({d['state'].nunique()} states, "
          f"{d['algorithm'].nunique()} algorithms)")


if __name__ == "__main__":
    main()
