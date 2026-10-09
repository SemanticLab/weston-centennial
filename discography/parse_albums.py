#!/usr/bin/env python3
"""Step 3b - parse each release article: infobox + personnel + track listing.

Personnel sections are the point of this whole exercise, and they are messy:

  * the heading is "Personnel" 267 times but also "Musicians", "Technical
    personnel", "Production personnel", "Performers", "Cast", ...
  * a "Personnel" h2 usually has h3 subsections ("The John Coltrane Quartet",
    "Additional personnel"), each with its own <ul>, so you cannot stop at the
    first sub-heading
  * a line is "Name <dash> role, role (note)" but the dash is any of - -- --- and
    some lines are bare names with no role at all
  * the first link on a line is NOT always the person: "George Gray / Viceroy -
    cover design" links to "Album cover"

So this records the raw line text alongside the parsed name, and leaves the
name -> QID decision to the next step, which type-checks against Wikidata.

Output: discography/raw/albums.json
"""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from wiki_common import parse_page

RAW = Path(__file__).resolve().parent / "raw"

PERSONNEL_HEAD = re.compile(
    r"personnel|musician|credits|line-?up|players|performers|cast|band$", re.I)
TECH_HEAD = re.compile(r"technical|production|artwork|design|reissue", re.I)

# En dash, em dash, hyphen, minus sign - always with surrounding whitespace so
# hyphenated names ("Jean-Luc Ponty") survive.
DASH = re.compile(r"\s+[–—−-]\s+")

TECH_ROLE = re.compile(
    r"engineer|producer|production|mixing|master|design|photograph|artwork|"
    r"liner note|cover|illustration|art direction|remaster|supervis|"
    r"transfer|editing|annotat|reissue|graphic|coordinat|art\b|editorial|"
    r"packaging|restorat|layout|typograph|sequenc|research|consultant|"
    r"director|A&R|tape|essay|text|translat|assistan", re.I)

INFOBOX_KEYS = {
    "released": "released", "recorded": "recorded", "studio": "studio",
    "venue": "venue", "genre": "genre", "length": "length", "label": "label",
    "producer": "producer", "type": "type", "chronology": "chronology",
}


def clean_text(el):
    el = BeautifulSoup(str(el), "lxml")
    for junk in el.select("sup.reference, style, .mw-editsection, .reference"):
        junk.decompose()
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def parse_infobox(soup):
    box = soup.select_one("table.infobox")
    if not box:
        return {}
    out = {}
    for tr in box.select("tr"):
        lab = tr.select_one("th.infobox-label") or tr.select_one("th[scope=row]")
        val = tr.select_one("td.infobox-data")
        if not lab or not val:
            continue
        key = re.sub(r"[^a-z]", "", lab.get_text(" ", strip=True).lower())
        for want, name in INFOBOX_KEYS.items():
            if key.startswith(want):
                links = [a.get("title") for a in val.find_all("a")
                         if (a.get("href") or "").startswith("/wiki/") and a.get("title")]
                out[name] = {"text": clean_text(val), "links": links}
                break
    return out


def _iter_flat(container):
    """Yield ('h', level, text) or ('ul', 0, node) in document order.

    Lists are not always direct children of mw-parser-output: they get wrapped
    in <div class="div-col"> for multi-column layout, and some albums lay their
    personnel out as a table of per-session lists. Descend into wrappers rather
    than only looking at top-level <ul>, or ~13 albums silently yield nothing.
    """
    for child in container.find_all(recursive=False):
        cls = " ".join(child.get("class") or [])
        if "mw-heading" in cls:
            h = child.find(["h2", "h3", "h4", "h5"])
            if h:
                yield ("h", int(h.name[1]), clean_text(h))
            continue
        if child.name in ("h2", "h3", "h4", "h5"):
            yield ("h", int(child.name[1]), clean_text(child))
            continue
        if child.name == "ul":
            yield ("ul", 0, child)
            continue
        if child.name in ("div", "table"):
            if SKIP_WRAPPER.search(cls):
                continue
            # a wrapper may itself contain headings; keep document order
            for node in child.find_all(["h2", "h3", "h4", "h5", "ul"]):
                if node.name == "ul":
                    if node.find_parent("ul") is not None:  # top-level lists only
                        continue
                    if node.find_parent(class_=SKIP_WRAPPER):
                        continue
                    yield ("ul", 0, node)
                else:
                    yield ("h", int(node.name[1]), clean_text(node))


# Page furniture whose lists are navigation, not credits. Album navboxes list
# every other album by the artist, which otherwise lands in the roster as
# "people" named "Live in Europe 1967: The Bootleg Series Vol. 1".
SKIP_WRAPPER = re.compile(
    r"navbox|vertical-navbox|metadata|reflist|mw-references|catlinks|"
    r"sistersitebox|hatnote|thumb|gallery|sidebar|authority-control|"
    r"portalbox|refbegin|mw-editsection")

