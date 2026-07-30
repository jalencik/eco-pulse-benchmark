"""Render manuscript templates by substituting verified figures from numbers.json.

An unresolved {{placeholder}} is a HARD FAILURE, not a silent pass-through. A template that
prints "{{taskn_cams_rmse}}" into a PDF is worse than one that refuses to build.
"""
from __future__ import annotations
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEC = ROOT/"paper"/"sections"
nums = json.loads((ROOT/"paper"/"numbers.json").read_text(encoding="utf-8"))
PLACEHOLDER = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")

unresolved, rendered = [], []
for tmpl in sorted(SEC.glob("*.md.tmpl")):
    text = tmpl.read_text(encoding="utf-8")
    missing = sorted({k for k in PLACEHOLDER.findall(text) if k not in nums})
    if missing:
        unresolved.append((tmpl.name, missing)); continue
    out = PLACEHOLDER.sub(lambda m: nums[m.group(1)], text)
    dest = SEC/tmpl.name.replace(".md.tmpl", ".md")
    dest.write_text(out, encoding="utf-8")
    used = len(set(PLACEHOLDER.findall(text)))
    rendered.append((dest.name, used))

for name, used in rendered:
    print(f"  rendered {name}  ({used} verified figures substituted)")
if unresolved:
    print("\nFAILED -- unresolved placeholders:")
    for name, keys in unresolved:
        print(f"  {name}: {keys}")
    sys.exit(1)
print(f"\nall templates rendered from {len(nums)} banked figures")
