"""Local benchmark dashboard server (stdlib only).

Usage: python dashboard/server.py [--port 8765] [--host 127.0.0.1]

Endpoints: GET / , GET /api/history, POST /api/run, GET /api/status,
DELETE /api/history/<run_id>, GET /api/export.csv
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import benchmark  # noqa: E402
from benchmark import ALGORITHM_NAMES  # noqa: E402
from networkx_graph_trial import load_county_graph  # noqa: E402

STATIC = (Path(__file__).resolve().parent / "static").resolve()
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
        ".ico": "image/x-icon", ".json": "application/json"}

GRAPH = None
LOCK = threading.Lock()          # guards STATE and history file writes
STATE = {"busy": False, "job_id": None, "started": None,
         "progress": {"message": "", "done_steps": 0, "total_steps": 0, "current_algorithm": None},
         "last_error": None, "last_record_id": None}

def _job(job_id, algs, impl, runs, warmup, notes):
    total = (warmup + runs) * len(algs)
    prog = STATE["progress"]
    prog.update(message="starting", done_steps=0, total_steps=total, current_algorithm=algs[0])

    def progress(msg):
        with LOCK:
            prog["message"] = msg
            prog["done_steps"] = min(total, prog["done_steps"] + 1)
            m2 = re.match(r"warmup (\w+) (\d+)/(\d+)", msg) or re.match(r"run \d+/\d+ (\w+):", msg)
            if m2 and m2.group(1) in algs:
                cur = m2.group(1)
                finished = msg.startswith("run")  # warmup msgs are emitted before the work
                prog["current_algorithm"] = algs[(algs.index(cur) + 1) % len(algs)] if finished else cur
    try:
        rec = benchmark.run_benchmark(G=GRAPH, algorithms=algs, impl=impl, runs=runs,
                                      warmup=warmup, notes=notes, progress=progress)
        with LOCK:
            benchmark.save_record(rec)
            STATE["last_record_id"] = rec["run_id"]
            prog.update(message="done", done_steps=total, current_algorithm=None)
    except Exception as e:  # noqa: BLE001
        with LOCK:
            STATE["last_error"] = f"{type(e).__name__}: {e}"
    finally:
        with LOCK:
            STATE["busy"] = False


def validate_run(body):
    if not isinstance(body, dict):
        raise ValueError("body must be a JSON object")
    algs = body.get("algorithms", list(ALGORITHM_NAMES))
    if not isinstance(algs, list) or not algs or not all(isinstance(a, str) for a in algs):
        raise ValueError("algorithms must be a non-empty list")
    bad = [a for a in algs if a not in ALGORITHM_NAMES]
    if bad:
        raise ValueError(f"unknown algorithms: {bad}")
    algs = [a for a in ALGORITHM_NAMES if a in set(algs)]
    impl = body.get("impl", "networkx")
    if impl not in ("networkx", "local"):
        raise ValueError("impl must be 'networkx' or 'local'")
    def intval(k, lo, hi, d):
        v = body.get(k, d)
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            raise ValueError(f"{k} must be an integer in [{lo}, {hi}]")
        return v
    runs = intval("runs", 1, 50, 5)
    warmup = intval("warmup", 0, 5, 1)
    notes = body.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 500:
        raise ValueError("notes must be a string up to 500 chars")
    return algs, impl, runs, warmup, notes.strip()


def export_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["run_id", "timestamp", "impl", "algorithm", "rep", "time_s", "colors"])
    for r in benchmark.load_history():
        for res in r.get("results", []):
            for i, t in enumerate(res.get("times_s", []), 1):
                w.writerow([r.get("run_id"), r.get("timestamp"), r.get("impl"),
                            res.get("algorithm"), i, t, res.get("colors")])
    return out.getvalue()


def delete_record(run_id):
    path = benchmark.DEFAULT_HISTORY
    with LOCK:
        recs = benchmark.load_history(path)
        keep = [r for r in recs if r.get("run_id") != run_id]
        if len(keep) == len(recs):
            return False
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".history-", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            for r in keep:
                f.write(json.dumps(r) + "\n")
        os.replace(tmp, path)
        return True


class Handler(BaseHTTPRequestHandler):
    server_version = "GCDash/1.0"

    def log_message(self, fmt, *args):
        if "/api/status" not in (args[0] if args else ""):
            super().log_message(fmt, *args)

    def _send(self, code, data, ctype="application/json", extra=None):
        body = data if isinstance(data, bytes) else (
            data.encode() if isinstance(data, str) else json.dumps(data).encode())
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _static(self, urlpath):
        rel = "index.html" if urlpath in ("", "/") else urlpath.lstrip("/")
        from urllib.parse import unquote
        try:
            target = (STATIC / unquote(rel)).resolve()
            target.relative_to(STATIC)
        except (ValueError, OSError):
            return self._send(404, {"error": "not found"})
        if not target.is_file():
            return self._send(404, {"error": "not found"})
        self._send(200, target.read_bytes(), MIME.get(target.suffix, "application/octet-stream"))

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/history":
            with LOCK:
                return self._send(200, benchmark.load_history())
        if path == "/api/status":
            with LOCK:
                s = {k: v for k, v in STATE.items() if k != "started"}
                s["elapsed_s"] = time.time() - STATE["started"] if STATE["busy"] and STATE["started"] else None
                return self._send(200, s)
        if path == "/api/export.csv":
            return self._send(200, export_csv(), "text/csv; charset=utf-8",
                              {"Content-Disposition": 'attachment; filename="benchmark_samples.csv"'})
        if path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        self._static(path)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/run":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 100_000:
                raise ValueError("body too large")
            algs, impl, runs, warmup, notes = validate_run(json.loads(self.rfile.read(n) or b"{}"))
        except (ValueError, json.JSONDecodeError) as e:
            return self._send(400, {"error": str(e)})
        with LOCK:
            if STATE["busy"]:
                return self._send(409, {"error": "a benchmark is already running"})
            job_id = uuid.uuid4().hex[:12]
            STATE.update(busy=True, job_id=job_id, started=time.time(), last_error=None)
        threading.Thread(target=_job, args=(job_id, algs, impl, runs, warmup, notes),
                         daemon=True).start()
        self._send(202, {"job_id": job_id})

    def do_DELETE(self):
        m = re.fullmatch(r"/api/history/([A-Za-z0-9_-]+)", self.path.split("?")[0])
        if not m:
            return self._send(404, {"error": "not found"})
        if delete_record(m.group(1)):
            return self._send(200, {"deleted": m.group(1)})
        self._send(404, {"error": "no such record"})


def main():
    global GRAPH
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    a = p.parse_args()
    print("Loading county graph...", flush=True)
    GRAPH, _ = load_county_graph()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    srv.daemon_threads = True
    print(f"Dashboard running at http://{a.host}:{a.port}/  (Ctrl+C to stop)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
