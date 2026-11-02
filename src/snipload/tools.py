"""yt-dlp und ffmpeg finden, Video-Infos holen, Werkzeuge installieren/aktualisieren."""
import glob
import io
import json
import os
import shutil
import threading
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime

from .util import IS_WIN, NO_WINDOW, clean_env
from .i18n import _

FROZEN = getattr(sys, "frozen", False)
WINGET_IDS = {"yt-dlp": "yt-dlp.yt-dlp", "ffmpeg": "Gyan.FFmpeg"}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}


def _winget_dirs():
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return None, None
    return (os.path.join(local, "Microsoft", "WinGet", "Links"),
            os.path.join(local, "Microsoft", "WinGet", "Packages"))


def own_dir():
    """Snipload-eigene Werkzeuge (yt-dlp, ffmpeg) - ohne winget, ohne Adminrechte."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"),
                                                                                         ".local", "share")
    d = os.path.join(base, "Snipload", "tools")
    os.makedirs(d, exist_ok=True)
    return d


def own_tool(name):
    p = os.path.join(own_dir(), name + (".exe" if IS_WIN else ""))
    return p if os.path.isfile(p) else None


def find_tool(name):
    """Zuerst Sniploads eigene Kopie (immer aktuell), dann PATH, dann die winget-Ordner."""
    exe = own_tool(name)
    if exe:
        return exe
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
                          creationflags=NO_WINDOW, env=clean_env())


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
        return "ok"


def winget_available():
    return IS_WIN and shutil.which("winget") is not None


# ---------------------------------------------------------------- eigene Kopien laden (ohne winget)
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
YTDLP_SUMS = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS"
FFMPEG_ZIPS = [
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
]


def _fetch(url, dest, progress=None, timeout=60):
    """Laedt eine Datei nach dest (erst .part, dann umbenennen). progress(frac) optional."""
    import urllib.request
    req = urllib.request.Request(url, headers=UA)
    part = dest + ".part"
    with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 18)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    os.replace(part, dest)
    return dest


def _is_exe(path):
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"MZ" and os.path.getsize(path) > 100_000
    except OSError:
        return False


def download_ytdlp(progress=None):
    """Aktuelle yt-dlp.exe direkt von GitHub in den eigenen Ordner. True bei Erfolg."""
    import hashlib
    import urllib.request
    dest = os.path.join(own_dir(), "yt-dlp.exe")
    tmp = dest + ".new"
    try:
        _fetch(YTDLP_URL, tmp, progress, 60)
        if not _is_exe(tmp):
            raise OSError("keine exe")
        want = {}
        try:  # Pruefsumme, wenn erreichbar
            sums = urllib.request.urlopen(urllib.request.Request(YTDLP_SUMS, headers=UA), timeout=20).read()
            want = {ln.split()[1]: ln.split()[0] for ln in sums.decode().splitlines() if len(ln.split()) == 2}
        except Exception:
            pass
        if want.get("yt-dlp.exe"):
            with open(tmp, "rb") as fh:
                h = hashlib.sha256(fh.read()).hexdigest()
            if want["yt-dlp.exe"].lower() != h:
                raise OSError("Pruefsumme falsch")
        os.replace(tmp, dest)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def download_ffmpeg(progress=None):
    """ffmpeg.exe + ffprobe.exe aus einem fertigen Windows-Paket in den eigenen Ordner."""
    import tempfile
    import zipfile
    for url in FFMPEG_ZIPS:
        tmpzip = os.path.join(tempfile.gettempdir(), "snipload_ffmpeg.zip")
        try:
            _fetch(url, tmpzip, (lambda f: progress(f * 0.95)) if progress else None, 60)
            got = 0
            with zipfile.ZipFile(tmpzip) as z:
                for member in z.namelist():
                    base = member.replace("\\", "/").rsplit("/", 1)[-1].lower()
                    if base in ("ffmpeg.exe", "ffprobe.exe") and "/bin/" in "/" + member.replace("\\", "/"):
                        out = os.path.join(own_dir(), base)
                        with z.open(member) as src, open(out + ".new", "wb") as dst:
                            shutil.copyfileobj(src, dst, 1 << 20)
                        if not _is_exe(out + ".new"):
                            raise OSError("keine exe")
                        os.replace(out + ".new", out)
                        got += 1
            if got >= 2:
                if progress:
                    progress(1.0)
                return True
        except Exception:
            pass
        finally:
            try:
                os.remove(tmpzip)
            except OSError:
                pass
    return False


def install(names, progress=None):
    """Laedt fehlende Werkzeuge direkt herunter (klappt auch ohne winget und ohne Adminrechte).
    Nur wenn das scheitert, wird winget versucht. Gibt die Liste der fehlgeschlagenen zurueck."""
    failed = []
    for i, n in enumerate(names):
        def prog(f, i=i, n=n):
            if progress:
                progress(n, (i + f) / len(names))
        ok = download_ytdlp(prog) if n == "yt-dlp" else download_ffmpeg(prog)
        if not ok and winget_available():
            try:
                run(["winget", "install", "-e", "--id", WINGET_IDS[n], "--accept-source-agreements",
                     "--accept-package-agreements", "--disable-interactivity"], 900)
            except Exception:
                pass
        if not find_tool(n):
            failed.append(n)
    return failed


def update_ytdlp():
    """Holt die neueste yt-dlp.exe direkt von GitHub (eigene Kopie, wird ab dann benutzt).
    Gibt (vorher, nachher) zurueck."""
    before = ytdlp_version()
    ok = IS_WIN and download_ytdlp()
    if not ok:
        base = ytdlp_cmd()
        try:
            if base and winget_available() and "winget" in base[0].lower():
                run(["winget", "upgrade", "-e", "--id", WINGET_IDS["yt-dlp"], "--accept-source-agreements",
                     "--accept-package-agreements", "--disable-interactivity"], 600)
            elif base:
                run(base + ["-U"], 600)
        except Exception:
            pass
    return before, ytdlp_version()


# ---------------------------------------------------------------- schnelles Kodieren
# Beim sekundengenauen Schnitt kodiert ffmpeg den Abschnitt neu. Ohne Vorgaben nimmt es libx264 "medium"
# auf dem Prozessor - bei 1440p/4K oft nur 0,1x Echtzeit. Darum: Grafikkarte (NVIDIA/Intel/AMD), sonst
# libx264 "veryfast" (etwa 3x so schnell, kaum sichtbarer Unterschied).
_HW = [
    ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p"]),
    ("h264_qsv", ["-c:v", "h264_qsv", "-preset", "faster", "-global_quality", "20", "-pix_fmt", "nv12"]),
    ("h264_amf", ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "19", "-qp_p", "21",
                  "-pix_fmt", "yuv420p"]),
]
CPU_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
_enc_cache = {}
_enc_lock = threading.Lock()
hw_broken = False


def video_encoder(allow_hw=True):
    """(Name, ffmpeg-Argumente) des schnellsten funktionierenden H.264-Encoders. Wird einmal getestet."""
    if not allow_hw or hw_broken:
        return "libx264", list(CPU_ARGS)
    with _enc_lock:
        if "best" not in _enc_cache:
            best = ("libx264", list(CPU_ARGS))
            ff = find_tool("ffmpeg")
            if ff and IS_WIN:
                for name, args in _HW:
                    try:
                        r = run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                 "color=c=black:s=1280x720:r=30", "-t", "0.5", *args, "-f", "null", "-"], 20)
                        if r.returncode == 0:
                            best = (name, list(args))
                            break
                    except Exception:
                        pass
            _enc_cache["best"] = best
        name, args = _enc_cache["best"]
        return name, list(args)


def is_forbidden(text):
    """YouTube hat den Download verweigert (HTTP 403). ffmpeg meldet das als Code 3436169992 / -858797304."""
    low = (text or "").lower()
    return ("403" in low and ("forbidden" in low or "http" in low)) or "3436169992" in low or "-858797304" in low


# ================================================================ Video-Infos
class InfoError(Exception):
    pass


def fetch_info(url):
    """Holt alle Infos (inkl. Storyboard) per yt-dlp -J."""
    base = ytdlp_cmd()
    if not base:
        raise InfoError(_("yt-dlp is missing"))
    cmd = base + ["-J", "--no-playlist", "--no-warnings", "--encoding", "utf-8", url]
    try:
        r = run(cmd, 120)
    except subprocess.TimeoutExpired:
        raise InfoError(_("YouTube isn't responding. Check your internet connection."))
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
        raise InfoError(friendly_error(err[-1] if err else _("No video info found.")))
    if info.get("_type") == "playlist":
        raise InfoError(_("This is a playlist. Please paste the link of a single video."))
    return info


def friendly_error(msg):
    m = msg.split("ERROR:", 1)[-1].strip()
    low = m.lower()
    if "private video" in low or "is private" in low:
        return _("This video is private.")
    if "unavailable" in low or "not available" in low:
        return _("This video isn't available (deleted, blocked or not available in your country).")
    if "sign in to confirm your age" in low or "age" in low and "sign in" in low:
        return _("This video is age-restricted and needs a sign-in.")
    if "sign in to confirm" in low or "not a bot" in low:
        return _("YouTube is currently blocking the request. Update yt-dlp in the settings and try again.")
    if is_forbidden(low):
        return _("YouTube refused the download (HTTP 403). Snipload already updated yt-dlp and tried again – "
                 "wait a few minutes and try once more.")
    if "unsupported url" in low:
        return _("Snipload can't open this link.")
    if "unable to download" in low or "getaddrinfo" in low or "network" in low or "timed out" in low:
        return _("No connection. Check your internet connection.")
    if "live event" in low or "is live" in low or "premieres in" in low:
        return _("Livestreams and premieres can only be downloaded after they've ended.")
    return m[:220]


def info_summary(info):
    """Nur die Felder, die Snipload braucht (fuer Verlauf und Warteschlange)."""
    keys = ("id", "title", "channel", "uploader", "duration", "webpage_url", "extractor_key",
            "view_count", "upload_date", "thumbnail", "width", "height")
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


def pick_preview_storyboard(info, strip_fmt):
    """Hoechstaufloesendes Storyboard fuer die grosse Vorschau (nur, wenn schaerfer als der Filmstreifen)."""
    sbs = [f for f in info.get("formats") or []
           if str(f.get("format_id", "")).startswith("sb") and f.get("fragments")
           and f.get("rows") and f.get("columns") and f.get("width") and f.get("fps")]
    if not sbs:
        return None
    best = max(sbs, key=lambda f: f.get("width") or 0)
    if strip_fmt is not None and (best.get("width") or 0) <= (strip_fmt.get("width") or 0):
        return None
    return best


def pick_frame_format(info, max_h=1080):
    """Video-Format fuer Standbilder: direkte https-Datei, am liebsten H.264.

    max_h=1080: fuer die Vorschau (720p ideal). max_h=None: hoechste Aufloesung (Facecam 1:1)."""
    cands = []
    for f in info.get("formats") or []:
        if f.get("vcodec") in (None, "none") or not f.get("url"):
            continue
        proto = f.get("protocol") or ""
        if proto not in ("https", "http", "m3u8", "m3u8_native"):  # m3u8: Twitch-VODs
            continue
        h = f.get("height") or 0
        if not h or (max_h and h > max_h):
            continue
        codec = (f.get("vcodec") or "").lower()
        score = (0 if proto.startswith("m3u8") else 1,           # direkte Datei bevorzugt (schneller)
                 h if (max_h is None or h <= 720) else 720 - (h - 720),  # Vorschau: 720p ideal
                 1 if codec.startswith(("avc", "h264")) else 0,  # schnell zu dekodieren
                 1 if f.get("ext") == "mp4" else 0)
        cands.append((score, f))
    if not cands:
        return None
    f = max(cands, key=lambda x: x[0])[1]
    return {"url": f["url"], "headers": f.get("http_headers") or {}, "height": f.get("height"),
            "width": f.get("width")}


def probe_size(path):
    """Breite/Hoehe eines Videos (ffprobe, sonst ffmpeg -i)."""
    import re as _re
    probe = find_tool("ffprobe")
    try:
        if probe:
            r = run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                     "-of", "csv=p=0:s=x", path], 30)
            m = _re.search(r"(\d+)x(\d+)", r.stdout.decode("utf-8", "replace"))
            if m:
                return int(m.group(1)), int(m.group(2))
        ff = find_tool("ffmpeg")
        if ff:
            r = run([ff, "-hide_banner", "-i", path], 30)
            m = _re.search(r"Video:.*?, (\d{2,5})x(\d{2,5})", r.stderr.decode("utf-8", "replace"))
            if m:
                return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None


def grab_frame(fmt, t, width=960, timeout=25):
    """width=None: Originalgroesse."""
    """Holt per ffmpeg ein echtes Standbild aus dem Video an Stelle t (Sekunden). PIL-Bild oder None."""
    from PIL import Image
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg or not fmt:
        return None
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", f"{max(0.0, t):.3f}"]
    headers = "".join(f"{k}: {v}\r\n" for k, v in (fmt.get("headers") or {}).items())
    if headers:
        cmd += ["-headers", headers]
    cmd += ["-i", fmt["url"], "-frames:v", "1", "-an"]
    if width:
        cmd += ["-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "pipe:1"]
    else:  # verlustfrei in Originalgroesse (fuer die pixelgenaue Facecam-Messung)
        cmd += ["-f", "image2pipe", "-vcodec", "png", "-compression_level", "1", "pipe:1"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           creationflags=NO_WINDOW, env=clean_env())
    except Exception:
        return None
    if r.returncode != 0 or not r.stdout:
        return None
    try:
        img = Image.open(io.BytesIO(r.stdout))
        img.load()
        return img.convert("RGB")
    except Exception:
        return None


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

    def __init__(self, fmt, duration, on_update=None, lazy=False):
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
        self.lazy = lazy
        if lazy:  # Blaetter nur auf Anfrage laden (das zuletzt angefragte zuerst)
            self._wanted = []
            self._event = threading.Event()
            threading.Thread(target=self._load_lazy, daemon=True).start()
        else:
            threading.Thread(target=self._load_all, daemon=True).start()

    def has(self, t):
        return self.sheets.get(self.frame_index(t) // self.per_sheet) is not None

    def request(self, t):
        """Lazy-Modus: Blatt fuer Zeitpunkt t (und die Nachbarn) zum Laden vormerken."""
        if not self.lazy:
            return
        i = self.frame_index(t) // self.per_sheet
        for j in (i + 1, i - 1, i):  # i zuletzt = hoechste Prioritaet
            if 0 <= j < len(self.urls) and j not in self.sheets and j in self._wanted:
                self._wanted.remove(j)
            if 0 <= j < len(self.urls) and j not in self.sheets:
                self._wanted.append(j)
        del self._wanted[:-12]
        self._event.set()

    def _load_lazy(self):
        from PIL import Image
        while not self.cancelled:
            if not self._wanted:
                self._event.wait(0.5)
                self._event.clear()
                continue
            i = self._wanted.pop()
            if i in self.sheets:
                continue
            try:
                img = Image.open(io.BytesIO(download_bytes(self.urls[i], 12)))
                img.load()
                self.sheets[i] = img.convert("RGB")
            except Exception:
                self.sheets[i] = None
            self.loaded += 1

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
