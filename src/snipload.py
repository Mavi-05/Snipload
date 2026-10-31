"""
Snipload
Laedt nur einen bestimmten Abschnitt eines YouTube-Videos herunter.
Werkzeuge im Hintergrund: yt-dlp + ffmpeg (werden bei Bedarf per winget installiert).
"""
import collections
import glob
import io
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw

APP = "Snipload"
VERSION = "2.1"

# ---------------------------------------------------------------- Farben
BG = "#0e0e11"
CARD = "#17171c"
BORDER = "#26262f"
FIELD = "#202027"
FIELD_HOVER = "#2a2a33"
TEXT = "#f3f3f6"
MUTED = "#8c8c99"
DIM = "#5d5d68"
ACCENT = "#ff0033"
ACCENT_HOVER = "#ff3358"
ACCENT_DIM = "#4a0f1c"
TRACK = "#2c2c35"
GOOD = "#2ecc71"

FAMILY = "Segoe UI" if os.name == "nt" else "DejaVu Sans"

FROZEN = getattr(sys, "frozen", False)
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

QUALITIES = {"Beste Qualität": None, "1080p": 1080, "720p": 720, "480p": 480}
KINDS = ["Video (MP4)", "Audio (MP3)"]
WINGET_IDS = {"yt-dlp": "yt-dlp.yt-dlp", "ffmpeg": "Gyan.FFmpeg"}

PCT_RE = re.compile(r"\[PCT\]\s*([\d.]+)%")
TIME_RE = re.compile(r"time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
SPEED_RE = re.compile(r"speed=\s*([\d.]+)x")
FMT_RE = re.compile(r"Downloading \d+ format\(s\):\s*(\S+)")


# ================================================================ Helfer
def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def parse_time(text):
    """'00:03:00', '3:00', '180' oder '2:05.5' -> Sekunden."""
    text = text.strip().replace(",", ".")
    if not text:
        raise ValueError("leer")
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError("zu viele Teile")
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    if total < 0:
        raise ValueError("negativ")
    return total


def fmt_time(sec):
    """Fuer yt-dlp: HH:MM:SS(.mmm)"""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec - h * 3600 - m * 60
    if abs(s - round(s)) < 0.0005:
        return f"{h:02d}:{m:02d}:{int(round(s)):02d}"
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def fmt_short(sec):
    """Fuer Anzeige: 3:05 oder 1:02:03"""
    sec = int(round(sec or 0))
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_field(sec):
    """Fuer die Zeitfelder: immer HH:MM:SS"""
    sec = max(0, int(round(sec)))
    return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"


def start_from_url(url):
    """Liest ?t=90 / &t=1m30s / #t=90 aus einem YouTube-Link."""
    try:
        p = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qs(p.query)
        t = (q.get("t") or q.get("start") or [None])[0]
        if not t and p.fragment.startswith("t="):
            t = p.fragment[2:]
        if not t:
            return None
        if t.isdigit():
            return float(t)
        m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", t)
        if m and any(m.groups()):
            h, mi, s = (int(x or 0) for x in m.groups())
            return float(h * 3600 + mi * 60 + s)
    except Exception:
        pass
    return None


def looks_like_url(text):
    return bool(re.match(r"^https?://\S+$", (text or "").strip()))


def is_youtube(text):
    return bool(re.search(r"(youtube\.com|youtu\.be)/", text or ""))


def _winget_dirs():
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return None, None
    return (os.path.join(local, "Microsoft", "WinGet", "Links"),
            os.path.join(local, "Microsoft", "WinGet", "Packages"))


def find_tool(name):
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


def find_ytdlp():
    exe = find_tool("yt-dlp")
    if exe:
        return [exe]
    if not FROZEN:
        import importlib.util
        if importlib.util.find_spec("yt_dlp"):
            return [sys.executable, "-m", "yt_dlp"]
    return None


def default_folder():
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def _config_base():
    return os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")


def settings_path():
    return os.path.join(_config_base(), "Snipload", "settings.json")


def load_settings():
    # aeltere Versionen hiessen "Clip Downloader" - deren Einstellungen und Verlauf uebernehmen
    for p in (settings_path(), os.path.join(_config_base(), "ClipDownloader", "settings.json")):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return {}


def save_settings(data):
    try:
        p = settings_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except Exception:
        pass


def open_file(path):
    if os.name == "nt":
        os.startfile(path)  # noqa
    else:
        subprocess.Popen(["xdg-open", path])


def show_in_folder(path):
    if os.name == "nt":
        if os.path.exists(path):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        else:
            os.startfile(os.path.dirname(path) or ".")  # noqa
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) or "."])


