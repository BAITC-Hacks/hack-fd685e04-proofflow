"""Canonical JSON/CSV gateway checks, independent of partner workbook layouts."""

import json

import pytest

from demo_data import build_demo
from engine import calculate
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


def test_catalog_metadata_is_merged_independently_of_file_order(tmp_path):
    sales = tmp_path / "sales.csv"
    sales.write_text("date;sku;warehouse;quantity;name;supplier;category\n"
                     "2026-09-21;A;W;5;Old name;Old supplier;Old category\n"
                     "2026-09-22;A;W;5;;;;\n", encoding="utf-8")
    catalog = tmp_path / "products.csv"
    catalog.write_text("sku;warehouse;name;supplier;category;unit;on_hand;lead_days;unit_price;growth\n"
                       "A;W;Cable;Supplier;Electrical;m;10;7;2.5;0.4\n", encoding="utf-8")
    left = import_files([str(sales), str(catalog)])
    right = import_files([str(catalog), str(sales)])
    assert left == right
    product = left["products"][0]
    assert product["name"] == "Cable" and product["supplier"] == "Supplier"
    assert product["category"] == "Electrical" and product["unit"] == "m"
    assert product["growth"] == 0.4
    assert product["provenance"]["growth"] == "observed"
    assert product["provenance"]["on_hand"] == "observed"


def test_csv_growth_changes_replenishment_quantity(tmp_path):
    source = tmp_path / "sales.csv"
    source.write_text("date;sku;quantity;on_hand;lead_days;growth\n"
                      "2026-09-20;A;10;0;7;0.5\n"
                      "2026-09-21;A;10;0;7;0.5\n"
                      "2026-09-22;A;10;0;7;0.5\n", encoding="utf-8")
    data = import_files([str(source)])
    growing = calculate(data)["rows"][0]
    data["products"][0]["growth"] = 0
    baseline = calculate(data)["rows"][0]
    assert growing["growth_factor"] == 1.5
    assert growing["recommended_quantity"] > baseline["recommended_quantity"]


def test_blank_catalog_cells_preserve_observed_values(tmp_path):
    sales = tmp_path / "sales.csv"
    sales.write_text("date;sku;quantity;unit_price;lead_days\n2026-09-22;A;10;2.5;7\n", encoding="utf-8")
    catalog = tmp_path / "products.csv"
    catalog.write_text("sku;name;unit_price;lead_days\nA;Cable; ;\n", encoding="utf-8")
    data = import_files([str(sales), str(catalog)])
    product = data["products"][0]
    assert product["unit_price"] == 2.5 and product["lead_days"] == 7
    assert product["provenance"]["unit_price"] == "observed"


def test_conflicting_catalog_values_are_rejected_in_both_orders(tmp_path):
    paths = []
    for name, supplier in (("one", "First"), ("two", "Second")):
        path = tmp_path / f"{name}.csv"
        path.write_text(f"sku;supplier\nA;{supplier}\n", encoding="utf-8")
        paths.append(str(path))
    for order in (paths, list(reversed(paths))):
        with pytest.raises(ValueError, match="Conflicting CSV product supplier"):
            import_files(order)


def test_authoritative_catalog_resolves_conflicting_transaction_metadata(tmp_path):
    sales = tmp_path / "sales.csv"
    sales.write_text("date;sku;quantity;supplier\n"
                     "2026-09-22;A;5;Legacy1\n2026-09-22;A;5;Legacy2\n", encoding="utf-8")
    catalog = tmp_path / "products.csv"
    catalog.write_text("sku;supplier\nA;Current\n", encoding="utf-8")
    for order in ([str(sales), str(catalog)], [str(catalog), str(sales)]):
        assert import_files(order)["products"][0]["supplier"] == "Current"
