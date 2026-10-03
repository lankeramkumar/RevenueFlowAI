"""Demo profile generator: a larger, randomized-but-reproducible bundle.

synthetic_data_requirements.md: "At least 30 customers, 200 orders,
realistic partial fulfillment, invoices/receipts/disputes/holds, USD and
EUR." Uses `random.Random(seed)` exclusively (never the system RNG or
wall clock) so the same seed always produces the same bundle.

"plus a second organization/business unit for isolation tests" is a
property of how this bundle gets *used* in a test (uploaded into two
different organizations through the real ingestion pipeline and checked
for leakage), not something the CSV content itself encodes -- a CSV
carries no organization identity; that's assigned by upload context, per
intent.md. See tests/integration/test_demo_profile.py.
"""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

Row = dict[str, str]

CUSTOMER_COUNT = 32
ORDER_COUNT = 210
ITEM_CODES = ["WIDGET-A", "WIDGET-B", "GADGET-X", "GADGET-Y", "THINGAMAJIG", "DOOHICKEY"]


def _money(value: Decimal | float) -> str:
    return f"{Decimal(value):.2f}"


@dataclass
class DemoBundle:
    rows: dict[str, list[Row]] = field(default_factory=dict)

    def add(self, filename: str, row: Row) -> None:
        self.rows.setdefault(filename, []).append(row)


