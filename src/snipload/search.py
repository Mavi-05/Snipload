"""YouTube und Twitch: Suche, Kanaele, VODs, Clips, Live - alles im gleichen Format fuer die Oberflaeche.

Ein Eintrag (item) sieht immer so aus:
  {kind: video|channel|clip|live, platform: youtube|twitch, id, url, title, channel, channel_url,
   thumb, duration, views, ts (Unix-Zeit oder None), live (bool), avatar, followers, handle}
"""
import json
import re
import time
import urllib.parse
import urllib.request

from . import tools

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36"}
TWITCH_GQL = "https://gql.twitch.tv/gql"
TWITCH_CLIENT_IDS = ["kimne78kx3ncx6brgo4mv6wki5h1ko", "ue6666qo983tsx6so1t0vnawi233wa"]


class SearchError(Exception):
    pass


# ================================================================ Link erkennen
YT_VIDEO = re.compile(r"(?:youtube\.com/(?:watch\?.*?v=|shorts/|live/|embed/)|youtu\.be/)([\w-]{11})")
YT_CHANNEL = re.compile(r"youtube\.com/((?:@[\w.\-%]+)|(?:channel/UC[\w-]{22})|(?:c/[\w.\-%]+)|(?:user/[\w.\-%]+))",
                        re.I)
TW_VOD = re.compile(r"twitch\.tv/(?:[\w]+/)?(?:videos|v)/(\d+)", re.I)
TW_CLIP = re.compile(r"(?:clips\.twitch\.tv/(?:embed\?clip=)?|twitch\.tv/\w+/clip/)([\w-]+)", re.I)
TW_CHANNEL = re.compile(r"twitch\.tv/(?!videos|directory|p/|downloads|settings|search)([A-Za-z0-9_]{2,25})/?(?:$|\?|#|"
                        r"/(?:videos|clips|about|schedule)\b)", re.I)


def classify(text):
    """Was ist das? -> (art, wert). art: video | channel | search"""
    t = (text or "").strip()
    if not t:
        return "search", ""
    low = t.lower()
    if not re.match(r"^(https?://|www\.|m\.|youtu|twitch|clips\.)", low):
        return "search", t
    if not low.startswith("http"):
        t = "https://" + t
    m = YT_VIDEO.search(t)
    if m:
        return "video", t
    m = YT_CHANNEL.search(t)
    if m:
        return "channel", {"platform": "youtube", "id": m.group(1), "url": "https://www.youtube.com/" + m.group(1)}
    if TW_VOD.search(t) or TW_CLIP.search(t):
        return "video", t
    m = TW_CHANNEL.search(t)
    if m:
        return "channel", {"platform": "twitch", "id": m.group(1).lower(),
                           "url": "https://www.twitch.tv/" + m.group(1).lower()}
    return "video", t


def platform_of(url):
    u = (url or "").lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "twitch.tv" in u:
        return "twitch"
    if "kick.com" in u:
        return "kick"
    return "other"


# ================================================================ Hilfen
def _https(u):
    if not u:
        return None
    return "https:" + u if u.startswith("//") else u


def _best_thumb(thumbs, want=480):
    best, bd = None, None
    for t in thumbs or []:
        u = _https(t.get("url"))
        if not u:
            continue
        w = t.get("width") or 0
        d = abs((w or want) - want)
        if best is None or d < bd:
            best, bd = u, d
    return best


def _ytdlp_json(args, timeout=60):
    base = tools.ytdlp_cmd()
    if not base:
        raise SearchError("yt-dlp missing")
    r = tools.run(base + tools.cookie_args() + ["-J", "--no-warnings", "--ignore-no-formats-error"] + args, timeout)
    out = (r.stdout or b"").decode("utf-8", "replace").strip()
    if r.returncode != 0 or not out:
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise SearchError(tools.friendly_error(err[-1] if err else "error"))
    return json.loads(out)


