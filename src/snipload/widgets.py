"""Wiederverwendbare Bausteine: Knoepfe, Karten, Zeitleiste, Zeitfeld, Meldungen."""
import math
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from . import theme as T
from .icons import icon
from .util import fmt_field, fmt_short, parse_time


# ================================================================ Knoepfe & Karten
def button(master, text="", command=None, kind="secondary", icon_name=None, size="md", **kw):
    """kind: primary | secondary | ghost | danger ; size: sm | md | lg"""
    h = {"sm": 30, "md": 36, "lg": 46}[size]
    fs = {"sm": 12, "md": 13, "lg": 14}[size]
    isz = {"sm": 14, "md": 16, "lg": 18}[size]
    if kind == "primary":
        opts = dict(fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, text_color="#ffffff",
                    text_color_disabled="#c9a0aa", border_width=0)
        ic_color = "#ffffff"
    elif kind == "ghost":
        opts = dict(fg_color="transparent", hover_color=T.SURFACE_3, text_color=T.TEXT_2,
                    text_color_disabled=T.TEXT_3, border_width=0)
        ic_color = T.TEXT_2
    elif kind == "danger":
        opts = dict(fg_color=T.SURFACE_2, hover_color=T.DANGER_SOFT, text_color=T.DANGER,
                    text_color_disabled=T.TEXT_3, border_width=1, border_color=T.BORDER)
        ic_color = T.DANGER
    else:
        opts = dict(fg_color=T.SURFACE_2, hover_color=T.SURFACE_3, text_color=T.TEXT,
                    text_color_disabled=T.TEXT_3, border_width=1, border_color=T.BORDER)
        ic_color = T.TEXT
    opts.update(height=h, corner_radius=T.RADIUS_SM if size != "lg" else T.RADIUS,
                font=T.F(fs, "bold" if kind == "primary" else "normal"))
    if icon_name:
        opts.update(image=icon(icon_name, isz, kw.pop("icon_color", ic_color)), compound="left")
    if not text:
        opts.setdefault("width", h)
    opts.update(kw)
    b = ctk.CTkButton(master, text=text, command=command, **opts)
    b._sn_kind = kind
    return b


def card(master, **kw):
    opts = dict(fg_color=T.SURFACE, corner_radius=T.RADIUS, border_width=1, border_color=T.BORDER)
    opts.update(kw)
    return ctk.CTkFrame(master, **opts)


def label(master, text="", size=13, color=T.TEXT_2, weight="normal", kind="text", **kw):
    return ctk.CTkLabel(master, text=text, text_color=color, font=T.F(size, weight, kind), **kw)


def entry(master, **kw):
    opts = dict(height=38, corner_radius=T.RADIUS_SM, fg_color=T.SURFACE_2, border_color=T.BORDER,
                border_width=1, text_color=T.TEXT, placeholder_text_color=T.TEXT_3, font=T.F(13))
    opts.update(kw)
    return ctk.CTkEntry(master, **opts)


def segmented(master, values, command=None, **kw):
    opts = dict(height=34, corner_radius=T.RADIUS_SM, fg_color=T.SURFACE_2, selected_color=T.ACCENT,
                selected_hover_color=T.ACCENT_HOVER, unselected_color=T.SURFACE_2,
                unselected_hover_color=T.SURFACE_3, text_color=T.TEXT, text_color_disabled=T.TEXT_3,
                font=T.F(12), border_width=2)
    opts.update(kw)
    return ctk.CTkSegmentedButton(master, values=values, command=command, **opts)


def option_menu(master, values, command=None, **kw):
    opts = dict(height=34, corner_radius=T.RADIUS_SM, fg_color=T.SURFACE_2, button_color=T.SURFACE_2,
                button_hover_color=T.SURFACE_3, text_color=T.TEXT, text_color_disabled=T.TEXT_3,
                dropdown_fg_color=T.SURFACE, dropdown_hover_color=T.SURFACE_3, dropdown_text_color=T.TEXT,
                font=T.F(12), dropdown_font=T.F(12), dynamic_resizing=False)
    opts.update(kw)
    return ctk.CTkOptionMenu(master, values=values, command=command, **opts)


