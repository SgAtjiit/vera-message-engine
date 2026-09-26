import json
import glob
import sys
sys.path.insert(0, ".")
from app.composer import compose

cats = {json.load(open(f, encoding="utf-8"))["slug"]: json.load(open(f, encoding="utf-8")) for f in glob.glob("expanded/categories/*.json")}

# Test 1: Merchant with 'hi' (Dr. Meera)
m_001 = json.load(open("expanded/merchants/m_001_drmeera_dentist_delhi.json", encoding="utf-8"))
trg_002 = json.load(open("expanded/triggers/trg_002_compliance_dci_radiograph.json", encoding="utf-8"))
res1 = compose(cats["dentists"], m_001, trg_002)
print("=== Test 1: Hindi code-mix (Dr. Meera with ['en', 'hi']) ===")
print("Body:", res1["body"])
print("CTA:", res1["cta"])
print("Rationale:", res1["rationale"])
print()

# Test 2: Merchant with only 'en'
m_en = dict(m_001)
m_en["identity"] = dict(m_001["identity"])
m_en["identity"]["languages"] = ["en"]
res2 = compose(cats["dentists"], m_en, trg_002)
print("=== Test 2: Pure English (Dr. Meera with ['en'] only) ===")
print("Body:", res2["body"])
print()

# Test 3: Customer with recall slots urgency
trg_003 = json.load(open("expanded/triggers/trg_003_recall_due_priya.json", encoding="utf-8"))
cust_001 = json.load(open("expanded/customers/c_001_priya_for_m001.json", encoding="utf-8"))
res3 = compose(cats["dentists"], m_001, trg_003, cust_001)
print("=== Test 3: Customer Recall Due with urgency & Hindi preference ===")
print("Body:", res3["body"])
print()
