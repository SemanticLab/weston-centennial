#!/usr/bin/env python3
"""Merge the witness judgement into weston/witnesses.json -- and build the one
index of everybody, weston/people.json.

witnesses.json   one row per interview in which someone spoke about him: who,
                 how they knew him, the caption phrase, the lead quote. Judged
                 by one Opus subagent (extract/WITNESS_SPEC.md) that saw each
                 witness's testimony whole.

people.json      every person connected to him by ANY layer, keyed once, with a
                 flag per layer:
                     witness          they spoke about him           (witnesses.json)
                     he_spoke_of      he spoke about them            (his_words.json)
                     on_his_records   credited on a record he led or played on
                                                                     (discography_personnel.json)
                     network          an edge in the Linked Jazz graph (connections.json)
                 The interesting rows are the ones with more than one flag: the
                 people who spoke of him AND whom he spoke of.

Every quote is re-verified as an exact substring of its block. The caption
phrase is checked for grounding: a place, name, title or year in the phrase
that the witness's own blocks never contain marks the row grounded=false (it is
still kept).
"""

import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject as SUBJ  # noqa: E402

ROOT = Path(SUBJ.ROOT)
D = ROOT / SUBJ.KEY
NETWORK = "https://thisismattmiller.github.io/linked-jazz-2026-network/#"

WEIGHTS = {"in music group with": 3.0, "collaborated with": 2.5, "played with": 2.5,
           "toured with": 2.5, "played under": 2.2, "mentor of": 2.2, "influenced by": 2.0,
           "friend of": 1.8, "acquaintance of": 1.2, "has met": 1.0, "knows of": 0.4, "none": 0.0}
# the same four tiers the Coltrane / Davis page used
TIER = {"in music group with": "band", "collaborated with": "band", "played with": "band",
        "toured with": "band", "played under": "learned", "mentor of": "learned",
        "influenced by": "learned", "friend of": "social", "acquaintance of": "social",
        "has met": "social", "knows of": "knew_of", "none": "none"}
DIRECTIONS = {"weston_leads", "witness_leads", "mutual", "na"}

# verbs, prepositions and other glue: a phrase is not ungrounded for using them
STOP = set("""a an the and or of to in on at for with from by his her hers their its it he she they
them was were is are be been being had has have that this these those as so but if then than when
while about into over under again very just only also not no nor too more most much many some any
each other such own same one two three first last early late young older still even both all who
whom whose which what where why how there here through during within across around after before
between behind beside near onto upon via toward towards along past off out up down back later once
often always never sometimes saw see seen hear heard hearing know knew known knowing meet met
meeting come came coming go went gone take took taken make made making give gave given call called
put set sat sit stand stood find found run ran join joined joining share shared sharing bring
brought keep kept work worked working play played playing record recorded recording tour toured
study studied learn learned teach taught write wrote written writing arrange arranged arranging
buy bought cite cited name named say said says tell told like loved love admire admired praise
praised remember remembered recall recalled think thought call calls same time years year long
band bands music musician musicians woman women girl lady man men people section sections
among including include included rely relied urge urged hold held cite cited praise use used
him tune tunes trip piece pieces""".split())
# "forty years" is grounded by "40 years"
NUMBER_WORDS = {"ten": "10", "fifteen": "15", "twenty": "20", "thirty": "30", "forty": "40",
                "fifty": "50"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def stem(w):
    for suf in ("ings", "ing", "ers", "er", "ed", "es", "s", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)]
    return w


def grounded(phrase, texts):
    """-> (bool, [unsupported words])."""
    hay = norm(" ".join(texts))
    stems = {stem(w) for w in hay.split()}
    bad = []
    for w in norm(phrase).split():
        if w in STOP or len(w) < 3:
            continue
        if w in hay.split() or stem(w) in stems or NUMBER_WORDS.get(w) in hay.split():
            continue
        bad.append(w)
    return (not bad), bad


