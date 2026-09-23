"""Local SQLite snapshots. Parameterised queries; no network access."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def data_directory():
    path = Path(os.environ.get("PROOFFLOW_DATA_DIR", Path(__file__).parent / "private_data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def database():
    connection = sqlite3.connect(data_directory() / "proofflow.sqlite3", timeout=30)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS approvals (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS run_items (run_id TEXT NOT NULL, item_key TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,item_key))")
    connection.commit()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def save_dataset(dataset):
    # Keep a small separate record for page reloads; parsing the full sales
    # archive just to render the product controls would waste time and memory.
    preview = {key: value for key, value in dataset.items() if key not in {"sales", "stockouts", "inbound"}}
    preview["_preview"] = True
    preview["metadata"] = {
        **dataset.get("metadata", {}),
        "record_counts": {key: len(dataset.get(key, [])) for key in ("products", "sales", "stockouts", "inbound")},
    }
    with database() as db:
        db.execute("INSERT INTO state(key,payload) VALUES('dataset',?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload", (encode(dataset),))
        db.execute("INSERT INTO state(key,payload) VALUES('dataset_preview',?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload", (encode(preview),))


def load_dataset():
    with database() as db:
        found = db.execute("SELECT payload FROM state WHERE key='dataset'").fetchone()
    return json.loads(found[0]) if found else None


def load_dataset_preview():
    with database() as db:
        found = db.execute("SELECT payload FROM state WHERE key='dataset_preview'").fetchone()
    return json.loads(found[0]) if found else None


def save_run(run):
    from exports import row_key
    payload = dict(run)
    payload["rows"] = [compact_row(row) for row in run["rows"]]
    # Never persist duplicate row objects inside supplier summaries.
    payload["supplier_groups"] = [
        {k: v for k, v in group.items() if k != "lines"}
        for group in run.get("supplier_groups", [])
    ]
    with database() as db:
        db.execute("INSERT INTO runs(id,payload) VALUES(?,?)", (run["run_id"], encode(payload)))
        db.executemany("INSERT INTO run_items(run_id,item_key,payload) VALUES(?,?,?)",
                       ((run["run_id"], row_key(row), encode(row)) for row in run["rows"]))


def compact_row(row):
    result = {k: v for k, v in row.items() if k not in {"history", "forecast", "excluded_events"}}
    result["detail_available"] = True
    result["excluded_event_count"] = len(row.get("excluded_events", []))
    return result


def load_item(run_id, key):
    with database() as db:
        item = db.execute("SELECT payload FROM run_items WHERE run_id=? AND item_key=?", (run_id, key)).fetchone()
    return json.loads(item[0]) if item else None


def load_run(run_id):
    with database() as db:
        found = db.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
        approval = db.execute("SELECT payload FROM approvals WHERE run_id=?", (run_id,)).fetchone()
    if not found:
        return None
    result = json.loads(found[0])
    result["approval"] = json.loads(approval[0]) if approval else None
    return result


def save_approval(run_id, approval):
    with database() as db:
        db.execute("INSERT INTO approvals(run_id,payload) VALUES(?,?)", (run_id, encode(approval)))
