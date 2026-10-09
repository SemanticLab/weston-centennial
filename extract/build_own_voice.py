#!/usr/bin/env python3
"""Merge the own-voice reading passes into weston/own_voice.json.

Four things only his own interview can give:

  self      Weston on himself -- his life, music and beliefs in his own words
  timeline  the facts about his life the transcript itself states, in order
  records   every recording, composition and film he discusses, with what he
            says each one was for
  journeys  the concerts, ceremonies and travels he recounts ("we don't do
            gigs, we have adventures"), each with a place

`records` and `journeys` are new in this build. The Liston interview this
pipeline was ported from was a life story told in short answers; this one is a
sequel to an earlier oral history, organised by its interviewer as a walk
through the records made since, and by Weston as a string of journeys. The
Liston build's third layer -- the interviewer's own testimony about the
subject -- has no counterpart: Willard Jenkins is not a witness.

All selected by Opus subagents working to extract/OWN_VOICE_SPEC.md after
reading the whole transcript. Every quote is re-verified here: an exact
substring of ONE block, spoken by Weston, with no transcriber's bracket in it.
A quote that fails is dropped and counted, never repaired.

Each self item also gets the exchange it sits in (the turns around it), so a
page can show Jenkins's question above Weston's answer without fetching the
transcript.
"""

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject as SUBJ  # noqa: E402

ROOT = Path(SUBJ.ROOT)
D = ROOT / SUBJ.KEY
THEMES = ["ancestors", "africa", "gnawa_morocco", "the_blues", "spirit_of_music", "family",
          "brooklyn", "the_masters", "the_piano", "melba_liston", "records", "the_band",
          "journeys", "machines_and_human_contact", "race_and_history", "recognition",
          "character"]
LENGTHS = {"line", "passage", "story"}
RECORD_KINDS = {"album", "live_album", "composition", "session", "film", "dvd"}
JOURNEY_KINDS = {"concert", "festival", "residency", "ceremony", "journey", "film_shoot", "home"}


def load_categories():
    """The category pass (extract/CATEGORY_SPEC.md): one scheme, two independent
    sorts, and an adjudication of the quotes the two sorts disagree on. Returns
    (scheme, {quote id: assignment}); empty when the pass has not been run."""
    o = D / "own_voice_output"
    need = [o / n for n in ("category_scheme.json", "category_a.json", "category_b.json")]
    if not all(p.exists() for p in need):
        return None, {}
    scheme, a, b = (json.loads(p.read_text(encoding="utf-8")) for p in need)
    keys = {c["key"] for c in scheme["categories"]}
    adj_p = o / "category_adjudicated.json"
    adj = {e["id"]: e for e in json.loads(adj_p.read_text(encoding="utf-8"))["items"]} \
        if adj_p.exists() else {}
    a = {e["id"]: e for e in a["items"]}
    b = {e["id"]: e for e in b["items"]}

    def sec(e, primary):
        s = e.get("secondary")
        return s if s in keys and s != primary else None

    out = {}
    for qid in a.keys() & b.keys():
        x, y = a[qid], b[qid]
        if qid in adj and adj[qid].get("category") in keys:
            # Pass C: a disagreement settled, or an agreed answer overruled
            e = adj[qid]
            out[qid] = {"category": e["category"], "secondary": sec(e, e["category"]),
                        "agreed": x["category"] == y["category"] == e["category"],
                        "reason": e.get("reason") or ""}
        elif x["category"] == y["category"] and x["category"] in keys:
            # a secondary stands only when both readers named the same one
            s = sec(x, x["category"])
            out[qid] = {"category": x["category"],
                        "secondary": s if s == sec(y, y["category"]) else None,
                        "agreed": True, "reason": ""}
    return scheme, out