def switch(master, text, variable=None, command=None, **kw):
    opts = dict(text=text, variable=variable, command=command, progress_color=T.ACCENT,
                button_color="#ffffff", button_hover_color="#ffffff", fg_color=T.SURFACE_3,
                text_color=T.TEXT, font=T.F(13), switch_width=40, switch_height=22)
    opts.update(kw)
    return ctk.CTkSwitch(master, **opts)


def badge(master, text, fg=T.SURFACE_3, color=T.TEXT_2, **kw):
    return ctk.CTkLabel(master, text=text, fg_color=fg, text_color=color, corner_radius=8,
                        font=T.F(11, "bold"), height=20, padx=7, **kw)


def progress_bar(master, **kw):
    opts = dict(height=8, corner_radius=4, fg_color=T.SURFACE_3, progress_color=T.ACCENT)
    opts.update(kw)
    pb = ctk.CTkProgressBar(master, **opts)
    pb.set(0)
    return pb


# ================================================================ Zeitfeld mit -/+ Knoepfen
class TimeField(ctk.CTkFrame):
    """[-] 00:02:05 [+]  - Mausrad oder Pfeiltasten aendern um 1 s (Umschalt: 5 s)."""

    def __init__(self, master, on_commit, on_soft=None, title=""):
        super().__init__(master, fg_color="transparent")
        self.on_commit = on_commit
        self.on_soft = on_soft
        self.var = tk.StringVar(value="00:00:00")
        label(self, title, 11, T.TEXT_3, "bold").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.minus = button(self, "", lambda: self.nudge(-1), icon_name="minus", size="md", width=34)
        self.minus.grid(row=1, column=0)
        self.entry = entry(self, textvariable=self.var, width=104, justify="center", font=T.F(14, kind="mono"))
        self.entry.grid(row=1, column=1, padx=4)
        self.plus = button(self, "", lambda: self.nudge(1), icon_name="plus", size="md", width=34)
        self.plus.grid(row=1, column=2)
        for seq in ("<Return>", "<FocusOut>", "<KP_Enter>"):
            self.entry.bind(seq, self._commit)
        self.entry.bind("<KeyRelease>", self._soft)
        self.entry.bind("<Up>", lambda e: (self.nudge(5 if e.state & 1 else 1), "break")[1])
        self.entry.bind("<Down>", lambda e: (self.nudge(-5 if e.state & 1 else -1), "break")[1])
        for w in (self.entry, self.entry._entry):
            w.bind("<MouseWheel>", self._wheel)
            w.bind("<Button-4>", self._wheel)
            w.bind("<Button-5>", self._wheel)

    def get(self):
        return parse_time(self.var.get())

    def set(self, sec):
        self.var.set(fmt_field(sec))

    def set_raw(self, text):
        self.var.set(text)

    def nudge(self, d):
        try:
            v = parse_time(self.var.get() or "0")
        except ValueError:
            v = 0
        self.var.set(fmt_field(max(0, v + d)))
        self.on_commit()

    def _wheel(self, e):
        up = getattr(e, "delta", 0) > 0 or getattr(e, "num", 0) == 4
        self.nudge(5 if (e.state & 1) else 1) if up else self.nudge(-5 if (e.state & 1) else -1)
        return "break"

    def _commit(self, e=None):
        self.on_commit()

    def _soft(self, e=None):
        if self.on_soft and e is not None and e.keysym not in ("Return", "Up", "Down", "Tab"):
            self.on_soft()

    def set_state(self, on):
        st = "normal" if on else "disabled"
        for w in (self.minus, self.plus, self.entry):
            w.configure(state=st)


