#!/usr/bin/env python3
"""Cached MediaWiki + Wikidata API helpers.

Everything is cached to discography/cache/ so re-running the pipeline costs
nothing and the parse steps can be iterated on without re-fetching ~500 pages.
Wikipedia asks for a descriptive User-Agent; anonymous scripted access without
one gets throttled or blocked.
"""

import hashlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
UA = ("weston-centennial/1.0 (Randy Weston centennial oral-history project; "
      "https://github.com/thisismattmiller) python-urllib")

WP_API = "https://en.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"


# Wikimedia returns HTTP 429 well before you would expect it -- 4 workers with
# no delay tripped it after ~100 article fetches. Serialise a minimum gap
# between requests across all threads and back off hard on 429.
_LOCK = threading.Lock()
_last_call = [0.0]
MIN_GAP = 0.35


def _throttle():
    with _LOCK:
        wait = MIN_GAP - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


def _get(url, params, timeout=60, retries=5):
    q = urllib.parse.urlencode({**params, "format": "json"})
    last = None
    for a in range(retries + 1):
        try:
            _throttle()
            req = urllib.request.Request(f"{url}?{q}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as ex:
            last = ex
            time.sleep((10 if ex.code == 429 else 2) * (a + 1))
        except Exception as ex:  # noqa: BLE001
            last = ex
            time.sleep(2 * (a + 1))
    raise last


def _cache_path(kind, key):
    d = CACHE / kind
    d.mkdir(parents=True, exist_ok=True)
    safe = urllib.parse.quote(key, safe="")[:120]
    h = hashlib.sha1(key.encode()).hexdigest()[:10]
    return d / f"{safe}__{h}.json"


def parse_page(title, force=False):
    """Rendered HTML for an article. Returns None if the page does not exist."""
    p = _cache_path("pages", title)
    if p.exists() and not force:
        return json.loads(p.read_text(encoding="utf-8"))
    d = _get(WP_API, {"action": "parse", "page": title, "prop": "text|sections",
                      "redirects": 1})
    if "error" in d:
        out = {"missing": True, "title": title, "error": d["error"].get("code")}
    else:
        out = {"missing": False,
               "title": d["parse"]["title"],
               "pageid": d["parse"]["pageid"],
               "html": d["parse"]["text"]["*"],
               "sections": d["parse"].get("sections", [])}
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def pageprops(titles, force=False):
    """title -> {qid, title (canonical), missing}. Batches of 50, follows redirects."""
    titles = list(dict.fromkeys(t for t in titles if t))
    out, todo = {}, []
    for t in titles:
        p = _cache_path("props", t)
        if p.exists() and not force:
            out[t] = json.loads(p.read_text(encoding="utf-8"))
        else:
            todo.append(t)

    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        d = _get(WP_API, {"action": "query", "prop": "pageprops",
                          "titles": "|".join(batch), "redirects": 1})
        q = d.get("query", {})
        # map every requested title through normalisation + redirects to a final title
        alias = {}
        for n in q.get("normalized", []):
            alias[n["from"]] = n["to"]
        for r in q.get("redirects", []):
            alias[r["from"]] = r["to"]

        by_title = {}
        for pg in q.get("pages", {}).values():
            by_title[pg["title"]] = {
                "title": pg["title"],
                "missing": "missing" in pg,
                "qid": (pg.get("pageprops") or {}).get("wikibase_item"),
            }

        for t in batch:
            seen, cur = set(), t
            while cur in alias and cur not in seen:   # chase normalize -> redirect
                seen.add(cur)
                cur = alias[cur]
            rec = by_title.get(cur) or {"title": cur, "missing": True, "qid": None}
            rec = {**rec, "requested": t}
            out[t] = rec
            _cache_path("props", t).write_text(
                json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.1)
    return out


def backlinks(title, force=False):
    """Every main-namespace article that links to `title` (redirects followed)."""
    p = _cache_path("backlinks", title)
    if p.exists() and not force:
        return json.loads(p.read_text(encoding="utf-8"))
    out, cont = [], {}
    while True:
        d = _get(WP_API, {"action": "query", "list": "backlinks", "bltitle": title,
                          "blnamespace": 0, "bllimit": 500, "blredirect": 1, **cont})
        for b in d.get("query", {}).get("backlinks", []):
            if "redirect" in b:
                out.extend(r["title"] for r in b.get("redirlinks", []))
            else:
                out.append(b["title"])
        if "continue" not in d:
            break
        cont = d["continue"]
    out = sorted(set(out))
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


# Wikidata claim helpers ------------------------------------------------------

def _claim_ids(ent, prop):
    vals = []
    for c in (ent.get("claims") or {}).get(prop, []):
        dv = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(dv, dict) and "id" in dv:
            vals.append(dv["id"])
    return vals


def _claim_strings(ent, prop):
    vals = []
    for c in (ent.get("claims") or {}).get(prop, []):
        dv = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(dv, str):
            vals.append(dv)
    return vals


def _claim_times(ent, prop):
    vals = []
    for c in (ent.get("claims") or {}).get(prop, []):
        dv = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(dv, dict) and "time" in dv:
            vals.append(dv["time"].lstrip("+")[:10])
    return vals


def wd_entities(qids, force=False):
    """qid -> slimmed entity dict. Batches of 50."""
    qids = list(dict.fromkeys(q for q in qids if q))
    out, todo = {}, []
    for q in qids:
        p = _cache_path("wd", q)
        if p.exists() and not force:
            out[q] = json.loads(p.read_text(encoding="utf-8"))
        else:
            todo.append(q)

    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        d = _get(WD_API, {"action": "wbgetentities", "ids": "|".join(batch),
                          "props": "labels|descriptions|claims|sitelinks",
                          "languages": "en", "sitefilter": "enwiki"})
        for qid, ent in (d.get("entities") or {}).items():
            if "missing" in ent:
                rec = {"qid": qid, "missing": True}
            else:
                rec = {
                    "qid": qid,
                    "missing": False,
                    "label": (ent.get("labels", {}).get("en") or {}).get("value"),
                    "description": (ent.get("descriptions", {}).get("en") or {}).get("value"),
                    "enwiki": (ent.get("sitelinks", {}).get("enwiki") or {}).get("title"),
                    "P31": _claim_ids(ent, "P31"),        # instance of
                    "P175": _claim_ids(ent, "P175"),      # performer
                    "P106": _claim_ids(ent, "P106"),      # occupation
                    "P1303": _claim_ids(ent, "P1303"),    # instrument
                    "P264": _claim_ids(ent, "P264"),      # record label
                    "P361": _claim_ids(ent, "P361"),      # part of
                    "P155": _claim_ids(ent, "P155"),      # follows
                    "P156": _claim_ids(ent, "P156"),      # followed by
                    "P136": _claim_ids(ent, "P136"),      # genre
                    "P577": _claim_times(ent, "P577"),    # publication date
                    "P569": _claim_times(ent, "P569"),    # date of birth
                    "P570": _claim_times(ent, "P570"),    # date of death
                    "P18": _claim_strings(ent, "P18"),    # image
                    "P436": _claim_strings(ent, "P436"),  # MusicBrainz release group
                    "P1954": _claim_strings(ent, "P1954"),  # Discogs master
                }
            out[qid] = rec
            _cache_path("wd", qid).write_text(
                json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.1)
    return out


# --- Wikidata class vocabulary ----------------------------------------------
# NOTE: in practice Wikidata types almost every release here as the generic
# Q482994 "album" -- 286 of 291. The studio/live/compilation/box-set
# distinction exists only in the Wikipedia section headings, so the SECTION is
# authoritative for release kind and P31 is used only to decide whether an
# article is a release at all.
RELEASE_CLASSES = {
    "Q482994": "album",
    "Q208569": "studio album",
    "Q209939": "live album",
    "Q222910": "compilation album",
    "Q169930": "extended play",
    "Q134556": "single",
    "Q4198319": "box set",
    "Q1121165": "soundtrack album",
    "Q108352648": "remix album",
    "Q217199": "remix album",
    "Q30070257": "video album",
    "Q7302866": "reissue album",
    "Q20670779": "demo album",
    "Q6041918": "greatest hits album",
    "Q112180489": "concert film",
    "Q11424": "film",
    "Q24862": "short film",
    "Q506240": "television film",
    "Q93204": "documentary film",
    "Q5398426": "television series",
    "Q2431196": "audiovisual work",
    "Q55850593": "album series",
    "Q10590726": "album series",
}
# Musical works (tunes), not releases -- "Naima", "Honeysuckle Rose".
COMPOSITION_CLASSES = {"Q105543609": "musical work", "Q7366": "song",
                       "Q207628": "musical composition", "Q2188189": "musical work"}
# Credited ensembles rather than individuals.
GROUP_CLASSES = {"Q5741069": "rock band", "Q215380": "musical group",
                 "Q2088357": "musical ensemble", "Q9212979": "musical group"}
HUMAN = "Q5"


# --- Wikimedia Commons ------------------------------------------------------

def commons_imageinfo(files, widths=(400, 800), force=False):
    """'File:X.jpg' -> url, thumbnails, size and full extmetadata.

    Queried against commons.wikimedia.org deliberately: Commons only hosts
    freely-licensed media, so a file that comes back "missing" here but exists
    on en.wikipedia is a local non-free (fair-use) upload and must not be
    republished. That distinction is the whole point of asking Commons rather
    than Wikipedia for the file.
    """
    files = list(dict.fromkeys(f for f in files if f))
    out, todo = {}, []
    for f in files:
        p = _cache_path("commons", f)
        if p.exists() and not force:
            out[f] = json.loads(p.read_text(encoding="utf-8"))
        else:
            todo.append(f)

    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        params = {"action": "query", "titles": "|".join(batch),
                  "prop": "imageinfo",
                  "iiprop": "url|size|mime|extmetadata|user|canonicaltitle",
                  "iiurlwidth": widths[0]}
        d = _get(COMMONS_API, params)
        q = d.get("query", {})
        alias = {n["from"]: n["to"] for n in q.get("normalized", [])}
        alias.update({r["from"]: r["to"] for r in q.get("redirects", [])})
        by_title = {}
        for pg in q.get("pages", {}).values():
            ii = (pg.get("imageinfo") or [{}])[0]
            by_title[pg["title"]] = {
                "file": pg["title"],
                "missing": "missing" in pg or not pg.get("imageinfo"),
                "url": ii.get("url"),
                "descriptionurl": ii.get("descriptionurl"),
                "thumb": ii.get("thumburl"),
                "thumb_width": ii.get("thumbwidth"),
                "width": ii.get("width"), "height": ii.get("height"),
                "mime": ii.get("mime"), "uploader": ii.get("user"),
                "extmetadata": {k: v.get("value")
                                for k, v in (ii.get("extmetadata") or {}).items()},
            }
        for f in batch:
            cur, seen = f, set()
            while cur in alias and cur not in seen:
                seen.add(cur)
                cur = alias[cur]
            rec = by_title.get(cur) or {"file": cur, "missing": True}
            out[f] = rec
            _cache_path("commons", f).write_text(
                json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return out


def commons_category_files(category, limit=30, force=False):
    """Files in a Commons category, for people who have P373 but no P18."""
    key = f"cat::{category}"
    p = _cache_path("commons", key)
    if p.exists() and not force:
        return json.loads(p.read_text(encoding="utf-8"))
    title = category if category.startswith("Category:") else f"Category:{category}"
    d = _get(COMMONS_API, {"action": "query", "list": "categorymembers",
                           "cmtitle": title, "cmtype": "file",
                           "cmlimit": limit})
    files = [m["title"] for m in (d.get("query", {}).get("categorymembers") or [])]
    p.write_text(json.dumps(files, ensure_ascii=False), encoding="utf-8")
    return files
