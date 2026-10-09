#!/usr/bin/env python3
"""Package one bundle per WITNESS for the row-level judgement.

The evaluation pass judged blocks. A page shows people: "Benny Powell -- played
trombone in his band for fifteen years -- [quote]". Going from blocks to people
needs three decisions:

  * what is this person's relation to him, really? The upstream relation is
    often `knows of`, often inferred from the interviewer's words, and
    documents found only by text search have no upstream row at all;
  * which of their blocks should lead;
  * the short "how they knew him" phrase.

All three go to one Opus subagent (extract/WITNESS_SPEC.md), which sees
everything one interviewee said about him at once.

A witness = one interview document, other than his own, in which at least one
block was judged to be about him. Unlike the Liston build there is no
interviewer-witness: Willard Jenkins's remarks to Weston are not testimony.

One witness is special. Melba Liston -- his arranger for forty years, and the
subject of the build this was ported from -- is the largest single source. Her
bundle also carries `liston_build`: the record her own-interview readers wrote
for Randy Weston in ~/git/liston-centennial-2026 (liston/her_words.json), who
read her whole transcript rather than windows of it.

Output: weston/witness_input.json
"""

import json
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject as SUBJ  # noqa: E402

ROOT = Path(SUBJ.ROOT)
D = ROOT / SUBJ.KEY
LISTON_REPO = "/Users/m/git/liston-centennial-2026"
LISTON_DOC = "Liston_Melba_Interview_Transcription"


