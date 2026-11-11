"""Kleine Helfer: Zeiten, Links, Dateien, Einstellungen, Windows-Funktionen."""
import json
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime

from . import APP
from .i18n import _, lang as i18n_lang

IS_WIN = os.name == "nt"
NO_WINDOW = subprocess.CREATE_NO_WINDOW if IS_WIN else 0


def clean_env(extra=None):
    """Umgebung fuer gestartete Programme ohne die internen Variablen der Snipload-exe.

    PyInstaller gibt _PYI_*-Variablen (und TCL/TK-Pfade in den Temp-Ordner) an Kindprozesse weiter.
    Ist das Kind selbst eine PyInstaller-exe (yt-dlp.exe, die neue Snipload.exe nach einem Update),
    haelt es sich sonst fuer einen Teil von Snipload und bricht mit "Security validation failure" ab.
    """
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("_PYI") or k.startswith("_MEI") or k in ("TCL_LIBRARY", "TK_LIBRARY"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if extra:
        env.update(extra)
    return env


# ================================================================ Pfade
def resource_path(*parts):
    """Mitgelieferte Dateien - im Quellcode-Ordner oder in der fertigen exe."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, *parts)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "..", "assets", *parts)


def web_path(*parts):
    """Dateien der Oberflaeche (web/) - im Quellcode-Paket oder in der fertigen exe."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "web", *parts)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", *parts)


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
    "auto_update": True,
    "language": None,         # None = Englisch (Standard); sonst Code aus i18n.LANGUAGES
    "fc_split": 0.40,
    "fc_bottom": False,
    "also_full": False,
    "name_template": "{title} [{start} - {end}]",
    "history": [],
    "geometry": None,
    # ab Version 4 (neue Oberflaeche)
    "favorites": [],
    "recent": [],
    "cookies_browser": None,
    "custom_editors": [],
    "premiere_mode": "bin",      # bin | timeline | sequence
    "open_in": None,             # Schnittprogramm, in das nach dem Export geschickt wird
    "window": None,
    "fc_sizes": None,
    "caption_style": None,
    "caption_model": "balanced",
    "caption_lang": "auto",
    "chat_style": None,
    "upscale_engine": "lanczos",
    "hw_encode": True,
    "platform": "youtube",
    "onboarded": False,
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
    if data.get("name_template") == "{titel} [{start} bis {ende}]":   # alter deutscher Standard
        data["name_template"] = DEFAULTS["name_template"]
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
        return _("{sec} s").format(sec=sec)
    m, s = divmod(sec, 60)
    if m < 60:
        return _("{m} min {s:02d} s").format(m=m, s=s) if s else _("{m} min").format(m=m)
    h, m = divmod(m, 60)
    return _("{h} h {m:02d} min").format(h=h, m=m)


def fmt_size(n):
    if not n:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


# Kurzschreibweise grosser Zahlen je Sprache: (Tausend, Million, Milliarde), Dezimalzeichen, Tausendertrenner
_COUNT = {
    "en": (("K", "M", "B"), ".", ","), "de": ((" Tsd.", " Mio.", " Mrd."), ",", "."),
    "es": ((" mil", " M", " mil M"), ",", "."), "fr": ((" k", " M", " Md"), ",", "\u202f"),
    "pt": ((" mil", " mi", " bi"), ",", "."), "tr": ((" B", " Mn", " Mr"), ",", "."),
    "ru": ((" тыс.", " млн", " млрд"), ",", "\u00a0"),
}


def fmt_count(n):
    if not n:
        return ""
    lang = i18n_lang()
    if lang in ("ja", "zh", "ko"):   # Zehntausender-System: 万 / 億 (ko: 만 / 억)
        man, oku = ("만", "억") if lang == "ko" else (("万", "億") if lang == "ja" else ("万", "亿"))
        if n >= 100_000_000:
            return f"{n / 1e8:.1f}".rstrip("0").rstrip(".") + oku
        if n >= 10_000:
            return f"{n / 1e4:.1f}".rstrip("0").rstrip(".") + man
        return f"{n:,}"
    (k, m, b), dec, sep = _COUNT.get(lang, _COUNT["en"])
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f}".replace(".", dec) + b
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}".replace(".", dec) + m
    if n >= 10_000:
        return f"{n / 1e3:.0f}" + k
    return f"{n:,}".replace(",", sep)


_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def fmt_upload_date(s):
    try:
        d = datetime.strptime(s, "%Y%m%d")
    except Exception:
        return ""
    return fmt_date(d)


