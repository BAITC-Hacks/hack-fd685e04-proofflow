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


def test_unconfirmed_numeric_price_is_excluded_from_all_monetary_totals(tmp_path, monkeypatch):
    monkeypatch.setenv("PROOFFLOW_DATA_DIR", str(tmp_path))
    products = [
        {"sku": "KNOWN", "warehouse": "W", "supplier": "Priced", "category": "C",
         "on_hand": 0, "lead_days": 0, "unit_price": 2.675,
         "provenance": {"on_hand": "observed", "lead_days": "observed", "unit_price": "observed"}},
        {"sku": "UNKNOWN", "warehouse": "W", "supplier": "Unpriced", "category": "C",
         "on_hand": 0, "lead_days": 0, "unit_price": 999,
         "provenance": {"on_hand": "observed", "lead_days": "observed", "unit_price": "missing"}},
    ]
    sales = [{"date": "2026-09-22", "sku": sku, "warehouse": "W", "quantity": 1}
             for sku in ("KNOWN", "UNKNOWN")]
    dataset = {"as_of": "2026-09-22", "products": products, "sales": sales,
               "settings": {"review_days": 1, "safety_days": 0},
               "metadata": {"synthetic": False}}
    with TestClient(app) as client:
        response = client.post("/api/calculate", json={"dataset": dataset})
        assert response.status_code == 200, response.text
        run = response.json()
        rows = {row["sku"]: row for row in run["rows"]}
        assert rows["KNOWN"]["price_known"] is True
        assert rows["UNKNOWN"]["price_known"] is False
        assert rows["UNKNOWN"]["recommended_quantity"] > 0
        assert rows["UNKNOWN"]["amount"] is None
        assert run["summary"]["total_amount"] == rows["KNOWN"]["amount"]
        assert run["summary"]["unpriced_order_lines"] == 1
        assert run["summary"]["total_amount_complete"] is False
        groups = {group["supplier"]: group for group in run["supplier_groups"]}
        assert groups["Priced"]["total_amount"] == rows["KNOWN"]["amount"]
        assert groups["Unpriced"]["total_amount"] == 0
        evidence = client.get(f"/api/runs/{run['run_id']}/evidence")
        assert evidence.status_code == 200
        report = evidence.json()
        assert report["reconciliation"]["status"] == "pass"
        assert report["recommended"]["known_amount"] == "2.68"
        assert report["recommended"]["unpriced_order_lines"] == 1
        exported = client.get(f"/api/runs/{run['run_id']}/export?format=csv")
        lines = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig")), delimiter=";"))
        unknown_line = next(line for line in lines[1:] if line[3] == "UNKNOWN")
        assert unknown_line[8:10] == ["", ""]
