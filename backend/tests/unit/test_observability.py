from fastapi.testclient import TestClient

from revenueflowai.main import app
from revenueflowai.observability import registry


def test_metrics_use_route_templates_not_raw_paths():
    registry.reset()
    client = TestClient(app)
    client.get("/api/v1/customers/DEMO-CUST-000001?business_unit_id=00000000-0000-0000-0000-000000000000")
    client.get("/api/v1/no-such-route/abc")
    body = client.get("/metrics").text
    assert 'route="/api/v1/customers/{customer_external_id}"' in body
    assert 'route="unmatched"' in body
    assert "DEMO-CUST-000001" not in body


def test_request_id_is_echoed_and_generated_when_absent():
    client = TestClient(app)
    supplied = client.get("/healthz", headers={"X-Request-ID": "trace-abc-12345678"})
    assert supplied.headers["x-request-id"] == "trace-abc-12345678"

    generated = client.get("/healthz")
    assert len(generated.headers["x-request-id"]) == 32


def test_unsafe_request_id_is_replaced_not_reflected():
    client = TestClient(app)
    response = client.get("/healthz", headers={"X-Request-ID": "bad id with spaces\n"})
    assert response.headers["x-request-id"] != "bad id with spaces"


def test_metrics_endpoint_exposes_request_counters_in_prometheus_format():
    registry.reset()
    client = TestClient(app)
    client.get("/healthz")
    body = client.get("/metrics").text
    assert "# TYPE http_requests_total counter" in body
    assert 'http_requests_total{method="GET",route="/healthz",status="200"} 1' in body
    assert "# TYPE http_request_duration_seconds histogram" in body
    assert 'http_request_duration_seconds_bucket{method="GET",route="/healthz",le="+Inf"} 1' in body
