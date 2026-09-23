"""Raw customer identities must never survive the HTTP calculation boundary."""

import os
import tempfile
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

import storage
from server import anonymize_sales_identifiers, app


def test_anonymization_is_stable_within_a_run_and_unlinkable_across_runs():
    rows = [{"client_id": "person@example.com", "event_id": "invoice-1"},
            {"client_id": "person@example.com", "event_id": "invoice-2"}]
    first = {"sales": [dict(row) for row in rows]}
    second = {"sales": [dict(row) for row in rows]}
    anonymize_sales_identifiers(first)
    anonymize_sales_identifiers(second)
    assert first["sales"][0]["client_id"] == first["sales"][1]["client_id"]
    assert first["sales"][0]["client_id"] != second["sales"][0]["client_id"]
    assert "person@example.com" not in str(first)
    assert "invoice-1" not in str(first)


def test_direct_calculate_never_returns_or_persists_a_raw_customer_name():
    as_of = date(2026, 9, 23)
    start = as_of - timedelta(days=39)
    sales = [{"date": (start + timedelta(days=i)).isoformat(), "sku": "S", "warehouse": "W",
              "quantity": 4, "client_id": "customer name <person@example.com>"} for i in range(40)]
    sales.append({"date": (as_of - timedelta(days=4)).isoformat(), "sku": "S", "warehouse": "W",
                  "quantity": 500, "client_id": "one-off real name"})
    dataset = {
        "as_of": as_of.isoformat(),
        "products": [{"sku": "S", "warehouse": "W", "supplier": "P", "category": "C",
                      "name": "Synthetic item", "on_hand": 0, "lead_days": 7}],
        "sales": sales, "stockouts": [], "inbound": [],
        "category_policies": {}, "settings": {}, "metadata": {"synthetic": True},
    }
    with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"PROOFFLOW_DATA_DIR": folder}):
        with TestClient(app) as client:
            response = client.post("/api/calculate", json={"dataset": dataset})
            assert response.status_code == 200, response.text
            run_id = response.json()["run_id"]
            detail = client.get(f"/api/runs/{run_id}/item", params={"sku": "S", "warehouse": "W"})
            assert detail.status_code == 200
            assert detail.json()["excluded_events"]
            content = str(detail.json()) + str(storage.load_run(run_id))
            assert "person@example.com" not in content
            assert "one-off real name" not in content
            assert "CID-" in content