# Lines that describe the session rather than credit a person.
PROSE = re.compile(
    r"^(recorded|mixed|mastered|remastered|produced|engineered|arranged|"
    r"released|all tracks|tracks?\b|disc\b|side\b|originally|reissued|"
    r"design|photograph|liner|cover|notes?\b|compiled|sessions?\b)", re.I)

SUFFIX = re.compile(r"(?:Jr|Sr|II|III|IV|Jnr|Snr)\.?", re.I)

# "Trumpets and flugelhorns: Benny Rosenfeld, Idrees Sulieman, ..."
ROLE_COLON = re.compile(r"^([A-Za-z][A-Za-z /&'-]{1,45}):\s*(.+)$")


def split_top_level(text):
    """Split on commas/& that are not inside parentheses.

    Needed because per-name annotations carry their own commas:
    'Ray Copeland (tracks 1, 2 & 5-8), Bill Hardman (tracks 1, 2 & 5-8)'.
    """
    out, buf, depth = [], [], 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if depth == 0:
            if ch == ",":
                out.append("".join(buf)); buf = []; i += 1; continue
            if ch == "&":
                out.append("".join(buf)); buf = []; i += 1; continue
            if text.startswith(" and ", i):
                out.append("".join(buf)); buf = []; i += 5; continue
        buf.append(ch)
        i += 1
    out.append("".join(buf))
    segs = [s.strip(" ;:") for s in out if s.strip(" .;:")]

    # "Walter Bishop, Jr. - piano" must not become two people, and the stray
    # "Walter Bishop" would resolve to his father, a different musician.
    merged = []
    for s in segs:
        if SUFFIX.fullmatch(s.strip(" .")) and merged:
            merged[-1] = f"{merged[-1].rstrip(' .')}, {s.strip(' .')}."
        else:
            merged.append(s)
    return [s.strip(" .;:") if not SUFFIX.search(s) else s.strip(" ;:")
            for s in merged if s.strip(" .;:")]


def looks_like_name(s):
    s = s.strip()
    if not s or len(s) > 45 or re.search(r"\d", s):
        return False
    words = s.split()
    if not 1 <= len(words) <= 5:
        return False
    caps = sum(1 for w in words if w[:1].isupper() or w[:1] in "\"'“")
    return caps >= max(1, len(words) - 1)


def _strip_note(seg):
    note = ""
    m = re.search(r"\(([^)]*)\)\s*$", seg)
    if m:
        note = m.group(1).strip()
        seg = seg[:m.start()].strip()
    return seg.strip(" .,;:"), note


def parse_person_line(li, group=""):
    """One <li> -> a LIST of credits.

    A line is not reliably one person. Real shapes in this corpus:
      'John Coltrane - tenor saxophone (tracks 1-5)'   single
      'Julius Watkins, Bob Northern - french horn'     several sharing a role
      'Trumpets and flugelhorns: Benny Rosenfeld, ...' role stated first
      'Recorded at Clinton Recording Studios...'       not a credit at all
    """
    for junk in li.select("sup.reference, .reference, style"):
        junk.decompose()
    nested = [ul.extract() for ul in li.find_all("ul")]
    text = re.sub(r"\s+", " ", li.get_text(" ", strip=True)).strip()
    for ul in nested:
        li.append(ul)
    if not text:
        return [], None

    links = [{"title": a.get("title"), "text": a.get_text(" ", strip=True)}
             for a in li.find_all("a")
             if (a.get("href") or "").startswith("/wiki/") and a.get("title")]
    link_texts = {l["text"] for l in links}

    names_part, roles_part = None, ""
    m = ROLE_COLON.match(text)
    if m and not DASH.search(m.group(1)):
        roles_part, names_part = m.group(1), m.group(2)
    elif DASH.search(text):
        a, b = DASH.split(text, maxsplit=1)
        names_part, roles_part = a, b
    elif PROSE.match(text) and not link_texts:
        return [], text                      # session note, not a credit
    else:
        names_part, roles_part = text, group

    roles_part, line_note = _strip_note(roles_part)
    roles = [r.strip(" .;") for r in re.split(r",| and ", roles_part) if r.strip(" .;")]

    segs = split_top_level(names_part)
    credits, leftover = [], []
    for seg in segs:
        nm, note = _strip_note(seg)
        if not nm:
            continue
        if not looks_like_name(nm):
            # keep it only if it exactly matches a linked article's anchor text
            hit = next((l for l in links if l["text"] == nm), None)
            if not hit:
                leftover.append(nm)
                continue
        credits.append({
            "raw": text, "name": nm, "roles": roles,
            "note": "; ".join(x for x in (note, line_note) if x),
            "links": [l for l in links if l["text"] == nm] or
                     ([links[0]] if len(segs) == 1 and links else []),
        })

    if not credits and PROSE.match(text):
        return [], text
    return credits, ("; ".join(leftover) if leftover else None)


