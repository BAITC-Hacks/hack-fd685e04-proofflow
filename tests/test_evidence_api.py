"""Downloaded evidence for a stored synthetic decision and its human approval."""
import hashlib
import json
import pytest

from fastapi.testclient import TestClient

import storage
from server import app


def test_evidence_download_tracks_manager_edit_without_exposing_events(tmp_path, monkeypatch):
    monkeypatch.setenv("PROOFFLOW_DATA_DIR", str(tmp_path))
    storage.save_run({
        "run_id": "evidence-synthetic", "source_synthetic": True,
        "source_label": "Synthetic API evidence", "locale": "kk",
        "rows": [{"sku": "A", "warehouse": "W", "supplier": "S", "recommended_quantity": 2,
                  "unit_price": 1.25, "price_known": True, "amount": 2.5,
                  "excluded_events": [{"client_id": "PRIVATE-CLIENT", "event_id": "PRIVATE-EVENT"}]}],
        "summary": {"items": 1, "order_lines": 1, "total_amount": 2.5, "unpriced_order_lines": 0},
        "supplier_groups": [{"supplier": "S", "order_lines": 1, "total_amount": 2.5}],
    })
    with TestClient(app) as client:
        draft_response = client.get("/api/runs/evidence-synthetic/evidence")
        assert draft_response.status_code == 200
        assert draft_response.headers["content-type"] == "application/json"
        assert "attachment;" in draft_response.headers["content-disposition"]
        assert draft_response.headers["cache-control"] == "no-store"
        draft = draft_response.json()
        assert draft["status"] == "draft" and draft["reconciliation"]["status"] == "pass"
        assert "PRIVATE-CLIENT" not in draft_response.text and "PRIVATE-EVENT" not in draft_response.text
        approved = client.post("/api/runs/evidence-synthetic/approve", json={
            "reviewer": "Private Manager", "quantities": {"W::A": 4},
        })
        assert approved.status_code == 200
        report_response = client.get("/api/runs/evidence-synthetic/evidence")
        assert report_response.status_code == 200
        report = report_response.json()
        assert report["status"] == "approved" and report["changed_lines"] == 1
        assert report["recommended"]["known_amount"] == "2.50"
        assert report["final"]["known_amount"] == "5.00"
        assert report["approval"]["supplier_sent"] is False
        assert report["fingerprint_sha256"] != draft["fingerprint_sha256"]
        assert "Private Manager" not in report_response.text
        fingerprint = report.pop("fingerprint_sha256")
        canonical = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        assert fingerprint == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_evidence_download_of_missing_run_is_404(tmp_path, monkeypatch):
    monkeypatch.setenv("PROOFFLOW_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        response = client.get("/api/runs/not-present/evidence")
        assert response.status_code == 404


@pytest.mark.parametrize("filename", ["broken.zip", "IEK-broken.xlsx"])
def test_corrupt_partner_archive_returns_actionable_422(tmp_path, monkeypatch, filename):
    monkeypatch.setenv("PROOFFLOW_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/import", files={"files": (filename, b"not a ZIP archive")})
        assert response.status_code == 422
        assert "повреждён" in response.json()["detail"]
        assert storage.load_dataset() is None
