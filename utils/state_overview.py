"""
One figure per graph type that puts graph size, runtime and colors used side by side, one row
per state.

Usage (from the repo root, after `python -m utils.bench --state all --census` and
`python -m utils.graph_metrics`)
  python -m utils.state_overview

Reads
  results/colorings.csv      colors used, chromatic number and median runtime per algorithm
  results/county_metrics.csv largest clique (omega) and max degree per graph
Writes
  results/figures/state_overview_census.png  Census adjacency graphs (queen)
  results/figures/state_overview_rook.png    TIGER rook graphs

Panels, sharing the state rows (sorted by number of counties):
  1. counties (n) and shared borders (m)
  2. median runtime per algorithm, log scale (as in state_runtime_*.png)
  3. colors used per algorithm on the integer labeling, shaded by how many colors above the
     chromatic number chi it is
"""

from pathlib import Path

import pandas as pd

from utils.graph_metrics import ALGOS, COLORS, FIGS, GRID, INK, MARKERS, METRICS, MUTED

COLORINGS = Path("results") / "colorings.csv"
TIMEOUT_MS = 60_000
# graph type -> (colorings.csv source, mode, file suffix, subtitle)
GRAPHS = {
    "census": ("census", "queen", "census",
               "Census adjacency (counties touching at a corner count as neighbours)"),
    "rook": ("tiger", "rook", "rook",
             "TIGER rook (counties must share at least 100 m of border)"),
}
# colors above chi -> cell fill (one hue, light to dark)
GAP_FILL = {0: "#ffffff", 1: "#fbd9a5", 2: "#f0a04b", 3: "#c86a1e"}
SIZE_COLORS = {"n": "#2a78d6", "m": "#9cc3ef"}


def load(source, mode):
    """One row per (state, algorithm), with omega and max degree joined in."""
    c = pd.read_csv(COLORINGS)
    c = c[(c["family"] == "map") & (c["layer"] == "county")
          & (c["source"] == source) & (c["mode"] == mode)]
    m = pd.read_csv(METRICS)[["graph", "omega", "max_degree"]]
    d = c.merge(m, on="graph", how="left")
    missing = d[d["omega"].isna()]["graph"].unique()
    if len(missing):
        print(f"warning: no county_metrics row for {len(missing)} graphs, e.g. {missing[0]}")
    return d


