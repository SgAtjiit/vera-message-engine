import json
import glob

samples = {}
for f in glob.glob("expanded/triggers/*.json"):
    data = json.load(open(f, encoding="utf-8"))
    k = data.get("kind")
    if k not in samples:
        samples[k] = data

for k, d in sorted(samples.items()):
    print(f"=== {k} (scope: {d.get('scope')}) ===")
    print(json.dumps(d.get("payload", {}), indent=2))
