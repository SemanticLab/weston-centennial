#!/usr/bin/env python3
"""His own interview -- the layer the Coltrane / Davis build could not have.

Randy Weston sat for the Smithsonian Jazz Oral History Program on 30 October
2009, interviewed by Willard Jenkins. Neither Coltrane nor Davis was ever
interviewed in this corpus, so that build only ever looked one way: what other
people said about the subject. Here, as in the Liston build, the arrow also runs
outward.

Outputs
  weston/own_interview.json     the whole transcript, block by block, with the
                                people named in each block and resolved roles
  weston/own_interview.txt      the same thing as plain reading text, one line
                                per block, for the reading agents
  weston/his_relationships.json every relation the upstream model classified
                                FROM him TO someone else (the mirror image of
                                relationships.json), with evidence + sources
  weston/his_words_input/       the same people, chunked for the judgement pass
                                (extract/HIS_WORDS_SPEC.md)

The upstream classification should not be published unjudged. In the Liston
build 59% of it was wrong (she answered "Yeah." and the model took her
interviewer's words for hers). Weston speaks at length, so that failure is
rarer here, but the model still types non-people as people ("Gnawa", "Isis")
and reads a name in a personnel list as a relationship. his_words.json is the
judged version.

Run:  uv run python extract/build_own_interview.py
"""

import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject as SUBJ  # noqa: E402

ROOT = Path(SUBJ.ROOT)
NETWORK = "https://thisismattmiller.github.io/linked-jazz-2026-network/#"
N_CHUNKS = 3
WS = re.compile(r"\s+")

ASYMMETRIC = {"mentor of", "influenced by", "played under"}
# {A} = Weston, {B} = the other person
READING = {
    "played with": "{A} played with {B}",
    "toured with": "{A} toured with {B}",
    "collaborated with": "{A} collaborated with {B}",
    "in music group with": "{A} was in a band with {B}",
    "friend of": "{A} was a friend of {B}",
    "acquaintance of": "{A} was an acquaintance of {B}",
    "has met": "{A} met {B}",
    "knows of": "{A} knew of {B}",
}
# direction is stored from the interviewee's side: 'interviewee' = he is the
# actor, 'target' = the other person is the actor
DIRECTED = {
    ("mentor of", "interviewee"): "{A} mentored {B}",
    ("mentor of", "target"): "{B} mentored {A}",
    ("influenced by", "interviewee"): "{A} was influenced by {B}",
    ("influenced by", "target"): "{B} was influenced by {A}",
    ("played under", "interviewee"): "{A} played under {B}",
    ("played under", "target"): "{A} played under {B}",
}


def collapse(s):
    return WS.sub(" ", s).strip() if s else ""


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def verify(evidence, texts):
    """exact | partial | paraphrase -- is the model's evidence really in the source?"""
    if not evidence:
        return None
    ev = collapse(evidence)
    hay = " ".join(texts)
    if ev in hay:
        return "exact"
    # the model joins fragments with " ... " and prefixes [INTERVIEWER] tags
    parts = [p.strip() for p in re.split(r"\.\.\.|…|\[INTERVIEWE[ER]\]|>>", ev) if len(p.strip()) >= 12]
    if parts:
        hit = sum(1 for p in parts if p in hay)
        if hit == len(parts):
            return "exact"
        if hit:
            return "partial"
    nh = norm(hay)
    toks = [t for t in norm(ev).split() if len(t) > 3]
    if toks and sum(1 for t in toks if t in nh) / len(toks) >= 0.8:
        return "partial"
    return "paraphrase"


