"""Seite "Neuer Clip": Link einfuegen, Abschnitt waehlen, Format waehlen, herunterladen."""
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from .. import theme as T
from .. import facecam
from .. import tools
from ..icons import icon, rounded_image
from ..jobs import Job, QUALITY_LABELS, ASPECT_LABELS, AUDIO_LABELS
from ..util import (build_name, fmt_count, fmt_duration_words, fmt_short, fmt_size, fmt_upload_date,
                    is_youtube, looks_like_url, open_path, parse_time, show_in_folder, start_from_url,
                    thumbs_dir)
from ..widgets import (Shimmer, Timeline, TimeField, badge, button, card, entry, label, option_menu, switch,
                       progress_bar, segmented)

PREV_W, PREV_H = 288, 162
KIND_VALUES = ["Video", "Nur Ton"]
ASPECT_VALUES = list(ASPECT_LABELS.values())
QUALITY_VALUES = list(QUALITY_LABELS.values())
AUDIO_VALUES = list(AUDIO_LABELS.values())


def _key_for(d, value):
    return next((k for k, v in d.items() if v == value), None)


class DownloadPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=T.BG, corner_radius=0)
        self.app = app
        self.cfg = app.cfg
        self.info = None
        self.summary = None
        self.storyboard = None
        self.thumb_pil = None
        self.thumb_path = None
        self.info_gen = 0
        self.url_seen = ""
        self.url_changed_at = 0.0
        self.name_dirty = False
        self.job = None
        self.preview_cache = {}
        self.hover_t = None
        self._sb_seen = -1
        self.sb_hi = None
        self._hi_seen = -1
        self.frame_fmt = None
        self.hd_cache = {}
        self.hd_want = None
        self.hd_due = 0.0
        self.hd_busy = False
        self.cur_t = None
        self.cam = None          # Facecam: {"vid","range","frames","result","layout","busy","progress"}
        self._shown_state = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build()
        self._apply_kind()
        self._refresh_bar()

    # ================================================================ Aufbau
    def _build(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD - 4, 10))
        head.grid_columnconfigure(0, weight=1)
        label(head, "Neuer Clip", 24, T.TEXT, "bold", kind="display").grid(row=0, column=0, sticky="w")
        label(head, "Link einfügen, Abschnitt wählen, fertig.", 13, T.TEXT_3).grid(row=1, column=0, sticky="w")

        self.body = ctk.CTkScrollableFrame(self, fg_color=T.BG, corner_radius=0,
                                           scrollbar_button_color=T.SURFACE_3,
                                           scrollbar_button_hover_color=T.BORDER_STRONG)
        self.body.grid(row=1, column=0, sticky="nsew", padx=(T.PAD - 6, 6))
        self.body.grid_columnconfigure(0, weight=1)
        self._build_video_card()
        self._build_range_card()
        self._build_output_card()
        self._build_bar()

    # ---------------------------------------------------------------- Karte 1: Link & Video
    def _build_video_card(self):
        c = card(self.body)
        c.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, T.GAP))
        c.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(c, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 0))
        bar.grid_columnconfigure(0, weight=1)
        field = ctk.CTkFrame(bar, fg_color=T.SURFACE_2, corner_radius=T.RADIUS_SM, border_width=1,
                             border_color=T.BORDER, height=44)
        field.grid(row=0, column=0, sticky="ew")
        field.grid_columnconfigure(1, weight=1)
        self.url_icon = ctk.CTkLabel(field, text="", image=icon("link", 17, T.TEXT_3))
        self.url_icon.grid(row=0, column=0, padx=(14, 4))
        self.url_entry = ctk.CTkEntry(field, placeholder_text="YouTube-Link einfügen  (Strg + V)", height=40,
                                      fg_color=T.SURFACE_2, border_width=0, text_color=T.TEXT,
                                      placeholder_text_color=T.TEXT_3, font=T.F(14))
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=(0, 4), pady=2)
        self.clear_btn = button(field, "", self.clear_url, "ghost", icon_name="x", size="sm", width=30)
        self.clear_btn.grid(row=0, column=2, padx=(0, 6))
        self.paste_btn = button(bar, "Einfügen", self.paste, "secondary", icon_name="paste", size="md", height=44)
        self.paste_btn.grid(row=0, column=1, padx=(10, 0))
        self.url_entry.bind("<Return>", lambda e: self._force_load())

        # Hinweis: neuer Link in der Zwischenablage
        self.clip_chip = ctk.CTkFrame(c, fg_color=T.ACCENT_SOFT, corner_radius=T.RADIUS_SM)
        self.clip_chip.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.clip_chip, text="", image=icon("paste", 15, T.ACCENT)).grid(row=0, column=0, padx=(12, 8),
                                                                                     pady=8)
        self.clip_lbl = label(self.clip_chip, "", 12, T.TEXT, anchor="w")
        self.clip_lbl.grid(row=0, column=1, sticky="ew")
        button(self.clip_chip, "Übernehmen", self._take_clip, "primary", size="sm").grid(row=0, column=2, padx=4)
        button(self.clip_chip, "", lambda: self.clip_chip.grid_remove(), "ghost", icon_name="x", size="sm",
               width=28).grid(row=0, column=3, padx=(0, 6))
        self.clip_pending = None

        # Video-Bereich
        v = ctk.CTkFrame(c, fg_color="transparent")
        v.grid(row=2, column=0, sticky="ew", padx=18, pady=(16, 18))
        v.grid_columnconfigure(1, weight=1)
        self.preview = ctk.CTkLabel(v, text="", width=PREV_W, height=PREV_H, fg_color=T.SURFACE_2,
                                    corner_radius=10, image=icon("film", 38, T.TEXT_3))
        self.preview.grid(row=0, column=0, rowspan=2, sticky="nw")
        self.preview_cap = badge(self.preview, "", fg="#000000", color="#ffffff")
        self.dur_badge = badge(self.preview, "", fg="#000000", color="#ffffff")

        info = ctk.CTkFrame(v, fg_color="transparent")
        info.grid(row=0, column=1, sticky="new", padx=(18, 0))
        info.grid_columnconfigure(0, weight=1)
        self.title_lbl = label(info, "Noch kein Video", 18, T.TEXT, "bold", kind="display", anchor="w",
                               justify="left", wraplength=420)
        self.title_lbl.grid(row=0, column=0, sticky="ew")
        self.meta_lbl = label(info, "Kopier einen YouTube-Link – Snipload erkennt ihn automatisch.", 13,
                              T.TEXT_3, anchor="w", justify="left", wraplength=420)
        self.meta_lbl.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        # Textumbruch an die tatsaechliche Breite anpassen (kleine Bildschirme)
        def rewrap(e):
            s = ctk.ScalingTracker.get_widget_scaling(info) or 1
            w = max(160, int(e.width / s) - 6)
            self.title_lbl.configure(wraplength=w)
            self.meta_lbl.configure(wraplength=w)
        info.bind("<Configure>", rewrap)
        acts = ctk.CTkFrame(v, fg_color="transparent", height=1)
        acts.grid(row=1, column=1, sticky="sw", padx=(18, 0))
        self.yt_btn = button(acts, "Auf YouTube ab Start ansehen", self.open_on_youtube, "secondary",
                             icon_name="external", size="sm")
        self.yt_btn.grid(row=0, column=0)
        self.retry_btn = button(acts, "Erneut laden", self._force_load, "secondary", icon_name="refresh", size="sm")
        self.yt_btn.grid_remove()
        self.retry_btn.grid_remove()
        self.shimmer = Shimmer(self, [self.preview])

    # ---------------------------------------------------------------- Karte 2: Abschnitt
    def _build_range_card(self):
        c = card(self.body)
        c.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, T.GAP))
        c.grid_columnconfigure(0, weight=1)
        hd = ctk.CTkFrame(c, fg_color="transparent")
        hd.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        hd.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hd, text="", image=icon("scissors", 16, T.TEXT_2)).grid(row=0, column=0, padx=(0, 8))
        label(hd, "Abschnitt", 15, T.TEXT, "bold", kind="display").grid(row=0, column=1, sticky="w")
        self.whole_btn = button(hd, "Ganzes Video", self.whole_video, "ghost", icon_name="film", size="sm")
        self.whole_btn.grid(row=0, column=2, padx=(6, 0))
        self.linkt_btn = button(hd, "Ab Link-Zeit", self._from_link_time, "ghost", icon_name="link", size="sm")

        scale = ctk.ScalingTracker.get_widget_scaling(c)
        self.timeline = Timeline(c, scale, self._timeline_changed, self._timeline_hover, bg=T.SURFACE)
        self.timeline.grid(row=1, column=0, sticky="ew", padx=6, pady=(4, 0))

        row = ctk.CTkFrame(c, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", padx=18, pady=(10, 16))
        row.grid_columnconfigure(1, weight=1)
        self.start_f = TimeField(row, lambda: self._fields_changed("a"), lambda: self._fields_changed("a", soft=True),
                                 "START")
        self.start_f.grid(row=0, column=0, sticky="w")
        mid = ctk.CTkFrame(row, fg_color="transparent")
        mid.grid(row=0, column=1)
        label(mid, "LÄNGE", 11, T.TEXT_3, "bold").pack()
        self.len_lbl = label(mid, "–", 22, T.TEXT, "bold", kind="display")
        self.len_lbl.pack()
        self.end_f = TimeField(row, lambda: self._fields_changed("b"), lambda: self._fields_changed("b", soft=True),
                               "ENDE")
        self.end_f.grid(row=0, column=2, sticky="e")
        self.keys_lbl = label(c, "Tipp: In die Leiste klicken, dann ← → bewegen den Griff (Umschalt = 5 s, "
                                 "Alt = 0,1 s), Tab wechselt zwischen Start und Ende.", 11, T.TEXT_3, anchor="w")
        self.keys_lbl.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 14))
        self.start_f.set(0)
        self.end_f.set(60)

    # ---------------------------------------------------------------- Karte 3: Ausgabe
    def _build_output_card(self):
        c = card(self.body)
        c.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, T.GAP))
        c.grid_columnconfigure((0, 1), weight=1, uniform="out")
        hd = ctk.CTkFrame(c, fg_color="transparent")
        hd.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 6))
        ctk.CTkLabel(hd, text="", image=icon("sparkles", 16, T.TEXT_2)).grid(row=0, column=0, padx=(0, 8))
        label(hd, "Ausgabe", 15, T.TEXT, "bold", kind="display").grid(row=0, column=1, sticky="w")

        left = ctk.CTkFrame(c, fg_color="transparent")
        left.grid(row=1, column=0, sticky="new", padx=(18, 9), pady=(4, 0))
        left.grid_columnconfigure(0, weight=1)
        label(left, "INHALT", 11, T.TEXT_3, "bold").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.kind_seg = segmented(left, KIND_VALUES, command=lambda v: self._apply_kind(save=True))
        self.kind_seg.grid(row=1, column=0, sticky="ew")
        self.kind_seg.set("Nur Ton" if self.cfg.get("kind") == "audio" else "Video")

        qf = ctk.CTkFrame(c, fg_color="transparent")
        qf.grid(row=1, column=1, sticky="new", padx=(9, 18), pady=(4, 0))
        qf.grid_columnconfigure(0, weight=1)
        self.q_title = label(qf, "QUALITÄT", 11, T.TEXT_3, "bold")
        self.q_title.grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.q_menu = option_menu(qf, QUALITY_VALUES, command=lambda v: self._save_opts())
        self.q_menu.set(QUALITY_LABELS.get(self.cfg.get("quality"), QUALITY_LABELS["best"]))
        self.q_menu.grid(row=1, column=0, sticky="ew")
        self.a_menu = option_menu(qf, AUDIO_VALUES, command=lambda v: self._save_opts())
        self.a_menu.set(AUDIO_LABELS.get(self.cfg.get("audio_fmt"), "MP3"))

        right = ctk.CTkFrame(c, fg_color="transparent")
        right.grid(row=2, column=0, columnspan=2, sticky="new", padx=18, pady=(14, 0))
        right.grid_columnconfigure(0, weight=1)
        label(right, "FORMAT", 11, T.TEXT_3, "bold").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.aspect_seg = segmented(right, ASPECT_VALUES, command=lambda v: self._apply_kind(save=True))
        self.aspect_seg.grid(row=1, column=0, sticky="ew")
        self.aspect_seg.set(ASPECT_LABELS.get(self.cfg.get("aspect"), "Original"))
        self.aspect_hint = label(right, "", 12, T.TEXT_3, anchor="w", justify="left", wraplength=700)
        self.aspect_hint.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        def rewrap_right(e):
            k = ctk.ScalingTracker.get_widget_scaling(right) or 1
            w = max(200, int(e.width / k) - 8)
            self.aspect_hint.configure(wraplength=w)
            self.fc_text.configure(wraplength=max(180, w - 260))
        right.bind("<Configure>", rewrap_right)
        self.also_var = tk.BooleanVar(value=bool(self.cfg.get("also_full", False)))
        self.also_sw = switch(right, "Zusätzlich das normale Video speichern", self.also_var, self._also_changed)
        self.fc_row = ctk.CTkFrame(right, fg_color=T.SURFACE_2, corner_radius=T.RADIUS_SM, border_width=1,
                                   border_color=T.BORDER)
        self.fc_row.grid_columnconfigure(1, weight=1)
        self.fc_icon = ctk.CTkLabel(self.fc_row, text="")
        self.fc_icon.grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=10, sticky="n")
        self.fc_text = label(self.fc_row, "", 12, T.TEXT, anchor="w", justify="left", wraplength=560)
        self.fc_text.grid(row=0, column=1, sticky="ew", pady=(10, 4), padx=(0, 10))
        self.fc_size = badge(self.fc_row, "", fg=T.ACCENT_SOFT, color=T.TEXT)
        fcb = ctk.CTkFrame(self.fc_row, fg_color="transparent")
        fcb.grid(row=1, column=1, sticky="w", pady=(0, 10))
        self.fc_edit = button(fcb, "Anpassen …", self.open_facecam_editor, "secondary", size="sm",
                              icon_name="monitor")
        self.fc_edit.pack(side="left")
        self.fc_recheck = button(fcb, "Neu prüfen", self.analyze_facecam, "ghost", size="sm", icon_name="refresh")
        self.fc_recheck.pack(side="left", padx=(6, 0))

        nm = ctk.CTkFrame(c, fg_color="transparent")
        nm.grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=(14, 0))
        nm.grid_columnconfigure(0, weight=1)
        label(nm, "DATEINAME", 11, T.TEXT_3, "bold").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.name_var = tk.StringVar()
        self.name_entry = entry(nm, textvariable=self.name_var)
        self.name_entry.grid(row=1, column=0, sticky="ew")
        self.ext_lbl = badge(nm, ".mp4", fg=T.SURFACE_2, color=T.TEXT_2)
        self.ext_lbl.grid(row=1, column=1, padx=(8, 0))
        self.name_entry.bind("<KeyRelease>", self._name_typed)
        self.reset_name_btn = button(nm, "", self._reset_name, "ghost", icon_name="refresh", size="sm", width=30)
        self.reset_name_btn.grid(row=1, column=2, padx=(4, 0))

        fd = ctk.CTkFrame(c, fg_color="transparent")
        fd.grid(row=4, column=0, columnspan=2, sticky="ew", padx=18, pady=(14, 18))
        fd.grid_columnconfigure(1, weight=1)
        label(fd, "SPEICHERN IN", 11, T.TEXT_3, "bold").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 5))
        ctk.CTkLabel(fd, text="", image=icon("folder", 16, T.TEXT_2)).grid(row=1, column=0, padx=(2, 8))
        self.folder_lbl = label(fd, "", 13, T.TEXT, anchor="w")
        self.folder_lbl.grid(row=1, column=1, sticky="ew")
        button(fd, "Ändern", self.pick_folder, "secondary", size="sm").grid(row=1, column=2, padx=(8, 0))
        button(fd, "Öffnen", lambda: open_path(self.cfg["folder"]), "ghost", size="sm",
               icon_name="external").grid(row=1, column=3, padx=(6, 0))
        self._show_folder()

    # ---------------------------------------------------------------- Aktionsleiste
    def _build_bar(self):
        outer = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=0, border_width=0, height=86)
        outer.grid(row=2, column=0, sticky="ew")
        ctk.CTkFrame(outer, fg_color=T.BORDER, height=1, corner_radius=0).pack(fill="x", side="top")
        self.bar = ctk.CTkFrame(outer, fg_color="transparent")
        self.bar.pack(fill="both", expand=True, padx=T.PAD, pady=14)
        self.bar.grid_columnconfigure(0, weight=1)

        # Bereit
        self.idle = ctk.CTkFrame(self.bar, fg_color="transparent")
        self.idle.grid_columnconfigure(0, weight=1)
        self.sum1 = label(self.idle, "", 14, T.TEXT, "bold", anchor="w")
        self.sum1.grid(row=0, column=0, sticky="w")
        self.sum2 = label(self.idle, "", 12, T.TEXT_3, anchor="w")
        self.sum2.grid(row=1, column=0, sticky="w")
        self.queue_btn = button(self.idle, "Zur Warteschlange", self.add_to_queue, "secondary", icon_name="plus",
                                size="lg", width=190)
        self.queue_btn.grid(row=0, column=1, rowspan=2, padx=(0, 10))
        self.go_btn = button(self.idle, "Herunterladen", self.download, "primary", icon_name="download", size="lg",
                             width=200)
        self.go_btn.grid(row=0, column=2, rowspan=2)

        # Laeuft
        self.run = ctk.CTkFrame(self.bar, fg_color="transparent")
        self.run.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self.run, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        self.run_stage = label(top, "", 14, T.TEXT, "bold", anchor="w")
        self.run_stage.grid(row=0, column=0, sticky="w")
        self.run_pct = label(top, "", 14, T.TEXT, "bold")
        self.run_pct.grid(row=0, column=1, sticky="e")
        self.run_bar = progress_bar(self.run)
        self.run_bar.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self.run_detail = label(self.run, "", 12, T.TEXT_3, anchor="w")
        self.run_detail.grid(row=2, column=0, sticky="w")
        self.cancel_btn = button(self.run, "Abbrechen", self.cancel, "secondary", icon_name="x", size="lg", width=150)
        self.cancel_btn.grid(row=0, column=1, rowspan=3, padx=(20, 0))

        # Fertig / Fehler
        self.done = ctk.CTkFrame(self.bar, fg_color="transparent")
        self.done.grid_columnconfigure(1, weight=1)
        self.done_icon = ctk.CTkLabel(self.done, text="", width=40, height=40, corner_radius=20,
                                      fg_color=T.SUCCESS_SOFT, image=icon("check", 20, T.SUCCESS))
        self.done_icon.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        self.done1 = label(self.done, "", 14, T.TEXT, "bold", anchor="w")
        self.done1.grid(row=0, column=1, sticky="w")
        self.done2 = label(self.done, "", 12, T.TEXT_3, anchor="w", justify="left", wraplength=460)
        self.done2.grid(row=1, column=1, sticky="w")
        self.done_btns = ctk.CTkFrame(self.done, fg_color="transparent")
        self.done_btns.grid(row=0, column=2, rowspan=2)
        self.b_new = button(self.done_btns, "Nächster Clip", self.next_clip, "ghost", icon_name="plus", size="lg")
        self.b_folder = button(self.done_btns, "Im Ordner zeigen", self.show_result, "secondary", icon_name="folder",
                               size="lg")
        self.b_play = button(self.done_btns, "Abspielen", self.play_result, "primary", icon_name="play", size="lg",
                             width=150)
        self.b_retry = button(self.done_btns, "Erneut versuchen", self.retry, "primary", icon_name="refresh",
                              size="lg")
        self.b_close = button(self.done_btns, "Schließen", self.dismiss, "secondary", size="lg")

    # ================================================================ Link & Infos
    def get_url(self):
        return self.url_entry.get().strip()

    def set_url(self, url, load_now=False):
        self.url_entry.delete(0, "end")
        if url:
            self.url_entry.insert(0, url)
        self.clip_chip.grid_remove()
        if load_now:
            self._force_load()

    def clear_url(self):
        self.set_url("")
        self.url_entry.focus_set()

    def paste(self):
        try:
            txt = self.app.clipboard_get().strip()
        except tk.TclError:
            txt = ""
        if looks_like_url(txt):
            self.app.clip_seen = txt
            self.set_url(txt, load_now=True)
        else:
            self.app.toast("In der Zwischenablage ist kein Link.", "warn")

    def offer_clip(self, url):
        """Neuer YouTube-Link in der Zwischenablage."""
        cur = self.get_url()
        if url == cur:
            return
        if not cur or not self.info:
            self.set_url(url, load_now=True)
            self.app.toast("Link aus der Zwischenablage übernommen.", "info", 2600)
        else:
            self.clip_pending = url
            short = url if len(url) < 60 else url[:57] + "…"
            self.clip_lbl.configure(text=f"Neuer Link in der Zwischenablage:  {short}")
            self.clip_chip.grid(row=1, column=0, sticky="ew", padx=18, pady=(10, 0))

    def _take_clip(self):
        if self.clip_pending:
            self.set_url(self.clip_pending, load_now=True)

    def tick(self):
        """Wird vom Hauptfenster regelmaessig aufgerufen."""
        url = self.get_url()
        now = time.time()
        if url != self.url_seen:
            self.url_seen = url
            self.url_changed_at = now
            self.info_gen += 1
            self._reset_video(loading=looks_like_url(url))
        elif self.url_changed_at and now - self.url_changed_at > 0.5:
            self.url_changed_at = 0
            if looks_like_url(url):
                self._load(url)
        self.timeline.storyboard_progress()
        changed = False
        if self.storyboard is not None and self._sb_seen != self.storyboard.loaded:
            self._sb_seen = self.storyboard.loaded
            changed = True
        if self.sb_hi is not None and self._hi_seen != self.sb_hi.loaded:
            self._hi_seen = self.sb_hi.loaded
            changed = True
        if changed:
            self._show_preview(self.hover_t)
        # HD-Standbild holen, sobald die Maus kurz still steht
        if (self.hd_want is not None and not self.hd_busy and self.frame_fmt
                and (getattr(self, "hd_fails", 0) < 3 or self.hd_cache) and time.time() >= self.hd_due):
            t = self.hd_want
            self.hd_want = None
            self.hd_busy = True
            fmt, gen = self.frame_fmt, self.info_gen
            threading.Thread(target=self._hd_worker, args=(fmt, t, gen), daemon=True).start()
        if self.cam is not None and self.cam.get("busy"):
            self._update_facecam_ui()
        self._refresh_bar()

    def _force_load(self):
        url = self.get_url()
        self.url_seen = url
        self.url_changed_at = 0
        self.info_gen += 1
        if looks_like_url(url):
            self._reset_video(loading=True)
            self._load(url)

    def _reset_video(self, loading=False):
        if self.storyboard is not None:
            self.storyboard.cancelled = True
        if self.sb_hi is not None:
            self.sb_hi.cancelled = True
        self.sb_hi = None
        self._hi_seen = -1
        self.frame_fmt = None
        self.hd_cache = {}
        self.hd_want = None
        self.hd_fails = 0
        self.cur_t = None
        self.cam = None
        self.info = None
        self.summary = None
        self.storyboard = None
        self._sb_seen = -1
        self.thumb_pil = None
        self.thumb_path = None
        self.preview_cache = {}
        self.name_dirty = False
        self.timeline.set_storyboard(None)
        self.timeline.loading = loading
        self.timeline.set_duration(0)
        self.preview.configure(image=icon("film", 38, T.TEXT_3), fg_color=T.SURFACE_2)
        self.preview_cap.place_forget()
        self.dur_badge.place_forget()
        self.yt_btn.grid_remove()
        self.retry_btn.grid_remove()
        self.linkt_btn.grid_remove()
        self.url_icon.configure(image=icon("link", 17, T.TEXT_3))
        if loading:
            self.title_lbl.configure(text="Lade Video …", text_color=T.TEXT_2)
            self.meta_lbl.configure(text="Hole Titel, Länge und Vorschaubilder.", text_color=T.TEXT_3)
            self.shimmer.start()
        else:
            self.shimmer.stop()
            url = self.get_url()
            if url:
                self.title_lbl.configure(text="Das ist kein gültiger Link", text_color=T.TEXT)
                self.meta_lbl.configure(text="Ein YouTube-Link beginnt mit https://", text_color=T.TEXT_3)
            else:
                self.title_lbl.configure(text="Noch kein Video", text_color=T.TEXT)
                self.meta_lbl.configure(text="Kopier einen YouTube-Link – Snipload erkennt ihn automatisch.",
                                        text_color=T.TEXT_3)
        if self.job is not None and not self.job.active:
            self.job = None
        self._update_name()

    def _load(self, url):
        if not tools.ytdlp_cmd():
            self.shimmer.stop()
            self.timeline.loading = False
            self.timeline.redraw()
            self.title_lbl.configure(text="yt-dlp fehlt noch", text_color=T.TEXT)
            self.meta_lbl.configure(text="Snipload braucht yt-dlp, um Videos zu laden.", text_color=T.TEXT_3)
            self.app.offer_install()
            return
        gen = self.info_gen
        threading.Thread(target=self._load_worker, args=(gen, url), daemon=True).start()

    def _load_worker(self, gen, url):
        try:
            info = tools.fetch_info(url)
        except tools.InfoError as ex:
            msg = str(ex)
            self.app.post(lambda: self._on_error(gen, msg))
            return
        except Exception as ex:
            msg = f"Unerwarteter Fehler: {ex}"
            self.app.post(lambda: self._on_error(gen, msg))
            return
        thumb_path = None
        if info.get("id"):
            thumb_path = os.path.join(thumbs_dir(), f"{info.get('extractor_key', 'x')}_{info['id']}.jpg")
        pil = tools.load_thumbnail(info, save_to=thumb_path)
        self.app.post(lambda: self._on_info(gen, info, pil, thumb_path if pil is not None else None))

    def _on_error(self, gen, msg):
        if gen != self.info_gen:
            return
        self.shimmer.stop()
        self.timeline.loading = False
        self.timeline.hint = "Mit diesem Link klappt es nicht."
        self.timeline.redraw()
        self.preview.configure(image=icon("alert", 34, T.DANGER), fg_color=T.DANGER_SOFT)
        self.title_lbl.configure(text="Video konnte nicht geladen werden", text_color=T.TEXT)
        self.meta_lbl.configure(text=msg, text_color=T.TEXT_2)
        self.retry_btn.grid(row=0, column=0)
        self.timeline.hint = "Füg oben einen Link ein – dann legst du hier Start und Ende fest."

    def _on_info(self, gen, info, pil, thumb_path):
        if gen != self.info_gen:
            return
        self.shimmer.stop()
        self.info = info
        self.summary = tools.info_summary(info)
        self.thumb_pil = pil
        self.thumb_path = thumb_path
        self.url_icon.configure(image=icon("check", 17, T.SUCCESS))
        title = info.get("title") or "Unbekannter Titel"
        self.title_lbl.configure(text=title if len(title) <= 110 else title[:108] + "…", text_color=T.TEXT)
        who = info.get("channel") or info.get("uploader") or ""
        parts = [who]
        if info.get("view_count"):
            parts.append(f"{fmt_count(info['view_count'])} Aufrufe")
        if info.get("upload_date"):
            parts.append(fmt_upload_date(info["upload_date"]))
        self.meta_lbl.configure(text="  ·  ".join(p for p in parts if p), text_color=T.TEXT_2)
        self.yt_btn.grid(row=0, column=0)
        dur = float(info.get("duration") or 0)
        if dur:
            self.dur_badge.configure(text=fmt_short(dur))
            self.dur_badge.place(relx=1.0, rely=1.0, x=-8, y=-8, anchor="se")
        self.timeline.loading = False
        self.timeline.set_duration(dur)
        sbf = tools.pick_storyboard(info) if dur else None
        if sbf:
            try:
                self.storyboard = tools.Storyboard(sbf, dur)
                self.timeline.set_storyboard(self.storyboard)
            except Exception:
                self.storyboard = None
        try:
            hi = tools.pick_preview_storyboard(info, sbf) if dur else None
            self.sb_hi = tools.Storyboard(hi, dur, lazy=True) if hi else None
        except Exception:
            self.sb_hi = None
        self.frame_fmt = tools.pick_frame_format(info) if dur else None
        # Startbereich festlegen
        t = start_from_url(self.get_url())
        if t is not None and dur and t < dur:
            self.linkt_btn.grid(row=0, column=3, padx=(6, 0))
            s, e = t, min(t + 60, dur)
        else:
            try:
                s = self.start_f.get()
                e = self.end_f.get()
            except ValueError:
                s, e = 0, 60
            if not dur:
                pass
            elif s >= dur:
                s, e = 0, min(60, dur)
            else:
                e = min(max(e, s + 1), dur)
        self._set_range(s, e)
        self._show_preview(None)
        self._update_facecam_ui(start_if_needed=True)

    # ================================================================ Vorschau
    @staticmethod
    def _hd_key(t):
        return round(t * 2) / 2  # auf halbe Sekunden genau

    def _hd_worker(self, fmt, t, gen):
        img = tools.grab_frame(fmt, self._hd_key(t))
        self.app.post(lambda: self._hd_done(gen, t, img))

    def _hd_done(self, gen, t, img):
        self.hd_busy = False
        if gen != self.info_gen:
            return
        key = self._hd_key(t)
        if img is None:
            # nach 3 Fehlschlaegen in Folge (und noch keinem Erfolg) keine HD-Bilder mehr versuchen;
            # die Facecam-Analyse nutzt frame_fmt weiter
            self.hd_fails = getattr(self, "hd_fails", 0) + 1
            return
        self.hd_fails = 0
        self.hd_cache[key] = ctk.CTkImage(rounded_image(img, PREV_W * 2, PREV_H * 2, 20), size=(PREV_W, PREV_H))
        while len(self.hd_cache) > 60:
            self.hd_cache.pop(next(iter(self.hd_cache)))
        if self.cur_t is not None and self._hd_key(self.cur_t) == key:
            self._show_preview(self.hover_t)

    def _preview_image(self, t):
        """Bestes verfuegbares Bild fuer Stelle t: HD-Standbild > grosses Storyboard > kleines > Vorschaubild."""
        if t is not None:
            hd = self.hd_cache.get(self._hd_key(t))
            if hd is not None:
                return hd, "hd"
            hi = self.sb_hi
            if hi is not None:
                if hi.has(t):
                    key = ("hi", hi.frame_index(t))
                    if key not in self.preview_cache:
                        fr = hi.frame(t, nearest=False)
                        if fr is not None:
                            self.preview_cache[key] = ctk.CTkImage(
                                rounded_image(fr, PREV_W * 2, PREV_H * 2, 20), size=(PREV_W, PREV_H))
                    if key in self.preview_cache:
                        return self.preview_cache[key], "sb"
                else:
                    hi.request(t)
            img = self._preview_image_small(t)
            if img is not None:
                return img, "sb"
        img = self._preview_image_small(None)
        return (img, "thumb") if img is not None else (None, None)

    def _preview_image_small(self, t):
        if self.storyboard is not None and t is not None:
            idx = self.storyboard.frame_index(t)
            key = ("sb", idx)
            if key in self.preview_cache:
                return self.preview_cache[key]
            # VOR dem Ausschneiden pruefen, ob das richtige Blatt schon da ist - sonst koennte ein
            # Ersatzbild (Nachbarblatt) im Zwischenspeicher landen, falls das Blatt genau jetzt fertig wird
            exact = self.storyboard.sheets.get(idx // self.storyboard.per_sheet) is not None
            fr = self.storyboard.frame(t)
            if fr is not None:
                img = rounded_image(fr, PREV_W * 2, PREV_H * 2, 20)
                ci = ctk.CTkImage(img, size=(PREV_W, PREV_H))
                if exact:
                    self.preview_cache[key] = ci
                return ci
        if self.thumb_pil is not None:
            if "thumb" not in self.preview_cache:
                img = rounded_image(self.thumb_pil, PREV_W * 2, PREV_H * 2, 20)
                self.preview_cache["thumb"] = ctk.CTkImage(img, size=(PREV_W, PREV_H))
            return self.preview_cache["thumb"]
        return None

    def _show_preview(self, t):
        """t = None: Startbild (mit Storyboard) bzw. Vorschaubild; sonst Bild an Stelle t."""
        if not self.info:
            return
        show_t = t
        if t is None and self.storyboard is not None:
            show_t = self.timeline.a if self.timeline.active == "a" else self.timeline.b
        if show_t is None and self.frame_fmt is not None:
            show_t = self.timeline.a if self.timeline.active == "a" else self.timeline.b
        img, quality = self._preview_image(show_t)
        if img is not None:
            self.preview.configure(image=img, fg_color=T.SURFACE)
        self.cur_t = show_t
        if show_t is not None and quality in ("hd", "sb"):
            self.preview_cap.configure(text=f"  {fmt_short(show_t)}" + ("  ·  HD  " if quality == "hd" else "  "))
            self.preview_cap.place(x=8, y=8, anchor="nw")
        else:
            self.preview_cap.place_forget()
        # nicht scharf? -> HD-Standbild anfordern, sobald die Maus kurz stillsteht
        if show_t is not None and quality != "hd" and self.frame_fmt is not None and \
                (getattr(self, "hd_fails", 0) < 3 or self.hd_cache):
            self.hd_want = show_t
            self.hd_due = time.time() + 0.45

    def _timeline_hover(self, t):
        self.hover_t = t
        self._show_preview(t)

    def open_on_youtube(self):
        import webbrowser
        if not self.info:
            return
        try:
            s = int(self.start_f.get())
        except ValueError:
            s = 0
        if self.info.get("extractor_key") == "Youtube" and self.info.get("id"):
            webbrowser.open(f"https://www.youtube.com/watch?v={self.info['id']}&t={s}s")
        else:
            webbrowser.open(self.info.get("webpage_url") or self.get_url())

    # ================================================================ Zeiten
    @property
    def vdur(self):
        return float((self.info or {}).get("duration") or 0)

    def _set_range(self, s, e):
        self.start_f.set(s)
        self.end_f.set(e)
        self.timeline.set_range(s, e)
        self._after_range()

    def _after_range(self):
        try:
            s, e = self.start_f.get(), self.end_f.get()
            self.len_lbl.configure(text=fmt_short(e - s) if e > s else "–",
                                   text_color=T.TEXT if e > s else T.DANGER)
        except ValueError:
            self.len_lbl.configure(text="?", text_color=T.DANGER)
        if self.job is not None and not self.job.active:
            self.job = None
        self._update_name()

    def _timeline_changed(self, a, b, which):
        if which in ("a", "mid"):
            self.start_f.set(a)
        if which in ("b", "mid"):
            self.end_f.set(b)
        self._after_range()

    def _fields_changed(self, which, soft=False):
        try:
            s = self.start_f.get()
            e = self.end_f.get()
        except ValueError:
            if not soft:
                self.len_lbl.configure(text="?", text_color=T.DANGER)
            return
        d = self.vdur
        if not soft:
            if d:
                s = min(s, max(0, d - 1))
                e = min(e, d)
            if e <= s:
                if which == "a":
                    e = min(s + 1, d) if d else s + 1
                else:
                    s = max(0, e - 1)
            self.start_f.set(s)
            self.end_f.set(e)
            self.timeline.active = which
        if d:
            self.timeline.set_range(min(s, d), min(e, d))
        self._after_range()
        if not soft:
            self._show_preview(None)

    def whole_video(self):
        if self.vdur:
            self._set_range(0, self.vdur)
            self._show_preview(None)

    def _from_link_time(self):
        t = start_from_url(self.get_url())
        if t is not None and self.vdur:
            self._set_range(t, min(t + 60, self.vdur))
            self._show_preview(None)

    def current_range(self):
        s = self.start_f.get()
        e = self.end_f.get()
        return s, e

    # ================================================================ Ausgabe
    def _apply_kind(self, save=False):
        audio = self.kind_seg.get() == "Nur Ton"
        if audio:
            self.q_title.configure(text="AUDIOFORMAT")
            self.q_menu.grid_remove()
            self.a_menu.grid(row=1, column=0, sticky="ew")
            self.aspect_seg.configure(state="disabled", selected_color=T.SURFACE_3, selected_hover_color=T.SURFACE_3)
            self.aspect_hint.configure(text="Beim reinen Ton gibt es kein Seitenformat.")
            self.fc_row.grid_forget()
        else:
            self.q_title.configure(text="QUALITÄT")
            self.a_menu.grid_remove()
            self.q_menu.grid(row=1, column=0, sticky="ew")
            self.aspect_seg.configure(state="normal", selected_color=T.ACCENT, selected_hover_color=T.ACCENT_HOVER)
            asp = _key_for(ASPECT_LABELS, self.aspect_seg.get())
            self.aspect_hint.configure(text={
                "original": "Wie auf YouTube, ohne Zuschnitt.",
                "crop916": "Hochformat 1080×1920 für Shorts, TikTok und Reels – die Bildmitte wird ausgeschnitten.",
                "blur916": "Hochformat 1080×1920: ganzes Bild in der Mitte, darüber und darunter unscharfer "
                           "Hintergrund.",
                "facecam": "Hochformat 1080×1920: Facecam oben, Gameplay darunter. Snipload sucht die Facecam "
                           "automatisch und passt die Größen an – unter „Anpassen“ machst du Facecam und "
                           "Gameplay größer oder kleiner.",
                "facecam_raw": "Nur die Facecam als eigenes Video – 1:1 in Originalgröße, pixelgenau "
                               "ausgeschnitten, ohne Rahmen. Dafür lädt Snipload das Video in bester Qualität.",
                "orig_facecam": "Zwei Dateien aus einem Download: das normale Video und die Facecam 1:1 in "
                                "Originalgröße (pixelgenau, ohne Rahmen). Lädt in bester Qualität.",
            }.get(asp, ""))
            if asp in ("facecam_raw", "orig_facecam"):
                self.q_menu.set(QUALITY_LABELS["best"])
                self.q_menu.configure(state="disabled")
            else:
                self.q_menu.configure(state="normal")
            if asp in ("crop916", "blur916", "facecam", "facecam_raw"):  # bei "Original + Facecam" schon drin
                self.also_sw.grid(row=4, column=0, sticky="w", pady=(10, 0))
            else:
                self.also_sw.grid_forget()
        if audio:
            self.also_sw.grid_forget()
            self.q_menu.configure(state="normal")
        self._update_facecam_ui(start_if_needed=True)
        self.ext_lbl.configure(text="." + (self._audio_fmt() if audio else "mp4"))
        if save:
            self._save_opts()
        self._refresh_bar(force=True)

    # ================================================================ Sitzung (fuer Neustart nach Update)
    def session_state(self):
        st = {"url": self.get_url()}
        try:
            st["start"], st["end"] = self.current_range()
        except ValueError:
            pass
        st["name"] = self.name_var.get() if self.name_dirty else None
        return st

    def restore_session(self, st):
        if st.get("url"):
            self.app.clip_seen = st["url"]
            self.set_url(st["url"], load_now=True)
        if st.get("start") is not None:
            self.start_f.set(st["start"])
        if st.get("end") is not None:
            self.end_f.set(st["end"])
        if st.get("name"):
            self.name_var.set(st["name"])
            self.name_dirty = True

    # ================================================================ Facecam
    def _facecam_mode(self):
        if self.kind_seg.get() == "Nur Ton":
            return None
        a = _key_for(ASPECT_LABELS, self.aspect_seg.get())
        if a == "orig_facecam":
            return "facecam_raw"   # gleiche Facecam-Messung, nur mit normalem Video dazu
        return a if a in ("facecam", "facecam_raw") else None

    def _facecam_selected(self):
        return self._facecam_mode() is not None

    def _also_changed(self):
        self.cfg["also_full"] = bool(self.also_var.get())
        self.app.save()
        self._refresh_bar(force=True)

    def _aspect(self):
        inf = self.info or {}
        return inf["width"] / inf["height"] if inf.get("width") and inf.get("height") else 16 / 9

    def analyze_facecam(self):
        """Holt ~10 Standbilder aus dem gewaehlten Zeitraum und sucht darin die Facecam."""
        if not self.info:
            return
        try:
            s, e = self.current_range()
        except ValueError:
            return
        vid = self.info.get("id")
        prev = self.cam or {}
        self.cam = {"vid": vid, "range": (s, e), "frames": [], "result": None, "busy": True, "progress": (0, 10),
                    "layout": prev.get("layout") if prev.get("vid") == vid else None}
        self._update_facecam_ui()
        fmt, gen = tools.pick_frame_format(self.info, max_h=None) or self.frame_fmt, self.info_gen
        if not fmt or not facecam.available():
            self.cam.update(busy=False, result={"ok": False, "message": "Für dieses Video gibt es keine "
                                                "Einzelbilder – leg die Facecam bitte von Hand fest."})
            if self.thumb_pil is not None:
                self.cam["frames"] = [(s, self.thumb_pil.convert("RGB"))]
            self._update_facecam_ui()
            return
        token = self.cam  # jede Analyse hat ihr eigenes Objekt - nur die neueste zaehlt
        threading.Thread(target=self._facecam_worker, args=(gen, token, fmt, s, e), daemon=True).start()

    def _facecam_worker(self, gen, token, fmt, s, e):
        from concurrent.futures import ThreadPoolExecutor
        n = 10
        ts = [s + (e - s) * (i + 0.5) / n for i in range(n)]
        done = [0]

        def grab(t):
            img = tools.grab_frame(fmt, t, width=None)   # Originalaufloesung fuer die 1:1-Messung
            done[0] += 1
            token["progress"] = (done[0], n)
            return (t, img)
        with ThreadPoolExecutor(max_workers=3) as ex:
            frames = list(ex.map(grab, ts))
        try:
            small = [(t, im.resize((960, max(2, int(960 * im.size[1] / im.size[0])))) if im is not None else None)
                     for t, im in frames]
            res = facecam.analyze(small, self._aspect())
            if res.get("ok") and not res.get("fullscreen"):
                good = [t for t, _ in frames if t not in set(res.get("missing") or [])]
                res["px"] = facecam.refine(frames, res["box"], good)
        except Exception as exc:
            res = {"ok": False, "message": f"Analyse fehlgeschlagen: {exc}"}
        self.app.post(lambda: self._facecam_done(gen, token, frames, res))

    def _facecam_done(self, gen, token, frames, res):
        if gen != self.info_gen or self.cam is not token:
            return  # veraltet: inzwischen anderes Video oder neuere Analyse
        self.cam.update(busy=False, frames=[(t, im) for t, im in frames if im is not None], result=res)
        lay = self.cam.get("layout")
        if res.get("ok") and not res.get("fullscreen") and not (lay and lay.get("manual")):
            px = res.get("px")
            box = facecam.px_to_norm(px) if px else res["box"]
            sizes = self.cfg.get("fc_sizes") or None
            lay = facecam.suggest_layout(box, self._aspect(), sizes,
                                         cam_bottom=bool(self.cfg.get("fc_bottom", False)))
            lay["sizes_manual"] = bool(sizes)
            self.cam["layout"] = lay
            self.cam["px"] = px
        self._update_facecam_ui()
        if res.get("ok") and not res.get("fullscreen") and res.get("coverage", 0) < 0.8:
            self.app.toast("Die Facecam ist nicht im ganzen Abschnitt zu sehen – schau es dir kurz an.", "warn", 7000,
                           action=self.open_facecam_editor, action_text="Ansehen", key="fc")

    def _update_facecam_ui(self, start_if_needed=False):
        if not hasattr(self, "fc_row"):
            return
        if not self._facecam_selected():
            self.fc_row.grid_forget()
            return
        self.fc_row.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        c = self.cam
        if not self.info:
            self.fc_icon.configure(image=icon("info", 16, T.TEXT_2))
            self.fc_text.configure(text="Sobald das Video geladen ist, sucht Snipload die Facecam.")
            self.fc_edit.configure(state="disabled")
            self.fc_recheck.pack_forget()
            return
        try:
            rng = self.current_range()
        except ValueError:
            rng = None
        if start_if_needed and (c is None or c.get("vid") != self.info.get("id")):
            self.analyze_facecam()
            return
        if c is None:
            return
        if c.get("busy"):
            i, n = c.get("progress", (0, 10))
            self.fc_icon.configure(image=icon("search", 16, T.ACCENT))
            self.fc_text.configure(text=f"Hole Bilder aus dem Abschnitt … {i}/{n}" if i < n else
                                   "Werte die Bilder aus und suche die Facecam …")
            self.fc_edit.configure(state="disabled")
            self.fc_recheck.pack_forget()
            return
        r = c.get("result") or {}
        lay = c.get("layout") or {}
        self.fc_edit.configure(state="normal")
        self.fc_edit.configure(text="Größen & Facecam …" if self._facecam_mode() == "facecam" else "Anpassen …")
        changed = rng is not None and c.get("range") and (abs(rng[0] - c["range"][0]) > 3 or
                                                           abs(rng[1] - c["range"][1]) > 3)
        if lay.get("manual"):
            ic, col, txt = "check", T.SUCCESS, "Facecam von dir festgelegt."
        elif r.get("fullscreen"):
            ic, col, txt = "info", T.TEXT_2, (r.get("message") or "") + " Tipp: Nimm lieber „Shorts 9:16“."
        elif r.get("ok") and r.get("coverage", 0) >= 1.0:
            ic, col, txt = "check", T.SUCCESS, r.get("message")
        elif r.get("ok"):
            ic, col, txt = "alert", T.WARN, r.get("message")
        else:
            ic, col, txt = "alert", T.WARN, (r.get("message") or "Keine Facecam erkannt.") + \
                " Klick auf „Anpassen“ und leg sie fest."
        if changed and not lay.get("manual"):
            txt += "  Der Zeitraum hat sich geändert – „Neu prüfen“ checkt ihn nochmal."
        self.fc_icon.configure(image=icon(ic, 16, col))
        self.fc_text.configure(text=txt)
        self.fc_recheck.pack(side="left", padx=(6, 0))
        px = c.get("px")
        if px:
            extra = f"  ·  {px['snapped']}" if px.get("snapped") else ""
            self.fc_size.configure(text=f"  {px['w']} × {px['h']} px  ·  x {px['x']}, y {px['y']}{extra}  ")
            self.fc_size.grid(row=0, column=2, rowspan=2, padx=(0, 12))
        else:
            self.fc_size.grid_forget()

    def open_facecam_editor(self):
        from .facecam_editor import FacecamEditor
        c = self.cam or {}
        if c.get("busy"):
            self.app.toast("Die Facecam wird gerade gesucht – einen Moment.", "info", 2500, key="fc")
            return
        frames = c.get("frames") or []
        if not frames:
            img = None
            if self.cur_t is not None:
                img = tools.grab_frame(self.frame_fmt, self.cur_t, width=960) if self.frame_fmt else None
            if img is None and self.thumb_pil is not None:
                img = self.thumb_pil.convert("RGB")
            if img is None:
                self.app.toast("Erst ein Video laden.", "warn")
                return
            frames = [(self.cur_t or 0, img)]

        def apply(layout, px=None):
            if self.cam is None or self.cam.get("vid") != (self.info or {}).get("id"):
                self.cam = {"vid": (self.info or {}).get("id"), "range": self.current_range(), "frames": frames,
                            "result": None, "busy": False}
            self.cam["layout"] = layout
            if px:
                px = dict(px)
                px.setdefault("snapped", None)
                self.cam["px"] = px
            self.cfg["fc_bottom"] = bool(layout.get("cam_bottom"))
            if layout.get("sizes_manual"):   # eigene Groessen fuer die naechsten Clips merken
                self.cfg["fc_sizes"] = {k: layout.get(k) for k in ("split", "gzoom", "czoom")}
            else:
                self.cfg.pop("fc_sizes", None)
            self.app.save()
            self._update_facecam_ui()
            self._refresh_bar(force=True)

        def redetect():
            if self.cam is not None and self.cam.get("layout"):
                self.cam["layout"].pop("manual", None)
            self.analyze_facecam()
        FacecamEditor(self.app, frames, c.get("result"), c.get("layout"), self._aspect(), apply, redetect,
                      mode=self._facecam_mode() or "facecam", px=c.get("px"))

    def _audio_fmt(self):
        return _key_for(AUDIO_LABELS, self.a_menu.get()) or "mp3"

    def _save_opts(self):
        c = self.cfg
        c["kind"] = "audio" if self.kind_seg.get() == "Nur Ton" else "video"
        c["quality"] = _key_for(QUALITY_LABELS, self.q_menu.get()) or "best"
        c["audio_fmt"] = self._audio_fmt()
        c["aspect"] = _key_for(ASPECT_LABELS, self.aspect_seg.get()) or "original"
        self.ext_lbl.configure(text="." + (c["audio_fmt"] if c["kind"] == "audio" else "mp4"))
        self.app.save()
        self._refresh_bar(force=True)

    def _update_name(self):
        if self.name_dirty:
            return
        if not self.info:
            self.name_var.set("")
            return
        try:
            s, e = self.current_range()
        except ValueError:
            return
        whole = s <= 0 and self.vdur and e >= self.vdur - 0.5
        self.name_var.set(build_name(self.cfg.get("name_template"), self.info, s, e, whole))

    def _name_typed(self, e=None):
        self.name_dirty = True

    def _reset_name(self):
        self.name_dirty = False
        self._update_name()

    def _show_folder(self):
        f = self.cfg.get("folder") or ""
        home = os.path.expanduser("~")
        shown = f.replace(home, "~", 1) if f.startswith(home) else f
        self.folder_lbl.configure(text=shown if len(shown) < 70 else "…" + shown[-68:])

    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.cfg.get("folder"))
        if d:
            self.cfg["folder"] = os.path.normpath(d)
            self.app.save()
            self._show_folder()
            self._refresh_bar(force=True)

    # ================================================================ Starten
    def _make_job(self):
        if not self.info:
            self.app.toast("Erst einen Link einfügen und warten, bis das Video geladen ist.", "warn")
            return None
        try:
            s, e = self.current_range()
        except ValueError:
            self.app.toast("Start oder Ende ist keine gültige Zeit (z. B. 00:03:00).", "error")
            return None
        if e <= s:
            self.app.toast("Das Ende muss nach dem Start liegen.", "error")
            return None
        if self.vdur and s >= self.vdur:
            self.app.toast(f"Der Start liegt hinter dem Videoende ({fmt_short(self.vdur)}).", "error")
            return None
        if self.vdur:
            e = min(e, self.vdur)
        folder = self.cfg.get("folder")
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            self.app.toast("Der Zielordner ist ungültig. Wähle einen anderen.", "error")
            return None
        if self._facecam_selected():
            c = self.cam
            if c and c.get("busy"):
                self.app.toast("Die Facecam wird noch erkannt – einen Moment.", "info", 3000, key="fc")
                return None
            if not c or not (c.get("layout") or {}).get("cam"):
                self.open_facecam_editor()
                return None
        if not self.app.ensure_tools():
            return None
        from ..util import safe_filename
        name = safe_filename(self.name_var.get().strip()) if self.name_var.get().strip() else \
            build_name(self.cfg.get("name_template"), self.info, s, e, False)
        kind = "audio" if self.kind_seg.get() == "Nur Ton" else "video"
        ext = self._audio_fmt() if kind == "audio" else "mp4"
        # vorhandene Datei nicht ueberschreiben, ausser sie stammt aus der Warteschlange
        name = self.app.unique_name(folder, name, ext)
        job = Job(self.get_url(), self.summary, s, e, kind,
                  _key_for(QUALITY_LABELS, self.q_menu.get()) or "best", self._audio_fmt(),
                  _key_for(ASPECT_LABELS, self.aspect_seg.get()) or "original",
                  bool(self.cfg.get("exact", True)), folder, name)
        job.thumb = self.thumb_path
        orig_plus_cam = job.aspect == "orig_facecam"
        if orig_plus_cam:  # ein Download, zwei Dateien: normales Video + Facecam 1:1
            job.aspect = "facecam_raw" if kind == "video" else "original"
        if job.aspect in ("facecam", "facecam_raw"):
            job.layout = dict(self.cam["layout"])
            if job.aspect == "facecam_raw":
                px = self.cam.get("px")
                if not px:
                    self.app.toast("Leg die Facecam bitte erst fest (Anpassen …).", "warn")
                    return None
                job.cam_px = dict(px)
                job.quality = "best"
        if job.aspect != "original" and job.kind == "video":
            job.also_full = True if orig_plus_cam else bool(self.also_var.get())
        return job

    def download(self):
        job = self._make_job()
        if job is None:
            return
        self.job = job
        self.app.queue.add(job)
        self._refresh_bar(force=True)

    def add_to_queue(self):
        job = self._make_job()
        if job is None:
            return
        self.app.queue.add(job)
        n = len(self.app.queue.pending())
        self.app.toast(f"Zur Warteschlange hinzugefügt – {n} offen.", "success", 3500,
                       action=lambda: self.app.show_page("queue"), action_text="Ansehen", key="queued")
        # naechster Abschnitt beginnt, wo der letzte aufgehoert hat
        try:
            s, e = self.current_range()
            length = e - s
            if self.vdur and e < self.vdur - 1:
                self._set_range(e, min(self.vdur, e + length))
                self._show_preview(None)
        except ValueError:
            pass

    def cancel(self):
        if self.job is not None:
            self.job.cancel()

    def retry(self):
        if self.job is None:
            return
        j = self.job
        new = Job(j.url, j.info, j.start, j.end, j.kind, j.quality, j.audio_fmt, j.aspect, j.exact, j.folder, j.name)
        new.thumb = j.thumb
        self.job = new
        self.app.queue.add(new)
        self._refresh_bar(force=True)

    def dismiss(self):
        self.job = None
        self._refresh_bar(force=True)

    def next_clip(self):
        self.job = None
        try:
            s, e = self.current_range()
            if self.vdur and e < self.vdur - 1:
                self._set_range(e, min(self.vdur, e + (e - s)))
                self._show_preview(None)
        except ValueError:
            pass
        self._refresh_bar(force=True)

    def play_result(self):
        if self.job and self.job.file and os.path.exists(self.job.file):
            open_path(self.job.file)

    def show_result(self):
        if self.job and self.job.file:
            show_in_folder(self.job.file)
        else:
            open_path(self.cfg["folder"])

    # ================================================================ Aktionsleiste aktualisieren
    def _summary_text(self):
        if not self.info:
            return "Noch kein Video geladen", "Füg oben einen YouTube-Link ein."
        try:
            s, e = self.current_range()
            rng = f"{fmt_short(s)} – {fmt_short(e)}  ·  {fmt_duration_words(max(0, e - s))}"
        except ValueError:
            rng = "Zeiten prüfen"
        audio = self.kind_seg.get() == "Nur Ton"
        if audio:
            fmt = f"Nur Ton · {self.a_menu.get()}"
        else:
            fmt = f"Video · {self.q_menu.get()}"
            asp = self.aspect_seg.get()
            if asp != "Original":
                fmt += f" · {asp}"
        if (not audio and self.aspect_seg.get() not in ("Original", "Original + Facecam")
                and self.also_var.get()):
            fmt += " + normales Video"
        folder = os.path.basename(self.cfg.get("folder") or "") or self.cfg.get("folder")
        return f"Clip {rng}", f"{fmt}  →  {folder}"

    def _refresh_bar(self, force=False):
        j = self.job
        if j is None:
            state = "idle"
        elif j.status in (Job.WAITING, Job.RUNNING):
            state = "run"
        elif j.status == Job.DONE:
            state = "done"
        else:
            state = "fail" if j.status == Job.FAILED else "idle"
            if j.status == Job.CANCELLED:
                self.job = None
        if state != self._shown_state or force:
            for f in (self.idle, self.run, self.done):
                f.grid_forget()
            {"idle": self.idle, "run": self.run, "done": self.done, "fail": self.done}[state].grid(
                row=0, column=0, sticky="ew")
            self._shown_state = state
            if state == "done":
                self.done_icon.configure(fg_color=T.SUCCESS_SOFT, image=icon("check", 20, T.SUCCESS))
                for b in (self.b_retry, self.b_close):
                    b.pack_forget()
                self.b_new.pack(side="left", padx=(0, 8))
                self.b_folder.pack(side="left", padx=(0, 8))
                self.b_play.pack(side="left")
            elif state == "fail":
                self.done_icon.configure(fg_color=T.DANGER_SOFT, image=icon("alert", 20, T.DANGER))
                for b in (self.b_new, self.b_folder, self.b_play):
                    b.pack_forget()
                self.b_close.pack(side="left", padx=(0, 8))
                self.b_retry.pack(side="left")
        if state == "idle":
            a, b = self._summary_text()
            self.sum1.configure(text=a)
            self.sum2.configure(text=b)
            ok = self.info is not None
            self.go_btn.configure(state="normal" if ok else "disabled",
                                  fg_color=T.ACCENT if ok else T.ACCENT_MUTED)
            self.queue_btn.configure(state="normal" if ok else "disabled")
        elif state == "run":
            if j.status == Job.WAITING:
                ahead = sum(1 for x in self.app.queue.jobs if x.active and x.id < j.id)
                self.run_stage.configure(text="In der Warteschlange")
                self.run_detail.configure(text=f"{ahead} Clip(s) davor – startet automatisch." if ahead else
                                          "Startet gleich …")
                self.run_pct.configure(text="")
                self.run_bar.set(0)
            else:
                self.run_stage.configure(text=j.stage)
                self.run_detail.configure(text=j.detail or j.title)
                self.run_pct.configure(text=f"{j.progress * 100:.0f} %")
                self.run_bar.configure(progress_color=T.ACCENT if j.progress > 0.005 else T.SURFACE_3)
                self.run_bar.set(j.progress)
        elif state == "done":
            name = os.path.basename(j.file) if j.file else j.name
            self.done1.configure(text="Fertig!  " + (name if len(name) <= 34 else name[:32].rstrip() + "…"))
            extra = [fmt_size(j.size), j.detail]
            self.done2.configure(text="  ·  ".join(x for x in extra if x))
        elif state == "fail":
            self.done1.configure(text="Das hat nicht geklappt")
            self.done2.configure(text=j.error or "Unbekannter Fehler.")
