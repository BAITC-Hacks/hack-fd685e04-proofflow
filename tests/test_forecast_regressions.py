"""Forecast invariants: recurring seasons, pure growth and physical unit changes."""
from copy import deepcopy
from datetime import date, timedelta

import pytest

from engine import _trend_factor, calculate


def sample(start, end, quantity, *, scale=1):
    return {
        "as_of": end.isoformat(),
        "products": [{"sku": "S", "warehouse": "W", "supplier": "V",
                      "on_hand": 0, "lead_days": 7, "pack_size": .01 * scale}],
        "sales": [{"date": (start + timedelta(days=i)).isoformat(), "sku": "S",
                   "warehouse": "W", "quantity": quantity(start + timedelta(days=i), i) * scale,
                   "client_id": "SYNTHETIC-REGULAR"}
                  for i in range((end - start).days + 1)],
        "metadata": {"synthetic": True},
    }


def row(data):
    return calculate(data)["rows"][0]


def test_recurring_september_demand_returns_after_zero_sales_offseason():
    data = sample(date(2024, 1, 1), date(2026, 8, 31),
                  lambda day, _: 10 if day.month == 9 else 0)
    result = row(data)
    assert result["excluded_quantity"] == 0
    assert result["daily_demand"] == pytest.approx(10, rel=.05)
    assert 265 <= result["recommended_quantity"] <= 295
    assert all(point["demand"] > 0 for point in result["forecast"])


def test_offseason_fallback_does_not_invent_coldstart_or_discontinued_demand():
    zero = sample(date(2024, 1, 1), date(2026, 8, 31), lambda day, _: 0)
    assert row(zero)["recommended_quantity"] == 0
    stopped = sample(date(2024, 1, 1), date(2026, 8, 31),
                     lambda day, _: 10 if day < date(2026, 5, 1) else 0)
    assert row(stopped)["recommended_quantity"] == 0
    empty = deepcopy(zero)
    empty["sales"] = []
    assert row(empty)["recommended_quantity"] == 0
    # Two observed zero-demand summers do not establish an unseen autumn
    # selling cycle after just one previous autumn peak.
    unproven = sample(date(2025, 6, 1), date(2026, 8, 31),
                      lambda day, _: 10 if day.month == 10 else 0)
    assert row(unproven)["recommended_quantity"] == 0


def test_short_linear_growth_does_not_crash_at_unobserved_month_boundary():
    data = sample(date(2026, 7, 1), date(2026, 9, 23), lambda _, i: 1 + i / 10)
    result = row(data)
    forecast = {point["date"]: point["demand"] for point in result["forecast"]}
    assert result["excluded_quantity"] == 0
    assert all(value == pytest.approx(1) for value in result["breakdown"]["seasonality_indices"]["month"].values())
    assert forecast["2026-10-01"] >= forecast["2026-09-30"] * .9
    assert result["daily_demand"] > data["sales"][-1]["quantity"]


def test_partial_month_in_previous_year_is_not_a_second_annual_cycle():
    data = sample(date(2025, 9, 24), date(2026, 9, 23), lambda _, i: 1 + i / 100)
    result = row(data)
    assert all(value == pytest.approx(1) for value in result["breakdown"]["seasonality_indices"]["month"].values())


def test_recent_stockout_does_not_shorten_elapsed_trend_window():
    observed = [{"demand": 10 + i * .03, "stockout": False, "excluded": False}
                for i in range(60)]
    censored = [{"demand": 0, "stockout": True, "excluded": False}
                for _ in range(30)]
    factor, level = _trend_factor(observed + censored, horizon=28, window=90)
    assert level == pytest.approx(10.885)
    assert factor > 1.18  # Trend continues across the 30 elapsed stockout days.


@pytest.mark.parametrize("identifier", ["client_id", "event_id"])
def test_spike_and_recommendation_are_invariant_to_fractional_unit_scale(identifier):
    results = []
    for scale in (1, .01):
        data = sample(date(2026, 7, 1), date(2026, 9, 23), lambda *_: 1, scale=scale)
        data["sales"].append({"date": "2026-09-19", "sku": "S", "warehouse": "W",
                              "quantity": 50 * scale, identifier: "SYNTHETIC-ONE-OFF"})
        result = row(data)
        assert result["excluded_quantity"] == pytest.approx(50 * scale)
        results.append(result["recommended_quantity"] / scale)
    assert results[0] == pytest.approx(results[1], abs=.01)
