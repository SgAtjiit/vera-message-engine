from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from app.models import TickRequest, TickResponse, TickAction
from app.state import state
from app.composer import compose

router = APIRouter()

MAX_TICK_ACTIONS = 20


KIND_PRIORITY: Dict[str, float] = {
    # Tier 1: Immediate Safety Hazard / Inbound Merchant Direct Inquiry
    "supply_alert": 100.0,              # Product recall / batch quarantine
    "active_planning_intent": 95.0,     # Merchant explicitly inquired in conversation
    "regulation_change": 90.0,          # Statutory deadline / compliance cutoffs

    # Tier 2: Real-time Live Event / Time-Bound Window / Conversion Window
    "ipl_match_today": 85.0,            # Live event today (kickoff in hours)
    "appointment_tomorrow": 82.0,       # 24h pre-appointment confirmation
    "chronic_refill_due": 80.0,         # Prescription stock exhaustion cutoff
    "renewal_due": 78.0,                # Paid subscription expiry countdown
    "competitor_opened": 75.0,          # Nearby competitor poaching market share

    # Tier 3: Transactional Customer Conversions & Followups
    "recall_due": 72.0,                 # Preventive clinical recall with open slots
    "trial_followup": 70.0,             # Post-trial conversion to membership/service
    "wedding_package_followup": 68.0,   # 30-day prep window milestone
    "customer_lapsed_hard": 65.0,       # High-risk lapsed customer (>60-90d)
    "customer_lapsed_soft": 62.0,       # Soft lapsed customer (30-60d)

    # Tier 4: Operational & Performance Swings
    "perf_dip": 60.0,                   # Severe drop in calls/views vs baseline
    "perf_spike": 58.0,                 # Momentum surge to capitalize on
    "review_theme_emerged": 55.0,       # Emerging negative or positive review theme
    "winback_eligible": 52.0,           # Paused campaign winback opportunity

    # Tier 5: Knowledge & Industry Insights
    "research_digest": 48.0,            # Clinical/industry research digest
    "cde_opportunity": 45.0,            # Continuing education / webinars

    # Tier 6: Ambient, Seasonal & Optimization Trends
    "seasonal_perf_dip": 40.0,          # Expected cyclical seasonal lull
    "milestone_reached": 38.0,          # Approaching review / rating milestone
    "category_seasonal": 35.0,          # General seasonal shift
    "gbp_unverified": 32.0,             # Unverified GBP uplift opportunity
    "dormant_with_vera": 30.0,          # Inactive merchant re-engagement
    "festival_upcoming": 28.0,          # Festival approaching (weeks away)
    "curious_ask_due": 25.0,            # Weekly open inquiry
}


def calculate_trigger_priority(trigger: Dict[str, Any], merchant: Dict[str, Any]) -> float:
    """
    Calculate composite priority score (0-150+) based on:
    1. KIND_PRIORITY tier weight (all 26 trigger kinds mapped).
    2. Trigger urgency (scaled * 20.0).
    3. Contextual boosts for real-time events and merchant conversation signals.
    """
    kind = trigger.get("kind", "")
    urgency = float(trigger.get("urgency", 1))
    base_weight = KIND_PRIORITY.get(kind, 30.0)

    boost = 0.0
    signals = merchant.get("signals", [])
    if isinstance(signals, list):
        if any("engaged" in str(s) for s in signals) and kind == "active_planning_intent":
            boost += 30.0
        if any("renewal" in str(s) for s in signals) and kind == "renewal_due":
            boost += 25.0
        if any("perf_dip" in str(s) for s in signals) and kind in ("perf_dip", "seasonal_perf_dip"):
            boost += 20.0
        if any("winback" in str(s) for s in signals) and kind == "winback_eligible":
            boost += 20.0

    if kind == "ipl_match_today":
        boost += 20.0
    if kind == "appointment_tomorrow":
        boost += 15.0

    return (urgency * 20.0) + base_weight + boost


