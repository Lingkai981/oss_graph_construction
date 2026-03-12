#!/usr/bin/env python3
"""Check index.json for path issues and optionally fix them."""
import json
from pathlib import Path

INDEX = Path("output/monthly-graphs/index.json")

with open(INDEX) as f:
    idx = json.load(f)

double = 0
single = 0
samples_d = []
samples_s = []
repos_double = set()
repos_single = set()

for repo, months in idx.items():
    for month, types in months.items():
        for gtype, path in types.items():
            if "output/monthly-graphs/output/" in path:
                double += 1
                repos_double.add(repo)
                if len(samples_d) < 3:
                    samples_d.append(path)
            else:
                single += 1
                repos_single.add(repo)
                if len(samples_s) < 3:
                    samples_s.append(path)

print(f"=== Index Path Analysis ===")
print(f"Total repos: {len(idx)}")
print(f"Double-prefix paths: {double}  ({len(repos_double)} repos)")
print(f"Normal paths:        {single}  ({len(repos_single)} repos)")
print()
print(f"Sample double: {samples_d[:2]}")
print(f"Sample normal: {samples_s[:2]}")
print()

# Check if double-prefix files actually exist at the CORRECT path
if samples_d:
    bad = samples_d[0]
    # The actual file should be at the path WITHOUT the extra prefix
    fixed = bad.replace("output/monthly-graphs/output/monthly-graphs/", "output/monthly-graphs/")
    print(f"Bad path:   {bad}")
    print(f"  exists? {Path(bad).exists()}")
    print(f"Fixed path: {fixed}")
    print(f"  exists? {Path(fixed).exists()}")
print()

# Check which repos are affected
print(f"Repos with double-prefix (49 original): {len(repos_double)}")
print(f"Repos with normal paths (24 new):       {len(repos_single)}")

# List the double-prefix repos
print("\nDouble-prefix repos:")
for r in sorted(repos_double):
    print(f"  {r}")
