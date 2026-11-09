"""Farben, Abstaende und Schriften - das Designsystem von Snipload."""
import os
import tkinter.font as tkfont

import customtkinter as ctk

# ---------------------------------------------------------------- Farben
BG = "#0b0b0e"          # Fensterhintergrund
SIDEBAR = "#101014"     # Seitenleiste
SURFACE = "#15151a"     # Karten
SURFACE_2 = "#1c1c23"   # Felder, Knoepfe
SURFACE_3 = "#24242d"   # Hover
BORDER = "#25252e"
BORDER_STRONG = "#33333e"
TEXT = "#f4f4f6"
TEXT_2 = "#a3a3b0"
TEXT_3 = "#6c6c79"
# Akzent aus dem Logo: Violett -> Blau
ACCENT = "#7c5cff"
ACCENT_HOVER = "#8f74ff"
ACCENT_PRESSED = "#6845f0"
ACCENT_SOFT = "#1e1838"   # ausgewaehlter Menuepunkt
ACCENT_MUTED = "#2f2758"  # deaktivierter Hauptknopf
ACCENT_2 = "#4f7dff"      # zweite Verlaufsfarbe (Blau)
CAM_FRAME = "#ff2e63"     # Facecam-Rahmen im Editor (bewusst rot, gut sichtbar)
SUCCESS = "#22c55e"
SUCCESS_SOFT = "#0f2a1a"
WARN = "#f5a524"
WARN_SOFT = "#2e2210"
DANGER = "#f04452"
DANGER_SOFT = "#2e1015"

# ---------------------------------------------------------------- Masse
RADIUS = 12
RADIUS_SM = 9
PAD = 24       # Seitenrand
GAP = 14       # Abstand zwischen Karten

_families = {}


def init_fonts(root):
    """Sucht die beste verfuegbare Schrift (Windows 11: Segoe UI Variable)."""
    try:
        fams = set(tkfont.families(root))
    except Exception:
        fams = set()
    def pick(*names):
        for n in names:
            if n in fams:
                return n
        return "Segoe UI" if os.name == "nt" else "DejaVu Sans"
    from .i18n import lang
    cjk = {"ja": ("Yu Gothic UI", "Meiryo UI", "MS UI Gothic", "Noto Sans CJK JP"),
           "ko": ("Malgun Gothic", "Noto Sans CJK KR"),
           "zh": ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC")}.get(lang())
    if cjk:   # Segoe UI hat keine japanischen/koreanischen/chinesischen Zeichen
        _families["text"] = _families["display"] = pick(*cjk, "Segoe UI")
    else:
        _families["text"] = pick("Segoe UI Variable Text", "Segoe UI", "Inter", "DejaVu Sans")
        _families["display"] = pick("Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", "Inter",
                                    "DejaVu Sans")
    _families["mono"] = pick("Cascadia Mono", "Consolas", "DejaVu Sans Mono")


def family(kind="text"):
    return _families.get(kind) or ("Segoe UI" if os.name == "nt" else "DejaVu Sans")


_font_cache = {}


def F(size=13, weight="normal", kind="text"):
    key = (size, weight, kind)
    f = _font_cache.get(key)
    if f is None:
        f = ctk.CTkFont(family=family(kind), size=size, weight=weight)
        _font_cache[key] = f
    return f
