#!/usr/bin/env python3
"""Package the own-voice pull quotes for the category pass.

Writes weston/category_input.json: every pull quote in own_voice.json -> self,
with the turn it was cut from and the question that set the turn off, and none
of the fields a sorter should not lean on beyond the earlier pass's tags. The
pass itself is extract/CATEGORY_SPEC.md (Opus subagents: one designs the
scheme, two sort independently, one settles what they disagree on); its outputs
land in weston/own_voice_output/category_*.json and are merged back into
own_voice.json by build_own_voice.py. Quotes are keyed by `id`, not block_id:
several come from the same block.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject as SUBJ  # noqa: E402

ROOT = Path(SUBJ.ROOT)
D = ROOT / SUBJ.KEY


def main():
    ov = json.loads((D / "own_voice.json").read_text(encoding="utf-8"))
    own = {b["block_id"]: b for b in
           json.loads((D / "own_interview.json").read_text(encoding="utf-8"))["items"]}
    items = []
    for i in ov["self"]["items"]:
        items.append({
            "id": i["id"],
            "pull_quote": i["pull_quote"],
            "page": i["page"],
            "question": [f'{t["speaker"]}: {t["text"]}' for t in i["exchange"]["question"]],
            "block_text": " ".join(own[b]["text"] for b in i["block_ids"]),
            "summary": i["summary"],
            "prompted_by": i["prompted_by"],
            "period": i["period"],
            "theme": i["theme"],
            "notable": i["notable"],
            "_order": (min(i["block_ids"]), i["offset_in_block"]),
        })
    items.sort(key=lambda e: e.pop("_order"))  # transcript order
    out = {"doc": ov["doc"], "read_this_first": ov["read_this_first"],
           "count": len(items), "items": items}
    (D / "category_input.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"category_input.json  {len(items)} pull quotes")


if __name__ == "__main__":
    main()
