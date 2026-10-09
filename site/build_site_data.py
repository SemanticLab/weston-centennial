#!/usr/bin/env python3
"""Build the page bundle: docs/data.json, docs/transcripts.json and the images
the page shows.

Reads the judged layers under weston/ and shared/, plus one hand-authored file
in this directory (editorial.json), and writes everything the page in docs/
needs. The page itself (docs/index.html, docs/app.js, docs/style.css) is static
and is not generated; nor are its two own images, docs/img/weston.jpg (the hero
photograph) and docs/img/linked-jazz.png (the mark), which came with the design.

What the page shows, and from where:
  hero           profile.json, biography_sources.json (birth and death),
                 own_voice.json -> self (the top-ranked quote); editorial.json
  his words      own_voice.json -> self, in the category pass's sections
  journeys       own_voice.json -> journeys
  records        own_voice.json -> records; discography.json for the list of
                 every record under his name, with sleeves from cover_art.json
  compositions   compositions.json: his tunes on other people's records
  people         his_words.json: the people he spoke of, with a verified quote
  witnesses      witnesses.json, filtered: only people who spoke themselves and
                 have a verbatim lead quote; editorial.json for the rest
  network        people.json: who is linked to him in which direction
  passages       docs/transcripts.json: the transcript text behind every quote,
                 opened in place by the page. His own interview goes in whole;
                 each witness's interview as a window around the quoted turn,
                 read from linked_jazz.sqlite. Each carries the archive's own
                 URL -- the page links to the original, not to a reader.
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "extract"))
import subject as SUBJ  # noqa: E402

ROOT = Path(SUBJ.ROOT)
D = ROOT / SUBJ.KEY
OUT = ROOT / "docs"
DB = SUBJ.DB

# archive name as a heading, and as the object of "Original transcript at ..."
ARCHIVES = {"si": ("Smithsonian Jazz Oral History Program", "the Smithsonian"),
            "rutgers": ("Rutgers Institute of Jazz Studies", "Rutgers"),
            "hamilton": ("Hamilton College, Fillius Jazz Archive", "Hamilton College")}
SPOKEN = ("dialogue", "prose", "note", "stage_direction")
# a witness's passage: at least this much either side of the quoted turn
WIN_MIN_BLOCKS, WIN_MIN_CHARS, WIN_MAX_BLOCKS, WIN_MAX_CHARS = 10, 3000, 16, 8000
# page furniture the Hamilton PDFs leave at the end of a turn
FOOTER = re.compile(
    r"(?:©\s*Fillius\s+Jazz\s+Archive[^A-Za-z]*(?:-\s*\d+\s*-)?|"
    r"Fillius\s+Jazz\s+Archive,\s*Hamilton\s+College[^.]*\.?|"
    r"-\s*\d+\s*-)\s*$", re.I)
JOURNEY_KINDS = {"concert": "Concert", "festival": "Festival", "residency": "Residency",
                 "ceremony": "Ceremony", "journey": "Journey", "film_shoot": "Film shoot",
                 "home": "Home"}
RECORD_KINDS = {"album": "Album", "live_album": "Live album", "composition": "Composition",
                "session": "Session", "film": "Film", "dvd": "DVD"}
# a family tie or a staff role is shown in place of the relation vocabulary's "none"
TIE_LABELS = {"family": "family", "spouse": "married to", "teacher": "taught by",
              "recording_staff": "recorded by", "interviewer": "interviewed by"}
# the page's first view of each list: this many, chosen by the reader's grade,
# kept in the list's own order; "show all" opens the rest
FIRST = {"own": 3, "journeys": 8, "records": 6, "people": 8, "witnesses": 8, "tunes": 10}
# portraits the image pass flagged are not shown (Oliver Nelson's was a car, once)
BAD_IMAGE_FLAGS = {"not_commons_licence_unverified", "picked_from_category_not_curated"}
NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                "seventeen", "eighteen", "nineteen", "twenty"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
        shutil.copyfile(src, dst)


def strip_album(title):
    """'Hi-Fly (Jaki Byard album)' -> 'Hi-Fly'."""
    return re.sub(r"\s*\((?:[^()]* )?album\)$", "", title)


def long_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{MONTHS[m - 1]} {d}, {y}"


# ------------------------------------------------------------------ passages
def clean(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    prev = None
    while prev != text:
        prev = text
        text = FOOTER.sub("", text).strip()
    return text


def turn(block_id, page, kind, speaker, text):
    return {"i": block_id, "p": page, "s": (speaker or "").strip().rstrip(":"),
            "t": clean(text), **({"n": 1} if kind in ("note", "stage_direction") else {})}


def doc_entry(collection, title, url, blocks, complete, interviewer=None, year=None):
    archive, at = ARCHIVES[collection]
    return {"title": title, "archive": archive, "at": at, "url": url,
            "pdf": url.lower().split("?")[0].endswith(".pdf"),
            "interviewer": interviewer, "year": year,
            "complete": complete, "blocks": [b for b in blocks if b["t"]]}


def own_transcript(own):
    d = own["doc"]
    blocks = [turn(b["block_id"], b["page"], b["type"], b["speaker_effective"], b["text"])
              for b in own["items"] if b["type"] in SPOKEN]
    return doc_entry(d["collection"], d["title"], d["source_url"], blocks, True,
                     SUBJ.INTERVIEWER["name"], SUBJ.OWN_DOC_YEAR)


# Smithsonian transcripts label speakers by surname only; the interviewer is
# named only where the name is known in full
KNOWN_INTERVIEWERS = {"Liston_Melba_Interview_Transcription": "Clora Bryant"}


def interviewer_of(db, doc_id, interviewee, url):
    """Who asked the questions: the Smithsonian records list the speakers (by
    surname, mostly), the Hamilton object URLs carry 'interviewed-<name>'."""
    if doc_id in KNOWN_INTERVIEWERS:
        return KNOWN_INTERVIEWERS[doc_id]
    meta = json.loads(db.execute("select meta_json from documents where doc_id=?",
                                 (doc_id,)).fetchone()[0] or "{}")
    others = [s for s in meta.get("speakers") or []
              if s != interviewee and s != "Ken Kimery" and " " in s.strip()]
    if others:
        return others[0]
    m = re.search(r"interviewed-([a-z]+)-([a-z]+)", url or "")
    return f"{m.group(1).title()} {m.group(2).title()}" if m else None


def witness_transcript(db, row):
    """The turns around a witness's lead quote, from the corpus."""
    doc_id = row["doc"]["doc_id"]
    coll, title, url, year = db.execute(
        "select collection, title, source_url, year from documents where doc_id=?", (doc_id,)).fetchone()
    rows = db.execute("select block_id, page, type, speaker, text from blocks where doc_id=? "
                      "order by page, block", (doc_id,)).fetchall()
    rows = [r for r in rows if r[2] in SPOKEN]
    at = [r[0] for r in rows].index(row["lead_block_id"])

    def walk(seq):
        out, chars = [], 0
        for r in seq:
            if len(out) >= WIN_MAX_BLOCKS or chars >= WIN_MAX_CHARS:
                break
            if len(out) >= WIN_MIN_BLOCKS and chars >= WIN_MIN_CHARS:
                break
            out.append(r)
            chars += len(r[4] or "")
        return out

    window = walk(rows[:at][::-1])[::-1] + [rows[at]] + walk(rows[at + 1:])
    if coll == "si":       # several Smithsonian titles are stored surname-first
        title = f"{row['name']} — Smithsonian Jazz Oral History"
    title = re.sub(r"^\d+_", "", title)
    # the Hamilton years are in the record; the Smithsonian PDFs carry none
    year = year if coll != "si" or year is None or year < 2015 else None
    return doc_entry(coll, title, url, [turn(*r) for r in window], False,
                     interviewer_of(db, doc_id, row["name"], url), year)


