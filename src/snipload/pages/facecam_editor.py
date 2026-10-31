"""Facecam-Editor: Rahmen auf dem echten Videobild verschieben/anpassen, Live-Vorschau des 9:16-Shorts."""
import math
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
        # Groessen (Facecam-Hoehe, Zooms) laufen automatisch mit, bis man sie selbst aendert
        self.sizes_manual = bool(self.layout.get("sizes_manual"))
        if not self.sizes_manual and not (layout or {}).get("gzoom"):
            self._auto_sizes()
        self.idx = self._first_good_frame()
        self.pdrag = None
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
        self.pw, self.ph = S(int(PREV_H * 9 / 16)), S(PREV_H)
        self.pcanvas = tk.Canvas(right, width=self.pw, height=self.ph, bg=T.SURFACE_2, highlightthickness=0, bd=0)
        self.pcanvas.pack(padx=16)
        if self.mode == "facecam":
            pc = self.pcanvas
            pc.bind("<ButtonPress-1>", self._p_press)
            pc.bind("<B1-Motion>", self._p_move)
            pc.bind("<ButtonRelease-1>", self._p_release)
            pc.bind("<Motion>", self._p_hover)
            pc.bind("<Leave>", lambda e: self._p_hover(None))
            pc.bind("<MouseWheel>", lambda e: self._p_wheel(e, 1 if e.delta > 0 else -1))
            pc.bind("<Button-4>", lambda e: self._p_wheel(e, 1))
            pc.bind("<Button-5>", lambda e: self._p_wheel(e, -1))
            label(right, "Ziehen verschiebt · Mausrad zoomt · Trennlinie ziehen ändert die Höhe", 11, T.TEXT_3,
                  anchor="w", justify="left", wraplength=S(250)).pack(fill="x", padx=16, pady=(6, 0))
        self._hover_part = None

        self.size_lbl = label(right, "", 13, T.TEXT, "bold", anchor="w", justify="left")
        self.size_lbl.pack(anchor="w", padx=16, pady=(8, 0))
        ctl = ctk.CTkFrame(right, fg_color="transparent")
        if self.mode == "facecam":
            ctl.pack(fill="x", padx=16, pady=(10, 0))
        self.sliders = {}
        for key, name in (("split", "FACECAM-HÖHE"), ("czoom", "FACECAM-ZOOM"), ("gzoom", "GAMEPLAY-ZOOM")):
            hd = ctk.CTkFrame(ctl, fg_color="transparent")
            hd.pack(fill="x")
            label(hd, name, 11, T.TEXT_3, "bold").pack(side="left")
            val = label(hd, "", 11, T.TEXT, "bold")
            val.pack(side="right")
            sl = ctk.CTkSlider(ctl, from_=0, to=1, number_of_steps=200,
                               command=lambda v, k=key: self._slider(k, v),
                               progress_color=T.ACCENT, button_color="#ffffff", button_hover_color="#ffffff",
                               fg_color=T.SURFACE_3, width=250)
            sl.pack(fill="x", pady=(3, 9))
            self.sliders[key] = (sl, val)
        sw = ctk.CTkFrame(ctl, fg_color="transparent")
        sw.pack(fill="x", pady=(0, 4))
        self.bottom_var = tk.BooleanVar(value=bool(self.layout.get("cam_bottom")))
        switch(sw, "Facecam unten", self.bottom_var, self._bottom_changed).pack(side="left")
        self.auto_btn = button(sw, "Automatisch", self._auto_clicked, "ghost", size="sm", icon_name="sparkles")
        self.auto_btn.pack(side="right")
        self._sync_sliders()

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
        if self.mode == "facecam":
            g = self._geom()
            self.size_lbl.configure(text=f"Facecam 1080 × {g['hf']}  ·  Gameplay 1080 × {g['hg']}")
        else:
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
        if not self.sizes_manual and self.mode == "facecam":
            self._auto_sizes()
            self._sync_sliders()
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
        lay["cam_bottom"] = bool(self.bottom_var.get()) if hasattr(self, "bottom_var") else lay.get("cam_bottom")
        return lay

    def _schedule_preview(self):
        if self._prev_job is None:
            self._prev_job = self.after(16, self._render_preview)

    def _small_full(self):
        """Verkleinerte Kopie des Bildes fuer eine fluessige Vorschau beim Ziehen."""
        if getattr(self, "_small_src", None) is not self.full:
            im = self.full
            if im.size[0] > 1600:
                im = im.resize((1600, int(1600 * im.size[1] / im.size[0])), Image.BILINEAR)
            self._small_src, self._small = self.full, im
        return self._small

    def _render_preview(self):
        self._prev_job = None
        c = self.pcanvas
        try:
            if self.mode == "facecam_raw":
                k = self.full.size[0] / self.ref_w
                p = self.px
                crop = self.full.crop((int(p["x"] * k), int(p["y"] * k), int((p["x"] + p["w"]) * k),
                                       int((p["y"] + p["h"]) * k)))
                crop.thumbnail((self.pw, self.ph), Image.LANCZOS)
                self._prev_photo = ImageTk.PhotoImage(crop)
                c.delete("all")
                c.create_image(self.pw // 2, self.ph // 2, image=self._prev_photo, anchor="center")
                return
            lay = self._layout_for_preview()
            pv = facecam.render_preview(self._small_full(), lay, self.ph)
            if pv.size != (self.pw, self.ph):
                pv = pv.resize((self.pw, self.ph), Image.BILINEAR)
            self._prev_photo = ImageTk.PhotoImage(pv)
            c.delete("all")
            c.create_image(0, 0, image=self._prev_photo, anchor="nw")
            self._draw_preview_overlay(lay)
        except Exception:
            pass

    def _geom(self):
        return facecam.layout_geometry(self._layout_for_preview(), self.aspect)

    def _parts(self):
        """Lage der beiden Flaechen in der Vorschau: {"cam": (y0, y1), "game": (y0, y1)} und Trennlinie."""
        g = self._geom()
        k = self.ph / facecam.OUT_H
        if g["cam_bottom"]:
            d = g["hg"] * k
            return {"game": (0, d), "cam": (d, self.ph)}, d, g
        d = g["hf"] * k
        return {"cam": (0, d), "game": (d, self.ph)}, d, g

    def _draw_preview_overlay(self, lay):
        c = self.pcanvas
        parts, d, g = self._parts()
        fnt = (T.family(), -int(10 * self.scale), "bold")
        hl = self._hover_part
        for name, (y0, y1) in parts.items():
            if hl == name:
                c.create_rectangle(1, y0 + 1, self.pw - 2, y1 - 2, outline=T.ACCENT, width=2)
            txt = "Facecam" if name == "cam" else "Gameplay"
            z = g["cam_plan" if name == "cam" else "game_plan"]["zoom"]
            tag = f"{txt}  {int(round(z * 100))} %"
            tx, ty = 8, y0 + 8
            tid = c.create_text(tx + 6, ty + 3, text=tag, anchor="nw", fill="#ffffff", font=fnt)
            bb = c.bbox(tid)
            if bb:
                r = c.create_rectangle(bb[0] - 6, bb[1] - 3, bb[2] + 6, bb[3] + 3, fill="#000000", outline="",
                                       stipple="gray50")
                c.tag_raise(tid, r)
        col = T.ACCENT if hl == "split" else "#ffffff"
        c.create_line(0, d, self.pw, d, fill=col, width=2 if hl == "split" else 1)
        gw, gh = int(30 * self.scale), int(8 * self.scale)
        cx = self.pw // 2
        c.create_rectangle(cx - gw // 2, d - gh // 2, cx + gw // 2, d + gh // 2, fill=col, outline="#000000")

    # ------------------------------------------------------------ Vorschau bedienen
    def _p_hit(self, x, y):
        parts, d, g = self._parts()
        if abs(y - d) <= 8 * self.scale:
            return "split"
        for name, (y0, y1) in parts.items():
            if y0 <= y < y1:
                return name
        return None

    def _p_hover(self, e):
        h = None if e is None else self._p_hit(e.x, e.y)
        cur = {"split": "sb_v_double_arrow", "cam": "fleur", "game": "fleur"}.get(h, "arrow")
        try:
            self.pcanvas.configure(cursor=cur)
        except tk.TclError:
            pass
        if h != self._hover_part:
            self._hover_part = h
            self._schedule_preview()

    def _p_press(self, e):
        h = self._p_hit(e.x, e.y)
        if h:
            self.pdrag = (h, e.x, e.y, dict(self.layout))

    def _p_move(self, e):
        if not self.pdrag:
            return
        h, sx, sy, start = self.pdrag
        k = self.ph / facecam.OUT_H
        if h == "split":
            y = min(max(e.y, 0), self.ph) / self.ph
            split = (1 - y) if self.bottom_var.get() else y
            self.layout["split"] = round(min(facecam.SPLIT_MAX, max(facecam.SPLIT_MIN, split)), 3)
        else:
            g = facecam.layout_geometry(dict(start, cam_bottom=self.bottom_var.get()), self.aspect)
            plan = g["cam_plan" if h == "cam" else "game_plan"]
            src = g["cam_src"] if h == "cam" else (0.0, 0.0, 1.0, 1.0)
            kx, ky = ("cx", "cy") if h == "cam" else ("gx", "gy")
            # Inhalt folgt der Maus: Mausweg (Vorschau-px) -> Ausgabe-px -> Bildhoehen -> normiert
            dx_n = (e.x - sx) / k / plan["scale"] / self.aspect
            dy_n = (e.y - sy) / k / plan["scale"]
            cx_, cy_, cw_, ch_ = plan["crop"]
            free_x, free_y = src[2] - cw_, src[3] - ch_
            if free_x > 1e-6:
                self.layout[kx] = round(min(1.0, max(0.0, (cx_ - dx_n - src[0]) / free_x)), 4)
            if free_y > 1e-6:
                self.layout[ky] = round(min(1.0, max(0.0, (cy_ - dy_n - src[1]) / free_y)), 4)
        self._touched()

    def _p_release(self, e):
        self.pdrag = None

    def _p_wheel(self, e, direction):
        h = self._p_hit(e.x, e.y)
        if h not in ("cam", "game"):
            return
        key = "czoom" if h == "cam" else "gzoom"
        plan = self._geom()["cam_plan" if h == "cam" else "game_plan"]
        z = plan["zoom"] * (1.08 if direction > 0 else 1 / 1.08)
        self.layout[key] = round(min(plan["zmax"], max(plan["zmin"], z)), 4)
        self._touched()

    # ------------------------------------------------------------ Groessen
    def _auto_sizes(self):
        lay = facecam.suggest_layout(self.layout["cam"], self.aspect, cam_bottom=self.layout.get("cam_bottom"))
        for k in ("split", "gzoom", "czoom", "gx", "gy", "cx", "cy"):
            self.layout[k] = lay[k]

    def _auto_clicked(self):
        self.sizes_manual = False
        self._auto_sizes()
        self._sync_sliders()
        self._redraw()

    def _touched(self):
        self.sizes_manual = True
        self._sync_sliders()
        self._redraw()

    def _zoom_to_t(self, z, zmin, zmax):
        return 0.0 if zmax <= zmin else math.log(max(z, zmin) / zmin) / math.log(zmax / zmin)

    def _sync_sliders(self):
        if not getattr(self, "sliders", None):
            return
        g = self._geom()
        sl, val = self.sliders["split"]
        split = g["hf"] / facecam.OUT_H
        sl.set((split - facecam.SPLIT_MIN) / (facecam.SPLIT_MAX - facecam.SPLIT_MIN))
        val.configure(text=f"{int(round(split * 100))} %")
        for key, pk in (("czoom", "cam_plan"), ("gzoom", "game_plan")):
            p = g[pk]
            sl, val = self.sliders[key]
            sl.set(self._zoom_to_t(p["zoom"], p["zmin"], p["zmax"]))
            if p["zoom"] <= p["zmin"] + 1e-3:
                txt = "ganzes Bild"
            elif p["bg"]:
                txt = f"{int(round(p['zoom'] * 100))} % · mit Rand"
            else:
                txt = f"{int(round(p['zoom'] * 100))} %"
            val.configure(text=txt)
        self.auto_btn.configure(state="normal" if self.sizes_manual else "disabled")

    def _slider(self, key, t):
        g = self._geom()
        if key == "split":
            self.layout["split"] = round(facecam.SPLIT_MIN + float(t) * (facecam.SPLIT_MAX - facecam.SPLIT_MIN), 3)
        else:
            p = g["cam_plan" if key == "czoom" else "game_plan"]
            self.layout[key] = round(p["zmin"] * (p["zmax"] / p["zmin"]) ** float(t), 4)
        self._touched()

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
    def _bottom_changed(self):
        self.layout["cam_bottom"] = bool(self.bottom_var.get())
        self._touched()

    def _redetect(self):
        self.destroy()
        if self.on_redetect:
            self.on_redetect()

    def _apply(self):
        self._px_typed()
        lay = self._layout_for_preview()
        lay["cam"] = facecam.px_to_norm(self.px)
        lay["manual"] = True
        lay["sizes_manual"] = self.sizes_manual
        self.on_apply(lay, dict(self.px))
        self.destroy()
