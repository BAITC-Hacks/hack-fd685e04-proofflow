"""Coverage assessment reports evidence and assumptions without exposing PII."""
from demo_data import build_demo
from quality import assess_dataset


def test_synthetic_demo_marked_assumed_not_observed():
    result = assess_dataset(build_demo())
    assert result["synthetic"] is True
    assert result["record_counts"]["products"] == 10
    assert result["field_coverage"]["lead_days"]["assumed"] == 10
    assert result["field_coverage"]["lead_days"]["observed"] == 0
    assert result["field_coverage"]["lead_days"]["observed_share"] == 0
    assert result["sales_identifiers"]["has_client_id"] is True


def test_explicit_provenance_counts_confirmed_skus_and_unknown_separately():
    data = {
        "products": [
            {"sku": "A", "lead_days": 7, "on_hand": 10, "unit_price": 4},
            {"sku": "B", "lead_days": 9, "on_hand": 0, "unit_price": 6,
             "provenance": {"lead_days": "assumed", "unit_price": "observed"}},
            {"sku": "C", "on_hand": 1},
        ],
        "sales": [{"client_id": "private@example.com"}, {"event_id": "DOC-123"}],
        "stockouts": [], "inbound": [],
        "metadata": {"field_provenance": {"lead_days": "observed", "on_hand": "observed"},
                     "source_provenance": {"sales": "observed"}},
    }
    result = assess_dataset(data)
    assert result["field_coverage"]["lead_days"] == {
        "present": 2, "observed": 1, "assumed": 1, "unknown": 0,
        "missing": 1, "observed_share": 1 / 3,
    }
    assert result["field_coverage"]["unit_price"]["unknown"] == 1
    assert result["field_coverage"]["on_hand"]["observed_share"] == 1
    assert result["source_status"]["sales"] == "observed"
    assert result["source_status"]["stockouts"] == "unknown"
    assert result["sales_identifiers"]["client_id_rows"] == 1
    assert result["sales_identifiers"]["event_id_rows"] == 1
    assert "private@example.com" not in str(result)
    assert "DOC-123" not in str(result)


def test_absent_provenance_is_unknown_not_invented_observed():
    result = assess_dataset({"products": [{"sku": "A", "lead_days": 10,
                                           "on_hand": 0, "unit_price": 0}],
                             "sales": [], "metadata": {"warnings": ["Sensitive client Jane"]}})
    assert all(result["field_coverage"][key]["unknown"] == 1
               for key in ("lead_days", "on_hand", "unit_price"))
    assert result["source_status"]["stockouts"] == "missing"
    assert result["metadata_warning_count"] == 1
    assert "Jane" not in str(result)
    assert any("Нет строк продаж" in warning for warning in result["warnings"])
