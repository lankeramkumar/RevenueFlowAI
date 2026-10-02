"""Model registration sanity checks — no database required."""

from revenueflowai import models
from revenueflowai.db import Base


def test_all_expected_tables_are_registered():
    expected_tables = {
        "organizations", "business_units", "app_users", "user_business_unit_grants",
        "import_jobs", "import_job_files", "dataset_versions", "audit_events",
        "customers", "orders", "order_lines", "shipments", "shipment_lines",
        "invoices", "invoice_lines", "receipts", "receipt_applications",
        "credit_memos", "credit_applications", "disputes", "order_holds",
    }
    assert expected_tables <= set(Base.metadata.tables.keys())
    assert len(models.__all__) == 20  # excludes the association table, which has no model class
