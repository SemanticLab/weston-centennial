#!/usr/bin/env python3
"""Compare the two independent category sorts and package what they disagree on.

Reads weston/own_voice_output/category_a.json and category_b.json (Pass B of
extract/CATEGORY_SPEC.md, two Opus subagents working alone from the scheme).
Checks both are complete and use only scheme keys, then writes
weston/own_voice_output/category_disagreements.json for Pass C.
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject as SUBJ  # noqa: E402

ROOT = Path(SUBJ.ROOT)
D = ROOT / SUBJ.KEY
OUT = D / "own_voice_output"


def load_sort(name, keys, ids):
    raw = json.loads((OUT / name).read_text(encoding="utf-8"))
    by = {}
    bad = []
    for e in raw["items"]:
        if e.get("id") not in ids:
            bad.append(f"unknown id {e.get('id')}")
        elif e["id"] in by:
            bad.append(f"duplicate {e['id']}")
        elif e.get("category") not in keys:
            bad.append(f"{e['id']}: category {e.get('category')!r} not in scheme")
        else:
            if e.get("secondary") not in keys or e.get("secondary") == e["category"]:
                e["secondary"] = None
            by[e["id"]] = e
    for i in sorted(ids - set(by)):
        bad.append(f"missing {i}")
    if bad:
        sys.exit(f"{name}: " + "; ".join(bad[:20]))
    return by, raw.get("scheme_problems") or []


def main():
    scheme = json.loads((OUT / "category_scheme.json").read_text(encoding="utf-8"))
    keys = {c["key"] for c in scheme["categories"]}
    inp = {i["id"]: i for i in
           json.loads((D / "category_input.json").read_text(encoding="utf-8"))["items"]}
    a, pa = load_sort("category_a.json", keys, set(inp))
    b, pb = load_sort("category_b.json", keys, set(inp))

    dis = []
    pairs = Counter()
    for bid in sorted(inp):
        x, y = a[bid], b[bid]
        if x["category"] == y["category"]:
            continue
        pairs[tuple(sorted((x["category"], y["category"])))] += 1
        dis.append({
            "id": bid, "pull_quote": inp[bid]["pull_quote"],
            "a": {k: x.get(k) for k in ("category", "secondary", "confidence", "reason")},
            "b": {k: y.get(k) for k in ("category", "secondary", "confidence", "reason")},
        })
    out = {
        "count": len(dis), "of": len(inp),
        "by_pair": [{"pair": list(p), "n": n} for p, n in pairs.most_common()],
        "scheme_problems": {"a": pa, "b": pb},
        "items": dis,
    }
    (OUT / "category_disagreements.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    agree = len(inp) - len(dis)
    print(f"category sorts agree on {agree} of {len(inp)} ({agree / len(inp):.0%}); "
          f"{len(dis)} to adjudicate")
    for p, n in pairs.most_common(8):
        print(f"  {n:3d}  {p[0]} / {p[1]}")
    # second-guess: where a reader's secondary is the other reader's primary
    soft = sum(1 for d in dis if d["a"]["secondary"] == d["b"]["category"]
               or d["b"]["secondary"] == d["a"]["category"])
    print(f"  {soft} of those are primary/secondary swaps")


if __name__ == "__main__":
    main()
