from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("vera.state")

START_TIME = time.time()


class VeraState:
    """
    Thread-safe in-memory state store for vera-bot.
    Manages contexts across the 4-context framework, conversation histories,
    and trigger suppression keys with TTL support.
    """

    def __init__(self, auto_load_expanded: bool = True):
        self._lock = threading.Lock()
        self._start_time = time.time()

        # (scope, context_id) -> {"version": int, "payload": dict[str, Any]}
        self._contexts: Dict[Tuple[str, str], Dict[str, Any]] = {}

        # Secondary lookup maps for convenience and resilient ID resolution:
        # e.g., "m_001" -> "m_001_drmeera_dentist_delhi"
        self._merchant_aliases: Dict[str, str] = {}
        self._customer_aliases: Dict[str, str] = {}
        self._trigger_aliases: Dict[str, str] = {}

        # conversation_id -> list of turn dicts
        self._conversations: Dict[str, List[Dict[str, Any]]] = {}

        # suppression_key -> expire_timestamp_epoch_float
        self._suppressions: Dict[str, float] = {}

        # O(1) context count cache for instant zero-overhead healthz probes
        self._context_counts: Dict[str, int] = {
            "category": 0,
            "merchant": 0,
            "customer": 0,
            "trigger": 0,
        }

        if auto_load_expanded:
            self.load_expanded_dataset()

    # -------------------------------------------------------------------------
    # Context Upsert & Retrieval
    # -------------------------------------------------------------------------

    def upsert_context(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: Dict[str, Any],
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Upsert a context document thread-safely:
        - Higher version replaces previous version atomically.
        - Identical version is accepted idempotently (no-op).
        - Lower (stale) version is rejected.

        Returns:
            (accepted: bool, reason: str, current_version: Optional[int])
        """
        with self._lock:
            key = (scope, context_id)
            current = self._contexts.get(key)

            if current is not None:
                curr_version = current["version"]
                if version < curr_version:
                    return False, "stale_version", curr_version
                elif version == curr_version:
                    # Idempotent re-post
                    return True, "identical_version", curr_version

            # Track scope count if newly added
            if current is None:
                self._context_counts[scope] = self._context_counts.get(scope, 0) + 1

            # Insert or atomic overwrite
            self._contexts[key] = {
                "version": version,
                "payload": payload,
            }
            self._register_alias(scope, context_id)

            return True, "stored", version

    def _register_alias(self, scope: str, context_id: str) -> None:
        """Register prefix/short ID aliases (e.g. m_001 -> m_001_drmeera...)."""
        prefix = context_id.split("_")[0] + "_" + context_id.split("_")[1] if "_" in context_id else context_id
        if scope == "merchant":
            self._merchant_aliases[context_id] = context_id
            self._merchant_aliases[prefix] = context_id
        elif scope == "customer":
            self._customer_aliases[context_id] = context_id
            self._customer_aliases[prefix] = context_id
        elif scope == "trigger":
            self._trigger_aliases[context_id] = context_id
            self._trigger_aliases[prefix] = context_id

    def get_context(self, scope: str, context_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve raw context payload by scope and context_id."""
        with self._lock:
            entry = self._contexts.get((scope, context_id))
            if entry:
                return entry.get("payload")

            # Try alias resolution
            resolved_id = None
            if scope == "merchant":
                resolved_id = self._merchant_aliases.get(context_id)
            elif scope == "customer":
                resolved_id = self._customer_aliases.get(context_id)
            elif scope == "trigger":
                resolved_id = self._trigger_aliases.get(context_id)

            if resolved_id and resolved_id != context_id:
                entry = self._contexts.get((scope, resolved_id))
                if entry:
                    return entry.get("payload")

            return None

    def get_merchant(self, merchant_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve MerchantContext payload by merchant_id or alias."""
        return self.get_context("merchant", merchant_id)

    def get_customer(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve CustomerContext payload by customer_id or alias."""
        return self.get_context("customer", customer_id)

    def get_category(self, category_slug: str) -> Optional[Dict[str, Any]]:
        """Retrieve CategoryContext payload by category_slug."""
        return self.get_context("category", category_slug)

    def get_trigger(self, trigger_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve TriggerContext payload by trigger_id or alias."""
        return self.get_context("trigger", trigger_id)

    # -------------------------------------------------------------------------
    # Suppression Management
    # -------------------------------------------------------------------------

    def mark_suppressed(self, key: str, ttl: float = 86400.0) -> None:
        """Mark a suppression key with an expiration TTL (seconds)."""
        if not key:
            return
        with self._lock:
            self._suppressions[key] = time.time() + max(0.0, ttl)

    def is_suppressed(self, key: str) -> bool:
        """Check if a suppression key is currently active and not expired."""
        if not key:
            return False
        with self._lock:
            expire_at = self._suppressions.get(key)
            if expire_at is None:
                return False
            now = time.time()
            if now > expire_at:
                del self._suppressions[key]
                return False
            return True

    # -------------------------------------------------------------------------
    # Conversation History
    # -------------------------------------------------------------------------

    def append_conversation_turn(self, conversation_id: str, turn: Dict[str, Any]) -> None:
        """Append a message turn to a conversation thread thread-safely."""
        with self._lock:
            self._conversations.setdefault(conversation_id, []).append(turn)

    def get_conversation(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get a copy of all turns for a given conversation thread."""
        with self._lock:
            return list(self._conversations.get(conversation_id, []))

    # -------------------------------------------------------------------------
    # Metrics & Reset
    # -------------------------------------------------------------------------

    def get_context_counts(self) -> Dict[str, int]:
        """Return counts of loaded contexts per scope in O(1) time without disk/DB overhead."""
        with self._lock:
            return dict(self._context_counts)

    def get_uptime_seconds(self) -> int:
        """Return uptime in seconds since instantiation."""
        return int(time.time() - self._start_time)

    def reset_state(self) -> None:
        """Clear all in-memory contexts, conversations, and suppressions."""
        with self._lock:
            self._contexts.clear()
            self._merchant_aliases.clear()
            self._customer_aliases.clear()
            self._trigger_aliases.clear()
            self._conversations.clear()
            self._suppressions.clear()
            self._context_counts = {
                "category": 0,
                "merchant": 0,
                "customer": 0,
                "trigger": 0,
            }

    # -------------------------------------------------------------------------
    # Dataset Loading on Startup
    # -------------------------------------------------------------------------

    def load_expanded_dataset(self, base_dir: Optional[Path | str] = None) -> int:
        """
        Load all JSON files from expanded/ directory on startup into the state store.
        Scans categories/, merchants/, customers/, and triggers/.
        """
        if base_dir is None:
            # Default to expanded/ at repo root
            root = Path(__file__).resolve().parent.parent
            candidate_dirs = [root / "expanded", root / "dataset"]
        else:
            candidate_dirs = [Path(base_dir).resolve()]

        expanded_dir: Optional[Path] = None
        for cand in candidate_dirs:
            if cand.exists() and cand.is_dir():
                expanded_dir = cand
                break

        if not expanded_dir:
            logger.warning("No expanded or dataset directory found for initial load.")
            return 0

        loaded_count = 0
        scope_mappings = [
            ("categories", "category", "slug"),
            ("merchants", "merchant", "merchant_id"),
            ("customers", "customer", "customer_id"),
            ("triggers", "trigger", "id"),
        ]

        for folder_name, scope, id_key in scope_mappings:
            folder_path = expanded_dir / folder_name
            if not folder_path.exists():
                continue

            for json_file in folder_path.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    context_id = data.get(id_key) or json_file.stem
                    self.upsert_context(
                        scope=scope,
                        context_id=context_id,
                        version=1,
                        payload=data,
                    )
                    loaded_count += 1
                except Exception as exc:
                    logger.error("Failed to load %s: %s", json_file, exc)

        logger.info("Loaded %d contexts from %s", loaded_count, expanded_dir)
        return loaded_count


# Global singleton state instance loaded on module import
state = VeraState(auto_load_expanded=True)

# Compatibility exports
contexts = state._contexts
conversations = state._conversations


def get_uptime_seconds() -> int:
    return state.get_uptime_seconds()


def get_context_counts() -> Dict[str, int]:
    return state.get_context_counts()


def reset_state() -> None:
    state.reset_state()
