import time
from fastapi.testclient import TestClient
from app.main import app
from app.state import state

client = TestClient(app)


def test_reply_auto_reply():
    conv_id = "conv_test_auto_reply"
    res = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "from_role": "merchant",
            "message": "Thank you for contacting us! Our team will respond shortly.",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "end"
    assert "auto-reply" in data["rationale"].lower() or "automated" in data["rationale"].lower()


def test_reply_intent_transition_action_mode():
    conv_id = "conv_test_intent_switch"
    res = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "from_role": "merchant",
            "message": "Ok lets do it. Whats next?",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "send"
    assert data["body"] is not None

    body_lower = data["body"].lower()
    actioning = ["done", "sending", "draft", "here", "confirm", "proceed", "next"]
    qualifying = ["would you", "do you", "can you tell", "what if", "how about"]

    assert any(w in body_lower for w in actioning), f"Expected actioning words in: {data['body']}"
    assert not any(w in body_lower for w in qualifying), f"Found qualifying words in: {data['body']}"


def test_reply_hostile():
    conv_id = "conv_test_hostile"
    res = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "from_role": "merchant",
            "message": "Stop messaging me. This is useless spam.",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "end"


def test_reply_decline():
    conv_id = "conv_test_decline"
    res = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "from_role": "merchant",
            "message": "Not interested at all, please cancel.",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "end"


def test_reply_ambiguous():
    conv_id = "conv_test_ambiguous"
    res = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "from_role": "merchant",
            "message": "I am very busy right now, check with me tomorrow.",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "wait"
    assert data["wait_seconds"] == 1800


def test_reply_off_topic():
    conv_id = "conv_test_off_topic"
    res = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "from_role": "merchant",
            "message": "Can your team help file my GST returns?",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "send"
    assert "gst" in data["body"].lower() or "advisor" in data["body"].lower() or "google" in data["body"].lower()


def test_reply_state_recording_and_speed():
    conv_id = "conv_test_state_record"
    start = time.time()
    res = client.post(
        "/v1/reply",
        json={
            "conversation_id": conv_id,
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "from_role": "merchant",
            "message": "What is included in the package?",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        },
    )
    elapsed = time.time() - start
    assert res.status_code == 200
    assert elapsed < 0.5, f"Response too slow: {elapsed}s (budget is 30s)"

    # Check turns in state
    turns = state.get_conversation(conv_id)
    assert len(turns) == 2  # 1 merchant in, 1 bot out
    assert turns[0]["from_role"] == "merchant"
    assert turns[1]["from_role"] == "bot"


if __name__ == "__main__":
    test_reply_auto_reply()
    test_reply_intent_transition_action_mode()
    test_reply_hostile()
    test_reply_decline()
    test_reply_ambiguous()
    test_reply_off_topic()
    test_reply_state_recording_and_speed()
    print("All reply endpoint tests passed successfully!")
