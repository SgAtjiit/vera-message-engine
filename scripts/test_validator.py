import re
from typing import Any, Dict, List, Optional, Set


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
            # Extract numbers from inside string fields
            nums = re.findall(r"\b\d+(?:[\.,]\d+)?\b", obj)
            for n in nums:
                literals.add(n)
                clean_n = n.replace(",", "")
                literals.add(clean_n)
                literals.add(f"{clean_n}%")
            # Extract currency
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

    # Common innocent conversational words like "1 line" or "2 options"
    literals.update(["1", "2", "3", "7", "30"])

    return literals


def extract_numbers_from_message(text: str) -> List[str]:
    """Extract all numbers, percentages, and prices from a drafted message."""
    # Match numbers, percentages, and prices
    matches = re.findall(r"\b\d+(?:[\.,]\d+)?%?|[₹$]\d+(?:,\d+)*", text)
    return matches


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
    
    # Split body into sentences
    sentences = re.split(r"(?<=[.!?])\s+", body)
    clean_sentences = []

    for sentence in sentences:
        nums = extract_numbers_from_message(sentence)
        has_unverified = False
        for n in nums:
            # Check direct match
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
        else:
            # Drop ungrounded sentence
            pass

    if clean_sentences:
        return " ".join(clean_sentences)

    # Fallback to 100% verified template
    m_ident = merchant.get("identity", {})
    owner = m_ident.get("owner_first_name") or m_ident.get("name", "there")
    salutation = f"Dr. {owner}" if category.get("slug") == "dentists" else f"Hi {owner}"
    loc = m_ident.get("locality") or m_ident.get("city", "your area")
    return f"{salutation}, checking in from Vera for your {loc} location. Would you like to review this week's update?"


# Test
if __name__ == "__main__":
    sample_cat = {"slug": "dentists", "digest": [{"source": "JIDA Oct 2026, p.14", "summary": "38% lower caries recurrence with 3-month recall"}]}
    sample_merch = {"identity": {"name": "Dr. Meera's Clinic", "locality": "Lajpat Nagar", "owner_first_name": "Meera"}, "performance": {"views": 2410, "calls": 18}}
    sample_trg = {"kind": "research_digest", "payload": {"top_item_id": "d_123"}}

    # Sentence with fabricated patient count 124
    msg_with_fab = "Dr. Meera, JIDA Oct 2026, p.14 shows 38% lower caries recurrence with 3-month recall. You currently have 124 high-risk adult patients in your charting. Should I draft a note for them?"
    cleaned = validate_and_ground_message(msg_with_fab, sample_cat, sample_merch, sample_trg)
    print("Cleaned message:")
    print(cleaned)
    assert "124" not in cleaned
    print("PASS: Unverified 124 was stripped cleanly!")
