import httpx

from revenueflowai.observability import registry
from revenueflowai.worker import _serve_metrics


def test_worker_serves_registry_at_metrics_path():
    registry.reset()
    registry.inc("import_jobs_total", outcome="activated")
    server = _serve_metrics(port=0)
    try:
        port = server.server_address[1]
        body = httpx.get(f"http://127.0.0.1:{port}/metrics").text
        assert 'import_jobs_total{outcome="activated"} 1' in body
        assert httpx.get(f"http://127.0.0.1:{port}/other").status_code == 404
    finally:
        server.shutdown()
        server.server_close()
