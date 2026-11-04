# Map coloring on US state maps

Turns a real map into a graph and colors it with several algorithms, so their results can be
compared on the same input. Three states (WA, CA, TX) have notebooks and both layers (Census
TIGER/Line or Cartographic Boundary files, 2024). County maps of all 50 states, DC and Puerto
Rico are benchmarked as well, using both the Census County Adjacency File and TIGER geometry (see
`results/county_analysis.md`):

| state | `county` | `cd` (119th Congress districts) |
|-------|----------|---------------------------------|
| WA | 39 | 10 |
| CA | 58 | 52 |
| TX | 254 | 38 |

To add a state, add its FIPS code to `STATES` in `utils/color.py` and its name to `STATE_NAMES`
in `utils/make_notebooks.py`.

## Layout

```
utils/
  color.py            pipeline: map -> graph -> colorings, plus the CLI
  bench.py            runs every algorithm on every graph -> results/colorings.csv
  graph_metrics.py    structure + search-effort metrics per county graph, figures
  make_notebooks.py   template that generates the state notebooks
stateNotebooks/       wa_, ca_, tx_coloring.ipynb + rome_ba_coloring.ipynb (generated)
results/              colorings.csv, county_metrics.csv, county_analysis.md, figures/, column docs
data/                 Census shapefile cache (downloaded, gitignored)
out/                  CLI outputs (created on first run)
```

## Setup

```bash
pip install geopandas networkx matplotlib requests pandas jupyter nbformat python-sat
```

The first run downloads Census shapefiles into `data/` (about 100 MB, mostly the national TIGER
county file). Later runs read from that cache. Run everything **from the repo root, as modules**
(`python -m utils.<name>`): the scripts import `utils.color`, and `data/`, `out/` and `results/`
are relative to the working directory.

## Usage

**Notebooks (visual walkthrough, one per state):**

```bash
jupyter notebook stateNotebooks/wa_coloring.ipynb    # or ca_coloring.ipynb, tx_coloring.ipynb
```

The notebooks do `import utils.color`, so the kernel's working directory must be the repo root
(Jupyter and VS Code default to the notebook's own folder; in VS Code set
`jupyter.notebookFileRoot` to `${workspaceFolder}`).

All three are generated from one template in `utils/make_notebooks.py`. To change a notebook, edit
the template and run `python -m utils.make_notebooks`; editing a notebook directly gets
overwritten. The notebooks are written without outputs, and running one takes 10–25 s. On large
maps (more than 80 regions), county labels are hidden and animations show every few steps.

**Command line:**

```bash
python -m utils.color --layer county --source tiger         # WA counties, legal boundaries
python -m utils.color --state TX --layer cd                 # Texas districts
python -m utils.color --layer cd --source cb                # districts, shoreline-clipped boundaries
python -m utils.color --layer county --mode queen           # corner contact also counts as adjacent
python -m utils.color --layer county --reference ref.json   # check a published map's coloring
python -m utils.color --overlay                             # counties split across districts
```

CLI results go to `out/<state>_<layer>_<source>/`: `edges.csv`, `graph.graphml`, `graph.json`,
`map_<algorithm>.png`, `graph_overlay.png`, `report.json`.

**Benchmark (colors and runtime for every algorithm on every graph):**

```bash
python -m utils.bench --state WA CA TX            # 24 map graphs -> results/colorings.csv (~30 s)
python -m utils.bench --state TX --layer county   # rerun a subset; other rows are kept

# counties of all 50 states + DC + PR: Census adjacency graph + TIGER rook graph (~3 min)
python -m utils.bench --state all --layer county --source tiger --mode rook --census
python -m utils.graph_metrics                     # metrics, correlations, figures (~2.5 min)

# 1000 Rome graphs (same sample as ../GraphColoring) + 30 Barabasi-Albert graphs, m=3 (~8 min)
python -m utils.bench --no-maps --rome 1000 --ba-n 50 100 200 500 1000 2000 --ba-m 3 --ba-seeds 5 --repeats 5 --orders 10
python -m utils.graph_metrics --family rome
python -m utils.graph_metrics --family ba --probe-limit 10
python -m utils.make_notebooks families           # stateNotebooks/rome_ba_coloring.ipynb
```