def generate_demo_bundle(seed: int, as_of: date) -> DemoBundle:
    rng = random.Random(seed)
    bundle = DemoBundle()

    customer_ids = [f"DEMO-CUST-{i:03d}" for i in range(1, CUSTOMER_COUNT + 1)]
    customer_currency = {cid: ("EUR" if i % 3 == 0 else "USD") for i, cid in enumerate(customer_ids)}

    customer_terms: dict[str, int] = {}
    for cid in customer_ids:
        terms_days = rng.choice([15, 30, 45, 60])
        customer_terms[cid] = terms_days
        bundle.add("customers.csv", {
            "customer_id": cid, "account_number": f"ACC-{cid[-3:]}",
            "customer_name": f"Demo Customer {cid[-3:]}",
            "payment_terms_days": str(terms_days),
        })

    hold_reasons = ["CREDIT_LIMIT", "MISSING_SHIP_TO", "FRAUD_REVIEW", "QUALITY_HOLD"]
    dispute_reasons = ["Pricing discrepancy", "Quantity discrepancy on delivery", "Damaged goods claim"]

    for order_index in range(1, ORDER_COUNT + 1):
        order_id = f"DEMO-ORD-{order_index:04d}"
        customer_id = rng.choice(customer_ids)
        currency = customer_currency[customer_id]
        order_date = as_of - timedelta(days=rng.randint(5, 180))

        bundle.add("orders.csv", {
            "order_id": order_id, "customer_id": customer_id, "order_date": order_date.isoformat(),
            "currency": currency, "status": "open",
            "promised_ship_date": (order_date + timedelta(days=7)).isoformat(),
        })

        line_count = rng.randint(1, 3)
        order_lines = []
        for line_index in range(1, line_count + 1):
            line_id = f"{order_id}-OL{line_index}"
            quantity = Decimal(rng.randint(1, 20))
            unit_price = Decimal(rng.choice([10, 25, 50, 75, 100, 150]))
            bundle.add("order_lines.csv", {
                "order_line_id": line_id, "order_id": order_id, "item_code": rng.choice(ITEM_CODES),
                "ordered_quantity": str(quantity), "cancelled_quantity": "0",
                "unit_price": _money(unit_price), "line_amount": _money(quantity * unit_price),
            })
            order_lines.append((line_id, quantity, unit_price))

        # Fulfillment mix: 70% fully shipped+billed, 20% partially shipped, 10% unshipped.
        fulfillment_roll = rng.random()
        if fulfillment_roll < 0.10:
            continue  # unshipped: no shipment/invoice rows at all

        shipment_date = order_date + timedelta(days=rng.randint(1, 10))
        shipment_id = f"{order_id}-SHP"
        bundle.add("shipments.csv", {
            "shipment_id": shipment_id, "order_id": order_id, "shipment_date": shipment_date.isoformat(),
            "status": "shipped", "delivery_date": (shipment_date + timedelta(days=3)).isoformat(),
        })

        is_partial = fulfillment_roll < 0.30  # the next 20% band above the 10% unshipped band
        invoice_lines_rows = []
        invoice_total = Decimal("0")
        for line_id, quantity, unit_price in order_lines:
            shipped_qty = (quantity * Decimal("6") // Decimal("10")) if is_partial else quantity
            if shipped_qty <= 0:
                shipped_qty = Decimal("1")
            shipment_line_id = f"{line_id}-SL"
            bundle.add("shipment_lines.csv", {
                "shipment_line_id": shipment_line_id, "shipment_id": shipment_id,
                "order_line_id": line_id, "shipped_quantity": str(shipped_qty),
            })
            billed_qty = shipped_qty  # fully bill what shipped, for the invoiced portion
            line_amount = billed_qty * unit_price
            invoice_lines_rows.append((shipment_line_id, line_id, billed_qty, line_amount))
            invoice_total += line_amount

        invoice_date = shipment_date
        due_date = invoice_date + timedelta(days=customer_terms[customer_id])
        invoice_id = f"{order_id}-INV"
        invoice_status = "posted"
        bundle.add("invoices.csv", {
            "invoice_id": invoice_id, "customer_id": customer_id, "order_id": order_id,
            "invoice_date": invoice_date.isoformat(), "due_date": due_date.isoformat(),
            "currency": currency, "invoice_amount": _money(invoice_total), "status": invoice_status,
        })
        for i, (shipment_line_id, order_line_id, billed_qty, line_amount) in enumerate(invoice_lines_rows, 1):
            bundle.add("invoice_lines.csv", {
                "invoice_line_id": f"{invoice_id}-IL{i}", "invoice_id": invoice_id,
                "order_line_id": order_line_id, "shipment_line_id": shipment_line_id,
                "billed_quantity": str(billed_qty), "line_amount": _money(line_amount),
            })

        # Payment mix: 50% paid in full, 25% partially paid, 25% unpaid.
        payment_roll = rng.random()
        if payment_roll < 0.75:
            if payment_roll < 0.50:
                paid_amount = invoice_total
            else:
                paid_amount = invoice_total * Decimal("6") / Decimal("10")
            paid_amount = paid_amount.quantize(Decimal("0.01"))
            if paid_amount > 0:
                receipt_id = f"{order_id}-RCP"
                bundle.add("receipts.csv", {
                    "receipt_id": receipt_id, "customer_id": customer_id,
                    "receipt_date": (due_date - timedelta(days=rng.randint(0, 5))).isoformat(),
                    "currency": currency, "receipt_amount": _money(paid_amount), "status": "posted",
                    "remittance_reference": invoice_id,
                })
                bundle.add("receipt_applications.csv", {
                    "application_id": f"{receipt_id}-APP", "receipt_id": receipt_id, "invoice_id": invoice_id,
                    "applied_amount": _money(paid_amount), "application_date": due_date.isoformat(),
                    "status": "posted",
                })

        # ~8% of invoices get an open dispute.
        if rng.random() < 0.08:
            bundle.add("disputes.csv", {
                "dispute_id": f"{invoice_id}-DISP", "invoice_id": invoice_id,
                "disputed_amount": _money(invoice_total * Decimal("2") / Decimal("10")),
                "reason": rng.choice(dispute_reasons), "status": "open",
                "opened_date": (due_date - timedelta(days=rng.randint(1, 10))).isoformat(),
                "closed_date": "",
            })

        # ~6% of orders get a hold; most of those are active, some released.
        if rng.random() < 0.06:
            applied_date = order_date + timedelta(days=rng.randint(0, 3))
            released = rng.random() < 0.4
            bundle.add("order_holds.csv", {
                "hold_id": f"{order_id}-HOLD", "order_id": order_id, "hold_reason": rng.choice(hold_reasons),
                "status": "released" if released else "active",
                "applied_date": applied_date.isoformat(),
                "released_date": (applied_date + timedelta(days=5)).isoformat() if released else "",
                "linked_invoice_id": "",
            })

    return bundle
