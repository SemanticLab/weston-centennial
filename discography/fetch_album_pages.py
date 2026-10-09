#!/usr/bin/env python3
"""Step 3a - download every release article into the local cache.

Separated from parsing so the parser can be iterated on for free.
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from wiki_common import parse_page

RAW = Path(__file__).resolve().parent / "raw"


def main():
    ents = json.loads((RAW / "entities.json").read_text(encoding="utf-8"))["entities"]
    todo = sorted({v["title"] for v in ents.values() if v["bucket"] == "release"})
    print(f"fetching {len(todo)} release articles (cached after first run)")

    ok = err = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(parse_page, t): t for t in todo}
        for i, f in enumerate(as_completed(futs), 1):
            t = futs[f]
            try:
                d = f.result()
                if d.get("missing"):
                    print(f"  MISSING: {t}")
                    err += 1
                else:
                    ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"  ERROR {t}: {e}")
                err += 1
            if i % 50 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    print(f"done: {ok} fetched, {err} problems")


if __name__ == "__main__":
    sys.exit(main())