def fmt_datetime(ts):
    """Zeitpunkt (Unix-Zeit) als Datum + Uhrzeit in der Schreibweise der eingestellten Sprache."""
    try:
        d = datetime.fromtimestamp(float(ts))
    except Exception:
        return ""
    if i18n_lang() == "en":
        h = d.hour % 12 or 12
        return f"{fmt_date(d)}, {h}:{d.minute:02d} {'PM' if d.hour >= 12 else 'AM'}"
    return f"{fmt_date(d)} {d.hour:02d}:{d.minute:02d}"


def fmt_date(d):
    lang = i18n_lang()
    if lang == "en":
        return f"{_MONTHS_EN[d.month - 1]} {d.day}, {d.year}"
    if lang in ("ja", "zh"):
        return f"{d.year}/{d.month}/{d.day}"
    if lang == "ko":
        return f"{d.year}. {d.month}. {d.day}."
    if lang in ("de", "tr", "ru"):
        return d.strftime("%d.%m.%Y")
    return d.strftime("%d/%m/%Y")


# ================================================================ Links
def looks_like_url(text):
    return bool(re.match(r"^https?://\S+$", (text or "").strip()))


def is_video_link(text):
    """Links, die Snipload aus der Zwischenablage uebernimmt: YouTube, Twitch-VODs/Clips, Kick."""
    return bool(re.search(r"^https?://([a-z0-9-]+\.)?(youtube\.com|youtu\.be|twitch\.tv|kick\.com)/",
                          (text or "").strip(), re.I))


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
    e_txt = fmt_short(end).replace(":", "-") if end is not None else _("end")
    date = datetime.now().strftime("%Y-%m-%d")
    vid = (info or {}).get("id") or ""
    # englische Platzhalter + die alten deutschen (fuer gespeicherte Vorlagen)
    values = {"title": title, "channel": channel, "start": s_txt, "end": e_txt, "date": date, "id": vid,
              "titel": title, "kanal": channel, "ende": e_txt, "datum": date}
    tpl = template or DEFAULTS["name_template"]
    if whole:  # ganzes Video: Zeitangaben samt Klammern weglassen
        tpl = re.sub(r"\s*[\[(]\s*\{start\}.*?\{(?:end|ende)\}\s*[\])]", "", tpl)
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
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"', env=clean_env())
        else:
            open_path(os.path.dirname(path) if path and os.path.isfile(path) else (path or "."))
    except Exception:
        pass


# ================================================================ Windows-Extras
def win_no_throttle(handle=None):
    """Windows-Energiesparmodus ("Effizienzmodus"/EcoQoS) fuer einen Prozess abschalten.

    Windows 11 bremst Prozesse, deren Fenster im Hintergrund liegen - ein Download/Schnitt wuerde dann
    stark verlangsamt, sobald man aus Snipload heraustabbt. handle=None: der eigene Prozess."""
    if not IS_WIN:
        return
    try:
        import ctypes
        from ctypes import wintypes

        class _State(ctypes.Structure):
            _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]
        k = ctypes.windll.kernel32
        k.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        h = wintypes.HANDLE(int(handle)) if handle else k.GetCurrentProcess()
        for mask in (0x1, 0x4):   # EXECUTION_SPEED, IGNORE_TIMER_RESOLUTION
            st = _State(1, mask, 0)   # StateMask 0 = nie drosseln
            k.SetProcessInformation(h, 4, ctypes.byref(st), ctypes.sizeof(st))   # 4 = ProcessPowerThrottling
    except Exception:
        pass


def win_unthrottle_tree(pid):
    """win_no_throttle fuer alle Nachkommen eines Prozesses (yt-dlp startet ffmpeg selbst - auch das
    soll im Hintergrund nicht gebremst werden)."""
    if not IS_WIN or not pid:
        return
    try:
        import ctypes
        from ctypes import wintypes

        class _PE(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_wchar * 260)]
        k = ctypes.windll.kernel32
        k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k.OpenProcess.restype = wintypes.HANDLE
        snap = k.CreateToolhelp32Snapshot(0x2, 0)   # TH32CS_SNAPPROCESS
        if not snap or snap == wintypes.HANDLE(-1).value:
            return
        children = {}
        e = _PE()
        e.dwSize = ctypes.sizeof(_PE)
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            children.setdefault(e.th32ParentProcessID, []).append(e.th32ProcessID)
            ok = k.Process32NextW(snap, ctypes.byref(e))
        k.CloseHandle(snap)
        todo, seen = list(children.get(pid, [])), set()
        while todo:
            p = todo.pop()
            if p in seen:
                continue
            seen.add(p)
            todo += children.get(p, [])
            h = k.OpenProcess(0x0200 | 0x1000, False, p)   # SET_INFORMATION | QUERY_LIMITED_INFORMATION
            if h:
                win_no_throttle(h)
                k.CloseHandle(h)
    except Exception:
        pass


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
