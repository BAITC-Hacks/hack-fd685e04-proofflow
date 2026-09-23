"""Synthetic audit cases; no partner source data."""
from copy import deepcopy
import hashlib
import json

import pytest

from evidence import build_evidence


def fixture():
    return {
        "run_id": "synthetic-evidence", "source_label": "Synthetic", "source_synthetic": True,
        "locale": "kk", "settings": {"locale": "kk", "review_days": 14}, "warnings": ["limitation"],
        "rows": [
            {"sku": "A", "warehouse": "W", "supplier": "S", "unit": "m",
             "recommended_quantity": 2, "unit_price": 1.25, "price_known": True,
             "amount": 2.5, "warnings": ["check stock"],
             "excluded_events": [{"client_id": "PRIVATE", "event_id": "SECRET"}]},
            {"sku": "B", "warehouse": "W", "supplier": "S", "unit": "pcs",
             "recommended_quantity": 3, "unit_price": 0, "price_known": False, "amount": 0},
        ],
        "summary": {"items": 2, "order_lines": 2, "total_amount": 2.5, "unpriced_order_lines": 1},
        "supplier_groups": [{"supplier": "S", "order_lines": 2, "total_amount": 2.5}],
    }


def test_unknown_price_is_not_zero_and_sensitive_events_are_omitted():
    report = build_evidence(fixture())
    assert report["recommended"]["known_amount"] == "2.50"
    assert report["recommended"]["unpriced_order_lines"] == 1
    assert report["recommended"]["amount_complete"] is False
    assert report["lines"][1]["unit_price"] is None
    assert report["lines"][0]["excluded_event_count"] == 1
    assert "PRIVATE" not in json.dumps(report) and "SECRET" not in json.dumps(report)
    assert report["reconciliation"]["status"] == "pass"


def test_human_changes_reconcile_against_original_summary():
    run = fixture()
    run["approval"] = {"approval_id": "approval", "quantities": {"W::A": 4, "W::B": 0},
                       "reviewer": "Private reviewer", "supplier_sent": False}
    report = build_evidence(run)
    assert report["status"] == "approved" and report["changed_lines"] == 2
    assert report["recommended"]["known_amount"] == "2.50"
    assert report["final"]["known_amount"] == "5.00"
    assert report["final"]["amount_complete"] is True
    assert report["final"]["order_lines"] == 1
    assert report["reconciliation"]["status"] == "pass"
    assert "Private reviewer" not in json.dumps(report)


def test_summary_and_supplier_mismatch_are_detected():
    run = fixture()
    run["summary"]["order_lines"] = 1
    run["supplier_groups"][0]["total_amount"] = 8
    report = build_evidence(run)
    failed = {c["check"] for c in report["reconciliation"]["checks"] if c["status"] == "fail"}
    assert failed == {"summary.order_lines", "supplier:S:total_amount"}


def test_fingerprint_is_canonical_and_tracks_approval_changes():
    run = fixture()
    original = deepcopy(run)
    first = build_evidence(run)
    run["rows"].reverse()
    assert first == build_evidence(run)
    fingerprint = first.pop("fingerprint_sha256")
    encoded = json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert fingerprint == hashlib.sha256(encoded.encode()).hexdigest()
    original["approval"] = {"quantities": {"W::A": 4, "W::B": 3}}
    assert build_evidence(original)["fingerprint_sha256"] != fingerprint


def test_missing_summary_is_explicitly_partial():
    run = fixture()
    del run["summary"]
    del run["supplier_groups"]
    assert build_evidence(run)["reconciliation"]["status"] == "partial"


def test_observed_zero_price_is_known():
    run = fixture()
    run["rows"][1]["price_known"] = True
    run["summary"]["unpriced_order_lines"] = 0
    report = build_evidence(run)
    assert report["recommended"]["amount_complete"] is True
    assert report["lines"][1]["final_amount"] == "0.00"


def test_decimal_half_up_rounding_detects_inconsistent_stored_amount():
    run = fixture()
    run["rows"] = [dict(run["rows"][0], recommended_quantity=1, unit_price=2.675, amount=2.67)]
    run.pop("summary")
    run.pop("supplier_groups")
    report = build_evidence(run)
    assert report["recommended"]["known_amount"] == "2.68"
    assert report["reconciliation"]["status"] == "fail"
    assert report["reconciliation"]["checks"][0]["check"] == "line_amount:W::A"


@pytest.mark.parametrize("quantity", [-1, float("nan"), float("inf"), True])
def test_invalid_quantities_are_rejected(quantity):
    run = fixture()
    run["rows"][0]["recommended_quantity"] = quantity
    with pytest.raises(ValueError):
        build_evidence(run)


def test_incomplete_or_unknown_approval_rows_are_rejected():
    for quantities in ({"W::A": 2}, {"W::A": 2, "W::B": 3, "W::C": 9}):
        run = fixture()
        run["approval"] = {"quantities": quantities}
        with pytest.raises(ValueError):
            build_evidence(run)


def test_duplicate_rows_rejected_and_input_is_not_mutated():
    run = fixture()
    before = deepcopy(run)
    build_evidence(run)
    assert run == before
    run["rows"].append(deepcopy(run["rows"][0]))
    with pytest.raises(ValueError):
        build_evidence(run)
