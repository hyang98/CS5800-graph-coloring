"""Pipeline tests. Run: python jb_folder/tests/test_pipeline.py (pytest also works)."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmark import ALGORITHM_NAMES, format_table, load_history, run_benchmark, save_record
from networkx_graph_trial import color_graph, load_county_graph, num_colors, validate_coloring

G, POS = load_county_graph()
# independent_set can use 6 or 7 colors: it loops over sets of string node ids,
# and Python randomizes string hashing in each process (see PYTHONHASHSEED).
EXPECTED = {"welsh_powell": {6}, "dsatur": {5}, "smallest_last": {5}, "independent_set": {6, 7}}


def test_graph_size():
    assert G.number_of_nodes() == 3109 and G.number_of_edges() == 9230
    assert len(POS) == 3109


def test_color_counts_and_validity():
    for alg in ALGORITHM_NAMES:
        c = color_graph(G, alg)
        assert num_colors(c) in EXPECTED[alg], (alg, num_colors(c))
        assert validate_coloring(G, c)


def test_validate_catches_broken():
    c = dict(color_graph(G, "dsatur"))
    u, v = next(iter(G.edges()))
    c[v] = c[u]
    assert not validate_coloring(G, c)
    c2 = dict(color_graph(G, "dsatur"))
    c2.pop(u)
    assert not validate_coloring(G, c2)
    assert num_colors({}) == 0


def test_benchmark_schema_and_history():
    algs = ["welsh_powell", "smallest_last"]
    rec = run_benchmark(G, algorithms=algs, runs=2, warmup=0)
    assert set(rec) == {"run_id", "timestamp", "impl", "runs_per_algorithm", "warmup", "notes",
                        "machine", "graph", "results"}
    assert [r["algorithm"] for r in rec["results"]] == algs
    keys = {"algorithm", "colors", "valid", "times_s", "mean_s", "median_s", "min_s",
            "max_s", "stdev_s", "cv_pct"}
    for r in rec["results"]:
        assert set(r) == keys and len(r["times_s"]) == 2 and r["valid"]
    assert rec["graph"]["nodes"] == 3109
    assert "hostname" not in rec["machine"]
    assert "welsh_powell" in format_table(rec)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sub" / "h.jsonl"
        assert load_history(p) == []
        save_record(rec, p)
        with open(p, "a") as f:
            f.write("not json\n")
        save_record(rec, p)
        h = load_history(p)
        assert len(h) == 2 and h[0] == rec


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("all tests passed")
