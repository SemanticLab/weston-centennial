#!/usr/bin/env python3
"""Step 6 - resolve a usable, correctly-attributed portrait for every person.

Wikidata's P18 gives a FILENAME, not a URL and not a licence. This resolves each
candidate against commons.wikimedia.org and records what a public page actually
needs: stable image URLs, the licence, the photographer, and a ready-made
attribution line.

Why Commons and not Wikipedia: Commons only hosts freely-licensed media. A file
that exists on en.wikipedia but comes back "missing" from Commons is a local
non-free (fair-use) upload -- legal on an encyclopedia article, not legal to
republish. Asking Commons is what makes that distinction visible.

Candidates are tried in order and the first Commons-resolvable one wins:
  1. wikidata_p18       the curated depiction of the person
  2. wikipedia_lead     page_image_free, for the 19 people with no P18
  3. commons_category   P373, picking the most portrait-looking file
  4. semlab             Linked Jazz's own thumbnail -- NOT Commons, no licence
                        metadata, recorded as a last resort and flagged

Output: shared/images.json
"""

import json
import re
import sqlite3
import unicodedata
import urllib.parse
from collections import Counter
from pathlib import Path

from wiki_common import (COMMONS_API, WP_API, _get, commons_category_files,
                         commons_imageinfo, wd_entities)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "discography" / "raw"
LJ = "/Users/m/git/ch-jazz-mashup/linked_jazz.sqlite"
SUBJECTS = {"weston": "Q1371187"}
OWN_DOC = "Randy-Weston-Transcription-2020_0"

# Files that are on Commons but are not a picture of the person.
NOT_A_PORTRAIT = re.compile(
    r"signature|autograph|grave|tomb|headstone|plaque|memorial|logo|"
    r"sheet music|score|poster|cover|label|stamp|coin|album|record|"
    r"discography|\.ogg$|\.oga$|\.wav$|\.mid$|\.pdf$|\.svg$", re.I)
# Filenames that suggest several people in shot. Deliberately NOT keying on a
# bare comma or on "festival": "Al Cohn, 1965.jpg" and "Chick Corea Kongsberg
# Jazzfestival 2018.jpg" are both solo portraits, and flagging them buried the
# real hits. The reliable signals are ensemble nouns, "with the ...", and a
# caption that positions the person within a group.
GROUP_SHOT = re.compile(
    r"orchestra|big band|quintet|quartet|sextet|septet|octet|ensemble|"
    r"all[- ]stars|messengers|\bwith the\b|\bwith \w+ and\b|"
    r"far left|far right|second from|third from|\bgroup\b", re.I)
AUDIO_VIDEO = re.compile(r"\.(ogg|oga|wav|mid|webm|ogv|mp3|flac)$", re.I)


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&amp;", "&").replace("&quot;", '"')
          .replace("&#039;", "'").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&nbsp;", " "))
    return re.sub(r"\s+", " ", s).strip()


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def filepath_url(file_title, width=None):
    """Special:FilePath is the stable, documented way to link a Commons file.

    Preferred over the raw upload.wikimedia.org thumb URL the API returns,
    which carries utm_* tracking parameters and encodes a hash-sharded path.
    """
    name = file_title.split(":", 1)[-1].replace(" ", "_")
    url = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
           + urllib.parse.quote(name))
    return f"{url}?width={width}" if width else url


def license_of(info):
    em = info.get("extmetadata") or {}
    short = strip_html(em.get("LicenseShortName"))
    lic = (short or strip_html(em.get("License")) or "").strip()
    artist = strip_html(em.get("Artist"))
    credit = strip_html(em.get("Credit"))
    required = str(em.get("AttributionRequired") or "").lower() == "true"
    pd = bool(re.search(r"public domain|^pd|cc0", lic, re.I))
    return {
        "short": lic or None,
        "usage_terms": strip_html(em.get("UsageTerms")) or None,
        "url": em.get("LicenseUrl"),
        "public_domain": pd,
        "attribution_required": required and not pd,
        "artist": artist or None,
        "credit": credit or None,
        "restrictions": strip_html(em.get("Restrictions")) or None,
        "date": strip_html(em.get("DateTimeOriginal")) or None,
    }


