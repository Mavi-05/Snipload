"""Eigene Linien-Icons (24er-Raster, im Stil von Lucide), mit 4-facher Aufloesung gezeichnet."""
import math

import customtkinter as ctk
from PIL import Image, ImageDraw

from . import theme as T

_cache = {}


class _Pen:
    def __init__(self, size_px, color, stroke=2.0):
        self.S = size_px * 4
        self.k = self.S / 24.0
        self.img = Image.new("RGBA", (self.S, self.S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.c = color
        self.w = max(2, int(round(stroke * self.k)))

    def P(self, x, y):
        return (x * self.k, y * self.k)

    def _cap(self, x, y):
        r = self.w / 2
        cx, cy = self.P(x, y)
        self.d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=self.c)

    def line(self, *pts):
        pp = [self.P(x, y) for x, y in pts]
        self.d.line(pp, fill=self.c, width=self.w, joint="curve")
        for x, y in pts:
            self._cap(x, y)

    def circle(self, x, y, r, fill=False):
        a, b = self.P(x - r, y - r)
        c, d = self.P(x + r, y + r)
        if fill:
            self.d.ellipse([a, b, c, d], fill=self.c)
        else:
            self.d.ellipse([a, b, c, d], outline=self.c, width=self.w)

    def rrect(self, x0, y0, x1, y1, r, fill=False):
        box = [*self.P(x0, y0), *self.P(x1, y1)]
        if fill:
            self.d.rounded_rectangle(box, radius=r * self.k, fill=self.c)
        else:
            self.d.rounded_rectangle(box, radius=r * self.k, outline=self.c, width=self.w)

    def arc(self, x, y, r, start, end):
        a, b = self.P(x - r, y - r)
        c, d = self.P(x + r, y + r)
        self.d.arc([a, b, c, d], start, end, fill=self.c, width=self.w)

    def poly(self, *pts):
        self.d.polygon([self.P(x, y) for x, y in pts], fill=self.c)


def _draw(name, p):
    L = p.line
    if name == "download":
        L((12, 3), (12, 15)); L((7, 10), (12, 15), (17, 10)); L((3, 15), (3, 19.5), (21, 19.5), (21, 15))
    elif name == "queue":
        for y in (6, 12, 18):
            L((9, y), (21, y)); p.circle(4, y, 1.3, fill=True)
    elif name == "history":
        p.circle(12, 12, 9); L((12, 7), (12, 12), (15.5, 14))
    elif name == "settings":
        for x, y1, y2, knob in ((5, 21, 3, 14), (12, 21, 3, 8), (19, 21, 3, 16)):
            L((x, y1), (x, knob + 2.2)); L((x, knob - 2.2), (x, y2))
            p.circle(x, knob, 2.2)
    elif name == "link":
        tmp = _Pen(p.S // 4, p.c)
        tmp.rrect(2.5, 9, 13.5, 15, 3); tmp.rrect(10.5, 9, 21.5, 15, 3)
        p.img.alpha_composite(tmp.img.rotate(45, resample=Image.BICUBIC))
    elif name == "paste":
        p.rrect(5, 4.5, 19, 21.5, 2.5); p.rrect(8.5, 2.5, 15.5, 6.5, 1.2)
        L((9, 12), (15, 12)); L((9, 16), (13, 16))
    elif name == "play":
        p.poly((7.5, 4.5), (19.5, 12), (7.5, 19.5))
    elif name == "folder":
        L((3, 7.5), (3, 18.5), (21, 18.5), (21, 9), (11.5, 9), (9.5, 6), (3, 6), (3, 7.5))
    elif name == "external":
        L((18, 13.5), (18, 20), (4, 20), (4, 6), (10.5, 6)); L((14.5, 4), (20, 4), (20, 9.5)); L((10, 14), (20, 4))
    elif name == "check":
        L((5, 12.5), (10, 17.5), (19, 7))
    elif name == "x":
        L((6, 6), (18, 18)); L((18, 6), (6, 18))
    elif name == "alert":
        L((12, 3.5), (21.5, 20), (2.5, 20), (12, 3.5)); L((12, 9.5), (12, 13.5)); p.circle(12, 16.8, 1.2, fill=True)
    elif name == "info":
        p.circle(12, 12, 9); L((12, 11), (12, 16.5)); p.circle(12, 7.8, 1.2, fill=True)
    elif name == "refresh":
        p.arc(12, 12, 8.5, 0, 270); L((12, 3.5), (17.5, 5.2), (20.5, 8)); L((20.5, 3), (20.5, 8), (15.5, 8))
    elif name == "film":
        p.rrect(3, 3, 21, 21, 2.5)
        L((7.5, 3), (7.5, 21)); L((16.5, 3), (16.5, 21)); L((3, 12), (21, 12))
        L((3, 7.5), (7.5, 7.5)); L((3, 16.5), (7.5, 16.5)); L((16.5, 7.5), (21, 7.5)); L((16.5, 16.5), (21, 16.5))
    elif name == "music":
        L((9, 18), (9, 5), (21, 3), (21, 16)); p.circle(6, 18, 3); p.circle(18, 16, 3)
    elif name == "scissors":
        p.circle(6, 6, 3); p.circle(6, 18, 3)
        L((20, 4), (8.2, 15.8)); L((14.5, 14.5), (20, 20)); L((8.2, 8.2), (12, 12))
    elif name == "plus":
        L((12, 5), (12, 19)); L((5, 12), (19, 12))
    elif name == "minus":
        L((5, 12), (19, 12))
    elif name == "trash":
        L((3.5, 6.5), (20.5, 6.5)); L((18.5, 6.5), (17.5, 20.5), (6.5, 20.5), (5.5, 6.5))
        L((9, 6.5), (9, 3.5), (15, 3.5), (15, 6.5)); L((10, 11), (10, 16.5)); L((14, 11), (14, 16.5))
    elif name == "search":
        p.circle(10.5, 10.5, 7); L((15.8, 15.8), (21, 21))
    elif name == "phone":
        p.rrect(6.5, 2.5, 17.5, 21.5, 2.5); L((10.5, 18), (13.5, 18))
    elif name == "monitor":
        p.rrect(2.5, 4, 21.5, 16.5, 2); L((8, 21), (16, 21)); L((12, 16.5), (12, 21))
    elif name == "sparkles":
        L((12, 3), (12, 7)); L((12, 17), (12, 21)); L((3, 12), (7, 12)); L((17, 12), (21, 12))
        L((5.6, 5.6), (8.4, 8.4)); L((15.6, 15.6), (18.4, 18.4)); L((5.6, 18.4), (8.4, 15.6)); L((15.6, 8.4), (18.4, 5.6))
    elif name == "pause":
        p.rrect(6, 4.5, 10, 19.5, 1, fill=True); p.rrect(14, 4.5, 18, 19.5, 1, fill=True)
    elif name == "chevron-down":
        L((6, 9), (12, 15), (18, 9))
    elif name == "arrow-right":
        L((5, 12), (19, 12)); L((13, 6), (19, 12), (13, 18))
    elif name == "keyboard":
        p.rrect(2.5, 6, 21.5, 18, 2)
        for x in (6.5, 10, 13.5, 17):
            p.circle(x, 10, 0.9, fill=True)
        L((7.5, 14.5), (16.5, 14.5))
    else:
        p.circle(12, 12, 8)


def icon_pil(name, size=18, color=T.TEXT, stroke=2.0):
    key = ("pil", name, size, color, stroke)
    if key not in _cache:
        rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
        p = _Pen(size, rgb, stroke)
        _draw(name, p)
        _cache[key] = p.img
    return _cache[key]


def icon(name, size=18, color=T.TEXT, stroke=2.0):
    """CTkImage, das CustomTkinter je nach Bildschirm-Skalierung scharf herunterrechnet."""
    key = ("ctk", name, size, color, stroke)
    if key not in _cache:
        img = icon_pil(name, size, color, stroke)
        _cache[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    return _cache[key]


def rounded_image(img, w, h, radius, bg=None):
    """Bild auf w x h zuschneiden (16:9 fuellend) und Ecken abrunden."""
    iw, ih = img.size
    target = w / h
    if iw / ih > target:
        nw = int(ih * target)
        img = img.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh = int(iw / target)
        img = img.crop((0, (ih - nh) // 2, iw, (ih - nh) // 2 + nh))
    img = img.convert("RGB").resize((w, h), Image.LANCZOS)
    mask = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * 4 - 1, h * 4 - 1], radius=radius * 4, fill=255)
    mask = mask.resize((w, h), Image.LANCZOS)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out