`exact` and `sat` run under `--exact-time-limit` (default 60 s); a run that hits it is recorded
with `status=timeout`. On the full sweep that happened once: `exact` on Kentucky's rook graph.

Columns are documented in `results/README.md`.

## How it works

### 1. Map → graph (`fetch_layer`, `build_graph`)

Each region becomes a node, placed at a point inside the region. Two nodes are joined by an edge
when the regions share a border. Shapes are projected to an equal-area projection (EPSG:5070) so
border lengths are in metres.

Two choices change the graph:

- **Adjacency rule** (`--mode`)
  - `rook` (default): the regions must share a border segment of at least `--min-shared-m`
    (100 m). Regions that meet at a single point may share a color. This is the standard
    map-coloring rule.
  - `queen`: any contact counts, including a single corner point.
- **Boundary source** (`--source`)
  - `tiger`: legal boundaries that extend into water. Island counties such as San Juan (WA)
    touch their neighbours across Puget Sound.
  - `cb`: boundaries clipped to the shoreline. Water-only borders disappear, and San Juan becomes
    an isolated node.
  - `census` (county layer, bench only): the Census County Adjacency File
    (`census_county_graph`). Census counts any contact, including a single point, and includes
    boundaries in water. For all 52 county maps it equals `tiger` + `queen` edge for edge.

`--snap-m` buffers every polygon slightly first, which closes small gaps left by digitizing.

### 2. Coloring

A coloring assigns each node a color so that no two neighbours share one. Every result is checked
with `is_proper`.

| name | how it works |
|------|--------------|
| `largest_first` | greedy, visiting nodes in order of decreasing degree |
| `dsatur` | greedy; the next node is the one whose neighbours already use the most distinct colors |
| `smallest_last` | repeatedly remove the lowest-degree node, then color in reverse removal order |
| `independent_set` | repeatedly take a maximal independent set and give it one color |
| `exact` | backtracking search that finds the true minimum (the chromatic number) |
| `sat` | SAT encoding solved by Glucose 4; a second, independent exact method used to cross-check `exact` |

Every greedy method gives each node the smallest color its colored neighbours aren't using. The
methods differ only in the order they visit nodes. `exact` starts at k = size of the largest
clique (a lower bound), and tries k, k+1, … until a DSatur-ordered backtracking search succeeds.
It is fast on these maps (20 ms for Texas counties), but its runtime depends heavily on vertex
labeling. On some random relabelings of Texas counties it takes 3 s or more.

`sat` (`sat_coloring`) answers the same question with a SAT solver. For each k from the clique
size upward it asks whether a k-coloring exists: one boolean per (node, color), a clause saying
every node gets a color, and a clause per edge and color forbidding both ends from sharing it. One
maximum clique is fixed to colors 0..q-1 to cut symmetric solutions. It shares no search code with
`exact`, so agreement between them is real evidence that the chromatic number is right. `bench.py`
and the CLI stop with an error if they disagree. They agree on all 24 WA/CA/TX graphs. `sat`
takes an optional `time_limit` (seconds) for larger non-map graphs.

### 3. Comparing with a real map (`analyze_reference`)

Give it a JSON file of `{region name or GEOID: color label}` transcribed from a published map.
It reports whether the coloring is proper, how many colors it uses compared with the chromatic
number, whether any algorithm produced the same color classes, and whether plain greedy could
reproduce it under some vertex order.

### 4. County × district overlay (`county_district_overlay`)

Intersects the two layers and lists every county that lies in more than one congressional
district. Pieces under 1 km² are ignored as slivers.

## Notebook sections

1. Load counties and draw the adjacency graph on the map
2. All algorithms side by side: colors used, runtime, class sizes, and identical partitions
3. Greedy / DSatur animated one county at a time, plus a static version with the visit order
4. The exact backtracking search animated, showing assignments and undos
5. Why the minimum isn't lower: largest clique, odd wheel, greedy with random orders
6. Edges gained or lost between `tiger` vs `cb` and `rook` vs `queen`
7. Congressional districts and counties split between districts
8. `analyze_reference` example

