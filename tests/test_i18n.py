"""Localized narratives must never change procurement arithmetic or stable codes."""
from copy import deepcopy
from datetime import date, timedelta

import pytest

from demo_data import build_demo
from engine import calculate
from localization import MESSAGES, SUPPORTED_LOCALES


def _run(locale):
    dataset = build_demo()
    dataset.setdefault("settings", {})["locale"] = locale
    return calculate(dataset)


def test_catalogues_are_complete_and_locales_explicit():
    assert SUPPORTED_LOCALES == ("ru", "kk", "en")
    assert set(MESSAGES["ru"]) == set(MESSAGES["kk"]) == set(MESSAGES["en"])
    with pytest.raises(ValueError, match="settings.locale"):
        _run("de")
    with pytest.raises(ValueError, match="settings.locale"):
        _run(None)


def test_language_switch_preserves_every_numeric_and_machine_field():
    results = {locale: _run(locale) for locale in SUPPORTED_LOCALES}
    baseline = results["ru"]
    for locale, result in results.items():
        assert result["locale"] == locale
        assert result["summary"] == baseline["summary"]
        assert result["supplier_groups"] == baseline["supplier_groups"]
        assert len(result["rows"]) == len(baseline["rows"])
        for translated, original in zip(result["rows"], baseline["rows"]):
            for key, expected in original.items():
                if key in {"explanation", "warnings", "excluded_events"}:
                    continue
                assert translated[key] == expected, (locale, original["sku"], key)
            assert translated["urgency"] == original["urgency"]
            assert str(translated["recommended_quantity"]) in translated["explanation"]
    assert "Прогноз спроса" in baseline["rows"][0]["explanation"]
    assert "болжамды сұраныс" in results["kk"]["rows"][0]["explanation"]
    assert "Forecast demand" in results["en"]["rows"][0]["explanation"]


@pytest.mark.parametrize(
    ("locale", "reason_fragment", "document_fragment", "inbound_fragment"),
    [
        ("ru", "Разовый выброс", "номером документа", "не учтена в прогнозе"),
        ("kk", "Бір күндік", "құжат нөміріне", "болжамға енгізілмеді"),
        ("en", "One-day outlier", "document numbers", "excluded from forecast"),
    ],
)
def test_warnings_and_exclusion_reasons_are_localized(
    locale, reason_fragment, document_fragment, inbound_fragment
):
    data = deepcopy(build_demo())
    data.setdefault("settings", {})["locale"] = locale
    data["sales"].append({
        "date": (date.fromisoformat(data["as_of"]) - timedelta(days=5)).isoformat(),
        "sku": "DEMO-INBOUND-05", "warehouse": "A", "quantity": 500,
        "event_id": "ANONYMOUS-DOCUMENT",
    })
    data["inbound"].append({
        "sku": "DEMO-INBOUND-05", "warehouse": "A", "quantity": 10,
        "eta": data["as_of"],
    })
    result = calculate(data)
    row = next(r for r in result["rows"] if r["sku"] == "DEMO-INBOUND-05")
    assert reason_fragment in row["excluded_events"][0]["reason"]
    assert any(document_fragment in warning for warning in row["warnings"])
    assert any(inbound_fragment in warning for warning in result["warnings"])
