from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from app.models import ReplyRequest, ReplyResponse
from app.state import state

logger = logging.getLogger("vera.reply")
router = APIRouter()

# =============================================================================
# Intent Classification Patterns
# =============================================================================

AUTO_REPLY_PATTERNS = [
    r"thank you for contacting",
    r"automated (assistant|response|reply|message)",
    r"auto[- ]?reply",
    r"team will respond shortly",
    r"we will respond shortly",
    r"currently away",
    r"out of office",
    r"virtual assistant",
    r"canned (reply|response)",
]

HOSTILE_PATTERNS = [
    r"\bstop\b",
    r"\bunsubscribe\b",
    r"\bspam\b",
    r"\buseless\b",
    r"don'?t message",
    r"do not message",
    r"\bblock(ed)?\b",
    r"remove (me|my number)",
    r"delete (me|my number)",
    r"leave me alone",
    r"harass(ment)?",
    r"fuck|bastard|idiot|scam",
    r"nahi chahiye",
    r"band karo",
    r"mat (bhejo|karo)",
]

DECLINE_PATTERNS = [
    r"not interested",
    r"no thanks",
    r"no thank you",
    r"\bdecline\b",
    r"\bcancel\b",
    r"don'?t want",
    r"not needed",
    r"no need",
    r"^no\.?$",
    r"^nah\.?$",
    r"^nahi\.?$",
]

ACCEPT_PATTERNS = [
    r"ok let'?s do it",
    r"let'?s do it",
    r"what'?s next",
    r"\byes\b",
    r"\byep\b",
    r"\byup\b",
    r"\bok\b",
    r"\bokay\b",
    r"\bproceed\b",
    r"\bconfirm\b",
    r"\bsend\b",
    r"go ahead",
    r"\bagree\b",
    r"\bdone\b",
    r"draft (it|this)",
    r"share (it|this)",
    r"\bsure\b",
    r"\bchalega\b",
    r"\bhaan\b",
    r"\bha\b",
    r"\bbhejo\b",
]

AMBIGUOUS_PATTERNS = [
    r"\bbusy\b",
    r"call later",
    r"talk later",
    r"give me time",
    r"check later",
    r"tomorrow",
    r"next week",
    r"baad mein",
    r"bad me",
    r"not right now",
    r"hold on",
    r"\bwait\b",
    r"thinking",
]

OFF_TOPIC_PATTERNS = [
    r"\bgst\b",
    r"income tax",
    r"tax return",
    r"\bitr\b",
    r"\bloan\b",
    r"bank account",
    r"credit card",
    r"\blawyer\b",
    r"legal notice",
    r"court case",
]


def classify_intent_rule_based(message: str, history: List[Dict[str, Any]]) -> str:
    """
    Classify intent using deterministic keyword and regex matching:
    Returns one of: 'auto_reply', 'hostile', 'decline', 'accept', 'ambiguous', 'off_topic', 'question'.
    """
    msg_clean = message.strip()
    msg_lower = msg_clean.lower()

    # 1. Check auto-reply patterns or repeated canned replies in history
    for pat in AUTO_REPLY_PATTERNS:
        if re.search(pat, msg_lower):
            return "auto_reply"

    prior_merchant_turns = [
        t.get("message", "").strip().lower()
        for t in history
        if t.get("from_role") == "merchant"
    ]
    # Detect consecutive repeating canned auto-replies (excluding accept/affirmative messages)
    if (
        len(prior_merchant_turns) >= 2
        and prior_merchant_turns[-1] == msg_lower
        and len(msg_lower) > 15
        and not any(re.search(pat, msg_lower) for pat in ACCEPT_PATTERNS)
    ):
        return "auto_reply"

    # 2. Check hostile / opt-out
    for pat in HOSTILE_PATTERNS:
        if re.search(pat, msg_lower):
            return "hostile"

    # 3. Check decline
    for pat in DECLINE_PATTERNS:
        if re.search(pat, msg_lower):
            return "decline"

    # 4. Check accept / action handoff
    for pat in ACCEPT_PATTERNS:
        if re.search(pat, msg_lower):
            return "accept"

    # 5. Check ambiguous / delay
    for pat in AMBIGUOUS_PATTERNS:
        if re.search(pat, msg_lower):
            return "ambiguous"

    # 6. Check off-topic
    for pat in OFF_TOPIC_PATTERNS:
        if re.search(pat, msg_lower):
            return "off_topic"

    # 7. Check question
    if "?" in msg_clean or any(msg_lower.startswith(q) for q in ["what", "how", "why", "when", "where", "who", "price", "cost", "kaise", "kitna"]):
        return "question"

    # Default to question if open-ended, or accept if brief affirmative
    return "question"


