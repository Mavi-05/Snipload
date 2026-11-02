"""Hauptfenster: Seitenleiste, Seiten, Hintergrund-Ereignisse."""
import os
import queue
import threading
import time
from datetime import datetime
import tkinter as tk

import customtkinter as ctk
from PIL import Image

from . import APP, VERSION
from . import theme as T
from . import tools
from . import updater
from .icons import icon
from .jobs import Job, JobQueue
from .util import (clean_env, is_video_link, load_settings, looks_like_url, open_path, resource_path, save_settings,
                   show_in_folder, unique_path, win_dark_titlebar, win_no_throttle, win_flash, win_sound_done)
from .widgets import Toaster, badge, button, dialog, label
from .i18n import _

NAV = [("download", _("New clip"), "scissors"), ("queue", _("Queue"), "queue"),
       ("history", _("History"), "history"), ("settings", _("Settings"), "settings")]


class App(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=T.BG)
        T.init_fonts(self)
        self.title(APP)
        self.cfg = load_settings()
        self.events = queue.Queue()
        self.tool_state = {"checking": True}
        self._auto_ytdlp_tried = False
        self.clip_seen = None
        self._clip_next = 0
        self._handled = set()
        self.page = None
        self._apply_geometry()
        self.after(220, self._set_icon)
        self.after(60, lambda: win_dark_titlebar(self, T.SIDEBAR))

        self.queue = JobQueue(on_change=lambda job: self.events.put(("job", job)))
        self.toaster = Toaster(self)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.container = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        self.container.grid(row=0, column=1, sticky="nsew")
        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        from .pages.download import DownloadPage
        from .pages.queue import QueuePage
        from .pages.history import HistoryPage
        from .pages.settings import SettingsPage
        self.pages = {}
        self.pages["download"] = DownloadPage(self.container, self)
        self.pages["queue"] = QueuePage(self.container, self)
        self.pages["history"] = HistoryPage(self.container, self)
        self.pages["settings"] = SettingsPage(self.container, self)
        self.show_page("download")

        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_configure)
        self.check_tools()
        self.after(500, self._check_clipboard)
        self.upd = {"state": None, "info": None, "progress": 0.0, "error": None}
        updater.cleanup_leftovers()
        self.after(600, self._after_update_start)
        # Nur fuer automatische Tests: einmal die Sprache wechseln und neu starten
        marker = os.environ.get("SNIPLOAD_TEST_RESTART")
        if marker and not os.path.exists(marker):
            open(marker, "w").close()
            self.cfg["language"] = os.environ.get("SNIPLOAD_TEST_LANG", "ja")
            self.after(4000, self.restart_app)
        self.after(4000, lambda: self.check_update(silent=True))
        self._tick()

    # ================================================================ Fenster
    def _set_icon(self):
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

    def _apply_geometry(self):
        scale = ctk.ScalingTracker.get_window_scaling(self) or 1.0
        sw = self.winfo_screenwidth() / scale
        sh = self.winfo_screenheight() / scale
        w, h = min(1180, int(sw * 0.92)), min(820, int(sh * 0.86))
        g = self.cfg.get("geometry")
        if isinstance(g, list) and len(g) == 2:
            w, h = max(980, min(g[0], int(sw))), max(640, min(g[1], int(sh)))
        x, y = int((sw - w) / 2), int(max(0, (sh - h) / 2 - 20))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(980, 620)

    def _on_configure(self, e):
        if e.widget is self:
            s = ctk.ScalingTracker.get_window_scaling(self) or 1.0
            self._geom = [int(self.winfo_width() / s), int(self.winfo_height() / s)]

    def _on_close(self):
        active = [j for j in self.queue.jobs if j.active]
        if active:
            if not dialog(self, _("Quit Snipload?"),
                          _("{count} download(s) are still running. Quitting will cancel them.").format(count=len(active)),
                          _("Quit"), _("Keep downloading"), kind="warn", danger=True):
                return
            for j in active:
                j.cancel()
        if getattr(self, "_geom", None) and self.state() == "normal":
            self.cfg["geometry"] = self._geom
        self.save()
        if self.upd.get("state") == "ready":  # fertiges Update beim Schliessen einspielen
            try:
                updater.install(self.upd["path"], restart=False)
            except Exception:
                pass
        self.destroy()

    # ================================================================ Seitenleiste
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=T.SIDEBAR, corner_radius=0, width=236)
        sb.grid(row=0, column=0, sticky="nsw")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(2, weight=1)
        ctk.CTkFrame(self, fg_color=T.BORDER, width=1, corner_radius=0).grid(row=0, column=0, sticky="nse")

        logo = ctk.CTkFrame(sb, fg_color="transparent")
        logo.grid(row=0, column=0, sticky="ew", padx=20, pady=(22, 26))
        try:
            img = ctk.CTkImage(Image.open(resource_path("icon.png")), size=(34, 34))
            ctk.CTkLabel(logo, text="", image=img).pack(side="left", padx=(0, 11))
        except Exception:
            pass
        tf = ctk.CTkFrame(logo, fg_color="transparent")
        tf.pack(side="left")
        label(tf, APP, 19, T.TEXT, "bold", kind="display").pack(anchor="w")
        label(tf, _("Version {version}").format(version=updater.current_version()), 11, T.TEXT_3).pack(anchor="w")

        nav = ctk.CTkFrame(sb, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="new", padx=12)
        nav.grid_columnconfigure(0, weight=1)
        label(nav, _("MENU"), 10, T.TEXT_3, "bold").grid(row=0, column=0, sticky="w", padx=12, pady=(0, 6))
        self.nav_btns = {}
        for i, (key, text, ic) in enumerate(NAV, start=1):
            b = ctk.CTkButton(nav, text=text, anchor="w", height=42, corner_radius=T.RADIUS_SM, fg_color="transparent",
                              hover_color=T.SURFACE_2, text_color=T.TEXT_2, font=T.F(14),
                              image=icon(ic, 18, T.TEXT_2), compound="left", command=lambda k=key: self.show_page(k))
            b.grid(row=i, column=0, sticky="ew", pady=2)
            self.nav_btns[key] = (b, ic)
        self.q_badge = badge(self.nav_btns["queue"][0], "", fg=T.ACCENT, color="#ffffff")

        # Update-Hinweis (nur sichtbar, wenn es eine neue Version gibt)
        self.upd_btn = ctk.CTkButton(sb, text="", height=40, corner_radius=T.RADIUS_SM, fg_color=T.ACCENT,
                                     hover_color=T.ACCENT_HOVER, text_color="#ffffff", font=T.F(13, "bold"),
                                     image=icon("download", 16, "#ffffff"), compound="left",
                                     command=self.update_clicked)
        self.upd_bar = ctk.CTkProgressBar(sb, height=4, corner_radius=2, fg_color=T.SURFACE_3,
                                          progress_color=T.ACCENT)
        self._sb = sb

        foot = ctk.CTkFrame(sb, fg_color=T.SURFACE, corner_radius=T.RADIUS, border_width=1, border_color=T.BORDER)
        foot.grid(row=5, column=0, sticky="ew", padx=14, pady=(10, 16))
        foot.grid_columnconfigure(1, weight=1)
        self.tool_dot = ctk.CTkFrame(foot, width=10, height=10, corner_radius=5, fg_color=T.TEXT_3)
        self.tool_dot.grid(row=0, column=0, rowspan=2, padx=(14, 10), pady=12)
        self.tool_l1 = label(foot, _("Checking tools …"), 12, T.TEXT, "bold", anchor="w")
        self.tool_l1.grid(row=0, column=1, sticky="sw", pady=(10, 0))
        self.tool_l2 = label(foot, "", 11, T.TEXT_3, anchor="w")
        self.tool_l2.grid(row=1, column=1, sticky="nw", pady=(0, 10))
        for w in (foot, self.tool_l1, self.tool_l2, self.tool_dot):
            w.bind("<Button-1>", lambda e: self.show_page("settings"))
            w.configure(cursor="hand2")

    def show_page(self, key):
        if key == self.page:
            return
        for k, p in self.pages.items():
            if k == key:
                p.grid(row=0, column=0, sticky="nsew")
            else:
                p.grid_forget()
        for k, (b, ic) in self.nav_btns.items():
            on = k == key
            b.configure(fg_color=T.ACCENT_SOFT if on else "transparent",
                        hover_color=T.ACCENT_SOFT if on else T.SURFACE_2,
                        text_color=T.TEXT if on else T.TEXT_2,
                        font=T.F(14, "bold" if on else "normal"),
                        image=icon(ic, 18, T.ACCENT if on else T.TEXT_2))
        self.page = key
        p = self.pages[key]
        if key == "queue":
            p.refresh()
        elif key == "history":
            p.refresh(force=True)
        elif key == "settings":
            p.on_show()

    def _bind_keys(self):
        def paste(e):
            w = self.focus_get()
            if isinstance(w, (tk.Entry, ctk.CTkEntry)) or (w is not None and w.winfo_class() == "Entry"):
                return  # normales Einfuegen in Textfelder
            self.show_page("download")
            self.pages["download"].paste()
            return "break"
        self.bind_all("<Control-v>", paste, add="+")
        self.bind_all("<Control-V>", paste, add="+")
        self.bind_all("<Control-Return>", lambda e: (self.pages["download"].download()
                                                     if self.page == "download" else None))
        for i, (key, _x, _x) in enumerate(NAV, start=1):
            self.bind_all(f"<Control-Key-{i}>", lambda e, k=key: self.show_page(k))

    # ================================================================ Hilfen fuer die Seiten
    def save(self):
        save_settings(self.cfg)

    def post(self, fn):
        """Funktion aus einem Hintergrund-Thread im Hauptthread ausfuehren."""
        self.events.put(("call", fn))

    def toast(self, text, kind="info", ms=3800, action=None, action_text=None, key=None):
        return self.toaster.show(text, kind, ms, action, action_text, key)

    def unique_name(self, folder, name, ext):
        """Dateiname, der weder auf der Platte noch in der Warteschlange schon vergeben ist."""
        taken = {(j.folder, f"{j.name}.{j.ext}".lower()) for j in self.queue.jobs if j.active}
        cand, i = name, 2
        while os.path.exists(os.path.join(folder, f"{cand}.{ext}")) or (folder, f"{cand}.{ext}".lower()) in taken:
            cand = f"{name} ({i})"
            i += 1
        return cand

    def reuse(self, h):
        """Clip aus dem Verlauf wieder in die Bearbeitung laden."""
        dp = self.pages["download"]
        self.show_page("download")
        dp.set_url(h.get("url", ""), load_now=True)
        dp.start_f.set(h.get("start") or 0)
        if h.get("end") is not None:
            dp.end_f.set(h["end"])
        self.clip_seen = h.get("url")
        self.toast(_("Link and times taken from your history."), "info", 2800)

    # ================================================================ Werkzeuge
    def check_tools(self):
        self.tool_state = {"checking": True}
        self._render_tool_status()

        def work():
            st = {"ytdlp": tools.ytdlp_version(), "ffmpeg": tools.ffmpeg_version()}
            self.post(lambda: self._tools_checked(st))
        threading.Thread(target=work, daemon=True).start()

    def _tools_checked(self, st):
        self.tool_state = st
        self._render_tool_status()
        self.pages["settings"].refresh_tools()
        age = tools.version_age_days(st.get("ytdlp") or "")
        # YouTube aendert staendig etwas - alte yt-dlp-Versionen fuehren zu "HTTP 403". Darum haelt Snipload
        # yt-dlp selbst aktuell: ab 7 Tagen Alter still im Hintergrund (hoechstens einmal pro Tag).
        if st.get("ytdlp") and age is not None and age > 7 and not self._auto_ytdlp_tried:
            last = self.cfg.get("_ytdlp_auto_at") or 0
            if time.time() - last > 20 * 3600 and not any(j.status == Job.RUNNING for j in self.queue.jobs):
                self._auto_ytdlp_tried = True
                self.cfg["_ytdlp_auto_at"] = time.time()
                self.save()
                self.update_ytdlp(silent=True)

    def _render_tool_status(self):
        st = self.tool_state
        if st.get("checking"):
            self.tool_dot.configure(fg_color=T.TEXT_3)
            self.tool_l1.configure(text=_("Checking tools …"))
            self.tool_l2.configure(text="")
            return
        if st.get("busy"):
            self.tool_dot.configure(fg_color=T.WARN)
            self.tool_l1.configure(text=st["busy"])
            self.tool_l2.configure(text=_("One moment please"))
            return
        y, f = st.get("ytdlp"), st.get("ffmpeg")
        if not y or not f:
            missing = [n for n, v in (("yt-dlp", y), ("ffmpeg", f)) if not v]
            self.tool_dot.configure(fg_color=T.DANGER)
            self.tool_l1.configure(text=_("{names} missing").format(names=" & ".join(missing)))
            self.tool_l2.configure(text=_("Click here to install"))
            return
        age = tools.version_age_days(y)
        if age is not None and age > 30:
            self.tool_dot.configure(fg_color=T.WARN)
            self.tool_l1.configure(text=_("Update recommended"))
            self.tool_l2.configure(text=f"yt-dlp {y}")
        else:
            self.tool_dot.configure(fg_color=T.SUCCESS)
            self.tool_l1.configure(text=_("Ready"))
            self.tool_l2.configure(text=f"yt-dlp {y}")

    def ensure_tools(self):
        """Vor dem Download: fehlt etwas, Installation anbieten. True = alles da."""
        missing = [n for n in ("yt-dlp", "ffmpeg") if not tools.find_tool(n) and not
                   (n == "yt-dlp" and tools.ytdlp_cmd())]
        if not missing:
            return True
        self.offer_install(missing)
        return False

    def offer_install(self, missing=None):
        if missing is None:
            missing = [n for n in ("yt-dlp", "ffmpeg") if not tools.find_tool(n)]
        if not missing or self.tool_state.get("busy"):
            return
        names = " & ".join(missing)
        if dialog(self, _("Install {names}?").format(names=names),
                  _("Snipload needs {names}. Install it automatically now? This takes 1–2 minutes.").format(names=names),
                  _("Install"), _("Later"), kind="download"):
            self.install(missing)

    def install(self, names):
        self.tool_state = {"busy": _("Installing {names} …").format(names=' & '.join(names))}
        self._render_tool_status()
        self.pages["settings"].refresh_tools()

        def prog(name, frac):
            text = _("Downloading {names} … {value:.0f} %").format(names=name, value=frac * 100)
            self.post(lambda: self._install_progress(text))

        def work():
            failed = tools.install(names, prog)
            self.post(lambda: self._installed(failed))
        threading.Thread(target=work, daemon=True).start()

    def _install_progress(self, text):
        if self.tool_state.get("busy"):
            self.tool_state["busy"] = text
            self._render_tool_status()

    def _installed(self, failed):
        if failed:
            self.toast(_("Couldn't download {names}. Check your internet connection and try again.").format(
                names=" & ".join(failed)), "error", 10000)
        else:
            self.toast(_("Installed – you're ready to go."), "success")
            dp = self.pages["download"]
            if dp.get_url() and not dp.info:
                dp._force_load()
        self.check_tools()

    def update_ytdlp(self, silent=False):
        if self.tool_state.get("busy"):
            return
        if any(j.status == Job.RUNNING for j in self.queue.jobs):
            if not silent:
                self.toast(_("Wait until the running download has finished."), "warn")
            return
        self.tool_state = {"busy": _("Updating yt-dlp …")}
        self._render_tool_status()
        self.pages["settings"].refresh_tools()

        def work():
            before, after = tools.update_ytdlp()
            self.post(lambda: self._updated(before, after, silent))
        threading.Thread(target=work, daemon=True).start()

    def _updated(self, before, after, silent=False):
        if silent:
            if after and before and after != before:
                self.toast(_("yt-dlp updated: {before} → {after}").format(before=before, after=after), "success")
            self.check_tools()
            return
        if after and before and after != before:
            self.toast(_("yt-dlp updated: {before} → {after}").format(before=before, after=after), "success")
        elif after:
            self.toast(_("yt-dlp is already the latest version ({after}).").format(after=after), "info")
        else:
            self.toast(_("The yt-dlp update didn't work. Check your internet connection."), "error", 8000)
        self.check_tools()

    # ================================================================ Snipload-Updates
    def check_update(self, silent=False):
        """Fragt GitHub nach einer neuen Version. silent: keine Meldung, wenn alles aktuell ist."""
        st = self.upd.get("state")
        if st in ("checking", "downloading", "ready"):
            return
        self.upd.update(state="checking", error=None)
        self._render_update()

        def work():
            try:
                info = updater.check()
                self.post(lambda: self._update_checked(info, None, silent))
            except updater.UpdateError as ex:
                msg = str(ex)
                self.post(lambda: self._update_checked(None, msg, silent))
        threading.Thread(target=work, daemon=True).start()
        self.after(6 * 3600 * 1000, lambda: self.check_update(silent=True))  # alle 6 Stunden

    def _update_checked(self, info, error, silent):
        self.upd["checked_at"] = datetime.now().strftime("%H:%M")
        if error:
            self.upd.update(state="error", error=error, info=None)
            if not silent:
                self.toast(error, "warn", 6000)
        elif info is None:
            self.upd.update(state="current", info=None)
            if not silent:
                self.toast(_("Snipload is up to date (version {version}).").format(version=updater.current_version()), "success")
        else:
            self.upd.update(state="available", info=info)
            if updater.can_self_update() and self.cfg.get("auto_update", True):
                self.download_update()
            else:
                self.toast(_("New version {version} available.").format(version=info['version']), "info", 8000,
                           action=self.update_clicked, action_text=_("View"), key="update")
        self._render_update()

    def download_update(self):
        info = self.upd.get("info")
        if not info or self.upd.get("state") in ("downloading", "ready"):
            return
        if not updater.can_self_update():
            import webbrowser
            webbrowser.open(info.get("page") or f"https://github.com/{updater.REPO}/releases/latest")
            return
        self.upd.update(state="downloading", progress=0.0)
        self._render_update()

        def prog(f):
            self.upd["progress"] = f

        def work():
            try:
                path = updater.download(info, prog)
                self.post(lambda: self._update_downloaded(path, None))
            except updater.UpdateError as ex:
                msg = str(ex)
                self.post(lambda: self._update_downloaded(None, msg))
        threading.Thread(target=work, daemon=True).start()

    def _update_downloaded(self, path, error):
        if error:
            self.upd.update(state="available", error=error)
            self.toast(error, "error", 7000)
        else:
            self.upd.update(state="ready", path=path)
            if self.cfg.get("auto_update", True):
                self._auto_restart(first=True)
            else:
                v = self.upd["info"]["version"]
                self.toast(_("Version {v} is ready.").format(v=v), "success", 10000, action=self.restart_for_update,
                           action_text=_("Restart"), key="update")
        self._render_update()

    # ---- automatischer Neustart: 5 s Countdown, wartet auf laufende Downloads, "Spaeter" moeglich
    def _auto_restart(self, first=False):
        if self.upd.get("state") != "ready" or self.upd.get("postponed"):
            return
        v = self.upd["info"]["version"]
        if any(j.active for j in self.queue.jobs):
            if not self.upd.get("waiting"):
                self.upd["waiting"] = True
                self.toast(_("Update {v} is ready – Snipload will restart as soon as your downloads are finished.").format(v=v),
                           "info", 7000, action=self._postpone_restart, action_text=_("Later"), key="update")
            self._render_update()
            self.after(2000, self._auto_restart)
            return
        self.upd["waiting"] = False
        if first or self.upd.get("countdown") is None:
            self.upd["countdown"] = 5
            self.toast(_("Snipload is updating to {v} and will reopen in a moment.").format(v=v), "success", 6000,
                       action=self._postpone_restart, action_text=_("Later"), key="update")
        n = self.upd["countdown"]
        self._render_update()
        if n <= 0:
            self.restart_for_update(confirm=False)
            return
        self.upd["countdown"] = n - 1
        self.after(1000, self._auto_restart)

    def _after_update_start(self):
        """Nach einem Update-Neustart: Hinweis zeigen und die Sitzung wiederherstellen."""
        v = self.cfg.pop("_updated_to", None)
        resume = self.cfg.pop("_resume", None)
        if v is None and resume is None:
            return
        self.save()
        if resume:
            try:
                self.pages["download"].restore_session(resume)
                if resume.get("page") in self.pages:
                    self.show_page(resume["page"])
            except Exception:
                pass
        if v:
            if v == updater.current_version():
                self.toast(_("Snipload has been updated to version {v}.").format(v=v), "success", 6000, key="update")
            else:
                self.toast(_("The update to {v} didn't work – Snipload keeps running with {version}.").format(v=v, version=updater.current_version()), "warn", 8000, key="update")

    def _postpone_restart(self):
        self.upd["postponed"] = True
        self.upd["countdown"] = None
        self.toast(_("Okay – the update will be installed the next time you close Snipload."), "info", 4000, key="update")
        self._render_update()

    def update_clicked(self):
        st = self.upd.get("state")
        info = self.upd.get("info") or {}
        if st == "ready":
            self.restart_for_update()
        elif st == "available":
            notes = _("\n\nWhat's new: {notes}").format(notes=info['notes']) if info.get("notes") else ""
            if dialog(self, _("Snipload {get} is here").format(get=info.get('version')),
                      _("You have version {version}.{notes}\n\nThe update downloads in the background – you can keep working.").format(version=updater.current_version(), notes=notes), _("Update now"), _("Later"),
                      kind="download"):
                self.download_update()
        elif st == "downloading":
            self.toast(_("The update is downloading …"), "info", 2500, key="update")
        else:
            self.check_update(silent=False)

    def restart_for_update(self, confirm=True):
        if self.upd.get("state") != "ready":
            return
        active = [j for j in self.queue.jobs if j.active]
        if active and confirm and not dialog(self, _("Restart now?"),
                                 _("{count} download(s) are still running. They will be cancelled.").format(count=len(active)),
                                 _("Restart"), _("Cancel"), kind="warn", danger=True):
            return
        for j in active:
            j.cancel()
        try:
            updater.install(self.upd["path"], restart=True)
        except Exception as ex:
            self.toast(_("Couldn't start the update: {ex}").format(ex=ex), "error", 8000)
            return
        if getattr(self, "_geom", None) and self.state() == "normal":
            self.cfg["geometry"] = self._geom
        # Sitzung merken: nach dem Neustart sind Link, Zeiten und Seite wieder da
        try:
            self.cfg["_resume"] = dict(self.pages["download"].session_state(), page=self.page)
        except Exception:
            pass
        self.cfg["_updated_to"] = self.upd["info"]["version"]
        self.save()
        self.destroy()

    def restart_app(self):
        """Snipload neu starten (z. B. nach einem Sprachwechsel) - Link, Zeiten und Seite bleiben erhalten."""
        import subprocess
        import sys
        active = [j for j in self.queue.jobs if j.active]
        if active and not dialog(self, _("Restart now?"),
                                 _("{count} download(s) are still running. They will be cancelled.").format(count=len(active)),
                                 _("Restart"), _("Cancel"), kind="warn", danger=True):
            return
        for j in active:
            j.cancel()
        if getattr(sys, "frozen", False):
            cmd = [sys.executable]
        else:
            cmd = [sys.executable, os.path.abspath(sys.argv[0])]
        flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
        if getattr(self, "_geom", None) and self.state() == "normal":
            self.cfg["geometry"] = self._geom
        try:
            self.cfg["_resume"] = dict(self.pages["download"].session_state(), page=self.page)
        except Exception:
            pass
        self.save()
        try:
            # saubere Umgebung: sonst haelt sich die neue exe fuer einen Teil der alten (PyInstaller)
            subprocess.Popen(cmd, creationflags=flags, close_fds=True, env=clean_env(),
                             cwd=os.path.dirname(cmd[-1]) or None,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as ex:
            self.toast(_("Couldn't restart: {ex}").format(ex=ex), "error", 8000)
            return
        self.destroy()

    def _fit_button_text(self, b, max_size=13, min_size=10):
        """Schrift verkleinern, bis der Text in den Knopf passt (lange Sprachen wie Russisch/Franzoesisch);
        reicht das nicht, wird der Text gekuerzt."""
        import tkinter.font as tkfont
        try:
            scale = ctk.ScalingTracker.get_widget_scaling(b) or 1.0
            avail = (236 - 2 * 14 - 26 - 18) * scale    # Seitenleiste - Rand - Symbol - Innenabstand
            full = b.cget("text")
            for size in range(max_size, min_size - 1, -1):
                f = tkfont.Font(family=T.family(), size=-int(round(size * scale)), weight="bold")
                if f.measure(full) <= avail:
                    b.configure(font=T.F(size, "bold"))
                    return
            b.configure(font=T.F(min_size, "bold"))
            f = tkfont.Font(family=T.family(), size=-int(round(min_size * scale)), weight="bold")
            txt = full
            while txt and f.measure(txt + "…") > avail:
                txt = txt[:-1]
            b.configure(text=txt.rstrip() + "…")
        except Exception:
            pass

    def _render_update(self):
        st = self.upd.get("state")
        info = self.upd.get("info") or {}
        b, bar = self.upd_btn, self.upd_bar
        if st in ("available", "downloading", "ready"):
            b.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 0))
            if st == "available":
                b.configure(text=_("Update {get} available").format(get=info.get('version')), state="normal",
                            image=icon("download", 16, "#ffffff"))
                bar.grid_forget()
            elif st == "downloading":
                b.configure(text=_("Downloading update … {value:.0f} %").format(value=self.upd.get('progress', 0) * 100),
                            image=icon("download", 16, "#ffffff"))
                bar.grid(row=4, column=0, sticky="ew", padx=20, pady=(6, 0))
                bar.set(self.upd.get("progress", 0))
            else:
                cd = self.upd.get("countdown")
                if self.upd.get("waiting"):
                    txt = _("Restart after downloads")
                elif cd is not None and not self.upd.get("postponed"):
                    txt = _("Restarting in {max} s – now?").format(max=max(0, cd))
                else:
                    txt = _("Restart for {get}").format(get=info.get('version'))
                b.configure(text=txt, state="normal", image=icon("refresh", 16, "#ffffff"))
                bar.grid_forget()
            self._fit_button_text(b)
        else:
            b.grid_forget()
            bar.grid_forget()
        sp = self.pages.get("settings") if hasattr(self, "pages") else None
        if sp is not None:
            sp.refresh_update()

    # ================================================================ Zwischenablage
    def _check_clipboard(self):
        if not self.cfg.get("watch_clipboard", True):
            return
        try:
            txt = self.clipboard_get().strip()
        except tk.TclError:
            return
        if txt and txt != self.clip_seen and is_video_link(txt) and looks_like_url(txt):
            self.clip_seen = txt
            self.pages["download"].offer_clip(txt)

    # ================================================================ Jobs
    def _on_job(self, job):
        if job is None:
            return
        if job.hint == "slow" and not getattr(job, "_hint_shown", False) and not self.cfg.get("_slow_hint_off"):
            job._hint_shown = True
            self.toast(_("This clip is cut frame-accurately, so the video is re-encoded – on this PC that's slow. "
                         "Turn off “Frame-accurate cuts” in the settings for much faster downloads."), "info", 12000,
                       action=lambda: self.show_page("settings"), action_text=_("Settings"), key="slow")
        if job.status in (Job.DONE, Job.FAILED) and job.id not in self._handled:
            self._handled.add(job.id)
            if job.status == Job.DONE:
                self._add_history(job)
                name = os.path.basename(job.file) if job.file else job.name
                if self.cfg.get("sound", True):
                    win_sound_done()
                win_flash(self)
                if self.cfg.get("open_after") and job.file:
                    show_in_folder(job.file)
                if not (self.page == "download" and self.pages["download"].job is job):
                    t = job.title if len(job.title) <= 44 else job.title[:42].rstrip() + "…"
                    self.toast(_("Done: {t}").format(t=t), "success", 5000, action=lambda: open_path(job.file),
                               action_text=_("Play"))
            else:
                if not (self.page == "download" and self.pages["download"].job is job):
                    self.toast(_("Failed: {error}").format(error=job.error), "error", 7000)

    def _add_history(self, job):
        entry = {
            "title": job.title, "channel": (job.info or {}).get("channel") or "",
            "file": job.file or "", "url": job.url, "id": (job.info or {}).get("id"),
            "start": 0 if job.whole else job.start, "end": None if job.whole else job.end,
            "kind": job.kind, "format": job.format_label(), "size": job.size, "thumb": job.thumb,
            "date": datetime.now().strftime("%d.%m.%Y %H:%M"), "ts": time.time(),
        }
        hist = [h for h in self.cfg.get("history", []) if h.get("file") != entry["file"] or not entry["file"]]
        self.cfg["history"] = [entry] + hist[:199]
        self.save()

    # ================================================================ Takt
    def _tick(self):
        try:
            for _x in range(200):
                kind, payload = self.events.get_nowait()
                if kind == "call":
                    try:
                        payload()
                    except Exception as ex:
                        print("Fehler im Ereignis:", ex)
                elif kind == "job":
                    self._on_job(payload)
        except queue.Empty:
            pass
        try:
            self.pages["download"].tick()
            if self.page == "queue":
                self.pages["queue"].refresh()
            elif self.page == "history":
                self.pages["history"].tick()
            n = len(self.queue.pending())
            b = self.q_badge
            if n:
                b.configure(text=str(n))
                b.place(relx=1.0, rely=0.5, x=-12, anchor="e")
            else:
                b.place_forget()
            if self.upd.get("state") == "downloading":
                self._render_update()
            now = time.time()
            if now >= self._clip_next:
                self._clip_next = now + 1.0
                self._check_clipboard()
        except Exception as ex:
            print("Fehler im Takt:", ex)
        self.after(90, self._tick)


def main():
    if os.name == "nt":
        try:  # eigene Taskleisten-Gruppe mit eigenem Icon
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Snipload.App")
        except Exception:
            pass
    win_no_throttle()   # im Hintergrund nicht vom Windows-Effizienzmodus bremsen lassen
    app = App()
    app.mainloop()