def source_line(t):
    """'Hamilton College, Fillius Jazz Archive, interviewed by Monk Rowe, 1999'."""
    parts = [t["archive"]]
    if t["interviewer"]:
        parts.append(f"interviewed by {t['interviewer']}")
    if t["year"]:
        parts.append(str(t["year"]))
    return ", ".join(parts)


# ------------------------------------------------------------------ verification
class Blocks:
    """His own interview, block by block, to re-check every quote the page
    shows against the text it will open."""

    def __init__(self, own):
        self.by_id = {b["block_id"]: b for b in own["items"]}
        self.failed = 0

    def marks(self, quote, block_ids, after=None, role="subject"):
        """The pieces of `quote` to highlight, one per block. A quote that runs
        across a page break is two pieces; each must sit in its block, spoken
        by him."""
        if len(block_ids) == 1:
            pieces = [(block_ids[0], quote)]
        else:
            pieces = [(block_ids[0], quote[:after].rstrip()), (block_ids[1], quote[after:].lstrip())]
        for bid, piece in pieces:
            b = self.by_id.get(bid)
            if not (b and b["speaker_role"] == role and piece in b["text"] and "[" not in piece):
                self.failed += 1
                print(f"  !! quote not verified in block {bid}: {piece[:60]!r}")
        return [p for _, p in pieces]


