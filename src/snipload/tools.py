"""yt-dlp und ffmpeg finden, Video-Infos holen, Werkzeuge installieren/aktualisieren."""
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime

from .util import IS_WIN, NO_WINDOW

FROZEN = getattr(sys, "frozen", False)
WINGET_IDS = {"yt-dlp": "yt-dlp.yt-dlp", "ffmpeg": "Gyan.FFmpeg"}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}


def _winget_dirs():
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return None, None
    return (os.path.join(local, "Microsoft", "WinGet", "Links"),
            os.path.join(local, "Microsoft", "WinGet", "Packages"))


def find_tool(name):
    """Erst im PATH, dann in den winget-Ordnern (eine laufende exe kennt den neuen PATH evtl. noch nicht)."""
    exe = shutil.which(name)
    if exe:
        return exe
    links, packages = _winget_dirs()
    if links:
        cand = os.path.join(links, name + ".exe")
        if os.path.exists(cand):
            return cand
    if packages and os.path.isdir(packages):
        hits = glob.glob(os.path.join(packages, "*", "**", name + ".exe"), recursive=True)
        if hits:
            return sorted(hits)[-1]
    return None


def ytdlp_cmd():
    exe = find_tool("yt-dlp")
    if exe:
        return [exe]
    if not FROZEN:
        import importlib.util
        if importlib.util.find_spec("yt_dlp"):
            return [sys.executable, "-m", "yt_dlp"]
    return None


def run(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                          creationflags=NO_WINDOW)


def ytdlp_version():
    base = ytdlp_cmd()
    if not base:
        return None
    try:
        return run(base + ["--version"], 30).stdout.decode("utf-8", "replace").strip() or None
    except Exception:
        return None


def version_age_days(version):
    """yt-dlp-Versionen sind Datumsangaben (2026.10.26) -> Alter in Tagen."""
    try:
        d = datetime.strptime(".".join(version.split(".")[:3]), "%Y.%m.%d")
        return (datetime.now() - d).days
    except Exception:
        return None


def ffmpeg_version():
    exe = find_tool("ffmpeg")
    if not exe:
        return None
    try:
        first = run([exe, "-version"], 20).stdout.decode("utf-8", "replace").splitlines()[0]
        return first.split(" ")[2] if first.startswith("ffmpeg version") else first
    except Exception:
        return "gefunden"


def winget_available():
    return IS_WIN and shutil.which("winget") is not None


def install(names):
    """Installiert fehlende Werkzeuge per winget. Gibt die Liste der fehlgeschlagenen zurueck."""
    failed = []
    for n in names:
        try:
            r = run(["winget", "install", "-e", "--id", WINGET_IDS[n], "--accept-source-agreements",
                     "--accept-package-agreements", "--disable-interactivity"], 900)
            if not find_tool(n) and r.returncode != 0:
                failed.append(n)
        except Exception:
            failed.append(n)
    return failed


def update_ytdlp():
    """Aktualisiert yt-dlp. Gibt (vorher, nachher) zurueck."""
    base = ytdlp_cmd()
    before = ytdlp_version()
    if not base:
        return before, None
    try:
        if winget_available() and "winget" in base[0].lower():
            run(["winget", "upgrade", "-e", "--id", WINGET_IDS["yt-dlp"], "--accept-source-agreements",
                 "--accept-package-agreements", "--disable-interactivity"], 600)
        else:
            run(base + ["-U"], 600)
    except Exception:
        pass
    return before, ytdlp_version()


# ================================================================ Video-Infos
class InfoError(Exception):
    pass


def fetch_info(url):
    """Holt alle Infos (inkl. Storyboard) per yt-dlp -J."""
    base = ytdlp_cmd()
    if not base:
        raise InfoError("yt-dlp fehlt")
    cmd = base + ["-J", "--no-playlist", "--no-warnings", "--encoding", "utf-8", url]
    try:
        r = run(cmd, 120)
    except subprocess.TimeoutExpired:
        raise InfoError("YouTube antwortet nicht. Prüf deine Internetverbindung.")
    out = r.stdout.decode("utf-8", "replace").strip()
    info = None
    if out:
        try:
            info = json.loads(out.splitlines()[-1] if not out.startswith("{") else out)
        except ValueError:
            for line in reversed(out.splitlines()):
                if line.startswith("{"):
                    try:
                        info = json.loads(line)
                        break
                    except ValueError:
                        pass
    if not info:
        err = [l for l in r.stderr.decode("utf-8", "replace").splitlines() if "ERROR" in l]
        raise InfoError(friendly_error(err[-1] if err else "Keine Video-Infos gefunden."))
    if info.get("_type") == "playlist":
        raise InfoError("Das ist eine Playlist. Bitte den Link eines einzelnen Videos einfügen.")
    return info


def friendly_error(msg):
    m = msg.split("ERROR:", 1)[-1].strip()
    low = m.lower()
    if "private video" in low or "is private" in low:
        return "Dieses Video ist privat."
    if "unavailable" in low or "not available" in low:
        return "Dieses Video ist nicht verfügbar (gelöscht, gesperrt oder in deinem Land blockiert)."
    if "sign in to confirm your age" in low or "age" in low and "sign in" in low:
        return "Dieses Video ist altersbeschränkt und braucht eine Anmeldung."
    if "sign in to confirm" in low or "not a bot" in low:
        return "YouTube blockt gerade die Anfrage. Aktualisiere yt-dlp in den Einstellungen und versuch es nochmal."
    if "unsupported url" in low:
        return "Diesen Link kann Snipload nicht öffnen."
    if "unable to download" in low or "getaddrinfo" in low or "network" in low or "timed out" in low:
        return "Keine Verbindung. Prüf deine Internetverbindung."
    if "live event" in low or "is live" in low or "premieres in" in low:
        return "Livestreams und Premieren können erst nach dem Ende geladen werden."
    return m[:220]