def main():
    wi = json.loads((D / "witness_input.json").read_text(encoding="utf-8"))["items"]
    wo = json.loads((D / "witness_output.json").read_text(encoding="utf-8"))["items"]
    if [i["witness_key"] for i in wi] != [o["witness_key"] for o in wo]:
        sys.exit("FATAL: witness_output order differs from witness_input")

    enr = {i["block_id"]: i for i in json.loads(
        (D / "enriched.json").read_text(encoding="utf-8"))["items"]}
    rec = {i["block_id"]: i for i in json.loads(
        (D / "recovered_evaluated.json").read_text(encoding="utf-8"))["items"]}
    own = {b["block_id"]: b for b in json.loads(
        (D / "own_interview.json").read_text(encoding="utf-8"))["items"]}
    docs_meta = {d["doc_id"]: d for d in json.loads(
        (D / "documents.json").read_text(encoding="utf-8"))["items"]}
    hw = json.loads((D / "his_words.json").read_text(encoding="utf-8"))["items"]
    hw_by_qid = {p["qid"]: p for p in hw if p["is_person"] and p["qid"]}
    roster = json.loads((D / "discography_personnel.json").read_text(encoding="utf-8"))["people"]
    ros_by_qid = {p["qid"]: p for p in roster if p["qid"]}
    conns = json.loads((D / "connections.json").read_text(encoding="utf-8"))["items"]
    con_by_qid = {c["other"]["qid"]: c for c in conns if c["other"].get("qid")}
    imgp = ROOT / "shared" / "images.json"
    images = json.loads(imgp.read_text(encoding="utf-8"))["people"] if imgp.exists() else {}

    import sqlite3
    dbc = sqlite3.connect(f"file:{SUBJ.DB}?mode=ro", uri=True)
    wd_by_label = defaultdict(list)
    for q, label, desc, b_, d_ in dbc.execute(
            "SELECT qid,label,description,birth,death FROM wd_people"):
        wd_by_label[label].append({"qid": q, "label": label, "description": desc,
                                   "birth": b_, "death": d_})
    dbc.close()

    # blocks added to the Liston bundle from the Liston build (see
    # build_witness_input.py): in neither enriched nor recovered
    extra_loc = {}
    for i in wi:
        base = (docs_meta.get(i["doc"]["doc_id"]) or {}).get("transcript_url")
        for b in i["blocks"]:
            if b.get("page") is not None and b["block_id"] not in enr:
                extra_loc[b["block_id"]] = (b["page"], f"{base}#b{b['page']}-{b['block']}" if base else None)

    def url_of(bid):
        if bid in extra_loc:
            return extra_loc[bid][1]
        if bid in enr:
            return enr[bid]["doc"]["transcript_url"]
        if bid in rec:
            return rec[bid]["transcript_url"]
        if bid in own:
            return own[bid]["transcript_url"]
        return None

    def page_of(bid):
        if bid in extra_loc:
            return extra_loc[bid][0]
        if bid in enr:
            return enr[bid]["page"]
        if bid in own:
            return own[bid]["page"]
        return None

    dropped = Counter()
    rows = []
    for i, o in zip(wi, wo):
        texts = {b["block_id"]: b["text"] for b in i["blocks"]}
        speakers = {b["block_id"]: (b.get("speaker_role"), b["kind"]) for b in i["blocks"]}

        def quote(q, bid, what):
            if not q:
                return None, None
            if bid not in texts:
                dropped[f"{what}: block not this witness's"] += 1
                return None, None
            if q not in texts[bid]:
                dropped[f"{what}: not verbatim"] += 1
                return None, None
            return q, bid

        lq, lb = quote(o.get("lead_quote"), o.get("lead_block_id"), "lead_quote")
        sq, sb = quote(o.get("second_quote"), o.get("second_block_id"), "second_quote")
        if sq and sq == lq:
            sq, sb = None, None

        rel = o.get("relation") if o.get("relation") in WEIGHTS else "none"
        dirn = o.get("direction") if o.get("direction") in DIRECTIONS else "na"
        ol = (o.get("one_liner") or "").strip().rstrip(".")
        # the judge read the surrounding turns too, so a fact may be grounded there
        hay = list(texts.values()) + [t["text"] for b in i["blocks"]
                                      for t in b["context_before"] + b["context_after"]]
        ok, bad = grounded(ol, hay) if ol else (True, [])

        qid = o.get("speaker_qid")
        known = {p["qid"] for p in i["interviewees"] if p["qid"]}
        if qid and qid not in known:      # a judge may not introduce an identifier
            dropped["speaker_qid not among the document's interviewees"] += 1
            qid = None
        person = next((p for p in i["interviewees"] if p["qid"] == qid), None) or {}
        qid_source = "doc_interviewees" if qid else None
        if not qid:
            # The witness has no reconciled QID: a co-interviewer who turned out
            # to be the one talking (Joe Williams in the Clark Terry interview),
            # or an interviewee the corpus never reconciled ("Butter Jackson").
            # Take a QID only on an exact, unique label match in the corpus's own
            # authority table -- on the judged name, or with a quoted nickname
            # removed -- never by search.
            nm = o.get("speaker_name") or ""
            for cand in dict.fromkeys([nm, re.sub(r'\s*["“][^"”]*["”]\s*', " ", nm).strip()]):
                hit = wd_by_label.get(cand)
                # ...and never onto a stub: wd_people holds 'Quentin "Butter"
                # Jackson' = Q99676854, a bare Wikidata item with no description,
                # dates or article, beside the real Quentin Jackson, Q720707.
                if hit and len(hit) == 1 and (hit[0]["description"] or hit[0]["birth"]):
                    person = hit[0]
                    qid, qid_source = person["qid"], "exact unique label match in wd_people"
                    break

        more = []
        for b in i["blocks"]:
            pq = b.get("pull_quote")
            if not pq or pq not in b["text"] or pq in (lq, sq):
                continue
            if (lq and (pq in lq or lq in pq)) or (sq and (pq in sq or sq in pq)):
                continue
            # the witness's own words only
            if b["speaker_role"] == "interviewer":
                continue
            more.append({"block_id": b["block_id"], "quote": pq, "notable": b["notable"] or 0,
                         "summary": b["summary"], "kind": b["kind"],
                         "page": page_of(b["block_id"]), "url": url_of(b["block_id"])})
        more.sort(key=lambda m: -m["notable"])

        said = hw_by_qid.get(qid)
        ros = ros_by_qid.get(qid)
        dm = docs_meta.get(i["doc"]["doc_id"], {})
        rows.append({
            "witness_key": o["witness_key"],
            "name": o.get("speaker_name") or (i["interviewees"][0]["label"] if i["interviewees"] else None),
            "qid": qid,
            "qid_source": qid_source,
            "description": person.get("description"),
            "born": person.get("birth"), "died": person.get("death"),
            "network_url": NETWORK + f"wd:{qid}" if qid else None,
            # ---- the judgement
            "spoke_themselves": bool(o.get("spoke_themselves")),
            "relation": rel,
            "relation_weight": WEIGHTS[rel],
            "tier": TIER[rel],
            "direction": dirn,
            "contact_level": o.get("contact_level"),
            "basis": o.get("basis") or [],
            "context": o.get("context") or "",
            "one_liner": ol,
            "grounded": ok,
            "ungrounded_words": bad,
            "summary": o.get("summary") or "",
            "stance": o.get("stance"), "stance_strength": o.get("stance_strength") or 0,
            "notable": o.get("notable") or 0,
            "caution": o.get("caution") or "",
            "confidence": o.get("confidence"),
            "notes": o.get("notes") or "",
            # ---- their words
            "lead_quote": lq, "lead_block_id": lb,
            "lead_page": page_of(lb) if lb else None, "lead_url": url_of(lb) if lb else None,
            "second_quote": sq, "second_block_id": sb,
            "second_url": url_of(sb) if sb else None,
            "more_quotes": more,
            "n_blocks": i["n_blocks"],
            "block_ids": [b["block_id"] for b in i["blocks"]],
            # ---- provenance
            "doc": {**i["doc"],
                    "transcript_url": (dm.get("transcript_url")
                                       or (url_of(i["blocks"][0]["block_id"]) or "").split("#")[0] or None),
                    "source_url": dm.get("source_url"),
                    "collection_label": dm.get("collection_label")},
            "upstream": {"relations": i["upstream_relations"],
                         "relation_ok": o.get("upstream_relation_ok")},
            # ---- joins to the other layers
            "on_his_records": bool(ros),
            "albums_with_him": ros["album_count"] if ros else 0,
            "liston_build": i.get("liston_build"),
            "instruments_on_his_records": ros["instruments"][:6] if ros else [],
            "he_spoke_of_them": bool(said),
            "he_said": ({"relation": said["relation"], "basis": said["basis"],
                         "one_liner": said["one_liner"], "summary": said["summary"],
                         "his_quote": said["his_quote"], "his_quote_url": said["his_quote_url"],
                         "notable": said["notable"]} if said else None),
            "image": (images.get(qid) or {}).get("image") if qid else None,
        })

    rows.sort(key=lambda r: (-r["notable"], -r["relation_weight"], -r["n_blocks"], r["name"] or ""))

    real = [r for r in rows if r["spoke_themselves"]]
    upstream_judged = [r["upstream"]["relation_ok"] for r in rows
                       if r["upstream"]["relation_ok"] is not None]
    stats = {
        "witness_documents": len(rows),
        "spoke_themselves": len(real),
        "name_only_in_interviewer_words": len(rows) - len(real),
        "distinct_people": len({r["qid"] or r["name"] for r in real}),
        "by_relation": dict(Counter(r["relation"] for r in real).most_common()),
        "by_tier": dict(Counter(r["tier"] for r in real).most_common()),
        "by_contact_level": dict(Counter(r["contact_level"] for r in real).most_common()),
        "by_stance": dict(Counter(r["stance"] for r in real).most_common()),
        "by_notable": dict(sorted(Counter(r["notable"] for r in rows).items(), reverse=True)),
        "with_lead_quote": sum(1 for r in rows if r["lead_quote"]),
        "one_liners": sum(1 for r in rows if r["one_liner"]),
        "one_liners_grounded": sum(1 for r in rows if r["one_liner"] and r["grounded"]),
        "with_caution": sum(1 for r in rows if r["caution"]),
        "also_on_his_records": sum(1 for r in real if r["on_his_records"]),
        "he_also_spoke_of_them": sorted({r["name"] for r in real if r["he_spoke_of_them"]}),
        "upstream_relation_wrong": upstream_judged.count(False),
        "upstream_relation_judged": len(upstream_judged),
        "quotes_dropped_on_verification": dict(dropped),
    }

    (D / "witnesses.json").write_text(json.dumps({
        "subject": SUBJ.KEY, "qid": SUBJ.QID,
        "generated_from": "linked_jazz.sqlite + Opus subagent judgement (extract/WITNESS_SPEC.md)",
        "direction_of_this_file": "FROM the witness TO Randy Weston",
        "count": len(rows),
        "method": (
            "One row per interview document, other than his own, in which at least one block was "
            "judged to be about him. A reader saw all of a witness's blocks at once and judged the "
            "relation, the lead quote and the caption phrase. spoke_themselves=false means his "
            "name is only in the interviewer's mouth or the archive's front matter: not a witness. "
            "Quotes re-verified verbatim here; grounded=false flags a caption word the testimony "
            "never contains. A person interviewed twice (Benny Powell, Jimmy Owens, Ron Carter, "
            "Orrin Keepnews) has two rows -- people.json folds them. The Melba Liston row also "
            "carries `liston_build`, what the readers of her whole interview concluded in "
            "~/git/liston-centennial-2026."),
        "read_this_first": "Read `caution` on every row before displaying its quote.",
        "relation_weights": WEIGHTS, "tiers": TIER,
        "stats": stats, "items": rows,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # ------------------------------------------------------------ people.json
    people = {}

    def get(qid, name):
        key = qid or ("name:" + norm(name))
        return people.setdefault(key, {
            "key": key, "qid": qid, "name": name, "description": None, "born": None, "died": None,
            "witness": False, "he_spoke_of": False, "on_his_records": False, "network": False,
            "layers": [], "witness_rows": [], "he_said": None, "records": None, "edge": None,
            "image": None})

    for r in rows:
        if not r["spoke_themselves"]:
            continue
        p = get(r["qid"], r["name"])
        p["witness"] = True
        p["description"] = p["description"] or r["description"]
        p["born"], p["died"] = p["born"] or r["born"], p["died"] or r["died"]
        p["witness_rows"].append({k: r[k] for k in (
            "witness_key", "relation", "tier", "direction", "contact_level", "one_liner", "summary",
            "lead_quote", "lead_url", "notable", "stance", "caution", "n_blocks")}
            | {"doc_title": r["doc"]["title"], "collection": r["doc"]["collection"],
               "year": r["doc"]["year"]})
    for h in hw:
        if not h["is_person"] or h["relation"] == "none" and not h["his_quote"]:
            continue
        p = get(h["qid"], h["name"])
        p["he_spoke_of"] = True
        p["description"] = p["description"] or h["description"]
        p["born"], p["died"] = p["born"] or h["born"], p["died"] or h["died"]
        p["he_said"] = {k: h[k] for k in (
            "relation", "direction", "basis", "tie", "one_liner", "summary", "his_quote",
            "his_quote_url", "interviewer_quote", "notable", "era", "n_his_quotes", "person_id",
            "instrument_or_role", "as_named_in_interview", "transcribed_wrong")}
    for m in roster:
        if not m["qid"] and not (m["said_about_subject"] or m["he_spoke_of_them"]):
            continue        # name-only credits: kept in discography_personnel.json only
        p = get(m["qid"], m["name"])
        p["on_his_records"] = True
        p["description"] = p["description"] or m["description"]
        p["born"], p["died"] = p["born"] or m["birth"], p["died"] or m["death"]
        p["records"] = {"album_count": m["album_count"], "albums": m["albums"],
                        "instruments": m["instruments"], "credit_type": m["credit_type"],
                        "interviewed_in_corpus": m["interviewed_in_corpus"]}
    for c in conns:
        o = c["other"]
        if not o.get("qid"):
            continue        # nm:/loc: nodes carry no stable identity to join on
        p = get(o["qid"], o["label"])
        p["network"] = True
        p["description"] = p["description"] or (o.get("wd_people") or {}).get("description") or o.get("description")
        p["edge"] = {"weight": c["weight"], "n": c["n"], "n_documents": c["n_documents"],
                     "relations": [r["relation"] for r in c["edge_relations"]],
                     "community": o.get("community"), "community_label": o.get("community_label"),
                     "network_url": c.get("network_url"), "evidence_url": c.get("evidence_url")}

    for p in people.values():
        p["layers"] = [k for k in ("witness", "he_spoke_of", "on_his_records", "network") if p[k]]
        p["both_directions"] = p["witness"] and p["he_spoke_of"]
        if p["qid"]:
            p["image"] = (images.get(p["qid"]) or {}).get("image")
            p["wikidata_url"] = f"https://www.wikidata.org/wiki/{p['qid']}"
            p["network_url"] = NETWORK + f"wd:{p['qid']}"
        best = max([r["notable"] for r in p["witness_rows"]] + [(p["he_said"] or {}).get("notable", 0)])
        p["notable"] = best
    plist = sorted(people.values(), key=lambda p: (
        -p["both_directions"], -p["notable"], -len(p["layers"]),
        -((p["records"] or {}).get("album_count", 0)), p["name"] or ""))

    pstats = {
        "people": len(plist),
        "with_qid": sum(1 for p in plist if p["qid"]),
        "by_layer": {k: sum(1 for p in plist if p[k])
                     for k in ("witness", "he_spoke_of", "on_his_records", "network")},
        "both_directions": [p["name"] for p in plist if p["both_directions"]],
        "witness_and_on_his_records": sum(1 for p in plist if p["witness"] and p["on_his_records"]),
        "he_spoke_of_and_on_his_records": sum(
            1 for p in plist if p["he_spoke_of"] and p["on_his_records"]),
        "in_all_four_layers": [p["name"] for p in plist if len(p["layers"]) == 4],
        "by_layer_count": dict(sorted(Counter(len(p["layers"]) for p in plist).items())),
        "with_image": sum(1 for p in plist if p["image"]),
    }
    (D / "people.json").write_text(json.dumps({
        "subject": SUBJ.KEY, "qid": SUBJ.QID,
        "generated_from": "witnesses.json + his_words.json + discography_personnel.json + connections.json",
        "count": len(plist),
        "method": (
            "One record per person, joined across four layers on Wikidata QID (people with no "
            "QID are keyed 'name:<normalised name>' and can only ever sit in one layer, except "
            "where a name matched exactly). Roster members with no QID who neither spoke of him "
            "nor were spoken of by him are left out -- they are in discography_personnel.json. "
            "Sorted: both directions first, then notable, then number of layers."),
        "stats": pstats, "items": plist,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "shared" / "people_summary.json").write_text(json.dumps(
        {"witnesses": stats, "people": pstats}, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"witnesses.json: {len(rows)} documents, {len(real)} real witnesses, "
          f"{stats['distinct_people']} distinct people")
    print(f"  relation {stats['by_relation']}")
    print(f"  tier {stats['by_tier']}   stance {stats['by_stance']}")
    print(f"  one-liners {stats['one_liners']} ({stats['one_liners_grounded']} grounded)   "
          f"cautions {stats['with_caution']}   dropped {dict(dropped)}")
    for r in rows:
        if r["one_liner"] and not r["grounded"]:
            print(f"    ungrounded: {r['name']}: {r['one_liner']!r} -> {r['ungrounded_words']}")
    print(f"  upstream relation wrong {stats['upstream_relation_wrong']}/{stats['upstream_relation_judged']}")
    print(f"people.json: {pstats['people']} people  layers {pstats['by_layer']}")
    print(f"  both directions ({len(pstats['both_directions'])}): {pstats['both_directions']}")
    print(f"  all four layers: {pstats['in_all_four_layers']}")


if __name__ == "__main__":
    main()