# ================================================================ Zeitleiste mit Filmstreifen
class Timeline(tk.Canvas):
    """Trimm-Leiste wie im Videoschnitt: Filmstreifen, zwei Griffe, Zeitskala, Hover-Zeit.

    on_change(a, b, which) beim Ziehen; on_hover(t oder None) fuer die Vorschau.
    """

    def __init__(self, master, scale, on_change, on_hover=None, bg=T.SURFACE):
        self.s = scale
        S = lambda v: int(round(v * scale))
        self.S = S
        self.top_h = S(26)       # Zeit-Etiketten ueber den Griffen
        self.strip_h = S(58)     # Filmstreifen
        self.axis_h = S(24)      # Zeitskala
        self.pad = S(14)
        super().__init__(master, height=self.top_h + self.strip_h + self.axis_h, bg=bg,
                         highlightthickness=0, bd=0, takefocus=1)
        self.bgc = bg
        self.on_change = on_change
        self.on_hover = on_hover
        self.duration = 0.0
        self.a = 0.0
        self.b = 0.0
        self.active = "a"
        self.drag = None
        self.drag_off = 0.0
        self.hover = None
        self.hover_x = None
        self.enabled = True
        self.loading = False
        self.hint = "Füg oben einen Link ein – dann legst du hier Start und Ende fest."
        self.storyboard = None
        self._base = None
        self._base_key = None
        self._photo = None
        self._sb_seen = -1
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", self._leave)
        for k, d in (("<Left>", -1), ("<Right>", 1)):
            self.bind(k, lambda e, d=d: self._key(e, d))
        self.bind("<Tab>", self._tab)

    # ---------------------------------------- API
    def set_duration(self, d):
        self.duration = float(d or 0)
        self._base = None
        self.redraw()

    def set_range(self, a, b):
        if self.duration > 0:
            a = max(0.0, min(a, self.duration))
            b = max(0.0, min(b, self.duration))
        self.a, self.b = a, b
        self.redraw()

    def set_storyboard(self, sb):
        self.storyboard = sb
        self._base = None
        self._sb_seen = -1
        self.redraw()

    def storyboard_progress(self):
        """Vom Hauptthread regelmaessig aufgerufen: neu geladene Kacheln einzeichnen."""
        sb = self.storyboard
        if sb is not None and sb.loaded != self._sb_seen:
            self._sb_seen = sb.loaded
            self._base = None
            self.redraw()

    def set_enabled(self, on):
        self.enabled = on
        self.redraw()

    # ---------------------------------------- Geometrie
    @property
    def x0(self):
        return self.pad

    @property
    def x1(self):
        return max(self.pad + 10, self.winfo_width() - self.pad)

    def _x(self, t):
        if not self.duration:
            return self.x0
        return self.x0 + (self.x1 - self.x0) * (t / self.duration)

    def _t(self, x):
        f = (x - self.x0) / max(1, (self.x1 - self.x0))
        return max(0.0, min(1.0, f)) * self.duration

    def _font(self, px, weight="normal", kind="text"):
        return (T.family(kind), -int(round(px * self.s)), weight)

    # ---------------------------------------- Filmstreifen
    def _build_base(self, w, h):
        key = (w, h, self._sb_seen, id(self.storyboard))
        if self._base is not None and self._base_key == key:
            return self._base
        sb = self.storyboard
        img = Image.new("RGB", (w, h), _rgb(T.SURFACE_2))
        if sb is not None and self.duration > 0:
            tile_w = max(8, int(h * 16 / 9))
            n = max(1, math.ceil(w / tile_w))
            for i in range(n):
                t = min(self.duration - 0.01, (i + 0.5) * self.duration / n)
                fr = sb.frame(t)
                if fr is None:
                    continue
                fr = _cover(fr, tile_w, h)
                img.paste(fr, (i * tile_w, 0))
            # feine Trennlinien zwischen den Kacheln
            d = ImageDraw.Draw(img)
            for i in range(1, n):
                d.line([(i * tile_w, 0), (i * tile_w, h)], fill=_rgb(T.SURFACE), width=1)
        else:
            # ohne Storyboard: dezente Kachelstruktur, damit die Leiste nicht leer wirkt
            d = ImageDraw.Draw(img)
            tile_w = max(8, int(h * 16 / 9))
            for x in range(0, w, tile_w):
                d.rectangle([x + 2, 2, x + tile_w - 3, h - 3], fill=_rgb("#202029"))
        self._base, self._base_key = img, key
        return img

    def _strip_photo(self, w, h, xa, xb):
        base = self._build_base(w, h).copy().convert("RGBA")
        shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shade)
        a, b = int(xa), int(xb)
        if a > 0:
            sd.rectangle([0, 0, a, h], fill=(8, 8, 11, 175))
        if b < w:
            sd.rectangle([b, 0, w, h], fill=(8, 8, 11, 175))
        if not self.enabled:
            sd.rectangle([0, 0, w, h], fill=(8, 8, 11, 120))
        base.alpha_composite(shade)
        # abgerundete Ecken gegen den Kartenhintergrund
        k = 3
        mask = Image.new("L", (w * k, h * k), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * k - 1, h * k - 1], radius=self.S(8) * k, fill=255)
        mask = mask.resize((w, h), Image.LANCZOS)
        out = Image.new("RGBA", (w, h), _rgb(self.bgc) + (255,))
        out.paste(base, (0, 0), mask)
        return ImageTk.PhotoImage(out)

    # ---------------------------------------- Zeichnen
    def redraw(self):
        self.delete("all")
        W = self.winfo_width()
        if W < 40:
            return
        S = self.S
        y0 = self.top_h
        y1 = y0 + self.strip_h
        x0, x1 = self.x0, self.x1
        if self.duration <= 0:
            self._round_rect(x0, y0, x1, y1, S(8), fill=T.SURFACE_2, outline=T.BORDER)
            for x in range(int(x0) + S(16), int(x1) - S(10), S(30)):
                self.create_line(x, y0 + S(14), x, y1 - S(14), fill="#202029", width=S(2))
            txt = "Video wird geladen …" if self.loading else self.hint
            self.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=txt, fill=T.TEXT_3, font=self._font(13))
            return
        xa, xb = self._x(self.a), self._x(self.b)
        w, h = int(x1 - x0), int(self.strip_h)
        self._photo = self._strip_photo(w, h, xa - x0, xb - x0)
        self.create_image(x0, y0, image=self._photo, anchor="nw")
        col = T.ACCENT if self.enabled else T.TEXT_3
        # Auswahlrahmen oben/unten
        lw = S(3)
        self.create_rectangle(xa, y0, xb, y0 + lw, fill=col, width=0)
        self.create_rectangle(xa, y1 - lw, xb, y1, fill=col, width=0)
        # Griffe
        hw = S(11)
        for name, x, side in (("a", xa, -1), ("b", xb, 1)):
            hot = self.drag == name or self.hover == name
            fill = T.ACCENT_HOVER if hot and self.enabled else col
            gx0, gx1 = (x - hw, x + S(1)) if side < 0 else (x - S(1), x + hw)
            self._round_rect(gx0, y0, gx1, y1, S(5), fill=fill, outline="")
            cx = (gx0 + gx1) / 2
            for dx in (-S(2), S(2)):
                self.create_line(cx + dx, (y0 + y1) / 2 - S(8), cx + dx, (y0 + y1) / 2 + S(8),
                                 fill="#ffffff", width=max(1, S(1.5)))
        # Hover-Linie mit Zeit
        if self.hover_x is not None and self.drag is None and self.enabled and self.hover in (None, "mid", "out"):
            hx = max(x0, min(x1, self.hover_x))
            self.create_line(hx, y0 - S(2), hx, y1 + S(2), fill="#ffffff", width=max(1, S(1.5)))
            self._bubble(hx, fmt_short(self._t(hx)), T.SURFACE_3, T.TEXT)
        else:
            self._range_labels(xa, xb)
        self._axis(x0, x1, y1)

    def _range_labels(self, xa, xb):
        S = self.S
        la, lb = fmt_short(self.a), fmt_short(self.b)
        gap = S(54)
        ta, tb = xa, xb
        if tb - ta < gap:
            mid = (ta + tb) / 2
            ta, tb = mid - gap / 2, mid + gap / 2
        ta_col = T.ACCENT if self.enabled else T.TEXT_3
        self._bubble(ta, la, ta_col, "#ffffff")
        self._bubble(tb, lb, ta_col, "#ffffff")

    def _bubble(self, x, text, fill, color):
        S = self.S
        f = self._font(11.5, "bold")
        tid = self.create_text(0, 0, text=text, font=f)
        bx0, by0, bx1, by1 = self.bbox(tid)
        self.delete(tid)
        bw = (bx1 - bx0) + S(12)
        bh = S(20)
        W = self.winfo_width()
        cx = max(bw / 2 + 1, min(W - bw / 2 - 1, x))
        y = S(2)
        self._round_rect(cx - bw / 2, y, cx + bw / 2, y + bh, S(6), fill=fill, outline="")
        self.create_text(cx, y + bh / 2, text=text, font=f, fill=color)

    def _axis(self, x0, x1, y):
        S = self.S
        d = self.duration
        width = x1 - x0
        target = max(2, int(width / S(90)))
        steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200]
        step = next((s for s in steps if d / s <= target), steps[-1])
        t = 0.0
        while t <= d + 0.001:
            x = self._x(t)
            self.create_line(x, y + S(4), x, y + S(9), fill=T.TEXT_3, width=1)
            anchor = "w" if t == 0 else ("e" if abs(t - d) < step * 0.3 else "center")
            if not (anchor == "center" and abs(t - d) < step * 0.6):
                self.create_text(x, y + S(17), text=fmt_short(t), fill=T.TEXT_3, font=self._font(10.5),
                                 anchor=anchor)
            t += step
        if abs((t - step) - d) > step * 0.3:  # Ende immer beschriften
            self.create_text(x1, y + S(17), text=fmt_short(d), fill=T.TEXT_3, font=self._font(10.5), anchor="e")

    def _round_rect(self, x0, y0, x1, y1, r, **kw):
        r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
               x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.create_polygon(pts, smooth=True, **kw)

    # ---------------------------------------- Maus & Tastatur
    def _which(self, x, y=None):
        if self.duration <= 0:
            return None
        xa, xb = self._x(self.a), self._x(self.b)
        grab = self.S(14)
        da, db = x - xa, x - xb
        if -grab <= da <= grab * 0.6 and (abs(da) <= abs(db) or x < xa):
            return "a"
        if -grab * 0.6 <= db <= grab:
            return "b"
        if xa < x < xb:
            return "mid"
        return "out"

    def _motion(self, e):
        if not self.enabled or self.duration <= 0 or self.drag:
            return
        self.hover = self._which(e.x, e.y)
        self.hover_x = e.x
        cur = {"a": "sb_h_double_arrow", "b": "sb_h_double_arrow", "mid": "fleur"}.get(self.hover, "hand2")
        self.configure(cursor=cur)
        if self.on_hover:
            self.on_hover(self._t(e.x) if self.hover in ("mid", "out") else (self.a if self.hover == "a" else self.b))
        self.redraw()

    def _leave(self, e):
        if self.drag:
            return
        self.hover = None
        self.hover_x = None
        if self.on_hover:
            self.on_hover(None)
        self.redraw()

    def _press(self, e):
        self.focus_set()
        if self.duration <= 0 or not self.enabled:
            return
        w = self._which(e.x, e.y)
        if w == "out":  # neben die Auswahl: naechsten Griff dorthin
            t = round(self._t(e.x))
            w = "a" if abs(t - self.a) <= abs(t - self.b) else "b"
            self._apply(w, t)
        elif w == "mid":
            self.drag_off = self._t(e.x) - self.a
        if w in ("a", "b"):
            self.active = w
        self.drag = w
        self.redraw()

    def _apply(self, which, t):
        gap = 1.0 if self.duration >= 2 else 0.1
        if which == "a":
            self.a = max(0.0, min(t, self.b - gap))
        else:
            self.b = min(self.duration, max(t, self.a + gap))
        self.active = which
        self.redraw()
        self.on_change(self.a, self.b, which)
        if self.on_hover:
            self.on_hover(self.a if which == "a" else self.b)

    def _move(self, e):
        if not self.drag:
            return
        if self.drag == "mid":
            length = self.b - self.a
            na = round(max(0.0, min(self._t(e.x) - self.drag_off, self.duration - length)))
            self.a, self.b = na, min(self.duration, na + length)
            self.redraw()
            self.on_change(self.a, self.b, "mid")
            if self.on_hover:
                self.on_hover(self.a)
        else:
            self._apply(self.drag, round(self._t(e.x)))

    def _release(self, e):
        self.drag = None
        self._motion(e)

    def _key(self, e, d):
        if self.duration <= 0 or not self.enabled:
            return
        step = 5 if e.state & 1 else (0.1 if e.state & 0x20000 or e.state & 8 else 1)  # Umschalt / Alt
        cur = self.a if self.active == "a" else self.b
        self._apply(self.active, round(cur + d * step, 1))
        return "break"

    def _tab(self, e):
        self.active = "b" if self.active == "a" else "a"
        self.redraw()
        if self.on_hover:
            self.on_hover(self.a if self.active == "a" else self.b)
        return "break"


