#!/usr/bin/env python3
"""Fix index.json: normalize all paths to absolute."""
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "output" / "monthly-graphs" / "index.json"

with open(INDEX) as f:
    idx = json.load(f)

fixed = 0
total = 0
for repo, months in idx.items():
    for month, types in months.items():
        for gtype, path in types.items():
            total += 1
            if not os.path.isabs(path):
                abs_path = str((ROOT / path).resolve())
                types[gtype] = abs_path
                fixed += 1

with open(INDEX, "w") as f:
    json.dump(idx, f, indent=2, ensure_ascii=False)

print(f"Total paths: {total}")
print(f"Fixed (relative → absolute): {fixed}")
print(f"Already absolute: {total - fixed}")

# Verify
sample_old = None
sample_new = None
for repo, months in idx.items():
    for month, types in months.items():
        for gtype, path in types.items():
            exists = Path(path).exists()
            if sample_old is None:
                sample_old = (repo, path[:90], exists)
            elif sample_new is None and repo != sample_old[0]:
                sample_new = (repo, path[:90], exists)
            break
        break
print(f"\nSample 1: {sample_old}")
print(f"Sample 2: {sample_new}")
