"""Small generated workbooks test the adapter without committing partner data."""

from datetime import date
from pathlib import Path
from zipfile import ZipFile

from openpyxl import Workbook

from importer import import_files


def _book(path: Path, rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_iek_real_schema_sources_are_joined_by_1c_code(tmp_path):
    sale = tmp_path / "Динамика продаж_IEK.xlsx"
    stock = tmp_path / "Ежемесячные остатки ИЭК.xlsx"
    pack = tmp_path / "MOQ ИЭК.xlsx"
    route = tmp_path / "Путь ИЭК.xlsx"
    _book(sale, [
        ["Дата", "Номер", "Документ", "Код", "Номенклатура", "Ед.", "Склад", "Количество"],
        ["20.09.2026 12:05:00", "doc-1", "Накладная", "SKU-1", "Кабель", "шт", "Алматы", 10],
        ["21.09.2026 12:05:00", "doc-2", "Возврат", "SKU-1", "Кабель", "шт", "Алматы", -2],
    ])
    _book(stock, [
        ["Номенклатура", "Ед.", "Номенклатура.Код", "авг. 2026", "сент. 2026", "Итого"],
        ["Кабель", "шт", "SKU-1", 100, 7, 999],
    ])
    _book(pack, [
        ["№", "Код 1с", "Артикул поставщика", "Наименование", "Мин. разр. к отгр."],
        [1, "SKU-1", "ARTICLE-1", "Кабель", 4],
    ])
    _book(route, [
        ["Код 1с", "Артикул ИЭК", "Наименование",
         "Поставка (поступление до 30.09.2026)"],
        ["SKU-1", "ARTICLE-1", "Кабель", 8],
    ])
    dataset = import_files([str(pack), str(stock), str(sale), str(route)])
    assert len(dataset["sales"]) == 1
    assert dataset["sales"][0]["date"] == "2026-09-20"
    assert "client_id" not in dataset["sales"][0]
    assert dataset["sales"][0]["event_id"] != "doc-1"  # importer pseudonymizes
    assert dataset["metadata"]["record_counts"]["nonpositive_sales"] == 1
    product = next(row for row in dataset["products"] if row["sku"] == "SKU-1")
    assert product["on_hand"] == 7  # Not the "Итого" total.
    assert product["pack_size"] == 4
    assert product["unit"] == "шт"
    assert product["moq"] == 0
    assert product["unit_price"] == 0
    assert product["lead_days"] == 0
    assert dataset["inbound"] == [{"sku": "SKU-1", "warehouse": "Алматы",
                                   "quantity": 8, "eta": "2026-09-30"}]


def test_systeme_report_uses_free_stock_and_no_coefficient_guess(tmp_path):
    sale = tmp_path / "Динамика продаж_Systeme.xlsx"
    report = tmp_path / "Товар в пути_Systeme.xlsx"
    _book(sale, [
        ["Дата", "Номер", "Документ", "Код", "Номенклатура", "Ед.", "Склад", "Количество"],
        ["22.09.2026 10:00:00", "doc-1", "Накладная", "S-1", "Розетка", "шт", "Алматы", 5],
    ])
    headers = [None] * 55
    for index, label in {2: "Код 1с", 3: "Наименование", 4: "Категория 2026",
                         43: "Кэф. Роста", 44: "Кэф. Сез-ти", 49: "Остаток",
                         50: "Зарезервировано", 51: "Свободный остаток",
                         54: "СЭ в пути 24.09"}.items():
        headers[index] = label
    line = [None] * 55
    for index, value in {2: "S-1", 3: "Розетка", 4: 3, 43: -8.4,
                         44: 17, 49: 100, 50: 20, 51: 80, 54: 12}.items():
        line[index] = value
    _book(report, [["Отчёт"], headers, line])
    dataset = import_files([str(sale), str(report)])
    product = next(row for row in dataset["products"] if row["sku"] == "S-1")
    assert product["on_hand"] == 80
    assert str(product["category"]) == "3"
    assert product.get("growth", 0) == 0
    assert dataset["inbound"][0]["eta"] == "2026-09-24"
    assert dataset["inbound"][0]["quantity"] == 12


def test_zip_member_path_cannot_escape_extract_dir(tmp_path):
    xlsx = tmp_path / "Динамика продаж_IEK.xlsx"
    _book(xlsx, [
        ["Дата", "Номер", "Документ", "Код", "Номенклатура", "Ед.", "Склад", "Количество"],
        [date(2026, 9, 22), "doc", "Накладная", "SKU-1", "Кабель", "шт", "Алматы", 1],
    ])
    archive_path = tmp_path / "IEK.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.write(xlsx, "../../Динамика продаж_IEK.xlsx")
    dataset = import_files([str(archive_path)])
    assert len(dataset["sales"]) == 1
    assert not (tmp_path.parent / "Динамика продаж_IEK.xlsx").exists()
