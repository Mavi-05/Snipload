"""Chat: Twitch-VOD-Chat und YouTube-Livechat-Wiederholungen laden, Hype-Momente finden und den Chat als
Video rendern - transparent (MOV ProRes 4444 / WebM) fuer Premiere/After Effects/CapCut oder zum Einbrennen.

Eine Nachricht: {"t": Sekunden ab VOD-Anfang, "user", "color", "parts": [{"t": text} | {"e": emote-url, "n": code}],
                 "badges": [url], "kind": "msg"|"super"}
"""
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import threading
import urllib.request

from . import tools
from .util import NO_WINDOW, clean_env, config_dir, web_path

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36"}
GQL = "https://gql.twitch.tv/gql"
GQL_CLIENT = "kimne78kx3ncx6brgo4mv6wki5h1ko"
COMMENTS_HASH = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"
NAME_COLORS = ["#ff4a4a", "#4aa3ff", "#3ddc84", "#ffb020", "#c084fc", "#ff6fb0", "#2dd4bf", "#f97316",
               "#a3e635", "#60a5fa", "#f472b6", "#facc15"]

DEFAULT_STYLE = {"width": 420, "height": 720, "font_size": 22, "bg": "none", "bg_opacity": 0.55,
                 "msg_bg": True, "badges": True, "emotes": True, "max_age": 20.0, "shadow": True,
                 "name_colors": True, "text_color": "#ffffff", "pos": "left", "scale": 0.36}


class ChatError(Exception):
    pass


def _post(payload, timeout=20):
    req = urllib.request.Request(GQL, data=json.dumps(payload).encode(), method="POST",
                                 headers=dict(UA, **{"Client-ID": GQL_CLIENT, "Content-Type": "text/plain;charset=UTF-8"}))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _name_color(name):
    h = int(hashlib.md5((name or "?").encode()).hexdigest()[:6], 16)
    return NAME_COLORS[h % len(NAME_COLORS)]


# ================================================================ Twitch
def twitch_vod_id(url):
    m = re.search(r"twitch\.tv/(?:\w+/)?(?:videos|v)/(\d+)", url or "")
    return m.group(1) if m else None


def twitch_comments(vod_id, start=0.0, end=None, progress=None, cancel=None):
    """Kommentare eines VODs zwischen start und end (Sekunden)."""
    out, seen = [], set()
    cursor = None
    offset = int(max(0, start))
    pages = 0
    while True:
        if cancel and cancel():
            raise ChatError("cancelled")
        variables = {"videoID": str(vod_id)}
        if cursor:
            variables["cursor"] = cursor
        else:
            variables["contentOffsetSeconds"] = offset
        payload = [{"operationName": "VideoCommentsByOffsetOrCursor", "variables": variables,
                    "extensions": {"persistedQuery": {"version": 1, "sha256Hash": COMMENTS_HASH}}}]
        try:
            data = _post(payload)
        except Exception as ex:
            if cursor:          # Cursor abgelehnt -> per Zeitpunkt weiter
                cursor = None
                offset = int(out[-1]["t"]) + 1 if out else offset + 1
                continue
            raise ChatError(f"Twitch chat: {ex}")
        d = data[0] if isinstance(data, list) else data
        if d.get("errors") and not (d.get("data") or {}).get("video"):
            msg = d["errors"][0].get("message", "error")
            if cursor:
                cursor = None
                offset = int(out[-1]["t"]) + 1 if out else offset + 1
                continue
            raise ChatError(f"Twitch chat: {msg}")
        video = (d.get("data") or {}).get("video") or {}
        com = video.get("comments") or {}
        edges = com.get("edges") or []
        if not edges:
            break
        last_t = None
        for e in edges:
            n = (e or {}).get("node") or {}
            cid = n.get("id")
            t = float(n.get("contentOffsetSeconds") or 0)
            last_t = t
            if cid in seen or t < start:
                continue
            if end is not None and t > end:
                continue
            seen.add(cid)
            msg = n.get("message") or {}
            parts = []
            for fr in msg.get("fragments") or []:
                em = fr.get("emote")
                if em and em.get("emoteID"):
                    parts.append({"e": f"https://static-cdn.jtvnw.net/emoticons/v2/{em['emoteID']}/default/dark/2.0",
                                  "n": fr.get("text")})
                elif fr.get("text"):
                    parts.append({"t": fr["text"]})
            user = ((n.get("commenter") or {}).get("displayName")) or "?"
            out.append({"t": t, "user": user, "color": msg.get("userColor") or _name_color(user),
                        "parts": parts, "badges": [f"{b.get('setID')}/{b.get('version')}" for b in msg.get("userBadges") or []],
                        "kind": "msg"})
        pages += 1
        if progress and end:
            progress(min(1.0, max(0.0, ((last_t or start) - start) / max(1.0, end - start))))
        info = com.get("pageInfo") or {}
        if (end is not None and last_t is not None and last_t > end) or not info.get("hasNextPage"):
            break
        cursor = edges[-1].get("cursor")
        if not cursor:
            offset = int(last_t or offset) + 1
    out.sort(key=lambda m: m["t"])
    return out


