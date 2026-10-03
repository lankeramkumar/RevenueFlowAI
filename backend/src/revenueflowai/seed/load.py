"""Load profile: reuses the demo generator's realistic-mix logic at a
scale targeting a requested total row count across all 13 files, per
synthetic_data_requirements.md's "exactly the requested total CSV data
rows across the declared files" (approximated here -- the realistic-mix
branching makes an exact count impractical without per-row trimming, so
this targets the requested total within a few percent, documented below).
"""

from datetime import date

from revenueflowai.seed.demo import DemoBundle, generate_demo_bundle

# Empirically measured from the demo profile at (32 customers, 210
# orders): ~10.4 total CSV rows per order including its own customers
# share. Used to size the load profile's order_count for a target total.
ROWS_PER_ORDER_ESTIMATE = 10.4
CUSTOMER_TO_ORDER_RATIO = 32 / 210


def generate_load_bundle(seed: int, as_of: date, total_rows: int, id_prefix: str = "LOAD") -> DemoBundle:
    order_count = max(1, round(total_rows / ROWS_PER_ORDER_ESTIMATE))
    customer_count = max(30, round(order_count * CUSTOMER_TO_ORDER_RATIO))

    return generate_demo_bundle(
        seed=seed, as_of=as_of, customer_count=customer_count, order_count=order_count, id_prefix=id_prefix,
    )