def rounded(img, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1], radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def fit_16_9(img, w, h):
    iw, ih = img.size
    target = w / h
    if iw / ih > target:
        nw = int(ih * target)
        img = img.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh = int(iw / target)
        img = img.crop((0, (ih - nh) // 2, iw, (ih - nh) // 2 + nh))
    return img.resize((w, h), Image.LANCZOS)


# ================================================================ Zeitleiste
class RangeSlider(tk.Canvas):
    """Zeitleiste mit zwei Griffen (Start/Ende). Mitte ziehen verschiebt beides."""

    def __init__(self, master, scale, on_change, bg):
        self.s = scale
        super().__init__(master, height=int(58 * scale), bg=bg, highlightthickness=0, bd=0)
        self.on_change = on_change
        self.duration = 0.0
        self.a = 0.0
        self.b = 0.0
        self.drag = None
        self.drag_off = 0.0
        self.hover = None
        self.enabled = True
        self.hint = "Link einfügen – dann hier Start und Ende ziehen"
        self.pad = int(16 * scale)
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda e: self._set_hover(None))

    # --- API
    def set_duration(self, d):
        self.duration = float(d or 0)
        self.redraw()

    def set_range(self, a, b):
        if self.duration > 0:
            a = max(0.0, min(a, self.duration))
            b = max(0.0, min(b, self.duration))
        self.a, self.b = a, b
        self.redraw()

    def set_enabled(self, on):
        self.enabled = on
        self.redraw()

    # --- Umrechnung
    def _x(self, t):
        w = self.winfo_width()
        return self.pad + (w - 2 * self.pad) * (t / self.duration if self.duration else 0)

    def _t(self, x):
        w = self.winfo_width()
        f = (x - self.pad) / max(1, (w - 2 * self.pad))
        return max(0.0, min(1.0, f)) * self.duration

    # --- Zeichnen
    def _font(self, px, bold=False):
        return (FAMILY, -int(px * self.s), "bold" if bold else "normal")

    def redraw(self):
        self.delete("all")
        w = self.winfo_width()
        if w < 10:
            return
        s = self.s
        y = int(31 * s)
        lw = max(4, int(6 * s))
        self.create_line(self.pad, y, w - self.pad, y, width=lw, fill=TRACK, capstyle="round")
        if self.duration <= 0:
            self.create_text(w / 2, y + int(18 * s), text=self.hint,
                             fill=DIM, font=self._font(12))
            return
        xa, xb = self._x(self.a), self._x(self.b)
        col = ACCENT if self.enabled else DIM
        self.create_line(xa, y, xb, y, width=lw, fill=col, capstyle="round")
        # Enden
        self.create_text(self.pad, y + int(19 * s), text="0:00", fill=DIM, anchor="w", font=self._font(11))
        self.create_text(w - self.pad, y + int(19 * s), text=fmt_short(self.duration), fill=DIM,
                         anchor="e", font=self._font(11))
        # Beschriftung ueber den Griffen (nicht ueberlappen lassen)
        la, lb = fmt_short(self.a), fmt_short(self.b)
        gap = int(46 * s)
        ta, tb = xa, xb
        if tb - ta < gap:
            mid = (ta + tb) / 2
            ta, tb = mid - gap / 2, mid + gap / 2
        ta = max(self.pad + gap / 2 - 8 * s, ta)
        tb = min(w - self.pad - gap / 2 + 8 * s, tb)
        self.create_text(ta, int(10 * s), text=la, fill=TEXT, font=self._font(12, True))
        self.create_text(tb, int(10 * s), text=lb, fill=TEXT, font=self._font(12, True))
        # Griffe
        for name, x in (("a", xa), ("b", xb)):
            big = self.hover == name or self.drag == name
            r = int((11 if big else 9) * s)
            self.create_oval(x - r, y - r, x + r, y + r, fill="#ffffff", outline=col, width=max(2, int(3 * s)))

    # --- Maus
    def _which(self, x):
        xa, xb = self._x(self.a), self._x(self.b)
        grab = 16 * self.s
        da, db = abs(x - xa), abs(x - xb)
        if min(da, db) <= grab:
            if abs(da - db) < 1:  # Griffe uebereinander: Richtung entscheidet spaeter
                return "a" if x < xa else "b"
            return "a" if da < db else "b"
        if xa < x < xb:
            return "mid"
        return None

    def _set_hover(self, h):
        if h != self.hover:
            self.hover = h
            self.configure(cursor="sb_h_double_arrow" if h in ("a", "b") else ("fleur" if h == "mid" else "hand2"))
            self.redraw()

    def _hover(self, e):
        if self.duration > 0 and self.enabled and not self.drag:
            self._set_hover(self._which(e.x))

    def _press(self, e):
        if self.duration <= 0 or not self.enabled:
            return
        w = self._which(e.x)
        if w is None:  # neben die Auswahl geklickt: naechsten Griff dorthin springen lassen
            t = round(self._t(e.x))
            w = "a" if abs(t - self.a) < abs(t - self.b) else "b"
            self._apply(w, t)
        elif w == "mid":
            self.drag_off = self._t(e.x) - self.a
        self.drag = w
        self.redraw()

    def _apply(self, which, t):
        min_gap = 1.0
        if which == "a":
            self.a = max(0.0, min(t, self.b - min_gap))
        elif which == "b":
            self.b = min(self.duration, max(t, self.a + min_gap))
        self.redraw()
        self.on_change(self.a, self.b)

    def _move(self, e):
        if not self.drag:
            return
        t = round(self._t(e.x))
        if self.drag == "mid":
            length = self.b - self.a
            na = round(max(0.0, min(self._t(e.x) - self.drag_off, self.duration - length)))
            self.a, self.b = na, na + length
            self.redraw()
            self.on_change(self.a, self.b)
        else:
            self._apply(self.drag, t)

    def _release(self, e):
        self.drag = None
        self._hover(e)
        self.redraw()


# ================================================================ App
class App(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=BG)
        self.title(f"{APP} {VERSION}")
        self.geometry("820x640")
        self.minsize(720, 600)
        self.after(250, self._set_icon)

        self.cfg = load_settings()
        self.q = queue.Queue()
        self.proc = None
        self.running = False
        self.busy_reason = None
        self.cancelled = False
        self.tail = collections.deque(maxlen=15)
        self.info = None
        self.info_gen = 0
        self.last_url = ""
        self.url_changed_at = 0.0
        self.last_clip_auto = ""
        self.thumb_img = None
        self.result_file = None
        self.syncing = False
        self.shown = 0.0
        self.job = {}
        self.clip_len = None

        self.start_v = tk.StringVar(value="00:00:00")
        self.end_v = tk.StringVar(value="00:01:00")
        self.folder_v = tk.StringVar(value=self.cfg.get("folder") or default_folder())
        self.kind_v = tk.StringVar(value=self.cfg.get("kind") if self.cfg.get("kind") in KINDS else KINDS[0])
        q = self.cfg.get("quality")
        self.quality_v = tk.StringVar(value=q if q in QUALITIES else "Beste Qualität")
        self.exact_v = tk.BooleanVar(value=self.cfg.get("exact", True))
        self.status_v = tk.StringVar(value="Bereit. Kopier einfach einen YouTube-Link – er wird automatisch eingefügt.")
        self.pct_v = tk.StringVar(value="")
        self.len_v = tk.StringVar(value="Länge 1:00")

        self.scale = ctk.ScalingTracker.get_window_scaling(self)
        self._build()
        self._kind_changed()
        self.bind("<FocusIn>", self._on_focus)
        self.bind("<Return>", lambda e: self.start() if not self.running else None)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(400, self._check_clipboard)
        self._poll()

    # ------------------------------------------------------------ Aufbau
    def F(self, size, weight="normal"):
        return ctk.CTkFont(family=FAMILY, size=size, weight=weight)

    def _set_icon(self):
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

    def _card(self, row, pady=(0, 10)):
        c = ctk.CTkFrame(self.body, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        c.grid(row=row, column=0, sticky="ew", pady=pady)
        return c

    def _label(self, master, text, size=12, color=MUTED, weight="normal", **kw):
        return ctk.CTkLabel(master, text=text, text_color=color, font=self.F(size, weight), **kw)

    def _button(self, master, text, cmd, primary=False, **kw):
        if primary:
            opts = dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#ffffff")
        else:
            opts = dict(fg_color=FIELD, hover_color=FIELD_HOVER, text_color=TEXT,
                        border_width=1, border_color=BORDER)
        opts.setdefault("corner_radius", 10)
        opts.setdefault("font", self.F(13, "bold" if primary else "normal"))
        opts.update(kw)
        return ctk.CTkButton(master, text=text, command=cmd, **opts)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.body = ctk.CTkFrame(self, fg_color=BG)
        self.body.grid(row=0, column=0, sticky="nsew", padx=20, pady=(14, 16))
        self.body.grid_columnconfigure(0, weight=1)

        # ---------- Kopfzeile
        head = ctk.CTkFrame(self.body, fg_color=BG)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        head.grid_columnconfigure(1, weight=1)
        try:
            logo = Image.open(resource_path("icon.png"))
            self.logo_img = ctk.CTkImage(logo, size=(34, 34))
            ctk.CTkLabel(head, image=self.logo_img, text="").grid(row=0, column=0, rowspan=2, padx=(0, 12))
        except Exception:
            pass
        self._label(head, APP, 20, TEXT, "bold").grid(row=0, column=1, sticky="sw")
        self._label(head, "Nur den Abschnitt laden, den du wirklich brauchst.", 12).grid(row=1, column=1, sticky="nw")
        self.hist_btn = self._button(head, "Verlauf", self.show_history, width=90, height=32)
        self.hist_btn.grid(row=0, column=2, rowspan=2, padx=(8, 0))
        self.upd_btn = self._button(head, "yt-dlp updaten", self.update_ytdlp, width=120, height=32)
        self.upd_btn.grid(row=0, column=3, rowspan=2, padx=(8, 0))

        # ---------- Link + Video-Infos
        c1 = self._card(1)
        c1.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(c1, fg_color=CARD)
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 10))
        top.grid_columnconfigure(0, weight=1)
        self.url_entry = ctk.CTkEntry(top, placeholder_text="YouTube-Link hier einfügen…", height=38,
                                      fg_color=FIELD, border_color=BORDER, text_color=TEXT,
                                      placeholder_text_color=DIM, font=self.F(13), corner_radius=10)
        self.url_entry.grid(row=0, column=0, sticky="ew")
        self._button(top, "Einfügen", self.paste, width=96, height=38).grid(row=0, column=1, padx=(8, 0))

        info = ctk.CTkFrame(c1, fg_color=CARD)
        info.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))
        info.grid_columnconfigure(1, weight=1)
        self.thumb_lbl = ctk.CTkLabel(info, text="", width=144, height=81, fg_color=FIELD, corner_radius=10)
        self.thumb_lbl.grid(row=0, column=0, rowspan=3, padx=(0, 14))
        self.title_lbl = self._label(info, "Noch kein Video", 14, TEXT, "bold", anchor="w", justify="left",
                                     wraplength=440)
        self.title_lbl.grid(row=0, column=1, sticky="ew")
        self.meta_lbl = self._label(info, "Füg einen Link ein – Titel, Länge und Vorschaubild erscheinen hier.",
                                    12, MUTED, anchor="w", justify="left", wraplength=440)
        self.meta_lbl.grid(row=1, column=1, sticky="ew", pady=(2, 0))
        self.yt_btn = self._button(info, "▶  Auf YouTube ab Start prüfen", self.preview_on_youtube,
                                   height=30, width=230, font=self.F(12))
        self.yt_btn.grid(row=2, column=1, sticky="w", pady=(8, 0))
        self.yt_btn.configure(state="disabled")

        # ---------- Abschnitt
        c2 = self._card(2)
        c2.grid_columnconfigure(0, weight=1)
        self.slider = RangeSlider(c2, self.scale, self._slider_changed, CARD)
        self.slider.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))
        times = ctk.CTkFrame(c2, fg_color=CARD)
        times.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
        self._label(times, "Start", 12).grid(row=0, column=0, padx=(0, 6))
        self.start_entry = ctk.CTkEntry(times, textvariable=self.start_v, width=96, height=34, justify="center",
                                        fg_color=FIELD, border_color=BORDER, text_color=TEXT,
                                        font=self.F(13), corner_radius=9)
        self.start_entry.grid(row=0, column=1)
        self._label(times, "Ende", 12).grid(row=0, column=2, padx=(16, 6))
        self.end_entry = ctk.CTkEntry(times, textvariable=self.end_v, width=96, height=34, justify="center",
                                      fg_color=FIELD, border_color=BORDER, text_color=TEXT,
                                      font=self.F(13), corner_radius=9)
        self.end_entry.grid(row=0, column=3)
        self._label(times, "", 12, MUTED, textvariable=self.len_v).grid(row=0, column=4, padx=(16, 0))
        times.grid_columnconfigure(5, weight=1)
        self.whole_btn = self._button(times, "Ganzes Video", self.whole_video, width=110, height=32,
                                      font=self.F(12))
        self.whole_btn.grid(row=0, column=6, sticky="e")
        for ent in (self.start_entry, self.end_entry):
            ent.bind("<Return>", lambda e: (self._fields_changed(), "break")[1])
            ent.bind("<FocusOut>", lambda e: self._fields_changed())
            ent.bind("<KeyRelease>", lambda e: self._fields_changed(soft=True))
            ent.bind("<MouseWheel>", self._wheel)
            ent.bind("<Button-4>", self._wheel)
            ent.bind("<Button-5>", self._wheel)

        # ---------- Optionen
        c3 = self._card(3)
        c3.grid_columnconfigure(4, weight=1)
        self.kind_seg = ctk.CTkSegmentedButton(
            c3, values=KINDS, variable=self.kind_v, command=lambda v: self._kind_changed(),
            selected_color=ACCENT, selected_hover_color=ACCENT_HOVER, unselected_color=FIELD,
            unselected_hover_color=FIELD_HOVER, fg_color=FIELD, text_color=TEXT, font=self.F(12),
            height=34, corner_radius=9)
        self.kind_seg.grid(row=0, column=0, padx=(14, 10), pady=(14, 8), sticky="w")
        self.q_menu = ctk.CTkOptionMenu(
            c3, values=list(QUALITIES), variable=self.quality_v, width=140, height=34,
            fg_color=FIELD, button_color=FIELD_HOVER, button_hover_color=BORDER, text_color=TEXT,
            dropdown_fg_color=CARD, dropdown_hover_color=FIELD_HOVER, dropdown_text_color=TEXT,
            font=self.F(12), dropdown_font=self.F(12), corner_radius=9,
            command=lambda v: self._save())
        self.q_menu.grid(row=0, column=1, padx=(0, 10), pady=(14, 8), sticky="w")
        self.exact_sw = ctk.CTkSwitch(c3, text="Sekundengenau schneiden", variable=self.exact_v,
                                      progress_color=ACCENT, button_color="#ffffff", button_hover_color="#ffffff",
                                      fg_color=TRACK, text_color=TEXT, font=self.F(12),
                                      command=self._save)
        self.exact_sw.grid(row=0, column=2, padx=(0, 14), pady=(14, 8), sticky="w")

        fold = ctk.CTkFrame(c3, fg_color=CARD)
        fold.grid(row=1, column=0, columnspan=5, sticky="ew", padx=14, pady=(0, 14))
        fold.grid_columnconfigure(1, weight=1)
        self._label(fold, "Speichern in", 12).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkEntry(fold, textvariable=self.folder_v, height=34, fg_color=FIELD, border_color=BORDER,
                     text_color=TEXT, font=self.F(12), corner_radius=9).grid(row=0, column=1, sticky="ew")
        self._button(fold, "Ändern…", self.pick_folder, width=90, height=34, font=self.F(12)).grid(
            row=0, column=2, padx=(8, 0))
        self._button(fold, "Öffnen", self.open_folder, width=80, height=34, font=self.F(12)).grid(
            row=0, column=3, padx=(8, 0))

        # ---------- Download
        act = ctk.CTkFrame(self.body, fg_color=BG)
        act.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        act.grid_columnconfigure(0, weight=1)
        self.go_btn = self._button(act, "⬇   Clip herunterladen", self.start, primary=True, height=48,
                                   font=self.F(15, "bold"), corner_radius=12)
        self.go_btn.grid(row=0, column=0, sticky="ew")
        self.cancel_btn = self._button(act, "Abbrechen", self.cancel, width=110, height=48)
        self.cancel_btn.grid(row=0, column=1, padx=(8, 0))
        self.cancel_btn.configure(state="disabled")

        self.bar = ctk.CTkProgressBar(act, height=10, corner_radius=5, progress_color=ACCENT, fg_color=TRACK)
        self.bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(14, 6))
        self.bar.set(0)
        st = ctk.CTkFrame(act, fg_color=BG)
        st.grid(row=2, column=0, columnspan=2, sticky="ew")
        st.grid_columnconfigure(0, weight=1)
        self.status_lbl = self._label(st, "", 12, MUTED, textvariable=self.status_v, anchor="w",
                                      justify="left", wraplength=500)
        self.status_lbl.grid(row=0, column=0, sticky="w")
        self.pct_lbl = self._label(st, "", 13, TEXT, "bold", textvariable=self.pct_v)
        self.pct_lbl.grid(row=0, column=2, sticky="e")

        self.done_row = ctk.CTkFrame(st, fg_color=BG)
        self.play_btn = self._button(self.done_row, "▶  Abspielen", self.play_result, width=116, height=30,
                                     font=self.F(12), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                     border_width=0, text_color="#ffffff")
        self.play_btn.grid(row=0, column=0)
        self.show_btn = self._button(self.done_row, "Im Ordner zeigen", self.show_result, width=136, height=30,
                                     font=self.F(12))
        self.show_btn.grid(row=0, column=1, padx=(8, 0))
        self._bar_reset()

        self.after(50, lambda: self.slider.redraw())

    # ------------------------------------------------------------ Einstellungen
    def _save(self, *_):
        self.cfg.update(folder=self.folder_v.get(), kind=self.kind_v.get(),
                        quality=self.quality_v.get(), exact=bool(self.exact_v.get()))
        save_settings(self.cfg)

    def _kind_changed(self):
        audio = self.kind_v.get() == KINDS[1]
        self.q_menu.configure(state="disabled" if audio else "normal")
        self._save()

    # ------------------------------------------------------------ Link & Zwischenablage
    def get_url(self):
        return self.url_entry.get().strip()

    def set_url(self, url):
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, url)

    def paste(self):
        try:
            txt = self.clipboard_get().strip()
        except tk.TclError:
            txt = ""
        if txt:
            self.set_url(txt)
        else:
            self.status_v.set("In der Zwischenablage ist kein Link.")

    def _on_focus(self, e):
        now = time.time()
        if now - getattr(self, "_last_focus_check", 0) > 0.7:
            self._last_focus_check = now
            self.after(80, self._check_clipboard)

    def _check_clipboard(self):
        if self.running:
            return
        try:
            txt = self.clipboard_get().strip()
        except tk.TclError:
            return
        if is_youtube(txt) and looks_like_url(txt) and txt != self.get_url() and txt != self.last_clip_auto:
            self.last_clip_auto = txt
            self.set_url(txt)
            self.status_v.set("Link aus der Zwischenablage übernommen.")

    def _url_tick(self):
        """Wird regelmaessig aufgerufen: erkennt neue Links und laedt die Video-Infos (mit kurzer Verzoegerung)."""
        url = self.get_url()
        now = time.time()
        if url != self.last_url:
            self.last_url = url
            self.url_changed_at = now
            self.info_gen += 1
            self._reset_info()
            if looks_like_url(url):
                self.meta_lbl.configure(text="Lade Video-Infos…")
            return
        if self.url_changed_at and now - self.url_changed_at > 0.45:
            self.url_changed_at = 0
            if looks_like_url(url):
                self._fetch_info(url)

    def _reset_info(self):
        self.info = None
        self.thumb_img = None
        self.thumb_lbl.configure(image=None, fg_color=FIELD)
        if not self.running:
            self._bar_reset()
            self.done_row.grid_forget()
        self.slider.hint = "Link einfügen – dann hier Start und Ende ziehen"
        if looks_like_url(self.get_url()):
            self.slider.hint = "Die Zeitleiste erscheint, sobald das Video geladen ist"
            if not self.running:
                self.status_v.set("Lade Video-Infos…")
        self.title_lbl.configure(text="Noch kein Video")
        self.meta_lbl.configure(text="Füg einen Link ein – Titel, Länge und Vorschaubild erscheinen hier.")
        self.yt_btn.configure(state="disabled")
        self.slider.set_duration(0)

    def _fetch_info(self, url):
        base = find_ytdlp()
        if not base:
            self.meta_lbl.configure(text="yt-dlp fehlt noch – klick auf „Clip herunterladen“, dann installiere ich es.")
            return
        gen = self.info_gen
        self.meta_lbl.configure(text="Lade Video-Infos…")
        threading.Thread(target=self._info_worker, args=(gen, url, base), daemon=True).start()

    def _info_worker(self, gen, url, base):
        cmd = base + ["--no-playlist", "--no-warnings", "--skip-download", "--encoding", "utf-8",
                      "--print", "%(.{id,title,channel,uploader,duration,thumbnail,webpage_url,extractor_key})j",
                      url]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=90, stdin=subprocess.DEVNULL,
                               creationflags=NO_WINDOW)
        except Exception as ex:
            self.q.put(("info_err", gen, str(ex)))
            return
        info = None
        for line in reversed(r.stdout.decode("utf-8", "replace").splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    info = json.loads(line)
                    break
                except ValueError:
                    pass
        if not info:
            err = [l for l in r.stderr.decode("utf-8", "replace").splitlines() if "ERROR" in l]
            msg = err[-1].split("ERROR:", 1)[-1].strip() if err else "Keine Infos gefunden."
            self.q.put(("info_err", gen, msg))
            return
        pil = None
        thumb = info.get("thumbnail")
        if info.get("extractor_key") == "Youtube" and info.get("id"):
            thumb = f"https://i.ytimg.com/vi/{info['id']}/mqdefault.jpg"
        if thumb:
            try:
                req = urllib.request.Request(thumb, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = resp.read()
                pil = Image.open(io.BytesIO(data))
                pil.load()
            except Exception:
                pil = None
        self.q.put(("info", gen, info, pil))

    def _on_info(self, gen, info, pil):
        if gen != self.info_gen:
            return
        self.info = info
        title = info.get("title") or "Unbekannter Titel"
        dur = info.get("duration") or 0
        who = info.get("channel") or info.get("uploader") or ""
        self.title_lbl.configure(text=title if len(title) <= 90 else title[:88] + "…")
        meta = " · ".join(x for x in (who, fmt_short(dur) if dur else "Länge unbekannt") if x)
        self.meta_lbl.configure(text=meta)
        self.yt_btn.configure(state="normal")
        if pil is not None:
            w, h = 144, 81
            k = 2  # doppelte Aufloesung fuer scharfe Darstellung
            img = rounded(fit_16_9(pil.convert("RGB"), w * k, h * k), 10 * k)
            self.thumb_img = ctk.CTkImage(img, size=(w, h))
            self.thumb_lbl.configure(image=self.thumb_img, fg_color=CARD)
        if dur:
            self.slider.set_duration(dur)
            t = start_from_url(self.get_url())
            try:
                s = parse_time(self.start_v.get())
                e = parse_time(self.end_v.get()) if self.end_v.get().strip() else dur
            except ValueError:
                s, e = 0, min(60, dur)
            if t is not None and t < dur:
                s, e = t, min(t + 60, dur)
            if s >= dur:
                s = 0
            e = min(max(e, s + 1), dur)
            self._set_range(s, e)
        self.status_v.set("Bereit. Zieh die Griffe auf der Zeitleiste oder tipp die Zeiten ein.")

    def _on_info_err(self, gen, msg):
        if gen != self.info_gen:
            return
        self.title_lbl.configure(text="Video nicht gefunden")
        self.slider.hint = "Prüf den Link – das Video konnte nicht geladen werden"
        self.slider.redraw()
        if not self.running:
            self.status_v.set("Mit diesem Link klappt es nicht. Ist das Video privat oder gelöscht?")
        short = msg if len(msg) < 160 else msg[:157] + "…"
        self.meta_lbl.configure(text=short)

    def preview_on_youtube(self):
        if not self.info:
            return
        try:
            s = int(parse_time(self.start_v.get()))
        except ValueError:
            s = 0
        if self.info.get("extractor_key") == "Youtube" and self.info.get("id"):
            webbrowser.open(f"https://www.youtube.com/watch?v={self.info['id']}&t={s}s")
        else:
            webbrowser.open(self.info.get("webpage_url") or self.get_url())

    # ------------------------------------------------------------ Zeiten
    def _set_range(self, s, e):
        self.syncing = True
        self.start_v.set(fmt_field(s))
        self.end_v.set(fmt_field(e) if e is not None else "")
        self.syncing = False
        self.slider.set_range(s, e if e is not None else (self.slider.duration or 0))
        self._update_len(s, e)

    def _update_len(self, s, e):
        if e is None:
            dur = self.info.get("duration") if self.info else None
            self.len_v.set(f"Länge {fmt_short(dur - s)}" if dur else "bis zum Ende")
        else:
            self.len_v.set(f"Länge {fmt_short(max(0, e - s))}")

    def _slider_changed(self, a, b):
        self.syncing = True
        self.start_v.set(fmt_field(a))
        self.end_v.set(fmt_field(b))
        self.syncing = False
        self._update_len(a, b)

    def _fields_changed(self, soft=False):
        if self.syncing:
            return
        try:
            s = parse_time(self.start_v.get())
            e = parse_time(self.end_v.get()) if self.end_v.get().strip() else None
        except ValueError:
            if not soft:
                self.len_v.set("Zeit ungültig")
            return
        dur = self.slider.duration
        if dur and not soft:
            s = min(s, max(0, dur - 1))
            if e is not None:
                e = min(e, dur)
            if e is not None and e <= s:
                e = min(s + 1, dur)
            self._set_range(s, e)
            return
        if dur:
            self.slider.set_range(min(s, dur), min(e if e is not None else dur, dur))
        if e is not None and e <= s:
            self.len_v.set("Ende vor Start")
        else:
            self._update_len(s, e)

    def _wheel(self, e):
        """Mausrad ueber einem Zeitfeld: +/- 1 Sekunde."""
        var = self.start_v if e.widget.master is self.start_entry or e.widget is self.start_entry else self.end_v
        try:
            cur = parse_time(var.get() or "0")
        except ValueError:
            return
        up = (getattr(e, "delta", 0) > 0) or getattr(e, "num", 0) == 4
        var.set(fmt_field(max(0, cur + (1 if up else -1))))
        self._fields_changed()
        return "break"

    def whole_video(self):
        dur = self.slider.duration
        self._set_range(0, dur if dur else None)

    # ------------------------------------------------------------ Ordner
    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder_v.get() or default_folder())
        if d:
            self.folder_v.set(os.path.normpath(d))
            self._save()

    def open_folder(self):
        d = self.folder_v.get()
        if os.path.isdir(d):
            open_file(d)

    # ------------------------------------------------------------ Laufzustand
    def set_running(self, running, reason=None):
        self.running = running
        self.busy_reason = reason if running else None
        self.go_btn.configure(state="disabled" if running else "normal",
                              fg_color=ACCENT_DIM if running else ACCENT)
        self.cancel_btn.configure(state="normal" if (running and reason == "download") else "disabled")
        self.upd_btn.configure(state="disabled" if running else "normal")
        self.slider.set_enabled(not running)

    def _bar_reset(self):
        self.bar.configure(progress_color=TRACK)
        self.bar.set(0)
        self.pct_v.set("")
        self.shown = 0.0

    def _progress(self, frac, status=None):
        if frac > 0:
            self.bar.configure(progress_color=ACCENT)
        frac = max(0.0, min(1.0, frac))
        if frac >= self.shown:
            self.shown = frac
            self.bar.set(frac)
            self.pct_v.set(f"{frac * 100:.0f} %")
        if status:
            self.status_v.set(status)

    # ------------------------------------------------------------ Download
    def start(self):
        if self.running:
            return
        url = self.get_url()
        if not looks_like_url(url):
            messagebox.showwarning(APP, "Bitte zuerst einen YouTube-Link einfügen.")
            return
        try:
            s = parse_time(self.start_v.get())
        except ValueError:
            messagebox.showwarning(APP, "Die Startzeit ist ungültig. Beispiel: 00:03:00")
            return
        e = None
        if self.end_v.get().strip():
            try:
                e = parse_time(self.end_v.get())
            except ValueError:
                messagebox.showwarning(APP, "Die Endzeit ist ungültig. Beispiel: 00:06:00")
                return
        vdur = (self.info or {}).get("duration") or 0
        if vdur:
            if s >= vdur:
                messagebox.showwarning(APP, f"Der Start liegt hinter dem Videoende ({fmt_short(vdur)}).")
                return
            if e is not None and e > vdur:
                e = vdur
        if e is not None and e <= s:
            messagebox.showwarning(APP, "Das Ende muss nach dem Start liegen.")
            return
        folder = self.folder_v.get().strip()
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            messagebox.showwarning(APP, "Der Zielordner ist ungültig.")
            return
        base = find_ytdlp()
        ffmpeg = find_tool("ffmpeg")
        missing = [n for n, ok in (("yt-dlp", base), ("ffmpeg", ffmpeg)) if not ok]
        if missing:
            self.offer_install(missing)
            return
        self._save()

        whole = s == 0 and (e is None or (vdur and e >= vdur - 0.5))
        if whole:
            tag = ""
        else:
            tag = f" [{fmt_short(s)} bis {fmt_short(e) if e is not None else 'Ende'}]".replace(":", "-")
        audio = self.kind_v.get() == KINDS[1]
        cmd = base + [
            "--no-playlist", "--newline", "--no-colors", "--windows-filenames", "--encoding", "utf-8",
            "--no-quiet", "--progress", "--force-overwrites",
            "--progress-template", "download:[PCT] %(progress._percent_str)s",
            "--print", "after_move:CLIPDL_FILE:%(filepath)s",
            "-P", folder, "-o", f"%(title).80s{tag}.%(ext)s",
            "--ffmpeg-location", ffmpeg,
        ]
        if not whole:
            cmd += ["--download-sections", f"*{fmt_time(s)}-{fmt_time(e) if e is not None else 'inf'}"]
            if self.exact_v.get():
                cmd.append("--force-keyframes-at-cuts")
        if audio:
            cmd += ["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "0"]
        else:
            h = QUALITIES[self.quality_v.get()]
            cmd += ["-f", f"bv*[height<={h}]+ba/b[height<={h}]/b" if h else "bv*+ba/b"]
            cmd += ["-S", "ext:mp4:m4a", "--merge-output-format", "mp4"]
        cmd.append(url)

        # Fortschritts-Zustand
        self.job = dict(s=s, e=e, audio=audio, url=url, folder=folder, started=time.time(),
                        title=(self.info or {}).get("title"))
        self.clip_len = (e - s) if e is not None else ((vdur - s) if vdur else None)
        self.passes = 1
        self.pass_idx = 0
        self.last_t = -1.0
        self.last_pct = -1.0
        self.post = False
        self.shown = 0.0
        self.result_file = None
        self.cancelled = False
        self.tail.clear()
        self.done_row.grid_forget()
        self._bar_reset()
        self.pct_v.set("0 %")
        self.status_v.set("Starte… Verbindung zu YouTube wird aufgebaut")
        self.set_running(True, "download")

        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, env=env)
        except OSError as ex:
            self.set_running(False)
            messagebox.showerror(APP, f"Konnte yt-dlp nicht starten:\n{ex}")
            return
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def _reader(self, proc):
        buf = b""
        while True:
            ch = proc.stdout.read(1)
            if not ch:
                break
            if ch in (b"\r", b"\n"):
                if buf:
                    self.q.put(("line", buf.decode("utf-8", "replace")))
                    buf = b""
            else:
                buf += ch
        if buf:
            self.q.put(("line", buf.decode("utf-8", "replace")))
        proc.wait()
        self.q.put(("done", proc.returncode))

    def _eta_text(self, frac):
        el = time.time() - self.job["started"]
        if frac < 0.04 or el < 2:
            return ""
        rest = el * (1 - frac) / frac
        return f"  ·  noch ca. {int(rest)} s" if rest < 90 else f"  ·  noch ca. {int(rest // 60) + 1} min"

    def _on_line(self, line):
        line = line.strip()
        if not line:
            return
        self.tail.append(line)
        if line.startswith("CLIPDL_FILE:"):
            self.result_file = line[len("CLIPDL_FILE:"):].strip()
            return
        m = FMT_RE.search(line)
        if m:
            self.passes = max(1, m.group(1).count("+") + 1)
            self.status_v.set("Starte Download…")
            return
        span = 0.94  # die letzten Prozent gehoeren dem Zusammenfuegen/Umwandeln
        m = PCT_RE.search(line)
        if m:
            pct = float(m.group(1))
            if pct + 30 < self.last_pct:
                self.pass_idx += 1
            self.last_pct = pct
            idx = min(self.pass_idx, self.passes - 1)
            frac = (idx + pct / 100) / self.passes * span
            what = "Ton" if (self.passes > 1 and idx == 1) or self.job["audio"] else "Video"
            self._progress(frac, f"Lade {what}…{self._eta_text(frac)}")
            return
        t = TIME_RE.search(line)
        if t and self.clip_len:
            sec = int(t.group(1)) * 3600 + int(t.group(2)) * 60 + float(t.group(3))
            if sec + 2 < self.last_t:
                self.pass_idx += 1
            self.last_t = sec
            idx = min(self.pass_idx, self.passes - 1)
            part = min(1.0, sec / self.clip_len)
            frac = (idx + part) / self.passes * span
            sp = SPEED_RE.search(line)
            speed = f"  ·  {float(sp.group(1)):.1f}× Tempo" if sp else ""
            what = "Ton" if (self.passes > 1 and idx == 1) or self.job["audio"] else "Video"
            self._progress(frac, f"Lade {what} und schneide…{speed}{self._eta_text(frac)}")
            return
        low = line.lower()
        if "[merger]" in low:
            self._progress(0.96, "Füge Bild und Ton zusammen…")
        elif "[extractaudio]" in low:
            self._progress(0.96, "Wandle in MP3 um…")
        elif "[youtube]" in low and "extracting" in low:
            self.status_v.set("Lese Video-Infos…")

    def _guess_result(self):
        """Falls der Dateiname nicht gemeldet wurde: neueste Datei im Zielordner."""
        try:
            cands = [os.path.join(self.job["folder"], f) for f in os.listdir(self.job["folder"])]
            cands = [p for p in cands if os.path.isfile(p) and os.path.getmtime(p) >= self.job["started"] - 2
                     and not p.endswith((".part", ".ytdl", ".tmp"))]
            return max(cands, key=os.path.getmtime) if cands else None
        except OSError:
            return None

    def _on_done(self, rc):
        self.set_running(False)
        if self.cancelled:
            self._bar_reset()
            self.status_v.set("Abgebrochen.")
            return
        if rc == 0:
            self.shown = 0
            self._progress(1.0)
            f = self.result_file if self.result_file and os.path.exists(self.result_file) else self._guess_result()
            self.result_file = f
            secs = time.time() - self.job["started"]
            name = os.path.basename(f) if f else "Datei"
            self.status_v.set(f"✓  Fertig in {secs:.0f} s  –  {name}")
            self.pct_v.set("")
            self.done_row.grid(row=0, column=1, sticky="e", padx=(10, 0))
            self.play_btn.configure(state="normal" if f else "disabled")
            self._add_history(f)
            if os.name == "nt":
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_OK)
                except Exception:
                    pass
        else:
            self._bar_reset()
            self.status_v.set("Fehler beim Download.")
            errs = [l for l in self.tail if "error" in l.lower()] or list(self.tail)[-5:]
            text = "\n".join(errs[-4:])
            hint = ""
            low = text.lower()
            if any(k in low for k in ("403", "sign in", "bot", "unable to extract", "nsig", "player")):
                hint = "\n\nDas liegt meist an einer alten yt-dlp-Version.\nKlick oben auf „yt-dlp updaten“ und versuch es nochmal."
            messagebox.showerror(APP, "Das hat nicht geklappt:\n\n" + text + hint)

    def cancel(self):
        if self.proc and self.running and self.busy_reason == "download":
            self.cancelled = True
            self.status_v.set("Breche ab…")
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                                   creationflags=NO_WINDOW, capture_output=True)
                else:
                    self.proc.terminate()
            except Exception:
                pass

    def play_result(self):
        if self.result_file and os.path.exists(self.result_file):
            open_file(self.result_file)

    def show_result(self):
        if self.result_file:
            show_in_folder(self.result_file)
        else:
            self.open_folder()

    # ------------------------------------------------------------ Verlauf
    def _add_history(self, path):
        j = self.job
        entry = dict(title=j.get("title") or (os.path.splitext(os.path.basename(path))[0] if path else "Clip"),
                     file=path or "", url=j["url"], start=j["s"], end=j["e"],
                     kind="MP3" if j["audio"] else "MP4", date=datetime.now().strftime("%d.%m.%Y %H:%M"))
        hist = [h for h in self.cfg.get("history", []) if h.get("file") != entry["file"]]
        self.cfg["history"] = [entry] + hist[:49]
        save_settings(self.cfg)

    def show_history(self):
        if getattr(self, "hist_win", None) and self.hist_win.winfo_exists():
            self.hist_win.focus()
            return
        win = ctk.CTkToplevel(self, fg_color=BG)
        self.hist_win = win
        win.title("Verlauf – " + APP)
        win.geometry("620x460")
        win.transient(self)
        win.after(250, lambda: self._icon_for(win))
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(win, fg_color=BG)
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        head.grid_columnconfigure(0, weight=1)
        self._label(head, "Deine letzten Clips", 17, TEXT, "bold").grid(row=0, column=0, sticky="w")
        self._button(head, "Verlauf leeren", lambda: self._clear_history(win), width=120, height=30,
                     font=self.F(12)).grid(row=0, column=1)
        lst = ctk.CTkScrollableFrame(win, fg_color=BG)
        lst.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 12))
        lst.grid_columnconfigure(0, weight=1)
        hist = self.cfg.get("history", [])
        if not hist:
            self._label(lst, "Noch keine Clips heruntergeladen.", 13).grid(row=0, column=0, pady=30)
        for i, h in enumerate(hist):
            row = ctk.CTkFrame(lst, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
            row.grid(row=i, column=0, sticky="ew", pady=4, padx=4)
            row.grid_columnconfigure(0, weight=1)
            exists = bool(h.get("file")) and os.path.exists(h["file"])
            title = h.get("title") or "Clip"
            self._label(row, title if len(title) <= 46 else title[:44].rstrip() + "…", 13, TEXT if exists else DIM,
                        "bold", anchor="w").grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
            rng = "ganzes Video" if not h.get("start") and h.get("end") is None else \
                f"{fmt_short(h.get('start') or 0)} – {fmt_short(h['end']) if h.get('end') is not None else 'Ende'}"
            sub = f"{rng}  ·  {h.get('kind', '')}  ·  {h.get('date', '')}" + ("" if exists else "  ·  Datei gelöscht")
            self._label(row, sub, 11, MUTED, anchor="w").grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))
            b1 = self._button(row, "▶", lambda p=h.get("file"): open_file(p), width=38, height=30)
            b1.grid(row=0, column=1, rowspan=2, padx=(4, 4))
            b2 = self._button(row, "Ordner", lambda p=h.get("file"): show_in_folder(p), width=70, height=30,
                              font=self.F(12))
            b2.grid(row=0, column=2, rowspan=2, padx=(0, 4))
            b3 = self._button(row, "Nochmal", lambda h=h: self._reuse(h, win), width=80, height=30,
                              font=self.F(12))
            b3.grid(row=0, column=3, rowspan=2, padx=(0, 10))
            if not exists:
                b1.configure(state="disabled")
                b2.configure(state="disabled")

    def _icon_for(self, win):
        try:
            win.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

    def _reuse(self, h, win):
        """Link und Zeiten eines alten Clips wieder eintragen."""
        win.destroy()
        self.set_url(h.get("url", ""))
        self.last_clip_auto = h.get("url", "")
        self._set_range(h.get("start") or 0, h.get("end"))
        self.status_v.set("Link und Zeiten aus dem Verlauf übernommen.")

    def _clear_history(self, win):
        if messagebox.askyesno(APP, "Verlauf wirklich leeren? (Die Dateien bleiben erhalten.)", parent=win):
            self.cfg["history"] = []
            save_settings(self.cfg)
            win.destroy()
            self.show_history()

    # ------------------------------------------------------------ yt-dlp aktualisieren / installieren
    def update_ytdlp(self):
        if self.running:
            return
        base = find_ytdlp()
        if not base:
            self.offer_install(["yt-dlp"])
            return
        self.set_running(True, "update")
        self.bar.configure(mode="indeterminate", progress_color=ACCENT)
        self.bar.start()
        self.pct_v.set("")
        self.status_v.set("Aktualisiere yt-dlp…")
        threading.Thread(target=self._update_worker, args=(base,), daemon=True).start()

    def _version(self, base):
        try:
            r = subprocess.run(base + ["--version"], capture_output=True, timeout=30, creationflags=NO_WINDOW)
            return r.stdout.decode("utf-8", "replace").strip()
        except Exception:
            return ""

    def _update_worker(self, base):
        before = self._version(base)
        winget_ok = os.name == "nt" and shutil.which("winget")
        try:
            if winget_ok and "WinGet" in base[0]:
                subprocess.run(["winget", "upgrade", "-e", "--id", "yt-dlp.yt-dlp",
                                "--accept-source-agreements", "--accept-package-agreements",
                                "--disable-interactivity"],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
            else:
                subprocess.run(base + ["-U"], capture_output=True, timeout=600, creationflags=NO_WINDOW)
        except Exception:
            pass
        after = self._version(find_ytdlp() or base)
        self.q.put(("updated", before, after))

    def _on_updated(self, before, after):
        self.bar.stop()
        self.bar.configure(mode="determinate")
        self._bar_reset()
        self.set_running(False)
        if after and before and after != before:
            self.status_v.set(f"✓  yt-dlp aktualisiert: {before} → {after}")
        elif after:
            self.status_v.set(f"✓  yt-dlp ist aktuell ({after}).")
        else:
            self.status_v.set("Update hat nicht geklappt. In PowerShell: winget upgrade yt-dlp.yt-dlp")

    def offer_install(self, missing):
        names = " und ".join(missing)
        if os.name != "nt" or not shutil.which("winget"):
            messagebox.showerror(APP, f"{names} wurde nicht gefunden.\n\nInstallieren mit:\n" +
                                 "\n".join(f"winget install {WINGET_IDS[m]}" for m in missing))
            return
        if not messagebox.askyesno(APP, f"{names} fehlt noch, das braucht der Downloader.\n\n"
                                        "Soll ich es jetzt automatisch installieren? (dauert 1–2 Minuten)"):
            return
        self.set_running(True, "install")
        self.bar.configure(mode="indeterminate", progress_color=ACCENT)
        self.bar.start()
        self.pct_v.set("")
        self.status_v.set(f"Installiere {names}… bitte warten")
        threading.Thread(target=self._install_worker, args=(missing,), daemon=True).start()

    def _install_worker(self, missing):
        failed = []
        for m in missing:
            try:
                r = subprocess.run(["winget", "install", "-e", "--id", WINGET_IDS[m],
                                    "--accept-source-agreements", "--accept-package-agreements",
                                    "--disable-interactivity"],
                                   creationflags=NO_WINDOW, capture_output=True, timeout=900)
                if not find_tool(m) and r.returncode != 0:
                    failed.append(m)
            except Exception:
                failed.append(m)
        self.q.put(("installed", failed))

    def _on_installed(self, failed):
        self.bar.stop()
        self.bar.configure(mode="determinate")
        self._bar_reset()
        self.set_running(False)
        if failed:
            self.status_v.set("Installation hat nicht geklappt.")
            messagebox.showerror(APP, "Konnte nicht installieren: " + ", ".join(failed) +
                                 "\n\nBitte in PowerShell eingeben:\n" +
                                 "\n".join(f"winget install {WINGET_IDS[m]}" for m in failed))
        else:
            self.status_v.set("✓  Installiert! Klick jetzt nochmal auf „Clip herunterladen“.")
            self.last_url = ""  # Video-Infos neu laden

    # ------------------------------------------------------------ Ereignisschleife
    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "line":
                    self._on_line(item[1])
                elif kind == "done":
                    self._on_done(item[1])
                elif kind == "info":
                    self._on_info(*item[1:])
                elif kind == "info_err":
                    self._on_info_err(*item[1:])
                elif kind == "installed":
                    self._on_installed(item[1])
                elif kind == "updated":
                    self._on_updated(item[1], item[2])
        except queue.Empty:
            pass
        try:
            self._url_tick()
        except Exception:
            pass
        self.after(80, self._poll)

    def _on_close(self):
        if self.running and self.busy_reason == "download":
            if not messagebox.askyesno(APP, "Es läuft noch ein Download. Wirklich beenden?"):
                return
            self.cancel()
        self._save()
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