def parse_personnel(soup):
    root = soup.select_one("div.mw-parser-output") or soup
    out, notes, cur_h2, cur_sub, in_pers = [], [], "", "", False

    for kind, lvl, node in _iter_flat(root):
        if kind == "h":
            if lvl == 2:
                cur_h2, cur_sub = node, ""
                in_pers = bool(PERSONNEL_HEAD.search(node))
            else:
                cur_sub = node
                # an h3 "Personnel" under a non-personnel h2 also counts
                if PERSONNEL_HEAD.search(node):
                    in_pers = True
                elif lvl == 3 and not PERSONNEL_HEAD.search(cur_h2):
                    in_pers = False
            continue

        if not in_pers:
            continue
        group = cur_sub or cur_h2
        for li in node.find_all("li", recursive=False):
            recs, note = parse_person_line(li, group)
            if note:
                notes.append({"section": cur_h2, "group": group, "text": note})
            for rec in recs:
                tech = bool(TECH_HEAD.search(group)) or (
                    bool(rec["roles"]) and all(TECH_ROLE.search(r) for r in rec["roles"]))
                out.append({**rec, "section": cur_h2, "group": group,
                            "credit_type": "technical" if tech else "musician"})
    return out, notes


def parse_tracks(soup):
    """Track listings come in four shapes on these pages.

    <ol> from the {{track listing}} template, <ul> for side-by-side LP sides,
    <dl>/<dd> for suite movements ("Part I - Acknowledgement"), and
    table.tracklist. Handling only <ul> found tracks on 63 of 287 albums.
    """
    root = soup.select_one("div.mw-parser-output") or soup
    tracks = []
    for h in root.find_all(["h2", "h3", "h4"]):
        if not re.search(r"track listing|contents|track list", clean_text(h), re.I):
            continue
        node = h.find_parent("div", class_="mw-heading") or h
        for sib in node.next_siblings:
            nm = getattr(sib, "name", None)
            if nm == "div" and sib.find(["h2"]):
                break
            if nm in ("h2",):
                break
            if nm is None:
                continue
            cls = " ".join(sib.get("class") or [])
            if SKIP_WRAPPER.search(cls):
                continue
            for el in ([sib] if nm in ("ol", "ul", "dl", "table")
                       else sib.find_all(["ol", "ul", "dl", "table"])):
                if el.name == "table":
                    if "tracklist" not in " ".join(el.get("class") or []):
                        continue
                    for tr in el.select("tr"):
                        # the track number is a <th scope="row">, not a <td>,
                        # so td-only selection drops the digit the filter needs
                        cells = [clean_text(c) for c in tr.find_all(["td", "th"])]
                        if len(cells) >= 2 and cells[0].rstrip(".").isdigit():
                            tracks.append(" - ".join(cells[:4]))
                else:
                    for item in el.find_all(["li", "dd"], recursive=False):
                        t = clean_text(item)
                        if t:
                            tracks.append(t)
    # de-duplicate while preserving order (reissue listings repeat tracks)
    seen, out = set(), []
    for t in tracks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:80]


def main():
    ents = json.loads((RAW / "entities.json").read_text(encoding="utf-8"))["entities"]
    releases = {}
    for v in ents.values():
        if v["bucket"] == "release":
            releases.setdefault(v["title"], v)

    albums = {}
    no_personnel = []
    for title, ent in sorted(releases.items()):
        d = parse_page(title)
        if d.get("missing"):
            continue
        soup = BeautifulSoup(d["html"], "lxml")
        personnel, session_notes = parse_personnel(soup)
        if not personnel:
            no_personnel.append(title)
        albums[title] = {
            "title": title,
            "qid": ent["qid"],
            "wikipedia_url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
            "wikidata_url": f"https://www.wikidata.org/wiki/{ent['qid']}" if ent["qid"] else None,
            "description": ent.get("description"),
            "classes": ent.get("classes"),
            "performers_qids": ent.get("performers"),
            "publication_dates": ent.get("publication_dates"),
            "musicbrainz": ent.get("musicbrainz"),
            "image": ent.get("image"),
            "infobox": parse_infobox(soup),
            "personnel": personnel,
            "personnel_count": len(personnel),
            "session_notes": session_notes,
            "tracks": parse_tracks(soup),
        }

    (RAW / "albums.json").write_text(
        json.dumps({"count": len(albums), "albums": albums},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    tot = sum(a["personnel_count"] for a in albums.values())
    mus = sum(1 for a in albums.values() for p in a["personnel"]
              if p["credit_type"] == "musician")
    print(f"{len(albums)} albums parsed")
    print(f"{tot} personnel credits ({mus} musician, {tot - mus} technical)")
    print(f"{len(no_personnel)} albums with no personnel section")
    print(f"albums with tracks: {sum(1 for a in albums.values() if a['tracks'])}")
    print(f"albums with infobox: {sum(1 for a in albums.values() if a['infobox'])}")


if __name__ == "__main__":
    main()
