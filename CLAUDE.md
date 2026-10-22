# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Research goal

Compare graph coloring algorithms on **electoral maps and county maps of the United States**.
Each map becomes a graph (region = node, shared border = edge), and the algorithms are compared on
colors used versus the chromatic number, runtime, and sensitivity to vertex order. We also measure
how much the result depends on how the map is turned into a graph (boundary source, adjacency rule).

Washington State (39 counties, 10 congressional districts) is the first case study. The plan is to
extend to other states and the national county map, then generalize beyond map graphs to
**Rome graphs** and **Barabási–Albert** random graphs. Map graphs are planar and sparse, so they
make a narrow test set; these families show which conclusions still hold on non-map graphs.

## Files

- `color.py`: the pipeline. `fetch_layer` → `build_graph` → `heuristic_colorings` /
  `exact_coloring` → `analyze_reference`, `draw_map`, `draw_overlay`, `county_district_overlay`.
  Run with `python color.py --layer {county,cd} --source {tiger,cb}` (see `README.md`). The module
  docstring still calls it `wa_map_coloring.py`; the real filename is `color.py`.
- `wa_coloring.ipynb`: visual walkthrough. It does `import color as wc` and reuses the module's
  functions. The exception is `traced_try_k`, a copy of `_try_k` with event tracing for the
  animation; keep it in sync if `_try_k` changes.
- `bench.py`: runs every algorithm on every graph and upserts rows into
  `results/colorings.csv` (columns documented in `results/README.md`). The results CSV is the
  source of truth for reported numbers. New graph families (Rome, BA) should be added as another
  generator next to `map_graphs` that yields `(G, meta)` with its own `family`.
- `data/`: Census shapefile cache (downloaded, about 90 MB). Don't commit it.
- `out/`: CLI outputs per `<layer>_<source>`.

Run from this folder: `DATA_DIR` and `out/` are relative paths. Needs `geopandas`, `networkx`,
`matplotlib`, `requests`, `pandas`.

## Conventions

- networkx's `smallest_last` and `independent_set` break ties by set iteration, so with string
  node IDs their color counts change with Python's hash seed. Relabel to integers before
  reporting numbers (`bench.py` does this), and report the spread over random relabelings
  rather than a single run.
- Every coloring must pass `is_proper(G, coloring) == []` before results are reported.
- When reporting colors used, also report the chromatic number from `exact_coloring`. Heuristics
  are judged against it.
- When stating results, state the graph-construction choices too (`source`, `mode`,
  `min_shared_m`, `snap_m`). They change the edge set: on WA counties `cb` drops 11 edges compared
  with `tiger`.
- Geometry stays in EPSG:5070 (metres) so border-length thresholds mean the same thing everywhere.
- Adding a state or layer means adding an entry to `SOURCES` and its state FIPS code;
  `fetch_layer` currently hard-codes `WA_FIPS = "53"`.

## Generalizing to Rome / Barabási–Albert

- The sibling project `../GraphColoring/` (CS 5800) already has a graph type, algorithm contract,
  verifier, Rome loader and benchmarks. Reuse it rather than duplicating it here.
- Rome graphs are already on disk at
  `../rl-4-gd-crossing-reduction/upgraded_ppo_export/rome/` (11,534 GraphML files); don't
  re-download them.
- Barabási–Albert: `nx.barabasi_albert_graph(n, m, seed=...)`. Always fix the seed.
- Rome and BA graphs aren't map graphs, so the 4-color guarantee doesn't apply. `exact_coloring`
  can become very slow there; set a size limit or time limit before running it on them.
