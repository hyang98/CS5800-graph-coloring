# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Research goal

Compare graph coloring algorithms on **electoral maps and county maps of the United States**.
Each map becomes a graph (region = node, shared border = edge), and the algorithms are compared on
colors used versus the chromatic number, runtime, and sensitivity to vertex order. We also measure
how much the result depends on how the map is turned into a graph (boundary source, adjacency rule).

Washington, California and Texas are the current case studies (`STATES` in `utils/color.py`). The
plan is to extend to more states and the national county map, then generalize beyond map graphs to
**Rome graphs** and **Barabási–Albert** random graphs. Map graphs are planar and sparse, so they
make a narrow test set; these families show which conclusions still hold on non-map graphs.

## Layout

```
utils/            code (imported as the `utils` package)
  color.py        pipeline + CLI
  bench.py        benchmark -> results/colorings.csv
  make_notebooks.py  notebook template
stateNotebooks/   generated wa_, ca_, tx_coloring.ipynb
results/          colorings.csv (source of truth) + README.md (column docs)
data/             Census shapefile cache (gitignored)
out/              CLI outputs (created on first CLI run)
```

- `utils/color.py`: the pipeline. `fetch_layer` → `build_graph` → `heuristic_colorings` /
  `exact_coloring` / `sat_coloring` → `analyze_reference`, `draw_map`, `draw_overlay`, `county_district_overlay`.
  Every fetch takes a `state` (`"WA"`, `"CA"`, `"TX"`). `integer_labels` gives reproducible
  node ids; use it before reporting any heuristic result.
- `utils/make_notebooks.py`: the single template that generates the notebooks in
  `stateNotebooks/`. Edit the template, then regenerate; never hand-edit the generated notebooks.
  The template's `traced_try_k` is a copy of `_try_k` with event tracing; keep it in sync if
  `_try_k` changes. Notebooks are committed without outputs.
- `utils/bench.py`: runs every algorithm on every graph and upserts rows into
  `results/colorings.csv` (columns documented in `results/README.md`). The results CSV is the
  source of truth for reported numbers. New graph families (Rome, BA) should be added as another
  generator next to `map_graphs` that yields `(G, meta)` with its own `family`.
- `data/`: Census shapefile cache (downloaded, about 100 MB). Don't commit it.
- `out/`: CLI outputs per `<state>_<layer>_<source>`.

Run everything from the repo root as modules (`python -m utils.color`, `python -m utils.bench`,
`python -m utils.make_notebooks`). `bench.py` does `import utils.color`, so `python utils/bench.py`
fails, and `DATA_DIR`, `out/` and `results/` are relative to the working directory. Notebooks
also need their kernel's working directory set to the repo root. Needs `geopandas`, `networkx`,
`matplotlib`, `requests`, `pandas`, `nbformat`, `python-sat`.

## Conventions

- networkx's `smallest_last` and `independent_set` break ties by set iteration, so with string
  node IDs their color counts change with Python's hash seed. Relabel to integers before
  reporting numbers (`bench.py` does this), and report the spread over random relabelings
  rather than a single run.
- Every coloring must pass `is_proper(G, coloring) == []` before results are reported.
- When reporting colors used, also report the chromatic number from `exact_coloring`. Heuristics
  are judged against it. `sat_coloring` is an independent SAT check of the same number;
  `bench.py` fails if the two disagree.
- When stating results, state the graph-construction choices too (`source`, `mode`,
  `min_shared_m`, `snap_m`). They change the edge set: on WA counties `cb` drops 11 edges compared
  with `tiger`.
- Geometry stays in EPSG:5070 (metres) so border-length thresholds mean the same thing everywhere.
- Adding a state means adding its FIPS code to `STATES` (`utils/color.py`) and its name to
  `STATE_NAMES` (`utils/make_notebooks.py`).
- `exact_coloring` runtime is heavy-tailed in the vertex labeling (TX counties: 0.02 s on most
  relabelings, 3 s+ on some). `bench.py` therefore doesn't run it over random relabelings. Keep
  a time limit on any new sweep that includes it.

## Generalizing to Rome / Barabási–Albert

- The sibling project `../GraphColoring/` (CS 5800) already has a graph type, algorithm contract,
  verifier, Rome loader and benchmarks. Reuse it rather than duplicating it here.
- Rome graphs are already on disk at
  `../rl-4-gd-crossing-reduction/upgraded_ppo_export/rome/` (11,534 GraphML files); don't
  re-download them.
- Barabási–Albert: `nx.barabasi_albert_graph(n, m, seed=...)`. Always fix the seed.
- Rome and BA graphs aren't map graphs, so the 4-color guarantee doesn't apply. `exact_coloring`
  can become very slow there; set a size limit or time limit before running it on them.
  `sat_coloring(G, time_limit=...)` supports a time limit. Keep the default `glucose4` solver,
  because python-sat's CaDiCaL ignores `interrupt()` and so never stops at the limit.
