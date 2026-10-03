"""Demo profile: reproducibility and the minimum scale
synthetic_data_requirements.md requires (30+ customers, 200+ orders).
Activation/isolation checks that need a live database are in
tests/integration/test_demo_profile_activation.py.
"""

from datetime import date

from revenueflowai.ingestion.validator import validate_bundle
from revenueflowai.seed.demo import generate_demo_bundle

AS_OF = date(2026, 10, 2)


def test_demo_bundle_meets_minimum_scale():
    bundle = generate_demo_bundle(seed=42, as_of=AS_OF)
    assert len(bundle.rows["customers.csv"]) >= 30
    assert len(bundle.rows["orders.csv"]) >= 200


def test_demo_bundle_uses_both_currencies():
    bundle = generate_demo_bundle(seed=42, as_of=AS_OF)
    currencies = {row["currency"] for row in bundle.rows["orders.csv"]}
    assert currencies == {"USD", "EUR"}


def test_demo_bundle_is_reproducible_for_the_same_seed():
    first = generate_demo_bundle(seed=42, as_of=AS_OF)
    second = generate_demo_bundle(seed=42, as_of=AS_OF)
    assert first.rows == second.rows


def test_demo_bundle_differs_for_a_different_seed():
    first = generate_demo_bundle(seed=42, as_of=AS_OF)
    second = generate_demo_bundle(seed=43, as_of=AS_OF)
    assert first.rows != second.rows


def test_demo_bundle_passes_real_validation(tmp_path):
    import csv

    from revenueflowai.seed.schema import CSV_COLUMNS

    bundle = generate_demo_bundle(seed=42, as_of=AS_OF)
    for filename, columns in CSV_COLUMNS.items():
        with (tmp_path / filename).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            for row in bundle.rows.get(filename, []):
                writer.writerow(row)

    result = validate_bundle(tmp_path)
    assert result.is_valid, [e.message for e in result.errors]


def test_demo_bundle_includes_realistic_variety():
    bundle = generate_demo_bundle(seed=42, as_of=AS_OF)
    # At least some disputes and holds -- "realistic partial fulfillment,
    # invoices/receipts/disputes/holds" per synthetic_data_requirements.md.
    assert len(bundle.rows.get("disputes.csv", [])) > 0
    assert len(bundle.rows.get("order_holds.csv", [])) > 0
    assert len(bundle.rows.get("receipts.csv", [])) > 0
    # Not every order is fully shipped/invoiced -- some partial, some unshipped.
    assert len(bundle.rows["orders.csv"]) > len(bundle.rows.get("invoices.csv", []))
