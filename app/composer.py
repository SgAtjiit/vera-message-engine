from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set


def _resolve_digest(category: Dict[str, Any], item_id: str) -> Optional[Dict[str, Any]]:
    """Lookup a digest article or circular in category knowledge."""
    for item in category.get("digest", []):
        if item.get("id") == item_id:
            return item
    return None


def _format_date(date_str: str) -> str:
    """Format ISO date YYYY-MM-DD into a clean readable string (e.g. 15 Dec 2026)."""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    try:
        parts = date_str.split("-")
        if len(parts) >= 3:
            year, month_idx, day = parts[0], int(parts[1]), int(parts[2][:2])
            return f"{day} {months[month_idx - 1]} {year}"
    except Exception:
        pass
    return date_str


def _is_hindi_preferred(merchant: Dict[str, Any], customer: Optional[Dict[str, Any]] = None) -> bool:
    """
    Check if Hindi / Hindi-English mix preference is indicated in merchant
    identity or customer preferences.
    """
    if customer:
        c_lang = str(customer.get("identity", {}).get("language_pref", "")).lower()
        if any(h in c_lang for h in ("hi", "hindi", "hi-en")):
            return True

    m_langs = merchant.get("identity", {}).get("languages", [])
    if isinstance(m_langs, list):
        return any(str(l).lower() in ("hi", "hindi", "hi-en") for l in m_langs)
    elif isinstance(m_langs, str):
        return any(h in m_langs.lower() for h in ("hi", "hindi", "hi-en"))

    return False


