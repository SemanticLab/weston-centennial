#!/usr/bin/env python3
"""
Build the PROFILE / DOCUMENTS / CO-OCCURRENCE layer for the Randy Weston
centennial extraction (ported from the Coltrane / Davis build).

Outputs (per subject):
  <subject>/profile.json
  <subject>/documents.json
  <subject>/cooccurrence.json

Run:  uv run python extract/build_profile_docs.py
Source DB is opened READ-ONLY.  Nothing is ever written to it.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import statistics
import sys
import urllib.parse
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subject as SUBJ  # noqa: E402

DB_PATH = "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite"
OUT_ROOT = "/Users/m/git/weston-centennial"

NETWORK_URL = "https://thisismattmiller.github.io/linked-jazz-2026-network/"
NODE_URL = NETWORK_URL + "#{node_id}"
WD_URL = "https://www.wikidata.org/wiki/{qid}"
WP_URL = "https://en.wikipedia.org/wiki/{title}"
# The deployed network viewer (ch-jazz-mashup/network/web/app.js:607) links Semlab
# items as https://base.semlab.io/wiki/Item:<semlab_id> ; the RDF entity URI form
# used throughout wikidata/semlab/*.json is http://base.semlab.io/entity/<id>.
SEMLAB_ITEM_URL = "https://base.semlab.io/wiki/Item:{sid}"
SEMLAB_ENTITY_URI = "http://base.semlab.io/entity/{sid}"

SUBJECTS = [
    {
        "key": "weston",
        "qid": "Q1371187",
        "node_id": "wd:Q1371187",
        "display": "Randy Weston",
        "nicknames": [],
    },
]

ETYPES = [
    "person", "place", "organization", "ensemble", "venue",
    "record_label", "musical_work", "instrument", "event", "date",
]

ETYPE_CAP = 150

SPEAKER_ROLE_METHOD = (
    "speaker_role: blocks.speaker is lowercased, stripped of punctuation and of "
    "honorifics/stopwords (mr, mrs, dr, interviewer, interviewee, speaker, unknown, "
    "initials), then compared to the doc's interviewee side (doc_interviewees.label "
    "plus documents.interviewee) and interviewer side (documents.interviewer) by "
    "token overlap on tokens of length >= 3; any shared token wins, interviewee side "
    "is tested first. If that fails and the speaker label is a 2-3 letter initialism "
    "(e.g. 'BM'), it is matched against the initials of each side's names. "
    "No match, or no speaker on the block at all (prose/PDF documents), => 'unknown'."
)

WS_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
HONORIFICS = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "professor", "rev", "sir",
    "interviewer", "interviewee", "speaker", "unknown", "narrator", "voice",
    "male", "female", "the", "and", "jr", "sr",
}


# ---------------------------------------------------------------- helpers
def collapse(s):
    if s is None:
        return None
    return WS_RE.sub(" ", s).strip()


def norm_key(s):
    """Case-insensitive grouping key for entity surface text."""
    return collapse(s).casefold() if s else ""


def name_tokens(s):
    if not s:
        return set()
    s = PUNCT_RE.sub(" ", s.lower())
    return {t for t in s.split() if len(t) >= 3 and t not in HONORIFICS}


def jloads(s, default=None):
    if s in (None, ""):
        return default
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return default


def nz(v):
    """Empty string -> None (the DB uses '' for some missing qids)."""
    return v if v not in ("", None) else None


def row_to_dict(row):
    return {k: row[k] for k in row.keys()}


def chunked(seq, n=900):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def qmarks(xs):
    return ",".join("?" * len(xs))


def trim_meta(obj, path="", dropped=None):
    """Recursively drop any array longer than 20 items."""
    if dropped is None:
        dropped = []
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if isinstance(v, list) and len(v) > 20:
                dropped.append({"path": p, "length": len(v)})
                continue
            out[k] = trim_meta(v, p, dropped)[0]
        return out, dropped
    if isinstance(obj, list):
        out = []
        for i, v in enumerate(obj):
            p = f"{path}[{i}]"
            if isinstance(v, list) and len(v) > 20:
                dropped.append({"path": p, "length": len(v)})
                continue
            out.append(trim_meta(v, p, dropped)[0])
        return out, dropped
    return obj, dropped


def wp_url(title):
    if not title:
        return None
    return WP_URL.format(title=urllib.parse.quote(title.replace(" ", "_"), safe="_(),'-!*~."))


def node_link(node_id):
    return NODE_URL.format(node_id=node_id) if node_id else None


def semlab_links(sid):
    if not sid:
        return None
    return {
        "semlab_id": sid,
        "url": SEMLAB_ITEM_URL.format(sid=sid),
        "entity_uri": SEMLAB_ENTITY_URI.format(sid=sid),
    }


def block_deep_link(doc, page, block):
    t = doc.get("transcript_url")
    if not t:
        return None
    return f"{t}#b{page}-{block}"


def fail(msg):
    raise SystemExit(f"SCHEMA/DATA SURPRISE — aborting: {msg}")


# ---------------------------------------------------------------- loaders
def load_documents(con, doc_ids):
    docs = {}
    for chunk in chunked(doc_ids):
        for r in con.execute(
            f"SELECT * FROM documents WHERE doc_id IN ({qmarks(chunk)})", chunk
        ):
            docs[r["doc_id"]] = row_to_dict(r)
    missing = set(doc_ids) - set(docs)
    if missing:
        fail(f"{len(missing)} doc_ids in persons have no documents row: {sorted(missing)[:5]}")
    return docs


def load_nodes(con, node_ids):
    out = {}
    node_ids = [n for n in node_ids if n]
    for chunk in chunked(node_ids):
        for r in con.execute(
            f"SELECT * FROM nodes WHERE node_id IN ({qmarks(chunk)})", chunk
        ):
            out[r["node_id"]] = row_to_dict(r)
    return out


def load_wd(con, qids):
    out = {}
    qids = [q for q in qids if q]
    for chunk in chunked(qids):
        for r in con.execute(
            f"SELECT * FROM wd_people WHERE qid IN ({qmarks(chunk)})", chunk
        ):
            out[r["qid"]] = row_to_dict(r)
    return out


def initials_of(names):
    """Initialisms ('Bill Russell' -> 'BR', 'BILLR') for 2-3 letter speaker labels."""
    out = set()
    for n in names:
        toks = [t for t in PUNCT_RE.sub(" ", (n or "").lower()).split()
                if t and t not in HONORIFICS]
        if len(toks) >= 2:
            out.add("".join(t[0] for t in toks))
            out.add(toks[-1][0] + toks[0][0])
        if toks:
            out.add(toks[-1][:1])
    return {i for i in out if 1 <= len(i) <= 3}


def speaker_role(speaker, itv_tokens, itr_tokens, itv_inits, itr_inits):
    if not speaker or not speaker.strip():
        return "unknown"
    toks = name_tokens(speaker)
    if toks & itv_tokens:
        return "interviewee"
    if toks & itr_tokens:
        return "interviewer"
    flat = PUNCT_RE.sub("", speaker).strip().lower()
    if 2 <= len(flat) <= 3 and flat.isalpha():
        if flat in itv_inits and flat not in itr_inits:
            return "interviewee"
        if flat in itr_inits and flat not in itv_inits:
            return "interviewer"
    return "unknown"


def src_block(doc, page, block, block_id, speaker=None, role=None):
    src = {
        "doc_id": doc["doc_id"],
        "block_id": block_id,
        "page": page,
        "block": block,
        "collection": doc.get("collection"),
        "title": doc.get("title"),
        "interviewee": doc.get("interviewee"),
        "interviewer": doc.get("interviewer"),
        "year": doc.get("year"),
        "transcript_url": block_deep_link(doc, page, block),
        "source_url": doc.get("source_url"),
    }
    if speaker is not None or role is not None:
        src["speaker"] = speaker
        src["speaker_role"] = role
    return src


# ---------------------------------------------------------------- per-subject build
def build_subject(con, subj, collections, communities, stats_out):
    qid = subj["qid"]
    node_id = subj["node_id"]
    key = subj["key"]

    # ---- persons rows for this subject
    prows = [row_to_dict(r) for r in con.execute(
        "SELECT * FROM persons WHERE qid = ? ORDER BY doc_id", (qid,))]
    if not prows:
        fail(f"no persons rows for {qid}")
    person_ids = [p["person_id"] for p in prows]
    doc_ids = sorted({p["doc_id"] for p in prows})

    # ---- person_mentions
    pm_rows = []
    for chunk in chunked(person_ids):
        pm_rows += [row_to_dict(r) for r in con.execute(
            f"SELECT pm.*, p.doc_id FROM person_mentions pm "
            f"JOIN persons p USING(person_id) "
            f"WHERE pm.person_id IN ({qmarks(chunk)})", chunk)]
    # Co-occurrence is "what is named in the same breath as him". Inside his own
    # interview his name is Willard Jenkins addressing him, so those blocks
    # would swamp the layer with the interview's own subject matter; they are
    # excluded here and covered by own_interview_entities.json instead.
    OWN = SUBJ.OWN_DOC
    subject_block_ids = sorted({r["block_id"] for r in pm_rows
                                if r["block_id"] is not None and r["doc_id"] != OWN})
    all_subject_block_ids = {r["block_id"] for r in pm_rows if r["block_id"] is not None}
    supplement = SUBJ.supplement_blocks(con, all_subject_block_ids)
    supplement_docs = sorted({ms[0]["doc_id"] for ms in supplement.values()})

    mentions_by_doc = Counter()
    blocks_by_doc = defaultdict(set)
    for r in pm_rows:
        mentions_by_doc[r["doc_id"]] += 1
        if r["block_id"] is not None:
            blocks_by_doc[r["doc_id"]].add(r["block_id"])
    # persons.count is the authoritative per-doc mention total
    count_by_doc = Counter()
    for p in prows:
        count_by_doc[p["doc_id"]] += p["count"] or 0
    if sum(count_by_doc.values()) != len(pm_rows):
        print(f"  ! note: sum(persons.count)={sum(count_by_doc.values())} but "
              f"person_mentions rows={len(pm_rows)} for {qid}", file=sys.stderr)

    # ---- documents
    docs = load_documents(con, doc_ids)

    # ---- doc_interviewees for those docs
    di_by_doc = defaultdict(list)
    for chunk in chunked(doc_ids):
        for r in con.execute(
            f"SELECT * FROM doc_interviewees WHERE doc_id IN ({qmarks(chunk)}) "
            f"ORDER BY doc_id, ord", chunk):
            d = row_to_dict(r)
            d["qid"] = nz(d["qid"])
            d["node_key"] = nz(d["node_key"])
            d["network_url"] = node_link(d["node_key"])
            di_by_doc[d["doc_id"]].append(d)

    itv_node_keys = {d["node_key"] for v in di_by_doc.values() for d in v if d["node_key"]}
    itv_qids = {d["qid"] for v in di_by_doc.values() for d in v if d["qid"]}
    itv_nodes = load_nodes(con, itv_node_keys)
    itv_wd = load_wd(con, itv_qids)

    # ---- classified relationships about the subject, per doc
    rel_by_doc = Counter()
    rel_total = 0
    rel_skipped = 0
    for chunk in chunked(person_ids):
        for r in con.execute(
            f"SELECT r.doc_id, r.skipped, COUNT(*) n FROM relationships r "
            f"WHERE r.person_id IN ({qmarks(chunk)}) GROUP BY 1,2", chunk):
            if r["skipped"] is None:
                rel_by_doc[r["doc_id"]] += r["n"]
                rel_total += r["n"]
            else:
                rel_skipped += r["n"]

    # ---- network edges
    edge_rows = [row_to_dict(r) for r in con.execute(
        "SELECT * FROM edges WHERE a = ? OR b = ?", (node_id, node_id))]

    # ================================================== PROFILE
    wd = con.execute("SELECT * FROM wd_people WHERE qid = ?", (qid,)).fetchone()
    if wd is None:
        fail(f"no wd_people row for {qid}")
    wd = row_to_dict(wd)
    wd["names_parsed"] = jloads(wd.pop("names"), [])

    node = con.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
    if node is None:
        fail(f"no nodes row for {node_id}")
    node = row_to_dict(node)
    node_colls = [r["collection"] for r in con.execute(
        "SELECT collection FROM node_collections WHERE node_id = ? ORDER BY collection",
        (node_id,))]

    comm = communities.get(node["community"])

    # name_reconciliation ledger rows resolving to this QID
    nr_rows = [row_to_dict(r) for r in con.execute(
        "SELECT * FROM name_reconciliation WHERE qid = ? ORDER BY mentions DESC", (qid,))]
    for r in nr_rows:
        r["name_collapsed"] = collapse(r["name"])

    # aliases: every distinct surface form across all docs
    alias_docs = Counter()
    alias_rows = Counter()
    aliases_by_doc = {}
    for p in prows:
        forms = jloads(p["surface_forms"], []) or []
        seen = set()
        aset = set()
        for f in forms:
            cf = collapse(f)
            if not cf:
                continue
            aset.add(cf.casefold())
            alias_rows[cf] += 1
            if cf not in seen:
                alias_docs[cf] += 1
                seen.add(cf)
        if p["canonical"]:
            aset.add(collapse(p["canonical"]).casefold())
        aliases_by_doc.setdefault(p["doc_id"], set()).update(aset)

    alias_items = [
        {"text": t, "n_docs": alias_docs[t], "n_person_rows": alias_rows[t]}
        for t in sorted(alias_docs, key=lambda x: (-alias_docs[x], x.lower()))
    ]

    # distinct interviewees who mention the subject
    itv_identity = {}
    for d in doc_ids:
        for e in di_by_doc.get(d, []):
            k = e["node_key"] or ("label:" + (collapse(e["label"]) or "").lower())
            itv_identity.setdefault(k, e)

    years = sorted(v["year"] for v in docs.values() if v.get("year"))
    year_span = {
        "min": years[0] if years else None,
        "max": years[-1] if years else None,
        "median": int(statistics.median(years)) if years else None,
        "n_docs_with_year": len(years),
        "n_docs_without_year": len(docs) - len(years),
    }

    other_docs = [d for d in doc_ids if d != OWN]
    other_itv = {k: e for k, e in itv_identity.items()
                 if e["qid"] != qid and any(x is e or x["node_key"] == e["node_key"]
                                           for d in other_docs for x in di_by_doc.get(d, []))}
    headline = {
        # ---- the numbers to quote: other people's interviews only
        "others": {
            "note": "Interviews other than his own. This is the 'what they said about him' "
                    "corpus; the reconciled person layer plus the text hits it missed.",
            "documents_reconciled": len(other_docs),
            "documents_text_hit_only": len([d for d in supplement_docs if d not in doc_ids]),
            "mentions_reconciled": sum(count_by_doc[d] for d in other_docs),
            "blocks_reconciled": sum(len(blocks_by_doc[d]) for d in other_docs),
            "blocks_text_hit_only": len(supplement),
            "distinct_interviewees": len(other_itv),
        },
        "own_interview": {
            "note": "His own Smithsonian interview (30 Oct 2009, interviewed by Willard Jenkins). "
                    "These 'mentions' are Jenkins addressing him, headers and archive notes.",
            "doc_id": OWN,
            "mentions": count_by_doc.get(OWN, 0),
            "blocks": len(blocks_by_doc.get(OWN, ())),
        },
        # ---- raw person-layer totals, own interview included (as the upstream DB counts them)
        "total_mentions": sum(count_by_doc.values()),
        "total_mentions_person_mentions_rows": len(pm_rows),
        "total_docs": len(doc_ids),
        "total_blocks_mentioning": len(all_subject_block_ids),
        "distinct_interviewees_who_mention": len(itv_identity),
        "n_classified_relationships": rel_total,
        "n_relationship_rows_skipped": rel_skipped,
        "n_network_edges": len(edge_rows),
        "network_edge_weight_sum": round(sum(e["weight"] or 0 for e in edge_rows), 4),
        "interview_years": year_span,
        "node_mentions": node["mentions"],
        "node_docs": node["docs"],
        "wd_people_mentions": wd["mentions"],
        "wd_people_docs": wd["docs"],
        "n_aliases": len(alias_items),
        "n_name_reconciliation_rows": len(nr_rows),
    }

    profile = {
        "key": key,
        "display_name": subj["display"],
        "nicknames": subj["nicknames"],
        "qid": qid,
        "node_id": node_id,
        "links": {
            "wikidata": WD_URL.format(qid=qid),
            "wikipedia": wp_url(wd.get("wp_title")),
            "network": node_link(node_id),
            "semlab": semlab_links(wd.get("semlab_id") or node.get("semlab_id")),
            "network_viewer": NETWORK_URL,
        },
        "wd_people": wd,
        "node": node,
        "node_collections": [
            {"collection": c, "label": collections.get(c, {}).get("label"),
             "url": collections.get(c, {}).get("url")}
            for c in node_colls
        ],
        "community": comm,
        "headline_stats": headline,
        "name_reconciliation": nr_rows,
        "aliases": {
            "count": len(alias_items),
            "note": "distinct persons.surface_forms across every doc where the subject "
                    "is reconciled; n_docs = interviews the form appears in.",
            "items": alias_items,
        },
    }

    out_profile = {
        "subject": key,
        "qid": qid,
        "generated_from": "linked_jazz.sqlite",
        "count": 1,
        "method": "identity layer joined from wd_people + nodes + node_collections + "
                  "communities + name_reconciliation; person identity resolved via "
                  "persons.qid / nodes.qid only (never raw text search).",
        "profile": profile,
        "items": [profile],
    }

    # ================================================== DOCUMENTS
    doc_items = []
    for d in doc_ids:
        doc = dict(docs[d])
        raw_meta = doc.pop("meta_json", None)
        meta, dropped = trim_meta(jloads(raw_meta, {}) or {})
        itvs = []
        for e in di_by_doc.get(d, []):
            n = itv_nodes.get(e["node_key"]) if e["node_key"] else None
            w = itv_wd.get(e["qid"]) if e["qid"] else None
            itvs.append({
                "ord": e["ord"],
                "label": e["label"],
                "node_key": e["node_key"],
                "qid": e["qid"],
                "network_url": e["network_url"],
                "node": None if not n else {
                    "node_id": n["node_id"], "kind": n["kind"], "label": n["label"],
                    "is_interviewee": n["is_interviewee"], "mentions": n["mentions"],
                    "docs": n["docs"], "community": n["community"],
                    "x": n["x"], "y": n["y"],
                    "wd_image_url": n["wd_image_url"],
                    "semlab_thumb_url": n["semlab_thumb_url"],
                },
                "wd_people": None if not w else {
                    "qid": w["qid"], "label": w["label"], "description": w["description"],
                    "birth": w["birth"], "death": w["death"], "wp_title": w["wp_title"],
                    "wikipedia_url": wp_url(w["wp_title"]),
                    "wikidata_url": WD_URL.format(qid=w["qid"]),
                    "image_url": w["image_url"],
                    "semlab_thumb_url": w["semlab_thumb_url"],
                    "semlab": semlab_links(w["semlab_id"]),
                },
            })
        coll = collections.get(doc.get("collection"), {})
        doc_items.append({
            "doc_id": d,
            "own_interview": d == OWN,
            "mention_source": "person_layer",
            "document": doc,
            "meta_json": meta,
            "meta_json_dropped_arrays": dropped,
            "collection_label": coll.get("label"),
            "collection_url": coll.get("url"),
            "transcript_url": doc.get("transcript_url"),
            "source_url": doc.get("source_url"),
            "doc_interviewees": itvs,
            "subject_mentions": count_by_doc[d],
            "subject_mention_rows": mentions_by_doc[d],
            "subject_blocks": len(blocks_by_doc[d]),
            "has_classified_relationship": rel_by_doc[d] > 0,
            "n_classified_relationships": rel_by_doc[d],
        })
    doc_items.sort(key=lambda x: (-x["subject_mentions"], -x["subject_blocks"], x["doc_id"]))

    by_collection = Counter()
    by_collection_mentions = Counter()
    by_decade = Counter()
    by_decade_mentions = Counter()
    by_method = Counter()
    for it in doc_items:
        c = it["document"].get("collection")
        by_collection[c] += 1
        by_collection_mentions[c] += it["subject_mentions"]
        y = it["document"].get("year")
        dk = f"{(y // 10) * 10}s" if y else "unknown"
        by_decade[dk] += 1
        by_decade_mentions[dk] += it["subject_mentions"]
        by_method[it["document"].get("method") or "unknown"] += 1

    # interviewee roster -- people OTHER than him who were interviewed
    roster = {}
    for it in doc_items:
        if it["own_interview"]:
            continue
        for e in it["doc_interviewees"]:
            k = e["node_key"] or ("label:" + (collapse(e["label"]) or "").lower())
            r = roster.setdefault(k, {
                "name": e["label"], "qid": e["qid"], "node_key": e["node_key"],
                "n_docs": 0, "n_mentions": 0,
                "image_url": (e["wd_people"] or {}).get("image_url")
                             or (e["node"] or {}).get("wd_image_url"),
                "semlab_thumb_url": (e["node"] or {}).get("semlab_thumb_url"),
                "description": (e["wd_people"] or {}).get("description"),
                "network_url": e["network_url"],
                "doc_ids": [],
            })
            r["n_docs"] += 1
            r["n_mentions"] += it["subject_mentions"]
            r["doc_ids"].append(it["doc_id"])
    roster_items = sorted(roster.values(),
                          key=lambda r: (-r["n_mentions"], -r["n_docs"], (r["name"] or "")))

    out_docs = {
        "subject": key,
        "qid": qid,
        "generated_from": "linked_jazz.sqlite",
        "count": len(doc_items),
        "method": "every interview with a persons row whose qid = the subject; "
                  "subject_mentions = SUM(persons.count) for that doc; "
                  "subject_blocks = DISTINCT person_mentions.block_id; "
                  "meta_json parsed and any array longer than 20 items dropped "
                  "(dropped paths listed in meta_json_dropped_arrays). "
                  "Sorted by subject mention count desc.",
        "totals": {
            "n_documents": len(doc_items),
            "n_mentions": sum(i["subject_mentions"] for i in doc_items),
            "n_blocks": sum(i["subject_blocks"] for i in doc_items),
            "n_docs_with_relationship": sum(1 for i in doc_items if i["has_classified_relationship"]),
            "n_interviewees": len(roster_items),
        },
        "by_collection": [
            {"collection": c, "label": collections.get(c, {}).get("label"),
             "n_docs": n, "n_mentions": by_collection_mentions[c]}
            for c, n in by_collection.most_common()
        ],
        "by_decade": [
            {"decade": d, "n_docs": n, "n_mentions": by_decade_mentions[d]}
            for d, n in sorted(by_decade.items(),
                               key=lambda kv: (kv[0] == "unknown", kv[0]))
        ],
        "by_method": [{"method": m, "n_docs": n} for m, n in by_method.most_common()],
        "own_interview_doc": OWN,
        "text_hit_only_documents": [
            {"doc_id": d, "title": sd.get("title"), "collection": sd.get("collection"),
             "interviewee": sd.get("interviewee"), "year": sd.get("year"),
             "transcript_url": sd.get("transcript_url"),
             "blocks": sorted(b for b, ms in supplement.items() if ms[0]["doc_id"] == d),
             "surface_forms": sorted({json.loads(ms[0]["surface_forms"])[0]
                                      for ms in supplement.values() if ms[0]["doc_id"] == d}),
             "note": "not reconciled to his QID upstream; found by text search and confirmed "
                     "block by block in enriched.json (mention_source = fts_supplement)"}
            for d, sd in sorted(load_documents(con, [x for x in supplement_docs
                                                    if x not in doc_ids]).items())
        ],
        "interviewees": roster_items,
        "items": doc_items,
    }

    # ================================================== CO-OCCURRENCE
    ent_rows = []
    for chunk in chunked(subject_block_ids):
        ent_rows += [row_to_dict(r) for r in con.execute(
            f"SELECT em.block_id, em.page, em.block, em.start, em.end, "
            f"e.entity_id, e.doc_id, e.etype, e.text, e.canonical "
            f"FROM entity_mentions em JOIN entities e ON e.entity_id = em.entity_id "
            f"WHERE em.block_id IN ({qmarks(chunk)})", chunk)]

    bad_etypes = {r["etype"] for r in ent_rows} - set(ETYPES)
    if bad_etypes:
        fail(f"unexpected entities.etype values: {sorted(bad_etypes)}")

    groups = defaultdict(lambda: defaultdict(lambda: {
        "blocks": set(), "docs": set(), "spellings": Counter(), "first": {}
    }))
    n_self_excluded = 0
    for r in ent_rows:
        et = r["etype"]
        disp = collapse(r["text"])
        if not disp:
            continue
        nk = disp.casefold()
        if et == "person":
            doc_aliases = aliases_by_doc.get(r["doc_id"], set())
            can = collapse(r["canonical"]).casefold() if r["canonical"] else None
            if nk in doc_aliases or (can and can in doc_aliases):
                n_self_excluded += 1
                continue
        g = groups[et][nk]
        g["blocks"].add(r["block_id"])
        g["docs"].add(r["doc_id"])
        g["spellings"][disp] += 1
        g["first"].setdefault(disp, r)

    # blocks needed for example snippets
    need_blocks = set()
    ranked = {}
    for et in ETYPES:
        gs = groups.get(et, {})
        order = sorted(gs.items(),
                       key=lambda kv: (-len(kv[1]["blocks"]), -len(kv[1]["docs"]),
                                       kv[0]))
        ranked[et] = order
        for _, g in order[:ETYPE_CAP]:
            disp = g["spellings"].most_common(1)[0][0]
            need_blocks.add(g["first"][disp]["block_id"])

    blocks = {}
    for chunk in chunked(need_blocks):
        for r in con.execute(
            f"SELECT block_id, doc_id, page, block, type, speaker, text FROM blocks "
            f"WHERE block_id IN ({qmarks(chunk)})", chunk):
            blocks[r["block_id"]] = row_to_dict(r)

    # speaker-role token sets per doc
    role_tokens = {}
    for d, doc in docs.items():
        itv_names = [e["label"] for e in di_by_doc.get(d, [])] + [doc.get("interviewee")]
        itr_names = [doc.get("interviewer")]
        itv = set()
        for n in itv_names:
            itv |= name_tokens(n)
        role_tokens[d] = (itv, name_tokens(doc.get("interviewer")),
                          initials_of(itv_names), initials_of(itr_names))

    def make_example(g):
        disp = g["spellings"].most_common(1)[0][0]
        m = g["first"][disp]
        b = blocks.get(m["block_id"])
        doc = docs.get(m["doc_id"])
        if b is None or doc is None:
            return None
        text = b["text"] or ""
        s = m["start"] if m["start"] is not None else 0
        e = m["end"] if m["end"] is not None else s + len(disp)
        lo, hi = max(0, s - 160), min(len(text), e + 160)
        raw = text[lo:hi]
        if lo > 0:
            raw = "…" + raw
        if hi < len(text):
            raw = raw + "…"
        itv_t, itr_t, itv_i, itr_i = role_tokens.get(
            m["doc_id"], (set(), set(), set(), set()))
        return {
            "text_snippet": collapse(raw),
            "text_raw": raw,
            "src": src_block(doc, m["page"], m["block"], m["block_id"],
                             b.get("speaker"),
                             speaker_role(b.get("speaker"), itv_t, itr_t,
                                          itv_i, itr_i)),
        }

    by_etype = {}
    for et in ETYPES:
        order = ranked[et]
        items = []
        for _, g in order[:ETYPE_CAP]:
            disp = g["spellings"].most_common(1)[0][0]
            items.append({
                "text": disp,
                "n_blocks": len(g["blocks"]),
                "n_docs": len(g["docs"]),
                "n_mentions": sum(g["spellings"].values()),
                "variants": [v for v, _ in g["spellings"].most_common(6)],
                "example": make_example(g),
            })
        by_etype[et] = {
            "etype": et,
            "distinct": len(order),
            "truncated": len(order) > ETYPE_CAP,
            "count": len(items),
            "items": items,
        }

    co_people = list(by_etype["person"]["items"][:50])

    out_cooc = {
        "subject": key,
        "qid": qid,
        "generated_from": "linked_jazz.sqlite",
        "count": sum(by_etype[e]["count"] for e in ETYPES),
        "method": "blocks = DISTINCT person_mentions.block_id for persons.qid = subject; "
                  "all entity_mentions in those same blocks, grouped by entities.etype. "
                  "Surface text is whitespace-collapsed and grouped case-insensitively; "
                  "the most frequent spelling is the display form. "
                  "Self-matches removed from the person list by testing the entity text "
                  "(and entities.canonical) against that document's own "
                  "persons.surface_forms/canonical alias set for the subject. "
                  f"Each etype list capped at {ETYPE_CAP} entries. " + SPEAKER_ROLE_METHOD,
        "n_subject_blocks": len(subject_block_ids),
        "n_entity_mentions_in_those_blocks": len(ent_rows),
        "n_self_matches_excluded": n_self_excluded,
        "etypes": ETYPES,
        "by_etype": by_etype,
        "musical_works": by_etype["musical_work"],
        "venues": by_etype["venue"],
        "co_mentioned_people_top50": co_people,
        "items": [by_etype[e] for e in sorted(
            ETYPES, key=lambda e: -by_etype[e]["distinct"])],
    }

    stats_out[key] = {
        "headline": headline,
        "top_works": by_etype["musical_work"]["items"][:10],
        "top_venues": by_etype["venue"]["items"][:10],
        "top_people": co_people[:10],
        "cooc": {e: (by_etype[e]["distinct"], by_etype[e]["truncated"]) for e in ETYPES},
        "self_excluded": n_self_excluded,
        "docs_count": len(doc_items),
        "n_interviewees": len(roster_items),
    }

    return out_profile, out_docs, out_cooc


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    return os.path.getsize(path)


def main():
    if not os.path.exists(DB_PATH):
        fail(f"database not found at {DB_PATH}")
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    collections = {r["collection"]: row_to_dict(r)
                   for r in con.execute("SELECT * FROM collections")}
    communities = {}
    for r in con.execute("SELECT * FROM communities"):
        c = row_to_dict(r)
        c["key_figures"] = jloads(c.get("key_figures"), [])
        communities[c["community_id"]] = c

    stats = {}
    sizes = []
    for subj in SUBJECTS:
        print(f"building {subj['key']} ({subj['qid']}) …")
        prof, docs, cooc = build_subject(con, subj, collections, communities, stats)
        base = os.path.join(OUT_ROOT, subj["key"])
        for name, obj in (("profile.json", prof), ("documents.json", docs),
                          ("cooccurrence.json", cooc)):
            p = os.path.join(base, name)
            sz = write_json(p, obj)
            sizes.append((p, obj.get("count"), sz))
    con.close()

    print("\n=== files written ===")
    for p, n, sz in sizes:
        print(f"  {p}  count={n}  {sz/1024:.1f} KB")

    for subj in SUBJECTS:
        k = subj["key"]
        s = stats[k]
        h = s["headline"]
        print(f"\n=== {subj['display']} ({subj['qid']}) — headline stats ===")
        print(f"  mentions            : {h['total_mentions']}")
        print(f"  documents           : {h['total_docs']}")
        print(f"  blocks mentioning   : {h['total_blocks_mentioning']}")
        print(f"  distinct interviewees who mention: {h['distinct_interviewees_who_mention']}")
        print(f"  classified relationships: {h['n_classified_relationships']} "
              f"(skipped rows {h['n_relationship_rows_skipped']})")
        print(f"  network edges       : {h['n_network_edges']}")
        y = h["interview_years"]
        print(f"  interview years     : {y['min']}–{y['max']} median {y['median']} "
              f"({y['n_docs_without_year']} undated)")
        print(f"  aliases             : {h['n_aliases']}   "
              f"name_reconciliation rows: {h['n_name_reconciliation_rows']}")
        print(f"  co-occ self-matches excluded: {s['self_excluded']}")
        print(f"  distinct entities by etype  : "
              + ", ".join(f"{e}={n}{'*' if t else ''}" for e, (n, t) in s["cooc"].items()))
        print(f"  -- top 10 musical works --")
        for i, it in enumerate(s["top_works"], 1):
            print(f"   {i:2d}. {it['text']!r}  blocks={it['n_blocks']} docs={it['n_docs']}")
        print(f"  -- top 10 venues --")
        for i, it in enumerate(s["top_venues"], 1):
            print(f"   {i:2d}. {it['text']!r}  blocks={it['n_blocks']} docs={it['n_docs']}")
        print(f"  -- top 10 co-mentioned people --")
        for i, it in enumerate(s["top_people"], 1):
            print(f"   {i:2d}. {it['text']!r}  blocks={it['n_blocks']} docs={it['n_docs']}")


if __name__ == "__main__":
    main()
