import json
from typing import Any, Dict, Optional


def _resolve_digest(category: Dict[str, Any], item_id: str) -> Optional[Dict[str, Any]]:
    for item in category.get("digest", []):
        if item.get("id") == item_id:
            return item
    return None


def _get_salutation(category: Dict[str, Any], merchant: Dict[str, Any]) -> str:
    slug = category.get("slug", "")
    ident = merchant.get("identity", {})
    owner = ident.get("owner_first_name")
    if not owner:
        # Fall back to clinic/business name without "Dr." duplication
        name = ident.get("name", "there")
        return f"Dr. {name}" if slug == "dentists" and not name.startswith("Dr.") else f"Hi {name}"
    
    if slug == "dentists":
        return f"Dr. {owner}"
    return f"Hi {owner}"


def _get_active_offer(merchant: Dict[str, Any], keyword: Optional[str] = None) -> Optional[Dict[str, Any]]:
    offers = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
    if not offers:
        return None
    if keyword:
        kw = keyword.lower()
        for o in offers:
            if kw in o.get("title", "").lower():
                return o
    return offers[0]


def compose(
    category: Dict[str, Any],
    merchant: Dict[str, Any],
    trigger: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compose a hyper-specific, grounded WhatsApp message.
    """
    kind = trigger.get("kind", "")
    payload = trigger.get("payload", {})
    scope = trigger.get("scope", "merchant")
    supp_key = trigger.get("suppression_key", "")

    m_ident = merchant.get("identity", {})
    m_name = m_ident.get("name", "our clinic")
    m_loc = m_ident.get("locality") or m_ident.get("city", "your area")
    salutation = _get_salutation(category, merchant)

    perf = merchant.get("performance", {})
    views = perf.get("views", 0)
    calls = perf.get("calls", 0)
    ctr_pct = f"{perf.get('ctr', 0.0) * 100:.1f}%" if "ctr" in perf else "2.1%"

    active_offer = _get_active_offer(merchant)
    offer_mention = f"'{active_offer.get('title')}'" if active_offer else ""

    # Check if customer-facing
    is_customer = scope == "customer" or (customer is not None)

    if is_customer:
        c_ident = customer.get("identity", {}) if customer else {}
        c_name = c_ident.get("name", "there")
        send_as = "merchant_on_behalf"

        if kind == "recall_due":
            service_due = payload.get("service_due", "cleaning").replace("_", " ")
            due_date = payload.get("due_date", "this month")
            slots = payload.get("available_slots", [])
            slot_text = ""
            first_slot_label = "this week"
            if slots:
                first_slot_label = slots[0].get("label", "this week")
                if len(slots) > 1:
                    slot_text = f" We have slots open {slots[0].get('label')} or {slots[1].get('label')}."
                else:
                    slot_text = f" We have a slot open {slots[0].get('label')}."

            offer_part = f" Active offer: {offer_mention}." if offer_mention else ""
            body = (
                f"Hi {c_name}, this is {m_name} in {m_loc}. You are due for your {service_due} on {due_date}."
                f"{slot_text}{offer_part} Would {first_slot_label} work for you?"
            )
            cta = "binary_yes_no"
            rationale = f"Lead signal: Preventive recall due on {due_date} with verified clinic slots."

        elif kind == "appointment_tomorrow":
            body = (
                f"Hi {c_name}, reminder of your appointment tomorrow with {m_name} in {m_loc}. "
                f"Looking forward to seeing you! Please let us know if you need to adjust your time."
            )
            cta = "binary_yes_no"
            rationale = "Lead signal: Appointment scheduled for tomorrow; confirmation reminder to prevent no-show."

        elif kind == "chronic_refill_due":
            molecules = ", ".join(payload.get("molecule_list", []))
            stock_date = payload.get("stock_runs_out_iso", "")[:10]
            body = (
                f"Hi {c_name}, this is {m_name} in {m_loc}. Your maintenance prescription for {molecules} "
                f"runs out on {stock_date}. Would you like us to deliver your monthly refill to your saved address tomorrow?"
            )
            cta = "binary_yes_no"
            rationale = f"Lead signal: Chronic medication refill due ({molecules}) before stock runs out on {stock_date}."

        elif kind == "trial_followup":
            trial_date = payload.get("trial_date", "recently")
            slots = payload.get("next_session_options", [])
            slot_label = slots[0].get("label", "this weekend") if slots else "this weekend"
            body = (
                f"Hi {c_name}, hope you enjoyed your trial session on {trial_date} at {m_name}! "
                f"We have a spot open for your next session on {slot_label}. Should I reserve it for you?"
            )
            cta = "binary_yes_no"
            rationale = f"Lead signal: Post-trial follow-up for session completed on {trial_date}."

        elif kind == "wedding_package_followup":
            wedding_date = payload.get("wedding_date", "")
            days_left = payload.get("days_to_wedding", "")
            days_str = f" ({days_left} days away)" if days_left else ""
            body = (
                f"Hi {c_name}, with your wedding coming up on {wedding_date}{days_str}, "
                f"our 30-day bridal skin prep window is now open at {m_name} in {m_loc}. Would you like to schedule your consultation this week?"
            )
            cta = "binary_yes_no"
            rationale = f"Lead signal: Wedding countdown ({wedding_date}) opening 30-day prep window."

        elif kind in ("customer_lapsed_soft", "customer_lapsed_hard"):
            rel = customer.get("relationship", {}) if customer else {}
            last_visit = rel.get("last_visit", "")
            services = rel.get("services_received", [])
            last_svc = services[-1] if services else "visit"
            visit_str = f" since your last {last_svc} on {last_visit}" if last_visit else ""
            offer_part = f" We'd love to welcome you back with our {offer_mention}." if offer_mention else ""
            body = (
                f"Hi {c_name}, we miss seeing you at {m_name} in {m_loc}! It's been a while{visit_str}."
                f"{offer_part} Would you like to book a session this week?"
            )
            cta = "binary_yes_no"
            rationale = f"Lead signal: Lapsed customer engagement based on visit history ({last_visit})."

        else:
            offer_part = f" Available offer: {offer_mention}." if offer_mention else ""
            body = (
                f"Hi {c_name}, greetings from {m_name} in {m_loc}.{offer_part} "
                f"Would you like to book your next appointment with us this week?"
            )
            cta = "binary_yes_no"
            rationale = f"Lead signal: Direct customer engagement from {m_name}."

        return {
            "body": body,
            "cta": cta,
            "send_as": send_as,
            "suppression_key": supp_key,
            "rationale": rationale,
        }

    # Merchant-facing message
    send_as = "vera"

    if kind == "regulation_change":
        item_id = payload.get("top_item_id", "")
        deadline = payload.get("deadline_iso", "")
        digest_item = _resolve_digest(category, item_id)
        if digest_item:
            source = digest_item.get("source", "regulatory circular")
            summary = digest_item.get("summary", "")
            date_mention = f"effective {deadline}" if deadline else ""
            body = (
                f"{salutation}, per {source}, {summary.rstrip('.')} {date_mention}. "
                f"Want me to draft an audit checklist for your {m_loc} clinic before the deadline?"
            )
            rationale = f"Lead signal: Regulatory compliance deadline ({deadline}) from {source}."
        else:
            date_mention = f"effective {deadline}" if deadline else "upcoming"
            body = (
                f"{salutation}, new compliance guidelines are {date_mention} for your category. "
                f"Want me to draft a compliance audit checklist for your {m_loc} clinic?"
            )
            rationale = f"Lead signal: Compliance guideline deadline ({deadline})."
        cta = "binary_yes_no"

    elif kind == "research_digest":
        item_id = payload.get("top_item_id", "")
        digest_item = _resolve_digest(category, item_id)
        cust_agg = merchant.get("customer_aggregate", {})
        high_risk_n = cust_agg.get("high_risk_adult_count")

        if digest_item:
            source = digest_item.get("source", "latest clinical journal")
            trial_n = digest_item.get("trial_n")
            summary = digest_item.get("summary", "")
            trial_str = f"a {trial_n:,}-patient trial published in " if trial_n else ""
            cohort_str = f" You currently have {high_risk_n} high-risk adult patients in your charting." if high_risk_n else ""
            body = (
                f"{salutation}, {trial_str}{source} shows {summary.rstrip('.')}.{cohort_str} "
                f"Should I draft a WhatsApp recall note for your high-risk patients to discuss this?"
            )
            rationale = f"Lead signal: Clinical trial evidence from {source} matching merchant cohort."
        else:
            body = (
                f"{salutation}, new clinical research was published this week relevant to your patient mix in {m_loc}. "
                f"Should I prepare a summary note you can share with your team?"
            )
            rationale = "Lead signal: Industry research publication digest."
        cta = "binary_yes_no"

    elif kind == "cde_opportunity":
        item_id = payload.get("digest_item_id", "")
        digest_item = _resolve_digest(category, item_id)
        credits = payload.get("credits", 2)
        if digest_item:
            title = digest_item.get("title", "IDA Webinar")
            summary = digest_item.get("summary", "")
            actionable = digest_item.get("actionable", "Free for members")
            body = (
                f"{salutation}, {title} offers {credits} CDE credits ({actionable}). {summary.rstrip('.')}. "
                f"Would you like me to share the registration link?"
            )
            rationale = f"Lead signal: Continuing Dental Education ({credits} credits) webinar opportunity."
        else:
            body = (
                f"{salutation}, there is a {credits}-credit CDE opportunity scheduled this week. "
                f"Would you like me to share the registration link?"
            )
            rationale = f"Lead signal: CDE credit opportunity ({credits} credits)."
        cta = "binary_yes_no"

    elif kind == "competitor_opened":
        comp_name = payload.get("competitor_name", "A competitor")
        dist = payload.get("distance_km", 1.0)
        their_offer = payload.get("their_offer", "")
        offer_str = f" promoting '{their_offer}'" if their_offer else ""
        our_offer_str = f" and active offer '{active_offer.get('title')}'" if active_offer else ""
        body = (
            f"{salutation}, {comp_name} just opened {dist} km away from your {m_loc} clinic{offer_str}. "
            f"Should I publish a spotlight post featuring your verified reviews{our_offer_str} to protect your local patient share?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Competitor {comp_name} opened within {dist} km with promotional pricing."

    elif kind == "perf_dip":
        metric = payload.get("metric", "views")
        delta = abs(int(payload.get("delta_pct", 0) * 100))
        window = payload.get("window", "7d")
        baseline = payload.get("vs_baseline", 0)
        offer_action = f" featuring your {offer_mention} offer" if active_offer else ""
        body = (
            f"{salutation}, your profile {metric} dropped {delta}% over the last {window} (baseline: {baseline}). "
            f"Should I draft a targeted local promotion{offer_action} to boost inquiries in {m_loc}?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Performance drop of {delta}% in {metric} over {window} vs baseline {baseline}."

    elif kind == "perf_spike":
        metric = payload.get("metric", "views")
        delta = abs(int(payload.get("delta_pct", 0) * 100))
        driver = payload.get("likely_driver", "recent profile activity")
        driver_str = f" driven by your {driver.replace('_', ' ')}" if driver else ""
        body = (
            f"{salutation}, great news — your {metric} surged +{delta}% over the last 7 days{driver_str}! "
            f"Would you like me to schedule a follow-up Google post to keep this momentum going?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Performance surge of +{delta}% in {metric}."

    elif kind == "seasonal_perf_dip":
        metric = payload.get("metric", "views")
        delta = abs(int(payload.get("delta_pct", 0) * 100))
        body = (
            f"{salutation}, your profile {metric} saw a {delta}% dip this week, which is normal seasonal lull across {m_loc}. "
            f"Should I launch a customer retention check-in campaign to keep existing clients engaged?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Expected seasonal dip of {delta}% in {metric}; retention campaign recommended."

    elif kind == "milestone_reached":
        metric = payload.get("metric", "reviews").replace("_", " ")
        now_val = payload.get("value_now", 0)
        target_val = payload.get("milestone_value", 0)
        gap = max(1, target_val - now_val)
        body = (
            f"{salutation}, {m_name} is currently at {now_val} {metric} — just {gap} away from hitting {target_val}! "
            f"Should I send review invitation links to your last 10 satisfied customers so we cross {target_val} this week?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Imminent milestone ({now_val}/{target_val} {metric}) within {gap} reviews."

    elif kind == "ipl_match_today":
        match = payload.get("match", "today's match")
        venue = payload.get("venue", "the stadium")
        match_time = payload.get("match_time_iso", "")[11:16] or "evening"
        offer_str = f" featuring your {offer_mention}" if active_offer else ""
        body = (
            f"{salutation}, {match} is playing today at {venue} at {match_time}. Delivery orders across {m_loc} "
            f"typically peak 45 minutes before first ball. Should I schedule a broadcast{offer_str} at 6:30 PM?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Major sports event ({match}) driving local delivery demand surge."

    elif kind == "category_seasonal":
        season = payload.get("season", "summer").replace("_", " ")
        trends = payload.get("trends", [])
        trends_str = ", ".join(trends[:3]).replace("_", " ")
        body = (
            f"{salutation}, seasonal demand shifts are underway for {season} in {m_loc}: {trends_str}. "
            f"Would you like me to prepare a recommended inventory and display checklist for your counter?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Seasonal demand transition for {season} ({trends_str})."

    elif kind == "curious_ask_due":
        body = (
            f"{salutation}, what service or item had the highest customer demand at your {m_loc} branch this week? "
            f"Reply with 1 line and I'll turn it into an engaging Google post for you today."
        )
        cta = "open_ended"
        rationale = "Lead signal: Weekly curious inquiry to extract merchant ground-truth for content creation."

    elif kind == "gbp_unverified":
        uplift = int(payload.get("estimated_uplift_pct", 0.3) * 100)
        body = (
            f"{salutation}, your Google Business Profile for {m_name} is currently unverified. "
            f"Verified profiles in {m_loc} get ~{uplift}% more discovery searches and calls. "
            f"Would you like me to guide you through the quick verification steps today?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Unverified GBP profile causing ~{uplift}% estimated loss in visibility."

    elif kind == "renewal_due":
        days = payload.get("days_remaining", 7)
        plan = payload.get("plan", "Pro")
        amt = payload.get("renewal_amount", "")
        amt_str = f" (₹{amt})" if amt else ""
        body = (
            f"{salutation}, your {plan} plan renews in {days} days{amt_str}. Over the last 30 days, your profile generated "
            f"{views} views and {calls} calls in {m_loc}. Would you like to review renewal options now?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Subscription renewal due in {days} days with verified 30-day performance data."

    elif kind == "supply_alert":
        mfg = payload.get("manufacturer", "Manufacturer")
        mol = payload.get("molecule", "product")
        batches = ", ".join(payload.get("affected_batches", []))
        body = (
            f"{salutation}, urgent safety alert: {mfg} issued a recall for {mol} affecting batches {batches}. "
            f"Would you like me to draft an immediate stock quarantine checklist for your {m_loc} dispensary?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Product recall on {mol} batches ({batches}) requiring quarantine."

    elif kind == "dormant_with_vera":
        days = payload.get("days_since_last_merchant_message", 30)
        offer_str = f" and your active offer {offer_mention}" if active_offer else ""
        body = (
            f"{salutation}, checking in — your profile logged {views} views and {calls} calls over the past 30 days in {m_loc}. "
            f"Would you like to review 2 quick promotional ideas{offer_str} to boost customer inquiries this week?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Re-engagement after {days} days dormancy backed by 30-day view/call metrics."

    elif kind == "winback_eligible":
        lapsed_n = payload.get("lapsed_customers_added_since_expiry", 24)
        body = (
            f"{salutation}, since your campaign paused, {lapsed_n} past customers in {m_loc} have entered their recall window. "
            f"Would you like to reactivate your campaign to reconnect with them this week?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Winback opportunity with {lapsed_n} lapsed customers awaiting re-engagement."

    elif kind == "active_planning_intent":
        topic = payload.get("intent_topic", "custom package").replace("_", " ")
        body = (
            f"{salutation}, following up on your question about the {topic} for {m_loc}: "
            f"I have prepared a draft outline with pricing and items. Would you like me to send it over for your review?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Fulfilling merchant's active planning inquiry regarding {topic}."

    elif kind == "festival_upcoming":
        festival = payload.get("festival", "the upcoming festival")
        days = payload.get("days_until", 14)
        date_str = payload.get("date", "")
        date_mention = f" on {date_str}" if date_str else ""
        offer_str = f" featuring your {offer_mention}" if active_offer else ""
        body = (
            f"{salutation}, {festival} is in {days} days{date_mention}. Nearby competitors in {m_loc} are already launching specials. "
            f"Should I draft a {festival} promotion{offer_str} for your review?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Upcoming festival {festival} in {days} days."

    elif kind == "review_theme_emerged":
        theme = payload.get("theme", "service").replace("_", " ")
        n = payload.get("occurrences_30d", 3)
        quote = payload.get("common_quote", "")
        quote_str = f' (e.g., "{quote}")' if quote else ""
        body = (
            f"{salutation}, customer reviews mentioned '{theme}' {n} times this month{quote_str}. "
            f"Would you like me to draft a reassuring owner response template to address this publicly?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Negative review trend ({theme}) mentioned {n} times in 30 days."

    else:
        # Generic fallback
        offer_str = f" with your active offer {offer_mention}" if active_offer else ""
        body = (
            f"{salutation}, your {m_loc} profile recorded {views} views and {calls} calls in the last 30 days. "
            f"Would you like me to share a quick optimization suggestion{offer_str} for this week?"
        )
        cta = "binary_yes_no"
        rationale = f"Lead signal: Routine performance check-in for {kind}."

    return {
        "body": body,
        "cta": cta,
        "send_as": send_as,
        "suppression_key": supp_key,
        "rationale": rationale,
    }


if __name__ == "__main__":
    pairs = json.load(open("expanded/test_pairs.json"))["pairs"]
    cats = {}
    import glob
    for f in glob.glob("expanded/categories/*.json"):
        c = json.load(open(f))
        cats[c["slug"]] = c

    for p in pairs[27:]:
        tid = p["trigger_id"]
        mid = p["merchant_id"]
        cid = p["customer_id"]
        trg = json.load(open(f"expanded/triggers/{tid}.json"))
        merch = json.load(open(f"expanded/merchants/{mid}.json"))
        cat = cats[merch["category_slug"]]
        cust = json.load(open(f"expanded/customers/{cid}.json")) if cid else None

        res = compose(cat, merch, trg, cust)
        print(f"=== {p['test_id']}: {tid} ===")
        print("Body:", res["body"])
        print("CTA:", res["cta"])
        print("Rationale:", res["rationale"])
        print("Send As:", res["send_as"])
        print()
