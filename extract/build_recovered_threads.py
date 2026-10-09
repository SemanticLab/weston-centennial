#!/usr/bin/env python3
"""Package the recovered blocks for judgement.

build_answers.py and build_continuations.py find blocks that FOLLOW a mention of
Weston but do not name him -- answers to a question about him, and "he ..."
continuations. In the Coltrane / Davis build five in six of those turned out to
be about somebody else (in the Liston build, 17 of 22), so nothing here is
usable until it has been read.

That build sent each thread to Gemini (classify_recovered_gemini.py). Here the
whole set is a few dozen blocks, so it goes to a single Opus subagent working to
extract/RECOVERED_SPEC.md, which gets something Gemini did not: the surrounding
transcript on both sides of every thread, so it can find where the pronoun's
antecedent actually is.

Output: weston/recovered_input.json
Then:   the subagent writes weston/recovered_output.json
Then:   extract/merge_recovered.py
"""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject as SUBJ  # noqa: E402

ROOT = Path(SUBJ.ROOT)
BEFORE, AFTER = 6, 3
WS = re.compile(r"\s+")


def collapse(s):
    return WS.sub(" ", s).strip() if s else ""


def main():
    con = sqlite3.connect(f"file:{SUBJ.DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    docs = {}

    def doc_blocks(did):
        if did not in docs:
            docs[did] = [dict(r) for r in con.execute(
                "SELECT block_id,page,block,type,speaker,text FROM blocks WHERE doc_id=? "
                "ORDER BY page,block", (did,))]
        return docs[did]

    def shape(b):
        return {"block_id": b["block_id"], "speaker": b["speaker"] or None,
                "type": b["type"], "text": collapse(b["text"])}

    threads = []
    for fname, kind, akey, bkey, label in (
        ("recovered_answers.json", "answer", "question", "answers",
         "the interviewer's question that named him"),
        ("recovered_continuations.json", "continuation", "anchor", "continuations",
         "the preceding block, which DID name him"),
    ):
        for it in json.loads((ROOT / SUBJ.KEY / fname).read_text(encoding="utf-8"))["items"]:
            a, blocks = it[akey], it[bkey]
            bl = doc_blocks(it["src"]["doc_id"])
            idx = {b["block_id"]: i for i, b in enumerate(bl)}
            lo = idx[a["block_id"]]
            hi = max(idx[b["block_id"]] for b in blocks)
            judged = {b["block_id"] for b in blocks}
            threads.append({
                "key": f"{SUBJ.KEY}:{kind}:{a['block_id']}",
                "kind": kind,
                "anchor_is": label,
                "doc": {k: it["src"].get(k) for k in
                        ("doc_id", "title", "collection", "year", "interviewee", "interviewer")},
                "context_before_anchor": [shape(b) for b in bl[max(0, lo - BEFORE):lo]],
                "anchor": {"block_id": a["block_id"], "speaker": a.get("speaker"),
                           "text": a["text"]},
                # everything from the anchor to the last judged block, in order, so
                # stepped-over interjections are visible too
                "thread": [{**shape(b), "judge_this": b["block_id"] in judged}
                           for b in bl[lo + 1:hi + 1]],
                "context_after": [shape(b) for b in bl[hi + 1:hi + 1 + AFTER]],
                "blocks_to_judge": [
                    {"block_id": b["block_id"], "speaker": b.get("speaker") or None,
                     "text": b["text"], "competing_names": b.get("competing_names", [])}
                    for b in blocks],
            })

    n = sum(len(t["blocks_to_judge"]) for t in threads)
    (ROOT / SUBJ.KEY / "recovered_input.json").write_text(json.dumps(
        {"subject": SUBJ.KEY, "qid": SUBJ.QID, "threads": len(threads), "blocks": n,
         "items": threads}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"recovered_input.json: {len(threads)} threads, {n} blocks to judge")


if __name__ == "__main__":
    main()