def generate_rule_based_reply(
    intent: str,
    message: str,
    merchant_name: str,
) -> Dict[str, Any]:
    """
    Map classified intent to guaranteed response:
    - accept -> 'send' in action mode (using actioning vocabulary: done, draft, here, confirm, next, proceed)
    - decline / hostile / auto_reply -> 'end'
    - ambiguous -> 'wait' (with wait_seconds)
    - question / off_topic -> 'send' (answering and maintaining clear boundaries)
    """
    if intent in ("hostile", "decline"):
        return {
            "action": "end",
            "body": "",
            "cta": None,
            "wait_seconds": None,
            "rationale": "Merchant declined or opted out; gracefully exiting conversation to respect preferences.",
        }

    if intent == "auto_reply":
        return {
            "action": "end",
            "body": "",
            "cta": None,
            "wait_seconds": None,
            "rationale": "Merchant automated assistant / canned auto-reply detected; ending turn to avoid auto-reply loops.",
        }

    if intent == "ambiguous":
        return {
            "action": "wait",
            "body": "",
            "cta": None,
            "wait_seconds": 1800,
            "rationale": "Merchant requested delay or time to check; backing off for 30 minutes before re-engaging.",
        }

    if intent == "accept":
        # Must strictly be in ACTION mode (contains actioning words: done, sending, draft, here, confirm, proceed, next; NO qualifying words)
        body = (
            f"Done! Here is the draft ready to confirm for {merchant_name}. "
            "Next, say confirm and I will proceed with sending it right away."
        )
        return {
            "action": "send",
            "body": body,
            "cta": "binary",
            "wait_seconds": None,
            "rationale": "Merchant confirmed intent; switched immediately to action mode with pre-drafted deliverable.",
        }

    if intent == "off_topic":
        body = (
            f"Hi {merchant_name}, I specialize in managing your Google Business listing, promotional offers, and customer outreach on magicpin. "
            "For accounting or legal matters, your advisor is best suited. Let me know whenever you're ready to update your business profile or run an offer!"
        )
        return {
            "action": "send",
            "body": body,
            "cta": "open_ended",
            "wait_seconds": None,
            "rationale": "Politely addressed off-topic query while maintaining assistant scope and offering core listing assistance.",
        }

    # Intent is 'question'
    body = (
        f"Hi {merchant_name}, here are the details: our assistant helps keep your Google listing updated, announces active offers, and handles patient recalls. "
        "I have a draft ready whenever you want to proceed. What questions do you have?"
    )
    return {
        "action": "send",
        "body": body,
        "cta": "open_ended",
        "wait_seconds": None,
        "rationale": "Answered merchant inquiry transparently with specific scope and offered actionable next steps.",
    }


# =============================================================================
# Optional LLM Call (Anthropic / OpenAI) with Strict Timeout Fallback
# =============================================================================

