"""Scoring: fixed rules, plain arithmetic. No AI. The same input always gives the same ranking.

The numbers live in rules.json (editable in the dashboard). Every score comes with the list of reasons that produced it.
"""
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_FILE = os.path.join(HERE, "rules.json")

DEFAULT_RULES = {
    "points": {
        "title_phrase": 35,          # the whole data18 title appears in the result's title (words in a row)
        "title_words": 25,           # otherwise: this many points x the share of the title's words that appear
        "performer_each": 20,        # per performer whose name appears in the result's title
        "performer_cap": 40,         # most points performers can give in total
        "performer_missing": 0,      # points lost when data18 lists performers but none appear in the title (0: many sites leave names out of titles)
        "studio": 10,                # the studio's name appears in the result's title
        "full_video_label": 5,        # the site itself labels the result "Full Video" (only some sites do)
        "length_match": 15,           # the result's length is within "length_match_within_minutes" of the length data18 gives
        "length_bonus": 10           # (only when data18's length is unknown) longer videos score a little higher (full scene over cut-down version)...
    },
    "length_match_within_minutes": 2.5,
    "short_version_below": 0.7,           # a result shorter than this share of data18's length is a shorter version...
    "short_version_penalty": -20,         # ...and loses this many points
    "hide_short_versions": False,         # true = leave shorter versions out of the results altogether
    "long_version_above": 1.5,            # a result longer than this multiple (a compilation?)...
    "long_version_penalty": -10,          # ...loses this many points
    "length_bonus_full_at_minutes": 40,   # ...reaching the full bonus at this many minutes
    "min_minutes": 3,                     # results shorter than this are left out (trailers, clips)
    "confident_score": 70,                # at least this score, and ahead of the next result by "confident_lead", = confident match
    "confident_lead": 15,
    "possible_score": 40,                 # at least this = a possible match (shown, but you decide); below = no match
    "override_min_performers": 2,         # ...unless the title names the studio AND every performer, and there are at least this many performers
    "no_title_evidence_cap": 30,          # a result with no title match at all can never score above this (performer + length alone is not a match)
    "search_ladder": [                    # Blanks: {title} {title_core} {title_key} {performer} {performers} {studio}. {title_core} = the title without small words like "to" and "the"; {title_key} = its first three real words
        {"q": "{title_core} {performer}", "pages": 1},    # pages = result pages read in the main pass; deep = extra pages read only if nothing was found (the whole pass is skipped on other sites, see deep_sites)
        {"q": "{performer}", "pages": 1, "deep": 4},
        {"q": "{title_core}", "pages": 1},
        {"q": "{performer} {studio} {title_core}", "pages": 1},
        {"q": "{performer} {title_core}", "pages": 1, "extra": True},    # extra: only tried on extra_sites, and only when the main queries found nothing
        {"q": "{title} {performer}", "pages": 1, "extra": True},
        {"q": "{title_key} {performer}", "pages": 1, "extra": True},
        {"q": "{title_key}", "pages": 1, "extra": True}
    ],
    "extra_sites": ["freepornvideos", "fpo.xxx", "xozilla", "porntrex"],
    "stop_when_confident": 1,             # stop searching a site as soon as it has a confident match
    "streamable_first": 1,                # search the streamable sites first; skip the rest when one of them has a confident match
    "streamable_only": 0,                 # 1 = never search the non-streamable sites (about a third of the requests); "Search all sites" in the page still does
    "deep_when_nothing": 1,               # read the deep pages only when the main pass found nothing on that site...
    "deep_sites": ["freepornvideos", "fpo.xxx", "xozilla", "porntrex", "tnaflix", "pornzog", "eporner"],   # ...and only on these sites (empty list = all)
    "max_requests_per_site": 14,
    "stopwords": ["a", "an", "the", "and", "of", "to", "in", "on", "for", "with", "my", "your", "her", "his", "at", "by", "is", "it", "our"]
}


