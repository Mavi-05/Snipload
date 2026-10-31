"""Kleine Helfer: Zeiten, Links, Dateien, Einstellungen, Windows-Funktionen."""
import json
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime

from . import APP

IS_WIN = os.name == "nt"
NO_WINDOW = subprocess.CREATE_NO_WINDOW if IS_WIN else 0


# ================================================================ Pfade
def resource_path(*parts):
    """Mitgelieferte Dateien - im Quellcode-Ordner oder in der fertigen exe."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, *parts)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "..", "assets", *parts)


def config_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, APP)
    os.makedirs(d, exist_ok=True)
    return d


def thumbs_dir():
    d = os.path.join(config_dir(), "thumbs")
    os.makedirs(d, exist_ok=True)
    return d


def default_folder():
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")


# ================================================================ Einstellungen
DEFAULTS = {
    "folder": None,
    "kind": "video",          # video | audio
    "quality": "best",        # best | 2160 | 1440 | 1080 | 720 | 480
    "audio_fmt": "mp3",       # mp3 | m4a | wav
    "aspect": "original",     # original | crop916 | blur916
    "exact": True,
    "sound": True,
    "open_after": False,
    "watch_clipboard": True,
    "name_template": "{titel} [{start} bis {ende}]",
    "history": [],
    "geometry": None,
}


def load_settings():
    data = {}
    candidates = [os.path.join(config_dir(), "settings.json")]
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    candidates.append(os.path.join(base, "ClipDownloader", "settings.json"))  # Version 2 hiess so
    for p in candidates:
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            break
        except Exception:
            continue
    # alte Schluessel aus Version 2 uebersetzen
    if data.get("kind") in ("Video (MP4)", "Audio (MP3)"):
        data["kind"] = "audio" if "Audio" in data["kind"] else "video"
    q = data.get("quality")
    if isinstance(q, str) and q.endswith("p") and q[:-1].isdigit():
        data["quality"] = q[:-1]
    elif q not in (None, "best", "2160", "1440", "1080", "720", "480"):
        data["quality"] = "best"
    out = dict(DEFAULTS)
    out.update({k: v for k, v in data.items() if k in DEFAULTS or k.startswith("_")})
    if not out.get("folder"):
        out["folder"] = default_folder()
    if not isinstance(out.get("history"), list):
        out["history"] = []
    return out


def save_settings(data):
    try:
        p = os.path.join(config_dir(), "settings.json")
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except Exception:
        pass


# ================================================================ Zeiten
def parse_time(text):
    """'00:03:00', '3:00', '180' oder '2:05.5' -> Sekunden (float)."""
    text = (text or "").strip().replace(",", ".")
    if not text:
        raise ValueError("leer")
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError("zu viele Teile")
    total = 0.0
    for p in parts:
        if p.strip() == "":
            raise ValueError("leer")
        total = total * 60 + float(p)
    if total < 0:
        raise ValueError("negativ")
    return total


def fmt_ytdlp(sec):
    """Fuer yt-dlp: HH:MM:SS(.mmm)"""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec - h * 3600 - m * 60
    if abs(s - round(s)) < 0.0005:
        return f"{h:02d}:{m:02d}:{int(round(s)):02d}"
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def fmt_short(sec):
    """Anzeige: 3:05 oder 1:02:03"""
    sec = int(round(max(0, sec or 0)))
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_field(sec):
    """Zeitfelder: HH:MM:SS, Zehntel nur wenn noetig."""
    sec = max(0.0, float(sec))
    tenths = int(round(sec * 10))
    whole, frac = divmod(tenths, 10)
    base = f"{whole // 3600:02d}:{(whole % 3600) // 60:02d}:{whole % 60:02d}"
    return base + (f".{frac}" if frac else "")


def fmt_duration_words(sec):
    sec = int(round(sec or 0))
    if sec < 60:
        return f"{sec} s"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m} min {s:02d} s" if s else f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m:02d} min"


def fmt_size(n):
    if not n:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def fmt_count(n):
    if not n:
        return ""
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f}".replace(".", ",") + " Mrd."
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}".replace(".", ",") + " Mio."
    if n >= 10_000:
        return f"{n / 1e3:.0f} Tsd."
    return f"{n:,}".replace(",", ".")


def fmt_upload_date(s):
    try:
        return datetime.strptime(s, "%Y%m%d").strftime("%d.%m.%Y")
    except Exception:
        return ""


# ================================================================ Links
def looks_like_url(text):
    return bool(re.match(r"^https?://\S+$", (text or "").strip()))


def is_youtube(text):
    return bool(re.search(r"^https?://([a-z0-9-]+\.)?(youtube\.com|youtu\.be)/", (text or "").strip(), re.I))


def start_from_url(url):
    """Liest ?t=90 / &t=1m30s / #t=90 / &start=90 aus einem Link."""
    try:
        p = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qs(p.query)
        t = (q.get("t") or q.get("start") or [None])[0]
        if not t and p.fragment.startswith("t="):
            t = p.fragment[2:]
        if not t:
            return None
        t = t.rstrip("s") if t.endswith("s") and t[:-1].isdigit() else t
        if t.isdigit():
            return float(t)
        m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", t)
        if m and any(m.groups()):
            h, mi, s = (int(x or 0) for x in m.groups())
            return float(h * 3600 + mi * 60 + s)
    except Exception:
        pass
    return None