# ------------------------------------------------------------------ his words
def build_own(ov, V):
    cats = sorted(ov["categories"], key=lambda c: c["order"])
    items = []
    for i in ov["self"]["items"]:
        items.append({
            "id": i["id"], "q": i["pull_quote"], "cat": i["category"],
            "b": i["block_ids"],
            "marks": V.marks(i["pull_quote"], i["block_ids"], i.get("page_break_after_chars")),
            "alone": i["stands_alone"],
            # a line that leans on the question before it gets a sentence saying what it answers
            "sum": i["summary"] if not i["stands_alone"] else None,
            "asked": (i["exchange"]["question"][0]["text"] if i["exchange"]["question"] else None),
            "n": i["notable"], "top": i.get("top_rank") or None,
            "page": i["page"],
        })
    # the top of each section is the reader's grade, then the five best, then transcript order
    order = {i["id"]: k for k, i in enumerate(ov["self"]["items"])}
    items.sort(key=lambda x: (-x["n"], x["top"] or 99, order[x["id"]]))
    counts = Counter(x["cat"] for x in items)
    return {
        "source": f"Smithsonian Jazz Oral History Program, interviewed by {SUBJ.INTERVIEWER['name']}, {SUBJ.OWN_DOC_YEAR}",
        "first": FIRST["own"],
        "categories": [{"key": c["key"], "label": c["label"], "count": counts[c["key"]],
                        "definition": c["definition"]} for c in cats],
        "items": items,
    }


# ------------------------------------------------------------------ journeys and records
def build_journeys(ov, V):
    out = []
    for j in sorted(ov["journeys"]["items"], key=lambda j: j["order"]):
        if not j.get("pull_quote"):
            continue
        out.append({
            "k": j["key"], "kind": JOURNEY_KINDS.get(j["kind"], j["kind"]),
            "year": j["year"], "when": j["when_as_stated"] or None,
            "title": j["title"], "q": j["pull_quote"],
            "b": [j["pull_quote_block_id"]],
            "marks": V.marks(j["pull_quote"], [j["pull_quote_block_id"]]),
            "place": j["place"] or None, "country": j["country"] or None,
            "geo": ({"lat": j["geo"]["lat"], "lon": j["geo"]["lon"], "precision": j["geo"]["precision"]}
                    if j.get("geo") else None),
            "what": j["what_happened"],
            "n": j["notable"], "top": bool(j.get("is_top")),
            "record": j.get("related_record_key"),
        })
    points = [{"k": j["key"], "title": j["title"], "kind": JOURNEY_KINDS.get(j["kind"], j["kind"]),
               "year": j["year"], "place": j["place"], "label": j["geo"]["label"],
               "lat": j["geo"]["lat"], "lon": j["geo"]["lon"], "precision": j["geo"]["precision"],
               "card": any(o["k"] == j["key"] for o in out),
               "b": [j["pull_quote_block_id"]] if j.get("pull_quote") else None}
              for j in sorted(ov["journeys"]["items"], key=lambda j: j["order"]) if j.get("geo")]
    countries = {j["country"] for j in ov["journeys"]["items"] if j.get("geo") and j["country"]}
    return {"count": len(out), "first": FIRST["journeys"], "items": out,
            "points": points, "countries": len(countries)}


