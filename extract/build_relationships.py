#!/usr/bin/env python3
"""
Build the RELATIONSHIPS layer for the Randy Weston centennial extraction
(ported from the Coltrane / Davis build). Direction: other interviewees -> him.
The mirror image, him -> others, is build_own_interview.py.

    uv run python extract/build_relationships.py

Reads (read-only) /Users/m/git/ch-jazz-mashup/linked_jazz.sqlite and writes
    weston/relationships.json

Every classified relationship row whose `persons.qid` is the subject, with the
interviewee who said it, the exact transcript turns the classifier read, the
narrated third-party statements, and page-ready aggregates.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import os
DB = os.environ.get("LINKED_JAZZ_DB", "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite")  # see extract/subject.py
OUT_ROOT = Path("/Users/m/git/weston-centennial")
NETWORK_URL = "https://thisismattmiller.github.io/linked-jazz-2026-network/#{node_id}"

SUBJECTS = {
    "weston": {
        "qid": "Q1371187",
        "label": "Randy Weston",
        "node_id": "wd:Q1371187",
        # normalized-name aliases used ONLY to match the free-text name slots
        # inside relationships.third_party (that column has no qid layer).
        "tp_aliases_strong": {"randy weston", "randolph weston", "randolph edward weston", "weston randy", "randy western"},
        "tp_aliases_weak": {"randy", "weston"},  # bare first or last name — plausible but unverified
    },
}

ASYMMETRIC = {"mentor of", "influenced by", "played under"}

# {A} = the interviewee (the person who said it), {B} = the subject (Weston)
SYMMETRIC_READING = {
    "played with": "{A} played with {B}",
    "toured with": "{A} toured with {B}",
    "collaborated with": "{A} collaborated with {B}",
    "in music group with": "{A} was in a band with {B}",
    "friend of": "{A} was a friend of {B}",
    "acquaintance of": "{A} was an acquaintance of {B}",
    "has met": "{A} met {B}",
    "knows of": "{A} knew of {B}",
}

WS = re.compile(r"\s+")
NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
STOP_TOKENS = {"jr", "sr", "ii", "iii", "mr", "mrs", "ms", "dr", "the", "and", "interviewee",
               "interviewer", "unknown", "speaker"}


def die(msg: str) -> None:
    print(f"FATAL: {msg}", file=sys.stderr)
    raise SystemExit(2)


def collapse(text):
    """Collapse whitespace runs for readability. Returns (collapsed, raw_or_None)."""
    if text is None:
        return None, None
    c = WS.sub(" ", text).strip()
    return c, (text if c != text else None)


def norm_name(s):
    if not s:
        return ""
    return WS.sub(" ", NON_ALNUM.sub(" ", s.lower())).strip()


def surname_tokens(s):
    return {t for t in norm_name(s).split() if len(t) > 2 and t not in STOP_TOKENS}


def norm_text(s):
    """Aggressive normalization for the evidence-vs-block match check."""
    if not s:
        return ""
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("—", " ").replace("–", " ")
    return WS.sub(" ", NON_ALNUM.sub(" ", s.lower())).strip()


def display_name(doc_interviewee, ivs):
    """Best display name for the person who said it.

    doc_interviewees is the pipeline's resolved interviewee list and is more reliable than
    documents.interviewee, which in some Rutgers records holds the INTERVIEWER's name and in
    several Smithsonian records is written 'Surname Given'. Falls back to
    documents.interviewee when the node label is only a surname.
    Returns (name, name_source, conflict)."""
    meta_name = (doc_interviewee or "").strip()
    labels = [(iv["label"] or "").strip() for iv in ivs if (iv["label"] or "").strip()]
    if not labels:
        return (meta_name or "the interviewee"), "documents.interviewee", False
    labels = [l.title() if l.isupper() else l for l in labels]
    conflict = bool(meta_name and surname_tokens(meta_name)
                    and not (surname_tokens(meta_name) & set().union(
                        *[surname_tokens(l) for l in labels])))
    if len(labels) == 1:
        lab = labels[0]
        # a single-token node label (surname only) loses information vs. the metadata name
        if len(lab.split()) == 1 and meta_name and surname_tokens(lab) <= surname_tokens(meta_name):
            return meta_name, "documents.interviewee", False
        if meta_name and norm_name(lab) == norm_name(meta_name):
            return meta_name, "documents.interviewee", False
        return lab, "doc_interviewees.label", conflict
    return " and ".join(labels), "doc_interviewees.label", conflict


def network_url(node_id):
    return NETWORK_URL.format(node_id=node_id) if node_id else None


def transcript_link(base, page, block):
    if not base:
        return None
    return f"{base}#b{page}-{block}"


def bucket_of(conf):
    """0.1 buckets; 1.0 lands in the 0.9-1.0 bucket."""
    if conf is None:
        return None
    i = int(conf * 10)
    if i >= 10:
        i = 9
    if i < 0:
        i = 0
    return i


def decade_of(year):
    if year is None:
        return "unknown"
    return f"{(int(year) // 10) * 10}s"


def reading_for(relation, direction, a_name, b_name):
    """Plain-English rendering. direction is relative to the interviewee:
    'target' = the named person (our subject B) is the senior/source,
    'interviewee' = the interviewee A is the senior/source."""
    A, B = a_name, b_name
    if relation in ASYMMETRIC:
        if direction == "target":
            senior, junior = B, A
        elif direction == "interviewee":
            senior, junior = A, B
        else:
            senior = junior = None
        if relation == "mentor of":
            if senior:
                return f"{senior} mentored {junior}"
            if direction == "mutual":
                return f"{A} and {B} mentored each other"
            return f"{A} and {B} were in a mentor relationship (direction unstated)"
        if relation == "influenced by":
            if senior:
                return f"{junior} was influenced by {senior}"
            if direction == "mutual":
                return f"{A} and {B} influenced each other"
            return f"{A} and {B} — musical influence (direction unstated)"
        if relation == "played under":
            if senior:
                return f"{junior} played in {senior}'s band"
            if direction == "mutual":
                return f"{A} and {B} each played in the other's band"
            return f"{A} and {B} — one played in the other's band (direction unstated)"
    tmpl = SYMMETRIC_READING.get(relation)
    if tmpl:
        return tmpl.format(A=A, B=B)
    return f"{A} — {relation or 'unclassified'} — {B}"


TRIPLE_READING = {
    "mentor of": "{s} mentored {o}",
    "influenced by": "{s} was influenced by {o}",
    "played under": "{s} played in {o}'s band",
    "played with": "{s} played with {o}",
    "toured with": "{s} toured with {o}",
    "collaborated with": "{s} collaborated with {o}",
    "in music group with": "{s} was in a band with {o}",
    "friend of": "{s} was a friend of {o}",
    "acquaintance of": "{s} was an acquaintance of {o}",
    "has met": "{s} met {o}",
    "knows of": "{s} knew of {o}",
}


def triple_reading(subj, rel, obj):
    """third_party is a literal subject-relation-object triple (no `direction` column)."""
    s = subj or "someone"
    o = obj or "someone"
    tmpl = TRIPLE_READING.get(rel)
    return tmpl.format(s=s, o=o) if tmpl else f"{s} {rel or '—'} {o}"


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    weights = json.loads(con.execute(
        "SELECT value FROM meta WHERE key='relation_weights'").fetchone()[0])
    generated = con.execute("SELECT value FROM meta WHERE key='generated'").fetchone()
    generated = generated[0] if generated else None
    coll_labels = {r["collection"]: r["label"]
                   for r in con.execute("SELECT collection, label FROM collections")}

    # ---------- doc-level lookups (only the docs we need, but the tables are small) ----------
    docs = {}
    for r in con.execute("SELECT * FROM documents"):
        docs[r["doc_id"]] = dict(r)
    doc_ivs = defaultdict(list)
    for r in con.execute("SELECT doc_id, ord, node_key, label, qid FROM doc_interviewees "
                         "ORDER BY doc_id, ord"):
        doc_ivs[r["doc_id"]].append({
            "ord": r["ord"], "label": r["label"], "node_key": r["node_key"],
            "qid": r["qid"], "network_url": network_url(r["node_key"]),
        })

    # ---------- third_party sweep over the WHOLE corpus (name-slot matching) ----------
    tp_rows = []
    for r in con.execute(
            "SELECT rel_id, person_id, doc_id, relation, direction, confidence, evidence, "
            "third_party FROM relationships "
            "WHERE third_party IS NOT NULL AND TRIM(third_party) NOT IN ('', 'null')"):
        raw = r["third_party"]
        try:
            obj = json.loads(raw)
        except Exception:
            print(f"  warn: unparseable third_party on rel_id={r['rel_id']}: {raw[:80]!r}")
            continue
        if not isinstance(obj, dict):
            print(f"  warn: non-object third_party on rel_id={r['rel_id']}: {type(obj).__name__}")
            continue
        tp_rows.append((dict(r), obj))

    def block_row(block_id):
        b = con.execute("SELECT block_id, doc_id, page, block, type, speaker, text "
                        "FROM blocks WHERE block_id=?", (block_id,)).fetchone()
        if b is None:
            die(f"relationship_sources points at missing block_id={block_id}")
        return b

    def src_block(doc, block_id, page, block):
        """SPEC.md provenance object, anchored on one transcript block."""
        return {
            "doc_id": doc["doc_id"], "block_id": block_id, "page": page, "block": block,
            "collection": doc["collection"], "title": doc["title"],
            "interviewee": doc["interviewee"], "interviewer": doc["interviewer"],
            "year": doc["year"],
            "transcript_url": transcript_link(doc["transcript_url"], page, block),
            "source_url": doc["source_url"],
        }

    def speaker_role(role, speaker, doc):
        """SPEC.md speaker_role. relationship_sources.role already encodes the side the
        pipeline assigned; fall back to surname-token overlap on blocks.speaker."""
        up = (role or "").strip().upper()
        if up.startswith("INTERVIEWEE"):
            return "interviewee"
        if up.startswith("INTERVIEWER"):
            return "interviewer"
        sp = surname_tokens(speaker)
        if sp:
            ivt = surname_tokens(doc["interviewee"] or "")
            for iv in doc_ivs.get(doc["doc_id"], []):
                ivt |= surname_tokens(iv["label"] or "")
            if sp & ivt:
                return "interviewee"
            if sp & surname_tokens(doc["interviewer"] or ""):
                return "interviewer"
        return "unknown"

    def sources_for(rel_id, doc):
        out = []
        rows = con.execute("SELECT ord, block_id, page, block, role FROM relationship_sources "
                           "WHERE rel_id=? ORDER BY ord", (rel_id,)).fetchall()
        for s in rows:
            b = block_row(s["block_id"])
            if b["doc_id"] != doc["doc_id"]:
                die(f"rel {rel_id}: source block {s['block_id']} is from a different document")
            text, raw = collapse(b["text"])
            item = {
                "ord": s["ord"], "role": s["role"],
                "speaker_role": speaker_role(s["role"], b["speaker"], doc),
                "speaker": b["speaker"], "block_type": b["type"], "text": text,
                "page": s["page"], "block": s["block"], "block_id": s["block_id"],
                "transcript_url": transcript_link(doc["transcript_url"], s["page"], s["block"]),
            }
            if raw is not None:
                item["text_raw"] = raw
            out.append(item)
        return out

    summary = {}
    for subject, cfg in SUBJECTS.items():
        qid, label = cfg["qid"], cfg["label"]
        print(f"\n=== {subject} ({qid}) ===")

        rows = con.execute(
            "SELECT r.*, p.canonical, p.count AS mention_count, p.surface_forms, p.doc_id AS pdoc "
            "FROM persons p JOIN relationships r USING(person_id) "
            "WHERE p.qid = ?", (qid,)).fetchall()
        if not rows:
            die(f"no relationships rows for {qid}")

        items, skipped_items = [], []
        ev_total = ev_full = ev_partial = 0

        for r in rows:
            doc = docs.get(r["doc_id"])
            if doc is None:
                die(f"rel {r['rel_id']} references unknown doc_id {r['doc_id']!r}")
            if r["doc_id"] != r["pdoc"]:
                die(f"rel {r['rel_id']}: relationships.doc_id != persons.doc_id")

            srcs = sources_for(r["rel_id"], doc)
            first = srcs[0] if srcs else None
            src = (src_block(doc, first["block_id"], first["page"], first["block"])
                   if first else
                   {"doc_id": doc["doc_id"], "block_id": None, "page": None, "block": None,
                    "collection": doc["collection"], "title": doc["title"],
                    "interviewee": doc["interviewee"], "interviewer": doc["interviewer"],
                    "year": doc["year"], "transcript_url": doc["transcript_url"],
                    "source_url": doc["source_url"]})

            ivs = doc_ivs.get(doc["doc_id"], [])
            primary = ivs[0] if ivs else {}
            speaker_name, name_source, name_conflict = display_name(doc["interviewee"], ivs)
            person = {
                "name": speaker_name,
                "name_source": name_source,
                "name_from_metadata": doc["interviewee"],
                "name_conflict": name_conflict,
                "node_key": primary.get("node_key"),
                "qid": primary.get("qid"),
                "network_url": primary.get("network_url"),
                "interviewees": ivs,
                "as_named_in_doc": r["canonical"],   # how the SUBJECT was called in this doc
                "subject_surface_forms": json.loads(r["surface_forms"]) if r["surface_forms"] else [],
                "subject_mentions_in_doc": r["mention_count"],
            }

            tp = None
            if r["third_party"] and r["third_party"].strip() not in ("", "null"):
                try:
                    parsed = json.loads(r["third_party"])
                    tp = parsed if isinstance(parsed, dict) else {"raw": r["third_party"]}
                except Exception:
                    tp = {"raw": r["third_party"]}

            evidence, evidence_raw = collapse(r["evidence"])

            base = {
                "rel_id": r["rel_id"],
                "relation": r["relation"],
                "relation_weight": weights.get(r["relation"]),
                "direction": r["direction"],
                "reading": reading_for(r["relation"], r["direction"], speaker_name, label),
                "proposed": r["proposed"],
                "confidence": r["confidence"],
                "evidence": evidence,
                "context_turns": r["context_turns"],
                "expansions": r["expansions"],
                "model": r["model"],
                "person": person,
                "third_party": tp,
                "src": src,
                "sources": srcs,
            }
            if evidence_raw is not None:
                base["evidence_raw"] = evidence_raw

            if r["skipped"] is not None:
                base["skipped"] = r["skipped"]
                base.pop("reading", None)
                skipped_items.append(base)
                continue

            # evidence-vs-transcript verification
            hay = norm_text(" || ".join(s["text"] or "" for s in srcs))
            frags = [norm_text(f) for f in re.split(r"\.\.\.|…", evidence or "")]
            frags = [f for f in frags if len(f) >= 15]
            if frags:
                ev_total += 1
                hit = sum(1 for f in frags if f in hay)
                if hit == len(frags):
                    ev_full += 1
                    base["evidence_verified"] = "exact"
                elif hit:
                    ev_partial += 1
                    base["evidence_verified"] = "partial"
                else:
                    base["evidence_verified"] = "paraphrase"
            else:
                base["evidence_verified"] = "too_short_to_check"
            items.append(base)

        items.sort(key=lambda i: (-(i["confidence"] or 0.0),
                                  -(i["relation_weight"] or 0.0),
                                  i["rel_id"]))
        skipped_items.sort(key=lambda i: i["rel_id"])

        # ---------- aggregates ----------
        rc = Counter(i["relation"] for i in items)
        by_relation = sorted(
            ({"relation": k, "n": n, "weight": weights.get(k)} for k, n in rc.items()),
            key=lambda d: (-d["n"], -(d["weight"] or 0), d["relation"]))
        if set(rc) - set(weights):
            die(f"relation(s) missing from meta.relation_weights: {set(rc) - set(weights)}")

        cb = Counter(bucket_of(i["confidence"]) for i in items)
        by_confidence = [{"bucket": f"{b/10:.1f}-{(b+1)/10:.1f}", "lo": round(b / 10, 1),
                          "hi": round((b + 1) / 10, 1), "n": cb.get(b, 0)} for b in range(10)]

        cc = Counter(i["src"]["collection"] for i in items)
        by_collection = sorted(({"collection": k, "label": coll_labels.get(k), "n": n}
                                for k, n in cc.items()), key=lambda d: -d["n"])
        dc = Counter(decade_of(i["src"]["year"]) for i in items)
        by_decade = sorted(({"decade": k, "n": n} for k, n in dc.items()),
                           key=lambda d: (d["decade"] == "unknown", d["decade"]))

        top_evidence = [{"rel_id": i["rel_id"], "relation": i["relation"],
                         "reading": i["reading"], "evidence": i["evidence"], "src": i["src"]}
                        for i in items if (i["evidence"] or "").strip()][:40]

        # ---------- third-party statements naming the subject ----------
        strong, weak = cfg["tp_aliases_strong"], cfg["tp_aliases_weak"]
        own_ids = {i["rel_id"] for i in items} | {i["rel_id"] for i in skipped_items}
        third_party = []
        for row, obj in tp_rows:
            roles, kind = [], None
            for slot in ("subject", "object"):
                nm = norm_name(obj.get(slot) if isinstance(obj.get(slot), str) else "")
                if nm in strong:
                    roles.append(slot)
                    kind = "alias_exact"
                elif nm in weak:
                    roles.append(slot)
                    kind = kind or "alias_weak"
            if not roles:
                continue
            doc = docs.get(row["doc_id"])
            if doc is None:
                die(f"third_party rel {row['rel_id']} references unknown doc {row['doc_id']!r}")
            srcs = sources_for(row["rel_id"], doc)
            first = srcs[0] if srcs else None
            person_row = con.execute("SELECT canonical, qid FROM persons WHERE person_id=?",
                                     (row["person_id"],)).fetchone()
            ivs = doc_ivs.get(doc["doc_id"], [])
            ev, ev_raw = collapse(row["evidence"])
            narrator = display_name(doc["interviewee"], ivs)[0]
            reading = triple_reading(obj.get("subject"), obj.get("relation"), obj.get("object"))
            tp_item = {
                "rel_id": row["rel_id"],
                "statement": {"subject": obj.get("subject"), "relation": obj.get("relation"),
                              "object": obj.get("object")},
                "reading": reading,
                "narration": f"{narrator} said that {reading}",
                "relation_in_vocab": obj.get("relation") in weights,
                "subject_slot": roles[0] if len(roles) == 1 else "both",
                "name_match": kind,
                "narrated_by": {
                    "name": narrator,
                    "name_from_metadata": doc["interviewee"],
                    "node_key": (ivs[0]["node_key"] if ivs else None),
                    "qid": (ivs[0]["qid"] if ivs else None),
                    "network_url": (ivs[0]["network_url"] if ivs else None),
                    "interviewees": ivs,
                },
                "about_person_in_row": {"canonical": person_row["canonical"] if person_row else None,
                                        "qid": person_row["qid"] if person_row else None},
                "row_relation": row["relation"], "row_direction": row["direction"],
                "row_confidence": row["confidence"], "row_evidence": ev,
                "is_subject_row": row["rel_id"] in own_ids,
                "src": (src_block(doc, first["block_id"], first["page"], first["block"])
                        if first else None),
                "sources": srcs,
            }
            if ev_raw is not None:
                tp_item["row_evidence_raw"] = ev_raw
            third_party.append(tp_item)
        third_party.sort(key=lambda t: (-(t["row_confidence"] or 0), t["rel_id"]))

        out = {
            "subject": subject,
            "qid": qid,
            "label": label,
            "node_id": cfg["node_id"],
            "network_url": network_url(cfg["node_id"]),
            "generated_from": "linked_jazz.sqlite",
            "db_generated": generated,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "count": len(items),
            "method": {
                "selection": ("Every row of `relationships` joined through `persons` where "
                              "persons.qid = the subject QID. Rows with skipped IS NULL are "
                              "`items`; skipped='self_or_host' rows are under `skipped`."),
                "other_person": ("The 'other person' is the interviewee who said it. Every "
                                 "doc_interviewees row is listed with node_key / qid / network "
                                 "deep link; `person.interviewees[0]` (ord 0) is the primary and "
                                 "a handful of documents have two co-interviewees. "
                                 "`person.name` prefers the resolved doc_interviewees label over "
                                 "documents.interviewee (which in some Rutgers records holds the "
                                 "INTERVIEWER's name and in several Smithsonian records is "
                                 "written 'Surname Given'), except when the node label is only a "
                                 "surname; `name_source` says which was used, "
                                 "`name_from_metadata` always keeps documents.interviewee "
                                 "verbatim, and `name_conflict` flags rows where the two names "
                                 "share no surname token."),
                "direction": ("relationships.direction is relative to the interviewee, per the "
                              "classifier prompt: 'target' = the NAMED person (the subject of "
                              "this file) is the senior/source of an asymmetric relation "
                              "(mentor of / influenced by / played under); 'interviewee' = the "
                              "interviewee is the senior/source; 'mutual' / 'na' otherwise."),
                "reading": ("`reading` is built from relation + direction with the interviewee "
                            "as A and the subject as B. Asymmetric relations resolve a "
                            "senior/junior pair from `direction` "
                            "(mentor of -> '<senior> mentored <junior>'; influenced by -> "
                            "'<junior> was influenced by <senior>'; played under -> "
                            "'<junior> played in <senior>'s band'), with 'mutual' rendered "
                            "reciprocally and 'na' flagged '(direction unstated)'. Symmetric "
                            "relations use a fixed verb template with the interviewee first "
                            "(e.g. '<A> played with <B>', '<A> met <B>', '<A> knew of <B>'). "
                            "'knows of' is always one-way from the interviewee by definition. "
                            "For the few two-interviewee documents the reading uses the "
                            "documents.interviewee display string ('X and Y')."),
                "sources": ("relationship_sources joined to blocks, in `ord` order — the exact "
                            "transcript turns shown to the classifier. `speaker_role` comes "
                            "from relationship_sources.role when it starts with INTERVIEWEE/ "
                            "INTERVIEWER, else from surname-token overlap between blocks.speaker "
                            "and the document's interviewee(s)/interviewer, else 'unknown'."),
                "src": ("SPEC.md provenance object anchored on the FIRST source turn (ord 0) of "
                        "the relationship; transcript_url = documents.transcript_url + "
                        "'#b<page>-<block>' and is null where the DB has no transcript_url."),
                "third_party": ("relationships.third_party is a JSON string "
                                "{subject, relation, object} describing a relation narrated "
                                "between two OTHER people. Parsed into an object on each item. "
                                "The top-level `third_party` array is a corpus-wide sweep of "
                                "every third_party statement whose subject or object name "
                                "matches this person, matched on normalized names (there is no "
                                "qid layer on that column): name_match 'alias_exact' for full "
                                "names, 'alias_weak' for the bare first name (Miles) which is "
                                "plausible but unverified."),
                "text": ("Verbatim from the DB; runs of whitespace collapsed to single spaces "
                         "with the original kept in `text_raw` / `evidence_raw` when it differed."),
                "sorting": ("items sorted by confidence desc, then meta.relation_weights desc, "
                            "then rel_id."),
                "evidence_verified": ("Self-check, not curation: the model's evidence quote is "
                                      "split on '...' and each fragment >=15 chars is looked up "
                                      "in the concatenated source-block text after "
                                      "lowercase/punctuation normalization. 'exact' = all "
                                      "fragments found, 'partial' = some, 'paraphrase' = none "
                                      "(the model was allowed to compress quotes)."),
            },
            "relation_weights": weights,
            "by_relation": by_relation,
            "by_confidence": by_confidence,
            "by_collection": by_collection,
            "by_decade": by_decade,
            "top_evidence": top_evidence,
            "third_party": third_party,
            "third_party_count": len(third_party),
            "skipped": {
                "note": ("relationships rows with skipped='self_or_host' — the pipeline judged "
                         "the detected person to BE the interviewee or the interviewer/host, so "
                         "no relation was classified and relation / direction / confidence / "
                         "evidence are all NULL and there are no source turns. For Randy Weston "
                         "this is CORRECT, unlike the Coltrane / Davis build where every such row "
                         "was a false self-match: the one row here is his own Smithsonian "
                         "interview, where 'Randy Weston' really is the interviewee. What he "
                         "said about other people in that interview is in his_relationships.json "
                         "and his_words.json."),
                "count": len(skipped_items),
                "items": skipped_items,
            },
            "items": items,
        }

        outdir = OUT_ROOT / subject
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / "relationships.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)

        rate = (ev_full / ev_total * 100) if ev_total else 0.0
        prate = ((ev_full + ev_partial) / ev_total * 100) if ev_total else 0.0
        summary[subject] = {
            "path": str(path), "items": len(items), "skipped": len(skipped_items),
            "third_party": len(third_party), "by_relation": by_relation,
            "ev_total": ev_total, "ev_full": ev_full, "ev_partial": ev_partial,
            "ev_rate": rate, "ev_rate_any": prate,
            "sources": sum(len(i["sources"]) for i in items),
            "name_conflicts": sum(1 for i in items if i["person"]["name_conflict"]),
            "multi_iv": sum(1 for i in items if len(i["person"]["interviewees"]) > 1),
            "no_year": sum(1 for i in items if i["src"]["year"] is None),
            "bytes": path.stat().st_size,
        }

        # ---------- spot-check: 3 items, print the evidence and the block text ----------
        picks = [items[0], items[len(items) // 2], items[-1]]
        for p in picks:
            print(f"\n--- spot-check rel_id={p['rel_id']} conf={p['confidence']} "
                  f"[{p['relation']} / {p['direction']}] {p['evidence_verified']}")
            print(f"    reading : {p['reading']}")
            print(f"    said by : {p['person']['name']} ({p['person']['node_key']}) "
                  f"{p['src']['collection']} {p['src']['year']}")
            print(f"    evidence: {(p['evidence'] or '')[:220]}")
            for s in p["sources"]:
                print(f"    src[{s['ord']}] {s['role']}/{s['speaker_role']} "
                      f"p{s['page']}b{s['block']}: {(s['text'] or '')[:220]}")
            print(f"    url     : {p['src']['transcript_url']}")

    # ---------- final summary ----------
    print("\n================ SUMMARY ================")
    for subj, s in summary.items():
        print(f"\n{subj}: {s['path']}  ({s['bytes']:,} bytes)")
        print(f"  items={s['items']}  skipped={s['skipped']}  "
              f"third_party={s['third_party']}  source_turns={s['sources']}")
        print(f"  name_conflicts={s['name_conflicts']}  two_interviewee_docs={s['multi_iv']}  "
              f"items_without_year={s['no_year']}")
        print(f"  evidence check: {s['ev_full']}/{s['ev_total']} exact "
              f"({s['ev_rate']:.1f}%), +{s['ev_partial']} partial "
              f"=> {s['ev_rate_any']:.1f}% at least partially literal")
        for b in s["by_relation"]:
            print(f"    {b['n']:>4}  {b['relation']:<22} w={b['weight']}")


if __name__ == "__main__":
    main()