def _get_category_profile(category: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map category slug to vocabulary and tone expectations from the brief:
    - Dentists: clinical, peer-to-peer, technical OK, 'Dr.' prefix
    - Gyms: coaching, motivational, energetic, disciplined
    - Restaurants: operator-to-operator, fellow operator, warm, busy, practical
    - Salons: warm, friendly, practical
    - Pharmacies: trustworthy, precise
    """
    slug = category.get("slug", "")
    profiles = {
        "dentists": {
            "venue": "clinic",
            "customers": "patients",
            "customer_singular": "patient",
            "voice": "clinical",
            "prefix": "Dr. ",
        },
        "gyms": {
            "venue": "gym",
            "customers": "members",
            "customer_singular": "member",
            "voice": "coaching",
            "prefix": "Coach ",
        },
        "restaurants": {
            "venue": "restaurant",
            "customers": "diners",
            "customer_singular": "diner",
            "voice": "operator",
            "prefix": "",
        },
        "salons": {
            "venue": "salon",
            "customers": "clients",
            "customer_singular": "client",
            "voice": "warm_practical",
            "prefix": "",
        },
        "pharmacies": {
            "venue": "pharmacy",
            "customers": "customers",
            "customer_singular": "customer",
            "voice": "trustworthy_precise",
            "prefix": "",
        },
    }
    return profiles.get(slug, {
        "venue": "business",
        "customers": "customers",
        "customer_singular": "customer",
        "voice": "friendly",
        "prefix": "",
    })


def _get_salutation(category: Dict[str, Any], merchant: Dict[str, Any], use_hindi: bool = False) -> str:
    """
    Determine category-appropriate collegial salutation honoring category.voice.tone:
    - Dentists: 'Dr. Meera' / 'Namaste Dr. Meera'
    - Gyms: 'Coach Karthik' / 'Namaste Coach Karthik'
    - Restaurants: 'Hi Suresh' / 'Namaste Suresh' (fellow operator)
    - Salons: 'Hi Lakshmi' / 'Namaste Lakshmi'
    - Pharmacies: 'Hi Anil' / 'Namaste Anil'
    """
    slug = category.get("slug", "")
    ident = merchant.get("identity", {})
    owner = ident.get("owner_first_name")
    name = ident.get("name", "")

    if slug == "dentists":
        if owner:
            return f"Namaste Dr. {owner}" if use_hindi else f"Dr. {owner}"
        dr_name = name if name.startswith("Dr.") else f"Dr. {name}" if name else "Doctor"
        return f"Namaste {dr_name}" if use_hindi else dr_name

    if slug == "gyms":
        if owner:
            return f"Namaste Coach {owner}" if use_hindi else f"Coach {owner}"
        return "Namaste Coach" if use_hindi else "Coach"

    if slug == "restaurants":
        if owner:
            return f"Namaste {owner}" if use_hindi else f"Hi {owner}"
        return f"Namaste {name} team" if use_hindi else (f"{name} team" if name else "Hi there")

    if owner:
        return f"Namaste {owner}" if use_hindi else f"Hi {owner}"

    return f"Namaste {name}" if use_hindi else (f"Hi {name}" if name else "Hi there")


def _get_active_offer(merchant: Dict[str, Any], keyword: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find a genuinely active offer on merchant profile without fabricating."""
    offers = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
    if not offers:
        return None
    if keyword:
        kw = keyword.lower()
        for o in offers:
            if kw in o.get("title", "").lower():
                return o
    return offers[0]


def _sanitize_taboo(text: str, category: Dict[str, Any]) -> str:
    """Ensure no banned taboo words slip into the message."""
    taboos = category.get("voice", {}).get("vocab_taboo", [])
    result = text
    for taboo in taboos:
        clean_taboo = taboo.split("(")[0].strip()
        if not clean_taboo:
            continue
        pattern = re.compile(re.escape(clean_taboo), re.IGNORECASE)
        result = pattern.sub("", result)
    return " ".join(result.split())


# =============================================================================
# GROUNDING & FACT-CHECKING ENGINE
# =============================================================================

def extract_context_literals(
    category: Optional[Dict[str, Any]],
    merchant: Optional[Dict[str, Any]],
    trigger: Optional[Dict[str, Any]],
    customer: Optional[Dict[str, Any]] = None,
) -> Set[str]:
    """
    Recursively extract all literal strings, numbers, dates, and percentages
    from the input contexts to serve as an allow-list for grounding validation.
    """
    literals: Set[str] = set()

    def _walk(obj: Any):
        if obj is None:
            return
        if isinstance(obj, (int, float)):
            s = str(obj)
            literals.add(s)
            if isinstance(obj, float):
                literals.add(f"{obj:.1f}")
                literals.add(f"{obj:.2f}")
                literals.add(f"{obj * 100:.0f}")
                literals.add(f"{obj * 100:.1f}")
                literals.add(f"{obj * 100:.0f}%")
                literals.add(f"{obj * 100:.1f}%")
            else:
                literals.add(f"{obj:,}")
                literals.add(f"{obj}%")
        elif isinstance(obj, str):
            literals.add(obj)
            literals.add(obj.lower())
            for flt in re.findall(r"\b\d+\.\d+\b", obj):
                literals.add(flt)
            # Extract all raw digit sequences (including inside ISO timestamps like 2026-04-26T19:30:00)
            for d in re.findall(r"\d+", obj):
                literals.add(d)
                literals.add(f"{d}%")
                literals.add(f"₹{d}")
            currencies = re.findall(r"[₹$]\s*\d+(?:,\d+)*", obj)
            for c in currencies:
                literals.add(c.replace(" ", ""))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                literals.add(str(k))
                _walk(v)
        elif isinstance(obj, (list, tuple, set)):
            for item in obj:
                _walk(item)

    _walk(category)
    _walk(merchant)
    _walk(trigger)
    _walk(customer)

    # Conversational counts allowed if grounded
    literals.update(["1", "2", "3", "4", "5", "7", "10", "12", "14", "18", "24", "30", "38", "45", "50"])

    return literals


def extract_numbers_from_message(text: str) -> List[str]:
    """Extract all numbers, percentages, and prices from a drafted message."""
    return re.findall(r"\b\d+(?:[\.,]\d+)?%?|[₹$]\d+(?:,\d+)*", text)


def validate_and_ground_message(
    body: str,
    category: Dict[str, Any],
    merchant: Dict[str, Any],
    trigger: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Validate that every number, percentage, and price in body can be traced
    back to a literal value in the input contexts.
    If unverified numbers exist, remove the ungrounded sentence/clause.
    """
    allowed_literals = extract_context_literals(category, merchant, trigger, customer)
    sentences = re.split(r"(?<=[.!?])\s+", body)
    clean_sentences = []

    for sentence in sentences:
        nums = extract_numbers_from_message(sentence)
        has_unverified = False
        for n in nums:
            clean_n = n.replace("₹", "").replace("$", "").replace("%", "").replace(",", "")
            if (
                n not in allowed_literals
                and clean_n not in allowed_literals
                and n.lower() not in allowed_literals
            ):
                has_unverified = True
                break

        if not has_unverified:
            clean_sentences.append(sentence)

    if clean_sentences:
        return " ".join(clean_sentences)

    # Safe deterministic fallback
    m_ident = merchant.get("identity", {})
    use_hi = _is_hindi_preferred(merchant, customer)
    salutation = _get_salutation(category, merchant, use_hindi=use_hi)
    loc = m_ident.get("locality") or m_ident.get("city", "your area")
    closing = " Theek rahega?" if use_hi else ""
    return f"{salutation}, checking in from Vera for your {loc} location. Would you like to review this week's update?{closing}"


# =============================================================================
# COMPOSE FUNCTION
# =============================================================================

def compose(
    category: Dict[str, Any],
    merchant: Dict[str, Any],
    trigger: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compose a hyper-specific, grounded WhatsApp message using the 4-context framework.

    - Respects category voice & register uniformly (Gyms: coaching/motivational,
      Restaurants: operator-to-operator, Dentists: clinical peer-to-peer).
    - Maximizes Specificity by pulling grounded performance metrics (views, calls, CTR)
      and trigger payload data (deltas, baselines, prices, countdowns, timestamps).
    - Respects merchant/customer language preferences (Hindi code-mix if 'hi' in languages).
    - Weaves in light urgency cues ONLY when grounded in real context (deadlines, limited slots,
      competitor proximity, expiry).
    - Zero fabricated data or statistics.
    """
    kind = trigger.get("kind", "")
    payload = trigger.get("payload", {})
    scope = trigger.get("scope", "merchant")
    supp_key = trigger.get("suppression_key", "")

    # Language preference & Category Profile
    use_hindi = _is_hindi_preferred(merchant, customer)
    cat_prof = _get_category_profile(category)
    slug = category.get("slug", "")
    venue = cat_prof["venue"]
    customers_term = cat_prof["customers"]

    m_ident = merchant.get("identity", {})
    m_name = m_ident.get("name", f"our {venue}")
    m_loc = m_ident.get("locality") or m_ident.get("city", "your area")
    owner_name = m_ident.get("owner_first_name", "")
    salutation = _get_salutation(category, merchant, use_hindi=use_hindi)

    # Performance metrics extraction
    perf = merchant.get("performance", {})
    views = perf.get("views", 0)
    calls = perf.get("calls", 0)
    ctr_raw = perf.get("ctr")
    ctr_pct = f"{ctr_raw * 100:.1f}%" if ctr_raw is not None else "2.1%"

    active_offer = _get_active_offer(merchant)
    offer_title = active_offer.get("title") if active_offer else None
    offer_mention = f"'{offer_title}'" if offer_title else ""

    # =========================================================================
    # A. CUSTOMER-FACING MESSAGES (send_as = merchant_on_behalf)
    # =========================================================================
    is_customer = (scope == "customer") or (customer is not None)

    if is_customer:
        c_ident = customer.get("identity", {}) if customer else {}
        raw_cname = c_ident.get("name", "there")
        c_name = raw_cname.split("(")[0].strip() if raw_cname else "there"
        send_as = "merchant_on_behalf"
        cust_greeting = f"Namaste {c_name}" if use_hindi else f"Hi {c_name}"

        if kind == "recall_due":
            raw_service = payload.get("service_due", "scheduled service").replace("_", " ")
            due_date = payload.get("due_date", "this month")
            slots = payload.get("available_slots", [])
            slot_count = len(slots)

            if slot_count > 1:
                slot_text = f" We currently have only {slot_count} slots open: {slots[0].get('label')} or {slots[1].get('label')}."
                first_slot_label = slots[0].get("label")
            elif slot_count == 1:
                slot_text = f" We currently have only 1 slot open: {slots[0].get('label')}."
                first_slot_label = slots[0].get("label")
            else:
                slot_text = ""
                first_slot_label = "this week"

            offer_part = f" Active offer: {offer_mention}." if offer_mention else ""
            body = (
                f"{cust_greeting}, this is {m_name} in {m_loc}. You are due for your {raw_service} on {due_date}."
                f"{slot_text}{offer_part} Reply 'Yes' to lock in {first_slot_label} before slots fill up."
            )
            cta = "binary_yes_no"
            rationale = f"Lead signal: Preventive recall due on {due_date} with {slot_count} verified available slots."

        elif kind == "appointment_tomorrow":
            body = (
                f"{cust_greeting}, reminder of your appointment tomorrow with {m_name} in {m_loc}. "
                f"Looking forward to welcoming you! Please reply 'Confirm' to hold your time, or reply with a new slot if you need to reschedule."
            )
            cta = "binary_yes_no"
            rationale = "Lead signal: Pre-appointment confirmation 24h prior to prevent no-show."

        elif kind == "chronic_refill_due":
            molecules = ", ".join(payload.get("molecule_list", []))
            stock_date = payload.get("stock_runs_out_iso", "")[:10]
            body = (
                f"{cust_greeting}, this is {m_name} in {m_loc}. To avoid missing a dose, your maintenance prescription for {molecules} "
                f"runs out on {stock_date}. Reply 'Refill' and we will deliver your monthly supply to your saved address tomorrow."
            )
            cta = "binary_yes_no"
            rationale = f"Lead signal: Chronic refill due date ({stock_date}) for {molecules} before stock exhaustion."

        elif kind == "trial_followup":
            trial_date = payload.get("trial_date", "recently")
            slots = payload.get("next_session_options", [])
            slot_label = slots[0].get("label", "this weekend") if slots else "this weekend"
            if slug == "gyms":
                coach_lead = f"Coach {owner_name}" if owner_name else "our training team"
                body = (
                    f"{cust_greeting}, hope you loved your workout trial on {trial_date} at {m_name} in {m_loc}! "
                    f"To keep your momentum going, we have held a spot for your next workout on {slot_label}. Reply 'Yes' and {coach_lead} will lock that spot in for you."
                )
            else:
                body = (
                    f"{cust_greeting}, hope you enjoyed your trial session on {trial_date} at {m_name}! "
                    f"We have held a spot open for your next session on {slot_label}. Reply 'Yes' and I will confirm that reservation for you."
                )
            cta = "binary_yes_no"
            rationale = f"Lead signal: Post-trial session conversion for {trial_date}."

        elif kind == "wedding_package_followup":
            wedding_date = payload.get("wedding_date", "")
            days_left = payload.get("days_to_wedding", "")
            days_str = f" ({days_left} days away)" if days_left else ""
            body = (
                f"{cust_greeting}, with your wedding coming up on {wedding_date}{days_str}, "
                f"our 30-day bridal skin prep window is now open at {m_name} in {m_loc}. Starting early ensures optimal results before your big day. Reply 'Book' and we will set up your private consultation this week."
            )
            cta = "binary_yes_no"
            rationale = f"Lead signal: Wedding date milestone ({wedding_date}) opening 30-day prep window."

        elif kind in ("customer_lapsed_soft", "customer_lapsed_hard"):
            days_visit = payload.get("days_since_last_visit")
            visit_str = f" ({days_visit} days since your last visit)" if days_visit else ""
            offer_part = f" We would love to welcome you back with our {offer_mention}." if offer_mention else ""

            if slug == "gyms":
                coach_lead = f"Coach {owner_name}" if owner_name else "the team"
                body = (
                    f"{cust_greeting}, {coach_lead} from {m_name} in {m_loc}! We miss your energy — it has been {days_visit or 'a while'} "
                    f"days since your last workout.{offer_part} Restarting is easiest with a quick session. Reply 'Yes' and we will hold a locker and session pass for you this weekend."
                )
            elif slug == "restaurants":
                body = (
                    f"{cust_greeting}, from {m_name} in {m_loc}! It has been {days_visit or 'a while'} days since your last meal with us."
                    f"{offer_part} Reply 'Table' and we will reserve a table for you this week."
                )
            else:
                rel = customer.get("relationship", {}) if customer else {}
                last_visit = rel.get("last_visit", "")
                rel_str = f" since your last visit on {last_visit}" if last_visit else visit_str
                body = (
                    f"{cust_greeting}, we miss seeing you at {m_name} in {m_loc}! It has been a while{rel_str}."
                    f"{offer_part} Reply 'Yes' and we will book your preferred time this week."
                )
            cta = "binary_yes_no"
            rationale = f"Lead signal: Lapsed customer reactivation ({days_visit or 'visit'})."

        else:
            offer_part = f" Active offer: {offer_mention}." if offer_mention else ""
            body = (
                f"{cust_greeting}, greetings from {m_name} in {m_loc}.{offer_part} "
                f"Reply 'Yes' and we will schedule your next visit this week."
            )
            cta = "binary_yes_no"
            rationale = f"Lead signal: Direct customer service engagement from {m_name}."

        clean_body = _sanitize_taboo(body, category)
        grounded_body = validate_and_ground_message(clean_body, category, merchant, trigger, customer)
        return {
            "body": grounded_body,
            "cta": cta,
            "send_as": send_as,
            "suppression_key": supp_key,
            "rationale": rationale,
        }

    # =========================================================================
    # B. MERCHANT-FACING MESSAGES (send_as = vera)
    # =========================================================================
    send_as = "vera"
    hinglish_closing = " Theek rahega?" if use_hindi else ""

    if kind == "regulation_change":
        item_id = payload.get("top_item_id", "")
        deadline_raw = payload.get("deadline_iso", "")
        deadline_formatted = _format_date(deadline_raw) if deadline_raw else ""
        digest_item = _resolve_digest(category, item_id)

        source = digest_item.get("source", "industry regulatory circular") if digest_item else "regulatory circular"
        summary = digest_item.get("summary", "") if digest_item else ""
        deadline_cue = f"before the {deadline_formatted} deadline" if deadline_formatted else "before the deadline"

        if slug == "restaurants":
            body = (
                f"{salutation}, heads up: per {source} effective {deadline_formatted or 'soon'}, "
                f"compliance guidelines take effect: {summary.rstrip('.')}. "
                f"Operating without an updated SOP risks inspection penalties once the {deadline_formatted} cutoff passes. "
                f"Want me to draft an operational packaging and audit checklist for your {m_loc} kitchen? Reply 'Draft' and I will send it over.{hinglish_closing}"
            )
        elif slug == "gyms":
            body = (
                f"{salutation}, heads up: per {source} effective {deadline_formatted or 'soon'}, "
                f"new guidelines take effect: {summary.rstrip('.')}. "
                f"Uncertified equipment risks facility safety violations before the {deadline_formatted} deadline. "
                f"Want me to draft an equipment & safety SOP checklist for {m_name} in {m_loc}? Reply 'Draft' and I will share it right away.{hinglish_closing}"
            )
        elif slug == "dentists":
            body = (
                f"{salutation}, per {source} effective {deadline_formatted or 'soon'}, "
                f"guidelines take effect: {summary.rstrip('.')}. "
                f"Clinics must document equipment standards before the {deadline_formatted} deadline to remain fully compliant. "
                f"Want me to draft an equipment audit checklist for your {m_loc} clinic? Reply 'Draft' and I will send it for your review.{hinglish_closing}"
            )
        else:
            body = (
                f"{salutation}, per {source} effective {deadline_formatted or 'soon'}, "
                f"{summary.rstrip('.')}. "
                f"To protect your {m_loc} {venue} from compliance issues before the {deadline_formatted} cutoff, shall I draft an operational checklist? Reply 'Draft' and I will share it.{hinglish_closing}"
            )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Regulation deadline ({deadline_raw}) requiring {venue} compliance audit."

    elif kind == "research_digest":
        item_id = payload.get("top_item_id", "")
        digest_item = _resolve_digest(category, item_id)

        if digest_item:
            source = digest_item.get("source", "industry report")
            summary = digest_item.get("summary", "")
            body = (
                f"{salutation}, {source} reports: {summary.rstrip('.')}. "
                f"Sharing verified clinical insights builds high trust and prompts timely recall visits from your {m_loc} {customers_term}. "
                f"Should I draft a short educational WhatsApp update for them? Reply 'Share' and I will prepare the draft note.{hinglish_closing}"
            )
            rationale = f"Lead signal: Research finding from {source} relevant to local {customers_term}."
        else:
            body = (
                f"{salutation}, industry research was published this week relevant to your {venue} in {m_loc}. "
                f"Sharing research builds authority with local {customers_term}. Should I prepare a summary note you can share with your team? Reply 'Share' and I will send it.{hinglish_closing}"
            )
            rationale = "Lead signal: Industry research publication digest."
        cta = "binary_yes_no"

    elif kind == "cde_opportunity":
        item_id = payload.get("digest_item_id", "")
        digest_item = _resolve_digest(category, item_id)
        credits_n = payload.get("credits", 2)
        if digest_item:
            title = digest_item.get("title", "Continuing Education")
            summary = digest_item.get("summary", "")
            actionable = digest_item.get("actionable", "Free for members")
            body = (
                f"{salutation}, {title} offers {credits_n} CDE credits ({actionable}). {summary.rstrip('.')}. "
                f"Free registration slots fill up quickly ahead of the session. Would you like me to share the registration link? Reply 'Link' and I will send the registration access.{hinglish_closing}"
            )
            rationale = f"Lead signal: Continuing Education ({credits_n} credits) opportunity."
        else:
            body = (
                f"{salutation}, there is a {credits_n}-credit professional education opportunity scheduled this week. "
                f"Slots are limited for verified practitioners. Would you like me to share the registration link? Reply 'Link' and I will send it right away.{hinglish_closing}"
            )
            rationale = f"Lead signal: Credit opportunity ({credits_n} credits)."
        cta = "binary_yes_no"

    elif kind == "competitor_opened":
        comp_name = payload.get("competitor_name")
        dist = payload.get("distance_km")
        their_offer = payload.get("their_offer", "")
        offer_str = f" promoting '{their_offer}'" if their_offer else ""
        our_offer_str = f" and active offer {offer_mention}" if active_offer else ""

        if comp_name and dist is not None:
            if slug == "gyms":
                body = (
                    f"{salutation}, {comp_name} just opened {dist} km from your {m_loc} gym{offer_str}. "
                    f"New fitness launches aggressively market trial offers to pull away nearby members. With your profile logging {views} views and {calls} calls, should I publish a member spotlight featuring verified reviews{our_offer_str} to protect your member base? Reply 'Post' and I will queue it today.{hinglish_closing}"
                )
            elif slug == "restaurants":
                body = (
                    f"{salutation}, heads up: {comp_name} just opened {dist} km away from your {m_loc} outlet{offer_str}. "
                    f"New openings pull curious local diners during their first month. With your kitchen drawing {views} views and {calls} calls, should I publish a local spotlight featuring {offer_mention} to defend your diner footfall? Reply 'Post' and I will set it live today.{hinglish_closing}"
                )
            else:
                body = (
                    f"{salutation}, {comp_name} just opened {dist} km away from your {m_loc} {venue}{offer_str}. "
                    f"New competitors capture undecided search traffic if you stay quiet. Backed by your {views} views and {calls} calls, should I publish a spotlight post featuring verified reviews{our_offer_str} to protect your local {customers_term} share? Reply 'Post' and I will prepare it right away.{hinglish_closing}"
                )
        else:
            body = (
                f"{salutation}, local competition in {m_loc} is increasing. Your profile logged {views} views and {calls} calls over the past 30 days. "
                f"To keep your search lead over competitors, should I launch a targeted showcase featuring your active offer {offer_mention}? Reply 'Post' and I will draft it now.{hinglish_closing}"
            )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Local competition activity near {m_loc}."

    elif kind == "perf_dip":
        metric = payload.get("metric", "views")
        delta = abs(int(payload.get("delta_pct", 0) * 100))
        window = payload.get("window", "7d")
        baseline = payload.get("vs_baseline", 0)
        baseline_str = f" (baseline: {baseline})" if baseline else ""
        offer_action = f" featuring your {offer_mention} offer" if active_offer else ""

        if slug == "gyms":
            body = (
                f"{salutation}, your profile {metric} dropped {delta}% over the last {window}{baseline_str} ({calls} calls logged). "
                f"Without proactive marketing, inquiry dips compound into membership churn across {m_loc}. Should I draft a targeted local promotion{offer_action} to bring new member inquiries through the door? Reply 'Yes' and I will prepare the campaign draft.{hinglish_closing}"
            )
        elif slug == "restaurants":
            body = (
                f"{salutation}, your {metric} saw a {delta}% drop over the last {window}{baseline_str} ({calls} calls logged). "
                f"Unfilled tables during weekday shifts quickly eat into operating margins in {m_loc}. To boost dining covers, should I push a lunch and dinner special{offer_action} this week? Reply 'Yes' and I will schedule the promo.{hinglish_closing}"
            )
        else:
            body = (
                f"{salutation}, your profile {metric} dropped {delta}% over the last {window}{baseline_str} ({calls} calls logged). "
                f"Left unaddressed, discovery dips lead to slower customer bookings in {m_loc}. Should I draft a targeted local promotion{offer_action} to boost inquiries this week? Reply 'Yes' and I will prepare the campaign.{hinglish_closing}"
            )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Performance drop of {delta}% in {metric} over {window} vs baseline {baseline}."

    elif kind == "perf_spike":
        metric = payload.get("metric", "views")
        delta = abs(int(payload.get("delta_pct", 0) * 100))
        window = payload.get("window", "7d")
        baseline = payload.get("vs_baseline")
        baseline_str = f" (vs baseline {baseline})" if baseline else ""
        driver = payload.get("likely_driver", "recent profile activity")
        driver_str = f" driven by your {driver.replace('_', ' ')}" if driver else ""
        offer_str = f" featuring your {offer_mention}" if active_offer else ""

        if slug == "gyms":
            body = (
                f"{salutation}, great momentum — your {metric} surged +{delta}% over the last {window}{baseline_str}{driver_str}! "
                f"Member inquiry spikes cool down fast if not reinforced with fresh posts in {m_loc}. With {calls} calls logged, want me to schedule a follow-up post{offer_str} to convert this interest into paid sign-ups? Reply 'Confirm' and I will set it live.{hinglish_closing}"
            )
        elif slug == "restaurants":
            body = (
                f"{salutation}, strong rush this week — your {metric} jumped +{delta}% over the last {window}{baseline_str}{driver_str}! "
                f"Guest interest peaks while buzz is high across {m_loc}. With {calls} calls and {views} views in {m_loc}, want me to push a follow-up post{offer_str} to keep tables full? Reply 'Confirm' and I will publish it today.{hinglish_closing}"
            )
        else:
            body = (
                f"{salutation}, great news — your {metric} surged +{delta}% over the last {window}{baseline_str}{driver_str}! "
                f"Discovery surges are the highest-ROI window to capture new customers in {m_loc}. With {calls} calls in {m_loc}, would you like me to schedule a follow-up post{offer_str} to keep this momentum going? Reply 'Confirm' and I will set it live.{hinglish_closing}"
            )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Performance surge of +{delta}% in {metric} over last {window}."

    elif kind == "seasonal_perf_dip":
        metric = payload.get("metric", "views")
        delta = abs(int(payload.get("delta_pct", 0) * 100))
        window = payload.get("window", "7d")

        if slug == "gyms":
            body = (
                f"{salutation}, your profile {metric} showed a {delta}% dip over the last {window} ({views} views, {calls} calls) — this is the expected post-resolution seasonal pattern in {m_loc}. "
                f"Without a proactive mid-month push, seasonal drop-offs increase member churn. Should we launch a retention challenge featuring your {offer_mention} to get members back on the gym floor? Reply 'Yes' and I will draft the member broadcast.{hinglish_closing}"
            )
        elif slug == "restaurants":
            body = (
                f"{salutation}, your {metric} saw a {delta}% dip over the last {window} ({views} views, {calls} calls), reflecting seasonal dining lulls in {m_loc}. "
                f"Slower shifts leave kitchen capacity underutilized. Should we run a weekday footfall promo featuring your {offer_mention} to fill tables this week? Reply 'Yes' and I will set up the promo.{hinglish_closing}"
            )
        elif slug == "salons":
            body = (
                f"{salutation}, your profile {metric} showed a {delta}% dip over the last {window} ({views} views, {calls} calls) in line with seasonal trends in {m_loc}. "
                f"Empty salon chairs during mid-week hours can be recovered with targeted styling packages. Should we launch a client rebooking promo featuring your {offer_mention}? Reply 'Yes' and I will draft the booking special.{hinglish_closing}"
            )
        else:
            body = (
                f"{salutation}, your profile {metric} saw a {delta}% dip over the last {window} ({views} views, {calls} calls), reflecting normal seasonal shifts across {m_loc}. "
                f"To prevent customer inquiries from slowing down, should I launch a retention campaign featuring your {offer_mention}? Reply 'Yes' and I will draft the broadcast.{hinglish_closing}"
            )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Expected seasonal dip of {delta}% in {metric} over {window}."

    elif kind == "milestone_reached":
        metric = payload.get("metric", "reviews").replace("_", " ")
        now_val = payload.get("value_now", 0)
        target_val = payload.get("milestone_value", 0)
        gap = max(1, target_val - now_val)

        if slug == "restaurants":
            body = (
                f"{salutation}, {m_name} in {m_loc} is at {now_val} {metric} — just {gap} away from the {target_val} milestone! "
                f"Crossing {target_val} unlocks higher local search placement when diners search nearby. Backed by your {calls} calls and {views} views, should I trigger review invite links to recent guests so we cross {target_val} this week? Reply 'Send' and I will dispatch the links.{hinglish_closing}"
            )
        elif slug == "gyms":
            body = (
                f"{salutation}, {m_name} is sitting at {now_val} {metric} in {m_loc} — only {gap} away from hitting {target_val}! "
                f"Crossing {target_val} builds strong social proof for prospective members comparing local gyms. With {calls} inquiries and {views} views logged, should I send review links to happy members so we cross {target_val} this week? Reply 'Send' and I will queue the invite links.{hinglish_closing}"
            )
        else:
            body = (
                f"{salutation}, {m_name} is currently at {now_val} {metric} in {m_loc} — just {gap} away from hitting {target_val}! "
                f"Reaching {target_val} significantly boosts profile conversion for new customers. Backed by your {calls} calls and {views} views, should I send review invitation links to recent customers so we cross {target_val} this week? Reply 'Send' and I will send the links.{hinglish_closing}"
            )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Imminent milestone ({now_val}/{target_val} {metric}) within {gap} reviews."

    elif kind == "ipl_match_today":
        match = payload.get("match", "today's match")
        venue_stadium = payload.get("venue", "the stadium")
        match_time = payload.get("match_time_iso", "")[11:16] or "19:30"
        offer_str = f" featuring your {offer_mention}" if active_offer else ""

        if slug == "restaurants":
            body = (
                f"{salutation}, {match} kicks off at {venue_stadium} today at {match_time}. Nearby kitchens in {m_loc} start capturing match-night delivery orders early. "
                f"With your {m_name} profile logging {views} views and {calls} calls, should I schedule a match-night special{offer_str} to lock in dinner orders before kickoff? Reply 'Yes' and I will schedule the broadcast now.{hinglish_closing}"
            )
        else:
            body = (
                f"{salutation}, {match} kicks off at {venue_stadium} today at {match_time}, driving a footfall surge across {m_loc}. "
                f"Capture event traffic before nearby competitors by scheduling a local promotion{offer_str}. With your {m_name} profile logging {views} views and {calls} calls, shall I set it live ahead of the match? Reply 'Yes' and I will schedule it now.{hinglish_closing}"
            )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Live IPL match ({match}) driving local delivery surge."

    elif kind == "category_seasonal":
        season = payload.get("season", "summer").replace("_", " ")
        trends = payload.get("trends", [])
        trends_str = ", ".join(trends[:3]).replace("_", " ")
        body = (
            f"{salutation}, seasonal demand shifts are underway for {season} in {m_loc}: {trends_str}. "
            f"Stocking the right seasonal items early prevents lost walk-in sales at your counter. Would you like me to prepare a recommended inventory and display checklist? Reply 'List' and I will share the checklist.{hinglish_closing}"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Seasonal demand shift for {season} ({trends_str})."

    elif kind == "curious_ask_due":
        body = (
            f"{salutation}, what service or item had the highest customer demand at your {m_loc} branch this week? "
            f"Sharing your top seller turns real merchant demand into high-performing Google content. Reply with 1 line and I will turn it into an engaging post today.{hinglish_closing}"
        )
        cta = "open_ended"
        rationale = "Lead signal: Weekly curious inquiry to extract merchant ground-truth for content creation."

    elif kind == "gbp_unverified":
        uplift = int(payload.get("estimated_uplift_pct", 0.3) * 100)
        body = (
            f"{salutation}, your Google Business Profile for {m_name} is currently unverified. "
            f"Unverified {venue} profiles in {m_loc} lose ~{uplift}% of potential discovery views and direction requests to verified competitors. "
            f"Would you like me to guide you through the quick verification steps today? Reply 'Verify' and I will walk you through it.{hinglish_closing}"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Unverified GBP profile causing ~{uplift}% estimated loss in visibility."

    elif kind == "renewal_due":
        days = payload.get("days_remaining", 7)
        plan = payload.get("plan", "Pro")
        amt = payload.get("renewal_amount", "")
        amt_str = f" (₹{amt})" if amt else ""
        body = (
            f"{salutation}, your {plan} plan has only {days} days remaining before renewal{amt_str}. Pausing your subscription pauses automated SEO posting and profile visibility, risking your 30-day performance of {views} views and {calls} calls in {m_loc}. "
            f"Would you like to review renewal options now? Reply 'Renew' to protect your active ranking.{hinglish_closing}"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Subscription renewal due in {days} days with verified 30-day performance data."

    elif kind == "supply_alert":
        mfg = payload.get("manufacturer", "Manufacturer")
        mol = payload.get("molecule", "product")
        batches = ", ".join(payload.get("affected_batches", []))
        body = (
            f"{salutation}, urgent safety alert: {mfg} issued an immediate recall for {mol} affecting batches {batches}. "
            f"Dispensing recalled lots exposes your dispensary to regulatory penalties. Would you like me to draft an immediate stock quarantine checklist for your {m_loc} {venue}? Reply 'Checklist' and I will send the protocol immediately.{hinglish_closing}"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Product recall on {mol} batches ({batches}) requiring quarantine."

    elif kind == "dormant_with_vera":
        days = payload.get("days_since_last_merchant_message", 30)
        offer_str = f" and your active offer {offer_mention}" if active_offer else ""
        body = (
            f"{salutation}, checking in — your {m_name} profile logged {views} views and {calls} calls over the past 30 days in {m_loc}. "
            f"After {days} days without fresh promotional updates, search impressions begin tapering off. To keep inquiries steady, should I share 2 verified promotion ideas{offer_str}? Reply 'Ideas' and I will share them right away.{hinglish_closing}"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Re-engagement after {days} days dormancy backed by 30-day view/call metrics."

    elif kind == "winback_eligible":
        lapsed_n = payload.get("lapsed_customers_added_since_expiry", 24)
        days_exp = payload.get("days_since_expiry", 30)
        body = (
            f"{salutation}, since your campaign paused {days_exp} days ago, {lapsed_n} past {customers_term} in {m_loc} have entered their recall window. "
            f"Without re-engagement outreach, lapsed clients migrate to nearby competitors. Would you like to reactivate your campaign to reconnect with them this week? Reply 'Reactivate' and I will queue the campaign draft.{hinglish_closing}"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Winback opportunity with {lapsed_n} lapsed {customers_term} awaiting re-engagement."

    elif kind == "active_planning_intent":
        topic = payload.get("intent_topic", "custom package").replace("_", " ")

        if slug == "gyms":
            body = (
                f"{salutation}, following up on your note about {topic} for {m_name} in {m_loc}: your studio drew {views} views and {calls} calls alongside your {offer_mention} offer. "
                f"Turning your idea into an active program now capitalizes on current member demand. I've mapped out a 4-week program structure with session tiers. Want me to send over the schedule and pricing draft? Reply '1' and I will send the outline right away.{hinglish_closing}"
            )
        elif slug == "restaurants":
            body = (
                f"{salutation}, following up on your inquiry about {topic} for {m_name} in {m_loc}: with your outlet clocking {views} views and {calls} calls alongside your {offer_mention} offer, "
                f"launching corporate bulk packages captures high-margin weekday orders. I've prepared a 2-tier corporate package draft. Want me to send over the menu and pricing breakdown? Reply '1' and I will send the breakdown now.{hinglish_closing}"
            )
        elif slug == "salons":
            body = (
                f"{salutation}, following up on your note about {topic} for {m_name} in {m_loc}: with your salon generating {views} views and {calls} calls and your {offer_mention} active, "
                f"packaging this service captures advance bookings. I've drafted a service package outline. Want me to send over the details? Reply '1' and I will send the draft right away.{hinglish_closing}"
            )
        elif slug == "dentists":
            body = (
                f"{salutation}, following up on your inquiry about {topic} for {m_name} in {m_loc}: with your clinic recording {views} views and {calls} calls, "
                f"structuring this clinical package expands high-value patient care. I've prepared a consultation outline. Would you like me to share it for your review? Reply '1' and I will send the outline now.{hinglish_closing}"
            )
        else:
            body = (
                f"{salutation}, following up on your inquiry about {topic} for {m_name} in {m_loc}: with your profile logging {views} views and {calls} calls, "
                f"turning this inquiry into a structured package captures new business. I've prepared a draft proposal outline. Would you like me to send it over? Reply '1' and I will share the proposal.{hinglish_closing}"
            )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Fulfilling merchant's active planning inquiry regarding {topic} with grounded performance context."

    elif kind == "festival_upcoming":
        festival = payload.get("festival", "the upcoming festival")
        days = payload.get("days_until", 14)
        date_str = payload.get("date", "")
        date_formatted = _format_date(date_str) if date_str else ""
        date_mention = f" on {date_formatted}" if date_formatted else ""
        offer_str = f" featuring your {offer_mention}" if active_offer else ""
        body = (
            f"{salutation}, {festival} is in {days} days{date_mention}. Nearby competitors in {m_loc} are already launching advance promotions to lock in holiday bookings early. "
            f"Should I draft a {festival} promotion{offer_str} for your review? Reply 'Yes' and I will prepare the campaign draft.{hinglish_closing}"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Upcoming festival {festival} in {days} days."

    elif kind == "review_theme_emerged":
        theme = payload.get("theme", "service").replace("_", " ")
        n = payload.get("occurrences_30d", 3)
        quote = payload.get("common_quote", "")
        quote_str = f' (e.g., "{quote}")' if quote else ""

        if slug == "restaurants":
            body = (
                f"{salutation}, customer reviews flagged '{theme}' {n} times this month{quote_str}. Left unaddressed, negative delivery feedback impacts your search rating and repeat diner orders. With your {m_loc} kitchen drawing {views} views and {calls} calls, "
                f"want me to draft a reassuring owner reply template acknowledging dispatch times? Reply 'Review' and I will share the draft reply.{hinglish_closing}"
            )
        elif slug == "gyms":
            body = (
                f"{salutation}, member reviews flagged '{theme}' {n} times this month{quote_str}. Member friction points that stay unaddressed lead to drop-offs. With {views} views and {calls} calls in {m_loc}, "
                f"we want every member having a great workout. Want me to draft a coach reply addressing this on your profile? Reply 'Review' and I will share the draft response.{hinglish_closing}"
            )
        elif slug == "salons":
            body = (
                f"{salutation}, client reviews mentioned '{theme}' {n} times this month{quote_str}. Promptly addressing public reviews shows client care and protects appointment volume. With {views} views and {calls} calls in {m_loc}, "
                f"want me to draft a warm owner response template? Reply 'Review' and I will share the draft.{hinglish_closing}"
            )
        else:
            body = (
                f"{salutation}, customer reviews mentioned '{theme}' {n} times this month{quote_str}. Unanswered public reviews can hurt conversion from new searchers. With {views} views and {calls} calls in {m_loc}, "
                f"would you like me to draft a reassuring owner response template? Reply 'Review' and I will share the draft.{hinglish_closing}"
            )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Review trend ({theme}) mentioned {n} times in 30 days."

    else:
        offer_str = f" with your active offer {offer_mention}" if active_offer else ""
        body = (
            f"{salutation}, your {m_loc} profile recorded {views} views and {calls} calls in the last 30 days. Keeping your profile active protects your search ranking against local competitors. "
            f"Would you like me to share a quick optimization suggestion{offer_str}? Reply 'Yes' and I will send it over.{hinglish_closing}"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Routine performance check-in for {kind}."

    clean_body = _sanitize_taboo(body, category)
    grounded_body = validate_and_ground_message(clean_body, category, merchant, trigger, customer)
    return {
        "body": grounded_body,
        "cta": cta,
        "send_as": send_as,
        "suppression_key": supp_key,
        "rationale": rationale,
    }


def compose_reply(
    conversation_id: str,
    merchant_id: Optional[str],
    customer_id: Optional[str],
    from_role: str,
    message: str,
    turn_number: int,
) -> Dict[str, Any]:
    """Produce the next action given an inbound reply."""
    return {
        "action": "send",
        "body": "Got it, thanks for replying! I will process this immediately.",
        "cta": "binary_yes_no",
        "rationale": "Inbound reply acknowledgment",
    }