def twitch_badges(login):
    """'setID/version' -> Bild-URL (globale + Kanal-Abzeichen)."""
    out = {}
    try:
        q = ('query($l:String!){badges{setID version imageURL(size:DOUBLE)} '
             'user(login:$l){broadcastBadges{setID version imageURL(size:DOUBLE)}}}')
        data = _post({"query": q, "variables": {"l": login}})
        d = data.get("data") or {}
        for b in (d.get("badges") or []) + (((d.get("user") or {}).get("broadcastBadges")) or []):
            if b and b.get("imageURL"):
                out[f"{b['setID']}/{b['version']}"] = b["imageURL"]
    except Exception:
        pass
    return out


def third_party_emotes(twitch_user_id):
    """7TV, BetterTTV, FrankerFaceZ: Code -> Bild-URL (global + Kanal)."""
    em = {}
    jobs = [
        ("https://7tv.io/v3/emote-sets/global", "7tv_set"),
        ("https://api.betterttv.net/3/cached/emotes/global", "bttv_list"),
        ("https://api.frankerfacez.com/v1/set/global", "ffz"),
    ]
    if twitch_user_id:
        jobs += [(f"https://7tv.io/v3/users/twitch/{twitch_user_id}", "7tv_user"),
                 (f"https://api.betterttv.net/3/cached/users/twitch/{twitch_user_id}", "bttv_user"),
                 (f"https://api.frankerfacez.com/v1/room/id/{twitch_user_id}", "ffz")]
    for url, kind in jobs:
        try:
            d = _get_json(url)
        except Exception:
            continue
        try:
            if kind in ("7tv_set", "7tv_user"):
                s = d if kind == "7tv_set" else (d.get("emote_set") or {})
                for e in s.get("emotes") or []:
                    host = ((e.get("data") or {}).get("host") or {}).get("url")
                    if host and e.get("name"):
                        em[e["name"]] = "https:" + host + "/2x.webp" if host.startswith("//") else host + "/2x.webp"
            elif kind == "bttv_list":
                for e in d or []:
                    em[e["code"]] = f"https://cdn.betterttv.net/emote/{e['id']}/2x"
            elif kind == "bttv_user":
                for e in (d.get("channelEmotes") or []) + (d.get("sharedEmotes") or []):
                    em[e["code"]] = f"https://cdn.betterttv.net/emote/{e['id']}/2x"
            elif kind == "ffz":
                for s in (d.get("sets") or {}).values():
                    for e in s.get("emoticons") or []:
                        u = (e.get("urls") or {}).get("2") or (e.get("urls") or {}).get("1")
                        if u and e.get("name"):
                            em[e["name"]] = u
        except Exception:
            continue
    return em


def apply_emotes(messages, emotes):
    """Woerter, die Drittanbieter-Emotes sind, in Bilder umwandeln."""
    if not emotes:
        return messages
    for m in messages:
        new = []
        for p in m["parts"]:
            if "t" not in p:
                new.append(p)
                continue
            buf = []
            for tok in re.split(r"(\s+)", p["t"]):
                if tok in emotes:
                    if buf:
                        new.append({"t": "".join(buf)})
                        buf = []
                    new.append({"e": emotes[tok], "n": tok})
                else:
                    buf.append(tok)
            if buf:
                new.append({"t": "".join(buf)})
        m["parts"] = new
    return messages


# ================================================================ YouTube
def youtube_chat(url, start=0.0, end=None, workdir=None, cancel=None):
    """Livechat-Wiederholung ueber yt-dlp (laedt den ganzen Chat, filtert dann den Abschnitt)."""
    base = tools.ytdlp_cmd()
    if not base:
        raise ChatError("yt-dlp missing")
    workdir = workdir or tempfile.mkdtemp(prefix="snipload_chat_")
    out = os.path.join(workdir, "chat")
    cmd = base + tools.cookie_args() + ["--skip-download", "--write-subs", "--sub-langs", "live_chat",
                                        "--no-playlist", "-o", out, "--no-warnings", url]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
                         env=clean_env(), stdin=subprocess.DEVNULL)
    for _l in iter(p.stdout.readline, b""):
        if cancel and cancel():
            p.kill()
            raise ChatError("cancelled")
    p.wait()
    files = [os.path.join(workdir, f) for f in os.listdir(workdir) if f.endswith(".live_chat.json")]
    if not files:
        raise ChatError("This video has no chat replay.")
    return parse_youtube_chat(files[0], start, end)


