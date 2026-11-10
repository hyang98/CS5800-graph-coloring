# jb_folder

Read's `networkx_graph_trial.py` (US county graph, greedy coloring),
lightly refactored into small functions, plus some tooling around it.
Data is read from `../read_folder/data`.

## Layout
- `networkx_graph_trial.py` - the script: load data, build graph, color, draw
- `greedy_coloring/` - unmodified copies of four networkx algorithms
  (`welsh_powell`, `dsatur`, `smallest_last`, `independent_set`), one file each
- `benchmark.py` - times the algorithms; history goes in `results/history.jsonl`
- `visualize_map.py` - colored US county map
- `dashboard/` - local web page to run benchmarks and view results and maps
- `tests/` - `test_greedy_coloring.py`, `test_pipeline.py`

## Setup
    source .venv/bin/activate
    pip install -r jb_folder/requirements.txt

## Run
    python jb_folder/networkx_graph_trial.py                       # color and draw dots
    python jb_folder/networkx_graph_trial.py --strategy smallest_last --impl local --no-plot
    python jb_folder/networkx_graph_trial.py --map                 # county map

    python jb_folder/benchmark.py --runs 5 --warmup 1 --impl local

    python jb_folder/dashboard/server.py       # then open http://127.0.0.1:8765
                                               # Ctrl+C stops it

    python jb_folder/tests/test_greedy_coloring.py
    python jb_folder/tests/test_pipeline.py

`--impl networkx` uses networkx's code, `--impl local` uses the copies in
`greedy_coloring/`; both give the same coloring.

## independent_set varies between runs
`independent_set` uses 6 or 7 colors on the county graph depending on the
run. It loops over sets of string node ids, and Python randomizes string
hashing in each process. Set `PYTHONHASHSEED` to a number to get repeatable
results. The other three algorithms always give the same result.

## More
A fuller version with additional refactoring lives on the local branch
`jb-full`.