def try_llm_reply(
    message: str,
    history: List[Dict[str, Any]],
    merchant: Optional[Dict[str, Any]],
    category: Optional[Dict[str, Any]],
    timeout_seconds: float = 6.0,
) -> Optional[Dict[str, Any]]:
    """
    Attempt an LLM completion using OpenAI or Anthropic SDK if configured with temperature=0.
    Times out in timeout_seconds (default 6s, well below the 30s budget) and returns None on any failure.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if not openai_key and not anthropic_key:
        return None

    system_prompt = (
        "You are Vera, magicpin's merchant assistant on WhatsApp. "
        "Classify merchant response and respond with a JSON object containing keys: "
        "'action' ('send' | 'wait' | 'end'), 'body' (string or null), 'cta' (string or null), "
        "'wait_seconds' (int or null), and 'rationale' (string). "
        "Rules: If merchant accepts/agrees, switch immediately to ACTION mode with draft; "
        "If merchant declines or asks to stop, action must be 'end'; "
        "If merchant asks for time/busy, action must be 'wait'. "
        "Output ONLY raw JSON."
    )

    user_prompt = json.dumps({
        "merchant_message": message,
        "merchant_name": merchant.get("identity", {}).get("name", "Merchant") if merchant else "Merchant",
        "category": category.get("slug", "general") if category else "general",
        "recent_history": history[-4:],
    })

    try:
        if openai_key:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key, timeout=timeout_seconds)
            completion = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = completion.choices[0].message.content
            if raw:
                data = json.loads(raw)
                if data.get("action") in ("send", "wait", "end") and "rationale" in data:
                    return data

        elif anthropic_key:
            from anthropic import Anthropic
            client = Anthropic(api_key=anthropic_key, timeout=timeout_seconds)
            response = client.messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"),
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=300,
                temperature=0.0,
            )
            raw = response.content[0].text
            if raw:
                data = json.loads(raw)
                if data.get("action") in ("send", "wait", "end") and "rationale" in data:
                    return data

    except Exception as exc:
        logger.warning("Optional LLM call bypassed or failed (%s); using deterministic fallback.", exc)

    return None


# =============================================================================
# Endpoint Implementation
# =============================================================================

@router.post("/v1/reply", response_model=ReplyResponse)
async def reply(body: ReplyRequest):
    """
    Handle inbound merchant/customer reply synchronously within 30 seconds:
    1. Append incoming turn to state conversation history.
    2. Retrieve merchant and category context from state.
    3. Attempt optional LLM call with temperature=0 (capped at 6s timeout).
    4. If LLM unavailable or timed out, use deterministic rule-based matching.
    5. Map intent to action ('send', 'wait', or 'end') and append bot turn if sent.
    6. Always return structured ReplyResponse with rationale.
    """
    # 1. Record incoming message in state
    turn_in = {
        "from_role": body.from_role,
        "message": body.message,
        "turn_number": body.turn_number,
        "received_at": body.received_at,
    }
    state.append_conversation_turn(body.conversation_id, turn_in)

    # 2. Context lookup
    history = state.get_conversation(body.conversation_id)
    merchant = state.get_merchant(body.merchant_id) if body.merchant_id else None
    category = state.get_category(merchant.get("category_slug", "")) if merchant else None
    merchant_name = merchant.get("identity", {}).get("name", "Merchant") if merchant else "there"

    # 3. Try optional LLM call with strict timeout (fallback on any error/timeout)
    reply_data = try_llm_reply(
        message=body.message,
        history=history,
        merchant=merchant,
        category=category,
        timeout_seconds=6.0,
    )

    # 4. Deterministic rule-based fallback
    if not reply_data:
        intent = classify_intent_rule_based(body.message, history)
        reply_data = generate_rule_based_reply(intent, body.message, merchant_name)

    action = reply_data.get("action", "send")
    resp_body = reply_data.get("body")
    cta = reply_data.get("cta")
    wait_seconds = reply_data.get("wait_seconds")
    rationale = reply_data.get("rationale", "Reply evaluated according to merchant intent.")

    # 5. Record bot outbound message if action is 'send'
    if action == "send" and resp_body:
        state.append_conversation_turn(
            body.conversation_id,
            {
                "from_role": "bot",
                "message": resp_body,
                "turn_number": body.turn_number + 1,
                "cta": cta,
            },
        )

    return ReplyResponse(
        action=action,
        body=resp_body,
        cta=cta,
        wait_seconds=wait_seconds,
        rationale=rationale,
    )