## Results so far

The full table is in `results/colorings.csv` (all states, boundary sources and adjacency rules).
Colors used on the `tiger` / `rook` graphs, with the range over 50 random relabelings in
brackets:

| graph | n | m | χ | largest_first | dsatur | smallest_last | independent_set |
|-------|---|---|---|---|---|---|---|
| WA counties | 39 | 91 | 4 | 5 [4–5] | 5 [4–5] | 5 [4–5] | 6 [4–6] |
| CA counties | 58 | 140 | 4 | 5 [4–6] | 4 [4–5] | 4 [4–4] | 4 [4–6] |
| TX counties | 254 | 660 | 4 | 5 [5–6] | 5 [4–5] | 4 [4–4] | 5 [5–6] |
| WA districts | 10 | 21 | 4 | 4 | 4 | 4 | 4 |
| CA districts | 52 | 133 | 4 | 5 [4–5] | 4 [4–4] | 4 [4–4] | 5 [5–6] |
| TX districts | 38 | 96 | 4 | 4 [4–5] | 4 [4–4] | 5 [4–5] | 5 [4–6] |

- Every graph is planar. On all county maps and WA districts the largest clique is 3, so the 4th
  color is forced by an odd wheel (a hub surrounded by an odd cycle of neighbours), which section
  5 of the notebook finds and highlights. The CA and TX district maps contain four mutually
  adjacent districts, so there the clique alone forces 4 colors.
- No heuristic is best everywhere. On the `rook` CA and TX county maps, `smallest_last` never
  exceeded 4 colors under any relabeling, but uses 5 on TX districts, where `dsatur` always finds 4.
  `independent_set` is the least reliable.
- The boundary source matters on coastlines: in WA, `cb` drops 11 water-crossing edges and
  isolates San Juan. In TX, `tiger` and `cb` give identical graphs.
- The adjacency rule matters on grid-like maps: `queen` adds 64 corner-only edges in TX (the
  Panhandle grid) and pushes heuristics up (`smallest_last` 4 → 5, `largest_first` 5 → 6). The
  chromatic number stays 4 everywhere.
- Counties split by district lines: 7 of 39 in WA, 27 of 58 in CA, 30 of 254 in TX.

**All states** (details in `results/county_analysis.md`):

- **χ:** 4 on 45 of 52 county maps under either rule.
  - Under the Census (queen) rule, Florida needs 5: five counties meet at one point in Lake
    Okeechobee, which makes a K5.
  - 25 of the 52 Census graphs are non-planar. Under rook only Louisiana is, because St. Martin
    Parish has two separate pieces.
- **Quality:** `smallest_last` reaches χ on 50 of 52 maps under the Census rule and 51 of 52 under
  rook. `dsatur` misses on 7–10 maps, and `largest_first` and `independent_set` miss on most.
- **Runtime:**
  - largest_first and smallest_last grow about linearly in n.
  - networkx's dsatur and independent_set grow about quadratically.
  - `exact` grows as search-tree nodes × n. The tree is usually about n nodes, but with a heavy
    tail: Kentucky timed out, and Missouri took 18k nodes.
  - `sat` stays near 1–3 ms throughout.

**Rome and Barabási–Albert graphs** (details in `results/rome_ba_analysis.md`, interactive in
`stateNotebooks/rome_ba_coloring.ipynb`):

- **Planarity:** 70% of Rome graphs are non-planar, yet they are the easiest family (mean
  degree 2.6, χ = 3 on 95%). Non-planar Rome graphs miss χ more often with the weaker heuristics,
  but once size and density are accounted for, planarity has no significant effect
  (`largest_first` p = 0.40, `independent_set` p = 0.96). Density is what matters.
- **BA graphs (m = 3):** ω = χ = 4 on every graph, and `exact` never backtracks. The hubs break
  `independent_set` (up to 10 colors at n = 2000) and `largest_first` (misses 87%). At n = 2000
  the quadratic algorithms (`dsatur`, `exact`, `independent_set`) take 1–2.5 s; `smallest_last`
  takes 8.5 ms and `sat` 18 ms.