def main():
    enr = json.loads((D / "enriched.json").read_text(encoding="utf-8"))["items"]
    rec = json.loads((D / "recovered_evaluated.json").read_text(encoding="utf-8"))["items"]
    rels = json.loads((D / "relationships.json").read_text(encoding="utf-8"))["items"]
    rel_by_doc = defaultdict(list)
    for r in rels:
        rel_by_doc[r["src"]["doc_id"]].append(r)

    con = sqlite3.connect(f"file:{SUBJ.DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    itv = defaultdict(list)
    for r in con.execute("SELECT doc_id,label,qid,node_key FROM doc_interviewees ORDER BY doc_id,ord"):
        itv[r["doc_id"]].append({"label": r["label"], "qid": r["qid"] or None,
                                 "node_key": r["node_key"]})
    docs = {r["doc_id"]: dict(r) for r in con.execute(
        "SELECT doc_id,collection,title,interviewee,interviewer,year,transcript_url,source_url "
        "FROM documents")}
    wd = {r["qid"]: dict(r) for r in con.execute(
        "SELECT qid,label,description,birth,death FROM wd_people")}
    con.close()

    by_doc = defaultdict(list)
    for i in enr:
        if i["own_interview"] or not i["is_about_subject"]:
            continue
        by_doc[i["doc_id"]].append(i)
    rec_by_doc = defaultdict(list)
    for i in rec:
        if i["is_about_subject"]:
            rec_by_doc[i["doc_id"]].append(i)

    def ctx(turns, n, tail):
        turns = turns[-n:] if tail else turns[:n]
        return [{"block_id": t["block_id"], "speaker": t["speaker"], "text": t["text"]} for t in turns]

    items = []
    for did in sorted(set(by_doc) | set(rec_by_doc)):
        d = docs[did]
        people = [{**p, **{k: (wd.get(p["qid"]) or {}).get(k) for k in ("description", "birth", "death")}}
                  for p in itv.get(did, [])]
        blocks = []
        for i in sorted(by_doc.get(did, []), key=lambda x: (x["page"], x["block"])):
            blocks.append({
                "block_id": i["block_id"], "kind": "mention",
                "speaker": i["speaker"], "speaker_role": i["speaker_role"],
                "mention_kind": i["mention_kind"], "notable": i["notable"],
                "stance": i["stance"], "summary": i["summary"],
                "pull_quote": i["pull_quote"], "notes": i["notes"],
                "context_before": ctx(i["context_before"], 4, True),
                "text": i["text"],
                "context_after": ctx(i["context_after"], 4, False),
            })
        for i in sorted(rec_by_doc.get(did, []), key=lambda x: x["block_id"]):
            blocks.append({
                "block_id": i["block_id"], "kind": "recovered_" + i["source"],
                "speaker": i["speaker"], "speaker_role": None,
                "mention_kind": i["mention_kind"], "notable": i["notable"],
                "stance": i["stance"], "summary": i["summary"],
                "pull_quote": i["pull_quote"], "notes": i["notes"],
                "context_before": [{"block_id": i["anchor"]["block_id"],
                                    "speaker": i["anchor"]["speaker"], "text": i["anchor"]["text"]}],
                "text": i["text"], "context_after": [],
            })
        items.append({
            "witness_key": did,
            "doc": {k: d[k] for k in ("doc_id", "collection", "title", "interviewee", "interviewer", "year")},
            "interviewees": people,
            "upstream_relations": [{"relation": r["relation"], "direction": r["direction"],
                                    "evidence": r["evidence"], "said_by": r["person"]["name"]}
                                   for r in rel_by_doc.get(did, [])],
            "n_blocks": len(blocks),
            "blocks": blocks,
        })

    # Melba Liston: add what the Liston build's readers concluded about Weston
    lp = Path(LISTON_REPO) / "liston" / "her_words.json"
    if lp.exists():
        hw = next((p for p in json.loads(lp.read_text(encoding="utf-8"))["items"]
                   if p.get("qid") == SUBJ.QID), None)
        for it in items:
            if it["witness_key"] == LISTON_DOC and hw:
                it["liston_build"] = {
                    "source": "~/git/liston-centennial-2026/liston/her_words.json",
                    "note": "Judged by readers of her WHOLE interview. her_quote and "
                            "more_her_quotes were verified verbatim there against her own turns. "
                            "A lead: your quotes must still be exact substrings of a block in "
                            "this bundle's blocks[].",
                    **{k: hw.get(k) for k in (
                        "relation", "direction", "basis", "tie", "era", "summary", "one_liner",
                        "her_quote", "her_quote_block_id", "more_her_quotes", "bryant_quote",
                        "stance", "notable", "notes")}}
                # Her best lines about him sit in turns that do not name him (he is
                # "Randy" two turns up, or just "he"), so the mention-based passes
                # never saw them. Add those blocks so they can be quoted here.
                have = {b["block_id"] for b in it["blocks"]}
                quotes = ([{"block_id": hw.get("her_quote_block_id"), "quote": hw.get("her_quote")}]
                          + list(hw.get("more_her_quotes") or []))
                con = sqlite3.connect(f"file:{SUBJ.DB}?mode=ro", uri=True)
                con.row_factory = sqlite3.Row
                seq = [dict(r) for r in con.execute(
                    "SELECT block_id,page,block,speaker,text FROM blocks WHERE doc_id=? "
                    "ORDER BY page,block", (LISTON_DOC,))]
                con.close()
                at = {b["block_id"]: n for n, b in enumerate(seq)}
                ws = __import__("re").compile(r"\s+")
                for q in quotes:
                    bid = q.get("block_id")
                    if not bid or bid in have or bid not in at:
                        continue
                    n = at[bid]
                    text = ws.sub(" ", seq[n]["text"] or "").strip()
                    if q["quote"] not in text:
                        continue
                    shp = lambda b: {"block_id": b["block_id"], "speaker": b["speaker"],
                                     "text": ws.sub(" ", b["text"] or "").strip()}
                    it["blocks"].append({
                        "block_id": bid, "kind": "liston_build_quote",
                        "speaker": seq[n]["speaker"], "speaker_role": "interviewee",
                        "mention_kind": "substantive_comment", "notable": hw.get("notable"),
                        "stance": hw.get("stance"),
                        "summary": "Selected by the Liston build's readers as one of her lines "
                                   "about Weston.",
                        "pull_quote": q["quote"], "notes": "",
                        "page": seq[n]["page"], "block": seq[n]["block"],
                        "context_before": [shp(b) for b in seq[max(0, n - 3):n]],
                        "text": text,
                        "context_after": [shp(b) for b in seq[n + 1:n + 3]],
                    })
                    have.add(bid)
                it["blocks"].sort(key=lambda b: b["block_id"])
                it["n_blocks"] = len(it["blocks"])

    (D / "witness_input.json").write_text(json.dumps(
        {"subject": SUBJ.KEY, "qid": SUBJ.QID, "count": len(items), "items": items},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"witness_input.json: {len(items)} witnesses, "
          f"{sum(i['n_blocks'] for i in items)} blocks, "
          f"{(D / 'witness_input.json').stat().st_size // 1024} KB")
    for i in items:
        print(f"   {i['n_blocks']:3}  {i['witness_key'][:44]:46} "
              f"{', '.join(p['label'] for p in i['interviewees'])[:40]:42} "
              f"upstream={[r['relation'] for r in i['upstream_relations']]}")


if __name__ == "__main__":
    main()