def parse_youtube_chat(path, start=0.0, end=None):
    msgs = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            r = d.get("replayChatItemAction") or {}
            try:
                t = int(r.get("videoOffsetTimeMsec") or 0) / 1000.0
            except ValueError:
                continue
            if t < start or (end is not None and t > end):
                continue
            for a in r.get("actions") or []:
                item = ((a.get("addChatItemAction") or {}).get("item")) or {}
                rend = item.get("liveChatTextMessageRenderer") or item.get("liveChatPaidMessageRenderer")
                if not rend:
                    continue
                parts = []
                for run in ((rend.get("message") or {}).get("runs")) or []:
                    if "text" in run:
                        parts.append({"t": run["text"]})
                    elif "emoji" in run:
                        th = ((run["emoji"].get("image") or {}).get("thumbnails")) or []
                        if th:
                            parts.append({"e": th[-1].get("url"), "n": (run["emoji"].get("shortcuts") or [""])[0]})
                user = ((rend.get("authorName") or {}).get("simpleText")) or "?"
                badges = []
                for b in rend.get("authorBadges") or []:
                    br = b.get("liveChatAuthorBadgeRenderer") or {}
                    th = ((br.get("customThumbnail") or {}).get("thumbnails")) or []
                    if th:
                        badges.append(th[-1].get("url"))
                    elif (br.get("icon") or {}).get("iconType") in ("MODERATOR", "OWNER", "VERIFIED"):
                        badges.append("yt:" + br["icon"]["iconType"].lower())
                kind = "super" if "liveChatPaidMessageRenderer" in item else "msg"
                m = {"t": t, "user": user, "color": _name_color(user), "parts": parts, "badges": badges, "kind": kind}
                if kind == "super":
                    m["amount"] = ((rend.get("purchaseAmountText") or {}).get("simpleText"))
                msgs.append(m)
    msgs.sort(key=lambda m: m["t"])
    return msgs