def build_records(ov, disc, covers, V):
    """The records and pieces he talks about, and the list of every record
    under his name."""
    by_qid = {v["qid"]: mbid for mbid, v in covers["items"].items() if v.get("qid")}
    leader = []
    for r in sorted(disc["releases"], key=lambda r: (str(r["year"]), r["title"])):
        if r["subject_role"] != "leader":
            continue
        cover = None
        mbid = r.get("musicbrainz")
        if mbid and (ROOT / "img" / "a" / f"{mbid}.jpg").exists():
            cover = f"img/a/{mbid}.jpg"
            copy(ROOT / cover, OUT / cover)
        leader.append({
            "t": strip_album(r["title"]).replace(" by Randy Weston", ""),
            "y": r["year"], "label": r.get("label"),
            "url": r.get("wikipedia_url") or (f"https://musicbrainz.org/release-group/{mbid}" if mbid else None),
            "cover": cover,
            "said": r["he_said_of_this_record"]["key"] if r.get("he_said_of_this_record") else None,
        })
    talked = []
    for r in sorted(ov["records"]["items"], key=lambda r: r["order"]):
        if not r.get("pull_quote"):
            continue
        talked.append({
            "k": r["key"], "title": r["title"], "as_transcribed": r["title_as_transcribed"]
            if r["title_as_transcribed"] != r["title"] else None,
            "kind": RECORD_KINDS.get(r["kind"], r["kind"]),
            "year": r["year"], "label": r["label_as_stated"] or None,
            "q": r["pull_quote"], "b": [r["pull_quote_block_id"]],
            "marks": V.marks(r["pull_quote"], [r["pull_quote_block_id"]]),
            "meaning": r.get("title_meaning") or None,
            "what": r["what_he_says"],
            "part_of": r.get("part_of"),
            "n": r["notable"], "top": bool(r.get("is_top")),
        })
    return {"count": len(talked), "first": FIRST["records"], "items": talked,
            "leader": leader}


# ------------------------------------------------------------------ compositions
def build_tunes(comp):
    out = []
    for t in sorted(comp["items"], key=lambda t: (-t["count"], t["title"])):
        recs = []
        for r in t["recordings"]:
            who = [p["name"] for p in r["performers"]] or [re.sub(r"^.*? by ", "", r.get("description") or "")]
            recs.append({"who": [w for w in who if w], "rel": strip_album(r["release"]),
                         "y": r["year"], "url": r.get("wikipedia_url"),
                         "sampled": r["how"] == "sampled"})
        recs.sort(key=lambda r: (str(r["y"]), r["rel"]))
        out.append({"title": t["title"], "n": t["count"], "first": t["first_year"],
                    "last": t["last_year"], "rec": recs})
    return {"count": len(out), "first": FIRST["tunes"], "recordings": comp["recordings"],
            "items": out}


# ------------------------------------------------------------------ people he spoke of
def portrait(qid, images, credits, name):
    if not qid:
        return None
    im = (images.get(qid) or {}).get("image")
    if not im or BAD_IMAGE_FLAGS & set(im.get("review_flags") or []):
        return None
    if not (ROOT / "img" / "p" / f"{qid}.jpg").exists():
        return None
    img = f"img/p/{qid}.jpg"
    copy(ROOT / img, OUT / img)
    if not any(c["name"] == name for c in credits):
        credits.append({"name": name, "attribution": im.get("attribution") or "",
                        "page": im.get("commons_page")})
    return img


