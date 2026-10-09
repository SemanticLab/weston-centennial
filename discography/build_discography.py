#!/usr/bin/env python3
"""Step 5 - assemble Randy Weston's discography and join it to the interviews.

WHAT COUNTS AS HIS. There is no "Randy Weston discography" article. Releases
come from (a) the Discography section of his biography -- every bullet, whether
or not the record has its own article -- and (b) album articles that link to him
(see harvest_discographies.py). A backlinked album is only admitted when its own
page credits him: in the Personnel section, on a track line, or in the prose.
`subject_credit` records which, and what the credit says.

For Liston the question about a record was "did she play on it or did she write
the charts". For Weston it is "is it his record, or did somebody record his
tune": he made 51 albums as leader and almost none as a sideman, but "Hi-Fly",
"Little Niles" and "Berkshire Blues" are on hundreds of other people's. So
`subject_role` is one of

    leader      his own record (his list says so, or Wikidata's performer does)
    sideman     he plays on someone else's record
    composer    someone recorded his tune; he was not in the studio
    listed_unverified / mentioned   see the credit review below

and every roster count that means "worked with him" is taken over leader +
sideman releases only -- a composer credit is not a session.

THE JOIN RUNS THREE WAYS. Each roster member carries what they said about him
(`quotes`, from the witnesses' interviews), what HE said about THEM (`he_said`,
from weston/his_words.json), and each release carries what he said about THAT
RECORD (`he_said_of_this_record`, from own_voice.json -> records): his 2009
interview is a walk through the records, which neither earlier build had.

Attribution rule for quotes about him (unchanged): a quote is attributed only
when the speaker is the interviewee and that interviewee resolves to exactly one
roster member -- by QID, or by an unambiguous name match. Documents with several
interviewees and single-token interviewee labels are left unattributed.

Writes:
  weston/discography.json            releases, with full credits
  weston/discography_personnel.json  the roster + the oral-history join
  shared/discography_summary.json
"""

import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wiki_common import parse_page  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "discography" / "raw"
LJ = "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite"

SUBJECT_QID = {"weston": "Q1371187"}
SUBJECT_NAME = {"weston": "Randy Weston"}
OWN_DOC = "Randy-Weston-Transcription-2020_0"

# release kind comes from the Wikidata description ("1959 studio album by ..."),
# because his article's sections say only leader / sideman
KIND_RULES = [
    (r"live album|recorded live|in concert|\bconcert\b|at newport|live at", "live"),
    (r"soundtrack|film score", "soundtrack"),
    (r"documentary|\bfilm\b", "film"),
    (r"compilation|box set|anthology", "compilation"),
    (r"studio album", "studio"),
    (r"\bsong\b|\bsingle\b", "single"),
]

ARRANGER = re.compile(r"arrang|conduct|orchestrat|musical director", re.I)
COMPOSER = re.compile(r"compos|written by|writer|songwrit", re.I)
PLAYER = re.compile(r"piano|pianist|keyboard|celest|harpsichord|\borgan\b|vocal|percussion", re.I)
# a credit line is his when it says Weston and is not the arranger Paul Weston
HIM = re.compile(r"\bWeston\b", re.I)
# ...nor his son Azzedin (congas on a dozen records), the drummer Calvin Weston, etc.
# and R. P. Weston, the music-hall songwriter ("With 'er 'ead Tucked Underneath 'er Arm")
NOT_HIM = re.compile(r"\b(Paul|P\.|R\.\s*P\.|Kim|Fitz|Azzedine?|Niles|(?:G\.\s*)?Calvin|Grant)\s*Weston\b", re.I)


def names_him(s):
    """Does this line name Randy Weston? Other Westons are removed first, so a
    line that names both ('Azzedin Weston, son of Randy Weston') still counts."""
    return bool(HIM.search(NOT_HIM.sub(" ", s or "")))


TUNE = re.compile(r'["“]\s*([^"”]+?)\s*["”]')
TUNE_ALIASES = {"hi fli": "hi fly", "hifly": "hi fly", "high fly": "hi fly"}


def tune_of(track_line):
    """'" Hi-Fly " ( Randy Weston ) - 3:58' -> ('hi fly', 'Hi-Fly')."""
    m = TUNE.search(track_line)
    if not m:
        return None, None
    title = re.sub(r"\s+", " ", m.group(1)).strip()
    k = norm(title)
    return TUNE_ALIASES.get(k, k), title
YEAR = re.compile(r"\b(19[2-9]\d|20[0-2]\d)\b")


def flags(blob, composer=False):
    return {"as_player": bool(PLAYER.search(blob)),
            "as_arranger": bool(ARRANGER.search(blob)),
            "as_composer": composer or bool(COMPOSER.search(blob))}


def classify_kind(desc, title):
    hay = f"{desc or ''} | {title}".lower()
    for pat, kind in KIND_RULES:
        if re.search(pat, hay):
            return kind
    return "album"


