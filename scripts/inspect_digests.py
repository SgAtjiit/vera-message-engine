import glob
import json

for f in sorted(glob.glob("expanded/categories/*.json")):
    cat = json.load(open(f, encoding="utf-8"))
    print(f"=== {cat['slug']} ===")
    for d in cat.get("digest", []):
        print(f"  [{d.get('id')}] {d.get('title')}")
        print(f"    Source: {d.get('source')} | Summary: {d.get('summary')[:90]}...")
