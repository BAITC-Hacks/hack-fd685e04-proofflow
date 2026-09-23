"""Requirement-linked regression checks for the new procurement algorithm."""
from copy import deepcopy
from datetime import date, timedelta

import pytest

from demo_data import build_demo
from engine import calculate


AS_OF = date(2026, 9, 23)


def sample(*, days=90, quantity=4, on_hand=10, lead_days=7):
    start = AS_OF - timedelta(days=days - 1)
    return {
        "as_of": AS_OF.isoformat(),
        "products": [{"sku": "A", "name": "Test A", "supplier": "S1", "category": "cable",
                      "warehouse": "W", "on_hand": on_hand, "lead_days": lead_days,
                      "unit_price": 10, "pack_size": 1}],
        "sales": [{"date": (start + timedelta(days=i)).isoformat(), "sku": "A",
                   "warehouse": "W", "quantity": quantity, "client_id": "REGULAR"}
                  for i in range(days)],
        "stockouts": [], "inbound": [],
        "settings": {"review_days": 14, "safety_days": 7},
        "category_policies": {}, "metadata": {"synthetic": True},
    }


def row(dataset):
    return calculate(dataset)["rows"][0]


def test_stock_and_category_policy_change_quantity():
    original = sample()
    base = row(original)
    stocked = deepcopy(original)
    stocked["products"][0]["on_hand"] += 70
    assert row(stocked)["recommended_quantity"] < base["recommended_quantity"]
    grown = deepcopy(original)
    grown["category_policies"]["cable"] = {"growth": .25, "safety_days": 12}
    assert row(grown)["recommended_quantity"] > base["recommended_quantity"]


def test_dated_inbound_reduces_order_but_late_receipt_cannot_hide_early_shortfall():
    data = sample(on_hand=5)
    base = row(data)
    early = deepcopy(data)
    early["inbound"] = [{"sku": "A", "warehouse": "W", "quantity": 60,
                         "eta": (AS_OF + timedelta(days=1)).isoformat()}]
    early_result = row(early)
    assert early_result["recommended_quantity"] < base["recommended_quantity"]
    late = deepcopy(data)
    late["inbound"] = [{"sku": "A", "warehouse": "W", "quantity": 300,
                        "eta": (AS_OF + timedelta(days=27)).isoformat()}]
    late_result = row(late)
    assert late_result["recommended_quantity"] > 0
    assert late_result["breakdown"]["order_rounding"]["end_horizon_gap"] == 0
    assert late_result["stockout_date"] == (AS_OF + timedelta(days=2)).isoformat()


def test_explicit_stockout_imputes_lost_demand_and_raises_recommendation():
    data = sample(days=90, on_hand=0)
    zero_start = AS_OF - timedelta(days=18)
    zero_end = AS_OF - timedelta(days=7)
    for sale in data["sales"]:
        if zero_start <= date.fromisoformat(sale["date"]) <= zero_end:
            sale["quantity"] = 0
    observed_only = row(data)
    with_intervals = deepcopy(data)
    with_intervals["stockouts"] = [{"sku": "A", "warehouse": "W",
                                    "start": zero_start.isoformat(), "end": zero_end.isoformat()}]
    adjusted = row(with_intervals)
    assert adjusted["lost_demand"] > 0
    assert adjusted["recommended_quantity"] > observed_only["recommended_quantity"]
    assert sum(h["lost_demand"] for h in adjusted["history"]) == pytest.approx(adjusted["lost_demand"])


def test_isolated_client_order_spike_removed_but_sustained_growth_retained():
    data = sample(days=90)
    base = row(data)
    anomalous = deepcopy(data)
    anomalous["sales"].append({"date": (AS_OF - timedelta(days=4)).isoformat(),
                               "sku": "A", "warehouse": "W", "quantity": 500,
                               "client_id": "ONE_TIME"})
    with_spike = row(anomalous)
    assert with_spike["excluded_quantity"] >= 500
    assert with_spike["recommended_quantity"] == base["recommended_quantity"]
    assert len(with_spike["excluded_events"]) == 1
    growing = sample(days=90)
    for i, sale in enumerate(growing["sales"]):
        sale["quantity"] = 2 + i // 20
    grow_result = row(growing)
    assert grow_result["trend_factor"] > 1
    assert grow_result["excluded_quantity"] == 0


def test_anonymous_aggregate_cannot_be_called_a_known_client_spike():
    data = sample(days=40)
    data["sales"].append({"date": (AS_OF - timedelta(days=4)).isoformat(),
                          "sku": "A", "warehouse": "W", "quantity": 500})
    assert row(data)["excluded_quantity"] == 0


def test_event_id_can_flag_one_off_order_without_claiming_customer_identity():
    data = sample(days=40)
    data["sales"].append({"date": (AS_OF - timedelta(days=4)).isoformat(),
                          "sku": "A", "warehouse": "W", "quantity": 500,
                          "event_id": "ANON-ORDER-1"})
    result = row(data)
    assert result["excluded_quantity"] >= 500
    assert any("номером документа, а не с идентификатором клиента" in w for w in result["warnings"])


def test_seasonality_is_non_neutral_and_future_date_specific():
    data = sample(days=730, quantity=1, on_hand=0)
    for sale in data["sales"]:
        if date.fromisoformat(sale["date"]).month in (9, 10):
            sale["quantity"] = 5
    result = row(data)
    assert result["seasonality_factor"] > 1
    assert result["forecast"][0]["seasonality_factor"] != 1


def test_supplier_groups_and_explanations_match_real_calculation():
    result = calculate(build_demo())
    assert len(result["rows"]) == 10
    assert result["summary"]["items"] == 10
    assert sum(group["order_lines"] for group in result["supplier_groups"]) == result["summary"]["order_lines"]
    for item in result["rows"]:
        assert any(group["supplier"] == item["supplier"] for group in result["supplier_groups"])
        assert str(item["recommended_quantity"]) in item["explanation"]
        assert item["breakdown"]["order_rounding"]["recommended"] == item["recommended_quantity"]
        assert len(item["history"]) <= 36


def test_future_receipt_is_not_silently_added_to_current_stock():
    data = sample(on_hand=0)
    data["inbound"] = [{"sku": "A", "warehouse": "W", "quantity": 300,
                        "eta": (AS_OF - timedelta(days=1)).isoformat()}]
    result = calculate(data)
    assert result["rows"][0]["inbound_quantity"] == 0
    assert any("не учтена в прогнозе" in w for w in result["warnings"])
