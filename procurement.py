"""Deterministic replenishment baseline. Quantities are recommendations only."""
from dataclasses import asdict, dataclass
from math import ceil, isfinite
from statistics import median
import json


@dataclass(frozen=True)
class Recommendation:
    sku: str
    supplier: str
    quantity: int
    daily_demand: float
    excluded_spikes: int
    explanation: str
    status: str = "draft_requires_review"


def recommend(sku, supplier, daily_sales, on_hand, in_transit, lead_days,
              review_days=7, growth=0.0, pack_size=1):
    """Robust baseline; full seasonal/stockout model is a subsequent increment.

    in_transit denotes confirmed receipts within the coverage horizon.
    No communication with suppliers is performed.
    """
    values = list(daily_sales)
    if not values or not sku or not supplier:
        raise ValueError("SKU, supplier and sales history are required")
    numbers = values + [on_hand, in_transit, lead_days, review_days, growth, pack_size]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in numbers):
        raise ValueError("All numeric inputs must be finite numbers")
    if any(v < 0 for v in values + [on_hand, in_transit, lead_days, review_days]):
        raise ValueError("Sales, stock and time horizons cannot be negative")
    if growth < -1 or pack_size < 1 or int(pack_size) != pack_size:
        raise ValueError("Invalid growth or pack size")
    baseline = median(values)
    deviations = median([abs(v - baseline) for v in values])
    # Explicit provisional outlier policy, not a task-mandated threshold.
    threshold = max(baseline * 3, baseline + 6 * deviations)
    cleaned = [baseline if baseline > 0 and v > threshold else v for v in values]
    excluded = sum(a != b for a, b in zip(values, cleaned))
    demand = sum(cleaned) / len(cleaned) * (1 + growth)
    target = demand * (lead_days + review_days)
    net = max(0.0, target - on_hand - in_transit)
    quantity = ceil(net / pack_size) * pack_size
    explanation = (f"Demand {demand:.3f}/day x {lead_days + review_days} days; "
                   f"stock {on_hand}; inbound {in_transit}; "
                   f"excluded spikes {excluded}; pack {pack_size}; order {quantity}.")
    return Recommendation(sku, supplier, quantity, demand, excluded, explanation)


if __name__ == "__main__":
    result = recommend("SYNTHETIC-001", "DEMO-SUPPLIER", [10] * 27 + [1000], 30, 20, 7)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
