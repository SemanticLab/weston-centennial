#!/usr/bin/env python3
"""Nickname / alias sweep for the Randy Weston centennial extraction.

(Ported from the Coltrane / Davis build, where it hunted "Trane" and "Prince of
Darkness". Weston had no stage nickname, so here it is a recall audit: every
block whose text says Weston (or the transcriber's "Randy Western"), with
whether the person layer already attributes it to him. A bare "Randy" is not
swept corpus-wide -- it is Brecker, Brooks, Newman and a dozen New Orleans
bandleaders -- only inside interviews already tied to him, by
extract/subject.py, which promotes the genuine misses into the evaluation
pass.)

The person layer (persons.qid) is the authoritative identity resolution; this
script is the *complement* to it. It runs raw FTS over the corpus for the
nicknames the alias resolver may not have folded in ("Trane", "Prince of
Darkness", "The Sorcerer") and reports which hits the person layer already
covers and which it does not.

Everything emitted here that is NOT backed by a persons.qid row is UNVERIFIED —
the flag `verified` says which is which. See extract/SPEC.md.
"""

import json
import re
import sqlite3
from pathlib import Path

import os
DB = os.environ.get("LINKED_JAZZ_DB", "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite")  # see extract/subject.py
OUT = Path("/Users/m/git/weston-centennial")

SUBJECTS = {
    "weston": {
        "qid": "Q1371187",
        "label": "Randy Weston",
        # (display name, FTS query, regex to confirm the hit in the raw text)
        # He had no stage nickname; this sweep is a recall check on the person
        # layer, which is why the bare surname is here.
        "nicknames": [
            ("Randy Weston", '"randy weston"', r"\bRandy\s+\[?Weston\b"),
            ("Weston", "Weston", r"\bWeston\b"),
            ("Randy Western", '"randy western"', r"\bRandy\s+Western\b"),
            ("Randolph Weston", '"randolph weston"', r"\bRandolph\s+Weston\b"),
        ],
    },
}

COLLAPSE = re.compile(r"\s+")


def collapse(s):
    return COLLAPSE.sub(" ", s).strip() if s else s


def deep_link(url, page, block):
    if not url:
        return None
    return f"{url}#b{page}-{block}"


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    for key, subj in SUBJECTS.items():
        qid = subj["qid"]

        # block_ids the authoritative person layer already attributes to this QID
        covered = {
            r[0]
            for r in con.execute(
                """SELECT DISTINCT pm.block_id
                     FROM persons p JOIN person_mentions pm USING(person_id)
                    WHERE p.qid = ? AND pm.block_id IS NOT NULL""",
                (qid,),
            )
        }

        items, per_nick = [], []
        seen = set()

        for display, query, pattern in subj["nicknames"]:
            rx = re.compile(pattern, re.IGNORECASE)
            rows = con.execute(
                """SELECT b.block_id, b.doc_id, b.page, b.block, b.speaker, b.text,
                          d.collection, d.title, d.interviewee, d.interviewer, d.year,
                          d.transcript_url, d.source_url
                     FROM blocks_fts f
                     JOIN blocks b    ON b.block_id = f.rowid
                     JOIN documents d ON d.doc_id  = b.doc_id
                    WHERE blocks_fts MATCH ?""",
                (query,),
            ).fetchall()

            hits = [r for r in rows if rx.search(r["text"] or "")]
            n_cov = sum(1 for r in hits if r["block_id"] in covered)
            per_nick.append(
                {
                    "nickname": display,
                    "fts_query": query,
                    "regex": pattern,
                    "fts_blocks": len(rows),
                    "regex_confirmed_blocks": len(hits),
                    "already_in_person_layer": n_cov,
                    "not_in_person_layer": len(hits) - n_cov,
                }
            )

            for r in hits:
                dedupe_key = (r["block_id"], display)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                spans = [
                    {"start": m.start(), "end": m.end(), "surface": m.group(0)}
                    for m in rx.finditer(r["text"] or "")
                ]
                items.append(
                    {
                        "nickname": display,
                        "verified": r["block_id"] in covered,
                        "n_hits_in_block": len(spans),
                        "spans": spans,
                        "speaker": r["speaker"],
                        "text": collapse(r["text"]),
                        "text_raw": r["text"],
                        "src": {
                            "doc_id": r["doc_id"],
                            "block_id": r["block_id"],
                            "page": r["page"],
                            "block": r["block"],
                            "collection": r["collection"],
                            "title": r["title"],
                            "interviewee": r["interviewee"],
                            "interviewer": r["interviewer"],
                            "year": r["year"],
                            "transcript_url": deep_link(
                                r["transcript_url"], r["page"], r["block"]
                            ),
                            "source_url": r["source_url"],
                        },
                    }
                )

        # unverified first (those are the interesting ones), then by nickname rarity
        rarity = {p["nickname"]: p["regex_confirmed_blocks"] for p in per_nick}
        items.sort(key=lambda i: (i["verified"], rarity[i["nickname"]], i["src"]["doc_id"]))

        out = {
            "subject": key,
            "qid": qid,
            "label": subj["label"],
            "generated_from": "linked_jazz.sqlite",
            "count": len(items),
            "method": (
                "FTS5 match on blocks_fts, then a case-insensitive regex re-check against "
                "blocks.text to drop tokenizer false positives. `verified` is true when the "
                "block is already attributed to this QID by the authoritative person layer "
                "(persons.qid -> person_mentions.block_id); verified=false hits are candidate "
                "mentions the alias resolver did not fold in and are UNVERIFIED — they may "
                "refer to someone or something else entirely (e.g. 'miles' the distance)."
            ),
            "person_layer_blocks": len(covered),
            "by_nickname": per_nick,
            "items": items,
        }

        path = OUT / key / "nicknames.json"
        path.write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"{key}: {len(items)} blocks -> {path} ({path.stat().st_size/1024:.0f} KB)")
        for p in per_nick:
            print(
                f"   {p['nickname']:<20} fts={p['fts_blocks']:<5} confirmed="
                f"{p['regex_confirmed_blocks']:<5} covered={p['already_in_person_layer']:<5} "
                f"new={p['not_in_person_layer']}"
            )

    con.close()


if __name__ == "__main__":
    main()
