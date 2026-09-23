"""Download-only supplier files. This module cannot transmit orders."""
import csv
import io
from decimal import Decimal, ROUND_HALF_UP


COLUMNS = [
    ("status", "Статус"), ("supplier", "Поставщик"), ("warehouse", "Склад"),
    ("sku", "Артикул"), ("name", "Наименование"), ("unit", "Ед. изм."),
    ("recommended_quantity", "Рекомендовано"), ("quantity", "Количество к заказу"),
    ("unit_price", "Цена (из источника)"), ("amount", "Сумма (из источника)"),
    ("urgency", "Срочность"), ("explanation", "Обоснование"),
    ("reviewer", "Утвердил"), ("approved_at", "Дата утверждения"),
]


def row_key(row):
    return f"{row.get('warehouse', '')}::{row['sku']}"


def export_rows(run, supplier=None):
    approval = run.get("approval")
    rows = []
    for source in run["rows"]:
        if supplier and source.get("supplier") != supplier:
            continue
        row = dict(source)
        quantity = approval["quantities"][row_key(row)] if approval else row["recommended_quantity"]
        row.update(quantity=quantity, status="Утверждён" if approval else "Черновик — требует проверки",
                   reviewer=approval["reviewer"] if approval else "",
                   approved_at=approval["approved_at"] if approval else "")
        row["amount"] = float((Decimal(str(quantity)) * Decimal(str(row.get("unit_price", 0)))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        rows.append(row)
    return rows


def safe_cell(value):
    # Prevent untrusted names/identifiers becoming formulas in spreadsheet viewers.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value if value is not None else ""


def to_csv(run, supplier=None):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow([title for _, title in COLUMNS])
    for row in export_rows(run, supplier):
        writer.writerow([safe_cell(row.get(key, "")) for key, _ in COLUMNS])
    return output.getvalue().encode("utf-8-sig")


def to_xlsx(run, supplier=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    book = Workbook()
    sheet = book.active
    sheet.title = "Заказы поставщикам"
    sheet.append([title for _, title in COLUMNS])
    for row in export_rows(run, supplier):
        sheet.append([safe_cell(row.get(key, "")) for key, _ in COLUMNS])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="15263A")
        cell.alignment = Alignment(wrap_text=True)
    widths = [28, 25, 22, 24, 44, 12, 18, 24, 20, 20, 16, 80, 24, 28]
    for i, width in enumerate(widths, 1):
        sheet.column_dimensions[sheet.cell(1, i).column_letter].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in (5, 12))
        for index in (7, 8, 9, 10):
            row[index-1].number_format = "#,##0.00"
    info = book.create_sheet("Методология")
    info.append(["Поле", "Значение"])
    info.append(["Расчёт", run["run_id"]])
    info.append(["На дату", run.get("as_of", "")])
    info.append(["Источник", run.get("source_label", "")])
    info.append(["Статус", "Утверждён" if run.get("approval") else "Черновик — требует проверки"])
    info.append(["Назначение", "Файл для проверки и ручной загрузки. Автоматическая отправка поставщику не выполняется."])
    for warning in run.get("warnings", []):
        info.append(["Ограничение", safe_cell(str(warning))])
    info.column_dimensions["A"].width = 24
    info.column_dimensions["B"].width = 100
    for row in info:
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()