def attribution_line(lic, info):
    """A line the page can print verbatim under the photo."""
    who = lic["artist"] or lic["credit"] or "unknown author"
    who = re.sub(r"\s*\(talk\)\s*", " ", who).strip(" ,;")
    bits = [f"{who}"]
    if lic["short"]:
        bits.append(lic["short"])
    return f"{bits[0]} ({', '.join(bits[1:])}), via Wikimedia Commons" \
        if len(bits) > 1 else f"{bits[0]}, via Wikimedia Commons"


def other_people_in_filename(file_title, person_name, roster_names, artist=""):
    """Names of OTHER known musicians appearing in the filename.

    A far better group-photo signal than punctuation: if the file is called
    "Fats Navarro, Charlie Rouse, Ernie Henry, Tadd Dameron", three of those
    four are on our own roster, so we know it is a group shot without guessing.

    The PHOTOGRAPHER must be excluded or this misfires badly: William P.
    Gottlieb shot much of the 1940s jazz scene, is himself in the corpus, and
    signs his filenames -- "Red Rodney, ca. June 1946 (William P. Gottlieb).jpg"
    is a solo portrait, not two people. Same for "portrait by ...".
    """
    hay = " " + norm(file_title) + " "
    mine = set(norm(person_name).split())
    shooter = norm(artist)
    hits = []
    for full, surname in roster_names:
        if surname in mine or full in norm(person_name):
            continue
        if shooter and (full in shooter or shooter in full):
            continue                      # the photographer, not a sitter
        if re.search(rf"(?:by|photo(?:graph)?(?:ed)? by)\s+{re.escape(full)}",
                     norm(file_title)):
            continue
        if f" {full} " in hay:
            hits.append(full)
    return sorted(set(hits))


def score_candidate(file_title, person_name):
    """Lower is better. Used to pick from a Commons category."""
    f = file_title
    s = 0
    if NOT_A_PORTRAIT.search(f):
        s += 100
    if AUDIO_VIDEO.search(f):
        s += 500
    if GROUP_SHOT.search(f):
        s += 20
    surname = (norm(person_name).split() or [""])[-1]
    if surname and surname in norm(f):
        s -= 10
    return s


def wikipedia_lead_images(titles):
    out = {}
    titles = [t for t in dict.fromkeys(titles) if t]
    for i in range(0, len(titles), 40):
        d = _get(WP_API, {"action": "query", "prop": "pageimages|pageprops",
                          "piprop": "original|name",
                          "titles": "|".join(titles[i:i + 40]), "redirects": 1})
        q = d.get("query", {})
        alias = {n["from"]: n["to"] for n in q.get("normalized", [])}
        alias.update({r["from"]: r["to"] for r in q.get("redirects", [])})
        by_title = {}
        for pg in q.get("pages", {}).values():
            nm = (pg.get("pageprops") or {}).get("page_image_free") or pg.get("pageimage")
            if nm:
                by_title[pg["title"]] = nm
        for t in titles[i:i + 40]:
            cur, seen = t, set()
            while cur in alias and cur not in seen:
                seen.add(cur)
                cur = alias[cur]
            if cur in by_title:
                out[t] = by_title[cur]
    return out


