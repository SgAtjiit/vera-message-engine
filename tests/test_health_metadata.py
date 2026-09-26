from fastapi.testclient import TestClient
from app.main import app
from app.state import state
import app.config as cfg

client = TestClient(app)


def test_health_endpoints_live():
    # 1. Test /v1/health
    res = client.get("/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert isinstance(data["uptime_seconds"], int)
    assert data["uptime_seconds"] >= 0

    counts = data["contexts_loaded"]
    assert counts["category"] >= 5
    assert counts["merchant"] >= 50
    assert counts["customer"] >= 200
    assert counts["trigger"] >= 100

    # 2. Test /v1/healthz, /health, /healthz aliases
    for path in ["/v1/healthz", "/health", "/healthz"]:
        r = client.get(path)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["contexts_loaded"] == counts

    # 3. Test live update: add a new customer context and verify health reflects it live
    state.upsert_context("customer", "c_live_test_001", 1, {"name": "Live Customer"})
    res_after = client.get("/v1/health")
    assert res_after.json()["contexts_loaded"]["customer"] == 201


def test_metadata_endpoint():
    res = client.get("/v1/metadata")
    assert res.status_code == 200
    data = res.json()
    assert data["team_name"] == cfg.TEAM_NAME
    assert data["team_members"] == cfg.TEAM_MEMBERS
    assert data["model"] == cfg.MODEL
    assert data["approach"] == cfg.APPROACH
    assert data["version"] == cfg.VERSION


if __name__ == "__main__":
    test_health_endpoints_live()
    test_metadata_endpoint()
    print("Health and metadata tests passed successfully!")
