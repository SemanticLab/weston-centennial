#!/usr/bin/env python3
"""Step 1 - harvest Randy Weston's discography from Wikipedia.

Coltrane and Davis each have a dedicated "<name> discography" article built
from tables. Weston, like Liston, does not: his discography is a section of his
biography article, laid out as bullet lists --

    As leader                       <ul><li>1954: Cole Porter in a Modern Mood (Riverside) - 10-inch LP
    As sideman
        <p>With Roy Brooks</p>      <ul><li>Duet in Detroit (Enja, 1984 [1993])

-- so the table walker from that build finds nothing here. Two sources instead:

  A. the Discography section's lists. Every <li> is kept, linked or not: the
     page lists 51 records as leader and about half have their own article;
     the unlinked ones (most of the 1970s and 2000s) are still his records.
     Where Liston's list was a sidewoman's, his is a leader's: the leader of
     every "As leader" bullet is Weston, and what trails the label is a note.

  B. backlinks. The list has two sideman dates and nothing at all for the
     thing that travelled furthest without him: his TUNES. "Hi-Fly" and
     "Little Niles" are on other people's records, which credit him on a
     track line and link to his article without ever appearing in his list.
     So every main-namespace article linking to "Randy Weston" is harvested
     as a candidate row; step 2 asks Wikidata which are releases, and step 5
     keeps only those whose own personnel or track credits actually name him.

Output: discography/raw/weston_rows.json
"""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from wiki_common import backlinks, parse_page

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"

PAGES = {"weston": "Randy Weston"}

NOISE = re.compile(
    r"^(Billboard|Record label|Album|Single|Music recording sales|RIAA|"
    r"British Phonographic|List of|Recording Industry|Category:|File:|"
    r"Help:|Template:|Wikipedia:)", re.I)
YEAR = re.compile(r"\b(19[2-9]\d|20[0-2]\d)\b")
BACKLINK_SKIP = re.compile(r"^(List of|Lists of|Index of|Timeline of|\d{4} in |Deaths in )", re.I)


def clean(el):
    for sup in el.select("sup.reference, style, .mw-editsection"):
        sup.decompose()
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def li_links(li):
    out = []
    for a in li.find_all("a"):
        href, title = a.get("href") or "", a.get("title")
        if not href.startswith("/wiki/") or not title:
            continue   # red links are /w/index.php?...redlink=1
        if a.find_parent(class_="reference") or NOISE.match(title):
            continue
        out.append({"title": title, "text": a.get_text(" ", strip=True),
                    "italic": a.find_parent("i") is not None})
    return out


def parse_entry(li, group, section=""):
    """One bullet -> year, title, label, leader, note. Italics mark the record title."""
    txt = clean(li)
    it = li.find("i")
    title = clean(it) if it else None
    years = YEAR.findall(txt)
    label = note = leader = None
    if re.search(r"leader", section, re.I):
        # "1964: Randy (Bakton) - later released as African Cookbook ( Atlantic ) in 1972"
        leader = "Randy Weston"
        tail = txt.split(title, 1)[-1] if title else txt
        m = re.match(r"\s*(?:\[[^\]]*\]\s*)?\(\s*([^()]*?)\s*\)\s*(?:[-–—]\s*(.*))?$", tail)
        if m:
            label = re.sub(r"\s*\[[^\]]*\]\s*", "", m.group(1)).strip() or None
            note = (m.group(2) or "").strip() or None
            b = re.match(r"\s*\[([^\]]*)\]", tail)
            if b:
                note = "; ".join(x for x in (b.group(1).strip(), note) if x)
    else:
        m = re.search(r"\(([^()]*?),\s*((?:19|20)\d\d)[^()]*\)\s*$", txt)
        if m:
            label = m.group(1).strip()
        if group and group.lower().startswith("with ") and group.lower() != "with others":
            leader = group[5:].strip()
        elif title:
            tail = txt.split(title, 1)[-1]
            tail = re.sub(r"\([^()]*\)", "", tail).strip(" ,–-")
            leader = tail or None
    return {"year": years[0] if years else None, "title_text": title,
            "label_text": label, "leader_text": leader, "note_text": note, "text": txt}


