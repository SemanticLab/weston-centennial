#!/usr/bin/env python3
"""Merge the his-words judgement chunks into weston/his_words.json.

his_relationships.json is what the upstream model thought Weston said about the
people in his interview. This is what three Opus subagents, each having read the
whole transcript, judged he actually said (extract/HIS_WORDS_SPEC.md) -- plus
the people the automatic name detection missed (Part D of
extract/OWN_VOICE_SPEC.md).

Nothing a judge wrote is trusted without re-checking it against the transcript:
every quote must be an exact substring of ONE block spoken by the right voice,
with no transcriber's bracket in it, and a quote that fails is dropped (and
counted), never repaired.

DUPLICATES. The transcript spells by ear, so one person turns up under two or
three strings ("Neil Clark" / "Neil Clarke", "Fatu" / "Fatou" / "Fatoumata
Mbengue", "Billy Hopper" / "Billy Harper"). The readers flag these in
`same_person_as`; the flags are resolved here into groups and each group is
folded into one record. The absorbed records are kept under `merged`, each
with the reader's reason, so every merge can be undone. NO_MERGE lists flags
that were looked at and refused.

Outputs
  weston/his_words.json        one record per person, judged, ranked
  shared/his_words_summary.json
"""

import json
import os
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject as SUBJ  # noqa: E402

ROOT = Path(SUBJ.ROOT)
D = ROOT / SUBJ.KEY
NETWORK = "https://thisismattmiller.github.io/linked-jazz-2026-network/#"

RELATIONS = {"in music group with", "collaborated with", "played with", "toured with",
             "played under", "mentor of", "influenced by", "friend of", "acquaintance of",
             "has met", "knows of", "none"}
DIRECTIONS = {"other_leads", "weston_leads", "mutual", "na"}
BASES = {"his_statement", "his_assent", "interviewer_only", "none"}

# same_person_as flags refused after a look: {person_id: reason}
NO_MERGE = {}
# merges the readers did not flag but which are plain from the transcript:
# (absorbed entry's as_named_in_interview, kept entry's as_named_in_interview, reason)
EXTRA_MERGES = [
    ("my father", "Pop",
     "The person layer detected 'Pop' (in the general saying 'Mom and Pop told us some things', "
     "309852) and its reader took the entry to be Weston's father; the Part D reader, finding "
     "the real passages about him ('My father taught me to study African civilization', 309854) "
     "undetected, added him separately. One man. The first name the chunk reader supplied "
     "(Frank Edward Weston) is from outside knowledge -- it is not in the transcript."),
]
# identity_ok=false means one of two things: the Wikidata match is wrong, or the
# match is right but a stray mention of somebody else was folded in. For the
# person_ids listed here the reader said the QID is right for the person the
# record describes, so it is kept; anything else with identity_ok=false loses it.
QID_RIGHT_BUT_FOLD_CONTAMINATED = {
    109397,   # Benny Bailey: right man, but a bare "Benny" (= Benny Powell, 309859 and
              # 309887) was folded into him
}
# The corrected-name rule below matches a label, and a label is not a person.
# person_id -> why the match it would make is refused.
QID_DENY = {
    109450: "'John Williams' conducting the Boston Pops is the film composer; the only John "
            "Williams in the corpus's authority table is a jazz musician (Q15429336).",
}


