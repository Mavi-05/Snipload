"""Seite "Warteschlange": alle Downloads mit Fortschritt."""
import os

import customtkinter as ctk
from PIL import Image

from .. import theme as T
from ..icons import icon, rounded_image
from ..jobs import Job
from ..util import fmt_short, fmt_size, open_path, show_in_folder
from ..widgets import badge, button, card, label, progress_bar

TH_W, TH_H = 120, 68

STATUS = {
    Job.WAITING: ("Wartet", T.SURFACE_3, T.TEXT_2),
    Job.RUNNING: ("Lädt", T.ACCENT_SOFT, T.ACCENT),
    Job.DONE: ("Fertig", T.SUCCESS_SOFT, T.SUCCESS),
    Job.FAILED: ("Fehler", T.DANGER_SOFT, T.DANGER),
    Job.CANCELLED: ("Abgebrochen", T.SURFACE_3, T.TEXT_3),
}

_thumb_cache = {}


def thumb_image(path, w=TH_W, h=TH_H):
    key = (path, w, h)
    if key in _thumb_cache:
        return _thumb_cache[key]
    img = None
    if path and os.path.exists(path):
        try:
            pil = Image.open(path)
            pil.load()
            img = ctk.CTkImage(rounded_image(pil, w * 2, h * 2, 14), size=(w, h))
        except Exception:
            img = None
    _thumb_cache[key] = img
    return img


class JobRow(ctk.CTkFrame):
    def __init__(self, master, page, job):
        super().__init__(master, fg_color=T.SURFACE, corner_radius=T.RADIUS, border_width=1, border_color=T.BORDER)
        self.page = page
        self.job = job
        self.grid_columnconfigure(1, weight=1)
        img = thumb_image(job.thumb)
        th = ctk.CTkLabel(self, text="", width=TH_W, height=TH_H, corner_radius=8,
                          fg_color=T.SURFACE if img else T.SURFACE_2,
                          image=img or icon("music" if job.kind == "audio" else "film", 22, T.TEXT_3))
        th.grid(row=0, column=0, rowspan=3, padx=(12, 14), pady=12)
        t = job.title
        label(self, t if len(t) <= 56 else t[:54].rstrip() + "…", 14, T.TEXT, "bold", anchor="w").grid(
            row=0, column=1, sticky="ew", pady=(12, 0))
        rng = "Ganzes Video" if job.whole else f"{fmt_short(job.start)} – {fmt_short(job.end)}"
        label(self, f"{rng}  ·  {job.format_label()}", 12, T.TEXT_3, anchor="w").grid(row=1, column=1, sticky="ew")
        pr = ctk.CTkFrame(self, fg_color="transparent")
        pr.grid(row=2, column=1, sticky="ew", pady=(6, 12))
        pr.grid_columnconfigure(0, weight=1)
        self.bar = progress_bar(pr, height=6)
        self.bar.grid(row=0, column=0, sticky="ew")
        self.detail = label(pr, "", 12, T.TEXT_2, anchor="w")
        self.detail.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=2, rowspan=3, padx=(12, 12))
        self.badge = badge(right, "")
        self.badge.pack(anchor="e", pady=(0, 8))
        self.btns = ctk.CTkFrame(right, fg_color="transparent")
        self.btns.pack(anchor="e")
        self._btn_state = None
        self.update_view()

    def update_view(self):
        j = self.job
        text, bg, fg = STATUS.get(j.status, STATUS[Job.WAITING])
        if j.status == Job.RUNNING:
            text = f"{j.progress * 100:.0f} %"
        self.badge.configure(text=text, fg_color=bg, text_color=fg)
        self.bar.set(j.progress if j.status != Job.WAITING else 0)
        if j.progress <= 0.005 and j.status in (Job.WAITING, Job.RUNNING, Job.CANCELLED):
            col = T.SURFACE_3  # kein roter Punkt bei 0 %
        else:
            col = {Job.DONE: T.SUCCESS, Job.FAILED: T.DANGER, Job.CANCELLED: T.TEXT_3}.get(j.status, T.ACCENT)
        self.bar.configure(progress_color=col)
        if j.status == Job.WAITING:
            ahead = sum(1 for x in self.page.app.queue.jobs if x.active and x.id < j.id)
            d = f"Wartet – {ahead} davor" if ahead else "Startet gleich …"
        elif j.status == Job.RUNNING:
            d = j.stage + (f"  ·  {j.detail}" if j.detail else "")
        elif j.status == Job.DONE:
            d = "  ·  ".join(x for x in (os.path.basename(j.file or ""), fmt_size(j.size)) if x)
        elif j.status == Job.FAILED:
            d = j.error
        else:
            d = "Abgebrochen"
        self.detail.configure(text=d if len(d) <= 80 else d[:78].rstrip() + "…",
                              text_color=T.DANGER if j.status == Job.FAILED else T.TEXT_2)
        if self._btn_state != j.status:
            self._btn_state = j.status
            for w in self.btns.winfo_children():
                w.destroy()
            if j.status == Job.DONE:
                button(self.btns, "", lambda: show_in_folder(j.file), "ghost", icon_name="folder", size="sm",
                       width=32).pack(side="left")
                button(self.btns, "", lambda: open_path(j.file) if j.file else None, "secondary", icon_name="play",
                       size="sm", width=32).pack(side="left", padx=(4, 0))
            if j.status in (Job.WAITING, Job.RUNNING):
                button(self.btns, "Abbrechen", j.cancel, "secondary", icon_name="x", size="sm").pack(side="left")
            else:
                button(self.btns, "", lambda: self.page.remove(j), "ghost", icon_name="trash", size="sm",
                       width=32).pack(side="left", padx=(4, 0))


class QueuePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=T.BG, corner_radius=0)
        self.app = app
        self.rows = {}
        self._ids = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD - 4, 10))
        head.grid_columnconfigure(0, weight=1)
        label(head, "Warteschlange", 24, T.TEXT, "bold", kind="display").grid(row=0, column=0, sticky="w")
        self.sub = label(head, "", 13, T.TEXT_3)
        self.sub.grid(row=1, column=0, sticky="w")
        self.clear_btn = button(head, "Fertige entfernen", self.clear_done, "secondary", icon_name="check")
        self.clear_btn.grid(row=0, column=1, rowspan=2)

        self.list = ctk.CTkScrollableFrame(self, fg_color=T.BG, corner_radius=0, scrollbar_button_color=T.SURFACE_3,
                                           scrollbar_button_hover_color=T.BORDER_STRONG)
        self.list.grid(row=1, column=0, sticky="nsew", padx=(T.PAD - 6, 6), pady=(0, T.PAD))
        self.list.grid_columnconfigure(0, weight=1)

        self.empty = ctk.CTkFrame(self.list, fg_color="transparent")
        ctk.CTkLabel(self.empty, text="", width=72, height=72, corner_radius=36, fg_color=T.SURFACE,
                     image=icon("queue", 30, T.TEXT_3)).pack(pady=(70, 16))
        label(self.empty, "Nichts in der Warteschlange", 17, T.TEXT, "bold", kind="display").pack()
        label(self.empty, "Mit „Zur Warteschlange“ sammelst du mehrere Clips –\nSnipload lädt sie nacheinander.",
              13, T.TEXT_3, justify="center").pack(pady=(6, 18))
        button(self.empty, "Neuen Clip erstellen", lambda: app.show_page("download"), "primary",
               icon_name="plus").pack()

    def remove(self, job):
        self.app.queue.remove(job)
        self.refresh()

    def clear_done(self):
        self.app.queue.clear_finished()
        self.refresh()

    def refresh(self):
        jobs = list(reversed(self.app.queue.jobs))  # neueste oben
        ids = [j.id for j in jobs]
        if ids != self._ids:
            self._ids = ids
            for r in self.rows.values():
                r.destroy()
            self.rows = {}
            if not jobs:
                self.empty.grid(row=0, column=0, sticky="nsew")
            else:
                self.empty.grid_forget()
                for i, j in enumerate(jobs):
                    r = JobRow(self.list, self, j)
                    r.grid(row=i, column=0, sticky="ew", padx=6, pady=(0, 10))
                    self.rows[j.id] = r
        else:
            for r in self.rows.values():
                r.update_view()
        active = sum(1 for j in jobs if j.active)
        done = sum(1 for j in jobs if j.status == Job.DONE)
        if not jobs:
            self.sub.configure(text="Clips, die Snipload nacheinander herunterlädt.")
        else:
            self.sub.configure(text=f"{active} offen  ·  {done} fertig")
        self.clear_btn.configure(state="normal" if any(not j.active for j in jobs) else "disabled")