def _rgb(hexcol):
    return tuple(int(hexcol[i:i + 2], 16) for i in (1, 3, 5))


def _cover(img, w, h):
    iw, ih = img.size
    s = max(w / iw, h / ih)
    nw, nh = max(1, int(iw * s + 0.5)), max(1, int(ih * s + 0.5))
    img = img.resize((nw, nh), Image.BILINEAR)
    l, t = (nw - w) // 2, (nh - h) // 2
    return img.crop((l, t, l + w, t + h))


# ================================================================ Meldungen (Toasts)
class Toaster:
    """Kurze Meldungen unten rechts im Fenster."""

    COLORS = {"info": (T.SURFACE_2, "info", T.TEXT_2), "success": (T.SURFACE_2, "check", T.SUCCESS),
              "warn": (T.SURFACE_2, "alert", T.WARN), "error": (T.SURFACE_2, "alert", T.DANGER)}

    def __init__(self, root):
        self.root = root
        self.items = []

    def show(self, text, kind="info", ms=3800, action=None, action_text=None, key=None):
        if key:  # gleiche Meldung ersetzen statt stapeln
            for old in [f for f in self.items if getattr(f, "_sn_key", None) == key]:
                self._close(old)
        bg, ic, col = self.COLORS.get(kind, self.COLORS["info"])
        f = ctk.CTkFrame(self.root, fg_color=bg, corner_radius=T.RADIUS, border_width=1, border_color=T.BORDER_STRONG)
        ctk.CTkLabel(f, text="", image=icon(ic, 18, col)).grid(row=0, column=0, padx=(14, 8), pady=12)
        label(f, text, 13, T.TEXT, wraplength=360, justify="left", anchor="w").grid(row=0, column=1, sticky="w",
                                                                                      pady=12)
        col_i = 2
        if action:
            def run():
                self._close(f)
                action()
            button(f, action_text or "Öffnen", run, "secondary", size="sm").grid(row=0, column=col_i, padx=(12, 0))
            col_i += 1
        button(f, "", lambda: self._close(f), "ghost", icon_name="x", size="sm", width=28).grid(
            row=0, column=col_i, padx=(6, 8))
        f._sn_key = key
        self.items.append(f)
        self._layout()
        self.root.after(ms, lambda: self._close(f))
        return f

    def _close(self, f):
        if f in self.items:
            self.items.remove(f)
            try:
                f.destroy()
            except Exception:
                pass
            self._layout()

    def _layout(self):
        # oben rechts, neueste oben - so verdecken Meldungen nie die Knoepfe unten
        for f in self.items[:-4]:
            f.place_forget()
        y = 18
        for f in reversed(self.items[-4:]):
            f.place(relx=1.0, rely=0.0, x=-22, y=y, anchor="ne")
            f.lift()
            f.update_idletasks()
            y += f.winfo_height() / max(0.5, ctk.ScalingTracker.get_widget_scaling(f)) + 10


