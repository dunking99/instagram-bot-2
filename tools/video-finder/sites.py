"""Site readers: for each site, how to build a search address and how to read the result cards (title, link, thumbnail, length).

Everything here is plain scraping with fixed patterns. No AI, no guessing. Python 3.9, standard library only.
"""
import html
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
MIN_GAP = 1.5            # seconds between two requests to the same site (be polite)
MAX_BLOCK = 7000         # a result card is never longer than this many characters


def slug(q):
    return re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")


def plus(q):
    return urllib.parse.quote_plus(q)


def seconds(text):
    """'10:06' -> 606, '1:02:33' -> 3753, anything else -> None"""
    nums = re.findall(r"\d+", text or "")
    if len(nums) == 1:
        return int(nums[0]) * 60                              # "5 Min": minutes only
    if len(nums) == 2:
        return int(nums[0]) * 60 + int(nums[1])
    if len(nums) == 3:
        return int(nums[0]) * 3600 + int(nums[1]) * 60 + int(nums[2])
    return None


# Each site: where its search is, and how a result card looks.
#   split = text that starts a card;  url / title / thumb / dur = patterns whose first group is the value
SITES = {
    "tnaflix": dict(
        name="tnaflix", home="https://www.tnaflix.com/",
        search=lambda q, pg=1: "https://www.tnaflix.com/search.php?what=" + plus(q) + ("&page=%d" % pg if pg > 1 else ""),
        split=r'<a class="thumb thumb-chrome', url=r'href="([^"]+/video\d+)"', title=r'alt="([^"]*)"',
        thumb=r'data-src="([^"]+)"', dur=r'video-duration">\s*([\d:]+)'),
    "fpo.xxx": dict(
        name="fpo.xxx", home="https://www.fpo.xxx/",
        search=lambda q, pg=1: "https://www.fpo.xxx/search/%s/" % slug(q) + ("?from_videos=%d" % pg if pg > 1 else ""),
        split=r'<div class="item', url=r'href="(https://www\.fpo\.xxx/video/\d+/[^"]+)"', title=r'title="([^"]*)"',
        thumb=r'data-original="([^"]+)"', dur=r'class="duration">\s*([\d:]+)'),
    "xhamster": dict(
        name="xhamster", home="https://xhamster.com/",
        search=lambda q, pg=1: "https://xhamster.com/search/" + slug(q) + ("/%d" % pg if pg > 1 else ""),
        split=r'thumb-list__item video-thumb', url=r'href="(https://xhamster\.com/videos/[^"]+)"', title=r'aria-label="([^"]*)"',
        thumb=r'srcset="(https://[^\s"]+)', dur=r'data-role="video-duration".{0,260}?>(\d{1,2}(?::\d{2}){1,2})<'),
    "youporn": dict(
        name="youporn", home="https://www.youporn.com/",
        search=lambda q, pg=1: "https://www.youporn.com/search/?query=" + plus(q) + ("&page=%d" % pg if pg > 1 else ""),
        split=r'<article class="video-box', url=r'href="(/watch/\d+/[^"]*)"', title=r'aria-label="([^"]*)"',
        thumb=r'data-src="(https://[^"]+)"', dur=r'tm_video_duration">\s*<span>\s*([\d:]+)'),
    "porngrey": dict(
        name="porngrey", home="https://www.porngrey.net/",
        search=lambda q, pg=1: "https://www.porngrey.net/search?q=" + plus(q) + ("&page=%d" % pg if pg > 1 else ""),
        split=r'<a href="/video/', url=r'^<a href="(/video/[^"]+)"', title=r'title="([^"]*)"',
        thumb=r'src="(/images/thumb/[^"]+)"', dur=r'card__info_time">\s*([\d:]+)'),
    "shyfap": dict(
        name="shyfap", home="https://www.shyfap.net/",
        search=lambda q, pg=1: "https://www.shyfap.net/search/?q=" + plus(q) + ("&page=%d" % pg if pg > 1 else ""),
        split=r'<div class="catalog_item"', url=r'href="(/video/[^"]+)"', title=r'media-card_title">([^<]*)<',
        thumb=r'data-original="([^"]+)"', dur=r'#i-clock"></use>.{0,200}?stats_item_value">\s*([\d:]+)'),
    "eporner": dict(
        name="eporner", home="https://www.eporner.com/",
        search=lambda q, pg=1: "https://www.eporner.com/search/%s/" % slug(q) + ("%d/" % pg if pg > 1 else ""),
        split=r'<div class="mb(?: hdy)?" data-id', url=r'href="(/video-[^"]+)"', title=r'class="mbtit"><a[^>]*>([^<]*)<',
        thumb=r'<img src="(https://[^"]+)"', dur=r'title="Duration">\s*([\d:]+)'),
    "freepornvideos": dict(
        name="freepornvideos", home="https://www.freepornvideos.xxx/",
        search=lambda q, pg=1: "https://www.freepornvideos.xxx/search/%s/" % slug(q) + ("%d/" % pg if pg > 1 else ""),
        split=r'<div class="item', url=r'href="(https://www\.freepornvideos\.xxx/videos/[^"]+)"', title=r'title="([^"]*)"',
        thumb=r'<img[^>]*?src="(https://img[^"]+)"', dur=r'class="duration">\s*(?:[A-Za-z ]*?)([\d:]+)'),
    "pornflip": dict(
        name="pornflip", home="https://www.pornflip.com/",
        search=lambda q, pg=1: "https://www.pornflip.com/videos?qry=" + plus(q) + ("&page=%d" % pg if pg > 1 else ""),
        split=r'<div class="card thumbs_rotate itemVideo', url=r'<a href="(/[A-Za-z0-9_-]{6,}/[^"]+)"', title=r'alt="([^"]*)"',
        thumb=r'class="card-img-top" src="([^"]+)"', dur=r'class="duration">\s*([\d:]+)'),
    "pornzog": dict(
        name="pornzog", home="https://pornzog.com/",
        search=lambda q, pg=1: "https://pornzog.com/search/?s=" + plus(q) if pg == 1 else "https://pornzog.com/search/%s/%d/" % (slug(q), pg),
        split=r'<img class="thumb" ', url=r'class="title" href="(/video/[^"]+)"', title=r'alt="([^"]*)"',
        thumb=r'data-original="([^"]+)"', dur=r'class="duration">\s*([\d:]+)'),
    "xozilla": dict(
        name="xozilla", home="https://www.xozilla.com/",
        search=lambda q, pg=1: "https://www.xozilla.com/search/%s/" % slug(q) + ("?from_videos=%d" % pg if pg > 1 else ""),
        split=r'<a href="https://www\.xozilla\.com/videos/\d+/[^"]+" class="item', url=r'^<a href="(https://www\.xozilla\.com/videos/[^"]+)"',
        title=r'<strong class="title">([^<]*)<', thumb=r'data-original="([^"]+)"', dur=r'<div class="duration">\s*([\dms: ]+)</div>'),
    "porntop": dict(
        name="porntop", home="https://porntop.com/",
        search=lambda q, pg=1: "https://porntop.com/videos.php?q=" + plus(q) + ("&p=%d" % pg if pg > 1 else ""),
        split=r'<div class="item">', url=r'href="(/video/[^"]+)"', title=r'title="([^"]*)"',
        thumb=r'data-original="([^"]+)"', dur=r'class="duration">\s*([\d:]+)'),
    "xxxbunker": dict(
        name="xxxbunker", home="https://xxxbunker.com/",
        search=lambda q, pg=1: "https://xxxbunker.com/?search=" + plus(q) + ("&page=%d" % pg if pg > 1 else ""),
        split=r'<div><a href="/\d{6,}"', url=r'^<div><a href="(/\d{6,})"', title=r'<span class="title">([^<]*)<',
        thumb=r'data-src="(//thumbs[^"]+)"', dur=r'class="duration">\s*(\d+)\s*Min'),
    "porntrex": dict(
        name="porntrex", home="https://www.porntrex.com/",
        search=lambda q, pg=1: "https://www.porntrex.com/search/%s/" % slug(q) + ("%d/" % pg if pg > 1 else ""),
        split=r'<div class="video-preview-screen video-item', url=r'href="(https://www\.porntrex\.com/video/\d+/[^"]+)"', title=r'alt="([^"]*)"',
        thumb=r'data-src="(//[^"]+)"', dur=r'class="durations?">(?:<[^>]+>)*\s*([\d:]+)'),
    # trendyporn, youcrazyx and yrprno run the same engine (cards like <div id="vid-168811" ...>); their search only serves page 1 reliably
    "trendyporn": dict(
        name="trendyporn", home="https://www.trendyporn.com/", max_pages=1,
        search=lambda q, pg=1: "https://www.trendyporn.com/search/%s/" % slug(q),
        split=r'<div id="vid-\d+"', url=r'href="(https://www\.trendyporn\.com/video/[^"]+\.html)"', title=r'title="([^"]*)"',
        thumb=r'data-original="([^"]+)"', dur=r'class="duration">\s*([\d:]+)'),
    "youcrazyx": dict(
        name="youcrazyx", home="https://www.youcrazyx.com/", max_pages=1,
        search=lambda q, pg=1: "https://www.youcrazyx.com/search/%s/" % slug(q),
        split=r'<div id="vid-\d+"', url=r'href="(https://www\.youcrazyx\.com/video/[^"]+\.html)"', title=r'title="([^"]*)"',
        thumb=r'data-original="([^"]+)"', dur=r'class="duration">\s*([\d:]+)'),
    "yrprno": dict(
        name="yrprno", home="https://www.yrprno.com/", max_pages=1,
        search=lambda q, pg=1: "https://www.yrprno.com/search/%s/" % slug(q),
        split=r'<div id="vid-\d+"', url=r'href="(https://www\.yrprno\.com/video/[^"]+\.html)"', title=r'title="([^"]*)"',
        thumb=r'data-original="([^"]+)"', dur=r'class="duration">\s*([\d:]+)'),
    "pornhub": dict(
        name="pornhub", home="https://www.pornhub.com/",
        search=lambda q, pg=1: "https://www.pornhub.com/video/search?search=" + plus(q) + ("&page=%d" % pg if pg > 1 else ""),
        split=r'<li class="pcVideoListItem', url=r'href="(/view_video\.php\?viewkey=[a-z0-9]+)"', title=r'title="([^"]*)"',
        thumb=r'data-image="([^"]+)"', dur=r'<var class="duration">\s*([\d:]+)'),
    # playvids runs the same engine as pornflip (/videos?qry=, cards <div class="card thumbs_rotate itemVideo ...">); its results are plain HTML
    "playvids": dict(
        name="playvids", home="https://www.playvids.com/",
        search=lambda q, pg=1: "https://www.playvids.com/videos?qry=" + plus(q) + ("&page=%d" % pg if pg > 1 else ""),
        split=r'<div class="card thumbs_rotate itemVideo', url=r'<a href="(/[A-Za-z0-9_-]{6,}/[^"]+)"', title=r'alt="([^"]*)"',
        thumb=r'class="card-img-top" src="([^"]+)"', dur=r'class="duration">\s*([\d:]+)'),
    # pornwex.tv: same kind of page as fpo.xxx (<div class="item">); search is /search/<words joined by +>/, only page 1 is used (page 2 is loaded by the page itself)
    "pornwex": dict(
        name="pornwex", home="https://www.pornwex.tv/", max_pages=1,
        search=lambda q, pg=1: "https://www.pornwex.tv/search/%s/" % plus(q),
        split=r'<div class="item', url=r'href="(https://www\.pornwex\.tv/video/\d+/[^"]+)"', title=r'title="([^"]*)"',
        thumb=r'<img class="thumb[^"]*" src="([^"]+)"', dur=r'class="duration">\s*([\d:]+)'),
    # porneec.com: WordPress; /?s= needs every word to match, so a loose query returns nothing; only page 1 is used
    "porneec": dict(
        name="porneec", home="https://porneec.com/", max_pages=1,
        search=lambda q, pg=1: "https://porneec.com/?s=" + plus(q),
        split=r'<article data-video-id', url=r'<a href="(https://porneec\.com/[^"]+/)"', title=r'<span class="title">([^<]*)<',
        thumb=r'data-main-thumb="([^"]+)"', dur=r'class="duration">\s*([\d:]+)'),
}