# ================================================================ Hype-Momente
def density(messages, duration, bucket=10.0):
    """Nachrichten je Zeitfenster -> Liste (fuer die Zeitleiste) und die staerksten Momente."""
    n = max(1, int((duration or (messages[-1]["t"] if messages else 0)) // bucket) + 1)
    counts = [0] * n
    for m in messages:
        i = int(m["t"] // bucket)
        if 0 <= i < n:
            counts[i] += 1
    mx = max(counts) or 1
    vals = [round(c / mx, 3) for c in counts]
    # Spitzen: lokale Maxima ueber dem Durchschnitt, mindestens 60 s auseinander
    avg = sum(counts) / len(counts) if counts else 0
    cand = sorted(range(n), key=lambda i: -counts[i])
    peaks = []
    for i in cand:
        if counts[i] <= max(3, avg * 1.8):
            break
        if all(abs(i - p) * bucket >= 60 for p in peaks):
            peaks.append(i)
        if len(peaks) >= 12:
            break
    return {"bucket": bucket, "values": vals,
            "peaks": [{"t": max(0.0, i * bucket - 20), "score": round(counts[i] / mx, 2), "count": counts[i]}
                      for i in sorted(peaks)]}


# ================================================================ Rendern
_img_cache = {}
_img_lock = threading.Lock()


def _cache_dir():
    d = os.path.join(config_dir(), "cache", "emotes")
    os.makedirs(d, exist_ok=True)
    return d


def _image(url, height):
    """Emote/Abzeichen laden (mit Datei-Cache) und auf Hoehe skalieren."""
    from PIL import Image
    key = (url, height)
    with _img_lock:
        if key in _img_cache:
            return _img_cache[key]
    im = None
    try:
        path = os.path.join(_cache_dir(), hashlib.md5(url.encode()).hexdigest())
        if not os.path.exists(path):
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            with open(path, "wb") as f:
                f.write(data)
        with open(path, "rb") as f:
            im = Image.open(io.BytesIO(f.read()))
            im.seek(0)
            im = im.convert("RGBA")
        w = max(1, int(round(im.width * height / im.height)))
        im = im.resize((w, height), Image.LANCZOS)
    except Exception:
        im = None
    with _img_lock:
        _img_cache[key] = im
    return im


def _font(size, bold=False):
    from PIL import ImageFont
    path = web_path("fonts", "Inter.ttf")
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_axes([14, 700 if bold else 500])
    except Exception:
        try:
            f.set_variation_by_name("Bold" if bold else "Medium")
        except Exception:
            pass
    return f


class Renderer:
    """Zeichnet den Chat-Stand zu einem Zeitpunkt als RGBA-Bild."""

    def __init__(self, style, badge_urls=None):
        self.st = dict(DEFAULT_STYLE, **(style or {}))
        self.W, self.H = int(self.st["width"]), int(self.st["height"])
        self.fs = int(self.st["font_size"])
        self.f_name = _font(self.fs, True)
        self.f_text = _font(self.fs, False)
        self.badge_urls = badge_urls or {}
        self._layout_cache = {}

    def _layout(self, m):
        """Nachricht -> Liste von Zeilen mit (art, inhalt, x, breite); Hoehe."""
        key = id(m)
        if key in self._layout_cache:
            return self._layout_cache[key]
        st, fs = self.st, self.fs
        pad = int(fs * 0.45)
        maxw = self.W - 2 * pad - (pad if st["msg_bg"] else 0)
        eh = int(fs * 1.45)
        items = []   # (art, inhalt, breite)
        if st["badges"]:
            for b in m.get("badges") or []:
                url = self.badge_urls.get(b) or (b if str(b).startswith("http") else None)
                if url:
                    im = _image(url, int(fs * 1.05))
                    if im:
                        items.append(("img", im, im.width + int(fs * 0.25)))
        name = m["user"] + (":" if m.get("kind") != "super" else "")
        items.append(("name", name, self.f_name.getlength(name) + fs * 0.35))
        for p in m["parts"]:
            if "e" in p and st["emotes"]:
                im = _image(p["e"], eh)
                if im:
                    items.append(("img", im, im.width + int(fs * 0.15)))
                    continue
                txt = p.get("n") or ""
            else:
                txt = p.get("t") or p.get("n") or ""
            for tok in re.split(r"(\s+)", txt):
                if tok:
                    items.append(("text", tok, self.f_text.getlength(tok)))
        lines, cur, x = [], [], 0.0
        for art, val, w in items:
            if art == "text" and val.isspace():
                if cur:
                    cur.append((art, " ", x, w))
                    x += w
                continue
            if x + w > maxw and cur:
                while cur and cur[-1][0] == "text" and cur[-1][1].isspace():
                    cur.pop()
                lines.append(cur)
                cur, x = [], 0.0
            if art == "text" and w > maxw:        # sehr langes Wort: hart umbrechen
                chunk = ""
                for ch in val:
                    if self.f_text.getlength(chunk + ch) > maxw - x and chunk:
                        cur.append((art, chunk, x, self.f_text.getlength(chunk)))
                        lines.append(cur)
                        cur, x, chunk = [], 0.0, ""
                    chunk += ch
                val, w = chunk, self.f_text.getlength(chunk)
            cur.append((art, val, x, w))
            x += w
        if cur:
            lines.append(cur)
        lh = int(fs * 1.5)
        h = len(lines) * lh + 2 * int(pad * 0.7)
        res = (lines, h, lh, pad)
        self._layout_cache[key] = res
        return res

    def frame(self, visible, slide=0.0, alphas=None):
        """visible: Nachrichten (aelteste zuerst). slide: 0..1 Einschub der neuesten Nachricht."""
        from PIL import Image, ImageDraw
        st = self.st
        img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        if st["bg"] == "solid":
            a = int(255 * float(st["bg_opacity"]))
            ImageDraw.Draw(img).rounded_rectangle([0, 0, self.W - 1, self.H - 1], radius=int(self.fs * 0.6),
                                                  fill=(10, 10, 16, a))
        d = ImageDraw.Draw(img)
        gap = int(self.fs * 0.35)
        y = self.H - gap
        layouts = [self._layout(m) for m in visible]
        if layouts and slide < 1.0:
            y += int(layouts[-1][1] * (1 - slide))    # neueste schiebt sich von unten herein
        for idx in range(len(visible) - 1, -1, -1):
            m = visible[idx]
            lines, h, lh, pad = layouts[idx]
            y -= h
            if y + h < 0:
                break
            alpha = (alphas or {}).get(idx, 1.0)
            layer = Image.new("RGBA", (self.W, h + 2), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            if st["msg_bg"]:
                fill = (14, 14, 22, int(255 * float(st["bg_opacity"])))
                if m.get("kind") == "super":
                    fill = (124, 92, 255, 200)
                ld.rounded_rectangle([0, 0, self.W - 1, h], radius=int(self.fs * 0.55), fill=fill)
            ty = int(pad * 0.7)
            for line in lines:
                for art, val, x, w in line:
                    xx = int(pad + x)
                    if art == "img":
                        layer.alpha_composite(val, (xx, ty + (lh - val.height) // 2))
                    else:
                        font = self.f_name if art == "name" else self.f_text
                        col = m["color"] if (art == "name" and st["name_colors"]) else st["text_color"]
                        if st["shadow"] and not st["msg_bg"]:
                            ld.text((xx + 1, ty + int(lh * 0.16) + 1), val, font=font, fill=(0, 0, 0, 200))
                        ld.text((xx, ty + int(lh * 0.16)), val, font=font, fill=col)
                ty += lh
            if alpha < 1.0:
                a = layer.getchannel("A").point(lambda v: int(v * alpha))
                layer.putalpha(a)
            img.alpha_composite(layer, (0, max(-h, y)))
            y -= gap
        return img


def render(messages, out_path, duration, style=None, fmt="mov", badge_urls=None, start=0.0, fps=30,
           progress=None, cancel=None, ffmpeg=None):
    """Chat als Video. Zeitachse ab 'start' (Sekunden im VOD). fmt: mov (ProRes 4444 mit Alpha),
    webm (VP9 mit Alpha), green (MP4 vor Gruen), png (MOV/PNG, verlustfrei mit Alpha - fuer das Einbrennen)."""
    ffmpeg = ffmpeg or tools.find_tool("ffmpeg")
    r = Renderer(style, badge_urls)
    msgs = [dict(m, rt=m["t"] - start) for m in messages if start <= m["t"] <= start + duration]
    max_age = float(r.st.get("max_age") or 0)
    # Ereignis-Zeitpunkte: neue Nachricht (plus kurze Einschub-Animation) und Ablauf alter Nachrichten
    slide_steps = [0.35, 0.7, 1.0]
    step_dt = 1.0 / fps
    events = [0.0]
    for m in msgs:
        for k in range(len(slide_steps)):
            events.append(m["rt"] + k * step_dt * 2)
        if max_age:
            events.append(m["rt"] + max_age)
    events = sorted({round(min(duration, max(0.0, e)), 3) for e in events if e <= duration})
    if not events or events[-1] < duration:
        events.append(round(duration, 3))
    tmp = tempfile.mkdtemp(prefix="snipload_chatframes_")
    listing = []
    last_png = None
    for i, t in enumerate(events[:-1]):
        if cancel and cancel():
            raise ChatError("cancelled")
        vis = [m for m in msgs if m["rt"] <= t and (not max_age or t - m["rt"] < max_age)][-40:]
        slide = 1.0
        if vis:
            age = t - vis[-1]["rt"]
            if age < len(slide_steps) * step_dt * 2:
                slide = slide_steps[min(len(slide_steps) - 1, int(age / (step_dt * 2)))]
        img = r.frame(vis, slide)
        if fmt == "green":
            from PIL import Image
            bg = Image.new("RGBA", img.size, (0, 255, 0, 255))
            bg.alpha_composite(img)
            img = bg
        p = os.path.join(tmp, f"{i:06d}.png")
        img.save(p, compress_level=1)
        last_png = p
        listing.append(f"file '{p.replace(os.sep, '/')}'\nduration {max(step_dt, events[i + 1] - t):.4f}")
        if progress and i % 10 == 0:
            progress(0.8 * i / max(1, len(events)))
    if last_png:
        listing.append(f"file '{last_png.replace(os.sep, '/')}'")
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("ffconcat version 1.0\n" + "\n".join(listing) + "\n")
    enc = {
        "mov": ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16",
                "-vendor", "apl0"],
        "webm": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "2M", "-auto-alt-ref", "0"],
        "green": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"],
        "png": ["-c:v", "png", "-pix_fmt", "rgba"],
    }[fmt]
    cmd = [ffmpeg, "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-vf",
           f"fps={fps},format={'yuva444p10le' if fmt == 'mov' else ('yuva420p' if fmt == 'webm' else ('rgba' if fmt == 'png' else 'yuv420p'))}",
           "-t", f"{duration:.3f}", *enc, out_path]
    res = subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW, env=clean_env(), stdin=subprocess.DEVNULL)
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    if res.returncode != 0 or not os.path.exists(out_path):
        raise ChatError("chat render failed: " + (res.stderr or b"").decode("utf-8", "replace")[-300:])
    if progress:
        progress(1.0)
    return out_path
