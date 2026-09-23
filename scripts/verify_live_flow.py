"""Verify a real localhost server with isolated disposable application data."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="Optional local partner files/directories; default is synthetic demo")
    parser.add_argument("--locale", choices=("ru", "kk", "en"), default="ru")
    args = parser.parse_args()
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    with TemporaryDirectory(prefix="proofflow-acceptance-") as temporary:
        env = dict(os.environ, PROOFFLOW_DATA_DIR=temporary)
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        started = time.perf_counter()
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=180) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Server exited before its health check")
                    try:
                        response = client.get("/api/health")
                        response.raise_for_status()
                        break
                    except httpx.TransportError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Server did not become healthy")
                for route in ("/", "/app.js", "/styles.css"):
                    client.get(route).raise_for_status()
                print("Server and interface assets: OK", flush=True)
                if args.files:
                    paths = []
                    for value in args.files:
                        path = Path(value)
                        if path.is_dir():
                            paths.extend(sorted(path.glob("*.xlsx")))
                        elif path.is_file():
                            paths.append(path)
                        else:
                            raise ValueError(f"Input does not exist: {path}")
                    if not paths:
                        raise ValueError("No input files found")
                    with ExitStack() as handles:
                        files = [("files", (path.name, handles.enter_context(path.open("rb")))) for path in paths]
                        loaded = client.post("/api/import", files=files)
                else:
                    loaded = client.post("/api/demo")
                loaded.raise_for_status()
                preview = loaded.json()["dataset"]
                print("Input loaded; calculating...", flush=True)
                calculated = client.post("/api/calculate", json={"settings": {"locale": args.locale}})
                calculated.raise_for_status()
                run = calculated.json()
                if not run["rows"]:
                    raise AssertionError("Calculation returned no rows")
                row = run["rows"][0]
                client.get(f"/api/runs/{run['run_id']}/item", params={"sku": row["sku"], "warehouse": row["warehouse"]}).raise_for_status()
                approval = client.post(f"/api/runs/{run['run_id']}/approve", json={
                    "reviewer": "Local acceptance check", "quantities": {},
                    "acknowledge_missing_inputs": bool(args.files),
                })
                approval.raise_for_status()
                assert approval.json()["supplier_sent"] is False
                for fmt in ("csv", "xlsx"):
                    exported = client.get(f"/api/runs/{run['run_id']}/export", params={"format": fmt})
                    exported.raise_for_status()
                    assert exported.content
                print(json.dumps({
                    "status": "passed", "synthetic": not bool(args.files), "locale": args.locale,
                    "input_counts": preview["metadata"]["record_counts"],
                    "result_items": len(run["rows"]), "order_lines": run["summary"]["order_lines"],
                    "seconds": round(time.perf_counter() - started, 3),
                    "scope": "live localhost HTTP, import, calculation, detail, approval, CSV/XLSX; no supplier dispatch",
                }, ensure_ascii=False, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
