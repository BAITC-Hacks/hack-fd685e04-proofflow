"""Human-facing engine text is Russian; calculation and API fields stay stable."""
from copy import deepcopy
from datetime import date, timedelta

from demo_data import build_demo
from engine import calculate


def test_demo_business_scenarios_and_machine_fields_remain_verifiable():
    result = calculate(build_demo())
    rows = {row["sku"]: row for row in result["rows"]}
    assert rows["DEMO-GROW-02"]["trend_factor"] > 1
    assert rows["DEMO-SEASON-01"]["seasonality_factor"] > 1
    assert rows["DEMO-STOCKOUT-03"]["lost_demand"] > 0
    assert rows["DEMO-SPIKE-04"]["excluded_quantity"] >= 300
    assert rows["DEMO-MOQ-07"]["recommended_quantity"] >= 50
    assert rows["DEMO-COLDSTART-09"]["recommended_quantity"] == 0
    assert rows["DEMO-INBOUND-05"]["recommended_quantity"] == 0
    assert all(row["urgency"] in {"critical", "high", "normal", "covered"}
               for row in result["rows"])
    assert all(row["breakdown"]["order_rounding"]["recommended"] == row["recommended_quantity"]
               for row in result["rows"])


def test_explanations_are_russian_and_include_actual_breakdown():
    result = calculate(build_demo())
    for row in result["rows"]:
        explanation = row["explanation"]
        assert "Прогноз спроса" in explanation
        assert "остаток" in explanation
        assert "поступления" in explanation
        assert "оценка упущенного спроса" in explanation
        assert "исключено выбросов" in explanation
        assert "Срочность" in explanation
        assert f"рекомендуем {row['recommended_quantity']:g}" in explanation
        assert f"максимальный дефицит по датам {row['breakdown']['order_rounding']['net_need']:.2f}" in explanation
        assert "Forecast" not in explanation
        assert "Synthetic=" not in explanation


def test_anomaly_and_warning_text_is_russian_without_customer_claim():
    data = deepcopy(build_demo())
    data["sales"].append({
        "date": (date.fromisoformat(data["as_of"]) - timedelta(days=5)).isoformat(),
        "sku": "DEMO-INBOUND-05", "warehouse": "A", "quantity": 500,
        "event_id": "ANONYMOUS-DOCUMENT",
    })
    data["inbound"].append({
        "sku": "DEMO-INBOUND-05", "warehouse": "A", "quantity": 10,
        "eta": data["as_of"],
    })
    result = calculate(data)
    row = next(r for r in result["rows"] if r["sku"] == "DEMO-INBOUND-05")
    assert row["excluded_events"]
    assert "Разовый выброс" in row["excluded_events"][0]["reason"]
    assert any("номером документа" in warning for warning in row["warnings"])
    assert any("не учтена в прогнозе" in warning for warning in result["warnings"])
    assert any("Нет истории продаж" in warning for warning in result["warnings"])