def info_summary(info):
    """Nur die Felder, die Snipload braucht (fuer Verlauf und Warteschlange)."""
    keys = ("id", "title", "channel", "uploader", "duration", "webpage_url", "extractor_key",
            "view_count", "upload_date", "thumbnail")
    return {k: info.get(k) for k in keys}


def pick_storyboard(info):
    """Waehlt ein Storyboard-Format (YouTube): kleine Vorschaubilder ueber die ganze Laenge."""
    sbs = [f for f in info.get("formats") or []
           if str(f.get("format_id", "")).startswith("sb") and f.get("fragments")
           and f.get("rows") and f.get("columns") and f.get("width") and f.get("fps")]
    if not sbs:
        return None
    # moeglichst ~160 px breit: scharf genug fuer die Vorschau, wenige Bilder zu laden
    sbs.sort(key=lambda f: (abs((f.get("width") or 0) - 160), -(f.get("width") or 0)))
    return sbs[0]


def thumbnail_urls(info):
    vid = info.get("id")
    urls = []
    if info.get("extractor_key") == "Youtube" and vid:
        urls += [f"https://i.ytimg.com/vi/{vid}/{n}.jpg" for n in ("maxresdefault", "sddefault", "hqdefault",
                                                                  "mqdefault")]
    thumbs = sorted((t for t in info.get("thumbnails") or [] if t.get("url")),
                    key=lambda t: -(t.get("preference") or 0))
    urls += [t["url"] for t in thumbs[:3]]
    if info.get("thumbnail"):
        urls.append(info["thumbnail"])
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def download_bytes(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def load_thumbnail(info, save_to=None):
    """Erstes funktionierendes Vorschaubild als PIL-Bild (YouTube-Platzhalter 120x90 werden uebersprungen)."""
    from PIL import Image
    for u in thumbnail_urls(info):
        try:
            data = download_bytes(u)
            img = Image.open(io.BytesIO(data))
            img.load()
            if img.size[0] <= 120:  # "kein Bild"-Platzhalter von YouTube
                continue
            if save_to:
                try:
                    img.convert("RGB").save(save_to, "JPEG", quality=88)
                except Exception:
                    pass
            return img
        except Exception:
            continue
    return None


class Storyboard:
    """Laedt die Storyboard-Kacheln im Hintergrund und schneidet Einzelbilder heraus."""

    def __init__(self, fmt, duration, on_update=None):
        self.fmt = fmt
        self.duration = float(duration or 0)
        self.cols = int(fmt["columns"])
        self.rows = int(fmt["rows"])
        self.w = int(fmt["width"])
        self.h = int(fmt["height"])
        self.fps = float(fmt["fps"])
        self.urls = [fr["url"] for fr in fmt["fragments"]]
        self.sheets = {}
        self.cache = {}
        self.on_update = on_update
        self.cancelled = False
        self.loaded = 0
        threading.Thread(target=self._load_all, daemon=True).start()

    @property
    def per_sheet(self):
        return self.cols * self.rows

    def _load_all(self):
        from PIL import Image
        n = len(self.urls)
        # erst grob verteilt laden (Filmstreifen sofort ueberall), dann den Rest
        order = []
        step = max(1, n // 8)
        for i in range(0, n, step):
            order.append(i)
        order += [i for i in range(n) if i not in order]
        for i in order:
            if self.cancelled:
                return
            try:
                img = Image.open(io.BytesIO(download_bytes(self.urls[i], 12)))
                img.load()
                self.sheets[i] = img.convert("RGB")
            except Exception:
                self.sheets[i] = None
            self.loaded += 1
            if self.on_update:
                self.on_update(self)

    def frame_index(self, t):
        total = max(1, int(self.duration * self.fps))
        return max(0, min(total - 1, int(t * self.fps)))

    def frame(self, t, nearest=True):
        """PIL-Bild fuer Zeitpunkt t oder None, falls die Kachel noch fehlt."""
        idx = self.frame_index(t)
        if idx in self.cache:
            return self.cache[idx]
        sheet_i, k = divmod(idx, self.per_sheet)
        sheet = self.sheets.get(sheet_i)
        if sheet is None:
            if nearest:  # naechstes geladenes Blatt nehmen
                for d in range(1, 4):
                    for j in (sheet_i - d, sheet_i + d):
                        if self.sheets.get(j) is not None:
                            k2 = 0 if j > sheet_i else self.per_sheet - 1
                            return self._crop(self.sheets[j], k2)
            return None
        img = self._crop(sheet, k)
        if img is not None:
            self.cache[idx] = img
        return img

    def _crop(self, sheet, k):
        r, c = divmod(k, self.cols)
        box = (c * self.w, r * self.h, (c + 1) * self.w, (r + 1) * self.h)
        if box[2] > sheet.size[0] or box[3] > sheet.size[1]:
            return None
        return sheet.crop(box)
