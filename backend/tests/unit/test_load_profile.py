"""Load profile: targets a requested total row count (approximately --
the realistic-mix branching logic makes an exact count impractical, see
seed/load.py) and remains reproducible for a given seed.
"""

from datetime import date

from revenueflowai.seed.load import generate_load_bundle

AS_OF = date(2026, 10, 2)


def test_load_bundle_approximates_requested_total_rows():
    bundle = generate_load_bundle(seed=42, as_of=AS_OF, total_rows=10_000)
    total = sum(len(rows) for rows in bundle.rows.values())
    # Within 20% of the target -- the realistic-mix generator can't hit an
    # exact count without per-row trimming; this proves the sizing logic
    # scales roughly linearly, not that it's exact.
    assert 8_000 <= total <= 12_000


def test_load_bundle_is_reproducible_for_the_same_seed():
    first = generate_load_bundle(seed=42, as_of=AS_OF, total_rows=5_000)
    second = generate_load_bundle(seed=42, as_of=AS_OF, total_rows=5_000)
    assert first.rows == second.rows


def test_load_bundle_uses_a_distinct_id_prefix_from_demo():
    bundle = generate_load_bundle(seed=42, as_of=AS_OF, total_rows=1_000)
    assert all(row["customer_id"].startswith("LOAD-CUST-") for row in bundle.rows["customers.csv"])
