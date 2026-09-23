"""Deterministic, explainable SKU replenishment engine.

All heuristics are provisional engineering defaults, not organizer-mandated
business rules. The engine never contacts suppliers or persists data.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from math import ceil, isfinite
from statistics import median
from typing import Any


DEFAULT_SETTINGS = {
    "review_days": 14,
    "safety_days": 7,
    "outlier_multiplier": 4.0,
    "spike_client_share": 0.60,
    "stockout_min_reference_days": 3,
    "seasonality_min_observations": 10,
    "trend_window_days": 90,
}

# Protect the synchronous local calculation from accidental unbounded loops.
# The supplied partner sample (~250k sales, 2023–2026) remains well below these.
MAX_HORIZON_DAYS = 730
MAX_PRODUCTS = 50_000
MAX_SALES = 2_000_000
MAX_STOCKOUTS = 100_000
MAX_INBOUND = 2_000_000
MAX_HISTORY_POINTS = 10_000_000
MAX_STOCKOUT_EXPANSION_DAYS = 10_000_000


def _ten_years_before(day: date) -> date:
    """Earliest permitted calendar date, including a leap-day fallback."""
    if day.year <= 10:
        return date.min
    try:
        return day.replace(year=day.year - 10)
    except ValueError:  # February 29 in a non-leap target year.
        return day.replace(year=day.year - 10, day=28)


def _number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _day(value: Any, name: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD)") from exc


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _key(sku: str, warehouse: str) -> tuple[str, str]:
    return warehouse, sku


def _local_expected(values: list[float], index: int, fallback: float) -> float:
    """Robust nearby estimate for an isolated one-day spike."""
    nearby = [values[j] for j in range(max(0, index - 7), min(len(values), index + 8))
              if abs(j - index) > 0 and values[j] >= 0]
    return median(nearby) if nearby else fallback


def _seasonal_indices(history: list[dict[str, Any]], min_observations: int) -> dict[str, Any]:
    """Estimate weekday and month indices from adjusted observed history.

    Month-of-year factors are enabled with >= min_observations across that
    month and renormalized to a sample-weighted mean of one.
    """
    positive = [r["demand"] for r in history if not r["stockout"] and not r["excluded"]]
    overall = _mean(positive)
    if overall <= 0:
        return {"weekday": {i: 1.0 for i in range(7)},
                "month": {i: 1.0 for i in range(1, 13)}}
    weekday_samples: dict[int, list[float]] = defaultdict(list)
    month_samples: dict[int, list[float]] = defaultdict(list)
    for row in history:
        if row["stockout"] or row["excluded"]:
            continue
        d = date.fromisoformat(row["date"])
        weekday_samples[d.weekday()].append(row["demand"])
        month_samples[d.month].append(row["demand"])
    weekday = {i: (_mean(v) / overall if len(v) >= 3 else 1.0)
               for i, v in weekday_samples.items()}
    weekday.update({i: 1.0 for i in range(7) if i not in weekday})
    # Normalize weekday indices so averaging them does not shift the level.
    weekday_norm = sum(weekday.values()) / 7 or 1.0
    weekday = {k: v / weekday_norm for k, v in weekday.items()}
    month = {i: (_mean(v) / overall if len(v) >= min_observations else 1.0)
             for i, v in month_samples.items()}
    month.update({i: 1.0 for i in range(1, 13) if i not in month})
    weighted = sum(month[m] * len(v) for m, v in month_samples.items()) / max(
        1, sum(len(v) for v in month_samples.values()))
    month = {k: v / (weighted or 1.0) for k, v in month.items()}
    return {"weekday": weekday, "month": month}


def _trend_factor(history: list[dict[str, Any]], horizon: int, window: int) -> tuple[float, float]:
    """Estimate a bounded per-day linear trend after spike/stockout adjustment."""
    recent = history[-max(window, 8):]
    usable = [(i, r["demand"]) for i, r in enumerate(recent)
              if not r["stockout"] and not r["excluded"]]
    if len(usable) < 8:
        level = _mean([v for _, v in usable])
        return (1.0, level)
    xs = [float(i) for i, _ in usable]
    ys = [v for _, v in usable]
    xbar, ybar = _mean(xs), _mean(ys)
    denominator = sum((x - xbar) ** 2 for x in xs)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denominator if denominator else 0.0
    # Keep the fitted window mean as the level; express projected change only
    # in trend_factor so it is not compounded twice below.
    level = max(0.0, ybar)
    # Report the average projected uplift across the forecast horizon. Bound
    # extreme extrapolation so a few observations cannot create an absurd order.
    raw_factor = (ybar + slope * (max(0, len(xs) - 1 - xbar) + max(0, horizon - 1) / 2)) / ybar if ybar > 0 else 1.0
    factor = min(2.0, max(0.5, raw_factor))
    return factor, level


def _ceil_pack(quantity: float, pack_size: float, moq: float) -> float:
    target = max(0.0, quantity)
    if target <= 1e-10:
        return 0
    target = max(target, moq)
    units = ceil((target - 1e-10) / pack_size)
    result = units * pack_size
    return int(result) if float(result).is_integer() else round(result, 6)


def _monthly_history(history: list[dict[str, Any]], max_months: int = 36) -> list[dict[str, Any]]:
    """Keep the chart/detail payload bounded while retaining exact monthly totals."""
    months: dict[str, dict[str, Any]] = {}
    for day in history:
        month = day["date"][:7]
        if month not in months:
            months[month] = {"date": f"{month}-01", "period": month, "days": 0,
                             "quantity": 0.0, "raw_quantity": 0.0,
                             "adjusted_quantity": 0.0, "raw_sales": 0.0,
                             "adjusted_demand": 0.0, "lost_demand": 0.0,
                             "excluded_quantity": 0.0, "stockout": False,
                             "excluded": False}
        point = months[month]
        point["days"] += 1
        for field in ("raw_quantity", "adjusted_quantity", "lost_demand", "excluded_quantity"):
            point[field] += day[field]
        point["stockout"] |= day["stockout"]
        point["excluded"] |= day["excluded"]
    compact = list(months.values())[-max_months:]
    for point in compact:
        point["raw_sales"] = point["raw_quantity"] = round(point["raw_quantity"], 6)
        point["quantity"] = point["adjusted_demand"] = point["adjusted_quantity"] = round(point["adjusted_quantity"], 6)
        point["lost_demand"] = round(point["lost_demand"], 6)
        point["excluded_quantity"] = round(point["excluded_quantity"], 6)
    return compact


def _calc_product(product: dict[str, Any], dataset: dict[str, Any], as_of: date,
                  sales_by_key: dict[tuple[str, str], list[dict[str, Any]]],
                  stockouts_by_key: dict[tuple[str, str], list[tuple[date, date]]],
                  inbound_by_key: dict[tuple[str, str], list[dict[str, Any]]],
                  settings: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    sku = product["sku"]
    warehouse = product["warehouse"]
    k = _key(sku, warehouse)
    on_hand = _number(product.get("on_hand", 0), f"products[{sku}].on_hand", minimum=0)
    lead_days = int(_number(product.get("lead_days", 0), f"products[{sku}].lead_days", minimum=0))
    sku_growth = _number(product.get("growth", 0), f"products[{sku}].growth", minimum=-1)
    pack_size = _number(product.get("pack_size", 1), f"products[{sku}].pack_size", minimum=1e-9)
    moq = _number(product.get("moq", 0), f"products[{sku}].moq", minimum=0)
    unit_price = _number(product.get("unit_price", 0), f"products[{sku}].unit_price", minimum=0)
    review_days = int(settings["review_days"])
    cat_policy = dataset.get("category_policies", {}).get(product.get("category", ""), {})
    category_growth = _number(cat_policy.get("growth", 0), f"category_policies[{product.get('category')}].growth", minimum=-1)
    safety_days = int(_number(cat_policy.get("safety_days", settings["safety_days"]),
                              f"category_policies[{product.get('category')}].safety_days", minimum=0))
    horizon = max(1, lead_days + review_days + safety_days)
    if horizon > MAX_HORIZON_DAYS:
        raise ValueError(
            f"products[{sku}].horizon exceeds {MAX_HORIZON_DAYS} days "
            "(lead_days + review_days + safety_days)")
    local_warnings: list[str] = []
    if not product.get("supplier"):
        local_warnings.append("Поставщик не указан: проверьте позицию в очереди без назначенного поставщика")

    tx_by_day_client: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    known_clients: set[str] = set()
    actual_client_ids: set[str] = set()
    for tx in sales_by_key.get(k, []):
        d = date.fromisoformat(tx["date"])
        # event_id is an opaque order/document token, never a customer identity.
        client = str(tx.get("client_id") or tx.get("event_id") or "__unknown_client__")
        if tx.get("client_id") or tx.get("event_id"):
            known_clients.add(client)
        if tx.get("client_id"):
            actual_client_ids.add(client)
        tx_by_day_client[d][client] += tx["quantity"]
    intervals = stockouts_by_key.get(k, [])
    start_dates = [d for d in tx_by_day_client if d <= as_of]
    observation_start = (dataset.get("metadata") or {}).get("observation_start")
    explicit_start = _day(observation_start, "metadata.observation_start") if observation_start else None
    stockout_starts = [start for start, _ in intervals if start <= as_of]
    anchors = start_dates + stockout_starts + ([explicit_start] if explicit_start else [])
    history_start = min(anchors) if anchors else as_of
    # Keep at least a full seasonal cycle when provided; do not fabricate rows
    # before the first observed date.
    history_dates = [history_start + timedelta(days=i)
                     for i in range((as_of - history_start).days + 1)]
    raw_values = [sum(tx_by_day_client.get(d, {}).values()) for d in history_dates]
    # Expand intervals once, rather than checking every date against every
    # interval; this matters for long histories with many stockout periods.
    censored_days: set[date] = set()
    for start, end in intervals:
        capped_start, capped_end = max(start, history_start), min(end, as_of)
        for offset in range(max(0, (capped_end - capped_start).days + 1)):
            censored_days.add(capped_start + timedelta(days=offset))
    is_stockout = [d in censored_days for d in history_dates]

    # Detect only isolated, customer-concentrated anomalies. A candidate is
    # retained if adjacent days are elevated, protecting sustained growth.
    eligible = [v for i, v in enumerate(raw_values) if not is_stockout[i]]
    base = median(eligible) if eligible else 0.0
    mad = median([abs(v - base) for v in eligible]) if eligible else 0.0
    threshold = max(base * settings["outlier_multiplier"], base + 6 * mad, base + 1.0)
    excluded_by_index: dict[int, float] = {}
    events: list[dict[str, Any]] = []
    document_spike_count = 0
    candidate_indices = [i for i, (v, so) in enumerate(zip(raw_values, is_stockout))
                         if not so and v > threshold]
    # A document number identifies an order, not a repeat customer. For that
    # weaker signal, require enough non-zero reference days and a genuinely
    # extreme quantity relative to the positive-day distribution. A median of
    # zero on intermittent SKUs must not classify ordinary orders as spikes.
    active_values = sorted(v for v in eligible if v > 0)
    active_median = median(active_values) if active_values else 0.0
    active_p90 = active_values[int(0.9 * (len(active_values) - 1))] if active_values else 0.0
    document_threshold = max(threshold * 2, active_median * 8, active_p90 * 3)
    client_history: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for transaction_day, clients in tx_by_day_client.items():
        for client_id, quantity in clients.items():
            client_history[client_id].append((transaction_day, quantity))
    for i in candidate_indices:
        day_clients = tx_by_day_client.get(history_dates[i], {})
        if not day_clients:
            continue
        client, largest = max(day_clients.items(), key=lambda item: item[1])
        if client not in known_clients:
            # Anonymous daily totals cannot prove a single-order/customer
            # spike. Do not silently remove their legitimate demand.
            continue
        if client not in actual_client_ids and (
                len(active_values) < 14 or largest <= document_threshold):
            continue
        total = raw_values[i]
        share = largest / total if total else 0.0
        # Require an isolated one-day event, not a plateau or accelerating run.
        adjacent = [raw_values[j] for j in (i - 1, i + 1) if 0 <= j < len(raw_values)]
        isolated = all(v <= threshold for v in adjacent)
        prior_client_values = [quantity for d, quantity in client_history[client]
                               if d != history_dates[i]]
        client_median = median(prior_client_values) if prior_client_values else 0.0
        client_spike = not prior_client_values or largest > max(
            client_median * settings["outlier_multiplier"], client_median + 1.0)
        recurring_month_peak = any(
            d != history_dates[i] and d.month == history_dates[i].month
            and quantity >= threshold
            for d, quantity in client_history[client])
        if not (isolated and share >= settings["spike_client_share"] and client_spike
                and not recurring_month_peak):
            continue
        expected = max(0.0, _local_expected(raw_values, i, base))
        removed = max(0.0, total - expected)
        excluded_by_index[i] = removed
        events.append({"date": history_dates[i].isoformat(), "client_id": client,
                       "raw_quantity": round(total, 6), "retained_quantity": round(expected, 6),
                       "excluded_quantity": round(removed, 6), "client_share": round(share, 4),
                       "reason": "Разовый выброс за день: преобладает один клиент или заказ; повторного пика в том же месяце нет"})
        if client not in actual_client_ids:
            document_spike_count += 1

    if document_spike_count:
        local_warnings.append(
            f"{document_spike_count} разовых всплесков связаны с номером документа, "
            "а не с идентификатором клиента; проверьте исключения в деталях")

    cleaned = [max(0.0, v - excluded_by_index.get(i, 0.0))
               for i, v in enumerate(raw_values)]
    # Compensate only explicit stockout intervals, using non-stockout peer days
    # with the same weekday. If too few peers exist, use the global in-stock
    # median and flag the lower-confidence estimate.
    in_stock_peers: dict[int, list[float]] = defaultdict(list)
    sparse_reference_days = 0
    for i, d in enumerate(history_dates):
        if not is_stockout[i] and i not in excluded_by_index:
            in_stock_peers[d.weekday()].append(cleaned[i])
    all_peers = [v for peers in in_stock_peers.values() for v in peers]
    global_peer = median(all_peers) if all_peers else 0.0
    history: list[dict[str, Any]] = []
    lost_total = 0.0
    for i, d in enumerate(history_dates):
        lost = 0.0
        if is_stockout[i]:
            peers = in_stock_peers.get(d.weekday(), [])
            if len(peers) < settings["stockout_min_reference_days"]:
                expected = global_peer
                sparse_reference_days += 1
            else:
                expected = median(peers)
            lost = max(0.0, expected - raw_values[i])
        adjusted = cleaned[i] + lost
        lost_total += lost
        history.append({"date": d.isoformat(), "quantity": round(adjusted, 6),
                        "raw_quantity": round(raw_values[i], 6),
                        "adjusted_quantity": round(adjusted, 6),
                        "raw_sales": round(raw_values[i], 6),
                        "adjusted_demand": round(adjusted, 6), "lost_demand": round(lost, 6),
                        "excluded_quantity": round(excluded_by_index.get(i, 0.0), 6),
                        "stockout": is_stockout[i], "excluded": i in excluded_by_index})
    if sparse_reference_days:
        local_warnings.append(
            f"Для {sparse_reference_days} дней отсутствия товара использована общая медиана: "
            f"наблюдений за тот же день недели меньше {settings['stockout_min_reference_days']}")

    seasonality = _seasonal_indices(
        [{"date": r["date"], "demand": r["adjusted_demand"],
          "stockout": r["stockout"], "excluded": r["excluded"]} for r in history],
        int(settings["seasonality_min_observations"]))
    # Fit the recent level/trend on deseasonalized observations. Otherwise a
    # normal seasonal peak near as_of looks like persistent growth and is then
    # multiplied by the same seasonal index a second time in the forecast.
    deseasonalized = []
    for item in history:
        observed_day = date.fromisoformat(item["date"])
        observed_factor = (seasonality["weekday"][observed_day.weekday()]
                           * seasonality["month"][observed_day.month])
        deseasonalized.append({
            "demand": item["adjusted_demand"] / max(observed_factor, 0.05),
            "stockout": item["stockout"], "excluded": item["excluded"],
        })
    trend_factor, level = _trend_factor(
        deseasonalized, horizon, int(settings["trend_window_days"]))
    growth_factor = max(0.0, (1 + sku_growth) * (1 + category_growth))
    forecast: list[dict[str, Any]] = []
    future_start = as_of + timedelta(days=1)
    for offset in range(horizon):
        d = future_start + timedelta(days=offset)
        sf = seasonality["weekday"][d.weekday()] * seasonality["month"][d.month]
        demand = max(0.0, level * trend_factor * sf * growth_factor)
        forecast.append({"date": d.isoformat(), "quantity": round(demand, 6),
                         "demand": round(demand, 6),
                         "seasonality_factor": round(sf, 6)})
    forecast_need = sum(item["demand"] for item in forecast)

    inbound = []
    for receipt in inbound_by_key.get(k, []):
        eta = date.fromisoformat(receipt["eta"])
        qty = receipt["quantity"]
        inbound.append({"eta": eta, "quantity": qty})
    inbound.sort(key=lambda r: r["eta"])
    horizon_end = as_of + timedelta(days=horizon)
    inbound_in_horizon = sum(r["quantity"] for r in inbound if r["eta"] <= horizon_end)
    # The terminal inventory balance alone is unsafe: a late receipt can
    # conceal an earlier stockout. Size the draft to the maximum cumulative
    # deficit on any day of the planning horizon.
    running_demand = 0.0
    running_inbound = 0.0
    receipt_index = 0
    net_need = 0.0
    for item in forecast:
        forecast_date = date.fromisoformat(item["date"])
        while receipt_index < len(inbound) and inbound[receipt_index]["eta"] <= forecast_date:
            running_inbound += inbound[receipt_index]["quantity"]
            receipt_index += 1
        running_demand += item["demand"]
        net_need = max(net_need, running_demand - on_hand - running_inbound)
    terminal_net_need = max(0.0, forecast_need - on_hand - inbound_in_horizon)
    recommended = _ceil_pack(net_need, pack_size, moq)

    projected = on_hand
    inbound_index = 0
    stockout_date = None
    coverage_days = None
    # Simulate through the replenishment horizon and lead time, honoring receipt
    # dates; no inbound is treated as present before its ETA.
    simulation_days = max(horizon, lead_days)
    for offset in range(simulation_days):
        d = future_start + timedelta(days=offset)
        while inbound_index < len(inbound) and inbound[inbound_index]["eta"] <= d:
            projected += inbound[inbound_index]["quantity"]
            inbound_index += 1
        daily = forecast[offset]["demand"] if offset < len(forecast) else (
            forecast[-1]["demand"] if forecast else 0.0)
        projected -= daily
        if projected < -1e-9:
            stockout_date = d.isoformat()
            coverage_days = float(offset)
            break
    if stockout_date is None:
        avg_daily = _mean([r["demand"] for r in forecast])
        coverage_days = round((on_hand + inbound_in_horizon) / avg_daily, 2) if avg_daily > 0 else None
    if stockout_date and (date.fromisoformat(stockout_date) <= as_of + timedelta(days=lead_days)):
        urgency = "critical"
    elif stockout_date:
        urgency = "high"
    elif recommended > 0:
        urgency = "normal"
    else:
        urgency = "covered"

    mean_seasonality = _mean([r["seasonality_factor"] for r in forecast])
    raw_daily = _mean(raw_values)
    adjusted_daily = _mean([r["adjusted_demand"] for r in history])
    warnings_for_row = sorted(set(local_warnings))
    if not tx_by_day_client:
        warnings_for_row.append("Нет истории продаж с датами: прогноз спроса построить невозможно")
    elif adjusted_daily == 0:
        warnings_for_row.append(
            "В истории нет положительного спроса: без дополнительных данных рекомендация равна нулю")
    if local_warnings:
        warnings.extend(f"{sku}/{warehouse}: {w}" for w in warnings_for_row)
    if not tx_by_day_client or adjusted_daily == 0:
        warnings.extend(w for w in warnings_for_row if w not in warnings)

    urgency_label = {"critical": "критическая", "high": "высокая",
                     "normal": "обычная", "covered": "запас покрывает спрос"}[urgency]
    source_label = "синтетические данные" if dataset.get("metadata", {}).get("synthetic", False) else "загруженные данные"
    stockout_label = stockout_date or "не ожидается в пределах горизонта расчёта"
    explanation = (
        f"Источник: {source_label}. "
        f"Прогноз спроса {forecast_need:.2f} ед. на {horizon} дн. "
        f"(поставка {lead_days} + пересмотр {review_days} + страховой запас {safety_days}); "
        f"остаток {on_hand:.2f}; поступления до конца горизонта {inbound_in_horizon:.2f}; "
        f"максимальный дефицит по датам {net_need:.2f} "
        f"(дефицит в конце горизонта {terminal_net_need:.2f}); "
        f"минимальная партия {moq:g}, кратность упаковки {pack_size:g}; рекомендуем {recommended:g}. "
        f"Скорректированный исторический спрос {adjusted_daily:.3f} ед./день; "
        f"оценка упущенного спроса {lost_total:.2f} ед.; "
        f"исключено выбросов {sum(excluded_by_index.values()):.2f} ед.; "
        f"сезонность ×{mean_seasonality:.3f}, тренд ×{trend_factor:.3f}, прирост ×{growth_factor:.3f}. "
        f"Срочность: {urgency_label}; ожидаемый дефицит без нового заказа: {stockout_label}."
    )
    return {
        "sku": sku, "name": product.get("name", sku), "supplier": product.get("supplier", ""),
        "category": product.get("category", ""), "warehouse": warehouse, "unit": product.get("unit", "pcs"),
        "on_hand": on_hand, "inbound_quantity": inbound_in_horizon, "lead_days": lead_days,
        "recommended_quantity": recommended, "unit_price": unit_price,
        "amount": round(recommended * unit_price, 2), "daily_demand": round(_mean([r["demand"] for r in forecast]), 6),
        "raw_daily_demand": round(raw_daily, 6), "lost_demand": round(lost_total, 6),
        "excluded_quantity": round(sum(excluded_by_index.values()), 6), "excluded_events": events,
        "seasonality_factor": round(mean_seasonality, 6), "trend_factor": round(trend_factor, 6),
        "growth_factor": round(growth_factor, 6), "coverage_days": coverage_days,
        "stockout_date": stockout_date, "projected_stockout_without_new_order": stockout_date,
        "urgency": urgency, "explanation": explanation,
        "breakdown": {"forecast_need": round(forecast_need, 6), "horizon_days": horizon,
                      "review_days": review_days, "safety_days": safety_days,
                      "sku_growth": sku_growth, "category_growth": category_growth,
                      "seasonality_indices": {"weekday": seasonality["weekday"], "month": seasonality["month"]},
                      "order_rounding": {"net_need": round(net_need, 6),
                                         "end_horizon_gap": round(terminal_net_need, 6), "moq": moq,
                                         "pack_size": pack_size, "recommended": recommended},
                      "inbound_receipts": [{"eta": r["eta"].isoformat(), "quantity": r["quantity"]}
                                           for r in inbound]},
        "history": _monthly_history(history), "forecast": forecast, "warnings": warnings_for_row,
    }


def calculate(dataset: dict[str, Any]) -> dict[str, Any]:
    """Calculate supplier order drafts for canonical dataset; deterministic."""
    if not isinstance(dataset, dict):
        raise ValueError("dataset must be an object")
    as_of = _day(dataset.get("as_of"), "as_of")
    if not isinstance(dataset.get("products"), list) or not dataset["products"]:
        raise ValueError("products must be a non-empty list")
    if len(dataset["products"]) > MAX_PRODUCTS:
        raise ValueError(f"products exceeds {MAX_PRODUCTS} rows")
    for field in ("sales", "stockouts", "inbound"):
        if dataset.get(field) is not None and not isinstance(dataset[field], list):
            raise ValueError(f"{field} must be a list")
    for field, limit in (("sales", MAX_SALES), ("stockouts", MAX_STOCKOUTS),
                         ("inbound", MAX_INBOUND)):
        if len(dataset.get(field) or []) > limit:
            raise ValueError(f"{field} exceeds {limit} rows")
    if dataset.get("metadata") is not None and not isinstance(dataset["metadata"], dict):
        raise ValueError("metadata must be an object")
    settings = dict(DEFAULT_SETTINGS)
    if dataset.get("settings") is not None and not isinstance(dataset["settings"], dict):
        raise ValueError("settings must be an object")
    if dataset.get("category_policies") is not None and not isinstance(dataset["category_policies"], dict):
        raise ValueError("category_policies must be an object")
    settings.update(dataset.get("settings") or {})
    for key in ("review_days", "safety_days", "stockout_min_reference_days",
                "seasonality_min_observations", "trend_window_days"):
        value = _number(settings[key], f"settings.{key}", minimum=0)
        if int(value) != value:
            raise ValueError(f"settings.{key} must be an integer")
        settings[key] = int(value)
    for key in ("outlier_multiplier", "spike_client_share"):
        settings[key] = _number(settings[key], f"settings.{key}", minimum=0)
    if settings["spike_client_share"] > 1:
        raise ValueError("settings.spike_client_share must be <= 1")
    history_floor = _ten_years_before(as_of)
    observation_start = dataset.get("metadata", {}).get("observation_start")
    if observation_start:
        observed_from = _day(observation_start, "metadata.observation_start")
        if observed_from < history_floor or observed_from > as_of:
            raise ValueError("metadata.observation_start must be within the last 10 years and not after as_of")

    global_warnings = list(dataset.get("metadata", {}).get("warnings", []))
    products_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for index, p in enumerate(dataset["products"]):
        if not isinstance(p, dict) or not p.get("sku"):
            raise ValueError(f"products[{index}] requires sku")
        p = dict(p)
        p["sku"] = str(p["sku"])
        p["warehouse"] = str(p.get("warehouse") or "default")
        k = _key(p["sku"], p["warehouse"])
        if k in products_by_key:
            raise ValueError(f"duplicate product sku/warehouse: {p['sku']}/{p['warehouse']}")
        products_by_key[k] = p

    sales_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    earliest_by_key: dict[tuple[str, str], date] = {}
    ignored_future_sales = 0
    ignored_unknown_sales = 0
    for i, row in enumerate(dataset.get("sales", [])):
        if not isinstance(row, dict):
            raise ValueError(f"sales[{i}] must be an object")
        d = _day(row.get("date"), f"sales[{i}].date")
        if d < history_floor:
            raise ValueError(f"sales[{i}].date is more than 10 years before as_of")
        qty = _number(row.get("quantity"), f"sales[{i}].quantity", minimum=0)
        k = _key(str(row.get("sku", "")), str(row.get("warehouse") or "default"))
        if d > as_of:
            ignored_future_sales += 1
        elif k not in products_by_key:
            ignored_unknown_sales += 1
        else:
            sales_by_key[k].append({"date": d.isoformat(), "quantity": qty,
                                    "client_id": row.get("client_id"),
                                    "event_id": row.get("event_id")})
            earliest_by_key[k] = min(d, earliest_by_key.get(k, d))
    if ignored_future_sales:
        global_warnings.append(
            f"Не учтено продаж после расчётной даты {as_of}: {ignored_future_sales}")
    if ignored_unknown_sales:
        global_warnings.append(
            f"Не учтено продаж для неизвестного артикула или склада: {ignored_unknown_sales}")

    stockouts_by_key: dict[tuple[str, str], list[tuple[date, date]]] = defaultdict(list)
    stockout_expansion_days = 0
    for i, row in enumerate(dataset.get("stockouts", [])):
        if not isinstance(row, dict):
            raise ValueError(f"stockouts[{i}] must be an object")
        start = _day(row.get("start"), f"stockouts[{i}].start")
        end = _day(row.get("end"), f"stockouts[{i}].end")
        if end < start:
            raise ValueError(f"stockouts[{i}].end precedes start")
        if start < _ten_years_before(end):
            raise ValueError(f"stockouts[{i}] interval exceeds 10 years")
        if start < history_floor:
            raise ValueError(f"stockouts[{i}].start is more than 10 years before as_of")
        k = _key(str(row.get("sku", "")), str(row.get("warehouse") or "default"))
        if k in products_by_key:
            if start <= as_of:
                stockouts_by_key[k].append((start, min(end, as_of)))
                earliest_by_key[k] = min(start, earliest_by_key.get(k, start))
                stockout_expansion_days += (min(end, as_of) - start).days + 1
                if stockout_expansion_days > MAX_STOCKOUT_EXPANSION_DAYS:
                    raise ValueError(
                        f"stockout intervals exceed {MAX_STOCKOUT_EXPANSION_DAYS} expanded days")
            else:
                global_warnings.append(
                    f"Период отсутствия товара stockouts[{i}] начинается после расчётной даты {as_of}; не учтён")
        else:
            global_warnings.append(
                f"Период отсутствия товара stockouts[{i}]: неизвестный артикул/склад {k[1]}/{k[0]}; не учтён")

    inbound_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for i, row in enumerate(dataset.get("inbound", [])):
        if not isinstance(row, dict):
            raise ValueError(f"inbound[{i}] must be an object")
        eta = _day(row.get("eta"), f"inbound[{i}].eta")
        qty = _number(row.get("quantity"), f"inbound[{i}].quantity", minimum=0)
        k = _key(str(row.get("sku", "")), str(row.get("warehouse") or "default"))
        if k in products_by_key:
            if eta <= as_of:
                # Past receipts are not silently applied to today's on-hand.
                global_warnings.append(
                    f"Поставка inbound[{i}] с датой {eta} не позже расчётной даты; "
                    "не учтена в прогнозе")
            else:
                inbound_by_key[k].append({"eta": eta.isoformat(), "quantity": qty})
        else:
            global_warnings.append(
                f"Поставка inbound[{i}]: неизвестный артикул/склад {k[1]}/{k[0]}; не учтена")

    history_points = 0
    for k in products_by_key:
        earliest = earliest_by_key.get(k, as_of)
        if observation_start:
            earliest = min(earliest, observed_from)
        history_points += (as_of - earliest).days + 1
        if history_points > MAX_HISTORY_POINTS:
            raise ValueError(f"combined product histories exceed {MAX_HISTORY_POINTS} days")

    rows = [_calc_product(p, dataset, as_of, sales_by_key, stockouts_by_key,
                          inbound_by_key, settings, global_warnings)
            for p in products_by_key.values()]
    rows.sort(key=lambda r: (r["supplier"].casefold(), r["urgency"] not in ("critical", "high"),
                             r["sku"].casefold(), r["warehouse"].casefold()))
    suppliers = sorted({r["supplier"] for r in rows if r["recommended_quantity"] > 0})
    summary = {"items": len(rows), "suppliers": len(suppliers),
               "order_lines": sum(r["recommended_quantity"] > 0 for r in rows),
               "total_amount": round(sum(r["amount"] for r in rows), 2),
               "critical_items": sum(r["urgency"] == "critical" for r in rows)}
    groups: dict[str, dict[str, Any]] = {}
    for item in rows:
        supplier = item["supplier"] or "UNASSIGNED"
        group = groups.setdefault(supplier, {"supplier": supplier, "order_lines": 0,
                                             "total_amount": 0.0})
        group["order_lines"] += item["recommended_quantity"] > 0
        group["total_amount"] += item["amount"]
    supplier_groups = [dict(groups[supplier], total_amount=round(groups[supplier]["total_amount"], 2))
                       for supplier in sorted(groups)]
    return {"as_of": as_of.isoformat(), "rows": rows, "summary": summary,
            "supplier_groups": supplier_groups, "warnings": sorted(set(global_warnings)),
            "methodology": "deterministic-provisional-v1"}