def subject_credit(album, page_title):
    """How does this release's own article credit Weston? -> dict.

    Order of trust: a Personnel line, then a track line, then prose. A track
    line that names him in the writer's parentheses -- '"Hi-Fly" (Randy
    Weston)' -- is a COMPOSER credit: someone recorded his tune, which is not
    evidence he was in the studio. Prose is the weakest: the sentence may be
    about something else entirely (a sideman's biography, a label's roster), so
    prose credits carry needs_review and the sentences themselves.
    """
    tr = [t for t in album["tracks"] if names_him(t)]
    lines = [p for p in album["personnel"] if names_him(p["name"])]
    if lines:
        roles, notes, raws = [], [], []
        for p in lines:
            for r in p["roles"]:
                if r and r.lower() != "personnel" and r not in roles:
                    roles.append(r)
            if p.get("note") and p["note"] not in notes:
                notes.append(p["note"])
            raws.append(p["raw"])
        f = flags(" ".join(roles + notes + raws), composer=bool(tr))
        return {"found_in": "personnel", "roles": roles, "note": "; ".join(notes),
                "raw": raws, "tracks_naming_him": tr[:12], "needs_review": False, **f}
    if tr:
        return {"found_in": "tracks", "roles": ["composer"],
                "note": f"{len(tr)} of {len(album['tracks'])} track lines name him",
                "raw": tr[:12], "tracks_naming_him": tr[:12], "needs_review": False,
                "as_player": False,
                "as_arranger": bool(ARRANGER.search(" ".join(tr))), "as_composer": True}
    doc = parse_page(page_title)
    if doc and not doc.get("missing"):
        soup = BeautifulSoup(doc["html"], "lxml")
        for junk in soup.select("sup.reference, style, .navbox, .reflist, .mw-editsection"):
            junk.decompose()
        hits = []
        for el in soup.find_all(["p", "li", "td", "th"]):
            if el.find(["p", "li", "td", "ul", "table"]):
                continue
            txt = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z\"])", txt):
                if names_him(sent) and sent not in hits:
                    hits.append(sent)
        if hits:
            return {"found_in": "prose", "roles": [], "note": "", "raw": [h[:500] for h in hits[:6]],
                    "tracks_naming_him": [], "needs_review": True, **flags(" ".join(hits))}
    return {"found_in": "none", "roles": [], "note": "", "raw": [], "tracks_naming_him": [],
            "needs_review": True, "as_player": False, "as_arranger": False, "as_composer": False}


def title_key(t):
    t = re.sub(r"\s*\((?:[^()]*\balbum|[^()]*\bsoundtrack)\)\s*$", "", t or "")
    return norm(t)


def load_interview_index():
    """doc_id -> {qids, labels}; and qid -> docs they were interviewed for."""
    con = sqlite3.connect(f"file:{LJ}?mode=ro", uri=True)
    docs = defaultdict(list)
    for doc_id, label, qid in con.execute(
            "select doc_id, label, qid from doc_interviewees"):
        docs[str(doc_id)].append({"label": label, "qid": qid or None})
    meta = {}
    for doc_id, title, coll, itv in con.execute(
            "select doc_id, title, collection, interviewee from documents"):
        meta[str(doc_id)] = {"title": title, "collection": coll}
        # documents.interviewee is a second, less reliable name for the same
        # person -- but it is the only place "Butter Jackson" (doc_interviewees,
        # no QID) is spelled "Quentin Jackson". Offered to the NAME matcher only,
        # as a QID-less row, so it can never override a reconciled interviewee;
        # where it is wrong (eight Rutgers docs name the interviewer, Patricia
        # Willard) it simply matches nobody on the roster.
        have = {norm(r["label"]) for r in docs[str(doc_id)]}
        if itv and norm(itv) not in have and not any(r["qid"] for r in docs[str(doc_id)]):
            docs[str(doc_id)].append({"label": itv, "qid": None})
    con.close()
    return docs, meta


