"""Canonical, fully synthetic replenishment dataset for local demo/testing."""
from datetime import date, timedelta


AS_OF = date(2026, 9, 23)


def build_demo() -> dict:
    products = [
        {"sku": "DEMO-SEASON-01", "name": "Synthetic seasonal cable", "supplier": "DEMO-SUPPLIER-A", "category": "cable", "warehouse": "A", "unit": "m", "on_hand": 80, "lead_days": 12, "moq": 20, "pack_size": 10, "unit_price": 120},
        {"sku": "DEMO-GROW-02", "name": "Synthetic rising-demand relay", "supplier": "DEMO-SUPPLIER-A", "category": "switchgear", "warehouse": "A", "unit": "pcs", "on_hand": 35, "lead_days": 9, "growth": 0.08, "pack_size": 5, "unit_price": 850},
        {"sku": "DEMO-STOCKOUT-03", "name": "Synthetic stockout example", "supplier": "DEMO-SUPPLIER-B", "category": "cable", "warehouse": "A", "unit": "pcs", "on_hand": 18, "lead_days": 5, "pack_size": 2, "unit_price": 400},
        {"sku": "DEMO-SPIKE-04", "name": "Synthetic one-off client spike", "supplier": "DEMO-SUPPLIER-B", "category": "switchgear", "warehouse": "B", "unit": "pcs", "on_hand": 60, "lead_days": 10, "pack_size": 10, "unit_price": 630},
        {"sku": "DEMO-INBOUND-05", "name": "Synthetic timely inbound", "supplier": "DEMO-SUPPLIER-C", "category": "lighting", "warehouse": "A", "unit": "pcs", "on_hand": 25, "lead_days": 8, "pack_size": 5, "unit_price": 210},
        {"sku": "DEMO-LATE-06", "name": "Synthetic late inbound urgency", "supplier": "DEMO-SUPPLIER-C", "category": "lighting", "warehouse": "B", "unit": "pcs", "on_hand": 8, "lead_days": 14, "pack_size": 4, "unit_price": 190},
        {"sku": "DEMO-MOQ-07", "name": "Synthetic minimum order example", "supplier": "DEMO-SUPPLIER-A", "category": "fasteners", "warehouse": "A", "unit": "pcs", "on_hand": 12, "lead_days": 6, "moq": 50, "pack_size": 10, "unit_price": 35},
        {"sku": "DEMO-CATEGORY-08", "name": "Synthetic category policy example", "supplier": "DEMO-SUPPLIER-B", "category": "fasteners", "warehouse": "A", "unit": "pcs", "on_hand": 20, "lead_days": 7, "growth": 0.04, "pack_size": 5, "unit_price": 55},
        {"sku": "DEMO-COLDSTART-09", "name": "Synthetic no-history warning", "supplier": "DEMO-SUPPLIER-C", "category": "new", "warehouse": "A", "unit": "pcs", "on_hand": 0, "lead_days": 11, "pack_size": 1, "unit_price": 100},
        {"sku": "DEMO-REPEAT-10", "name": "Synthetic recurring client peak", "supplier": "DEMO-SUPPLIER-A", "category": "cable", "warehouse": "B", "unit": "m", "on_hand": 50, "lead_days": 6, "pack_size": 5, "unit_price": 80},
    ]
    sales = []
    start = AS_OF - timedelta(days=364)
    for p_idx, p in enumerate(products):
        if p["sku"] == "DEMO-COLDSTART-09":
            continue
        for offset in range(365):
            d = start + timedelta(days=offset)
            if p["sku"] == "DEMO-SEASON-01":
                qty = 3 if d.month in (11, 12, 1, 2) else 1
            elif p["sku"] == "DEMO-GROW-02":
                qty = 2 + offset // 90
            elif p["sku"] == "DEMO-STOCKOUT-03":
                qty = 4
                if AS_OF - timedelta(days=25) <= d <= AS_OF - timedelta(days=12):
                    qty = 0
            elif p["sku"] == "DEMO-SPIKE-04":
                qty = 3
            elif p["sku"] == "DEMO-INBOUND-05":
                qty = 2
            elif p["sku"] == "DEMO-LATE-06":
                qty = 2
            elif p["sku"] == "DEMO-MOQ-07":
                qty = 1
            elif p["sku"] == "DEMO-CATEGORY-08":
                qty = 2
            else:
                qty = 2
            if qty:
                client = f"SYNTH-CLIENT-{p_idx}-REGULAR"
                sales.append({"date": d.isoformat(), "sku": p["sku"], "warehouse": p["warehouse"],
                              "quantity": qty, "client_id": client})
    sales.append({"date": (AS_OF - timedelta(days=40)).isoformat(), "sku": "DEMO-SPIKE-04",
                  "warehouse": "B", "quantity": 300, "client_id": "SYNTH-CLIENT-ONE-OFF"})
    # A recurring, month-separated buyer peak is intentionally not removable.
    for days_ago in (150, 40):
        sales.append({"date": (AS_OF - timedelta(days=days_ago)).isoformat(), "sku": "DEMO-REPEAT-10",
                      "warehouse": "B", "quantity": 100, "client_id": "SYNTH-RECURRING-CLIENT"})
    return {
        "as_of": AS_OF.isoformat(),
        "products": products,
        "sales": sales,
        "stockouts": [{"sku": "DEMO-STOCKOUT-03", "warehouse": "A",
                        "start": (AS_OF - timedelta(days=25)).isoformat(),
                        "end": (AS_OF - timedelta(days=12)).isoformat()}],
        "inbound": [
            {"sku": "DEMO-INBOUND-05", "warehouse": "A", "quantity": 35,
             "eta": (AS_OF + timedelta(days=8)).isoformat()},
            {"sku": "DEMO-LATE-06", "warehouse": "B", "quantity": 80,
             "eta": (AS_OF + timedelta(days=28)).isoformat()},
        ],
        "category_policies": {
            "cable": {"growth": 0.03, "safety_days": 5},
            "switchgear": {"growth": 0.05, "safety_days": 8},
            "fasteners": {"growth": 0.12, "safety_days": 6},
        },
        "settings": {"review_days": 14, "safety_days": 7, "outlier_multiplier": 4.0},
        "metadata": {"source_label": "Synthetic demo fixtures — not customer/partner data",
                     "synthetic": True, "warnings": []},
    }