def load_rules():
    try:
        with open(RULES_FILE) as f:
            rules = json.load(f)
    except (OSError, ValueError):
        rules = {}
    out = json.loads(json.dumps(DEFAULT_RULES))
    for k, v in rules.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def check_rules(rules):
    """Raise ValueError with a plain message when edited rules can't be used."""
    if not isinstance(rules, dict):
        raise ValueError("The rules must be a JSON object.")
    for k, default in DEFAULT_RULES.items():
        if k not in rules:
            raise ValueError("Missing setting: %s" % k)
        if isinstance(default, dict):
            for kk, dv in default.items():
                if not isinstance(rules[k].get(kk), (int, float)):
                    raise ValueError("%s.%s must be a number." % (k, kk))
        elif isinstance(default, (int, float)) and not isinstance(rules[k], (int, float)):
            raise ValueError("%s must be a number." % k)
        elif isinstance(default, list) and not isinstance(rules[k], list):
            raise ValueError("%s must be a list." % k)
    return rules


FILLER = {"video", "videos", "full", "hd", "porn", "xxx", "movie", "scene", "uncut", "official"}
SYNONYMS = {"pt": "part", "ep": "episode", "vol": "volume", "stepsis": "stepsister", "stepmom": "stepmother", "stepdad": "stepfather"}