def main():
    own = json.loads((D / "own_interview.json").read_text(encoding="utf-8"))
    order = own["items"]
    pos = {b["block_id"]: n for n, b in enumerate(order)}
    dropped = Counter()

    def verify(quote, bid, role, what):
        if not quote or bid not in pos:
            dropped[f"{what}: missing"] += 1
            return None
        b = order[pos[bid]]
        if b["speaker_role"] != role:
            dropped[f"{what}: wrong speaker"] += 1
            return None
        if quote not in b["text"]:
            dropped[f"{what}: not verbatim"] += 1
            return None
        if "[" in quote:
            dropped[f"{what}: contains a transcriber bracket"] += 1
            return None
        return b

    def turn(b):
        return {"block_id": b["block_id"], "page": b["page"], "speaker": b["speaker_effective"],
                "role": b["speaker_role"], "inherited": b["speaker_inherited"], "text": b["text"]}

    def exchange(bid):
        """The question that set the turn off. His turns run across page breaks, so
        walk back over his own continuation blocks to the interviewer's turn."""
        n = pos[bid]
        k = n - 1
        own_before = []
        while k >= 0 and order[k]["speaker_role"] == "subject":
            own_before.append(order[k])
            k -= 1
        q = order[k] if k >= 0 and order[k]["speaker_role"] == "interviewer" else None
        # a question split over a page break
        qs = []
        while q is not None:
            qs.append(q)
            k -= 1
            q = order[k] if k >= 0 and order[k]["speaker_role"] == "interviewer" else None
        return {"question": [turn(x) for x in reversed(qs)],
                "earlier_in_same_answer": [x["block_id"] for x in reversed(own_before)]}

    def more_quotes(lst, what):
        out = []
        for m in lst or []:
            b = verify(m.get("quote"), m.get("block_id"), "subject", what)
            if b is not None:
                out.append({"block_id": b["block_id"], "page": b["page"], "quote": m["quote"],
                            "url": b["transcript_url"]})
        return out

    def people(lst):
        return [{"as_transcribed": p.get("as_transcribed") or "", "name": p.get("name") or "",
                 "role": p.get("role") or ""} for p in lst or [] if p.get("name") or p.get("as_transcribed")]

    # ---------------- self
    raw = json.loads((D / "own_voice_output" / "self.json").read_text(encoding="utf-8"))
    top = raw.get("top") or []
    self_items, seen_ids, spans = [], set(), {}
    for e in raw["items"]:
        b = verify(e.get("pull_quote"), e.get("block_id"), "subject", "self")
        if b is None:
            continue
        qid = e.get("id")
        if not qid or qid in seen_ids:
            dropped["self: missing or duplicate id"] += 1
            continue
        s = b["text"].index(e["pull_quote"])
        span = (s, s + len(e["pull_quote"]))
        if any(s0 < span[1] and e0 > span[0] for s0, e0 in spans.get(b["block_id"], [])):
            dropped["self: overlaps another quote from the same block"] += 1
            continue
        spans.setdefault(b["block_id"], []).append(span)
        seen_ids.add(qid)
        self_items.append({
            "id": qid,
            "block_id": b["block_id"], "page": b["page"], "block": b["block"],
            "pull_quote": e["pull_quote"],
            "chars": len(e["pull_quote"]),
            "offset_in_block": s,
            "length": e.get("length") if e.get("length") in LENGTHS else None,
            "theme": [t for t in (e.get("theme") or []) if t in THEMES],
            "period": e.get("period") or "",
            "summary": e.get("summary") or "",
            "prompted_by": e.get("prompted_by") or "",
            "stands_alone": bool(e.get("stands_alone")),
            "context_block_ids": [c for c in (e.get("context_block_ids") or []) if c in pos],
            "stance": e.get("stance"),
            "notable": e.get("notable") or 0,
            "is_top": qid in top,
            "top_rank": top.index(qid) + 1 if qid in top else None,
            "contains_laughs_marker": "(Laughs)" in e["pull_quote"],
            "whole_block": e["pull_quote"].strip() == b["text"].strip(),
            "spans_page_break": False,
            "block_ids": [b["block_id"]],
            "notes": e.get("notes") or "",
            "exchange": exchange(b["block_id"]),
            "url": b["transcript_url"],
        })

    # ---- quotes that run across a page break. The PDF's pages cut his sentences
    # in two ("...the spirit / came and said to me"), and a block is a page's worth
    # of a turn, so the one-block rule cannot hold these. Each is verified against
    # the two blocks joined with a single space, must really cross the join, and
    # must not overlap a single-block quote on either side.
    jpath = D / "own_voice_output" / "self_joined.json"
    n_joined = 0
    if jpath.exists():
        for e in json.loads(jpath.read_text(encoding="utf-8"))["items"]:
            bids, q, qid = e.get("block_ids") or [], e.get("pull_quote"), e.get("id")
            if len(bids) != 2 or not all(x in pos for x in bids) or not q or not qid or qid in seen_ids:
                dropped["joined: malformed"] += 1
                continue
            a, b = order[pos[bids[0]]], order[pos[bids[1]]]
            if (pos[bids[1]] != pos[bids[0]] + 1 or a["speaker_role"] != "subject"
                    or b["speaker_role"] != "subject" or not b["speaker_inherited"]):
                dropped["joined: not a subject turn continued across a page break"] += 1
                continue
            joined = a["text"] + " " + b["text"]
            if q not in joined or "[" in q:
                dropped["joined: not verbatim"] += 1
                continue
            s0 = joined.index(q)
            e0 = s0 + len(q)
            if not (s0 < len(a["text"]) and e0 > len(a["text"]) + 1):
                dropped["joined: does not cross the page break"] += 1
                continue
            sa = (s0, len(a["text"]))
            sb = (0, e0 - len(a["text"]) - 1)
            if any(x0 < sa[1] and x1 > sa[0] for x0, x1 in spans.get(a["block_id"], [])) or \
               any(x0 < sb[1] and x1 > sb[0] for x0, x1 in spans.get(b["block_id"], [])):
                dropped["joined: overlaps a single-block quote"] += 1
                continue
            spans.setdefault(a["block_id"], []).append(sa)
            spans.setdefault(b["block_id"], []).append(sb)
            seen_ids.add(qid)
            n_joined += 1
            self_items.append({
                "id": qid,
                "block_id": a["block_id"], "page": a["page"], "block": a["block"],
                "pull_quote": q, "chars": len(q), "offset_in_block": s0,
                "length": e.get("length") if e.get("length") in LENGTHS else None,
                "theme": [t for t in (e.get("theme") or []) if t in THEMES],
                "period": e.get("period") or "", "summary": e.get("summary") or "",
                "prompted_by": e.get("prompted_by") or "",
                "stands_alone": bool(e.get("stands_alone")),
                "context_block_ids": [c for c in (e.get("context_block_ids") or []) if c in pos],
                "stance": e.get("stance"), "notable": e.get("notable") or 0,
                "is_top": False, "top_rank": None,
                "contains_laughs_marker": "(Laughs)" in q, "whole_block": False,
                "spans_page_break": True, "block_ids": [a["block_id"], b["block_id"]],
                "page_break_after_chars": len(a["text"]) - s0,
                "notes": e.get("notes") or "",
                "exchange": exchange(a["block_id"]),
                "url": a["transcript_url"],
            })
    self_items.sort(key=lambda i: (-i["notable"], i["top_rank"] or 99, i["block_id"], i["offset_in_block"]))

    # ---------------- categories: the page section each pull quote sits in
    scheme, cats = load_categories()
    uncategorised = 0
    for i in self_items:
        c = cats.get(i["id"])
        if scheme and not c:
            uncategorised += 1
        i["category"] = c["category"] if c else None
        i["category_secondary"] = c["secondary"] if c else None
        i["category_agreed"] = c["agreed"] if c else None
        i["category_note"] = c["reason"] if c else ""
    categories = []
    for n, c in enumerate((scheme or {}).get("categories") or []):
        categories.append({
            "key": c["key"], "label": c["label"], "order": n + 1, "definition": c["definition"],
            "count": sum(1 for i in self_items if i["category"] == c["key"]),
            "notable_2plus": sum(1 for i in self_items
                                 if i["category"] == c["key"] and i["notable"] >= 2),
        })

    # ---------------- timeline
    tl = []
    for n, e in enumerate(raw.get("timeline") or []):
        bids = [x for x in (e.get("block_ids") or []) if x in pos]
        tl.append({
            "order": n + 1, "when": e.get("when") or "", "sort_year": e.get("sort_year"),
            "event": e.get("event") or "", "place": e.get("place") or "",
            "stated_by": e.get("stated_by"),
            "confirmed_by_weston": bool(e.get("confirmed_by_weston")),
            "block_ids": bids,
            "url": order[pos[bids[0]]]["transcript_url"] if bids else None,
            "notes": e.get("notes") or "",
        })
    tl.sort(key=lambda i: (i["sort_year"] is None, i["sort_year"] or 0, i["order"]))

    # ---------------- records
    recs = []
    rp = D / "own_voice_output" / "records.json"
    if rp.exists():
        for n, e in enumerate(json.loads(rp.read_text(encoding="utf-8"))["items"]):
            pq, pb = e.get("pull_quote"), None
            if pq:
                pb = verify(pq, e.get("pull_quote_block_id"), "subject", "records")
                if pb is None:
                    pq = None
            bids = [x for x in (e.get("block_ids") or []) if x in pos]
            recs.append({
                "key": e.get("key"), "order": n + 1,
                "title": e.get("title") or e.get("title_as_transcribed"),
                "title_as_transcribed": e.get("title_as_transcribed") or "",
                "kind": e.get("kind") if e.get("kind") in RECORD_KINDS else None,
                "year": e.get("year"), "year_as_stated": e.get("year_as_stated") or "",
                "label_as_stated": e.get("label_as_stated") or "",
                "raised_by": e.get("raised_by"),
                "part_of": e.get("part_of"),
                "what_he_says": e.get("what_he_says") or "",
                "title_meaning": e.get("title_meaning") or "",
                "pull_quote": pq,
                "pull_quote_block_id": pb["block_id"] if pb else None,
                "pull_quote_url": pb["transcript_url"] if pb else None,
                "more_quotes": more_quotes(e.get("more_quotes"), "records.more"),
                "personnel_as_stated": people(e.get("personnel_as_stated")),
                "pieces_named": e.get("pieces_named") or [],
                "discrepancies": e.get("discrepancies") or "",
                "notable": e.get("notable") or 0,
                "block_ids": bids,
                "url": order[pos[bids[0]]]["transcript_url"] if bids else None,
                "notes": e.get("notes") or "",
            })

    # ---------------- journeys
    jrn, jtop = [], []
    jp = D / "own_voice_output" / "journeys.json"
    if jp.exists():
        rawj = json.loads(jp.read_text(encoding="utf-8"))
        jtop = rawj.get("top") or []
        rec_keys = {r["key"] for r in recs}
        for n, e in enumerate(rawj["items"]):
            pq, pb = e.get("pull_quote"), None
            if pq:
                pb = verify(pq, e.get("pull_quote_block_id"), "subject", "journeys")
                if pb is None:
                    pq = None
            bids = [x for x in (e.get("block_ids") or []) if x in pos]
            jrn.append({
                "key": e.get("key"), "order": n + 1,
                "title": e.get("title") or "",
                "kind": e.get("kind") if e.get("kind") in JOURNEY_KINDS else None,
                "place": e.get("place") or "", "country": e.get("country") or "",
                "place_as_transcribed": e.get("place_as_transcribed") or "",
                "year": e.get("year"), "when_as_stated": e.get("when_as_stated") or "",
                "what_happened": e.get("what_happened") or "",
                "who_was_there": people(e.get("who_was_there")),
                "pull_quote": pq,
                "pull_quote_block_id": pb["block_id"] if pb else None,
                "pull_quote_url": pb["transcript_url"] if pb else None,
                "more_quotes": more_quotes(e.get("more_quotes"), "journeys.more"),
                "related_record_key": e.get("related_record_key")
                if e.get("related_record_key") in rec_keys else None,
                "discrepancies": e.get("discrepancies") or "",
                "notable": e.get("notable") or 0,
                "is_top": e.get("key") in jtop,
                "block_ids": bids,
                "url": order[pos[bids[0]]]["transcript_url"] if bids else None,
                "notes": e.get("notes") or "",
                # filled by discography/geocode_places.py
                "geo": None,
            })
        # coordinates, when the geocoding step has run
        gp = ROOT / "shared" / "places.json"
        if gp.exists():
            geo = {g["key"]: g for g in json.loads(gp.read_text(encoding="utf-8"))["items"]}
            for j in jrn:
                g = geo.get(j["key"])
                if g and g.get("lat") is not None:
                    j["geo"] = {k: g.get(k) for k in ("lat", "lon", "qid", "label", "matched_on",
                                                       "precision")}

    stats = {
        "self": {
            "count": len(self_items),
            "blocks_quoted": len({i["block_id"] for i in self_items}),
            "by_notable": dict(sorted(Counter(i["notable"] for i in self_items).items(), reverse=True)),
            "by_theme": dict(Counter(t for i in self_items for t in i["theme"]).most_common()),
            "by_length": dict(Counter(i["length"] for i in self_items).most_common()),
            "stand_alone": sum(1 for i in self_items if i["stands_alone"]),
            "spanning_a_page_break": sum(1 for i in self_items if i["spans_page_break"]),
            "median_chars": sorted(i["chars"] for i in self_items)[len(self_items) // 2] if self_items else 0,
        },
        "timeline": {
            "count": len(tl),
            "stated_by": dict(Counter(i["stated_by"] for i in tl).most_common()),
            "confirmed_by_weston": sum(1 for i in tl if i["confirmed_by_weston"]),
            "undated": sum(1 for i in tl if i["sort_year"] is None),
            "with_a_note": sum(1 for i in tl if i["notes"]),
        },
        "records": {
            "count": len(recs),
            "by_kind": dict(Counter(r["kind"] for r in recs).most_common()),
            "with_his_quote": sum(1 for r in recs if r["pull_quote"]),
            "with_discrepancy": sum(1 for r in recs if r["discrepancies"]),
            "by_notable": dict(sorted(Counter(r["notable"] for r in recs).items(), reverse=True)),
        },
        "journeys": {
            "count": len(jrn),
            "by_kind": dict(Counter(j["kind"] for j in jrn).most_common()),
            "by_country": dict(Counter(j["country"] for j in jrn).most_common()),
            "with_his_quote": sum(1 for j in jrn if j["pull_quote"]),
            "with_coordinates": sum(1 for j in jrn if j["geo"]),
            "by_notable": dict(sorted(Counter(j["notable"] for j in jrn).items(), reverse=True)),
        },
        "quotes_dropped_on_verification": dict(dropped),
    }
    if scheme:
        stats["categories"] = {
            "count": len(categories),
            "by_category": {c["key"]: c["count"] for c in categories},
            "two_readers_agreed": sum(1 for i in self_items if i["category_agreed"]),
            "adjudicated": sum(1 for i in self_items if i["category_agreed"] is False),
            "with_secondary": sum(1 for i in self_items if i["category_secondary"]),
            "uncategorised": uncategorised,
        }
    out = {
        "subject": SUBJ.KEY, "qid": SUBJ.QID,
        "generated_from": "linked_jazz.sqlite + Opus subagent reading pass (extract/OWN_VOICE_SPEC.md)",
        "doc": {"doc_id": SUBJ.OWN_DOC, "title": own["doc"]["title"],
                "interview_date": SUBJ.OWN_DOC_DATE,
                "interviewer": SUBJ.INTERVIEWER, "transcript_url": own["doc"]["transcript_url"],
                "source_url": own["doc"]["source_url"]},
        "read_this_first": (
            "This interview is a sequel ('since the last oral history a lot has happened'): it "
            "covers roughly 1997-2009 and is not a life story, so the timeline is thin before "
            "the 1990s. Weston speaks in long paragraphs; every pull_quote is a cut from one, "
            "and several items can come from one block (key on `id`, not block_id). Ten "
            "items (ids j01-j10, spans_page_break=true) are sentences the PDF's page breaks cut "
            "in two: they are verified against two consecutive blocks joined by one space. The "
            "transcript spells by ear and misstates some dates -- quotes keep its spelling; "
            "`notes` and `discrepancies` say what is meant. `stands_alone: false` means the line "
            "needs the question, which is in `exchange.question`. Timeline entries with "
            "stated_by 'jenkins' and confirmed_by_weston false are not his testimony."),
        "themes": THEMES,
        "categories": categories,
        "stats": stats,
        "self": {"count": len(self_items), "top": [i["id"] for i in self_items if i["is_top"]],
                 "items": self_items},
        "timeline": {"count": len(tl), "items": tl},
        "records": {"count": len(recs), "items": recs},
        "journeys": {"count": len(jrn), "top": [j["key"] for j in jrn if j["is_top"]], "items": jrn},
    }
    (D / "own_voice.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "shared").mkdir(exist_ok=True)
    (ROOT / "shared" / "own_voice_summary.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"own_voice.json  self {len(self_items)}  timeline {len(tl)}  records {len(recs)}  "
          f"journeys {len(jrn)}  dropped {dict(dropped)}")
    print("  self notable", stats["self"]["by_notable"], " length", stats["self"]["by_length"])
    print("  themes", stats["self"]["by_theme"])
    if scheme:
        print("  categories:")
        for c in categories:
            print(f"    {c['count']:3d}  {c['label']}")
        if uncategorised:
            print(f"  !! {uncategorised} pull quotes have no category -- re-run the category pass")
    print("  his top lines:")
    for i in self_items[:12]:
        print(f"    [{i['notable']}] p{i['page']:<3} {i['pull_quote'][:110]!r}")
    print("  journeys:", stats["journeys"]["by_country"])


if __name__ == "__main__":
    main()
