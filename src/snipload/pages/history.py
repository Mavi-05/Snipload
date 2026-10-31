"""Seite "Verlauf": alle heruntergeladenen Clips mit Vorschaubild und Suche."""
import os
import time

import customtkinter as ctk

from .. import theme as T
from ..icons import icon
from ..util import fmt_short, fmt_size, open_path, show_in_folder
from ..widgets import button, dialog, entry, label
from .queue import thumb_image

PAGE_SIZE = 60


class HistoryPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=T.BG, corner_radius=0)
        self.app = app
        self.rows = []
        self._sig = None
        self._typed_at = 0
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD - 4, 10))
        head.grid_columnconfigure(0, weight=1)
        label(head, "Verlauf", 24, T.TEXT, "bold", kind="display").grid(row=0, column=0, sticky="w")
        self.sub = label(head, "", 13, T.TEXT_3)
        self.sub.grid(row=1, column=0, sticky="w")
        sf = ctk.CTkFrame(head, fg_color=T.SURFACE_2, corner_radius=T.RADIUS_SM, border_width=1,
                          border_color=T.BORDER)
        sf.grid(row=0, column=1, rowspan=2, padx=(0, 10))
        ctk.CTkLabel(sf, text="", image=icon("search", 15, T.TEXT_3)).pack(side="left", padx=(12, 2))
        self.search = ctk.CTkEntry(sf, placeholder_text="Suchen …", width=220, height=34, border_width=0,
                                   fg_color=T.SURFACE_2, text_color=T.TEXT, placeholder_text_color=T.TEXT_3,
                                   font=T.F(13))
        self.search.pack(side="left", padx=(0, 6), pady=2)
        self.search.bind("<KeyRelease>", lambda e: setattr(self, "_typed_at", time.time()))
        self.clear_btn = button(head, "Leeren", self.clear, "ghost", icon_name="trash")
        self.clear_btn.grid(row=0, column=2, rowspan=2)

        self.list = ctk.CTkScrollableFrame(self, fg_color=T.BG, corner_radius=0, scrollbar_button_color=T.SURFACE_3,
                                           scrollbar_button_hover_color=T.BORDER_STRONG)
        self.list.grid(row=1, column=0, sticky="nsew", padx=(T.PAD - 6, 6), pady=(0, T.PAD))
        self.list.grid_columnconfigure(0, weight=1)
        self.empty = ctk.CTkFrame(self.list, fg_color="transparent")
        ctk.CTkLabel(self.empty, text="", width=72, height=72, corner_radius=36, fg_color=T.SURFACE,
                     image=icon("history", 30, T.TEXT_3)).pack(pady=(70, 16))
        self.empty_title = label(self.empty, "Noch keine Clips", 17, T.TEXT, "bold", kind="display")
        self.empty_title.pack()
        self.empty_sub = label(self.empty, "Alles, was du herunterlädst, landet hier.", 13, T.TEXT_3)
        self.empty_sub.pack(pady=(6, 0))

    def tick(self):
        if self._typed_at and time.time() - self._typed_at > 0.25:
            self._typed_at = 0
            self.refresh(force=True)

    def clear(self):
        if not self.app.cfg.get("history"):
            return
        if dialog(self.app, "Verlauf leeren?", "Die Liste wird geleert. Deine Dateien bleiben natürlich erhalten.",
                  "Leeren", "Abbrechen", kind="warn", danger=True):
            self.app.cfg["history"] = []
            self.app.save()
            self.refresh(force=True)

    def remove(self, entry_):
        self.app.cfg["history"] = [h for h in self.app.cfg.get("history", []) if h is not entry_]
        self.app.save()
        self.refresh(force=True)

    def refresh(self, force=False):
        hist = self.app.cfg.get("history", [])
        q = self.search.get().strip().lower()
        items = [h for h in hist if not q or q in (h.get("title", "") + " " + h.get("channel", "")).lower()]
        sig = (len(hist), id(hist[0]) if hist else None, q)
        if sig == self._sig and not force:
            return
        self._sig = sig
        for r in self.rows:
            r.destroy()
        self.rows = []
        total_size = sum(h.get("size") or 0 for h in hist)
        self.sub.configure(text=f"{len(hist)} Clips  ·  {fmt_size(total_size)}" if hist else
                           "Deine heruntergeladenen Clips.")
        self.clear_btn.configure(state="normal" if hist else "disabled")
        if not items:
            self.empty_title.configure(text="Nichts gefunden" if q else "Noch keine Clips")
            self.empty_sub.configure(text=f"Kein Clip passt zu „{q}“." if q else
                                     "Alles, was du herunterlädst, landet hier.")
            self.empty.grid(row=0, column=0, sticky="nsew")
            return
        self.empty.grid_forget()
        for i, h in enumerate(items[:PAGE_SIZE]):
            r = self._row(h)
            r.grid(row=i, column=0, sticky="ew", padx=6, pady=(0, 8))
            self.rows.append(r)

    def _row(self, h):
        exists = bool(h.get("file")) and os.path.exists(h["file"])
        r = ctk.CTkFrame(self.list, fg_color=T.SURFACE, corner_radius=T.RADIUS, border_width=1, border_color=T.BORDER)
        r.grid_columnconfigure(1, weight=1)
        img = thumb_image(h.get("thumb"), 112, 63)
        kind_icon = "music" if h.get("kind") == "audio" else "film"
        ctk.CTkLabel(r, text="", width=112, height=63, corner_radius=8, fg_color=T.SURFACE if img else T.SURFACE_2,
                     image=img or icon(kind_icon, 20, T.TEXT_3)).grid(row=0, column=0, rowspan=2, padx=(12, 14),
                                                                      pady=10)
        title = h.get("title") or "Clip"
        label(r, title if len(title) <= 60 else title[:58].rstrip() + "…", 14, T.TEXT if exists else T.TEXT_3, "bold",
              anchor="w").grid(row=0, column=1, sticky="sew", pady=(10, 0))
        if h.get("start") in (None, 0) and h.get("end") is None:
            rng = "Ganzes Video"
        else:
            rng = f"{fmt_short(h.get('start') or 0)} – {fmt_short(h['end']) if h.get('end') is not None else 'Ende'}"
        parts = [rng, h.get("format") or h.get("kind", "").upper(), fmt_size(h.get("size")), h.get("date", "")]
        if not exists:
            parts.append("Datei nicht mehr vorhanden")
        label(r, "  ·  ".join(p for p in parts if p), 12, T.TEXT_3 if exists else T.DANGER, anchor="w").grid(
            row=1, column=1, sticky="new", pady=(2, 10))
        acts = ctk.CTkFrame(r, fg_color="transparent")
        acts.grid(row=0, column=2, rowspan=2, padx=(10, 12))
        b_play = button(acts, "", lambda: open_path(h["file"]), "secondary", icon_name="play", size="sm", width=32)
        b_play.pack(side="left")
        b_dir = button(acts, "", lambda: show_in_folder(h["file"]), "ghost", icon_name="folder", size="sm", width=32)
        b_dir.pack(side="left", padx=(4, 0))
        button(acts, "Nochmal", lambda: self.app.reuse(h), "ghost", icon_name="refresh", size="sm").pack(
            side="left", padx=(4, 0))
        button(acts, "", lambda: self.remove(h), "ghost", icon_name="x", size="sm", width=32).pack(side="left",
                                                                                                 padx=(4, 0))
        if not exists:
            b_play.configure(state="disabled")
            b_dir.configure(state="disabled")
        return r