def life(p):
    b, d = p.get("born"), p.get("died")
    if b and d:
        return f"{b}–{d}"
    if b:
        return f"born {b}"
    return ""


def build_people(hw, images, credits, V):
    out = []
    for p in hw["items"]:
        if not (p["is_person"] and p["basis"] in ("his_statement", "his_assent") and p["his_quote"]):
            continue
        rel = p["relation"]
        if rel == "none":
            rel = next((TIE_LABELS[t] for t in p["tie"] if t in TIE_LABELS), None)
            if not rel:
                continue       # nothing to say how they are linked
        meta = " · ".join(x for x in (life(p), p.get("instrument_or_role")) if x)
        out.append({
            "id": f"p{abs(p['person_id'])}" + ("r" if p["person_id"] < 0 else ""),
            "name": p["name"], "qid": p["qid"],
            "meta": meta or (p.get("description") or ""),
            "line": p["one_liner"],
            "rel": rel,
            "as_named": p["as_named_in_interview"] if p["transcribed_wrong"] else None,
            "q": p["his_quote"], "b": [p["his_quote_block_id"]],
            "marks": V.marks(p["his_quote"], [p["his_quote_block_id"]]),
            "more": [{"q": m["quote"], "b": [m["block_id"]], "marks": V.marks(m["quote"], [m["block_id"]])}
                     for m in p["more_his_quotes"][:2]],
            "img": portrait(p["qid"], images, credits, p["name"]),
            "n": p["notable"], "w": p["relation_weight"],
            "wiki": p.get("wikipedia"),
        })
    out.sort(key=lambda x: (-x["n"], -x["w"], x["name"]))
    return {"count": len(out), "first": FIRST["people"], "items": out}


# ------------------------------------------------------------------ witnesses
def build_witnesses(wit, editorial, transcripts, images, credits, db):
    ed = editorial["witnesses"]
    out = []
    for r in wit["items"]:
        if not (r["spoke_themselves"] and r["lead_quote"]):
            continue
        e = ed.get(r["witness_key"], {})
        if e.get("hide"):
            continue
        if r["witness_key"] == SUBJ.OWN_DOC:
            continue
        doc = r["doc"]["doc_id"]
        transcripts[doc] = witness_transcript(db, r)
        shown = {b["i"] for b in transcripts[doc]["blocks"]}
        second = r["second_quote"] if e.get("show_second") else None
        blocks = sorted({b for b in (r["lead_block_id"], r["second_block_id"] if second else None)
                         if b in shown})
        out.append({
            "id": f"w{r['witness_key']}",
            "name": r["name"], "qid": r["qid"],
            "line": r["one_liner"] if r["grounded"] else None,
            "rel": r["relation"], "tier": r["tier"],
            "q": r["lead_quote"], "second": second,
            "note": e.get("note"),
            "doc": doc, "blocks": blocks, "marks": [r["lead_quote"], second],
            "src": source_line(transcripts[doc]),
            "img": portrait(r["qid"], images, credits, r["name"]),
            "n": r["notable"], "w": r["relation_weight"],
            "both": bool(r["he_spoke_of_them"]),
        })
    out.sort(key=lambda x: (-x["n"], -x["w"], x["name"]))
    spoke = {r["qid"] or r["name"] for r in wit["items"] if r["spoke_themselves"]}
    return {"count": len(out), "people": len({x["qid"] or x["name"] for x in out}),
            "people_in_data": len(spoke),
            "first": FIRST["witnesses"], "items": out}


