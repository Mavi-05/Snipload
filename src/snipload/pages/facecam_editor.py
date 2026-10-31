"""Facecam-Editor: Rahmen auf dem echten Videobild verschieben/anpassen, Live-Vorschau des 9:16-Shorts."""
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from .. import facecam
from .. import theme as T
from ..icons import icon
from ..util import fmt_short, resource_path, win_dark_titlebar
from ..widgets import button, label, switch

CAN_W, CAN_H = 704, 396     # Arbeitsflaeche (16:9)
PREV_H = 448                # Hoehe der 9:16-Vorschau


class FacecamEditor(ctk.CTkToplevel):
    """frames: Liste (t, PIL) der Analyse; result: Analyse-Ergebnis; layout: aktuelles Layout.
    on_apply(layout) wird beim Uebernehmen aufgerufen; on_redetect() startet eine neue Analyse."""

    def __init__(self, app, frames, result, layout, aspect, on_apply, on_redetect=None, mode="facecam", px=None):
        super().__init__(app, fg_color=T.BG)
        self.app = app
        self.title("Facecam einstellen – Snipload")
        self.bind("<KeyPress>", self._key)
        self.resizable(False, False)
        self.transient(app)
        self.frames = [(t, im) for t, im in frames if im is not None]
        self.result = result or {}
        self.aspect = aspect
        self.on_apply = on_apply
        self.on_redetect = on_redetect
        self.mode = mode
        self.layout = dict(facecam.DEFAULT_LAYOUT)
        self.layout.update(layout or {})
        if not self.layout.get("cam"):
            self.layout["cam"] = (0.70, 0.04, 0.27, 0.36)  # typische Facecam oben rechts
        ref = self.frames[0][1].size if self.frames else (1920, 1080)
        self.ref_w, self.ref_h = ref
        # Pixel sind die "Wahrheit" (1:1); die normierte Box wird daraus berechnet
        if px and px.get("ref_w"):
            k = self.ref_w / px["ref_w"]
            self.px = {"x": int(round(px["x"] * k)), "y": int(round(px["y"] * k)), "w": int(round(px["w"] * k)),
                       "h": int(round(px["h"] * k)), "ref_w": self.ref_w, "ref_h": self.ref_h}
        else:
            self.px = facecam.norm_to_px(self.layout["cam"], self.ref_w, self.ref_h)
        self.layout["cam"] = facecam.px_to_norm(self.px)
        self.idx = self._first_good_frame()
        self.drag = None
        self._photo = None
        self._prev_job = None
        self.scale = ctk.ScalingTracker.get_widget_scaling(app) or 1.0
        self._build()
        self._load_frame()
        self.after(40, lambda: win_dark_titlebar(self, T.BG))
        self.after(250, self._icon)
        self.update_idletasks()
        try:
            x = app.winfo_rootx() + max(0, (app.winfo_width() - self.winfo_width()) // 2)
            y = app.winfo_rooty() + 30
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass
        self.grab_set()
        self.focus_force()
        self.bind("<Escape>", lambda e: self.destroy())

    def _icon(self):
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

    def _first_good_frame(self):
        missing = set(self.result.get("missing") or [])
        for i, (t, _) in enumerate(self.frames):
            if t not in missing:
                return i
        return 0

    # ------------------------------------------------------------ Aufbau
    def _build(self):
        S = lambda v: int(round(v * self.scale))
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=18)

        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="", image=icon("monitor", 20, T.ACCENT)).pack(side="left", padx=(0, 10))
        label(head, "Facecam einstellen", 19, T.TEXT, "bold", kind="display").pack(side="left")
        self.status = ctk.CTkFrame(body, fg_color=T.SURFACE, corner_radius=T.RADIUS_SM, border_width=1,
                                   border_color=T.BORDER)
        self.status.pack(fill="x", pady=(12, 12))
        self.st_icon = ctk.CTkLabel(self.status, text="")
        self.st_icon.pack(side="left", padx=(12, 8), pady=9)
        self.st_text = label(self.status, "", 12, T.TEXT, anchor="w", justify="left", wraplength=880)
        self.st_text.pack(side="left", fill="x", expand=True, pady=9)
        self._show_status()

        main = ctk.CTkFrame(body, fg_color="transparent")
        main.pack(fill="both", expand=True)

        # ---- links: Videobild mit Rahmen
        left = ctk.CTkFrame(main, fg_color=T.SURFACE, corner_radius=T.RADIUS, border_width=1, border_color=T.BORDER)
        left.pack(side="left", fill="y")
        label(left, "Zieh den roten Rahmen auf die Facecam – an den Ecken änderst du die Größe.", 12, T.TEXT_2,
              anchor="w").pack(fill="x", padx=16, pady=(14, 8))
        self.cw, self.ch = S(CAN_W), S(CAN_H)
        self.canvas = tk.Canvas(left, width=self.cw, height=self.ch, bg=T.SURFACE, highlightthickness=0, bd=0)
        self.canvas.pack(padx=16)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._move)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Motion>", self._hover)

        pxrow = ctk.CTkFrame(left, fg_color="transparent")
        pxrow.pack(fill="x", padx=16, pady=(10, 0))
        self.px_vars = {}
        for i, (key, name) in enumerate((("x", "X"), ("y", "Y"), ("w", "Breite"), ("h", "Höhe"))):
            label(pxrow, name, 11, T.TEXT_3, "bold").grid(row=0, column=i * 2, padx=(0 if i == 0 else 12, 6))
            v = tk.StringVar()
            e = ctk.CTkEntry(pxrow, textvariable=v, width=70, height=30, justify="center", fg_color=T.SURFACE_2,
                             border_color=T.BORDER, text_color=T.TEXT, font=T.F(13, kind="mono"))
            e.grid(row=0, column=i * 2 + 1)
            e.bind("<Return>", lambda ev: self._px_typed())
            e.bind("<FocusOut>", lambda ev: self._px_typed())
            self.px_vars[key] = v
        label(pxrow, f"px  ·  Video {self.ref_w}×{self.ref_h}", 11, T.TEXT_3).grid(row=0, column=8, padx=(12, 0))
        label(left, "Feinschliff: Pfeiltasten verschieben um 1 px, mit Umschalt ändern sie die Größe.", 11,
              T.TEXT_3, anchor="w").pack(fill="x", padx=16, pady=(6, 0))

        # Bildleiste: alle geprueften Bilder aus dem Zeitraum
        strip = ctk.CTkFrame(left, fg_color="transparent")
        strip.pack(fill="x", padx=16, pady=(12, 14))
        label(strip, "GEPRÜFTE STELLEN IM ZEITRAUM", 11, T.TEXT_3, "bold").pack(anchor="w", pady=(0, 6))
        row = ctk.CTkFrame(strip, fg_color="transparent")
        row.pack(fill="x")
        self.thumb_btns = []
        missing = set(self.result.get("missing") or [])
        tw, th = 62, 35
        for i, (t, im) in enumerate(self.frames):
            ok = t not in missing
            small = im.copy()
            small.thumbnail((tw * 2, th * 2))
            img = ctk.CTkImage(small, size=(tw, th))
            b = ctk.CTkButton(row, text=fmt_short(t), image=img, compound="top", width=tw + 8, height=th + 26,
                              fg_color=T.SURFACE_2, hover_color=T.SURFACE_3, corner_radius=8, border_width=2,
                              border_color=T.BORDER, text_color=T.TEXT_2 if ok else T.WARN, font=T.F(10),
                              command=lambda i=i: self._select(i))
            b.pack(side="left", padx=(0, 6))
            self.thumb_btns.append(b)

        # ---- rechts: Vorschau + Regler
        right = ctk.CTkFrame(main, fg_color=T.SURFACE, corner_radius=T.RADIUS, border_width=1, border_color=T.BORDER)
        right.pack(side="left", fill="both", expand=True, padx=(14, 0))
        label(right, "SO SIEHT DEIN SHORT AUS" if self.mode == "facecam" else "DEINE FACECAM (1:1)", 11,
              T.TEXT_3, "bold").pack(anchor="w", padx=16, pady=(14, 8))
        self.prev = ctk.CTkLabel(right, text="", width=int(PREV_H * 9 / 16), height=PREV_H, fg_color=T.SURFACE_2,
                                 corner_radius=10)
        self.prev.pack(padx=16)

        self.size_lbl = label(right, "", 14, T.TEXT, "bold")
        self.size_lbl.pack(anchor="w", padx=16, pady=(10, 0))
        ctl = ctk.CTkFrame(right, fg_color="transparent")
        if self.mode == "facecam":
            ctl.pack(fill="x", padx=16, pady=(14, 0))
        label(ctl, "FACECAM-HÖHE", 11, T.TEXT_3, "bold").pack(anchor="w")
        self.split = ctk.CTkSlider(ctl, from_=0.25, to=0.6, number_of_steps=35, command=self._split_changed,
                                   progress_color=T.ACCENT, button_color="#ffffff", button_hover_color="#ffffff",
                                   fg_color=T.SURFACE_3, width=240)
        self.split.set(self.layout.get("split", 0.4))
        self.split.pack(anchor="w", pady=(4, 10))
        label(ctl, "GAMEPLAY-AUSSCHNITT", 11, T.TEXT_3, "bold").pack(anchor="w")
        self.gx = ctk.CTkSlider(ctl, from_=0, to=1, number_of_steps=100, command=self._gx_changed,
                                progress_color=T.ACCENT, button_color="#ffffff", button_hover_color="#ffffff",
                                fg_color=T.SURFACE_3, width=240)
        self.gx.set(self.layout.get("gx", 0.5))
        self.gx.pack(anchor="w", pady=(4, 10))
        self.bottom_var = tk.BooleanVar(value=bool(self.layout.get("cam_bottom")))
        switch(ctl, "Facecam unten", self.bottom_var, self._bottom_changed).pack(anchor="w", pady=(0, 6))

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill="x", pady=(14, 0))
        if self.on_redetect:
            button(btns, "Neu erkennen", self._redetect, "ghost", icon_name="refresh").pack(side="left")
        button(btns, "Übernehmen", self._apply, "primary", icon_name="check", width=150).pack(side="right")
        button(btns, "Abbrechen", self.destroy, "secondary", width=120).pack(side="right", padx=(0, 8))

    def _show_status(self):
        r = self.result
        if not r:
            ic, col, txt = "info", T.TEXT_2, "Leg die Facecam von Hand fest."
        elif not r.get("ok"):
            ic, col = "alert", T.WARN
            txt = (r.get("message") or "Keine Facecam erkannt.") + " Leg den Rahmen bitte von Hand fest."
        elif r.get("fullscreen"):
            ic, col, txt = "info", T.TEXT_2, r.get("message")
        elif r.get("coverage", 0) >= 1.0:
            ic, col, txt = "check", T.SUCCESS, r.get("message") + " Prüf kurz die Bilder unten."
        else:
            ic, col, txt = "alert", T.WARN, r.get("message") + " Gelb markierte Stellen ansehen."
        self.st_icon.configure(image=icon(ic, 18, col))
        self.st_text.configure(text=txt)

    # ------------------------------------------------------------ Bild
    def _select(self, i):
        self.idx = i
        self._load_frame()

    def _load_frame(self):
        if not self.frames:
            self.base = Image.new("RGB", (self.cw, self.ch), (30, 30, 36))
            self.full = self.base
        else:
            self.full = self.frames[self.idx][1].convert("RGB")
            self.base = self.full.resize((self.cw, self.ch), Image.LANCZOS)
        for i, b in enumerate(self.thumb_btns):
            b.configure(border_color=T.ACCENT if i == self.idx else T.BORDER)
        self._redraw()

    def _px(self):
        x, y, w, h = self.layout["cam"]
        return x * self.cw, y * self.ch, (x + w) * self.cw, (y + h) * self.ch

    def _redraw(self):
        x0, y0, x1, y1 = self._px()
        img = self.base.convert("RGBA")
        shade = Image.new("RGBA", img.size, (8, 8, 11, 150))
        d = ImageDraw.Draw(shade)
        d.rectangle([x0, y0, x1, y1], fill=(0, 0, 0, 0))
        # Gameplay-Ausschnitt gestrichelt andeuten
        g = facecam.layout_geometry(self._layout_for_preview(), self.aspect)["game"]
        img.alpha_composite(shade)
        self._photo = ImageTk.PhotoImage(img)
        c = self.canvas
        c.delete("all")
        c.create_image(0, 0, image=self._photo, anchor="nw")
        gx0, gy0 = g[0] * self.cw, g[1] * self.ch
        gx1, gy1 = (g[0] + g[2]) * self.cw, (g[1] + g[3]) * self.ch
        if self.mode == "facecam":
            c.create_rectangle(gx0 + 1, gy0 + 1, gx1 - 1, gy1 - 1, outline="#ffffff", dash=(6, 5), width=1)
            c.create_text(gx0 + 8, gy1 - 10, text="Gameplay", anchor="sw", fill="#ffffff",
                          font=(T.family(), -int(11 * self.scale), "bold"))
        w = max(2, int(3 * self.scale))
        c.create_rectangle(x0, y0, x1, y1, outline=T.ACCENT, width=w)
        r = int(7 * self.scale)
        for hx, hy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            c.create_oval(hx - r, hy - r, hx + r, hy + r, fill="#ffffff", outline=T.ACCENT, width=w)
        c.create_text(x0 + 8, y0 + 8, text="Facecam", anchor="nw", fill="#ffffff",
                      font=(T.family(), -int(11 * self.scale), "bold"))
        for k, v in self.px_vars.items():
            if str(self.focus_get()) != str(getattr(v, "_entry", "")):
                v.set(str(self.px[k]))
        self.size_lbl.configure(text=f"{self.px['w']} × {self.px['h']} px")
        self._schedule_preview()

    def _set_px(self, x, y, w, h):
        """Pixelwerte setzen (gerade Masse, innerhalb des Bildes)."""
        w = max(16, min(int(w), self.ref_w)) // 2 * 2
        h = max(16, min(int(h), self.ref_h)) // 2 * 2
        x = max(0, min(int(x), self.ref_w - w))
        y = max(0, min(int(y), self.ref_h - h))
        self.px.update(x=x, y=y, w=w, h=h)
        self.layout["cam"] = facecam.px_to_norm(self.px)
        self._redraw()

    def _px_typed(self):
        try:
            vals = {k: int(float(v.get())) for k, v in self.px_vars.items()}
        except ValueError:
            self._redraw()
            return
        self._set_px(vals["x"], vals["y"], vals["w"], vals["h"])

    def _key(self, e):
        w = self.focus_get()
        if w is not None and w.winfo_class() == "Entry":
            return
        d = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}.get(e.keysym)
        if not d:
            return
        p = self.px
        if e.state & 1:  # Umschalt: Groesse aendern (in 2-px-Schritten, H.264 braucht gerade Masse)
            self._set_px(p["x"], p["y"], p["w"] + 2 * d[0], p["h"] + 2 * d[1])
        else:
            self._set_px(p["x"] + d[0], p["y"] + d[1], p["w"], p["h"])
        return "break"

    def _layout_for_preview(self):
        lay = dict(self.layout)
        lay["split"] = float(self.split.get()) if hasattr(self, "split") else lay.get("split", 0.4)
        lay["gx"] = float(self.gx.get()) if hasattr(self, "gx") else lay.get("gx", 0.5)
        lay["cam_bottom"] = bool(self.bottom_var.get()) if hasattr(self, "bottom_var") else lay.get("cam_bottom")
        return lay

    def _schedule_preview(self):
        if self._prev_job is None:
            self._prev_job = self.after(30, self._render_preview)

    def _render_preview(self):
        self._prev_job = None
        try:
            if self.mode == "facecam_raw":
                k = self.full.size[0] / self.ref_w
                p = self.px
                crop = self.full.crop((int(p["x"] * k), int(p["y"] * k), int((p["x"] + p["w"]) * k),
                                       int((p["y"] + p["h"]) * k)))
                box_w, box_h = int(PREV_H * 9 / 16), PREV_H
                crop.thumbnail((box_w * 2, box_h * 2), Image.LANCZOS)
                mask = Image.new("L", crop.size, 0)
                ImageDraw.Draw(mask).rounded_rectangle([0, 0, crop.size[0] - 1, crop.size[1] - 1], radius=14,
                                                       fill=255)
                out = Image.new("RGBA", crop.size, (0, 0, 0, 0))
                out.paste(crop, (0, 0), mask)
                self._prev_img = ctk.CTkImage(out, size=(crop.size[0] // 2, crop.size[1] // 2))
                self.prev.configure(image=self._prev_img, fg_color=T.SURFACE)
                return
            pv = facecam.render_preview(self.full, self._layout_for_preview(), PREV_H * 2)
            mask = Image.new("L", pv.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, pv.size[0] - 1, pv.size[1] - 1], radius=20, fill=255)
            out = Image.new("RGBA", pv.size, (0, 0, 0, 0))
            out.paste(pv, (0, 0), mask)
            self._prev_img = ctk.CTkImage(out, size=(int(PREV_H * 9 / 16), PREV_H))
            self.prev.configure(image=self._prev_img, fg_color=T.SURFACE)
        except Exception:
            pass

    # ------------------------------------------------------------ Maus
    def _hit(self, x, y):
        x0, y0, x1, y1 = self._px()
        r = 12 * self.scale
        for name, (hx, hy) in (("nw", (x0, y0)), ("ne", (x1, y0)), ("sw", (x0, y1)), ("se", (x1, y1))):
            if abs(x - hx) <= r and abs(y - hy) <= r:
                return name
        e = 7 * self.scale
        if y0 < y < y1 and abs(x - x0) <= e:
            return "w"
        if y0 < y < y1 and abs(x - x1) <= e:
            return "e"
        if x0 < x < x1 and abs(y - y0) <= e:
            return "n"
        if x0 < x < x1 and abs(y - y1) <= e:
            return "s"
        if x0 < x < x1 and y0 < y < y1:
            return "move"
        return None

    def _hover(self, e):
        h = self._hit(e.x, e.y)
        cur = {"move": "fleur", "nw": "size_nw_se", "se": "size_nw_se", "ne": "size_ne_sw", "sw": "size_ne_sw",
               "w": "sb_h_double_arrow", "e": "sb_h_double_arrow", "n": "sb_v_double_arrow",
               "s": "sb_v_double_arrow"}.get(h, "crosshair")
        try:
            self.canvas.configure(cursor=cur)
        except tk.TclError:
            self.canvas.configure(cursor="hand2")

    def _press(self, e):
        h = self._hit(e.x, e.y)
        if h is None:  # neuen Rahmen aufziehen
            h = "se"
            nx, ny = e.x / self.cw, e.y / self.ch
            self.layout["cam"] = (nx, ny, 0.01, 0.01)
        self.drag = (h, e.x, e.y, tuple(self.layout["cam"]))

    def _move(self, e):
        if not self.drag:
            return
        h, sx, sy, (x, y, w, hgt) = self.drag
        dx, dy = (e.x - sx) / self.cw, (e.y - sy) / self.ch
        x0, y0, x1, y1 = x, y, x + w, y + hgt
        if h == "move":
            x0 = min(max(0.0, x + dx), 1 - w)
            y0 = min(max(0.0, y + dy), 1 - hgt)
            x1, y1 = x0 + w, y0 + hgt
        else:
            if "w" in h:
                x0 = min(max(0.0, x + dx), x1 - 0.05)
            if "e" in h:
                x1 = max(min(1.0, x + w + dx), x0 + 0.05)
            if "n" in h:
                y0 = min(max(0.0, y + dy), y1 - 0.05)
            if "s" in h:
                y1 = max(min(1.0, y + hgt + dy), y0 + 0.05)
        self._set_px(round(x0 * self.ref_w), round(y0 * self.ref_h), round((x1 - x0) * self.ref_w),
                     round((y1 - y0) * self.ref_h))

    def _release(self, e):
        self.drag = None
        x, y, w, h = self.layout["cam"]
        if w < 0.05 or h < 0.05:  # versehentlicher Klick
            self.layout["cam"] = (min(x, 0.9), min(y, 0.9), max(w, 0.1), max(h, 0.1))
            self._redraw()

    # ------------------------------------------------------------ Regler
    def _split_changed(self, v):
        self._redraw()

    def _gx_changed(self, v):
        self._redraw()

    def _bottom_changed(self):
        self._redraw()

    def _redetect(self):
        self.destroy()
        if self.on_redetect:
            self.on_redetect()

    def _apply(self):
        self._px_typed()
        lay = self._layout_for_preview()
        lay["cam"] = facecam.px_to_norm(self.px)
        lay["manual"] = True
        self.on_apply(lay, dict(self.px))
        self.destroy()
