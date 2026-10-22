# Map coloring on Washington State

Turns a real map into a graph and colors it with several algorithms, so their results can be
compared on the same input. Two layers are supported:

| layer    | regions | source |
|----------|---------|--------|
| `county` | 39 WA counties | Census TIGER/Line or Cartographic Boundary, 2024 |
| `cd`     | 10 WA congressional districts (119th Congress) | same |

## Setup

```bash
pip install geopandas networkx matplotlib requests pandas jupyter
```

The first run downloads Census shapefiles into `data/` (about 90 MB, mostly the national TIGER
county file). Later runs read from that cache. Run everything from this folder, since `data/` and
`out/` are relative paths.

## Usage

**Notebook (visual walkthrough):**

```bash
jupyter notebook wa_coloring.ipynb
```

**Command line:**

```bash
python color.py --layer county --source tiger           # counties, legal boundaries
python color.py --layer cd --source cb                  # districts, shoreline-clipped boundaries
python color.py --layer county --mode queen             # corner contact also counts as adjacent
python color.py --layer county --reference ref.json     # check a published map's coloring
python color.py --overlay                               # counties split across districts
```

CLI results go to `out/<layer>_<source>/`: `edges.csv`, `graph.graphml`, `graph.json`,
`map_<algorithm>.png`, `graph_overlay.png`, `report.json`.

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
  - `tiger`: legal boundaries that extend into water. Island counties such as San Juan touch
    their neighbours across Puget Sound.
  - `cb`: boundaries clipped to the shoreline. Water-only borders disappear and San Juan becomes
    an isolated node.

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

Every greedy method gives each node the smallest color its colored neighbours aren't using. The
methods differ only in the order they visit nodes. `exact` starts at k = size of the largest
clique (a lower bound), and tries k, k+1, … until a DSatur-ordered backtracking search succeeds.
It is fast here because map graphs are small and planar.

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

## Results so far (counties, `tiger`, `rook`)

- 39 nodes, 91 edges, planar, maximum degree 8, no isolated counties.
- Chromatic number 4. Only `smallest_last` reaches it; `largest_first`, `dsatur` and
  `independent_set` each use 5.
- The largest clique is only 3 (Stevens, Lincoln, Spokane). The 4th color is forced by an odd
  wheel: Snohomish surrounded by an odd cycle of 5 neighbours.
- `cb` drops 11 water-crossing edges and isolates San Juan. `queen` adds one edge
  (Yakima–King). All three graphs still need exactly 4 colors.
- 7 counties are split between congressional districts; King County spans 4 of them.
