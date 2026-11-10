"""Check that the local copies in greedy_coloring/ match networkx exactly.

Run from anywhere:   python jb_folder/tests/test_greedy_coloring.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import networkx as nx

from greedy_coloring import ALGORITHMS, NX_STRATEGY_NAMES
from networkx_graph_trial import load_county_graph


def is_valid(G, col):
    return set(col) == set(G) and all(col[u] != col[v] for u, v in G.edges())


def small_graphs():
    graphs = [nx.empty_graph(0), nx.empty_graph(1), nx.empty_graph(5),
              nx.complete_graph(7), nx.path_graph(10), nx.star_graph(8),
              nx.petersen_graph(), nx.cycle_graph(9),
              nx.disjoint_union(nx.complete_graph(4), nx.path_graph(5))]
    for n in (5, 15, 40):
        for p in (0.1, 0.3, 0.6, 0.9):
            for seed in (0, 1, 2):
                graphs.append(nx.gnp_random_graph(n, p, seed=seed))
    return graphs


def test_matches_networkx_small():
    for name, color in ALGORITHMS.items():
        for G in small_graphs():
            got = color(G)
            assert got == nx.greedy_color(G, strategy=NX_STRATEGY_NAMES[name]), name
            assert is_valid(G, got), name


def test_county_graph():
    G, _ = load_county_graph()
    assert (G.number_of_nodes(), G.number_of_edges()) == (3109, 9230)
    # independent_set can use 6 or 7 colors: it loops over sets of string node ids,
    # and Python randomizes string hashing in each process (see PYTHONHASHSEED).
    expected = {"welsh_powell": {6}, "dsatur": {5}, "smallest_last": {5}, "independent_set": {6, 7}}
    for name, color in ALGORITHMS.items():
        start = time.perf_counter()
        got = color(G)
        elapsed = time.perf_counter() - start
        assert got == nx.greedy_color(G, strategy=NX_STRATEGY_NAMES[name]), name
        assert is_valid(G, got), name
        n_colors = max(got.values()) + 1
        assert n_colors in expected[name], (name, n_colors)
        print(f"  county {name}: {n_colors} colors, {elapsed:.2f}s")


if __name__ == "__main__":
    tests = [fn for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for fn in tests:
        print(f"{fn.__name__} ...")
        fn()
        print("  ok")
    print(f"{len(tests)} tests passed")
