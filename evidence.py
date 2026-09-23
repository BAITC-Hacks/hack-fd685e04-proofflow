"""Deterministic decision reconciliation; no network, signing, or order sending."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
import json


SETTINGS = (
    "locale", "review_days", "safety_days", "outlier_multiplier",
    "spike_client_share", "stockout_min_reference_days",
    "seasonality_min_observations", "trend_window_days",
)


def _number(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite nonnegative number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a finite nonnegative number") from None
    if not result.is_finite() or result < 0 or result > Decimal("1e30"):
        raise ValueError(f"{label} must be a finite nonnegative number")
    return result


def _text(value):
    return format(value, "f")


def _money(quantity, price):
    with localcontext() as context:
        context.prec = 80
        return (quantity * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _totals(rows, phase):
    ordered = [row for row in rows if Decimal(row[f"{phase}_quantity"]) > 0]
    unknown = [row for row in ordered if row["unit_price"] is None]
    with localcontext() as context:
        context.prec = 80
        known_amount = sum((Decimal(row[f"{phase}_amount"]) for row in ordered
                            if row[f"{phase}_amount"] is not None), Decimal(0))
        return {
            "items": len(rows), "order_lines": len(ordered),
            "total_quantity": _text(sum((Decimal(row[f"{phase}_quantity"]) for row in rows), Decimal(0))),
            "known_amount": _text(known_amount.quantize(Decimal("0.01"))),
            "unpriced_order_lines": len(unknown),
            "unpriced_quantity": _text(sum((Decimal(row[f"{phase}_quantity"]) for row in unknown), Decimal(0))),
            "amount_complete": not unknown,
        }


def _check(checks, name, actual, expected, present=True):
    if not present:
        checks.append({"check": name, "status": "not_available"})
        return
    try:
        matches = Decimal(str(actual)) == Decimal(str(expected))
    except (InvalidOperation, ValueError):
        matches = False
    checks.append({"check": name, "status": "pass" if matches else "fail",
                   "recorded": actual, "recomputed": expected})


def build_evidence(run: dict) -> dict:
    """Reconcile an immutable run snapshot and its optional human approval.

    Monetary values and quantities are decimal strings. Missing prices are
    null. The SHA-256 identifies this report's canonical JSON, not its author.
    """
    if not isinstance(run, dict) or not isinstance(run.get("rows"), list):
        raise ValueError("run.rows must be a list")
    approval = run.get("approval")
    quantities = approval.get("quantities", {}) if approval else {}
    if not isinstance(quantities, dict):
        raise ValueError("approval.quantities must be an object")
    lines, checks, keys = [], [], set()
    row_warning_count = 0
    for row in run["rows"]:
        key = f"{row.get('warehouse', '')}::{row['sku']}"
        if key in keys:
            raise ValueError("duplicate warehouse/SKU in evidence run")
        keys.add(key)
        recommended = _number(row["recommended_quantity"], "recommended quantity")
        # Approval storage guarantees a full map. Never silently invent a
        # missing approved quantity in a malformed or truncated snapshot.
        if approval and key not in quantities:
            raise ValueError("approval is missing a row quantity")
        final = _number(quantities[key], "approved quantity") if approval else recommended
        raw_price = row.get("unit_price")
        known = row.get("price_known", raw_price not in (None, "", 0)) is True
        price = _number(raw_price, "unit price") if known else None
        recommended_amount = _money(recommended, price) if known else None
        final_amount = _money(final, price) if known else None
        row_warning_count += len(row.get("warnings") or [])
        line = {
            "key": key, "sku": str(row["sku"]), "warehouse": str(row.get("warehouse", "")),
            "supplier": str(row.get("supplier") or "UNASSIGNED"),
            "unit": str(row.get("unit", "")),
            "recommended_quantity": _text(recommended), "final_quantity": _text(final),
            "quantity_delta": _text(final - recommended), "manually_changed": final != recommended,
            "unit_price": _text(price) if known else None,
            "recommended_amount": _text(recommended_amount) if known else None,
            "final_amount": _text(final_amount) if known else None,
            "warning_count": len(row.get("warnings") or []),
            "excluded_event_count": int(row.get("excluded_event_count", len(row.get("excluded_events") or []))),
            "input_provenance": {field: row.get("input_provenance", {}).get(field, "unknown")
                                 for field in ("on_hand", "lead_days", "unit_price")},
        }
        lines.append(line)
        if known:
            _check(checks, f"line_amount:{key}", row.get("amount"),
                   line["recommended_amount"], "amount" in row)
    if set(quantities) - keys:
        raise ValueError("approval contains an unknown row")
    lines.sort(key=lambda row: row["key"])
    before, after = _totals(lines, "recommended"), _totals(lines, "final")
    suppliers, members_by_supplier = [], {}
    for row in lines:
        members_by_supplier.setdefault(row["supplier"], []).append(row)
    for supplier, members in sorted(members_by_supplier.items()):
        suppliers.append({"supplier": supplier, "recommended": _totals(members, "recommended"),
                          "final": _totals(members, "final")})
    summary = run.get("summary") or {}
    for name, expected in (("items", before["items"]), ("order_lines", before["order_lines"]),
                           ("total_amount", before["known_amount"]),
                           ("unpriced_order_lines", before["unpriced_order_lines"])):
        _check(checks, f"summary.{name}", summary.get(name), expected, name in summary)
    # Summary remains a recommendation snapshot after approval. Compare it to
    # recommended values, and report approved values separately.
    groups = run.get("supplier_groups")
    if groups is not None:
        recorded = {}
        for group in groups:
            supplier = str(group.get("supplier") or "UNASSIGNED")
            if supplier in recorded:
                checks.append({"check": "supplier_groups.unique", "status": "fail"})
            recorded[supplier] = group
        checks.append({"check": "supplier_groups.coverage", "status":
                       "pass" if set(recorded) == {s["supplier"] for s in suppliers} else "fail"})
        for supplier in suppliers:
            group = recorded.get(supplier["supplier"], {})
            for field, expected in (("order_lines", supplier["recommended"]["order_lines"]),
                                    ("total_amount", supplier["recommended"]["known_amount"])):
                _check(checks, f"supplier:{supplier['supplier']}:{field}", group.get(field),
                       expected, field in group)
    else:
        checks.append({"check": "supplier_groups", "status": "not_available"})
    settings = run.get("settings") or {}
    report = {
        "schema_version": "proofflow-evidence-v1", "run_id": str(run.get("run_id", "")),
        "as_of": run.get("as_of"), "created_at": run.get("created_at"),
        "source": {"label": run.get("source_label", ""), "synthetic": run.get("source_synthetic")},
        "locale": run.get("locale", settings.get("locale", "ru")),
        "settings": {key: settings[key] for key in SETTINGS if key in settings},
        "filters": {key: run.get("filters", {}).get(key) for key in ("warehouse", "category", "supplier")
                    if key in (run.get("filters") or {})},
        "methodology": run.get("methodology"), "status": "approved" if approval else "draft",
        "approval": {"approval_id": approval.get("approval_id"), "approved_at": approval.get("approved_at"),
                     "supplier_sent": approval.get("supplier_sent", False),
                     "acknowledged_missing_inputs": approval.get("acknowledged_missing_inputs", False)} if approval else None,
        "recommended": before, "final": after,
        "changed_lines": sum(row["manually_changed"] for row in lines),
        "warnings": {"run_count": len(run.get("warnings") or []), "row_count": row_warning_count},
        "suppliers": suppliers, "lines": lines,
        "reconciliation": {"status": "fail" if any(c["status"] == "fail" for c in checks)
                           else "partial" if any(c["status"] == "not_available" for c in checks) else "pass",
                           "checks": sorted(checks, key=lambda c: c["check"])},
        "fingerprint_scope": "Canonical JSON excluding fingerprint_sha256; change detection only, not a signed or tamper-proof ledger.",
        "currency": None,
        "budget_note": "Known amounts use source prices; currency is not provided by the data contract. Unknown-price lines are excluded from known_amount. Quantities can have different units and must not be treated as interchangeable.",
    }
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    report["fingerprint_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return report
