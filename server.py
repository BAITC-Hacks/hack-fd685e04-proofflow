"""ProofFlow localhost purchasing service. Run: python server.py."""
import json
import hashlib
import hmac
import math
import secrets
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictFloat

import exports
import storage

ROOT = Path(__file__).parent
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
app = FastAPI(title="ProofFlow Procurement", version="0.2.0",
              description="Local recommendations requiring explicit human approval.")


def anonymize_sales_identifiers(dataset):
    """Discard raw customer/document IDs before any storage or calculation.

    The per-operation HMAC key is intentionally never persisted. Matching IDs
    remain equal within this dataset/run, while original names or emails cannot
    appear in detailed diagnostics or saved artifacts.
    """
    sales = dataset.get("sales", [])
    if not isinstance(sales, list):
        return
    key = secrets.token_bytes(32)
    seen = {}
    for row in sales:
        if not isinstance(row, dict):
            continue  # The engine reports malformed rows with their index.
        for field, prefix in (("client_id", "CID"), ("event_id", "EID")):
            value = row.get(field)
            if value is None or value == "":
                continue
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise ValueError(f"sales.{field} must be an anonymous scalar identifier")
            raw = str(value)
            cache_key = field, raw
            if cache_key not in seen:
                digest = hmac.new(key, raw.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
                seen[cache_key] = f"{prefix}-{digest}"
            row[field] = seen[cache_key]


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset: dict | None = None
    settings: dict | None = None
    category_policies: dict | None = None
    filters: dict[str, str | None] | None = None


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantities: dict[str, StrictFloat] = Field(default_factory=dict)
    reviewer: str = Field(min_length=1, max_length=120)


@app.middleware("http")
async def local_write_guard(request: Request, call_next):
    # Avoid cross-origin drive-by mutations to the single-user local service.
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
        from urllib.parse import urlparse
        origin_host = urlparse(origin).netloc
        if origin_host != request.headers.get("host"):
            return JSONResponse({"detail": "Cross-origin writes are not permitted"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


def source_response(dataset):
    from quality import assess_dataset
    metadata = dataset.get("metadata", {})
    preview = {key: value for key, value in dataset.items() if key not in {"sales", "stockouts", "inbound"}}
    preview["_preview"] = True
    preview["quality"] = assess_dataset(dataset)
    preview["metadata"] = {**metadata, "record_counts": {key: len(dataset.get(key, [])) for key in ("products", "sales", "stockouts", "inbound")}}
    return {"dataset": preview, "source_label": metadata.get("source_label", "Загруженные данные")}


@app.get("/api/dataset")
def current_dataset():
    preview = storage.load_dataset_preview()
    if preview is None:
        return {"dataset": None, "source_label": "Выберите демо или загрузите данные"}
    return {"dataset": preview, "source_label": preview.get("metadata", {}).get("source_label", "Загруженные данные")}


@app.post("/api/demo")
def demo():
    from demo_data import build_demo
    data = build_demo()
    anonymize_sales_identifiers(data)
    data["_data_ref"] = uuid4().hex
    storage.save_dataset(data)
    return source_response(data)


@app.post("/api/import")
async def import_data(request: Request):
    from importer import import_files
    try:
        async with request.form(max_files=24, max_fields=12, max_part_size=MAX_UPLOAD_BYTES) as form:
            files = [value for _, value in form.multi_items() if hasattr(value, "filename") and hasattr(value, "read")]
            if not files:
                raise HTTPException(422, "Выберите JSON, CSV, XLSX или ZIP с данными")
            total = 0
            with tempfile.TemporaryDirectory(prefix="proofflow-import-") as folder:
                paths = []
                for index, file in enumerate(files):
                    name = Path(file.filename or "upload").name
                    suffix = Path(name).suffix.lower()
                    if suffix not in {".json", ".csv", ".xlsx", ".zip"}:
                        raise HTTPException(422, f"Неподдерживаемый формат: {suffix}")
                    path = Path(folder) / f"{index}_{name}"
                    with path.open("wb") as output:
                        while chunk := await file.read(1024 * 1024):
                            total += len(chunk)
                            if total > MAX_UPLOAD_BYTES:
                                raise HTTPException(413, "Суммарный размер файлов превышает 80 МБ")
                            output.write(chunk)
                    paths.append(str(path))
                from starlette.concurrency import run_in_threadpool
                data = await run_in_threadpool(import_files, paths)
                if not isinstance(data, dict) or not data.get("products"):
                    raise ValueError("Не найден справочник товаров")
                anonymize_sales_identifiers(data)
                data["_data_ref"] = uuid4().hex
                storage.save_dataset(data)
                return source_response(data)
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/calculate")
def calculate(body: CalculationRequest):
    from engine import calculate as run_engine
    # SQLite deserialisation and request parsing already create independent
    # objects. Avoid another deep copy of ~250k sales rows on every run.
    data = body.dataset if body.dataset is not None else storage.load_dataset()
    if data is None:
        raise HTTPException(422, "Сначала загрузите данные или откройте демо")
    if data.get("_preview"):
        stored = storage.load_dataset()
        if stored is None or data.get("_data_ref") != stored.get("_data_ref"):
            raise HTTPException(409, "Данные изменились. Обновите страницу перед расчётом.")
        # UI edits only the small product/settings preview; transaction history
        # stays local and is never round-tripped through the browser.
        for key in ("products", "settings", "category_policies"):
            if key in data:
                stored[key] = data[key]
        data = stored
    if body.settings is not None:
        data["settings"] = {**data.get("settings", {}), **body.settings}
    if body.category_policies is not None:
        data["category_policies"] = {**data.get("category_policies", {}), **body.category_policies}
    try:
        anonymize_sales_identifiers(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        result = run_engine(data)
        filters = body.filters or {}
        allowed_filters = {"warehouse", "category", "supplier"}
        if set(filters) - allowed_filters:
            raise ValueError("Неизвестный фильтр")
        for row in result["rows"]:
            if not row.get("supplier"):
                row["supplier"] = "UNASSIGNED"
        rows = [row for row in result["rows"] if all(not value or str(row.get(key, "")) == value for key, value in filters.items())]
        keys = [exports.row_key(row) for row in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("Повторяющиеся артикулы в одном складе: проверьте справочник")
        result["rows"] = rows
        groups = {}
        for row in rows:
            supplier = row["supplier"]
            group = groups.setdefault(supplier, {"supplier": supplier, "order_lines": 0, "total_amount": 0.0})
            group["order_lines"] += row["recommended_quantity"] > 0
            group["total_amount"] += row.get("amount", 0)
        result["supplier_groups"] = [
            {**groups[supplier], "total_amount": round(groups[supplier]["total_amount"], 2)}
            for supplier in sorted(groups)
        ]
        result["summary"] = {
            "items": len(rows), "suppliers": len({r["supplier"] for r in rows}),
            "order_lines": sum(r["recommended_quantity"] > 0 for r in rows),
            "total_amount": round(sum(r.get("amount", r["recommended_quantity"] * r.get("unit_price", 0)) for r in rows), 2),
            "critical_items": sum(r.get("urgency") == "critical" for r in rows),
        }
        result.update(run_id=uuid4().hex, created_at=datetime.now(timezone.utc).isoformat(),
                      source_label=data.get("metadata", {}).get("source_label", "Загруженные данные"),
                      settings=data.get("settings", {}), filters=filters, approval=None)
        storage.save_run(result)
        return storage.load_run(result["run_id"])
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise HTTPException(422, str(exc)) from exc


def require_run(run_id):
    run = storage.load_run(run_id)
    if run is None:
        raise HTTPException(404, "Расчёт не найден")
    return run


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    return require_run(run_id)


@app.get("/api/runs/{run_id}/item")
def item_detail(run_id: str, sku: str, warehouse: str):
    item = storage.load_item(run_id, f"{warehouse}::{sku}")
    if item is None:
        raise HTTPException(404, "Позиция расчёта не найдена")
    return item


@app.post("/api/runs/{run_id}/approve")
def approve(run_id: str, body: ApprovalRequest):
    run = require_run(run_id)
    if run.get("approval"):
        raise HTTPException(409, "Расчёт уже утверждён. Создайте новый для изменений.")
    if not body.reviewer.strip():
        raise HTTPException(422, "Укажите ответственного сотрудника")
    expected = {exports.row_key(row): row for row in run["rows"]}
    if set(body.quantities) - expected.keys():
        raise HTTPException(422, "Корректировка содержит неизвестную позицию")
    if not expected:
        raise HTTPException(422, "Пустой расчёт нельзя утвердить")
    quantities = {key: body.quantities.get(key, row["recommended_quantity"]) for key, row in expected.items()}
    if any(not math.isfinite(value) or value < 0 or value > 1e12 for value in quantities.values()):
        raise HTTPException(422, "Количество должно быть конечным числом от 0 до 10^12")
    approval = {"approval_id": uuid4().hex, "status": "approved",
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "reviewer": body.reviewer.strip(), "quantities": quantities,
                "supplier_sent": False}
    try:
        storage.save_approval(run_id, approval)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Расчёт уже утверждён") from exc
    return approval


@app.get("/api/runs/{run_id}/export")
def export_run(run_id: str, format: str = "csv", supplier: str | None = None):
    run = require_run(run_id)
    if format not in {"csv", "xlsx"}:
        raise HTTPException(422, "Поддерживаются csv и xlsx")
    payload = exports.to_csv(run, supplier) if format == "csv" else exports.to_xlsx(run, supplier)
    media = "text/csv; charset=utf-8" if format == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    name = f"proofflow-{run_id[:8]}-{'approved' if run.get('approval') else 'draft'}.{format}"
    return Response(payload, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/template")
def template():
    from demo_data import build_demo
    content = json.dumps(build_demo(), ensure_ascii=False, indent=2).encode("utf-8")
    return Response(content, media_type="application/json", headers={"Content-Disposition": 'attachment; filename="proofflow-synthetic-template.json"'})


@app.get("/")
def index():
    path = ROOT / "frontend" / "index.html"
    if not path.exists():
        raise HTTPException(503, "Интерфейс собирается. API доступно в /docs")
    return FileResponse(path)


@app.get("/app.js")
def javascript():
    return FileResponse(ROOT / "frontend" / "app.js", media_type="text/javascript")


@app.get("/styles.css")
def stylesheet():
    return FileResponse(ROOT / "frontend" / "styles.css", media_type="text/css")


if (ROOT / "frontend").is_dir():
    app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
