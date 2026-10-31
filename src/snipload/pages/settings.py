"""Seite "Einstellungen"."""
import os
import threading
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from .. import APP, VERSION
from .. import theme as T
from .. import tools
from ..icons import icon
from ..util import DEFAULTS, build_name, config_dir, open_path
from ..widgets import button, card, entry, label, switch

EXAMPLE_INFO = {"title": "Mein Lieblingsvideo", "channel": "Kanalname", "id": "abc123"}


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=T.BG, corner_radius=0)
        self.app = app
        self.cfg = app.cfg
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD - 4, 10))
        label(head, "Einstellungen", 24, T.TEXT, "bold", kind="display").grid(row=0, column=0, sticky="w")
        label(head, "Snipload so einstellen, wie du es magst.", 13, T.TEXT_3).grid(row=1, column=0, sticky="w")
        self.body = ctk.CTkScrollableFrame(self, fg_color=T.BG, corner_radius=0, scrollbar_button_color=T.SURFACE_3,
                                           scrollbar_button_hover_color=T.BORDER_STRONG)
        self.body.grid(row=1, column=0, sticky="nsew", padx=(T.PAD - 6, 6), pady=(0, T.PAD))
        self.body.grid_columnconfigure(0, weight=1)
        self._row = 0
        self._build()

    def _section(self, title, icon_name, sub=None):
        c = card(self.body)
        c.grid(row=self._row, column=0, sticky="ew", padx=6, pady=(0, T.GAP))
        self._row += 1
        c.grid_columnconfigure(0, weight=1)
        hd = ctk.CTkFrame(c, fg_color="transparent")
        hd.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 4))
        ctk.CTkLabel(hd, text="", image=icon(icon_name, 17, T.TEXT_2)).pack(side="left", padx=(0, 9))
        label(hd, title, 15, T.TEXT, "bold", kind="display").pack(side="left")
        if sub:
            label(c, sub, 12, T.TEXT_3, anchor="w", justify="left", wraplength=640).grid(row=1, column=0,
                                                                                       sticky="ew", padx=20)
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 18))
        inner.grid_columnconfigure(0, weight=1)
        return inner

    def _setting_row(self, parent, row, title, desc, widget_factory):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", pady=6)
        f.grid_columnconfigure(0, weight=1)
        label(f, title, 13, T.TEXT, anchor="w").grid(row=0, column=0, sticky="w")
        if desc:
            label(f, desc, 12, T.TEXT_3, anchor="w", justify="left", wraplength=520).grid(row=1, column=0, sticky="w")
        w = widget_factory(f)
        w.grid(row=0, column=1, rowspan=2, sticky="e", padx=(16, 0))
        return w

    def _switch(self, parent, row, key, title, desc):
        var = tk.BooleanVar(value=bool(self.cfg.get(key, DEFAULTS.get(key))))

        def changed():
            self.cfg[key] = bool(var.get())
            self.app.save()
        return self._setting_row(parent, row, title, desc, lambda f: switch(f, "", var, changed, width=48))

    def _build(self):
        # ---------------------------------------------------- Speichern
        s = self._section("Speichern", "folder")
        fr = ctk.CTkFrame(s, fg_color="transparent")
        fr.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        fr.grid_columnconfigure(0, weight=1)
        label(fr, "Zielordner", 13, T.TEXT, anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.folder_var = tk.StringVar(value=self.cfg.get("folder"))
        entry(fr, textvariable=self.folder_var, state="disabled", text_color=T.TEXT).grid(row=1, column=0,
                                                                                          sticky="ew")
        button(fr, "Ändern", self.pick_folder, "secondary").grid(row=1, column=1, padx=(8, 0))
        button(fr, "", lambda: open_path(self.cfg["folder"]), "ghost", icon_name="external").grid(row=1, column=2,
                                                                                                  padx=(4, 0))

        nm = ctk.CTkFrame(s, fg_color="transparent")
        nm.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        nm.grid_columnconfigure(0, weight=1)
        label(nm, "Dateiname-Vorlage", 13, T.TEXT, anchor="w").grid(row=0, column=0, sticky="w")
        label(nm, "Platzhalter: {titel}  {kanal}  {start}  {ende}  {datum}  {id}", 12, T.TEXT_3,
              anchor="w").grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.tpl_var = tk.StringVar(value=self.cfg.get("name_template") or DEFAULTS["name_template"])
        e = entry(nm, textvariable=self.tpl_var)
        e.grid(row=2, column=0, sticky="ew")
        button(nm, "Standard", self.reset_template, "ghost", icon_name="refresh").grid(row=2, column=1, padx=(8, 0))
        self.example = label(nm, "", 12, T.TEXT_2, anchor="w")
        self.example.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        e.bind("<KeyRelease>", lambda ev: self._tpl_changed())
        self._tpl_changed(save=False)

        # ---------------------------------------------------- Schneiden & Ablauf
        s = self._section("Schneiden & Ablauf", "scissors")
        self._switch(s, 0, "exact", "Sekundengenau schneiden",
                     "Start und Ende sitzen exakt. Ausgeschaltet geht es schneller, der Schnitt kann aber "
                     "ein paar Sekunden früher beginnen.")
        self._switch(s, 1, "sound", "Ton, wenn ein Clip fertig ist", None)
        self._switch(s, 2, "open_after", "Ordner nach dem Download öffnen",
                     "Zeigt die fertige Datei sofort im Explorer.")
        self._switch(s, 3, "watch_clipboard", "Links aus der Zwischenablage erkennen",
                     "Kopierst du einen YouTube-Link, schlägt Snipload ihn automatisch vor.")

        # ---------------------------------------------------- Werkzeuge
        s = self._section("Werkzeuge", "settings",
                          "Snipload nutzt yt-dlp zum Laden und ffmpeg zum Schneiden. Wenn Downloads plötzlich "
                          "nicht mehr klappen, hilft fast immer ein yt-dlp-Update.")
        self.t_ytdlp = self._tool_row(s, 0, "yt-dlp", "Lädt die Videos von YouTube")
        self.t_ffmpeg = self._tool_row(s, 1, "ffmpeg", "Schneidet und wandelt um")

        # ---------------------------------------------------- Ueber
        s = self._section("Über Snipload", "info")
        ab = ctk.CTkFrame(s, fg_color="transparent")
        ab.grid(row=0, column=0, sticky="ew")
        ab.grid_columnconfigure(1, weight=1)
        try:
            from PIL import Image
            from ..util import resource_path
            logo = ctk.CTkImage(Image.open(resource_path("icon.png")), size=(44, 44))
            ctk.CTkLabel(ab, text="", image=logo).grid(row=0, column=0, rowspan=2, padx=(0, 14))
        except Exception:
            pass
        label(ab, f"{APP} {VERSION}", 15, T.TEXT, "bold", kind="display", anchor="w").grid(row=0, column=1,
                                                                                         sticky="w")
        label(ab, "Clips aus YouTube-Videos – schnell, genau, ohne Umwege.", 12, T.TEXT_3, anchor="w").grid(
            row=1, column=1, sticky="w")
        button(ab, "Daten-Ordner", lambda: open_path(config_dir()), "ghost", icon_name="folder").grid(
            row=0, column=2, rowspan=2)
        label(s, "Bitte nur Inhalte herunterladen, die du verwenden darfst.", 12, T.TEXT_3, anchor="w").grid(
            row=1, column=0, sticky="w", pady=(14, 0))

    # ---------------------------------------------------- Werkzeug-Zeilen
    def _tool_row(self, parent, row, name, desc):
        f = ctk.CTkFrame(parent, fg_color=T.SURFACE_2, corner_radius=T.RADIUS_SM, border_width=1,
                         border_color=T.BORDER)
        f.grid(row=row, column=0, sticky="ew", pady=5)
        f.grid_columnconfigure(1, weight=1)
        dot = ctk.CTkFrame(f, width=10, height=10, corner_radius=5, fg_color=T.TEXT_3)
        dot.grid(row=0, column=0, rowspan=2, padx=(16, 12))
        label(f, name, 13, T.TEXT, "bold", anchor="w").grid(row=0, column=1, sticky="w", pady=(10, 0))
        st = label(f, desc, 12, T.TEXT_3, anchor="w")
        st.grid(row=1, column=1, sticky="w", pady=(0, 10))
        btn = button(f, "Prüfe …", None, "secondary", size="sm")
        btn.grid(row=0, column=2, rowspan=2, padx=12)
        btn.configure(state="disabled")
        return {"dot": dot, "status": st, "btn": btn, "desc": desc}

    def refresh_tools(self):
        st = self.app.tool_state
        y = self.t_ytdlp
        if st.get("checking"):
            return
        if st.get("busy"):
            y["btn"].configure(text=st["busy"], state="disabled")
            self.t_ffmpeg["btn"].configure(state="disabled")
            return
        ver = st.get("ytdlp")
        if ver:
            age = tools.version_age_days(ver)
            old = age is not None and age > 30
            y["dot"].configure(fg_color=T.WARN if old else T.SUCCESS)
            y["status"].configure(text=f"Version {ver}" + (f"  ·  {age} Tage alt – Update empfohlen" if old else
                                                           "  ·  aktuell genug"))
            y["btn"].configure(text="Aktualisieren", state="normal", command=self.app.update_ytdlp,
                               image=icon("refresh", 14, T.TEXT), compound="left")
        else:
            y["dot"].configure(fg_color=T.DANGER)
            y["status"].configure(text="Nicht installiert")
            y["btn"].configure(text="Installieren", state="normal", command=lambda: self.app.install(["yt-dlp"]),
                               image=icon("download", 14, T.TEXT), compound="left")
        f = self.t_ffmpeg
        fv = st.get("ffmpeg")
        if fv:
            f["dot"].configure(fg_color=T.SUCCESS)
            f["status"].configure(text=f"Version {fv}")
            f["btn"].grid_remove()
        else:
            f["dot"].configure(fg_color=T.DANGER)
            f["status"].configure(text="Nicht installiert")
            f["btn"].grid()
            f["btn"].configure(text="Installieren", state="normal", command=lambda: self.app.install(["ffmpeg"]),
                               image=icon("download", 14, T.TEXT), compound="left")

    # ---------------------------------------------------- Aktionen
    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.cfg.get("folder"))
        if d:
            self.cfg["folder"] = os.path.normpath(d)
            self.folder_var.set(self.cfg["folder"])
            self.app.save()
            self.app.pages["download"]._show_folder()

    def reset_template(self):
        self.tpl_var.set(DEFAULTS["name_template"])
        self._tpl_changed()

    def _tpl_changed(self, save=True):
        tpl = self.tpl_var.get().strip() or DEFAULTS["name_template"]
        ex = build_name(tpl, EXAMPLE_INFO, 125, 185, False)
        self.example.configure(text=f"Beispiel:  {ex}.mp4")
        if save:
            self.cfg["name_template"] = tpl
            self.app.save()
            dp = self.app.pages.get("download")
            if dp is not None:
                dp._update_name()

    def on_show(self):
        self.folder_var.set(self.cfg.get("folder"))
        self.refresh_tools()