def harvest(subject, page_title):
    doc = parse_page(page_title)
    assert not doc["missing"], f"{page_title} missing"
    soup = BeautifulSoup(doc["html"], "lxml")

    disc = next((h for h in soup.find_all("h2")
                 if h.get_text(" ", strip=True).lower().startswith("discography")), None)
    assert disc is not None, "no Discography section"

    rows, section, group = [], "Discography", None
    node = disc.find_parent("div") or disc
    for sib in node.next_siblings:
        nm = getattr(sib, "name", None)
        if nm is None:
            continue
        if nm == "div" and sib.find("h2"):
            break
        if nm == "h2":
            break
        h3 = sib if nm in ("h3", "h4") else (sib.find(["h3", "h4"]) if nm == "div" else None)
        if h3 is not None:
            section, group = clean(h3).replace("[ edit ]", "").strip(), None
            continue
        if nm in ("p", "dl"):
            g = clean(sib)
            if g:
                group = g
            continue
        if nm == "div":
            uls = sib.find_all("ul")       # div.div-col wrappers
        elif nm == "ul":
            uls = [sib]
        else:
            continue
        for ul in uls:
            for li_i, li in enumerate(ul.find_all("li", recursive=False)):
                links = li_links(li)
                e = parse_entry(li, group, section)
                rows.append({
                    "table": None, "row": li_i, "from_list": True, "source": "discography_section",
                    "section_path": ["Discography", section] + ([group] if group else []),
                    "section": section, "group": group, **e,
                    "has_release_link_candidate": any(l["italic"] for l in links),
                    "cells": [{"col": 0, "header": section, "is_row_header": True,
                               "text": e["text"], "links": links}],
                })
    n_section = len(rows)

    # ---- B: articles that link to him
    listed = {l["title"] for r in rows for c in r["cells"] for l in c["links"]}
    bl = [t for t in backlinks(doc["title"]) if not BACKLINK_SKIP.match(t)]
    for i, t in enumerate(bl):
        if t in listed or t == doc["title"]:
            continue
        rows.append({
            "table": None, "row": i, "from_list": False, "source": "backlink",
            "section_path": ["Backlink"], "section": "Backlink", "group": None,
            "year": None, "title_text": None, "label_text": None, "leader_text": None,
            "text": t, "has_release_link_candidate": True,
            "cells": [{"col": 0, "header": "Backlink", "is_row_header": True,
                       "text": t, "links": [{"title": t, "text": t, "italic": True}]}],
        })

    RAW.mkdir(parents=True, exist_ok=True)
    out = {"subject": subject, "source_page": doc["title"],
           "source_url": "https://en.wikipedia.org/wiki/" + doc["title"].replace(" ", "_"),
           "count": len(rows), "from_discography_section": n_section,
           "from_backlinks": len(rows) - n_section, "rows": rows}
    (RAW / f"{subject}_rows.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    sec = [r for r in rows if r["source"] == "discography_section"]
    unlinked = [r for r in sec if not any(l["italic"] for c in r["cells"] for l in c["links"])]
    linked = {l["title"] for r in rows for c in r["cells"] for l in c["links"]}
    print(f"{subject}: {n_section} discography entries "
          f"({len(unlinked)} with no article link), "
          f"{len(rows) - n_section} backlink candidates, {len(linked)} distinct linked articles")
    for s in dict.fromkeys(r["section"] for r in sec):
        print(f"   {s}: {sum(1 for r in sec if r['section'] == s)}")
    return out


def main():
    for subject, page in PAGES.items():
        harvest(subject, page)


if __name__ == "__main__":
    main()
