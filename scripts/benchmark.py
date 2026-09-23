"""Local, read-only timing of import and calculation; prints no source rows."""

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="Local JSON/CSV/XLSX/ZIP input paths; no arguments runs synthetic demo")
    args = parser.parse_args()

    start = perf_counter()
    if args.files:
        from importer import import_files
        paths = []
        for entry in args.files:
            source = Path(entry)
            if source.is_dir():
                paths.extend(str(path) for path in sorted(source.rglob("*"))
                             if path.is_file() and path.suffix.lower() in {".xlsx", ".csv", ".json", ".zip"})
            elif source.is_file():
                paths.append(str(source))
            else:
                raise SystemExit(f"Input not found: {entry}")
        if not paths:
            raise SystemExit("No supported files found")
        dataset = import_files(paths)
        source = "local partner files"
    else:
        from demo_data import build_demo
        dataset = build_demo()
        source = "synthetic demo"
    imported = perf_counter()

    from engine import calculate
    if not dataset.get("products") or not dataset.get("sales"):
        raise SystemExit("Input normalization produced no products or sales")
    result = calculate(dataset)
    calculated = perf_counter()
    report = {
        "source": source,
        "record_counts": {name: len(dataset.get(name, [])) for name in ("products", "sales", "stockouts", "inbound")},
        "result_counts": {
            "items": len(result.get("rows", [])),
            "order_lines": sum(row.get("recommended_quantity", 0) > 0 for row in result.get("rows", [])),
            "warnings": len(result.get("warnings", [])),
        },
        "seconds": {
            "load_or_import": round(imported - start, 3),
            "calculation": round(calculated - imported, 3),
            "total": round(calculated - start, 3),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
