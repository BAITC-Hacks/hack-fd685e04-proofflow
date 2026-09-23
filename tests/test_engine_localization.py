"""Human-facing engine text is Russian; calculation and API fields stay stable."""
from copy import deepcopy
from datetime import date, timedelta

from demo_data import build_demo
from engine import calculate


def test_demo_quantities_and_machine_fields_after_seasonal_correction():
    result = calculate(build_demo())
    quantities = {row["sku"]: row["recommended_quantity"] for row in result["rows"]}
    assert quantities == {
        # The level is now deseasonalized before trend fitting; these two
        # previous expectations included a duplicated seasonal uplift.
        "DEMO-GROW-02": 70,
        "DEMO-MOQ-07": 50,
        "DEMO-REPEAT-10": 5,
        "DEMO-SEASON-01": 0,
        "DEMO-CATEGORY-08": 45,
        "DEMO-SPIKE-04": 50,
        "DEMO-STOCKOUT-03": 82,
        "DEMO-LATE-06": 48,
        "DEMO-COLDSTART-09": 0,
        "DEMO-INBOUND-05": 0,
    }
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