def nkey(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def main():
    own = json.loads((D / "own_interview.json").read_text(encoding="utf-8"))
    blocks = {b["block_id"]: b for b in own["items"]}
    hr = json.loads((D / "his_relationships.json").read_text(encoding="utf-8"))
    up = {x["person"]["person_id"]: x for x in hr["items"] + hr["skipped"]["items"]}
    weights = hr["relation_weights"]

    dropped = Counter()

    def check(quote, bid, role, what):
        """-> (quote, block) if it verifies, else (None, None)."""
        if not quote:
            return None, None
        b = blocks.get(bid)
        if b is None:
            dropped[f"{what}: block not in interview"] += 1
            return None, None
        if b["speaker_role"] != role:
            dropped[f"{what}: wrong speaker"] += 1
            return None, None
        if quote not in b["text"]:
            dropped[f"{what}: not verbatim"] += 1
            return None, None
        if "[" in quote:
            dropped[f"{what}: contains a transcriber bracket"] += 1
            return None, None
        return quote, b

    def shape(e, u, source):
        hq, hb = check(e.get("his_quote"), e.get("his_quote_block_id"), "subject", "his_quote")
        iq, ib = check(e.get("interviewer_quote"), e.get("interviewer_quote_block_id"),
                       "interviewer", "interviewer_quote")
        more = []
        for m in e.get("more_his_quotes") or []:
            q, b = check(m.get("quote"), m.get("block_id"), "subject", "more_his_quotes")
            if q and q != hq:
                more.append({"block_id": b["block_id"], "quote": q, "page": b["page"],
                             "url": b["transcript_url"]})
        rel = e.get("relation") if e.get("relation") in RELATIONS else "none"
        if rel != e.get("relation"):
            dropped["relation outside vocabulary -> none"] += 1
        dirn = e.get("direction") if e.get("direction") in DIRECTIONS else "na"
        basis = e.get("basis") if e.get("basis") in BASES else "none"
        p = (u or {}).get("person") or {}
        ok = bool(e.get("identity_ok", True))
        qid = p.get("qid") if (ok or e.get("person_id") in QID_RIGHT_BUT_FOLD_CONTAMINATED) else None
        return {
            "person_id": e.get("person_id"),
            "source": source,
            "name": e.get("name") or p.get("name"),
            "as_named_in_interview": p.get("as_named_in_interview") or (e.get("as_in_transcript") or [None])[0],
            "also_named": list(e.get("as_in_transcript") or p.get("surface_forms") or []),
            "transcribed_wrong": bool(e.get("transcribed_wrong")),
            "is_person": bool(e.get("is_person", True)),
            "not_person_kind": e.get("not_person_kind"),
            # ---- identity
            "qid": qid,
            "qid_source": "person_layer" if qid else None,
            "identity_ok": ok,
            "fold_contaminated": (not ok) and qid is not None,
            "identity_note": e.get("identity_note") or "",
            "same_person_as": e.get("same_person_as") or None,
            "upstream_qid": p.get("qid"),
            "description": p.get("description") if qid else (e.get("who_is_this") or None),
            "born": p.get("born") if qid else None,
            "died": p.get("died") if qid else None,
            "wikipedia": p.get("wikipedia") if qid else None,
            "node_keys": (p.get("node_keys") or []) if qid or not p.get("qid") else [],
            "network_url": p.get("network_url") if qid or not p.get("qid") else None,
            # ---- the judgement
            "who_speaks_of_them": e.get("who_speaks_of_them"),
            "basis": basis,
            "relation": rel,
            "relation_weight": weights.get(rel, 0.0),
            "direction": dirn,
            "tie": e.get("tie") or [],
            "instrument_or_role": e.get("instrument_or_role") or "",
            "firsthand": bool(e.get("firsthand")),
            "stance": e.get("stance"),
            "stance_strength": e.get("stance_strength") or 0,
            "era": e.get("era") or "",
            "summary": e.get("summary") or "",
            "one_liner": e.get("one_liner") or "",
            # ---- his words (verified verbatim, right speaker, no transcriber brackets)
            "his_quote": hq,
            "his_quote_block_id": hb["block_id"] if hb else None,
            "his_quote_page": hb["page"] if hb else None,
            "his_quote_url": hb["transcript_url"] if hb else None,
            "interviewer_quote": iq,
            "interviewer_quote_block_id": ib["block_id"] if ib else None,
            "interviewer_quote_url": ib["transcript_url"] if ib else None,
            "more_his_quotes": more,
            "n_his_quotes": (1 if hq else 0) + len(more),
            "topics": e.get("topics") or [],
            "notable": e.get("notable") or 0,
            "is_chunk_top": False,
            "confidence": e.get("confidence"),
            "notes": e.get("notes") or "",
            # ---- provenance
            "n_mentions": p.get("n_mentions") or len(e.get("block_ids") or []),
            "mention_block_ids": p.get("mention_block_ids") or e.get("block_ids") or [],
            "is_interviewer": p.get("qid") == SUBJ.INTERVIEWER["qid"],
            "upstream": {"relation": (u or {}).get("relation"),
                         "direction": (u or {}).get("direction"),
                         "evidence": (u or {}).get("evidence"),
                         "relation_ok": e.get("upstream_relation_ok")} if u else None,
        }

    items, missing, tops = {}, [], set()
    for f in sorted((D / "his_words_input").glob("chunk_*.json")):
        o = D / "his_words_output" / f.name
        if not o.exists():
            missing.append(f.name)
            continue
        want = [i["person_id"] for i in json.loads(f.read_text(encoding="utf-8"))["items"]]
        d = json.loads(o.read_text(encoding="utf-8"))
        got = [i["person_id"] for i in d["items"]]
        if got != want:
            sys.exit(f"FATAL: {o.name} person_id order differs from its input")
        tops.update(d.get("chunk_top") or [])
        for e in d["items"]:
            items[e["person_id"]] = shape(e, up.get(e["person_id"]), "person_layer")
    for pid in tops:
        if pid in items:
            items[pid]["is_chunk_top"] = True

    # ---- people the name detection missed, found by a reader. They get negative
    # ids so that everything downstream can key on person_id.
    mp = D / "own_voice_output" / "missed_people.json"
    n_added = 0
    if mp.exists():
        for n, e in enumerate(json.loads(mp.read_text(encoding="utf-8"))["items"], 1):
            rec = shape({**e, "is_person": True, "identity_ok": True, "person_id": -n},
                        None, "reader_added")
            items[-n] = rec
            n_added += 1

    # ---- duplicates: resolve same_person_as flags into groups (union-find)
    index = {}
    for pid, it in items.items():
        for n in [it["name"], it["as_named_in_interview"], *it["also_named"]]:
            k = nkey(n)
            if k:
                index.setdefault(k, set()).add(pid)
    parent = {pid: pid for pid in items}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    reasons, unresolved_flags = {}, []
    for pid, it in items.items():
        tgt = it["same_person_as"]
        if not tgt or pid in NO_MERGE or not it["is_person"]:
            continue
        hits = index.get(nkey(tgt), set()) - {pid}
        hits = {h for h in hits if items[h]["is_person"]}
        if not hits:
            # the other string is not a separate entry -- it is just another way
            # the transcript names this one ("Lucas" for Lukas Foss)
            if tgt not in it["also_named"]:
                it["also_named"].append(tgt)
            unresolved_flags.append({"person_id": pid, "name": it["as_named_in_interview"],
                                     "same_person_as": tgt,
                                     "resolution": "no separate entry carries that name; added "
                                                   "to also_named"})
            continue
        for h in hits:
            parent[find(pid)] = find(h)
            reasons.setdefault(pid, f"reader flagged '{it['as_named_in_interview']}' as the same "
                                    f"person as '{tgt}'" + (f" -- {it['notes']}" if it["notes"] else ""))
    for src_name, dst_name, why in EXTRA_MERGES:
        src = next((pid for pid, it in items.items() if it["as_named_in_interview"] == src_name), None)
        dst = next((pid for pid, it in items.items() if it["as_named_in_interview"] == dst_name), None)
        if src is not None and dst is not None:
            parent[find(src)] = find(dst)
            reasons[src] = reasons[dst] = why
    # two entries the readers gave the same corrected full name are one person,
    # flagged or not
    by_name = {}
    for pid, it in items.items():
        k = nkey(it["name"])
        if it["is_person"] and len(k.split()) >= 2 and pid not in NO_MERGE:
            by_name.setdefault(k, []).append(pid)
    for k, pids in by_name.items():
        for other in pids[1:]:
            if find(other) != find(pids[0]):
                parent[find(other)] = find(pids[0])
                reasons.setdefault(other, f"two entries were given the same corrected name "
                                          f"'{items[pids[0]]['name']}'")

    groups = {}
    for pid in items:
        groups.setdefault(find(pid), []).append(pid)

    merged = []
    for members in groups.values():
        if len(members) < 2:
            continue
        # keep the entry with a QID, then the most mentions, then the best grade
        members.sort(key=lambda p: (-bool(items[p]["qid"]), -(items[p]["n_mentions"] or 0),
                                    -items[p]["notable"], p < 0, p))
        keep = items[members[0]]
        for src in members[1:]:
            a = items.pop(src)
            keep["also_named"] = sorted((set(keep["also_named"]) | set(a["also_named"])
                                         | {a["as_named_in_interview"]}) - {None})
            keep["mention_block_ids"] = sorted(set(keep["mention_block_ids"]) | set(a["mention_block_ids"]))
            keep["n_mentions"] = (keep["n_mentions"] or 0) + (a["n_mentions"] or 0)
            keep["node_keys"] = sorted(set(keep["node_keys"]) | set(a["node_keys"]))
            keep["transcribed_wrong"] = keep["transcribed_wrong"] or a["transcribed_wrong"]
            have = {keep["his_quote"]} | {m["quote"] for m in keep["more_his_quotes"]}
            extra = ([{"block_id": a["his_quote_block_id"], "quote": a["his_quote"],
                       "page": a["his_quote_page"], "url": a["his_quote_url"]}]
                     if a["his_quote"] else []) + a["more_his_quotes"]
            for m in extra:
                if m["quote"] not in have:
                    keep["more_his_quotes"].append(m)
                    have.add(m["quote"])
            if not keep["his_quote"] and keep["more_his_quotes"]:
                m = keep["more_his_quotes"].pop(0)
                keep.update(his_quote=m["quote"], his_quote_block_id=m["block_id"],
                            his_quote_page=m["page"], his_quote_url=m["url"])
            keep["n_his_quotes"] = (1 if keep["his_quote"] else 0) + len(keep["more_his_quotes"])
            # the absorbed entry may carry the fuller judgement
            if a["relation_weight"] > keep["relation_weight"]:
                for k in ("relation", "relation_weight", "direction", "basis", "tie", "firsthand",
                          "summary", "one_liner", "era", "stance", "stance_strength"):
                    keep[k] = a[k]
            else:
                keep["tie"] = sorted(set(keep["tie"]) | set(a["tie"]))
            for k in ("instrument_or_role", "one_liner", "summary", "era"):
                keep[k] = keep[k] or a[k]
            keep["notable"] = max(keep["notable"], a["notable"])
            keep["is_chunk_top"] = keep["is_chunk_top"] or a["is_chunk_top"]
            keep["notes"] = (keep["notes"] + f" | merged: '{a['as_named_in_interview']}' "
                                              f"(person_id {src})").strip(" |")
            merged.append({"merged_into": members[0], "merged_into_name": keep["name"],
                           "reason": reasons.get(src) or reasons.get(members[0]) or "",
                           "record": a})

    # People with no QID take one only on an exact, unique label match in the
    # corpus's own Wikidata authority table -- never a search. This is what
    # turns a corrected mishearing ("Kenny Durham" -> Kenny Dorham) back into a
    # reconciled person.
    con = sqlite3.connect(f"file:{SUBJ.DB}?mode=ro", uri=True)
    for rec in items.values():
        if rec["qid"] or not rec["is_person"] or len(nkey(rec["name"]).split()) < 2:
            continue
        if rec["person_id"] in QID_DENY:
            rec["identity_note"] = (rec["identity_note"] + " | No QID: "
                                    + QID_DENY[rec["person_id"]]).strip(" |")
            continue
        if rec["transcribed_wrong"] and rec["confidence"] == "low":
            continue        # the reader was guessing at who a garbled name is
        rows = con.execute(
            "SELECT qid, description, birth, death, wp_title FROM wd_people WHERE label = ?",
            (rec["name"],)).fetchall()
        if len(rows) == 1 and (rows[0][1] or rows[0][2]):   # never onto a stub item
            q, desc, b_, d_, wp = rows[0]
            if rec["upstream_qid"] == q and not rec["identity_ok"]:
                continue        # the reader rejected exactly this match
            rec.update(qid=q, qid_source="exact unique label match in wd_people, on the "
                                         "reader's corrected name",
                       born=b_, died=d_, node_keys=[f"wd:{q}"], network_url=NETWORK + f"wd:{q}",
                       wikipedia=("https://en.wikipedia.org/wiki/" + wp.replace(" ", "_")) if wp else None)
            rec["description_from_transcript"] = rec["description"]
            rec["description"] = desc or rec["description"]
    con.close()

    people = list(items.values())
    people.sort(key=lambda x: (not x["is_person"], -x["notable"], -x["relation_weight"],
                               -x["n_his_quotes"], x["name"] or ""))

    real = [p for p in people if p["is_person"]]
    rel_ok = [p["upstream"]["relation_ok"] for p in people
              if p["upstream"] and p["upstream"]["relation_ok"] is not None]
    stats = {
        "entries": len(people),
        "real_people": len(real),
        "not_people": len(people) - len(real),
        "not_people_kinds": dict(Counter(p["not_person_kind"] for p in people if not p["is_person"])),
        "reader_added_people": sum(1 for p in real if p["source"] == "reader_added"),
        "reader_added_before_merging": n_added,
        "merged_duplicates": len(merged),
        "chunks_missing": missing,
        "with_a_relation": sum(1 for p in real if p["relation"] != "none"),
        "by_relation": dict(Counter(p["relation"] for p in real).most_common()),
        "by_basis": dict(Counter(p["basis"] for p in real).most_common()),
        "by_who_speaks": dict(Counter(p["who_speaks_of_them"] for p in real).most_common()),
        "by_notable": dict(sorted(Counter(p["notable"] for p in real).items(), reverse=True)),
        "by_tie": dict(Counter(t for p in real for t in p["tie"]).most_common()),
        "with_his_own_quote": sum(1 for p in real if p["his_quote"]),
        "his_quotes_total": sum(p["n_his_quotes"] for p in real),
        "names_transcribed_wrong": sum(1 for p in real if p["transcribed_wrong"]),
        "reconciled_to_wikidata": sum(1 for p in real if p["qid"]),
        "reconciled_via_corrected_name": sum(1 for p in real if (p["qid_source"] or "").startswith("exact")),
        "identity_rejected": sum(1 for p in real if not p["identity_ok"]),
        "upstream_relation_wrong": rel_ok.count(False),
        "upstream_relation_judged": len(rel_ok),
        "upstream_relation_wrong_pct": round(100 * rel_ok.count(False) / len(rel_ok), 1) if rel_ok else 0,
        "quotes_dropped_on_verification": dict(dropped),
    }

    out = {
        "subject": SUBJ.KEY, "qid": SUBJ.QID,
        "generated_from": "linked_jazz.sqlite + Opus subagent judgement pass "
                          "(extract/HIS_WORDS_SPEC.md, extract/OWN_VOICE_SPEC.md part D)",
        "direction_of_this_file": "FROM Randy Weston TO the person named",
        "count": len(people),
        "doc": {"doc_id": SUBJ.OWN_DOC, "title": own["doc"]["title"], "year": SUBJ.OWN_DOC_YEAR,
                "date": SUBJ.OWN_DOC_DATE, "interviewer": SUBJ.INTERVIEWER["name"],
                "transcript_url": own["doc"]["transcript_url"],
                "source_url": own["doc"]["source_url"]},
        "method": (
            "One record per person named in his 2009 interview. Each of three readers read the "
            "whole transcript and then judged ~38 people: is this a person at all, who is really "
            "meant (the transcript spells by ear), is the Wikidata match right, who actually "
            "speaks of them, what the relation is and what it rests on (basis), and his best "
            "verbatim line about them. Every quote here was re-verified in this script as an "
            "exact substring of one block spoken by the right voice with no transcriber's "
            "bracket in it; failures are dropped and counted in "
            "stats.quotes_dropped_on_verification. source='reader_added' marks people the name "
            "detection missed (negative person_id). Duplicates flagged by the readers are folded "
            "together; the absorbed records are under `merged`. Sorted by notable, then relation "
            "weight."),
        "read_this_first": (
            "`name` is the reader's corrected spelling; the quotes keep the transcript's "
            "(transcribed_wrong=true where they differ: 'Kenny Durham', 'Buddy Boland', 'Paul "
            "Robinson'). basis is the field to filter on: his_statement = he said it; his_assent "
            "= Willard Jenkins said it and Weston agreed (the words are in interviewer_quote); "
            "interviewer_only = Weston did not confirm it. Many entries are one name in a band "
            "roll-call: notable 1, and the quote is the roll-call."),
        "relation_weights": weights,
        "stats": stats,
        "merged": merged,
        "alias_only_flags": unresolved_flags,
        "items": people,
    }
    (D / "his_words.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "shared").mkdir(exist_ok=True)
    (ROOT / "shared" / "his_words_summary.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"his_words.json: {len(people)} entries -- {len(real)} people "
          f"({stats['reader_added_people']} reader-added), {len(people) - len(real)} not people, "
          f"{len(merged)} merged, chunks missing: {missing}")
    print(f"  with a relation: {stats['with_a_relation']}   with his own quote: "
          f"{stats['with_his_own_quote']}   his quotes total: {stats['his_quotes_total']}")
    print(f"  names transcribed wrong: {stats['names_transcribed_wrong']}   with QID: "
          f"{stats['reconciled_to_wikidata']} ({stats['reconciled_via_corrected_name']} via corrected name)")
    print(f"  by basis    {stats['by_basis']}")
    print(f"  by relation {stats['by_relation']}")
    print(f"  by notable  {stats['by_notable']}")
    print(f"  upstream relation wrong: {stats['upstream_relation_wrong']}/"
          f"{stats['upstream_relation_judged']} ({stats['upstream_relation_wrong_pct']}%)")
    print(f"  quotes dropped on verification: {dict(dropped)}")
    for m in merged:
        print(f"  merged {m['record']['as_named_in_interview']!r} -> {m['merged_into_name']!r}")
    for u in unresolved_flags:
        print(f"  alias only: {u['name']!r} also named {u['same_person_as']!r}")
    print("  top:")
    for p in real[:12]:
        print(f"    [{p['notable']}] {p['name'][:26]:28} {p['relation']:20} {p['basis']:18} "
              f"{(p['his_quote'] or '')[:70]!r}")


if __name__ == "__main__":
    main()
