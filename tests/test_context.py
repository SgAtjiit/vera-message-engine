import uuid
from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app
from app.state import state

client = TestClient(app)


def test_push_context_success():
    # Push brand new merchant version
    payload = {
        "scope": "merchant",
        "context_id": "m_test_push_001",
        "version": 1,
        "delivered_at": "2026-04-26T10:00:00Z",
        "payload": {
            "merchant_id": "m_test_push_001",
            "category_slug": "salons",
            "identity": {"name": "Test Salon"},
        },
    }

    res = client.post("/v1/context", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["accepted"] is True
    assert "ack_id" in data
    # Verify ack_id is a valid UUID
    parsed_uuid = uuid.UUID(data["ack_id"])
    assert str(parsed_uuid) == data["ack_id"]

    # Verify stored_at is valid UTC ISO string ending in Z
    assert data["stored_at"].endswith("Z")
    datetime.fromisoformat(data["stored_at"].replace("Z", "+00:00"))

    # Verify state has the payload
    stored = state.get_merchant("m_test_push_001")
    assert stored is not None
    assert stored["identity"]["name"] == "Test Salon"


def test_push_context_idempotency_and_versioning():
    # 1. Same version re-pushed -> 200 accepted
    payload_v1 = {
        "scope": "merchant",
        "context_id": "m_test_push_001",
        "version": 1,
        "delivered_at": "2026-04-26T10:05:00Z",
        "payload": {"name": "Test Salon v1"},
    }
    res_same = client.post("/v1/context", json=payload_v1)
    assert res_same.status_code == 200
    assert res_same.json()["accepted"] is True

    # 2. Higher version -> 200 accepted & replaces
    payload_v2 = {
        "scope": "merchant",
        "context_id": "m_test_push_001",
        "version": 2,
        "delivered_at": "2026-04-26T10:10:00Z",
        "payload": {"name": "Test Salon v2"},
    }
    res_v2 = client.post("/v1/context", json=payload_v2)
    assert res_v2.status_code == 200
    assert res_v2.json()["accepted"] is True
    assert state.get_merchant("m_test_push_001")["name"] == "Test Salon v2"

    # 3. Lower version -> 409 Conflict stale_version
    payload_stale = {
        "scope": "merchant",
        "context_id": "m_test_push_001",
        "version": 1,
        "delivered_at": "2026-04-26T10:15:00Z",
        "payload": {"name": "Test Salon v1 again"},
    }
    res_stale = client.post("/v1/context", json=payload_stale)
    assert res_stale.status_code == 409
    data_stale = res_stale.json()
    assert data_stale["accepted"] is False
    assert data_stale["reason"] == "stale_version"
    assert data_stale["current_version"] == 2


def test_push_context_invalid_scope():
    payload = {
        "scope": "invalid_scope",
        "context_id": "xyz",
        "version": 1,
        "delivered_at": "2026-04-26T10:00:00Z",
        "payload": {},
    }
    res = client.post("/v1/context", json=payload)
    assert res.status_code == 400
    data = res.json()
    assert data["accepted"] is False
    assert data["reason"] == "invalid_scope"


if __name__ == "__main__":
    test_push_context_success()
    test_push_context_idempotency_and_versioning()
    test_push_context_invalid_scope()
    print("All context endpoint tests passed successfully!")