# ================================================================ Lade-Platzhalter
class Shimmer:
    """Laesst Platzhalter-Flaechen sanft pulsieren, waehrend Daten laden."""

    def __init__(self, root, widgets):
        self.root = root
        self.widgets = widgets
        self.on = False
        self.i = 0
        self.cols = ["#1c1c23", "#202028", "#24242d", "#282832", "#24242d", "#202028"]

    def start(self):
        if not self.on:
            self.on = True
            self._tick()

    def stop(self):
        self.on = False
        for w in self.widgets:
            try:
                w.configure(fg_color=T.SURFACE_2)
            except Exception:
                pass

    def _tick(self):
        if not self.on:
            return
        c = self.cols[self.i % len(self.cols)]
        self.i += 1
        for w in self.widgets:
            try:
                w.configure(fg_color=c)
            except Exception:
                pass
        self.root.after(130, self._tick)


# ================================================================ Dialog
def dialog(root, title, text, ok_text="OK", cancel_text="Abbrechen", kind="info", danger=False):
    """Eigener, zum Design passender Dialog. Gibt True (OK) oder False zurueck."""
    win = ctk.CTkToplevel(root, fg_color=T.SURFACE)
    win.title(title)
    win.resizable(False, False)
    win.transient(root)
    result = {"ok": False}
    ic, col = {"info": ("info", T.TEXT_2), "warn": ("alert", T.WARN), "error": ("alert", T.DANGER),
               "question": ("info", T.ACCENT), "download": ("download", T.ACCENT)}.get(kind, ("info", T.TEXT_2))
    body = ctk.CTkFrame(win, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=24, pady=(22, 18))
    head = ctk.CTkFrame(body, fg_color="transparent")
    head.pack(fill="x")
    ctk.CTkLabel(head, text="", image=icon(ic, 22, col)).pack(side="left", padx=(0, 10))
    label(head, title, 17, T.TEXT, "bold", kind="display").pack(side="left")
    label(body, text, 13, T.TEXT_2, wraplength=400, justify="left", anchor="w").pack(fill="x", pady=(12, 20))
    row = ctk.CTkFrame(body, fg_color="transparent")
    row.pack(fill="x")

    def close(ok):
        result["ok"] = ok
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()

    if ok_text:
        button(row, ok_text, lambda: close(True), "danger" if danger else "primary", width=120).pack(side="right")
    if cancel_text:
        button(row, cancel_text, lambda: close(False), "secondary", width=110).pack(side="right", padx=(0, 8))
    win.bind("<Escape>", lambda e: close(False))
    win.bind("<Return>", lambda e: close(True))
    win.protocol("WM_DELETE_WINDOW", lambda: close(False))
    win.update_idletasks()
    try:
        rx, ry = root.winfo_rootx(), root.winfo_rooty()
        rw, rh = root.winfo_width(), root.winfo_height()
        ww, wh = win.winfo_reqwidth(), win.winfo_reqheight()
        win.geometry(f"+{rx + (rw - ww) // 2}+{ry + max(40, (rh - wh) // 3)}")
    except Exception:
        pass
    from .util import win_dark_titlebar, resource_path
    win.after(30, lambda: win_dark_titlebar(win, T.SURFACE))
    win.after(250, lambda: _set_icon(win, resource_path("icon.ico")))
    try:
        win.grab_set()
    except Exception:
        pass
    win.focus_force()
    root.wait_window(win)
    return result["ok"]


def _set_icon(win, path):
    try:
        win.iconbitmap(path)
    except Exception:
        pass
