"""Benchmark graph-coloring algorithms.

Runs are consecutive in one process, not parallel: parallel runs compete for
CPU and memory and distort the timings. Repetitions go round-robin
(for rep: for algorithm: time it) after `warmup` untimed runs per algorithm.

CLI: python benchmark.py --runs 5 --warmup 1 --impl networkx \
        --algorithms dsatur smallest_last --notes "..." --no-save
"""

import argparse
import hashlib
import json
import platform
import socket
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import networkx as nx

from greedy_coloring import ALGORITHMS
from networkx_graph_trial import (color_graph, graph_stats, load_county_graph,
                                  num_colors, validate_coloring)

ALGORITHM_NAMES = list(ALGORITHMS)

HERE = Path(__file__).resolve().parent
DEFAULT_HISTORY = HERE / "results" / "history.jsonl"


def _machine_info() -> dict:
    import os
    host = hashlib.sha256(socket.gethostname().encode()).hexdigest()[:12]
    return {"hostname_hash": host, "platform": platform.platform(),
            "machine": platform.machine(), "processor": platform.processor(),
            "cpu_count": os.cpu_count(), "python": platform.python_version(),
            "python_impl": platform.python_implementation(), "networkx": nx.__version__,
            # independent_set depends on set order of string ids, which depends on this
            # ("random" means unset)
            "pythonhashseed": os.environ.get("PYTHONHASHSEED", "random")}


def run_benchmark(G=None, algorithms=ALGORITHM_NAMES, impl="networkx", runs=5, warmup=1,
                  notes="", progress: Callable[[str], None] | None = None) -> dict:
    """Time each algorithm `runs` times (round-robin) and return a record dict."""
    say = progress or (lambda _m: None)
    if G is None:
        G, _ = load_county_graph()
    algorithms = list(algorithms)

    for alg in algorithms:
        for i in range(warmup):
            say(f"warmup {alg} {i + 1}/{warmup}")
            color_graph(G, alg, impl)

    times = {a: [] for a in algorithms}
    last = {}
    for rep in range(runs):
        for alg in algorithms:
            t0 = time.perf_counter()
            last[alg] = color_graph(G, alg, impl)
            times[alg].append(time.perf_counter() - t0)
            say(f"run {rep + 1}/{runs} {alg}: {times[alg][-1]:.4f}s")

    results = []
    for alg in algorithms:
        ts = times[alg]
        mean = statistics.mean(ts) if ts else 0.0
        sd = statistics.stdev(ts) if len(ts) >= 2 else 0.0
        results.append({
            "algorithm": alg,
            "colors": num_colors(last[alg]) if alg in last else 0,
            "valid": validate_coloring(G, last[alg]) if alg in last else False,
            "times_s": ts,
            "mean_s": mean,
            "median_s": statistics.median(ts) if ts else 0.0,
            "min_s": min(ts) if ts else 0.0,
            "max_s": max(ts) if ts else 0.0,
            "stdev_s": sd,
            "cv_pct": 100 * sd / mean if mean else 0.0,
        })
    return {"run_id": uuid.uuid4().hex,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "impl": impl, "runs_per_algorithm": runs, "warmup": warmup, "notes": notes,
            "machine": _machine_info(), "graph": graph_stats(G), "results": results}


def save_record(record: dict, path=DEFAULT_HISTORY) -> None:
    """Append one JSON line to the history file (creating the directory)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def load_history(path=DEFAULT_HISTORY) -> list[dict]:
    """Read all records; [] if missing; malformed lines are skipped."""
    path = Path(path)
    if not path.exists():
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def format_table(record: dict) -> str:
    """Aligned text table of a record's results."""
    g = record["graph"]
    head = (f"impl={record['impl']}  runs={record['runs_per_algorithm']}  "
            f"warmup={record['warmup']}  graph={g['nodes']} nodes/{g['edges']} edges")
    cols = ["algorithm", "colors", "valid", "mean_s", "median_s", "min_s", "max_s", "stdev_s", "cv_%"]
    rows = [[r["algorithm"], str(r["colors"]), str(r["valid"]),
             f"{r['mean_s']:.4f}", f"{r['median_s']:.4f}", f"{r['min_s']:.4f}",
             f"{r['max_s']:.4f}", f"{r['stdev_s']:.4f}", f"{r['cv_pct']:.1f}"]
            for r in record["results"]]
    w = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c) for i, c in enumerate(cols)]
    fmt = lambda cells: "  ".join(c.ljust(w[i]) if i == 0 else c.rjust(w[i])
                                  for i, c in enumerate(cells))
    return "\n".join([head, fmt(cols), "  ".join("-" * x for x in w)] + [fmt(r) for r in rows])


def main() -> None:
    p = argparse.ArgumentParser(description="Benchmark graph coloring algorithms")
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--impl", choices=["networkx", "local"], default="networkx")
    p.add_argument("--algorithms", nargs="+", choices=ALGORITHM_NAMES, default=ALGORITHM_NAMES)
    p.add_argument("--notes", default="")
    p.add_argument("--no-save", action="store_true")
    a = p.parse_args()
    rec = run_benchmark(algorithms=a.algorithms, impl=a.impl, runs=a.runs,
                        warmup=a.warmup, notes=a.notes)
    print(format_table(rec))
    if a.no_save:
        print("(not saved)")
    else:
        save_record(rec)
        print(f"saved to {DEFAULT_HISTORY}")


if __name__ == "__main__":
    main()
