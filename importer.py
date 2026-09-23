"""Local canonical input gateway. Partner workbook parsing lives in partner_xlsx."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import secrets
from datetime import date
from pathlib import Path


def _read_csv(path: Path) -> list[dict]:
    raw = path.read_bytes()
    if len(raw) > 80 * 1024 * 1024:
        raise ValueError("CSV exceeds the 80 MB input limit")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1251")
    sample = content[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";"
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError(f"CSV has no header: {path.name}")
    return [{str(key or "").strip(): value for key, value in row.items()}
            for row in reader]


def _float(value, field: str) -> float:
    if value is None or str(value).strip() == "":
        return 0.0
    try:
        result = float(str(value).strip().replace(" ", "").replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"Invalid {field} number") from exc
    if not (-1e15 < result < 1e15):
        raise ValueError(f"Invalid {field} number")
    return result


def _csv_dataset(paths: list[Path]) -> dict:
    products: dict[tuple[str, str], dict] = {}
    sales: list[dict] = []
    inbound: list[dict] = []
    stockouts: list[dict] = []
    warnings = []
    for path in paths:
        rows = _read_csv(path)
        for row in rows:
            sku = str(row.get("sku") or row.get("артикул") or row.get("Код") or "").strip()
            if not sku:
                continue
            warehouse = str(row.get("warehouse") or row.get("склад") or row.get("Склад") or "default").strip()
            key = warehouse, sku
            product = products.setdefault(key, {
                "sku": sku, "warehouse": warehouse,
                "name": row.get("name") or row.get("наименование") or sku,
                "supplier": row.get("supplier") or row.get("поставщик") or "UNASSIGNED",
                "category": row.get("category") or row.get("категория") or "unknown",
                "unit": row.get("unit") or row.get("единица") or "pcs",
                "on_hand": 0, "lead_days": 0, "moq": 0, "pack_size": 1, "unit_price": 0,
                "provenance": {"on_hand": "missing", "lead_days": "missing", "unit_price": "missing"},
            })
            if row.get("on_hand") not in (None, ""):
                product["on_hand"] = _float(row["on_hand"], "on_hand")
                product["provenance"]["on_hand"] = "observed"
            if row.get("lead_days") not in (None, ""):
                product["lead_days"] = _float(row["lead_days"], "lead_days")
                product["provenance"]["lead_days"] = "observed"
            if row.get("unit_price") not in (None, ""):
                product["unit_price"] = _float(row["unit_price"], "unit_price")
                product["provenance"]["unit_price"] = "observed"
            if row.get("pack_size") not in (None, ""):
                product["pack_size"] = _float(row["pack_size"], "pack_size")
            if row.get("moq") not in (None, ""):
                product["moq"] = _float(row["moq"], "moq")
            quantity = row.get("quantity") or row.get("Количество") or row.get("количество")
            if row.get("date") or row.get("Дата"):
                day = str(row.get("date") or row.get("Дата")).strip()
                date.fromisoformat(day)
                qty = _float(quantity, "quantity")
                if qty < 0:
                    warnings.append("Отрицательные строки продаж пропущены как возможные возвраты; требуется сверка с учётной системой.")
                    continue
                item = {"date": day, "sku": sku, "warehouse": warehouse, "quantity": qty}
                for field in ("client_id", "event_id", "price"):
                    if row.get(field) not in (None, ""):
                        item[field] = row[field]
                sales.append(item)
            elif row.get("eta"):
                eta = str(row["eta"]).strip()
                date.fromisoformat(eta)
                inbound.append({"sku": sku, "warehouse": warehouse,
                                "quantity": _float(quantity, "inbound quantity"), "eta": eta})
            elif row.get("start") and row.get("end"):
                stockouts.append({"sku": sku, "warehouse": warehouse,
                                  "start": str(row["start"]).strip(), "end": str(row["end"]).strip()})
    if not products or not sales:
        raise ValueError("CSV input requires dated sales and a SKU column")
    warnings.extend([
        "Не все обязательные атрибуты товара подтверждены; проверьте остаток, срок поставки и цену перед утверждением.",
        "Нулевые значения по умолчанию не являются подтверждёнными остатками или ценами.",
    ])
    return {"as_of": max(item["date"] for item in sales),
            "products": list(products.values()), "sales": sales,
            "stockouts": stockouts, "inbound": inbound,
            "category_policies": {}, "settings": {},
            "metadata": {"source_label": "Локальные CSV", "synthetic": False,
                         "warnings": sorted(set(warnings)),
                         "source_provenance": {"sales": "observed"}}}


def _validate(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object")
    if not isinstance(data.get("products"), list) or not data["products"]:
        raise ValueError("Input requires a non-empty products list")
    if not isinstance(data.get("sales", []), list):
        raise ValueError("Input sales must be a list")
    date.fromisoformat(str(data.get("as_of", "")))
    for key in ("sales", "stockouts", "inbound"):
        data.setdefault(key, [])
    data.setdefault("settings", {})
    data.setdefault("category_policies", {})
    metadata = data.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("Input metadata must be an object")
    metadata.setdefault("source_label", "Загруженные данные")
    metadata.setdefault("synthetic", False)
    metadata.setdefault("warnings", [])
    # Importer consumers may call engine.calculate directly, outside the HTTP
    # gateway. Remove raw customer/document identifiers at this boundary too.
    secret = secrets.token_bytes(32)
    cache = {}
    for row in data["sales"]:
        if not isinstance(row, dict):
            continue
        for field, prefix in (("client_id", "CID"), ("event_id", "EID")):
            raw = row.get(field)
            if raw is None or raw == "":
                continue
            if isinstance(raw, bool) or not isinstance(raw, (str, int)):
                raise ValueError(f"sales.{field} must be a scalar identifier")
            key = field, str(raw)
            if key not in cache:
                cache[key] = prefix + "-" + hmac.new(secret, key[1].encode("utf-8"), hashlib.sha256).hexdigest()[:24]
            row[field] = cache[key]
    return data


def import_files(paths: list[str]) -> dict:
    """Read a canonical template, CSV files, or partner workbook collection."""
    files = [Path(path) for path in paths]
    if not files or any(not path.is_file() for path in files):
        raise ValueError("Select existing local input files")
    suffixes = {path.suffix.lower() for path in files}
    if suffixes == {".json"} and len(files) == 1:
        try:
            data = json.loads(files[0].read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON template") from exc
    elif suffixes == {".csv"}:
        data = _csv_dataset(files)
    elif suffixes <= {".xlsx", ".zip"}:
        from partner_xlsx import import_partner_files
        data = import_partner_files([str(path) for path in files])
    else:
        raise ValueError("Use one canonical JSON, CSV files, or partner XLSX/ZIP files")
    return _validate(data)