# ------------------------------------------------------------------ network
def build_network(people, witnesses, spoke_of):
    """Everyone shown on the page, around him: those who spoke of him, those
    he spoke of at the reader's top grade, and the two who did both."""
    wit = {w["qid"] or w["name"]: w for w in witnesses["items"]}
    said = {p["qid"] or p["name"]: p for p in spoke_of["items"]}
    nodes = []
    for p in people["items"]:
        key = p["qid"] or p["name"]
        w, s = wit.get(key), said.get(key)
        if w and s:
            kind = "both"
        elif w:
            kind = "to"
        elif s and s["n"] >= 3:
            kind = "from"
        else:
            continue
        nodes.append({"label": p["name"], "kind": kind,
                      "to": (w or s)["id"], "from": s["id"] if s else None,
                      "qid": p["qid"]})
    nodes.sort(key=lambda n: ({"both": 0, "to": 1, "from": 2}[n["kind"]], n["label"]))
    c = Counter(n["kind"] for n in nodes)
    return {"nodes": nodes, "counts": {k: c[k] for k in ("both", "to", "from")},
            "url": f"https://thisismattmiller.github.io/linked-jazz-2026-network/#{SUBJ.NODE_ID}"}


def stamp_versions():
    """Cloudflare caches .css and .js for hours and tells browsers to do the
    same for everything. index.html is not cached at the edge, so each asset
    URL in it carries a hash of the file: a changed file is a new URL. app.js
    reads the data hash from the <meta name="build"> tag."""
    h = lambda *names: hashlib.sha1(b"".join((OUT / n).read_bytes() for n in names)).hexdigest()[:10]
    page = OUT / "index.html"
    html = page.read_text(encoding="utf-8")
    html, n1 = re.subn(r'href="style\.css(\?v=\w+)?"', f'href="style.css?v={h("style.css")}"', html)
    html, n2 = re.subn(r'src="app\.js(\?v=\w+)?"', f'src="app.js?v={h("app.js")}"', html)
    html, n3 = re.subn(r'<meta name="build" content="\w*">',
                       f'<meta name="build" content="{h("data.json", "transcripts.json")}">', html)
    if (n1, n2, n3) != (1, 1, 1):
        sys.exit("index.html: could not stamp asset versions")
    page.write_text(html, encoding="utf-8")


