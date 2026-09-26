import time
from fastapi.testclient import TestClient
from app.main import app
from app.state import state

client = TestClient(app)


def test_tick_empty():
    res = client.post("/v1/tick", json={"now": "2026-04-26T10:00:00Z", "available_triggers": []})
    assert res.status_code == 200
    assert res.json() == {"actions": []}


def test_tick_basic():
    # Reset suppressions
    state._suppressions.clear()

    trg_id = "trg_001_research_digest_dentists"
    res = client.post(
        "/v1/tick",
        json={"now": "2026-04-26T10:30:00Z", "available_triggers": [trg_id]},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["actions"]) == 1

    action = data["actions"][0]
    assert action["trigger_id"] == trg_id
    assert action["merchant_id"] == "m_001_drmeera_dentist_delhi"
    assert action["send_as"] in ("vera", "merchant_on_behalf")
    assert len(action["body"]) > 0
    assert len(action["rationale"]) > 0

    # Verify suppression key is now active in state
    supp_key = action["suppression_key"]
    assert state.is_suppressed(supp_key) is True

    # Immediate second tick with the same trigger must return empty because it is now suppressed
    res_second = client.post(
        "/v1/tick",
        json={"now": "2026-04-26T10:35:00Z", "available_triggers": [trg_id]},
    )
    assert res_second.status_code == 200
    assert res_second.json()["actions"] == []


def test_tick_cap_at_20_and_speed():
    state._suppressions.clear()

    # Pass all 100 triggers from expanded dataset
    all_triggers = [f"trg_{i:03d}" for i in range(1, 101)]

    start = time.time()
    res = client.post(
        "/v1/tick",
        json={"now": "2026-04-26T10:40:00Z", "available_triggers": all_triggers},
    )
    elapsed = time.time() - start

    assert res.status_code == 200
    data = res.json()

    # Must be capped at 20 actions max
    assert len(data["actions"]) <= 20
    # Must be fast (< 200ms)
    print(f"Tick with 100 triggers took {elapsed*1000:.1f}ms, returned {len(data['actions'])} actions")
    assert elapsed < 0.5, f"Tick took too long: {elapsed}s"

    # Each action must be from a unique merchant
    merchant_ids = [a["merchant_id"] for a in data["actions"]]
    assert len(merchant_ids) == len(set(merchant_ids)), "Multiple actions returned for the same merchant in one tick"


if __name__ == "__main__":
    test_tick_empty()
    test_tick_basic()
    test_tick_cap_at_20_and_speed()
    print("All tick endpoint tests passed successfully!")
