"""Boundary and safety regressions for the local procurement workflow.

The real partner files are intentionally never loaded by this test module.
"""

import csv
import io
import os
import tempfile
import unittest
from datetime import date, timedelta
from time import perf_counter
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import load_workbook

import exports
import storage
from engine import calculate
from server import app


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"PROOFFLOW_DATA_DIR": self.temp.name})
        self.env.start()
        self.client = TestClient(app)
        self.run = {
            "run_id": "synthetic-security-run", "as_of": "2026-09-23",
            "source_label": "Synthetic security fixture", "warnings": [],
            "rows": [{"sku": "SKU", "name": "Synthetic product", "warehouse": "WH",
                      "supplier": "SYNTHETIC", "category": "Test", "unit": "pcs",
                      "recommended_quantity": 4, "unit_price": 2.0,
                      "urgency": "normal", "explanation": "Synthetic fixture"}],
        }
        storage.save_run(self.run)

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.temp.cleanup()

    def test_spreadsheet_exports_never_emit_executable_untrusted_cells(self):
        for marker in ("=", "+", "-", "@", "  ="):
            with self.subTest(marker=marker):
                value = marker + 'HYPERLINK("https://example.invalid","x")'
                self.run["rows"][0]["name"] = value
                self.run["run_id"] = "formula-" + str(ord(marker[0]))
                storage.save_run(self.run)
                csv_response = self.client.get(f"/api/runs/{self.run['run_id']}/export?format=csv")
                self.assertEqual(csv_response.status_code, 200)
                csv_row = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig")), delimiter=";"))[1]
                self.assertEqual(csv_row[4], "'" + value)
                xlsx_response = self.client.get(f"/api/runs/{self.run['run_id']}/export?format=xlsx")
                self.assertEqual(xlsx_response.status_code, 200)
                book = load_workbook(io.BytesIO(xlsx_response.content), data_only=False)
                cell = book["Заказы поставщикам"]["E2"]
                self.assertEqual(cell.data_type, "s")
                self.assertEqual(cell.value, "'" + value)
                book.close()

    def test_approval_rejects_nonfinite_unknown_and_out_of_range_quantities(self):
        invalid = (
            {"WH::SKU": -1}, {"WH::SKU": 1e13}, {"WH::SKU": "NaN"},
            {"WH::UNKNOWN": 1},
        )
        for quantities in invalid:
            with self.subTest(quantities=quantities):
                response = self.client.post("/api/runs/synthetic-security-run/approve",
                                            json={"reviewer": "Synthetic reviewer", "quantities": quantities})
                self.assertEqual(response.status_code, 422, response.text)
        self.assertIsNone(storage.load_run("synthetic-security-run")["approval"])

    def test_unknown_request_fields_and_cross_origin_mutation_rejected(self):
        self.assertEqual(self.client.post("/api/calculate", json={"unexpected": 1}).status_code, 422)
        self.assertEqual(self.client.post("/api/runs/synthetic-security-run/approve",
                                          json={"reviewer": "Test", "send_to_supplier": True}).status_code, 422)
        response = self.client.post("/api/runs/synthetic-security-run/approve",
                                    headers={"Origin": "https://attacker.example"},
                                    json={"reviewer": "Test"})
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(storage.load_run("synthetic-security-run")["approval"])

    def test_csv_export_is_not_an_automatic_supplier_dispatch(self):
        self.assertFalse(hasattr(exports, "send_order"))
        response = self.client.get("/api/runs/synthetic-security-run/export?format=csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Черновик", response.content.decode("utf-8-sig"))
        self.assertIsNone(storage.load_run("synthetic-security-run")["approval"])


class SyntheticScaleBenchmark(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("PROOFFLOW_PERF_BENCH") == "1", "opt-in scale benchmark")
    def test_250k_transactions_and_2500_skus(self):
        """Use a fixed synthetic workload; print timing, do not assert a machine-specific SLA."""
        as_of = date(2026, 9, 23)
        dates = [(as_of - timedelta(days=99 - day)).isoformat() for day in range(100)]
        products = []
        sales = []
        for sku_index in range(2500):
            sku = f"SYNTH-{sku_index:05d}"
            products.append({"sku": sku, "warehouse": "WH", "supplier": f"SUP-{sku_index % 25}",
                             "category": "Synthetic", "on_hand": 10, "lead_days": 7,
                             "unit_price": 5, "pack_size": 1})
            sales.extend({"date": day, "sku": sku, "warehouse": "WH", "quantity": 2,
                          "client_id": f"SYNTH-C-{sku_index % 100}"} for day in dates)
        dataset = {"as_of": as_of.isoformat(), "products": products, "sales": sales,
                   "metadata": {"synthetic": True, "source_label": "250k synthetic scale test"}}
        start = perf_counter()
        result = calculate(dataset)
        duration = perf_counter() - start
        self.assertEqual(len(result["rows"]), 2500)
        self.assertEqual(len(sales), 250_000)
        self.assertEqual(len(result["supplier_groups"]), 25)
        print(f"\nSYNTHETIC_250K_ENGINE_SECONDS={duration:.3f}; products=2500; sales=250000")


if __name__ == "__main__":
    unittest.main()
