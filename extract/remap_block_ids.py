#!/usr/bin/env python3
"""Carry every stored block id onto a rebuilt corpus database.

The data layer was built against linked_jazz.sqlite as it stood on 2 October
2026 (schema 1, now kept as linked_jazz.pre_audit.sqlite). The per-transcript
audit that produced schema 2.1 (9 October) renumbered blocks.block_id across
the whole corpus, stripped the Hamilton PDFs' page footers out of block text
and resolved the speakers of page-break continuation blocks. It did not move a
block: (doc_id, page, block) is the same key in both, so the join on that key
gives a complete old -> new id map.

This script walks the merged JSON files under weston/ and shared/, rewrites
each block id it finds (the key names below), and refreshes any block `text`
that still carries the old DB's text for that block. Quote strings are not
touched: the verifier (verify_all.py) re-checks each one against the new text
afterwards.

The judges' input and output files (`*_input*`, `*_output*`) are left alone:
they stay in the id space of the DB they were judged against, which is the DB
build_all.sh builds them from (LINKED_JAZZ_DB, see extract/subject.py).

build_all.sh runs it after the pipeline and before verify_all.py:
    uv run python extract/remap_block_ids.py
It refuses to run on files that already carry the new ids."""

import json
import re
import sqlite3
import sys
from pathlib import Path

import subject as SUBJ

ROOT = Path(SUBJ.ROOT)
OLD_DB = "/Users/m/git/ch-jazz-mashup/linked_jazz.pre_audit.sqlite"
NEW_DB = "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite"   # always the current DB, whatever LINKED_JAZZ_DB says
ID_KEYS = {"block_id", "anchor_block_id", "her_quote_block_id", "his_quote_block_id",
           "interviewer_quote_block_id", "lead_block_id", "pull_quote_block_id",
           "second_block_id", "quote_block_id"}
LIST_KEYS = {"block_ids", "context_block_ids", "mention_block_ids", "blocks"}


def load_map():
    old = sqlite3.connect(f"file:{OLD_DB}?mode=ro", uri=True)
    new = sqlite3.connect(f"file:{NEW_DB}?mode=ro", uri=True)
    o = {(d, p, b): (i, t) for i, d, p, b, t in old.execute("select block_id, doc_id, page, block, text from blocks")}
    n = {(d, p, b): (i, t) for i, d, p, b, t in new.execute("select block_id, doc_id, page, block, text from blocks")}
    ids, texts = {}, {}
    for k, (oid, otext) in o.items():
        if k in n:
            ids[oid] = n[k][0]
            texts[oid] = (otext, n[k][1])
    return ids, texts, {v[0] for v in n.values()}


def already_remapped():
    """Old and new ids share one number range, so the only safe guard is a
    known block: his own interview's blocks must still carry old ids."""
    new = sqlite3.connect(f"file:{NEW_DB}?mode=ro", uri=True)
    items = json.loads((ROOT / SUBJ.KEY / "own_interview.json").read_text(encoding="utf-8"))["items"]
    hits = 0
    for b in items:
        r = new.execute("select doc_id, page, block from blocks where block_id=?", (b["block_id"],)).fetchone()
        if r and r == (SUBJ.OWN_DOC, b["page"], b["block"]):
            hits += 1
    return hits == len(items)


def main():
    if already_remapped():
        sys.exit("the files already carry the new DB's block ids; nothing to do")
    ids, texts, new_ids = load_map()
    files = sorted(f for f in list((ROOT / SUBJ.KEY).rglob("*.json")) + list((ROOT / "shared").glob("*.json"))
                   if not re.search(r"_(input|output)", str(f.relative_to(ROOT))))
    stats = {"files": 0, "ids": 0, "texts": 0}
    unknown = []

    def remap_id(v, where):
        if v is None:
            return v
        if v in ids:
            stats["ids"] += 1
            return ids[v]
        unknown.append((where, v))
        return v

    def walk(x, where):
        if isinstance(x, dict):
            old_id = x.get("block_id")
            for k, v in list(x.items()):
                if k in ID_KEYS and isinstance(v, int):
                    x[k] = remap_id(v, f"{where}/{k}")
                elif k in LIST_KEYS and isinstance(v, list) and all(isinstance(e, int) for e in v):
                    x[k] = [remap_id(e, f"{where}/{k}") for e in v]
                else:
                    walk(v, f"{where}/{k}")
            # a block record carrying the old DB's text gets the new DB's
            if isinstance(old_id, int) and old_id in texts and isinstance(x.get("text"), str):
                otext, ntext = texts[old_id]
                if x["text"] == otext and otext != ntext:
                    x["text"] = ntext
                    stats["texts"] += 1
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{where}[{i}]")

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        before = stats["ids"]
        walk(data, str(f.relative_to(ROOT)))
        if stats["ids"] > before:
            f.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            stats["files"] += 1

    print(f"remapped {stats['ids']} block ids in {stats['files']} files; refreshed {stats['texts']} block texts")
    if unknown:
        print(f"  !! {len(unknown)} ids not in the old DB, e.g. {unknown[:5]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