# Sites whose video address can be read straight from the page and streamed without downloading (tested in ~/stream-test)
STREAMABLE = {"freepornvideos", "fpo.xxx", "xozilla", "porntrex"}

# Sites tested but not usable yet (shown greyed out in the dashboard)
UNAVAILABLE = {
    "fapcat": "Behind a Cloudflare 'Just a moment' check (bot detection). Not bypassed.",
    "exporntoons": "Behind a Cloudflare 'Just a moment' check (bot detection). Not bypassed.",
    "ukdevilz": "Behind a Cloudflare 'Just a moment' check (bot detection). Not bypassed.",
    "tyler-brown": "Its search ignores the query (always the same list), so it can't be searched.",
    "peekvids": "Answers 'too many requests' (HTTP 429) to this kind of reader.",
    "noodlemagazine": "Refuses this kind of reader (HTTP 403).",
}

_locks = {k: threading.Lock() for k in SITES}
_last = {k: 0.0 for k in SITES}


def fetch(site, url):
    """-> (text, error). A 404 means 'no results' (some sites answer that way), not an error."""
    with _locks[site]:                                       # one request at a time per site, with a pause between them
        wait = MIN_GAP - (time.time() - _last[site])
        if wait > 0:
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en", "Referer": SITES[site]["home"]})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace"), None
        except urllib.error.HTTPError as e:
            return "", (None if e.code == 404 else "HTTP %d" % e.code)
        except Exception as e:
            return "", "%s" % (getattr(e, "reason", e),)
        finally:
            _last[site] = time.time()


