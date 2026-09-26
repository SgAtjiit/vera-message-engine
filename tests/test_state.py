import threading
import time
from app.state import VeraState


def test_vera_state():
    # 1. Test basic init and expanded dataset loading
    state = VeraState(auto_load_expanded=True)
    counts = state.get_context_counts()
    print("Counts on startup:", counts)
    assert counts["category"] == 5
    assert counts["merchant"] == 50
    assert counts["customer"] == 200
    assert counts["trigger"] == 100

    # 2. Test get_merchant, get_customer, get_category, get_trigger
    m = state.get_merchant("m_001_drmeera_dentist_delhi")
    assert m is not None
    assert m["identity"]["name"] == "Dr. Meera's Dental Clinic"

    m_short = state.get_merchant("m_001")
    assert m_short is not None
    assert m_short["identity"]["name"] == "Dr. Meera's Dental Clinic"

    cat = state.get_category("dentists")
    assert cat is not None and cat["slug"] == "dentists"

    cust = state.get_customer("c_001_priya_for_m001")
    assert cust is not None and cust["identity"]["name"] == "Priya"

    trg = state.get_trigger("trg_001_research_digest_dentists")
    assert trg is not None and trg["kind"] == "research_digest"

    # 3. Test upsert_context idempotency and version control
    # Lower version rejected
    ok, reason, ver = state.upsert_context("category", "dentists", 0, {"slug": "dentists", "v": 0})
    assert not ok and reason == "stale_version" and ver == 1

    # Identical version idempotent
    ok, reason, ver = state.upsert_context("category", "dentists", 1, {"slug": "dentists", "v": 1})
    assert ok and reason == "identical_version" and ver == 1

    # Higher version replaces
    ok, reason, ver = state.upsert_context("category", "dentists", 2, {"slug": "dentists", "v": 2})
    assert ok and reason == "stored" and ver == 2
    assert state.get_category("dentists")["v"] == 2

    # 4. Test suppression and TTL
    state.mark_suppressed("test_key_1", ttl=0.2)
    assert state.is_suppressed("test_key_1") is True
    time.sleep(0.25)
    assert state.is_suppressed("test_key_1") is False

    # 5. Test conversation turns
    state.append_conversation_turn("conv_test", {"from": "merchant", "msg": "hello"})
    state.append_conversation_turn("conv_test", {"from": "bot", "msg": "hi there"})
    turns = state.get_conversation("conv_test")
    assert len(turns) == 2
    assert turns[0]["msg"] == "hello"

    # 6. Test concurrent multi-threaded access
    errors = []

    def worker(w_id):
        try:
            for i in range(50):
                state.upsert_context("merchant", f"m_thread_{w_id}", i, {"count": i})
                state.mark_suppressed(f"key_{w_id}_{i}", ttl=1.0)
                _ = state.is_suppressed(f"key_{w_id}_{i}")
                state.append_conversation_turn(f"conv_{w_id}", {"turn": i})
                _ = state.get_conversation(f"conv_{w_id}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Thread errors: {errors}"
    print("All VeraState tests passed!")


if __name__ == "__main__":
    test_vera_state()
