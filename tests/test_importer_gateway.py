"""Canonical JSON/CSV gateway checks, independent of partner workbook layouts."""

import json

import pytest

from demo_data import build_demo
from importer import import_files


def test_json_template_round_trip_without_raw_identifiers(tmp_path):
    source = tmp_path / "synthetic.json"
    source.write_text(json.dumps(build_demo(), ensure_ascii=False), encoding="utf-8")
    data = import_files([str(source)])
    assert len(data["products"]) == 10
    assert data["metadata"]["synthetic"] is True
    assert data["sales"][0]["client_id"].startswith("CID-")
    assert "SYNTH-CLIENT-" not in str(data["sales"])


def test_csv_sales_and_negative_return_are_separated(tmp_path):
    source = tmp_path / "sales.csv"
    source.write_text(
        "date;sku;warehouse;quantity;client_id;on_hand;lead_days\n"
        "2026-09-21;A;W;5;person@example.com;10;7\n"
        "2026-09-22;A;W;-1;person@example.com;10;7\n", encoding="utf-8")
    data = import_files([str(source)])
    assert len(data["sales"]) == 1
    assert data["products"][0]["on_hand"] == 10
    assert data["products"][0]["lead_days"] == 7
    assert data["sales"][0]["client_id"].startswith("CID-")
    assert "person@example.com" not in str(data)
    assert any("Отрицательные" in warning for warning in data["metadata"]["warnings"])


def test_bad_json_is_a_clear_validation_error(tmp_path):
    source = tmp_path / "broken.json"
    source.write_text('{"bad":', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        import_files([str(source)])