def _yt_item(e):
    vid = e.get("id")
    url = e.get("url") or ""
    ie = (e.get("ie_key") or "").lower()
    if ie == "youtubetab" or (url and ("/channel/" in url or "/@" in url) and "watch" not in url):
        avatar = _best_thumb(e.get("thumbnails"), 176)
        return {"kind": "channel", "platform": "youtube", "id": e.get("channel_id") or vid,
                "url": e.get("uploader_url") or e.get("channel_url") or url,
                "title": e.get("channel") or e.get("title"), "channel": e.get("channel") or e.get("title"),
                "avatar": avatar, "thumb": avatar, "followers": e.get("channel_follower_count"),
                "handle": e.get("uploader_id"), "verified": bool(e.get("channel_is_verified")),
                "videos": e.get("playlist_count"), "description": e.get("description")}
    live = e.get("live_status") in ("is_live", "is_upcoming") or bool(e.get("is_live"))
    is_short = "/shorts/" in url
    return {"kind": "live" if live else "video", "platform": "youtube", "id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}" if vid else url,
            "title": e.get("title"), "channel": e.get("channel") or e.get("uploader"),
            "channel_url": e.get("channel_url") or e.get("uploader_url"),
            "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg" if vid else _best_thumb(e.get("thumbnails")),
            "duration": e.get("duration"), "views": e.get("view_count") or e.get("concurrent_view_count"),
            "ts": e.get("timestamp") or e.get("release_timestamp"), "live": live, "short": is_short,
            "upcoming": e.get("live_status") == "is_upcoming"}


# ================================================================ YouTube
def youtube_search(query, kind="videos", limit=24):
    if kind == "channels":
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query) + "&sp=EgIQAg%253D%253D"
        data = _ytdlp_json(["--flat-playlist", "--playlist-end", str(limit), url], 60)
    elif kind == "live":
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query) + "&sp=EgJAAQ%253D%253D"
        data = _ytdlp_json(["--flat-playlist", "--playlist-end", str(limit), url], 60)
    else:
        data = _ytdlp_json(["--flat-playlist", f"ytsearch{limit}:{query}"], 60)
    items = [_yt_item(e) for e in data.get("entries") or [] if isinstance(e, dict)]
    if kind == "channels":
        items = [i for i in items if i["kind"] == "channel"]
    return items


def youtube_channel(ident, tab="videos", limit=48):
    """ident: '@handle', 'channel/UC…' oder volle URL. tab: videos | streams | shorts"""
    base = ident if ident.startswith("http") else "https://www.youtube.com/" + ident.lstrip("/")
    base = re.sub(r"/(videos|streams|shorts|featured|about|playlists|live)/?$", "", base.rstrip("/"))
    data = _ytdlp_json(["--flat-playlist", "--playlist-end", str(limit), f"{base}/{tab}"], 90)
    thumbs = data.get("thumbnails") or []
    avatar = next((_https(t.get("url")) for t in thumbs if "avatar" in str(t.get("id", ""))), None)
    banner = next((_https(t.get("url")) for t in thumbs if "banner" in str(t.get("id", ""))), None)
    ch = {"platform": "youtube", "id": data.get("channel_id") or ident, "url": base,
          "title": data.get("channel") or data.get("uploader") or data.get("title"),
          "handle": data.get("uploader_id"), "followers": data.get("channel_follower_count"),
          "avatar": avatar or _best_thumb(thumbs, 176), "banner": banner,
          "description": (data.get("description") or "")[:400], "verified": bool(data.get("channel_is_verified")),
          "live": None}
    items = []
    for e in data.get("entries") or []:
        if not isinstance(e, dict):
            continue
        it = _yt_item(e)
        it["channel"] = it.get("channel") or ch["title"]
        if tab == "shorts":
            it["short"] = True
        items.append(it)
    return {"channel": ch, "items": items, "tabs": ["videos", "streams", "shorts"], "tab": tab}


# ================================================================ Twitch
def _gql(payload, timeout=20):
    """Twitch-GraphQL. Probiert die bekannten Client-IDs der Twitch-Webseite nacheinander."""
    last = None
    for cid in TWITCH_CLIENT_IDS:
        req = urllib.request.Request(TWITCH_GQL, data=json.dumps(payload).encode(), method="POST",
                                     headers=dict(UA, **{"Client-ID": cid, "Content-Type": "text/plain;charset=UTF-8"}))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as ex:
            last = ex
            continue
        errs = data.get("errors") if isinstance(data, dict) else None
        if errs and not data.get("data"):
            last = SearchError(str(errs[0].get("message", errs)))
            continue
        return data
    raise SearchError(f"Twitch: {last}")


def _tw_thumb(u, w=480, h=270):
    if not u:
        return None
    return u.replace("%{width}", str(w)).replace("%{height}", str(h)).replace("{width}", str(w)).replace(
        "{height}", str(h))