def norm(s):
    """Fold a name for comparison: accents, punctuation, case."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def resolve_doc_person(rows, by_qid, by_name):
    """Which roster member is this document's interviewee? -> (key, how).

    Used for BOTH "was this person interviewed" and "did this person say
    something", so the two can never disagree -- Jimmy Owens was interviewed
    but his interviewee row carries no QID, and keying the interview list on
    QID alone left him marked as having spoken without having been interviewed.
    """
    withq = [i for i in rows if i["qid"]]
    if len(withq) == 1 and withq[0]["qid"] in by_qid:
        return by_qid[withq[0]["qid"]], "qid"
    if len(withq) > 1:
        return None, "multiple_interviewees"
    hits = set()
    for i in rows:
        n = norm(i["label"])
        if len(n.split()) < 2:      # "Jackson", "Labarbera" -- too ambiguous
            continue
        rev = " ".join(reversed(n.split()))   # surname-first documents
        for cand in (n, rev):
            if cand in by_name:
                hits.add(by_name[cand])
    if len(hits) == 1:
        return hits.pop(), "interviewee_name_match"
    return None, "interviewee_not_on_roster_or_ambiguous"


def load_quotes(subject, doc_itv, by_qid, by_name):
    """roster person_key -> the verified things that person said about him.

    Attribution is resolved against the ROSTER, not against all of Wikidata,
    because only roster members matter for this join. Two routes:

      qid   the document's single QID-bearing interviewee is on the roster.
      name  the interviewee was never reconciled to a QID (that is true of 45%
            of documents) but their name matches exactly one roster member.
            Also tries the reversed form: 13 documents store the interviewee
            surname-first ("Terry Clark" = Clark Terry).

    Single-token interviewee labels ("Jackson", "Labarbera") are refused --
    they are too collision-prone to attribute a public quote on.
    """
    said = defaultdict(lambda: {"blocks": [], "quotes": []})
    unattributed = Counter()
    methods = Counter()

    def attribute(doc_id):
        key, how = resolve_doc_person(doc_itv.get(str(doc_id), []), by_qid, by_name)
        if key:
            methods[how] += 1
        else:
            unattributed[how] += 1
        return key

    p = ROOT / subject / "enriched.json"
    if not p.exists():
        print("  (enriched.json not built yet -- the quote join is empty; re-run after "
              "extract/build_enriched.py)")
    for it in (json.loads(p.read_text(encoding="utf-8"))["items"] if p.exists() else []):
        if not it.get("is_about_subject") or it.get("speaker_role") != "interviewee":
            continue
        if it["doc_id"] == OWN_DOC:      # there the "interviewee" is Weston himself
            continue
        key = attribute(it["doc_id"])
        if not key:
            continue
        rec = said[key]
        rec["blocks"].append(it["block_id"])
        if it.get("pull_quote"):
            rec["quotes"].append({
                "block_id": it["block_id"], "quote": it["pull_quote"],
                "stance": it.get("stance"), "notable": it.get("notable") or 0,
                "summary": it.get("summary"), "source": "mention",
                "doc_id": it["doc_id"], "url": (it.get("doc") or {}).get("transcript_url"),
            })

    p = ROOT / subject / "recovered_evaluated.json"
    if p.exists():
        for it in json.loads(p.read_text(encoding="utf-8"))["items"]:
            if not it.get("is_about_subject"):
                continue
            key = attribute(it["doc_id"])
            if not key:
                continue
            rec = said[key]
            rec["blocks"].append(it["block_id"])
            if it.get("pull_quote"):
                rec["quotes"].append({
                    "block_id": it["block_id"], "quote": it["pull_quote"],
                    "stance": it.get("stance"), "notable": it.get("notable") or 0,
                    "summary": it.get("summary"), "source": "recovered",
                    "doc_id": it["doc_id"], "url": it.get("transcript_url"),
                })

    for rec in said.values():
        rec["quotes"].sort(key=lambda q: -q["notable"])
    return said, dict(unattributed), dict(methods)


def load_he_said():
    """qid / normalised name -> what Weston said about that person (his_words.json)."""
    p = ROOT / "weston" / "his_words.json"
    by_qid, by_name = {}, {}
    if not p.exists():
        return by_qid, by_name, False
    for it in json.loads(p.read_text(encoding="utf-8"))["items"]:
        if not it.get("is_person"):
            continue
        rec = {
            "relation": it.get("relation"), "direction": it.get("direction"),
            "basis": it.get("basis"), "tie": it.get("tie") or [],
            "summary": it.get("summary"), "one_liner": it.get("one_liner"),
            "his_quote": it.get("his_quote"), "his_quote_block_id": it.get("his_quote_block_id"),
            "interviewer_quote": it.get("interviewer_quote"),
            "instrument_or_role": it.get("instrument_or_role"),
            "name_in_interview": it.get("as_named_in_interview"),
            "notable": it.get("notable") or 0,
            "url": it.get("his_quote_url") or it.get("url"),
        }
        if it.get("qid"):
            by_qid[it["qid"]] = rec
        # his_words names are the reader's corrected spellings, so "Kenny Durham"
        # in the transcript still meets Kenny Dorham on the record
        for nm in [it.get("name"), it.get("as_named_in_interview"), *(it.get("also_named") or [])]:
            n = norm(nm or "")
            if len(n.split()) >= 2:
                by_name.setdefault(n, rec)
    return by_qid, by_name, True


def main():
    subject, qid_subj = "weston", SUBJECT_QID["weston"]
    albums = json.loads((RAW / "albums.json").read_text(encoding="utf-8"))["albums"]
    ents = json.loads((RAW / "entities.json").read_text(encoding="utf-8"))["entities"]
    people = json.loads((RAW / "personnel_resolved.json").read_text(
        encoding="utf-8"))["people"]
    rows = json.loads((RAW / "weston_rows.json").read_text(encoding="utf-8"))["rows"]
    doc_itv, doc_meta = load_interview_index()

    # ---- which release articles, and how each was found
    found = {}     # canonical article title -> {sources, bullets}
    for v in ents.values():
        if v["bucket"] != "release":
            continue
        m = found.setdefault(v["title"], {"sources": set(), "bullets": []})
        for sn in v["seen_in"]:
            # in a discography bullet only the italic link is the record; the
            # other links on the line are the leader
            if sn.get("source") == "discography_section" and not sn.get("italic"):
                continue
            m["sources"].add(sn.get("source") or "discography_section")
            if sn.get("source") == "discography_section":
                m["bullets"].append(sn)

    ent_by_title = {v["title"]: v for v in ents.values() if v["bucket"] == "release"}
    releases, rejected = [], []
    for title, m in sorted(found.items()):
        a = albums.get(title)
        if not a:
            continue
        info = a["infobox"]
        credit = subject_credit(a, title)
        listed = "discography_section" in m["sources"]
        if not listed and credit["found_in"] == "none":
            rejected.append({"title": title, "qid": a["qid"],
                             "reason": "links to his article but its own page does not credit him"})
            continue
        b = m["bullets"][0] if m["bullets"] else {}
        section = b.get("section") or ""
        his_by_wikidata = qid_subj in (ent_by_title.get(title, {}).get("performers") or [])
        if listed and re.search(r"leader", section, re.I):
            role = "leader"
        elif his_by_wikidata and credit["found_in"] in ("personnel", "none", "prose"):
            role = "leader"         # Wikidata's performer (P175) is Weston
        elif credit["roles"] and all(r.lower() == "cast" for r in credit["roles"]):
            role = "appears_on_screen"      # archival footage in a documentary
        elif credit["found_in"] == "personnel":
            role = "sideman"        # a personnel line on someone else's record
        elif credit["as_composer"]:
            role = "composer"
        elif listed:
            role = "sideman"       # his article files it under "As sideman"
        else:
            role = "mentioned"
        if role == "leader" and credit["found_in"] in ("none", "prose"):
            credit["needs_review"] = False      # it is his own record
        year = (b.get("year")
                or next((d[:4] for d in a["publication_dates"] if d[:4].isdigit() and d[:4] != "0000"), None)
                or next(iter(YEAR.findall((info.get("released") or {}).get("text") or "")), None)
                or next(iter(YEAR.findall((info.get("recorded") or {}).get("text") or "")), None)
                or next(iter(YEAR.findall(a["description"] or "")), None))
        releases.append({
            "title": title,
            "qid": a["qid"],
            "has_article": True,
            "kind": classify_kind(a["description"], title),
            "subject_role": role,
            "subject_credit": credit,
            "listed_in_his_discography": listed,
            "found_via": sorted(m["sources"]),
            "leader": b.get("leader_text"),
            "note": b.get("note_text"),
            "performer_is_subject_on_wikidata": his_by_wikidata,
            "year": year,
            "sections": sorted({x.get("section") for x in m["bullets"] if x.get("section")}),
            "wikipedia_url": a["wikipedia_url"],
            "wikidata_url": a["wikidata_url"],
            "description": a["description"],
            "released": (info.get("released") or {}).get("text"),
            "recorded": (info.get("recorded") or {}).get("text"),
            "studio": (info.get("studio") or {}).get("text"),
            "venue": (info.get("venue") or {}).get("text"),
            "label": (info.get("label") or {}).get("text") or b.get("label_text"),
            "genre": (info.get("genre") or {}).get("text"),
            "length": (info.get("length") or {}).get("text"),
            "producer": (info.get("producer") or {}).get("text"),
            "publication_dates": a["publication_dates"],
            "musicbrainz": a["musicbrainz"],
            "image": a["image"],
            "discography_row": b.get("row_text") or "",
            "track_count": len(a["tracks"]),
            "tracks": a["tracks"],
            "personnel_count": a["personnel_count"],
            "personnel": [{
                "name": p["name"], "person_key": p.get("person_key"),
                "qid": p.get("person_qid"), "identified_via": p.get("identified_via"),
                "roles": p["roles"], "note": p["note"],
                "credit_type": p["credit_type"], "group": p["group"],
            } for p in a["personnel"]],
            "session_notes": a["session_notes"],
        })

    # ---- prose-only and uncredited releases, as judged by a reader
    # (discography/raw/credit_review_output.json -- an Opus subagent given the
    # album page's own sentences; see the README). "no" = he is only mentioned
    # there, so the release leaves the discography; "yes" = the prose is a real
    # credit; "unverified" = his biography lists it, the album page is silent.
    mentioned_only = []
    rp = RAW / "credit_review_output.json"
    if rp.exists():
        rv = json.loads(rp.read_text(encoding="utf-8"))
        verdict = {i["title"]: i for i in rv["items"]}
        keep = []
        for rel in releases:
            v = verdict.get(rel["title"])
            if v is None:
                keep.append(rel)
                continue
            c = rel["subject_credit"]
            c["review"] = {k: v.get(k) for k in ("credited_on_this_release", "role", "scope",
                                                  "evidence", "reasoning", "confidence")}
            c["review"]["judged_by"] = rv.get("judged_by")
            if v["credited_on_this_release"] == "no":
                mentioned_only.append({"title": rel["title"], "qid": rel["qid"], "year": rel["year"],
                                       "wikipedia_url": rel["wikipedia_url"],
                                       "reason": v["reasoning"], "evidence": v["evidence"]})
                continue
            if v["credited_on_this_release"] == "yes":
                c["needs_review"] = False
                role = v["role"]
                c["as_arranger"] = role == "arranger"
                c["as_player"] = role in ("sideman", "leader")
                c["as_composer"] = role in ("composer", "sampled")
                c["note"] = v.get("scope") or c["note"]
                rel["subject_role"] = role
            else:   # unverified: keep where his biography files it, and say so
                c["needs_review"] = True
                c["as_arranger"] = c["as_player"] = c["as_composer"] = False
                rel["subject_role"] = "listed_unverified"
            keep.append(rel)
        releases = keep

    # ---- discography bullets whose record has no article of its own
    release_titles = {v["requested_title"] for v in ents.values() if v["bucket"] == "release"}
    by_key = {}
    for rel in releases:
        by_key.setdefault(title_key(rel["title"]), rel)
    unlinked, merged_bullets = [], 0
    for r in rows:
        if r.get("source") != "discography_section":
            continue
        links = [l for c in r["cells"] for l in c["links"]]
        if any(l["italic"] and l["title"] in release_titles for l in links):
            continue
        # the bullet is plain text on his page, but the record may still have an
        # article that the backlink sweep found: fold the bullet into it
        k = norm(r["title_text"] or "")
        hit = by_key.get(k) or next(
            (rel for kk, rel in by_key.items()
             if k and len(k.split()) >= 2 and (kk.endswith(" " + k) or kk.startswith(k + " "))), None)
        if hit is not None:
            hit["listed_in_his_discography"] = True
            hit["found_via"] = sorted(set(hit["found_via"]) | {"discography_section"})
            hit["leader"] = hit["leader"] or r["leader_text"]
            hit["year"] = r["year"] or hit["year"]
            hit["discography_row"] = hit["discography_row"] or r["text"]
            hit["sections"] = sorted(set(hit["sections"]) | {r["section"]})
            if hit["subject_role"] in ("mentioned", "composer"):
                hit["subject_role"] = "leader" if re.search(r"leader", r["section"], re.I) else "sideman"
            hit["note"] = hit.get("note") or r.get("note_text")
            merged_bullets += 1
            continue
        leaders = [l["title"] for l in links if not l["italic"]]
        unlinked.append({
            "title": r["title_text"] or r["text"],
            "qid": None, "has_article": False, "kind": "album",
            "subject_role": "leader" if re.search(r"leader", r["section"], re.I) else "sideman",
            "subject_credit": {"found_in": "his_discography_list_only", "roles": [], "note": "",
                               "raw": [r["text"]], "tracks_naming_him": [], "needs_review": False,
                               "as_arranger": False, "as_player": False, "as_composer": False},
            "listed_in_his_discography": True, "found_via": ["discography_section"],
            "leader": r["leader_text"], "leader_articles": leaders, "note": r.get("note_text"),
            "performer_is_subject_on_wikidata": False,
            "year": r["year"], "sections": [r["section"]],
            "wikipedia_url": None, "wikidata_url": None, "description": None,
            "released": r["year"], "recorded": None, "studio": None, "venue": None,
            "label": r["label_text"], "genre": None, "length": None, "producer": None,
            "publication_dates": [], "musicbrainz": None, "image": None,
            "discography_row": r["text"], "track_count": 0, "tracks": [],
            "personnel_count": 0, "personnel": [], "session_notes": [],
        })
    releases += unlinked
    releases.sort(key=lambda r: (r["year"] or "9999", r["title"]))

    # ---- MusicBrainz ids for his records that have no article (and so no
    # Wikidata P436): an exact title match against his own release groups, or a
    # title that is the other plus a subtitle ("Self Portraits" / "Self
    # Portraits: The Last Day"). Two groups with one title are split by year.
    mbp = RAW / "musicbrainz_release_groups.json"
    n_mb = 0
    if mbp.exists():
        def tkey(t):
            return " ".join(w for w in norm(t).split() if w not in ("the", "and", "a"))
        groups = json.loads(mbp.read_text(encoding="utf-8"))["release_groups"]
        for rel in releases:
            rel["musicbrainz_matched_by"] = "wikidata" if rel["musicbrainz"] else None
            if rel["musicbrainz"] or rel["subject_role"] != "leader":
                continue
            k = tkey(title_key(rel["title"]) or rel["title"])
            hits = [g for g in groups if tkey(g["title"]) == k]
            if not hits and len(k.split()) >= 2:
                hits = [g for g in groups if len(tkey(g["title"]).split()) >= 2
                        and (k.startswith(tkey(g["title"]) + " ") or tkey(g["title"]).startswith(k + " "))]
            hits = [g for g in hits if "Compilation" not in g["secondary_types"]]
            if len(hits) > 1 and rel["year"]:
                hits.sort(key=lambda g: abs(int((g["first_release_date"] or "9999")[:4]) - int(rel["year"])))
                hits = hits[:1]
            if len(hits) == 1:
                rel["musicbrainz"] = hits[0]["mbid"]
                rel["musicbrainz_matched_by"] = "title"
                rel["musicbrainz_title"] = hits[0]["title"]
                n_mb += 1
    for rel in releases:
        rel.setdefault("musicbrainz_matched_by", "wikidata" if rel["musicbrainz"] else None)

    # ---- what he said about each record, in his 2009 interview
    ovp = ROOT / subject / "own_voice.json"
    n_rec_joined, rec_unjoined = 0, []
    if ovp.exists():
        by_title = {}
        for rel in releases:
            if rel["subject_role"] == "leader":
                by_title.setdefault(title_key(rel["title"]), rel)
        for rec in json.loads(ovp.read_text(encoding="utf-8"))["records"]["items"]:
            if rec["kind"] not in ("album", "live_album", "session", "dvd"):
                continue
            k = norm(rec["title"])
            hit = by_title.get(k) or next(
                (rel for kk, rel in by_title.items() if k and len(k.split()) >= 2
                 and (kk.startswith(k + " ") or k.startswith(kk + " "))), None)
            if hit is None:
                rec_unjoined.append(rec["title"])
                continue
            hit["he_said_of_this_record"] = {k2: rec[k2] for k2 in (
                "key", "title_as_transcribed", "year_as_stated", "what_he_says", "title_meaning",
                "pull_quote", "pull_quote_block_id", "pull_quote_url", "more_quotes",
                "personnel_as_stated", "pieces_named", "discrepancies", "notable", "url")}
            n_rec_joined += 1
    for rel in releases:
        rel.setdefault("he_said_of_this_record", None)

    # ---- his tunes on other people's records
    from wiki_common import wd_entities  # noqa: E402
    perf_qids = sorted({q for r in releases if r["subject_role"] in ("composer", "sampled")
                        for q in (albums.get(r["title"]) or {}).get("performers_qids") or []})
    perf = wd_entities(perf_qids)
    tunes = {}
    for r in releases:
        if r["subject_role"] not in ("composer", "sampled"):
            continue
        performers = [{"qid": q, "name": (perf.get(q) or {}).get("label")}
                      for q in (albums.get(r["title"]) or {}).get("performers_qids") or []]
        lines = r["subject_credit"]["tracks_naming_him"] or [
            x for x in r["subject_credit"]["raw"] if TUNE.search(x)]
        seen = set()
        for line in lines:
            k, title = tune_of(line)
            if not k or k in seen:
                continue
            seen.add(k)
            t = tunes.setdefault(k, {"key": k, "title": title, "spellings": Counter(), "recordings": []})
            t["spellings"][title] += 1
            t["recordings"].append({
                "release": r["title"], "year": r["year"], "performers": performers,
                "description": r["description"], "wikipedia_url": r["wikipedia_url"],
                "qid": r["qid"], "track_line": line, "how": r["subject_role"],
                "needs_review": r["subject_credit"]["needs_review"]})
    tune_list = []
    for t in tunes.values():
        t["title"] = t["spellings"].most_common(1)[0][0]
        t["spellings"] = sorted(t["spellings"])
        t["recordings"].sort(key=lambda x: (x["year"] or "9999", x["release"]))
        t["count"] = len(t["recordings"])
        t["first_year"] = next((x["year"] for x in t["recordings"] if x["year"]), None)
        t["last_year"] = next((x["year"] for x in reversed(t["recordings"]) if x["year"]), None)
        tune_list.append(t)
    tune_list.sort(key=lambda t: (-t["count"], t["title"]))
    (ROOT / subject / "compositions.json").write_text(json.dumps({
        "subject": subject, "subject_qid": qid_subj,
        "source": "track lines of album articles that link to him and credit him as a writer",
        "count": len(tune_list),
        "recordings": sum(t["count"] for t in tune_list),
        "method": (
            "His tunes on OTHER people's records, as English Wikipedia's album articles document "
            "them: every release whose track listing names him as a writer and on which he does "
            "not play. Grouped by tune title (the first quoted string on the track line; 'Hi Fly' "
            "/ 'Hi-Fli' folded into 'Hi-Fly'). This is a floor, not a count -- only albums with "
            "an article that links to him are seen, and most recordings of 'Hi-Fly' have neither. "
            "A track line may carry co-writers (Jon Hendricks's lyrics to 'Babe's Blues' and "
            "'Pretty Strange'); it is kept verbatim in track_line."),
        "items": tune_list}, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- credits a script cannot settle: package them for a reader
    review = []
    for r in releases:
        c = r["subject_credit"]
        if not c["needs_review"] or c.get("review"):
            continue
        a = albums.get(r["title"]) or {}
        review.append({
            "title": r["title"], "qid": r["qid"], "year": r["year"],
            "description": r["description"], "wikipedia_url": r["wikipedia_url"],
            "role_by_rule": r["subject_role"], "credit_found_in": c["found_in"],
            "sentences_naming_him": c["raw"],
            "listed_in_his_discography": r["listed_in_his_discography"],
            "personnel": [f"{p['name']} - {', '.join(p['roles'])}" for p in a.get("personnel") or []],
            "tracks": a.get("tracks") or [],
        })
    (RAW / "credit_review_input.json").write_text(json.dumps(
        {"subject": subject, "count": len(review), "items": review},
        ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- roster: everyone credited on the releases with an article.
    # A composer credit is not a session: the people on records that merely
    # include "Hi-Fly" never worked with him, so the roster is built from the
    # records he led or played on.
    SESSION_ROLES = ("leader", "sideman")
    wanted = {r["title"] for r in releases if r["has_article"] and r["subject_role"] in SESSION_ROLES}
    members = {key: e for key, e in people.items()
               if e.get("qid") != qid_subj
               and any(c["album"] in wanted for c in e["credits"])}
    by_qid = {e["qid"]: key for key, e in members.items() if e["qid"]}
    by_name = {}
    for key, e in members.items():
        for v in [e["name"], *e["name_variants"]]:
            n = norm(v)
            if len(n.split()) >= 2:
                by_name[n] = None if n in by_name and by_name[n] != key else key
    by_name = {k: v for k, v in by_name.items() if v}

    said, unattributed, methods = load_quotes(subject, doc_itv, by_qid, by_name)
    he_qid, he_name, have_he = load_he_said()

    itv_by_key = defaultdict(list)
    for doc_id, rws in doc_itv.items():
        if doc_id == OWN_DOC:
            continue
        key, how = resolve_doc_person(rws, by_qid, by_name)
        if key:
            itv_by_key[key].append({
                "doc_id": doc_id, "matched_via": how,
                "label": rws[0]["label"] if rws else None,
                **doc_meta.get(doc_id, {})})

    roster = []
    for key, e in members.items():
        creds = [c for c in e["credits"] if c["album"] in wanted]
        itv = itv_by_key.get(key, [])
        spoke = said.get(key)
        he = he_qid.get(e["qid"]) if e["qid"] else None
        if he is None:
            for v in [e["name"], *e["name_variants"]]:
                he = he_name.get(norm(v))
                if he:
                    break
        roster.append({
            "person_key": key,
            "qid": e["qid"],
            "name": e["name"],
            "identified_via": e["identified_via"],
            "description": e["description"],
            "wikipedia": e["wikipedia"],
            "birth": e["birth"], "death": e["death"], "image": e["image"],
            "name_variants": e["name_variants"],
            "instruments": sorted({r for c in creds for r in c["roles"]}),
            "album_count": len({c["album"] for c in creds}),
            "albums": sorted({c["album"] for c in creds}),
            "credit_type": "musician" if any(
                c["credit_type"] == "musician" for c in creds) else "technical",
            # ---- the oral-history join, both directions ----
            "interviewed_in_corpus": bool(itv),
            "interviews": itv,
            "said_about_subject": bool(spoke),
            "blocks_about_subject": len(spoke["blocks"]) if spoke else 0,
            "quotes": (spoke["quotes"][:8] if spoke else []),
            "he_spoke_of_them": bool(he),
            "he_said": he,
        })
    roster.sort(key=lambda p: (-p["blocks_about_subject"], -bool(p["he_spoke_of_them"]),
                               -p["album_count"], p["name"]))

    played_and_spoke = [p for p in roster if p["said_about_subject"]]
    played_and_interviewed = [p for p in roster if p["interviewed_in_corpus"]]
    bandmates_spoke = [p for p in played_and_spoke if p["credit_type"] == "musician"]
    writers_spoke = [p for p in played_and_spoke if p["credit_type"] == "technical"]
    he_spoke = [p for p in roster if p["he_spoke_of_them"]]
    both_ways = [p for p in roster if p["he_spoke_of_them"] and p["said_about_subject"]]

    with_article = [r for r in releases if r["has_article"]]
    stats = {
        "releases": len(releases),
        "releases_with_article": len(with_article),
        "releases_listed_without_article": len(unlinked),
        "from_his_discography_section": sum(1 for r in releases if r["listed_in_his_discography"]),
        "musicbrainz_ids": {"from_wikidata": sum(1 for r in releases if r["musicbrainz_matched_by"] == "wikidata"),
                            "by_title_match": n_mb,
                            "leader_releases_without": sorted(r["title"] for r in releases
                                                              if r["subject_role"] == "leader" and not r["musicbrainz"])},
        "records_he_discussed_in_his_interview": n_rec_joined,
        "records_he_discussed_not_in_this_discography": rec_unjoined,
        "found_only_by_backlink": sum(1 for r in releases if not r["listed_in_his_discography"]),
        "backlinked_releases_rejected_no_credit": len(rejected),
        "releases_where_he_is_only_mentioned": [m["title"] for m in mentioned_only],
        "by_kind": dict(Counter(r["kind"] for r in releases)),
        "by_subject_role": dict(Counter(r["subject_role"] for r in releases)),
        "credit_found_in": dict(Counter(r["subject_credit"]["found_in"] for r in releases)),
        "credited_as_arranger_or_conductor": sum(
            1 for r in releases if r["subject_credit"]["as_arranger"]),
        "credited_as_composer": sum(1 for r in releases if r["subject_credit"]["as_composer"]),
        "his_tunes_on_others_records": {"tunes": len(tune_list),
                                        "recordings": sum(t["count"] for t in tune_list),
                                        "top": [[t["title"], t["count"]] for t in tune_list[:10]]},
        "credits_needing_review": sorted(r["title"] for r in releases
                                         if r["subject_credit"]["needs_review"]),
        "unlinked_bullets_merged_into_articles": merged_bullets,
        "credited_as_player": sum(1 for r in releases if r["subject_credit"]["as_player"]),
        "credited_as_both": sum(1 for r in releases if r["subject_credit"]["as_arranger"]
                                and r["subject_credit"]["as_player"]),
        "total_credits": sum(r["personnel_count"] for r in releases),
        "roster_size": len(roster),
        "roster_with_qid": sum(1 for p in roster if p["qid"]),
        "roster_interviewed_in_corpus": len(played_and_interviewed),
        "roster_who_spoke_about_subject": len(played_and_spoke),
        "musicians_who_played_and_spoke": len(bandmates_spoke),
        "critics_producers_who_were_credited_and_spoke": len(writers_spoke),
        "critics_producers_named": sorted(p["name"] for p in writers_spoke),
        "his_words_available": have_he,
        "roster_he_spoke_of": len(he_spoke),
        "roster_both_directions": len(both_ways),
        "roster_both_directions_named": sorted(p["name"] for p in both_ways),
        "quote_blocks_from_credited_people": sum(p["blocks_about_subject"] for p in roster),
        "quote_blocks_from_musicians": sum(p["blocks_about_subject"] for p in bandmates_spoke),
        "attribution_methods": methods,
        "unattributed_quote_blocks": unattributed,
    }

    base = {"subject": subject, "subject_qid": qid_subj,
            "subject_name": SUBJECT_NAME[subject],
            "source": "en.wikipedia.org 'Randy Weston' (Discography section) + album "
                      "articles that link to him; entities typed against Wikidata"}
    (ROOT / subject / "discography.json").write_text(
        json.dumps({**base, "count": len(releases), "stats": stats,
                    "rejected_backlinks": rejected,
                    "mentioned_only": mentioned_only,
                    "releases": releases}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    (ROOT / subject / "discography_personnel.json").write_text(
        json.dumps({**base, "count": len(roster),
                    "join_rule": "quote attributed only when the speaker is "
                                 "the interviewee and the document has exactly "
                                 "one QID-bearing interviewee; he_said is joined by "
                                 "QID, else by an exact normalised full-name match",
                    "stats": stats, "people": roster},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n=== {subject} ===")
    print(f" releases {len(releases)}  ({len(with_article)} with an article, "
          f"{len(unlinked)} listed without one; {stats['found_only_by_backlink']} found only "
          f"by backlink; {len(rejected)} backlinked albums rejected)")
    print(f" kinds {stats['by_kind']}")
    print(f" his role {stats['by_subject_role']}   credit found in {stats['credit_found_in']}")
    print(f" as arranger/conductor {stats['credited_as_arranger_or_conductor']}"
          f"   as composer {stats['credited_as_composer']}"
          f"   as player {stats['credited_as_player']}   player+arranger {stats['credited_as_both']}")
    print(f" needs review: {stats['credits_needing_review']}")
    print(f" credits {stats['total_credits']}  roster {len(roster)} "
          f"({stats['roster_with_qid']} with QID)")
    print(f" MusicBrainz ids: {stats['musicbrainz_ids']['from_wikidata']} from Wikidata, {n_mb} by title; "
          f"his own records still without: {stats['musicbrainz_ids']['leader_releases_without']}")
    print(f" records he talks about in his interview: {n_rec_joined} joined, "
          f"not in the discography: {rec_unjoined}")
    print(f" credited on a record with him AND interviewed in the corpus: "
          f"{len(played_and_interviewed)}")
    print(f" ... AND said something about him on the record: {len(played_and_spoke)}  "
          f"({len(bandmates_spoke)} musicians, {len(writers_spoke)} critics/producers)")
    print(f" he spoke of them: {len(he_spoke)}   both directions: {len(both_ways)} "
          f"{stats['roster_both_directions_named']}")
    print(f" attribution: {methods}")
    print(f" unattributed: {unattributed}")
    print(" top musician-witnesses:")
    for p in bandmates_spoke[:12]:
        print(f"   {p['blocks_about_subject']:3} blocks / {p['album_count']:3} albums  "
              f"{p['name'][:28]:30} {p['qid']}")
    print(f" his tunes on other people's records: {len(tune_list)} tunes, "
          f"{sum(t['count'] for t in tune_list)} recordings; top: "
          f"{[(t['title'], t['count']) for t in tune_list[:8]]}")
    print(f" credits for a reader to settle: {[x['title'] for x in review]}")
    if rejected:
        print(f" rejected backlinks: {len(rejected)} (albums that link to him only through a "
              f"sideman's navbox), e.g. {[r['title'] for r in rejected[:5]]}")

    (ROOT / "shared").mkdir(exist_ok=True)
    (ROOT / "shared" / "discography_summary.json").write_text(
        json.dumps({subject: stats}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