# ================================================================ Dateinamen
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name, limit=150):
    name = _BAD.sub("", name)
    # Emojis & Co. raus: viele Programme (Schnitt, Upload, aeltere Tools) kommen damit nicht klar
    name = "".join(ch for ch in name if ord(ch) < 0x2190 or 0x2E80 <= ord(ch) < 0xD800 or 0xF900 <= ord(ch) < 0xFE00)
    name = name.replace("‍", "")
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if not name:
        name = "Clip"
    if name.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                                     *(f"LPT{i}" for i in range(1, 10))}:
        name = "_" + name
    return name[:limit].rstrip(". ")


def build_name(template, info, start, end, whole):
    title = (info or {}).get("title") or "Clip"
    channel = (info or {}).get("channel") or (info or {}).get("uploader") or ""
    s_txt = fmt_short(start).replace(":", "-")
    e_txt = fmt_short(end).replace(":", "-") if end is not None else "Ende"
    values = {"titel": title, "kanal": channel, "start": s_txt, "ende": e_txt,
              "datum": datetime.now().strftime("%Y-%m-%d"), "id": (info or {}).get("id") or ""}
    tpl = template or DEFAULTS["name_template"]
    if whole:  # ganzes Video: Zeitangaben samt Klammern weglassen
        tpl = re.sub(r"\s*[\[(]\s*\{start\}.*?\{ende\}\s*[\])]", "", tpl)
    try:
        out = tpl.format(**values)
    except (KeyError, IndexError, ValueError):
        out = DEFAULTS["name_template"].format(**values)
    return safe_filename(out)


def unique_path(folder, name, ext):
    p = os.path.join(folder, f"{name}.{ext}")
    i = 2
    while os.path.exists(p):
        p = os.path.join(folder, f"{name} ({i}).{ext}")
        i += 1
    return p


# ================================================================ Dateien oeffnen
def open_path(path):
    try:
        if IS_WIN:
            os.startfile(path)  # noqa
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def show_in_folder(path):
    try:
        if IS_WIN and path and os.path.exists(path):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        else:
            open_path(os.path.dirname(path) if path and os.path.isfile(path) else (path or "."))
    except Exception:
        pass


# ================================================================ Windows-Extras
def win_dark_titlebar(window, caption_hex=None):
    """Dunkle Titelleiste (Windows 10/11) und passende Leistenfarbe (Windows 11)."""
    if not IS_WIN:
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        val = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (neu/alt)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4) == 0:
                break
        if caption_hex:
            r, g, b = (int(caption_hex[i:i + 2], 16) for i in (1, 3, 5))
            color = ctypes.c_int(r | (g << 8) | (b << 16))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), 4)  # Leistenfarbe
            text = ctypes.c_int(0xF6F4F4)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text), 4)  # Textfarbe
    except Exception:
        pass


def win_flash(window):
    """Laesst das Taskleisten-Symbol aufblinken, wenn das Fenster nicht vorne ist."""
    if not IS_WIN:
        return
    try:
        import ctypes
        from ctypes import wintypes

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                        ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x3 | 0xC, 0, 0)  # alles, bis Fokus
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


def win_sound_done():
    if not IS_WIN:
        return
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_OK)
    except Exception:
        pass