def _ts(iso):
    if not iso:
        return None
    try:
        return int(time.mktime(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone)
    except Exception:
        return None


def _tw_channel_item(u):
    st = u.get("stream") or None
    return {"kind": "channel", "platform": "twitch", "id": u.get("login"), "url": f"https://www.twitch.tv/{u.get('login')}",
            "title": u.get("displayName") or u.get("login"), "channel": u.get("displayName") or u.get("login"),
            "handle": u.get("login"), "avatar": u.get("profileImageURL"), "thumb": u.get("profileImageURL"),
            "followers": (u.get("followers") or {}).get("totalCount"), "description": u.get("description"),
            "live": bool(st), "live_title": (st or {}).get("title"), "viewers": (st or {}).get("viewersCount"),
            "game": ((st or {}).get("game") or {}).get("displayName")}


USER_FIELDS = """id login displayName description profileImageURL(width:300) bannerImageURL
  followers { totalCount }
  stream { id title viewersCount createdAt game { displayName } previewImageURL(width:640, height:360)
           archiveVideo { id } }"""


def twitch_search(query, limit=16):
    q = query.strip().lstrip("@")
    items = []
    try:
        data = _gql({"query": "query($q:String!,$n:Int){searchUsers(userQuery:$q, first:$n){edges{node{%s}}}}"
                     % USER_FIELDS, "variables": {"q": q, "n": limit}})
        for e in ((data.get("data") or {}).get("searchUsers") or {}).get("edges") or []:
            if e and e.get("node"):
                items.append(_tw_channel_item(e["node"]))
    except SearchError:
        pass
    if re.fullmatch(r"[A-Za-z0-9_]{2,25}", q) and not any(i["handle"].lower() == q.lower() for i in items):
        try:   # genauer Treffer nach Login nach vorne
            u = twitch_user(q)
            if u:
                items.insert(0, _tw_channel_item(u))
        except SearchError:
            pass
    items.sort(key=lambda i: (not i["live"], i["handle"].lower() != q.lower()))
    return items


def twitch_user(login):
    data = _gql({"query": "query($l:String!){user(login:$l){%s}}" % USER_FIELDS, "variables": {"l": login}})
    return (data.get("data") or {}).get("user")


def _tw_video_item(n, login=None, name=None):
    vid = n.get("id")
    return {"kind": "video", "platform": "twitch", "id": vid, "url": f"https://www.twitch.tv/videos/{vid}",
            "title": n.get("title"), "channel": name or login, "channel_url": f"https://www.twitch.tv/{login}" if login else None,
            "thumb": _tw_thumb(n.get("previewThumbnailURL")), "duration": n.get("lengthSeconds"),
            "views": n.get("viewCount"), "ts": _ts(n.get("createdAt")), "game": (n.get("game") or {}).get("displayName"),
            "live": n.get("status") == "RECORDING"}


def _tw_clip_item(n, login=None, name=None):
    slug = n.get("slug") or n.get("id")
    return {"kind": "clip", "platform": "twitch", "id": slug, "url": n.get("url") or f"https://clips.twitch.tv/{slug}",
            "title": n.get("title"), "channel": name or login, "thumb": n.get("thumbnailURL"),
            "duration": n.get("durationSeconds"), "views": n.get("viewCount"), "ts": _ts(n.get("createdAt")),
            "game": (n.get("game") or {}).get("displayName"), "curator": (n.get("curator") or {}).get("displayName"),
            "vod": ((n.get("video") or {}).get("id")), "vod_offset": n.get("videoOffsetSeconds")}


TW_TABS = ["archives", "highlights", "uploads", "clips_7d", "clips_30d", "clips_all"]


def twitch_channel(login, tab="archives", limit=36):
    login = login.lower().lstrip("@")
    u = twitch_user(login)
    if not u:
        raise SearchError(f'Twitch channel "{login}" not found')
    ch = _tw_channel_item(u)
    ch["banner"] = u.get("bannerImageURL")
    st = u.get("stream")
    ch["stream"] = None
    if st:
        ch["stream"] = {"title": st.get("title"), "viewers": st.get("viewersCount"),
                        "thumb": st.get("previewImageURL"), "started": _ts(st.get("createdAt")),
                        "game": (st.get("game") or {}).get("displayName"),
                        "vod": (st.get("archiveVideo") or {}).get("id")}
    items = []
    name = ch["title"]
    if tab.startswith("clips"):
        period = {"clips_7d": "LAST_WEEK", "clips_30d": "LAST_MONTH", "clips_all": "ALL_TIME", "clips_24h": "LAST_DAY"}
        try:
            data = _gql({"query": """query($l:String!,$n:Int,$p:ClipsPeriod){user(login:$l){clips(first:$n,
                        criteria:{period:$p, sort:VIEWS_DESC}){edges{node{id slug title durationSeconds viewCount createdAt
                        thumbnailURL url videoOffsetSeconds game{displayName} curator{displayName} video{id}}}}}}""",
                         "variables": {"l": login, "n": min(limit, 50), "p": period.get(tab, "LAST_WEEK")}})
            for e in (((data.get("data") or {}).get("user") or {}).get("clips") or {}).get("edges") or []:
                if e and e.get("node"):
                    items.append(_tw_clip_item(e["node"], login, name))
        except SearchError:
            rng = {"clips_7d": "7d", "clips_30d": "30d", "clips_all": "all", "clips_24h": "24hr"}.get(tab, "7d")
            data = _ytdlp_json(["--flat-playlist", "--playlist-end", str(limit),
                                f"https://www.twitch.tv/{login}/clips?filter=clips&range={rng}"], 60)
            for e in data.get("entries") or []:
                items.append({"kind": "clip", "platform": "twitch", "id": e.get("id"), "url": e.get("url"),
                              "title": e.get("title"), "channel": name, "thumb": e.get("thumbnail"),
                              "duration": e.get("duration"), "views": e.get("view_count"), "ts": e.get("timestamp")})
    else:
        btype = {"archives": "ARCHIVE", "highlights": "HIGHLIGHT", "uploads": "UPLOAD"}.get(tab, "ARCHIVE")
        try:
            data = _gql({"query": """query($l:String!,$n:Int,$t:BroadcastType){user(login:$l){videos(first:$n, type:$t,
                        sort:TIME){edges{node{id title lengthSeconds createdAt viewCount status
                        previewThumbnailURL(width:480, height:270) game{displayName}}}}}}""",
                         "variables": {"l": login, "n": limit, "t": btype}})
            for e in (((data.get("data") or {}).get("user") or {}).get("videos") or {}).get("edges") or []:
                if e and e.get("node"):
                    items.append(_tw_video_item(e["node"], login, name))
        except SearchError:
            data = _ytdlp_json(["--flat-playlist", "--playlist-end", str(limit),
                                f"https://www.twitch.tv/{login}/videos?filter={tab}"], 60)
            for e in data.get("entries") or []:
                items.append({"kind": "video", "platform": "twitch", "id": e.get("id"),
                              "url": e.get("url") or f"https://www.twitch.tv/videos/{e.get('id')}",
                              "title": e.get("title"), "channel": name, "thumb": e.get("thumbnail"),
                              "duration": e.get("duration"), "views": e.get("view_count"), "ts": e.get("timestamp")})
    return {"channel": ch, "items": items, "tabs": TW_TABS[:3] + ["clips_7d", "clips_30d", "clips_all"], "tab": tab}


def twitch_vod_meta(vod_id):
    """Zusatzinfos zu einem VOD: Vorschaubilder fuer die Zeitleiste (Sprite-Sheets), Kanal, Kapitel."""
    data = _gql({"query": """query($id:ID!){video(id:$id){id title lengthSeconds seekPreviewsURL
                 owner{id login displayName} game{displayName}
                 moments(momentRequestType:VIDEO_CHAPTER_MARKERS){edges{node{positionMilliseconds durationMilliseconds
                 description details{... on GameChangeMomentDetails{game{displayName}}}}}}}}""",
                 "variables": {"id": str(vod_id)}})
    v = (data.get("data") or {}).get("video") or {}
    out = {"owner": v.get("owner"), "chapters": []}
    for e in ((v.get("moments") or {}).get("edges") or []):
        n = (e or {}).get("node") or {}
        start = (n.get("positionMilliseconds") or 0) / 1000
        dur = (n.get("durationMilliseconds") or 0) / 1000
        title = n.get("description") or (((n.get("details") or {}).get("game") or {}).get("displayName")) or ""
        out["chapters"].append({"start_time": start, "end_time": start + dur, "title": title})
    sp = v.get("seekPreviewsURL")
    if sp:
        try:
            req = urllib.request.Request(sp, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                sheets = json.loads(r.read().decode("utf-8"))
            base = sp.rsplit("/", 1)[0] + "/"
            best = None
            for s in sheets or []:
                if not best or (s.get("width", 0) > best.get("width", 0)):
                    best = s
            if best:
                out["storyboard"] = {"width": best.get("width"), "height": best.get("height"), "cols": best.get("cols"),
                                     "rows": best.get("rows"), "interval": best.get("interval"),
                                     "count": best.get("count"),
                                     "sheets": [base + img for img in best.get("images") or []]}
        except Exception:
            pass
    return out


def channel(platform, ident, tab=None):
    if platform == "twitch":
        return twitch_channel(ident, tab or "archives")
    return youtube_channel(ident, tab or "videos")


def search(query, platform="youtube", kind="videos"):
    if platform == "twitch":
        return twitch_search(query)
    return youtube_search(query, kind)