def plot(d, path, subtitle):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, NullLocator

    states = (d.drop_duplicates("state").sort_values(["n", "m"]).reset_index(drop=True))
    row = {s: i for i, s in enumerate(states["state"])}
    d = d.assign(y=d["state"].map(row))
    nrows = len(states)

    fig, (a_size, a_time, a_col) = plt.subplots(
        1, 3, figsize=(16, 0.28 * nrows + 2.6), sharey=True,
        gridspec_kw={"width_ratios": [1.4, 3.2, 2.0], "wspace": 0.05})

    for ax in (a_size, a_time):  # zebra bands so each state reads as one row
        for i in range(0, nrows, 2):
            ax.axhspan(i - 0.5, i + 0.5, color="#f4f3ef", zorder=0, linewidth=0)

    # 1. graph size
    h = 0.36
    a_size.barh(states.index + h / 2, states["m"], height=h, color=SIZE_COLORS["m"],
                label="edges (m)", zorder=2)
    a_size.barh(states.index - h / 2, states["n"], height=h, color=SIZE_COLORS["n"],
                label="counties (n)", zorder=2)
    labels = [f"{r.state}  n={int(r.n)} m={int(r.m)} ω={int(r.omega)}"
              for r in states.itertuples()]
    a_size.set_yticks(range(nrows), labels, fontsize=7.5, color=INK)
    a_size.tick_params(axis="y", length=0, pad=6)
    a_size.set_title("graph size", loc="left", fontsize=9.5, color=INK, pad=28)
    a_size.legend(loc="lower right", frameon=False, fontsize=8)

    # 2. runtime
    for a in ALGOS:
        s = d[d["algorithm"] == a]
        ok = s[s["runtime_ms_median"].notna()]
        a_time.scatter(ok["runtime_ms_median"], ok["y"], s=34, color=COLORS[a],
                       marker=MARKERS[a], edgecolor="white", linewidth=0.6, label=a, zorder=3)
        for y in s[s["runtime_ms_median"].isna()]["y"]:
            a_time.scatter(TIMEOUT_MS, y, s=60, color=COLORS[a], marker="X", zorder=4)
            a_time.annotate(f"{a}: did not finish in {TIMEOUT_MS / 1000:.0f} s",
                            (TIMEOUT_MS, y), xytext=(-8, 0), textcoords="offset points",
                            ha="right", va="center", fontsize=7.5, color=INK)
    a_time.set_xscale("log")
    ticks = [0.001, 0.01, 0.1, 1, 10, 100, 1000, 10000, 60000]
    a_time.xaxis.set_major_locator(FixedLocator(ticks))
    a_time.set_xticklabels(["0.001 ms", "0.01 ms", "0.1 ms", "1 ms", "10 ms", "100 ms", "1 s", "10 s",
                            "60 s"])
    a_time.xaxis.set_minor_locator(NullLocator())
    lo = d["runtime_ms_median"].min()
    a_time.set_xlim(min(0.005, lo / 2), TIMEOUT_MS * 1.6)
    a_time.tick_params(axis="y", length=0, labelright=False)
    a_time.set_title("median runtime of one coloring (log scale)", loc="left", fontsize=9.5,
                     color=INK, pad=28)
    a_time.legend(loc="lower right", frameon=True, facecolor="white", edgecolor=GRID,
                  fontsize=8, title="algorithm", title_fontsize=8)

    # 3. colors used vs chi
    cols = ["chi", *ALGOS]
    for j, a in enumerate(cols):
        for r in states.itertuples():
            if a == "chi":
                v, gap = int(r.chromatic_number), None
            else:
                hit = d[(d["state"] == r.state) & (d["algorithm"] == a)]
                if hit.empty or pd.isna(hit["colors"].iloc[0]):
                    a_col.text(j, row[r.state], "–", ha="center", va="center", fontsize=7.5,
                               color=MUTED)
                    continue
                v = int(hit["colors"].iloc[0])
                gap = v - int(r.chromatic_number)
            fill = "#eeedea" if gap is None else GAP_FILL.get(gap, GAP_FILL[3])
            a_col.add_patch(plt.Rectangle((j - 0.46, row[r.state] - 0.44), 0.92, 0.88,
                                          facecolor=fill, edgecolor="none", zorder=1))
            a_col.text(j, row[r.state], str(v), ha="center", va="center", fontsize=7.5,
                       color=INK, fontweight="bold" if gap is None else "normal", zorder=2)
    a_col.set_xlim(-0.5, len(cols) - 0.5)
    a_col.set_xticks(range(len(cols)),
                     ["χ"] + [a.replace("_", "\n") for a in ALGOS], fontsize=7.5, color=INK)
    a_col.xaxis.set_ticks_position("top")
    a_col.tick_params(axis="both", length=0, labelright=False)
    a_col.set_title("colors used (shade = colors above χ)", loc="left", fontsize=9.5,
                    color=INK, pad=28)
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=GAP_FILL[g], edgecolor=GRID)
               for g in (0, 1, 2)]
    a_col.legend(handles, ["= χ", "χ + 1", "χ + 2"], loc="upper center",
                 bbox_to_anchor=(0.5, -0.004), ncol=3, frameon=False, fontsize=8)

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

    fig.suptitle("County maps by state: graph size, runtime and colors used per algorithm",
                 y=1 - 0.25 / fig.get_figheight(),
                 x=0.01, ha="left", fontsize=13, color=INK)
    fig.text(0.01, 1 - 0.7 / fig.get_figheight(),
             f"{subtitle}. States sorted by number of counties. ω = largest clique. "
             "Runtime is the median of 21 runs; colors are on the integer labeling "
             "(results/colorings.csv).", ha="left", fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.115, right=0.99, top=1 - 1.25 / fig.get_figheight(),
                        bottom=0.6 / fig.get_figheight())
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    FIGS.mkdir(parents=True, exist_ok=True)
    for key, (source, mode, suffix, subtitle) in GRAPHS.items():
        d = load(source, mode)
        path = FIGS / f"state_overview_{suffix}.png"
        plot(d, path, subtitle)
        print(f"wrote {path} ({d['state'].nunique()} states)")


if __name__ == "__main__":
    main()
