"""Unknown price must not masquerade as a real zero in supplier files."""

import csv
import io

from openpyxl import load_workbook

import exports


def _run(price_known):
    return {
        "run_id": "synthetic-export-provenance", "as_of": "2026-09-23",
        "source_label": "Synthetic export fixture", "warnings": [], "approval": None,
        "rows": [{"sku": "A", "warehouse": "W", "supplier": "S", "name": "Test A",
                  "unit": "pcs", "recommended_quantity": 5, "unit_price": 0,
                  "price_known": price_known, "urgency": "normal", "explanation": "Test"}],
    }


def test_unknown_price_exports_blank_not_zero():
    run = _run(False)
    csv_rows = list(csv.reader(io.StringIO(exports.to_csv(run).decode("utf-8-sig")), delimiter=";"))
    assert csv_rows[1][8:10] == ["", ""]
    workbook = load_workbook(io.BytesIO(exports.to_xlsx(run)), data_only=True)
    assert workbook["Заказы поставщикам"]["I2"].value in (None, "")
    assert workbook["Заказы поставщикам"]["J2"].value in (None, "")
    assert any(
        "отсутствие подтверждённой цены" in str(cell.value)
        for cell in workbook["Методология"]["B"]
    )
    workbook.close()


def test_documented_zero_price_stays_zero():
    run = _run(True)
    csv_rows = list(csv.reader(io.StringIO(exports.to_csv(run).decode("utf-8-sig")), delimiter=";"))
    assert csv_rows[1][8] == "0"
    assert csv_rows[1][9] == "0.0"