def main():
    con = sqlite3.connect(f"file:{SUBJ.DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    did = SUBJ.OWN_DOC

    doc = con.execute("SELECT * FROM documents WHERE doc_id=?", (did,)).fetchone()
    if doc is None:
        sys.exit(f"FATAL: {did} not in documents")
    doc = dict(doc)
    meta = json.loads(doc.pop("meta_json") or "{}")
    turl = doc["transcript_url"]

    blocks = [dict(r) for r in con.execute(
        "SELECT block_id,page,block,type,speaker,text FROM blocks WHERE doc_id=? ORDER BY page,block",
        (did,))]
    if len(blocks) != doc["num_blocks"]:
        sys.exit(f"FATAL: {len(blocks)} blocks, documents says {doc['num_blocks']}")

    # ---- people named in each block
    persons = {r["person_id"]: dict(r) for r in con.execute(
        "SELECT * FROM persons WHERE doc_id=?", (did,))}
    nodes_of = defaultdict(list)
    for r in con.execute(
        "SELECT pn.person_id, pn.node_key, pn.label, pn.qid FROM person_nodes pn "
        "JOIN persons p USING(person_id) WHERE p.doc_id=? ORDER BY pn.person_id, pn.ord", (did,)):
        nodes_of[r["person_id"]].append({"node_key": r["node_key"], "label": r["label"],
                                         "qid": r["qid"] or None})
    wd = {}
    qids = sorted({p["qid"] for p in persons.values() if p["qid"]})
    for r in con.execute(
            f"SELECT qid,label,description,birth,death,wp_title FROM wd_people "
            f"WHERE qid IN ({','.join('?' * len(qids))})", qids):
        wd[r["qid"]] = dict(r)

    in_block = defaultdict(list)
    mention_blocks = defaultdict(list)
    for r in con.execute(
        "SELECT pm.person_id, pm.block_id, pm.start, pm.end FROM person_mentions pm "
        "JOIN persons p USING(person_id) WHERE p.doc_id=? ORDER BY pm.block_id, pm.start", (did,)):
        p = persons[r["person_id"]]
        in_block[r["block_id"]].append({
            "person_id": r["person_id"], "canonical": p["canonical"], "qid": p["qid"] or None,
            "start": r["start"], "end": r["end"]})
        if r["block_id"] not in mention_blocks[r["person_id"]]:
            mention_blocks[r["person_id"]].append(r["block_id"])

    # ---- roles: two labelled voices; a blank dialogue speaker is a page-break
    # continuation of the previous voice (14 blocks). Three blocks the upstream
    # segmentation got wrong are fixed by hand:
    #   309811, 309812  typed 'note', but they are Jenkins's opening turn
    #   309916          typed 'dialogue', but it is the transcriber's credit line
    FORCED = {309811: SUBJ.INTERVIEWER["speaker_label"],
              309812: SUBJ.INTERVIEWER["speaker_label"],
              309916: ""}
    role_of = {SUBJ.SUBJECT_SPEAKER: "subject",
               SUBJ.INTERVIEWER["speaker_label"].lower(): "interviewer"}
    last = None
    items, lines = [], []
    by_id = {}
    for b in blocks:
        spk = (b["speaker"] or "").strip()
        inherited = False
        if b["block_id"] in FORCED:
            spk = FORCED[b["block_id"]]
            inherited = bool(spk)
            if spk:
                last = spk
        elif b["type"] == "dialogue":
            if spk:
                last = spk
            elif last:
                spk, inherited = last, True
        role = role_of.get(spk.lower(), "none") if spk else "none"
        raw = b["text"] or ""
        text = collapse(raw)
        for m in in_block.get(b["block_id"], []):
            m["surface"] = raw[m["start"]:m["end"]]
        it = {
            "block_id": b["block_id"], "page": b["page"], "block": b["block"],
            "type": b["type"],
            "speaker": (b["speaker"] or "").strip() or None,
            "speaker_effective": spk or None,
            "speaker_inherited": inherited,
            "speaker_role": role,
            "text": text,
            **({"text_raw": raw} if raw != text else {}),
            "chars": len(text),
            "people": in_block.get(b["block_id"], []),
            "transcript_url": f"{turl}#b{b['page']}-{b['block']}" if turl else None,
        }
        items.append(it)
        by_id[b["block_id"]] = it
        who = (spk or f"({b['type']})") + ("*" if inherited else "")
        lines.append(f"[b{b['block_id']} p{b['page']}.{b['block']}] {who}: {text}")

    role_counts = Counter(i["speaker_role"] for i in items)
    chars_by_role = Counter()
    for i in items:
        chars_by_role[i["speaker_role"]] += i["chars"]

    own = {
        "subject": SUBJ.KEY, "qid": SUBJ.QID, "generated_from": "linked_jazz.sqlite",
        "count": len(items),
        "doc": {**doc, "speakers": meta.get("speakers"), "interview_dates": SUBJ.OWN_DOC_DATE,
                "year_note": "documents.year is 2020, the year the PDF was posted; the interview "
                             "was recorded on 30 October 2009 (stated in its opening turn)."},
        "interviewer": {**SUBJ.INTERVIEWER,
                        "note": "Willard Jenkins, jazz journalist and broadcaster, co-author "
                                "of Weston's autobiography African Rhythms (2010). Not a witness: "
                                "his questions are context for Weston's answers. "
                                "documents.interviewer is empty for this doc; the name comes "
                                "from the transcript's front matter."},
        "role_counts": dict(role_counts),
        "chars_by_role": dict(chars_by_role),
        "method": (
            "Every block of the document in (page, block) order, text whitespace-collapsed "
            "(text_raw kept when that changed anything). speaker_role: 'subject' = Weston, "
            "'interviewer' = Willard Jenkins, 'none' = header/note/boilerplate. A dialogue block "
            "with no speaker label is a page-break continuation and inherits the previous voice "
            "(speaker_inherited). Blocks 309811-309812 (Jenkins's opening, typed 'note' upstream) "
            "and 309916 (the transcriber's credit, typed 'dialogue') are assigned by hand. people[] is the per-document person layer: every name the "
            "NER + alias pass found in that block, with offsets into the ORIGINAL text."),
        "read_this_first": (
            "This is a SECOND oral history: Jenkins opens with 'since the last oral history a "
            "lot has happened', and the conversation covers roughly 1997-2009 -- the Verve "
            "records, the Gnawa, Egypt, Japan, his marriage -- taking the earlier life as read. "
            "The transcript is lightly edited and spells names by ear ('Louie Armstrong', "
            "'Buddy Boland', 'Kenny Durham', 'Dr. Wayne Chandler'); quote it as it stands. "
            "Square brackets are the transcriber's: '[inaudible]' and two small word "
            "insertions. Never quote a bracketed insertion as his."),
        "items": items,
    }
    out = ROOT / SUBJ.KEY
    out.mkdir(exist_ok=True)
    (out / "own_interview.json").write_text(
        json.dumps(own, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "own_interview.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- his relationships: the upstream classification, turned around
    weights = json.loads(con.execute(
        "SELECT value FROM meta WHERE key='relation_weights'").fetchone()[0])
    order_of = {}
    for i, it in enumerate(items):
        for m in it["people"]:
            order_of.setdefault(m["person_id"], i)

    rels, skipped = [], []
    for r in con.execute(
        "SELECT r.*, p.canonical, p.count AS n_mentions, p.qid, p.wd_label, p.wd_description, "
        "p.surface_forms, p.vias FROM relationships r JOIN persons p USING(person_id) "
            "WHERE r.doc_id=? ORDER BY p.count DESC, r.rel_id", (did,)):
        r = dict(r)
        pid = r["person_id"]
        sources = []
        for s in con.execute(
            "SELECT rs.ord, rs.role, rs.block_id FROM relationship_sources rs WHERE rs.rel_id=? "
                "ORDER BY rs.ord", (r["rel_id"],)):
            b = by_id.get(s["block_id"])
            if b is None:
                sys.exit(f"FATAL: source block {s['block_id']} not in {did}")
            sources.append({
                "ord": s["ord"], "role": s["role"], "block_id": b["block_id"],
                "page": b["page"], "block": b["block"], "speaker": b["speaker_effective"],
                "speaker_role": b["speaker_role"], "text": b["text"],
                "transcript_url": b["transcript_url"]})
        nodes = nodes_of.get(pid, [])
        qid = r["qid"] or None
        w = wd.get(qid) or {}
        name = w.get("label") or r["wd_label"] or r["canonical"]
        rel, dirn = r["relation"], r["direction"]
        reading = None
        if rel:
            tpl = DIRECTED.get((rel, dirn)) or READING.get(rel)
            reading = tpl.format(A=SUBJ.NAME, B=name) if tpl else None
        subj_src = [s for s in sources if s["speaker_role"] == "subject"]
        rec = {
            "rel_id": r["rel_id"],
            "relation": rel,
            "relation_weight": weights.get(rel) if rel else None,
            "direction": dirn,
            "reading": reading,
            "proposed": r["proposed"],
            "confidence": r["confidence"],
            "evidence": r["evidence"],
            "evidence_verified": verify(r["evidence"], [s["text"] for s in sources]),
            # the single most useful flag on these rows
            "evidence_in_his_own_words": verify(r["evidence"], [s["text"] for s in subj_src])
            if subj_src else None,
            "model": r["model"],
            "person": {
                "person_id": pid,
                "name": name,
                "as_named_in_interview": r["canonical"],
                "surface_forms": json.loads(r["surface_forms"] or "[]"),
                "qid": qid,
                "description": w.get("description") or r["wd_description"],
                "born": w.get("birth"), "died": w.get("death"),
                "node_keys": [n["node_key"] for n in nodes],
                "network_url": NETWORK + nodes[0]["node_key"] if nodes else None,
                "wikipedia": ("https://en.wikipedia.org/wiki/" + w["wp_title"].replace(" ", "_"))
                if w.get("wp_title") else None,
                "n_mentions": r["n_mentions"],
                "mention_block_ids": mention_blocks.get(pid, []),
                "first_mention_order": order_of.get(pid),
            },
            "sources": sources,
            "src": {
                "doc_id": did, "collection": doc["collection"], "title": doc["title"],
                "interviewee": doc["interviewee"], "interviewer": SUBJ.INTERVIEWER["name"],
                "year": SUBJ.OWN_DOC_YEAR, "transcript_url": sources[0]["transcript_url"] if sources else turl,
                "source_url": doc["source_url"]},
        }
        (skipped if r["skipped"] else rels).append({**rec, **({"skipped": r["skipped"]} if r["skipped"] else {})})

    rels.sort(key=lambda x: (-(x["relation_weight"] or 0), -x["person"]["n_mentions"], x["rel_id"]))
    by_rel = Counter(x["relation"] for x in rels)
    hr = {
        "subject": SUBJ.KEY, "qid": SUBJ.QID, "generated_from": "linked_jazz.sqlite",
        "count": len(rels),
        "direction_of_this_file": "FROM Randy Weston TO the person named -- the mirror of relationships.json",
        "status": "UPSTREAM MODEL OUTPUT, UNJUDGED. Use his_words.json for anything shown to a reader.",
        "method": (
            "Every relationships row whose doc_id is his own interview, joined to the per-document "
            "person, its network node(s) and wd_people. `reading` renders the relation as a "
            "sentence with Weston as A. evidence_verified tests the model's evidence string "
            "against the source turns it read (exact / partial / paraphrase); "
            "evidence_in_his_own_words runs the same test against ONLY the turns Weston himself "
            "spoke -- null or 'paraphrase' there means the classification rests on what Willard "
            "Jenkins said, not on Weston's words."),
        "relation_weights": weights,
        "by_relation": [{"relation": k, "weight": weights.get(k), "count": v}
                        for k, v in sorted(by_rel.items(), key=lambda kv: -(weights.get(kv[0]) or 0))],
        "evidence_verified": dict(Counter(x["evidence_verified"] for x in rels)),
        "evidence_in_his_own_words": dict(Counter(str(x["evidence_in_his_own_words"]) for x in rels)),
        "reconciled_vs_not": dict(Counter("qid" if x["person"]["qid"] else "name_only" for x in rels)),
        "skipped": {
            "note": "self_or_host rows: the upstream pipeline took the detected person to be "
                    "the interviewee or the interviewer. Everyone but Weston himself is handed "
                    "to the judgement pass anyway.",
            "count": len(skipped), "items": skipped},
        "items": rels,
    }
    (out / "his_relationships.json").write_text(
        json.dumps(hr, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- judgement chunks: everyone but Weston himself, in reading order
    people = [x for x in rels + skipped if x["person"]["qid"] != SUBJ.QID]
    people.sort(key=lambda x: (x["person"]["first_mention_order"] is None,
                               x["person"]["first_mention_order"] or 0, x["rel_id"]))
    cdir = out / "his_words_input"
    cdir.mkdir(exist_ok=True)
    for old in cdir.glob("chunk_*.json"):
        old.unlink()
    size = -(-len(people) // N_CHUNKS)
    chunks = [people[i:i + size] for i in range(0, len(people), size)]
    for n, ch in enumerate(chunks, 1):
        its = []
        for x in ch:
            p = x["person"]
            its.append({
                "person_id": p["person_id"],
                "as_named_in_interview": p["as_named_in_interview"],
                "surface_forms": p["surface_forms"],
                "upstream_identity": {"qid": p["qid"], "name": p["name"],
                                      "description": p["description"],
                                      "born": p["born"], "died": p["died"]},
                "n_mentions": p["n_mentions"],
                "mention_block_ids": p["mention_block_ids"],
                "is_interviewer": p["qid"] == SUBJ.INTERVIEWER["qid"],
                "upstream": {
                    "relation": x["relation"], "direction": x["direction"],
                    "proposed": x["proposed"], "confidence": x["confidence"],
                    "evidence": x["evidence"],
                    "evidence_in_his_own_words": x["evidence_in_his_own_words"],
                    "skipped": x.get("skipped")},
            })
        (cdir / f"chunk_{n:03d}.json").write_text(json.dumps(
            {"subject": SUBJ.KEY, "chunk": n, "n_chunks": len(chunks), "count": len(its),
             "transcript": "weston/own_interview.txt", "items": its},
            ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- everything else named in his interview: places, bands, tunes, venues...
    ETYPES = ["place", "venue", "ensemble", "musical_work", "organization", "record_label",
              "event", "instrument", "date"]
    ents = defaultdict(dict)
    for r in con.execute(
        "SELECT e.entity_id, e.etype, e.text, e.count, e.confidence, em.block_id "
        "FROM entities e JOIN entity_mentions em USING(entity_id) "
            "WHERE e.doc_id=? AND e.etype != 'person' AND em.block_id IS NOT NULL", (did,)):
        t = collapse(r["text"])
        g = ents[r["etype"]].setdefault(t.casefold(), {
            "text": t, "mentions": 0, "block_ids": [], "said_by": set(), "confidence": r["confidence"]})
        g["mentions"] += 1
        if r["block_id"] not in g["block_ids"]:
            g["block_ids"].append(r["block_id"])
        g["said_by"].add(by_id[r["block_id"]]["speaker_role"])
    ent_out = {}
    for et in ETYPES:
        rows_ = []
        for g in ents.get(et, {}).values():
            first = by_id[g["block_ids"][0]]
            rows_.append({
                "text": g["text"], "mentions": g["mentions"], "n_blocks": len(g["block_ids"]),
                # lower-case surface forms are common nouns the tagger swept up
                # ("band", "the group", "it") -- kept, flagged, sorted last
                "generic": g["text"] == g["text"].lower(),
                "said_by": sorted(x for x in g["said_by"] if x != "none") or ["none"],
                "block_ids": g["block_ids"][:20],
                "first": {"block_id": first["block_id"], "page": first["page"],
                          "speaker": first["speaker_effective"], "text": first["text"][:400],
                          "transcript_url": first["transcript_url"]},
            })
        rows_.sort(key=lambda x: (x["generic"], -x["mentions"], x["text"].lower()))
        ent_out[et] = rows_
    (out / "own_interview_entities.json").write_text(json.dumps({
        "subject": SUBJ.KEY, "qid": SUBJ.QID, "generated_from": "linked_jazz.sqlite",
        "doc_id": did,
        "count": sum(len(v) for v in ent_out.values()),
        "method": (
            "Every non-person entity the NER pass (GLiNER, 9 types) tagged in his own interview, "
            "grouped case-insensitively by surface text. said_by: 'subject' = Weston, "
            "'interviewer' = Willard Jenkins. RAW and unjudged: the tagger mistypes names "
            "and sweeps up common nouns, which are flagged "
            "generic=true and sorted last. People are in his_words.json."),
        "by_type": {et: {"count": len(v), "named": sum(1 for x in v if not x["generic"])}
                    for et, v in ent_out.items()},
        "items": ent_out,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("own_interview_entities.json:",
          {et: f"{sum(1 for x in v if not x['generic'])}/{len(v)}" for et, v in ent_out.items()})

    print(f"own_interview.json: {len(items)} blocks, roles {dict(role_counts)}, "
          f"chars {dict(chars_by_role)}")
    print(f"own_interview.txt : {sum(len(x) + 1 for x in lines):,} chars")
    print(f"his_relationships.json: {len(rels)} classified + {len(skipped)} skipped")
    print(f"  evidence_verified          {hr['evidence_verified']}")
    print(f"  evidence_in_his_own_words  {hr['evidence_in_his_own_words']}")
    for r in hr["by_relation"]:
        print(f"  {r['count']:>4}  {r['relation']:<22} w={r['weight']}")
    print(f"his_words_input: {len(people)} people -> {len(chunks)} chunks "
          f"{[len(c) for c in chunks]}")
    con.close()


if __name__ == "__main__":
    main()
