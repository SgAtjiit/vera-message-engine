from fastapi.testclient import TestClient
from app.main import app
from app.state import state


def test_main_lifespan_and_routes():
    # Using TestClient as context manager triggers the lifespan startup event
    with TestClient(app) as client:
        # 1. Test root route
        res_root = client.get("/")
        assert res_root.status_code == 200
        data_root = res_root.json()
        assert data_root["name"] == "vera-bot"
        assert data_root["status"] == "running"

        # 2. Verify all 5 routes are active and mounted
        res_health = client.get("/v1/health")
        assert res_health.status_code == 200

        res_meta = client.get("/v1/metadata")
        assert res_meta.status_code == 200

        res_ctx = client.post(
            "/v1/context",
            json={
                "scope": "category",
                "context_id": "dentists",
                "version": 1,
                "payload": {"slug": "dentists"},
                "delivered_at": "2026-04-26T10:00:00Z",
            },
        )
        assert res_ctx.status_code == 200

        res_tick = client.post(
            "/v1/tick",
            json={"now": "2026-04-26T10:00:00Z", "available_triggers": []},
        )
        assert res_tick.status_code == 200

        res_reply = client.post(
            "/v1/reply",
            json={
                "conversation_id": "conv_main_test",
                "merchant_id": "m_001_drmeera_dentist_delhi",
                "from_role": "merchant",
                "message": "Ok lets do it. Whats next?",
                "received_at": "2026-04-26T10:00:00Z",
                "turn_number": 2,
            },
        )
        assert res_reply.status_code == 200
        assert res_reply.json()["action"] == "send"


def test_validation_error_handler():
    with TestClient(app) as client:
        # Invalid body to /v1/context (missing required fields)
        res = client.post("/v1/context", json={"bad_field": 123})
        assert res.status_code == 422
        data = res.json()
        assert data["accepted"] is False
        assert data["error"] == "validation_error"


if __name__ == "__main__":
    test_main_lifespan_and_routes()
    test_validation_error_handler()
    print("All main.py tests passed successfully!")