LOOKALIKES = str.maketrans({   # letters from other alphabets that look like plain ones (some titles use them on purpose)
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i", "ѕ": "s", "ј": "j", "ԁ": "d", "һ": "h", "ӏ": "l",
    "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ꜰ": "f", "ɢ": "g", "ʜ": "h", "ɪ": "i", "ᴊ": "j", "ᴋ": "k", "ʟ": "l", "ᴍ": "m",
    "ɴ": "n", "ᴏ": "o", "ᴘ": "p", "ʀ": "r", "ꜱ": "s", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w", "ʏ": "y", "ᴢ": "z"})


def tokens(text):
    """Lowercase words with accents, punctuation and html leftovers removed, 'Pt.' read as 'part', and so on."""
    text = (text or "").lower().translate(LOOKALIKES)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.replace("&", " and ")
    words = re.findall(r"[a-z0-9]+", text)
    return [SYNONYMS.get(w, w) for w in words]


def contains_run(haystack, needle):
    """True when the words of `needle` appear in `haystack` one after another."""
    n = len(needle)
    return n > 0 and any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def score(card, want, rules):
    """-> (points, [reasons]) for one result card against what we are looking for.
    want = {title, performers:[...], studio}"""
    pts, why = rules["points"], []
    stop = set(rules["stopwords"])
    cand = tokens(card["title"])
    total = 0.0

    # title (counts in proportion to how much of the result's title it is: "To Ourselves" is all of "To Ourselves", but only a part of "Time To Ourselves, Dear")
    wt = tokens(want.get("title"))
    wt_core = [w for w in wt if w not in stop]
    if wt_core:
        known = set()
        for p in (want.get("performers") or []):
            known |= set(tokens(p))
        known |= set(tokens(want.get("studio")))
        # the result's title words that are not stop words, performers, the studio, filler ("full video", "hd") or the numbers of a date ("2026 02 23")
        dated = any(re.fullmatch(r"(19|20)\d\d", w) for w in cand)             # a year in the title means its other bare numbers are probably the date; without one ("Pure Lust 2") they are part of the name
        extras = [w for w in cand if w not in stop and w not in known and w not in FILLER and not (dated and w.isdigit() and w not in wt)]
        coverage = len(wt_core) / float(max(len(extras), len(wt_core)))
        if contains_run(cand, wt):
            got = round(pts["title_phrase"] * coverage, 1)
            total += got
            why.append("title phrase found +%g%s" % (got, "" if coverage >= 1 else " (%d of %d title words are the title)" % (len(wt_core), len(extras))))
        else:
            share = sum(1 for w in wt_core if w in cand) / float(len(wt_core))
            got = round(pts["title_words"] * share * coverage, 1)
            if got:
                total += got
                why.append("%d of %d title words found +%g" % (round(share * len(wt_core)), len(wt_core), got))
            else:
                why.append("no title words found +0")

    title_pts = total

    # performers
    perfs = [p for p in (want.get("performers") or []) if tokens(p)]
    if perfs:
        got, names = 0.0, []
        for p in perfs:
            pt = tokens(p)
            if all(w in cand for w in pt):
                got += pts["performer_each"]
                names.append(p)
        got = min(got, pts["performer_cap"])
        if names:
            total += got
            why.append("%s found +%g" % (", ".join(names), got))
        else:
            total += pts["performer_missing"]
            why.append("no performer named in the title %g" % pts["performer_missing"])
    else:
        why.append("data18 lists no performers (not scored)")

    # studio
    st = tokens(want.get("studio"))
    if st and all(w in cand for w in st):
        total += pts["studio"]
        why.append("studio %s found +%g" % (want["studio"], pts["studio"]))

    # the site's own "Full Video" label
    if card.get("full") and pts.get("full_video_label"):
        total += pts["full_video_label"]
        why.append("labelled 'Full Video' by the site +%g" % pts["full_video_label"])

    # length
    dur = card.get("duration")
    want_min = (want.get("duration") or 0) / 60.0
    if dur is not None:
        minutes = dur / 60.0
        if minutes < rules["min_minutes"]:
            return -999.0, ["too short (%.1f min, under %g)" % (minutes, rules["min_minutes"])]
        if want_min > 0:                                           # data18 told us how long the scene is
            ratio = minutes / want_min
            if abs(minutes - want_min) <= rules["length_match_within_minutes"]:
                total += pts["length_match"]
                why.append("length %d min matches data18's %d min +%g" % (round(minutes), round(want_min), pts["length_match"]))
            elif ratio < rules["short_version_below"]:
                if rules["hide_short_versions"]:
                    return -999.0, ["shorter version (%d of %d min), hidden" % (round(minutes), round(want_min))]
                total += rules["short_version_penalty"]
                why.append("SHORTER VERSION: %d min of data18's %d min %g" % (round(minutes), round(want_min), rules["short_version_penalty"]))
            elif ratio > rules["long_version_above"]:
                total += rules["long_version_penalty"]
                why.append("much longer than data18's %d min (%d min) %g" % (round(want_min), round(minutes), rules["long_version_penalty"]))
            else:
                why.append("%d min (data18: %d min), no length points" % (round(minutes), round(want_min)))
        else:
            bonus = round(pts["length_bonus"] * min(minutes, rules["length_bonus_full_at_minutes"]) / rules["length_bonus_full_at_minutes"], 1)
            total += bonus
            why.append("%d min long +%g" % (round(minutes), bonus))
    else:
        why.append("length unknown")
    strong = bool(st) and all(w in cand for w in st) and len(perfs) >= rules["override_min_performers"] and all(all(w in cand for w in tokens(p)) for p in perfs)
    if wt_core and title_pts <= 0 and total > rules["no_title_evidence_cap"] and not strong:
        total = rules["no_title_evidence_cap"]
        why.append("no title evidence: capped at %g" % total)
    elif wt_core and title_pts <= 0 and strong:
        why.append("no title words, but the studio and all performers are named")
    return round(total, 1), why


def verdict(ranked, rules):
    """ranked = results sorted best first (each has 'score'). -> 'confident' | 'possible' | 'none'"""
    if not ranked or ranked[0]["score"] < rules["possible_score"]:
        return "none"
    lead = ranked[0]["score"] - (ranked[1]["score"] if len(ranked) > 1 else -999)
    if ranked[0]["score"] >= rules["confident_score"] and lead >= rules["confident_lead"]:
        return "confident"
    return "possible"