def collect_people():
    """Everyone a page might need a face for, with why they matter."""
    people = {}

    def add(qid, name, **flags):
        if not qid:
            return
        p = people.setdefault(qid, {
            "qid": qid, "name": name, "subjects": set(),
            "on_roster": False, "interviewed": False, "spoke_about": set(),
            "he_spoke_of": False, "network_neighbour": False,
            "album_count": 0, "blocks_about": 0, "wikipedia": None})
        for k, v in flags.items():
            if k == "subject":
                p["subjects"].add(v)
            elif k == "spoke_about":
                p["spoke_about"].add(v)
            elif k in ("album_count", "blocks_about"):
                p[k] = max(p[k], v)
            elif v:
                p[k] = v

    for subject, qid in SUBJECTS.items():
        add(qid, "Randy Weston", subject=subject)

    # the people HE spoke about in his own interview (his_words.json) and his
    # network neighbours -- neither of which the Coltrane / Davis build had,
    # because neither man was ever interviewed
    for subject in SUBJECTS:
        f = ROOT / subject / "his_words.json"
        if f.exists():
            for i in json.loads(f.read_text(encoding="utf-8"))["items"]:
                if i.get("is_person") and i.get("qid"):
                    add(i["qid"], i["name"], subject=subject, he_spoke_of=True,
                        wikipedia=(i.get("wikipedia") or "").rsplit("/", 1)[-1].replace("_", " ") or None)
        f = ROOT / subject / "connections.json"
        if f.exists():
            for i in json.loads(f.read_text(encoding="utf-8"))["items"]:
                o = i["other"]
                if o.get("qid"):
                    add(o["qid"], o["label"], subject=subject, network_neighbour=True)
        f = ROOT / subject / "witnesses.json"
        if f.exists():
            for i in json.loads(f.read_text(encoding="utf-8"))["items"]:
                if i.get("qid"):
                    add(i["qid"], i["name"], subject=subject, interviewed=True,
                        **({"spoke_about": subject} if i.get("spoke_themselves") else {}))

    for subject in SUBJECTS:
        for p in json.loads((ROOT / subject / "discography_personnel.json")
                            .read_text(encoding="utf-8"))["people"]:
            if not p["qid"]:
                continue
            add(p["qid"], p["name"], subject=subject, on_roster=True,
                wikipedia=p.get("wikipedia"),
                interviewed=p["interviewed_in_corpus"],
                album_count=p["album_count"],
                blocks_about=p["blocks_about_subject"],
                **({"spoke_about": subject} if p["said_about_subject"] else {}))

    # people who spoke about either man but never played on a record
    con = sqlite3.connect(f"file:{LJ}?mode=ro", uri=True)
    itv = {}
    for doc_id, label, qid in con.execute(
            "select doc_id, label, qid from doc_interviewees"):
        itv.setdefault(str(doc_id), []).append((label, qid or None))
    con.close()

    for subject in SUBJECTS:
        for fname, cond in (("enriched.json",
                             lambda i: i.get("is_about_subject")
                             and i.get("speaker_role") == "interviewee"),
                            ("recovered_evaluated.json",
                             lambda i: i.get("is_about_subject"))):
            f = ROOT / subject / fname
            if not f.exists():
                continue
            for i in json.loads(f.read_text(encoding="utf-8"))["items"]:
                if not cond(i) or str(i["doc_id"]) == OWN_DOC:
                    continue
                rows = [r for r in itv.get(str(i["doc_id"]), []) if r[1]]
                if len(rows) == 1:
                    add(rows[0][1], rows[0][0], subject=subject,
                        interviewed=True, spoke_about=subject)
    return people


