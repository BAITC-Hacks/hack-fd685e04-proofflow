"""Local-host and real-data approval boundaries."""

import csv
import io
import os
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient

from server import app


def _real_missing_dataset():
    return {
        "as_of": "2026-09-23",
        "products": [{
            "sku": "A", "warehouse": "W", "supplier": "S", "category": "C",
            "on_hand": 0, "lead_days": 0, "unit_price": 0,
            "provenance": {"on_hand": "missing", "lead_days": "missing", "unit_price": "missing"},
        }],
        "sales": [{"date": "2026-09-22", "sku": "A", "warehouse": "W",
                   "quantity": 10, "event_id": "anonymous-document"}],
        "stockouts": [], "inbound": [], "metadata": {"synthetic": False},
    }


def test_host_allowlist_rejects_rebinding_reads_and_writes():
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/health", headers={"Host": "127.0.0.1:8000"}).status_code == 200
        assert client.get("/api/health", headers={"Host": "localhost:8000"}).status_code == 200
        assert client.get("/api/health", headers={"Host": "rebind.example"}).status_code == 403
        assert client.post("/api/demo", headers={"Host": "rebind.example"}).status_code == 403
        assert client.get("/api/health", headers={"Host": "localhost.evil.example"}).status_code == 403
        assert client.get("/api/health", headers={"Host": "localhost:bad"}).status_code == 403
        assert client.post("/api/demo", headers={"Host": "localhost:8000", "Origin": "http://["}).status_code == 403


def test_real_unverified_stock_and_lead_require_explicit_acknowledgement():
    with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"PROOFFLOW_DATA_DIR": folder}):
        with TestClient(app) as client:
            calculated = client.post("/api/calculate", json={"dataset": _real_missing_dataset()})
            assert calculated.status_code == 200, calculated.text
            run = calculated.json()
            assert run["source_synthetic"] is False
            assert run["rows"][0]["recommended_quantity"] > 0
            assert run["rows"][0]["input_provenance"]["on_hand"] == "missing"
            assert run["rows"][0]["price_known"] is False
            exported = client.get(f"/api/runs/{run['run_id']}/export?format=csv")
            assert exported.status_code == 200
            export_row = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig")), delimiter=";"))[1]
            assert export_row[8:10] == ["", ""]
            url = f"/api/runs/{run['run_id']}/approve"
            refused = client.post(url, json={"reviewer": "Manager"})
            assert refused.status_code == 422
            assert "не подтверждены" in refused.json()["detail"]
            accepted = client.post(url, json={"reviewer": "Manager", "acknowledge_missing_inputs": True})
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["acknowledged_missing_inputs"] is True


def test_synthetic_demo_approval_does_not_require_real_data_acknowledgement():
    with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"PROOFFLOW_DATA_DIR": folder}):
        with TestClient(app) as client:
            assert client.post("/api/demo").status_code == 200
            calculated = client.post("/api/calculate", json={})
            assert calculated.status_code == 200, calculated.text
            run = calculated.json()
            approved = client.post(f"/api/runs/{run['run_id']}/approve", json={"reviewer": "Demo manager"})
            assert approved.status_code == 200, approved.text
            assert approved.json()["acknowledged_missing_inputs"] is False
