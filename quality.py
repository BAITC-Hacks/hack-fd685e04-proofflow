"""PII-free, provenance-aware coverage summary for procurement inputs.

This is data coverage, never a confidence score or a claim of forecast accuracy.
Only explicit provenance can mark real input as observed. Synthetic inputs are
assumed by definition. Raw metadata warnings and identifier values are omitted.
"""
from __future__ import annotations

from typing import Any


_STATUSES = {"observed", "assumed", "missing"}
_FIELDS = ("lead_days", "on_hand", "unit_price")
_SOURCES = ("sales", "stockouts", "inbound")


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _marker(product: dict[str, Any], metadata: dict[str, Any], field: str,
            synthetic: bool) -> str:
    if synthetic:
        return "assumed"
    for mapping in (product.get("provenance"), metadata.get("field_provenance"),
                    metadata.get("provenance")):
        if isinstance(mapping, dict):
            marker = mapping.get(field)
            if isinstance(marker, str) and marker in _STATUSES:
                return marker
    return "unknown"


def _source_status(dataset: dict[str, Any], metadata: dict[str, Any],
                   source: str, synthetic: bool) -> str:
    if source not in dataset:
        return "missing"
    if synthetic:
        return "assumed"
    for mapping in (metadata.get("source_provenance"), metadata.get("provenance")):
        if isinstance(mapping, dict):
            marker = mapping.get(source)
            if isinstance(marker, str) and marker in _STATUSES:
                return marker
    return "unknown"


def assess_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    """Return an O(products + sales) aggregate with no identifiers or raw warnings."""
    if not isinstance(dataset, dict):
        raise ValueError("dataset must be an object")
    products = dataset.get("products") or []
    sales = dataset.get("sales") or []
    stockouts = dataset.get("stockouts") or []
    inbound = dataset.get("inbound") or []
    if any(not isinstance(rows, list) for rows in (products, sales, stockouts, inbound)):
        raise ValueError("products, sales, stockouts and inbound must be lists")
    metadata = dataset.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    synthetic = metadata.get("synthetic") is True

    coverage: dict[str, dict[str, Any]] = {
        field: {"present": 0, "observed": 0, "assumed": 0,
                "unknown": 0, "missing": 0}
        for field in _FIELDS
    }
    for product in products:
        if not isinstance(product, dict):
            raise ValueError("products must contain objects")
        for field in _FIELDS:
            item = coverage[field]
            if not _present(product.get(field)):
                item["missing"] += 1
                continue
            item["present"] += 1
            item[_marker(product, metadata, field, synthetic)] += 1
    for item in coverage.values():
        # Share of all SKUs with *documented* observed provenance, not a
        # probabilistic confidence/accuracy percentage. Unknown remains visible.
        item["observed_share"] = item["observed"] / len(products) if products else None

    identifier_counts = {"client_id_rows": 0, "event_id_rows": 0,
                         "rows_without_identifier": 0}
    for row in sales:
        if not isinstance(row, dict):
            raise ValueError("sales must contain objects")
        has_client = _present(row.get("client_id"))
        has_event = _present(row.get("event_id"))
        identifier_counts["client_id_rows"] += has_client
        identifier_counts["event_id_rows"] += has_event
        identifier_counts["rows_without_identifier"] += not (has_client or has_event)
    identifier_counts["has_client_id"] = identifier_counts["client_id_rows"] > 0
    identifier_counts["has_event_id"] = identifier_counts["event_id_rows"] > 0

    raw_warnings = metadata.get("warnings")
    metadata_warning_count = len(raw_warnings) if isinstance(raw_warnings, list) else 0
    warnings: list[str] = []
    if metadata_warning_count:
        warnings.append(
            f"Источник содержит предупреждения: {metadata_warning_count}. "
            "Проверьте их в отчёте импорта перед утверждением заказа.")
    if not sales:
        warnings.append("Нет строк продаж: прогноз регулярного спроса не подтверждён.")
    elif not (identifier_counts["has_client_id"] or identifier_counts["has_event_id"]):
        warnings.append(
            "Нет обезличенных клиентов или номеров документов: обнаружение разовых заказов ограничено.")
    if not stockouts and _source_status(dataset, metadata, "stockouts", synthetic) != "observed":
        warnings.append(
            "Периоды отсутствия товара не подтверждены: компенсацию упущенного спроса проверить нельзя.")
    if not inbound and _source_status(dataset, metadata, "inbound", synthetic) != "observed":
        warnings.append(
            "Поставки в пути не подтверждены: проверьте, что их действительно нет.")

    return {
        "synthetic": metadata.get("synthetic") if isinstance(metadata.get("synthetic"), bool) else None,
        "record_counts": {"products": len(products), "sales": len(sales),
                          "stockouts": len(stockouts), "inbound": len(inbound)},
        "field_coverage": coverage,
        "source_status": {source: _source_status(dataset, metadata, source, synthetic)
                          for source in _SOURCES},
        "sales_identifiers": identifier_counts,
        "metadata_warning_count": metadata_warning_count,
        "warnings": warnings,
    }
