"""Phase 0 smoke tests: the app boots, and the contract is reachable."""

from fastapi.testclient import TestClient


def test_health_endpoint_reports_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_schema_is_generated(client: TestClient) -> None:
    """The OpenAPI document is what the frontend types are generated from; if it
    fails to build, the contract pipeline is broken."""
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"]
    assert "/health" in schema["paths"]
