"""Resource limits reject pathological input before large forecast/history loops."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from engine import (MAX_HORIZON_DAYS, MAX_PRODUCTS, MAX_SALES,
                    calculate)
from server import app


AS_OF = date(2026, 9, 23)


def fixture():
    return {
        "as_of": AS_OF.isoformat(),
        "products": [{"sku": "A", "warehouse": "W", "supplier": "S",
                      "on_hand": 0, "lead_days": 10}],
        "sales": [{"date": (AS_OF - timedelta(days=30)).isoformat(),
                   "sku": "A", "warehouse": "W", "quantity": 2,
                   "client_id": "ANON"}],
        "stockouts": [], "inbound": [], "metadata": {"synthetic": True},
    }


def test_horizon_at_limit_is_valid_and_one_day_over_rejected():
    data = fixture()
    data["products"][0]["lead_days"] = MAX_HORIZON_DAYS - 21
    assert calculate(data)["rows"][0]["breakdown"]["horizon_days"] == MAX_HORIZON_DAYS
    data["products"][0]["lead_days"] += 1
    with pytest.raises(ValueError, match="horizon exceeds 730"):
        calculate(data)


def test_ten_calendar_years_allowed_but_older_history_rejected():
    data = fixture()
    data["sales"][0]["date"] = "2016-09-23"
    assert calculate(data)["rows"]
    data["sales"][0]["date"] = "2016-09-22"
    with pytest.raises(ValueError, match="more than 10 years"):
        calculate(data)
    data = fixture()
    data["metadata"]["observation_start"] = "2016-09-22"
    with pytest.raises(ValueError, match="within the last 10 years"):
        calculate(data)


def test_stockout_interval_over_ten_years_rejected_without_expansion():
    data = fixture()
    data["stockouts"] = [{"sku": "A", "warehouse": "W",
                          "start": "2016-09-22", "end": AS_OF.isoformat()}]
    with pytest.raises(ValueError, match="interval exceeds 10 years"):
        calculate(data)


def test_row_count_limits_checked_before_processing():
    data = fixture()
    data["products"] = data["products"] * (MAX_PRODUCTS + 1)
    with pytest.raises(ValueError, match="products exceeds"):
        calculate(data)
    data = fixture()
    data["sales"] = data["sales"] * (MAX_SALES + 1)
    with pytest.raises(ValueError, match="sales exceeds"):
        calculate(data)


def test_large_but_realistic_partner_window_still_works():
    data = fixture()
    data["sales"][0]["date"] = "2023-01-01"
    data["metadata"]["observation_start"] = "2023-01-01"
    data["sales"] *= 250_000
    result = calculate(data)
    assert result["summary"]["items"] == 1


def test_combined_history_points_rejected_before_per_product_expansion():
    data = fixture()
    data["products"] = [{"sku": str(i), "warehouse": "W", "lead_days": 1}
                        for i in range(3_000)]
    data["sales"] = []
    data["metadata"]["observation_start"] = "2016-09-23"
    with pytest.raises(ValueError, match="combined product histories exceed"):
        calculate(data)


def test_repeated_long_stockout_intervals_rejected_before_expansion():
    data = fixture()
    data["stockouts"] = [{"sku": "A", "warehouse": "W",
                          "start": "2016-09-23", "end": AS_OF.isoformat()}] * 3_000
    with pytest.raises(ValueError, match="expanded days"):
        calculate(data)


def test_http_returns_422_instead_of_running_pathological_horizon():
    data = fixture()
    data["products"][0]["lead_days"] = 20_000
    with TestClient(app) as client:
        response = client.post("/api/calculate", json={"dataset": data})
    assert response.status_code == 422
    assert "horizon exceeds" in response.json()["detail"]