def parse_xhamster(text):
    """xhamster's page holds most cards as placeholders, but lists every video as JSON: id, duration, title, pageURL, thumbURL."""
    cards = {}
    for m in re.finditer(r'\{"id":\d+,"duration":(\d+),"created":\d+,"title":"((?:[^"\\]|\\.)*)".{0,600}?"pageURL":"([^"]+)","thumbURL":"([^"]+)"', text, re.S):
        try:
            title, url, thumb = (json.loads('"%s"' % m.group(i)) for i in (2, 3, 4))
        except ValueError:
            continue
        cards.setdefault(url, dict(url=url, title=html.unescape(title).strip(), thumb=thumb, duration=int(m.group(1))))
    return list(cards.values())


def parse(site, text):
    """Result cards of one search page -> [{url, title, thumb, duration}] (duration in seconds or None)"""
    if site == "xhamster":
        return parse_xhamster(text)
    spec = SITES[site]
    text = re.sub(r'src="data:[^"]{60,}"', 'src=""', text)    # placeholder images can be tens of kilobytes and push the title out of reach
    idx = [m.start() for m in re.finditer(spec["split"], text)]
    cards = {}
    for a, b in zip(idx, idx[1:] + [len(text)]):
        block = text[a:min(b, a + MAX_BLOCK)]
        def grab(key, flags=re.S):
            m = re.search(spec[key], block, flags)
            return html.unescape(m.group(1)).strip() if m else ""
        url = grab("url")
        if not url:
            continue
        url = urllib.parse.urljoin(spec["home"], url)
        card = dict(url=url, title=grab("title") or grab_alt(block), thumb=urllib.parse.urljoin(spec["home"], grab("thumb")) if grab("thumb") else "",
                    duration=seconds(grab("dur")), full=bool(re.search(r'class="duration">\s*Full Video', block)))   # some sites label full-length videos
        old = cards.get(url)
        if old:                                              # the same video can appear twice on a page: keep the fuller entry
            for k, v in card.items():
                if v and not old.get(k):
                    old[k] = v
        else:
            cards[url] = card
    return list(cards.values())


def grab_alt(block):
    m = re.search(r'alt="([^"]*)"', block)
    return html.unescape(m.group(1)).strip() if m else ""


def search(site, query, page=1):
    """-> (cards, error, address) for one query (one result page) on one site"""
    url = SITES[site]["search"](query, page)
    text, err = fetch(site, url)
    if err:
        return [], err, url
    return parse(site, text), None, url