@router.post("/v1/tick", response_model=TickResponse)
async def tick(body: TickRequest):
    """
    Handle simulation tick event:
    1. Inspect available_triggers hint.
    2. Filter out suppressed or invalid triggers.
    3. Select best trigger per merchant (ranked by calculate_trigger_priority).
    4. Sort candidates by priority descending and cap at 20 actions.
    5. Call composer.compose on truncated candidates (fast, non-blocking).
    6. Mark returned suppression keys as active in state.
    """
    if not body.available_triggers:
        return TickResponse(actions=[])

    # 1. Gather valid, non-suppressed triggers grouped by merchant
    merchant_candidates: Dict[str, Dict[str, Any]] = {}

    for trg_id in body.available_triggers:
        trg = state.get_trigger(trg_id)
        if not trg:
            continue

        suppression_key = trg.get("suppression_key", "")
        if suppression_key and state.is_suppressed(suppression_key):
            continue

        merchant_id = trg.get("merchant_id")
        if not merchant_id:
            continue

        merchant = state.get_merchant(merchant_id)
        if not merchant:
            continue

        category_slug = merchant.get("category_slug")
        category = state.get_category(category_slug) if category_slug else None
        if not category:
            continue

        customer_id = trg.get("customer_id")
        customer = state.get_customer(customer_id) if customer_id else None

        urgency = int(trg.get("urgency", 1))
        priority = calculate_trigger_priority(trg, merchant)

        candidate = {
            "trg_id": trg_id,
            "trigger": trg,
            "merchant_id": merchant_id,
            "merchant": merchant,
            "category": category,
            "customer_id": customer_id,
            "customer": customer,
            "urgency": urgency,
            "priority": priority,
        }

        # Keep highest priority trigger per merchant
        existing = merchant_candidates.get(merchant_id)
        if existing is None or priority > existing["priority"]:
            merchant_candidates[merchant_id] = candidate

    if not merchant_candidates:
        return TickResponse(actions=[])

    # 2. Sort candidates by priority descending and truncate to MAX_TICK_ACTIONS
    sorted_candidates = sorted(
        merchant_candidates.values(),
        key=lambda c: c["priority"],
        reverse=True,
    )[:MAX_TICK_ACTIONS]

    # 3. Fast composition for truncated candidates
    actions: List[TickAction] = []

    for item in sorted_candidates:
        trg = item["trigger"]
        merchant = item["merchant"]
        category = item["category"]
        customer = item["customer"]
        merchant_id = item["merchant_id"]
        customer_id = item["customer_id"]
        trg_id = trg.get("id") or item["trg_id"]

        # Call composer
        composed = compose(
            category=category,
            merchant=merchant,
            trigger=trg,
            customer=customer,
        )

        body_text = composed.get("body", "").strip()
        if not body_text:
            continue

        # Suppression management
        supp_key = composed.get("suppression_key") or trg.get("suppression_key", "")
        if supp_key:
            state.mark_suppressed(supp_key)

        default_send_as = "merchant_on_behalf" if (customer or trg.get("scope") == "customer") else "vera"
        send_as = composed.get("send_as") or default_send_as
        conv_id = f"conv_{merchant_id}_{trg_id}"

        # Record proactive initial turn in state
        state.append_conversation_turn(conv_id, {
            "from_role": "bot",
            "message": body_text,
            "send_as": send_as,
            "turn_number": 1,
            "trigger_id": trg_id,
        })

        actions.append(
            TickAction(
                conversation_id=conv_id,
                merchant_id=merchant_id,
                customer_id=customer_id,
                send_as=send_as,
                trigger_id=trg_id,
                template_name=composed.get("template_name", f"vera_{trg.get('kind', 'generic')}_v1"),
                template_params=composed.get("template_params", [merchant.get("identity", {}).get("name", "")]),
                body=body_text,
                cta=composed.get("cta", "open_ended"),
                suppression_key=supp_key,
                rationale=composed.get("rationale", f"Proactive message triggered by {trg.get('kind', 'event')}"),
            )
        )

    return TickResponse(actions=actions)