def main():
    people = collect_people()
    print(f"{len(people)} distinct people to find a portrait for")

    ents = wd_entities(list(people))
    for qid, p in people.items():
        e = ents.get(qid) or {}
        p["wikipedia"] = e.get("enwiki") or p["wikipedia"]
        p["p18"] = (e.get("P18") or [None])[0]
        p["name"] = e.get("label") or p["name"]

    # candidate 2: Wikipedia lead image, only for people with no P18
    need_lead = [p["wikipedia"] for p in people.values()
                 if not p["p18"] and p["wikipedia"]]
    leads = wikipedia_lead_images(need_lead)
    print(f"  {len(leads)} Wikipedia lead images found for the {len(need_lead)} "
          f"without P18")

    # candidate 3: Commons category, for those still empty
    still = [p for p in people.values()
             if not p["p18"] and not leads.get(p["wikipedia"] or "")]
    cats = {}
    for i in range(0, len(still), 50):
        d = _get("https://www.wikidata.org/w/api.php",
                 {"action": "wbgetentities", "props": "claims",
                  "ids": "|".join(p["qid"] for p in still[i:i + 50])})
        for qid, ent in (d.get("entities") or {}).items():
            for c in (ent.get("claims") or {}).get("P373", []):
                v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                if isinstance(v, str):
                    cats[qid] = v
    print(f"  {len(cats)} Commons categories to search for the remaining "
          f"{len(still)}")

    cat_pick = {}
    for qid, cat in cats.items():
        files = commons_category_files(cat)
        files = [f for f in files if not AUDIO_VIDEO.search(f)]
        if not files:
            continue
        best = sorted(files, key=lambda f: score_candidate(f, people[qid]["name"]))[0]
        if score_candidate(best, people[qid]["name"]) < 100:
            cat_pick[qid] = best

    # semlab thumbnails (not Commons, no licence metadata)
    con = sqlite3.connect(f"file:{LJ}?mode=ro", uri=True)
    semlab = {q: t for q, t in con.execute(
        "select qid, semlab_thumb_url from wd_people "
        "where semlab_thumb_url is not null and semlab_thumb_url <> ''")}
    con.close()

    # resolve every Commons candidate in one batched pass
    wanted = {}
    for p in people.values():
        f = None
        src = None
        if p["p18"]:
            f, src = p["p18"], "wikidata_p18"
        elif leads.get(p["wikipedia"] or ""):
            f, src = leads[p["wikipedia"]], "wikipedia_lead"
        elif cat_pick.get(p["qid"]):
            f, src = cat_pick[p["qid"]], "commons_category"
        if f:
            wanted[p["qid"]] = (f if f.startswith("File:") else f"File:{f}", src)

    print(f"  resolving {len(wanted)} files against Commons ...")
    info = commons_imageinfo([f for f, _ in wanted.values()])

    # full names of everyone we know about, for the group-photo check
    roster_names = []
    for p in people.values():
        n = norm(p["name"])
        if len(n.split()) >= 2:
            roster_names.append((n, n.split()[-1]))

    out, stats = {}, Counter()
    for qid, p in sorted(people.items(),
                         key=lambda kv: -kv[1]["blocks_about"]):
        rec = {
            "qid": qid, "name": p["name"],
            "subjects": sorted(p["subjects"]),
            "on_roster": p["on_roster"], "interviewed": p["interviewed"],
            "spoke_about": sorted(p["spoke_about"]),
            "he_spoke_of": p["he_spoke_of"],
            "network_neighbour": p["network_neighbour"],
            "album_count": p["album_count"],
            "blocks_about_subject": p["blocks_about"],
            "wikipedia": p["wikipedia"],
            "wikidata_url": f"https://www.wikidata.org/wiki/{qid}",
            "image": None,
        }
        pair = wanted.get(qid)
        if pair:
            fname, src = pair
            i = info.get(fname) or {}
            if not i.get("missing"):
                lic = license_of(i)
                flags = []
                others = other_people_in_filename(
                    fname, p["name"], roster_names, lic["artist"] or "")
                if NOT_A_PORTRAIT.search(fname):
                    flags.append("may_not_be_a_portrait")
                if GROUP_SHOT.search(fname) or others:
                    flags.append("may_be_a_group_photo")
                if src == "commons_category":
                    flags.append("picked_from_category_not_curated")
                if not lic["artist"] and lic["attribution_required"]:
                    flags.append("attribution_required_but_author_unknown")
                if lic["restrictions"]:
                    flags.append("has_restrictions")
                rec["image"] = {
                    "source": src,
                    "file": fname,
                    "commons_page": i.get("descriptionurl")
                    or f"https://commons.wikimedia.org/wiki/{fname.replace(' ', '_')}",
                    "url_full": filepath_url(fname),
                    "url_800": filepath_url(fname, 800),
                    "url_400": filepath_url(fname, 400),
                    "url_200": filepath_url(fname, 200),
                    "width": i.get("width"), "height": i.get("height"),
                    "mime": i.get("mime"),
                    "hosted_on_commons": True,
                    "license": lic,
                    "attribution": attribution_line(lic, i),
                    "also_pictured": others,
                    "review_flags": flags,
                }
                stats[f"resolved_{src}"] += 1
                if flags:
                    stats["flagged_for_review"] += 1
            else:
                stats["candidate_not_on_commons"] += 1
                rec["image_note"] = (
                    f"{fname} is not on Commons - likely a local non-free "
                    f"upload; not safe to republish")
        if rec["image"] is None and semlab.get(qid):
            rec["image"] = {
                "source": "semlab", "file": None,
                "url_full": semlab[qid], "url_800": semlab[qid],
                "url_400": semlab[qid], "url_200": semlab[qid],
                "hosted_on_commons": False,
                "license": {"short": None, "public_domain": False,
                            "attribution_required": True, "artist": None},
                "attribution": "Linked Jazz / Semantic Lab - licence unverified",
                "review_flags": ["not_commons_licence_unverified"],
            }
            stats["resolved_semlab"] += 1
        if rec["image"] is None:
            stats["no_image"] += 1
        out[qid] = rec

    total = len(out)
    withimg = sum(1 for r in out.values() if r["image"])
    commons = sum(1 for r in out.values()
                  if r["image"] and r["image"]["hosted_on_commons"])
    spoke = [r for r in out.values() if r["spoke_about"]]
    spoke_img = [r for r in spoke if r["image"]]

    summary = {
        "people": total,
        "with_an_image": withimg,
        "coverage_pct": round(100 * withimg / total, 1),
        "commons_hosted": commons,
        "by_source": {k.replace("resolved_", ""): v for k, v in stats.items()
                      if k.startswith("resolved_")},
        "flagged_for_review": stats["flagged_for_review"],
        "candidate_not_on_commons": stats["candidate_not_on_commons"],
        "no_image": stats["no_image"],
        "people_who_spoke": len(spoke),
        "people_who_spoke_with_an_image": len(spoke_img),
        "spoke_coverage_pct": round(100 * len(spoke_img) / max(1, len(spoke)), 1),
        "people_he_spoke_of": sum(1 for r in out.values() if r["he_spoke_of"]),
        "people_he_spoke_of_with_an_image": sum(
            1 for r in out.values() if r["he_spoke_of"] and r["image"]),
        "licenses": dict(Counter(
            (r["image"]["license"]["short"] or "unknown")
            for r in out.values() if r["image"]).most_common()),
        "attribution_required": sum(
            1 for r in out.values()
            if r["image"] and r["image"]["license"]["attribution_required"]),
    }

    (ROOT / "shared" / "images.json").write_text(
        json.dumps({"summary": summary,
                    "note": "Special:FilePath URLs are stable and resize via "
                            "?width=. Every hosted_on_commons image is freely "
                            "licensed; check license.attribution_required and "
                            "print the attribution line.",
                    "count": total, "people": out},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{withimg}/{total} people have an image ({summary['coverage_pct']}%)")
    print(f"  by source: {summary['by_source']}")
    print(f"  people who spoke about him: "
          f"{len(spoke_img)}/{len(spoke)} ({summary['spoke_coverage_pct']}%)")
    print(f"  flagged for review: {summary['flagged_for_review']}   "
          f"not on Commons: {summary['candidate_not_on_commons']}")
    print(f"  licences: {summary['licenses']}")


if __name__ == "__main__":
    main()