def main():
    prof = load(D / "profile.json")["profile"]
    docs = load(D / "documents.json")
    ov = load(D / "own_voice.json")
    hw = load(D / "his_words.json")
    wit = load(D / "witnesses.json")
    disc = load(D / "discography.json")
    comp = load(D / "compositions.json")
    people = load(D / "people.json")
    bio = load(D / "biography_sources.json")
    covers = load(ROOT / "shared" / "cover_art.json")
    images = load(ROOT / "shared" / "images.json")["people"]
    editorial = load(HERE / "editorial.json")
    own_interview = load(D / "own_interview.json")

    V = Blocks(own_interview)
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    transcripts = {"own": own_transcript(own_interview)}
    credits = []

    own = build_own(ov, V)
    journeys = build_journeys(ov, V)
    records = build_records(ov, disc, covers, V)
    tunes = build_tunes(comp)
    spoke_of = build_people(hw, images, credits, V)
    witnesses = build_witnesses(wit, editorial, transcripts, images, credits, db)
    network = build_network(people, witnesses, spoke_of)

    # the hero quote: editorial.json names one by id, else the reader's top-ranked line
    want = editorial.get("hero_quote_id")
    top = next((i for i in ov["self"]["items"] if i["id"] == want), None) if want else None
    if want and not top:
        sys.exit(f"editorial.json hero_quote_id {want!r} is not in own_voice.json")
    top = top or min(ov["self"]["items"], key=lambda i: i.get("top_rank") or 99)
    wd = {s["property"]: s for s in bio["wikidata"]["statements"]}
    born_place = next((s["label"] for s in bio["wikidata"]["statements"]
                       if s["property"] == "P19" and s.get("qualifiers")), wd["P19"]["label"])
    hero_photo = editorial["hero_photo"]
    credits.append({"name": f"{prof['display_name']} (the photograph at the top of the page)",
                    "attribution": hero_photo["attribution"], "page": hero_photo["page"]})

    n_name_him = len(docs["items"]) + len(docs["text_hit_only_documents"])
    data = {
        "generated_by": "site/build_site_data.py",
        "hero": {
            "name": prof["display_name"],
            "eyebrow": f"Centennial · {SUBJ.BORN[:4]}–{int(SUBJ.BORN[:4]) + 100}",
            "tagline": editorial["tagline"],
            "dates": f"{born_place}, {long_date(SUBJ.BORN)} – {long_date(SUBJ.DIED)}",
            "lede": editorial["lede"],
            "quote": {"q": top["pull_quote"], "b": top["block_ids"],
                      "marks": V.marks(top["pull_quote"], top["block_ids"], top.get("page_break_after_chars")),
                      "by": f"{prof['display_name']} to {SUBJ.INTERVIEWER['name']}, {SUBJ.OWN_DOC_YEAR}"},
            "photo": {"file": hero_photo["file"], "alt": hero_photo["alt"]},
        },
        "links": [
            {"label": "Wikipedia", "url": prof["links"]["wikipedia"]},
            {"label": "Wikidata", "url": prof["links"]["wikidata"]},
            {"label": "Smithsonian transcript", "url": ov["doc"]["source_url"]},
            {"label": "MusicBrainz", "url": f"https://musicbrainz.org/artist/{wd['P434']['value']}"},
            {"label": "Linked Jazz network", "url": network["url"]},
        ],
        "own": own,
        "journeys": journeys,
        "records": records,
        "tunes": tunes,
        "people": spoke_of,
        "witnesses": witnesses,
        "network": network,
        "sources": {
            "own": {"title": "Randy Weston, Smithsonian Jazz Oral History Program, "
                             f"interviewed by {SUBJ.INTERVIEWER['name']}, {long_date(SUBJ.OWN_DOC_DATE)}.",
                    "pdf": ov["doc"]["source_url"]},
            "interviews": n_name_him,
            "wikidata": prof["links"]["wikidata"],
        },
        "credits": {"portraits": sorted(credits, key=lambda c: c["name"]),
                    "covers": "Album sleeves from the Cover Art Archive, shown for identification."},
    }
    if V.failed:
        sys.exit(f"{V.failed} quotes failed verification against his interview")

    OUT.mkdir(exist_ok=True)
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                                   encoding="utf-8")
    (OUT / "transcripts.json").write_text(
        json.dumps(transcripts, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if "linked-jazz-2026-transcripts" in (OUT / "data.json").read_text(encoding="utf-8"):
        sys.exit("data.json still links to the transcript reader")

    # drop portraits and sleeves an earlier build copied that the page no longer shows
    used = {p["img"] for p in spoke_of["items"]} | {w["img"] for w in witnesses["items"]} \
        | {r["cover"] for r in records["leader"]}
    for f in list((OUT / "img" / "p").glob("*.jpg")) + list((OUT / "img" / "a").glob("*.jpg")):
        if str(f.relative_to(OUT)) not in used:
            f.unlink()

    stamp_versions()

    print(f"docs/data.json  {os.path.getsize(OUT / 'data.json') // 1024} KB")
    print(f"docs/transcripts.json  {os.path.getsize(OUT / 'transcripts.json') // 1024} KB  "
          f"{len(transcripts)} interviews, "
          f"{sum(len(t['blocks']) for t in transcripts.values())} turns")
    print(f"  his words {len(own['items'])} in {len(own['categories'])} sections")
    print(f"  journeys {journeys['count']}  records {records['count']} talked about, "
          f"{len(records['leader'])} under his name ({sum(1 for r in records['leader'] if r['cover'])} with a sleeve)")
    print(f"  tunes {tunes['count']} ({tunes['recordings']} recordings)")
    print(f"  people he spoke of {spoke_of['count']} ({sum(1 for p in spoke_of['items'] if p['img'])} with a portrait)")
    print(f"  witnesses {witnesses['count']} passages from {witnesses['people']} people "
          f"({sum(1 for w in witnesses['items'] if w['img'])} with a portrait)")
    print(f"  network {len(network['nodes'])} nodes  {network['counts']}")


if __name__ == "__main__":
    main()
