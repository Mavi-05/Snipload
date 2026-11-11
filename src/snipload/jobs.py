"""Downloads: Auftraege (Jobs) und die Warteschlange, die sie nacheinander abarbeitet."""
import collections
import itertools
import os
import re
import subprocess
import threading
import tempfile
import time

from . import tools
from .util import NO_WINDOW, IS_WIN, clean_env, fmt_ytdlp, win_no_throttle, win_unthrottle_tree
from .i18n import _

PCT_RE = re.compile(r"\[PCT\]\s*([\d.]+)%")
TIME_RE = re.compile(r"time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
SPEED_RE = re.compile(r"speed=\s*([\d.]+)x")
FMT_RE = re.compile(r"Downloading \d+ format\(s\):\s*(\S+)")
_YTDLP_LOCK = threading.Lock()

QUALITY_LABELS = {"best": _("Best quality"), "2160": "2160p (4K)", "1440": "1440p", "1080": "1080p",
                  "720": "720p", "480": "480p"}
ASPECT_LABELS = {"original": _("Original"), "orig_facecam": _("Original + Facecam"), "facecam_raw": _("Facecam only"),
                 "crop916": _("Shorts 9:16"), "blur916": _("Shorts + blur"), "facecam": _("Facecam split")}
AUDIO_LABELS = {"mp3": "MP3", "m4a": "M4A", "wav": "WAV"}

_ids = itertools.count(1)


class Job:
    WAITING, RUNNING, DONE, FAILED, CANCELLED = "waiting", "running", "done", "failed", "cancelled"

    def __init__(self, url, info, start, end, kind, quality, audio_fmt, aspect, exact, folder, name, spec=None):
        self.id = next(_ids)
        self.url = url
        self.info = info                # gekuerzte Video-Infos (tools.info_summary)
        self.start = float(start)
        self.end = None if end is None else float(end)
        self.kind = kind                # video | audio
        self.quality = quality
        self.audio_fmt = audio_fmt
        self.aspect = aspect if kind == "video" else "original"
        self.exact = exact
        self.folder = folder
        self.name = name                # Dateiname ohne Endung
        self.status = Job.WAITING
        self.progress = 0.0
        self.stage = _("Waiting…")
        self.detail = ""
        self.error = ""
        self.file = None
        self.size = 0
        self.started_at = None
        self.finished_at = None
        self.thumb = None               # Pfad zum gespeicherten Vorschaubild
        self.layout = None              # Facecam-Split: {"cam": (x,y,w,h), "split", "gx", "cam_bottom"}
        self.cam_px = None              # Nur Facecam: {"x","y","w","h","ref_w","ref_h"} in Pixeln
        self.also_full = False          # Nur Facecam: zusaetzlich das normale Video behalten
        self.extra_files = []
        self.hint = None                # z. B. "slow": Hinweis an die App (einmalig)
        self.spec = spec or {}          # Extras: captions, chat, upscale, speed, fades, eq, size_mb, gif, ...
        self.sent_to = None             # an welches Schnittprogramm uebergeben
        self._cancel = False
        self._proc = None

    # -------------------------------------------------- Beschreibung
    @property
    def duration(self):
        vdur = (self.info or {}).get("duration") or 0
        end = self.end if self.end is not None else vdur
        return max(0.0, (end or 0) - self.start) if end else None

    @property
    def whole(self):
        vdur = (self.info or {}).get("duration") or 0
        return self.start <= 0 and (self.end is None or (vdur and self.end >= vdur - 0.5))

    @property
    def ext(self):
        return self.audio_fmt if self.kind == "audio" else "mp4"

    @property
    def title(self):
        return (self.info or {}).get("title") or self.name

    def format_label(self):
        if self.kind == "audio":
            return AUDIO_LABELS.get(self.audio_fmt, self.audio_fmt.upper())
        if (self.spec or {}).get("gif"):
            return "GIF"
        q = _("Best") if self.quality == "best" else f"{self.quality}p"
        if self.aspect == "facecam_raw" and self.cam_px:
            size = f"{self.cam_px['w']}×{self.cam_px['h']}"
            return _("Original + Facecam {size}").format(size=size) if self.also_full else _("Facecam 1:1 · {size}").format(size=size)
        if self.also_full and self.aspect != "original":
            extra = _(" + original")
        else:
            extra = ""
        a = {"original": "", "crop916": _(" · Shorts"), "blur916": _(" · Shorts+blur"),
             "facecam": _(" · Facecam split")}.get(self.aspect, "")
        return f"MP4 · {q}{a}{extra}"

    @property
    def active(self):
        return self.status in (Job.WAITING, Job.RUNNING)

    def cancel(self):
        self._cancel = True
        p = self._proc
        if p and p.poll() is None:
            try:
                if IS_WIN:
                    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                                   creationflags=NO_WINDOW, capture_output=True)
                else:
                    p.terminate()
            except Exception:
                pass
        if self.status == Job.WAITING:
            self.status = Job.CANCELLED
            self.stage = _("Cancelled")


class JobQueue:
    """Arbeitet die Jobs nacheinander in einem Hintergrund-Thread ab."""

    def __init__(self, on_change=None):
        self.jobs = []
        self.on_change = on_change
        self._lock = threading.Lock()
        self._wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def add(self, job):
        with self._lock:
            self.jobs.append(job)
        self._wake.set()
        self._changed(job)
        return job

    def remove(self, job):
        job.cancel()
        with self._lock:
            if job in self.jobs:
                self.jobs.remove(job)
        self._changed(job)

    def clear_finished(self):
        with self._lock:
            self.jobs = [j for j in self.jobs if j.active]
        self._changed(None)

    def pending(self):
        return [j for j in self.jobs if j.active]

    def _changed(self, job):
        if self.on_change:
            try:
                self.on_change(job)
            except Exception:
                pass

    def _next(self):
        with self._lock:
            for j in self.jobs:
                if j.status == Job.WAITING and not j._cancel:
                    return j
        return None

    def _loop(self):
        while True:
            job = self._next()
            if job is None:
                self._wake.wait(1.0)
                self._wake.clear()
                continue
            try:
                Runner(job, self._changed).run()
            except Exception as ex:  # nie den Warteschlangen-Thread sterben lassen
                job.status = Job.FAILED
                job.error = _("Unexpected error: {ex}").format(ex=ex)
                job.stage = _("Error")
            job.finished_at = time.time()
            self._changed(job)


class Runner:
    """Fuehrt einen Job aus: yt-dlp (Abschnitt laden) und optional ffmpeg (Shorts-Format)."""

    def __init__(self, job, notify):
        self.job = job
        self.notify = notify
        self.tail = collections.deque(maxlen=20)
        self.encoder = None      # welcher Video-Encoder beim Schnitt benutzt wird
        self.no_hw = not tools.HW_ALLOWED   # Grafikkarten-Encoder abgeschaltet (Einstellung oder nach Fehler)
        self.slow_since = None   # seit wann die Verarbeitung deutlich langsamer als Echtzeit ist

    def set(self, progress=None, stage=None, detail=None):
        j = self.job
        if progress is not None and progress >= j.progress:
            j.progress = min(1.0, progress)
        if stage is not None:
            j.stage = stage
        if detail is not None:
            j.detail = detail
        self.notify(j)

    def eta(self, frac):
        el = time.time() - self.job.started_at
        if frac < 0.04 or el < 2:
            return ""
        rest = el * (1 - frac) / frac
        return _("about {int} s left").format(int=int(rest)) if rest < 90 else _("about {value} min left").format(value=int(rest // 60) + 1)

    # -------------------------------------------------- Ablauf
    def run(self):
        from . import finish
        j = self.job
        sp = j.spec or {}
        j.status = Job.RUNNING
        j.started_at = time.time()
        self.set(0.0, _("Starting…"), "")
        base = tools.ytdlp_cmd()
        ffmpeg = tools.find_tool("ffmpeg")
        if not base or not ffmpeg:
            missing = [n for n, ok in (("yt-dlp", base), ("ffmpeg", ffmpeg)) if not ok]
            return self.fail(_("{names} missing. Install it under Settings → Tools.").format(names=" & ".join(missing)))
        os.makedirs(j.folder, exist_ok=True)

        gif = sp.get("gif") if j.kind == "video" else None
        up = sp.get("upscale") or {}
        ai = j.kind == "video" and up.get("target") and up.get("engine") in ("esrgan", "topaz")
        ch0 = sp.get("chat") or {}
        chat_extra = bool(j.kind == "video" and ch0.get("messages") and (ch0.get("burn") or ch0.get("alpha")))
        post = finish.needs_finish(j) or bool(gif) or chat_extra
        final = os.path.join(j.folder, f"{j.name}.{'gif' if gif else j.ext}")
        if j.aspect == "facecam_raw":
            final = os.path.join(j.folder, f"{j.name} [Facecam].{'gif' if gif else 'mp4'}")
        dl_name = f"{j.name}.snipload-tmp" if post else j.name
        self.span = 0.5 if post else 0.95
        ok, dl_file = self.download_robust(base, ffmpeg, dl_name)
        if j._cancel:
            self._cleanup(dl_file if post else None)
            return self.cancelled()
        if not ok:
            return self.fail(self.error_text())
        temps = []
        try:
            if post:
                src = dl_file
                info = finish.probe(src)
                # 1) KI-Hochskalieren (vor dem Layout, damit der genutzte Ausschnitt scharf wird)
                if ai:
                    factor = finish.scale_factor_for_ai(j, info["w"] or 1920, info["h"] or 1080)
                    if factor > 1:
                        from . import upscale
                        label = _("AI upscaling ×{n}…").format(n=factor)
                        self.set(self.span, label, "")
                        up_file = os.path.join(j.folder, f"{j.name}.snipload-up.mp4")
                        temps.append(up_file)
                        cb = lambda f: self.set(self.span + 0.25 * f, label, "")
                        try:
                            if up.get("engine") == "topaz":
                                upscale.topaz_video(src, up_file, factor, info, cb, lambda: j._cancel)
                            else:
                                upscale.esrgan_video(src, up_file, factor, info, up.get("model") or "video", cb,
                                                     lambda: j._cancel, ffmpeg)
                            # Koordinaten der Facecam beziehen sich auf die Originalgroesse
                            src = up_file
                            info = finish.probe(src)
                        except Exception as ex:
                            if j._cancel:
                                return self.cancelled()
                            j.hint = "upscale_failed"
                            self.tail.append(f"upscale: {ex}")
                    self.span = min(0.8, self.span + 0.25)
                if j._cancel:
                    return self.cancelled()
                # 2) Ausgabegroesse ermitteln, Untertitel und Chat vorbereiten
                lay, W, H = finish.layout_filter(j, info["w"] or 1920, info["h"] or 1080)
                speed = float(sp.get("speed") or 1.0)
                ass_path = fonts_dir = None
                cap = sp.get("captions") or {}
                if j.kind == "video" and cap.get("words") and cap.get("burn", True):
                    from . import captions
                    ass_path = os.path.join(j.folder, f"{j.name}.snipload-cap.ass")
                    temps.append(ass_path)
                    with open(ass_path, "w", encoding="utf-8") as f:
                        f.write(captions.build_ass(cap["words"], cap.get("style") or {}, W, H, speed=speed))
                    fonts_dir = captions.fonts_dir_for(cap.get("style") or {}, tempfile.mkdtemp(prefix="snipload_fonts_"))
                chat_video = chat_box = None
                ch = sp.get("chat") or {}
                if j.kind == "video" and ch.get("messages") and (ch.get("burn") or ch.get("alpha")):
                    from . import chat as chatmod
                    self.set(self.span, _("Rendering chat…"), "")
                    dur = j.duration or info.get("duration") or 0
                    style = dict(ch.get("style") or {})
                    if ch.get("burn"):
                        # Chat-Feld relativ zur Endgroesse
                        box = ch.get("box") or {"x": 0.03, "y": 0.45, "w": 0.4, "h": 0.4}
                        bw = max(80, int(W * box["w"]) // 2 * 2)
                        bh = max(80, int(H * box["h"]) // 2 * 2)
                        scale = float(style.get("scale_px") or 0) or (bw / 420.0)
                        st = dict(style, width=int(bw / scale), height=int(bh / scale))
                        chat_video = os.path.join(j.folder, f"{j.name}.snipload-chat.mov")
                        temps.append(chat_video)
                        chatmod.render(ch["messages"], chat_video, dur, st, fmt="png", start=j.start,
                                       badge_urls=ch.get("badge_urls"), ffmpeg=ffmpeg, cancel=lambda: j._cancel)
                        chat_box = (int(W * box["x"]), int(H * box["y"]), bw, bh)
                    if ch.get("alpha"):
                        fmt = ch["alpha"]
                        ext = {"mov": "mov", "webm": "webm", "green": "mp4"}.get(fmt, "mov")
                        alpha_out = os.path.join(j.folder, f"{j.name} [Chat].{ext}")
                        chatmod.render(ch["messages"], alpha_out, dur, dict(ch.get("alpha_style") or style), fmt=fmt, start=j.start,
                                       badge_urls=ch.get("badge_urls"), ffmpeg=ffmpeg, cancel=lambda: j._cancel)
                        j.extra_files.append(alpha_out)
                if j._cancel:
                    return self.cancelled()
                # 3) Abschluss-Durchgang
                need_video_pass = finish.needs_finish(j) or chat_video or ass_path
                out = final
                if gif:
                    out = os.path.join(j.folder, f"{j.name}.snipload-gif.mp4")
                    temps.append(out)
                if need_video_pass:
                    ok = self.finish_pass(ffmpeg, src, out, info, ass_path, fonts_dir, chat_video, chat_box)
                    if not ok and not j._cancel and self.encoder not in (None, "libx264"):
                        tools.hw_broken = True
                        self.no_hw = True
                        ok = self.finish_pass(ffmpeg, src, out, info, ass_path, fonts_dir, chat_video, chat_box)
                    if j._cancel:
                        return self.cancelled()
                    if not ok:
                        return self.fail(self.error_text() or _("Converting to Shorts format didn't work."))
                else:
                    out = src
                    if not gif:      # nichts neu zu rechnen (z. B. nur transparenter Chat): Datei nur umbenennen
                        if os.path.exists(final):
                            os.remove(final)
                        os.replace(src, final)
                        out = final
                # 4) GIF
                if gif:
                    ok = self.run_ffmpeg(finish.gif_cmd(ffmpeg, out, final + ".part.gif", int(gif.get("fps") or 15),
                                                        int(gif.get("width") or 480)),
                                         _("Creating GIF…"), (info.get("duration") or j.duration or 0) / max(0.25, speed))
                    if not ok:
                        return self.fail(self.error_text())
                    os.replace(final + ".part.gif", final)
                # 5) Ganzes Video zusaetzlich behalten (Facecam-Modi)
                if j.also_full:
                    full = os.path.join(j.folder, f"{j.name}.mp4" if j.aspect == "facecam_raw"
                                        else f"{j.name} [Original].mp4")
                    try:
                        if os.path.exists(full):
                            os.remove(full)
                        os.replace(dl_file, full)
                        j.extra_files.append(full)
                    except OSError:
                        pass
                dl_file = final
            # 6) Untertitel zusaetzlich als .srt
            cap = sp.get("captions") or {}
            if cap.get("words") and cap.get("srt"):
                from . import captions
                srt_path = os.path.splitext(final)[0] + ".srt"
                with open(srt_path, "w", encoding="utf-8") as f:
                    f.write(captions.srt(cap["words"], cap.get("style"), float(sp.get("speed") or 1.0)))
                j.extra_files.append(srt_path)
        finally:
            for t in temps + ([dl_file] if post and dl_file and dl_file.endswith(("snipload-tmp.mp4", "snipload-tmp.m4a",
                                                                                   "snipload-tmp.webm")) else []):
                self._cleanup(t)
            if post:
                for f in os.listdir(j.folder):
                    if f.startswith(j.name + ".snipload-") and os.path.isfile(os.path.join(j.folder, f)):
                        self._cleanup(os.path.join(j.folder, f))
        j.file = dl_file if dl_file and os.path.exists(dl_file) else self.guess_result()
        try:
            j.size = os.path.getsize(j.file) if j.file else 0
        except OSError:
            j.size = 0
        j.status = Job.DONE
        secs = time.time() - j.started_at
        files = _("{value} files · ").format(value=1 + len(j.extra_files)) if j.extra_files else ""
        self.set(1.0, _("Done"), _("{files}in {secs:.0f} s").format(files=files, secs=secs))

    def finish_pass(self, ffmpeg, src, dst, info, ass_path, fonts_dir, chat_video, chat_box):
        from . import finish
        j = self.job
        sp = j.spec or {}
        if j.aspect == "facecam_raw" and not sp.get("upscale"):
            venc = ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p"]
        else:
            self.encoder, venc = tools.video_encoder(allow_hw=not self.no_hw)
        speed = max(0.25, float(sp.get("speed") or 1.0))
        dur = (info.get("duration") or j.duration or 0) / speed
        size_mb = float(sp.get("size_mb") or 0)
        bitrate = finish.size_bitrate(size_mb, dur, info.get("audio") and not sp.get("mute")) if size_mb else None
        label = _("Cutting out the facecam…") if j.aspect == "facecam_raw" else _("Rendering…")
        tmp = dst + ".part" + os.path.splitext(dst)[1]
        for attempt in range(3):
            cmd, _d = finish.build(j, ffmpeg, src, tmp, info, venc, ass_path, fonts_dir, chat_video, chat_box, bitrate)
            ok = self.run_ffmpeg(cmd, label, dur)
            if not ok:
                self._cleanup(tmp)
                return False
            if bitrate and os.path.getsize(tmp) > size_mb * 1024 * 1024 and attempt < 2:
                bitrate = int(bitrate * 0.85 * size_mb * 1024 * 1024 / os.path.getsize(tmp))
                continue
            break
        try:
            if os.path.exists(dst):
                os.remove(dst)
            os.replace(tmp, dst)
            return True
        except OSError as ex:
            self.tail.append(f"ERROR: {ex}")
            return False

    def run_ffmpeg(self, cmd, label, dur):
        """ffmpeg mit Fortschritt (-progress pipe:1) zwischen self.span und 0.97."""
        j = self.job
        self.set(self.span + 0.01, label, "")
        t0 = time.time()
        try:
            j._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, env=clean_env())
            win_no_throttle(getattr(j._proc, '_handle', None))
        except OSError as ex:
            self.tail.append(f"ERROR: {ex}")
            return False
        for line in _lines(j._proc.stdout):
            self.tail.append(line)
            if line.startswith(("out_time_us=", "out_time_ms=")) and dur:
                try:
                    sec = int(line.split("=", 1)[1]) / 1e6
                except ValueError:
                    continue
                frac = max(0.0, min(1.0, sec / dur))
                el = time.time() - t0
                eta = ""
                if frac > 0.05 and el > 1.5:
                    rest = el * (1 - frac) / frac
                    eta = (_("about {int} s left").format(int=int(rest)) if rest < 90
                           else _("about {value} min left").format(value=int(rest // 60) + 1))
                self.set(self.span + 0.01 + frac * (0.97 - self.span), label, eta)
        rc = j._proc.wait()
        j._proc = None
        return rc == 0 and not j._cancel

    def cancelled(self):
        self.job.status = Job.CANCELLED
        self.set(None, _("Cancelled"), "")

    def fail(self, msg):
        self.job.status = Job.FAILED
        self.job.error = msg
        self.set(None, _("Error"), msg)

    def _cleanup(self, path):
        if not path:
            return
        for p in (path, path + ".part"):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

    def guess_result(self):
        j = self.job
        try:
            cands = [os.path.join(j.folder, f) for f in os.listdir(j.folder) if f.startswith(j.name)]
            cands = [p for p in cands if os.path.isfile(p) and os.path.getmtime(p) >= j.started_at - 2
                     and not p.endswith((".part", ".ytdl", ".tmp"))]
            return max(cands, key=os.path.getmtime) if cands else None
        except OSError:
            return None

    def error_text(self):
        lines = [l for l in self.tail if "ERROR" in l or "rror" in l]
        if not lines:
            lines = list(self.tail)[-2:]
        return tools.friendly_error(lines[-1]) if lines else _("Unknown error.")

    # -------------------------------------------------- yt-dlp
    def build_cmd(self, base, ffmpeg, out_name, sections=True):
        j = self.job
        outtmpl = out_name.replace("%", "%%") + ".%(ext)s"
        cmd = base + tools.cookie_args() + [
            "--no-playlist", "--newline", "--no-colors", "--encoding", "utf-8", "--windows-filenames",
            "--no-quiet", "--progress", "--force-overwrites", "--no-mtime",
            "--progress-template", "download:[PCT] %(progress._percent_str)s",
            "--print", "after_move:SNIPLOAD_FILE:%(filepath)s",
            "-P", j.folder, "-o", outtmpl, "--ffmpeg-location", ffmpeg,
        ]
        if not sections:
            cmd += ["-N", "4"]   # ganzes Video mit yt-dlps eigenem Downloader (Notweg bei HTTP 403)
        elif not j.whole:
            end = fmt_ytdlp(j.end) if j.end is not None else "inf"
            cmd += ["--download-sections", f"*{fmt_ytdlp(j.start)}-{end}"]
            if j.exact:
                cmd.append("--force-keyframes-at-cuts")
                if j.kind == "video":
                    # Sonst kodiert ffmpeg mit Standard-Einstellungen (libx264 "medium" auf der CPU) - bei
                    # hohen Aufloesungen oft nur 0,1x Echtzeit. Grafikkarte oder "veryfast" ist viel schneller.
                    self.encoder, enc = tools.video_encoder(allow_hw=not self.no_hw)
                    cmd += ["--downloader-args", "ffmpeg_o:" + " ".join(enc + ["-c:a", "aac", "-b:a", "192k"])]
        if j.kind == "audio":
            cmd += ["-f", "ba/b", "-x", "--audio-format", j.audio_fmt, "--audio-quality", "0"]
        else:
            h = None if j.quality == "best" else int(j.quality)
            # Bei gleicher Aufloesung H.264 bevorzugen: laesst sich viel schneller lesen als AV1/VP9
            cmd += ["-f", f"bv*[height<={h}]+ba/b[height<={h}]/b" if h else "bv*+ba/b",
                    "-S", "res,fps,vcodec:h264,ext:mp4:m4a", "--merge-output-format", "mp4"]
        cmd.append(j.url)
        return cmd

    def _forbidden(self):
        return tools.is_forbidden("\n".join(self.tail))

    def download_robust(self, base, ffmpeg, out_name):
        """Laedt den Abschnitt. Verweigert YouTube den Download (HTTP 403 - meist wegen einer veralteten
        yt-dlp-Version), aktualisiert Snipload yt-dlp und versucht es nochmal. Hilft das nicht, laedt es das
        ganze Video mit yt-dlps eigenem Downloader und schneidet den Abschnitt selbst heraus."""
        j = self.job
        ok, f = self.download(base, ffmpeg, out_name)
        if not ok and not j._cancel and self.encoder not in (None, "libx264") and not self._forbidden():
            # Grafikkarten-Encoder kam mit dem Video nicht klar (z. B. 10-Bit/HDR) -> mit der CPU nochmal
            tools.hw_broken = True
            self.no_hw = True
            self.tail.clear()
            ok, f = self.download(base, ffmpeg, out_name)
        if ok or j._cancel or not self._forbidden():
            return ok, f
        self.set(0.0, _("YouTube blocked the download – updating yt-dlp and trying again…"), "")
        with _YTDLP_LOCK:
            tools.update_ytdlp()
        base = tools.ytdlp_cmd() or base
        self.tail.clear()
        ok, f = self.download(base, ffmpeg, out_name)
        if ok or j._cancel or not self._forbidden():
            return ok, f
        self.tail.clear()
        return self.download_then_cut(base, ffmpeg, out_name)

    def download_then_cut(self, base, ffmpeg, out_name):
        j = self.job
        span = self.span
        self.span = span * (1.0 if j.whole else 0.8)
        ok, full = self.download(base, ffmpeg, out_name + ".full", sections=False)
        self.span = span
        if not ok or j._cancel:
            self._cleanup(full)
            return False, None
        if j.whole:
            dst = os.path.join(j.folder, out_name + os.path.splitext(full)[1])
            os.replace(full, dst)
            return True, dst
        ext = os.path.splitext(full)[1]
        dst = os.path.join(j.folder, out_name + ext)
        tmp = os.path.join(j.folder, out_name + ".cut" + ext)
        length = (j.end - j.start) if j.end is not None else None
        cmd = [ffmpeg, "-hide_banner", "-y", "-ss", fmt_ytdlp(j.start), "-i", full]
        if length:
            cmd += ["-t", f"{length:.3f}"]
        if j.kind == "audio" or not j.exact:
            cmd += ["-c", "copy"]
        else:
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-c:a", "aac", "-b:a", "192k"]
        if ext.lower() in (".mp4", ".m4a"):
            cmd += ["-movflags", "+faststart"]
        cmd += ["-progress", "pipe:1", "-nostats", tmp]
        label = _("Cutting the section…")
        self.set(self.span * 0.8, label, "")
        try:
            j._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, env=clean_env())
            win_no_throttle(getattr(j._proc, '_handle', None))
        except OSError as ex:
            self.tail.append(f"ERROR: {ex}")
            self._cleanup(full)
            return False, None
        for line in _lines(j._proc.stdout):
            self.tail.append(line)
            if length and line.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    frac = max(0.0, min(1.0, int(line.split("=", 1)[1]) / 1e6 / length))
                except ValueError:
                    continue
                self.set(self.span * (0.8 + 0.2 * frac), label, "")
        rc = j._proc.wait()
        j._proc = None
        self._cleanup(full)
        if rc == 0 and os.path.exists(tmp) and not j._cancel:
            try:
                if os.path.exists(dst):
                    os.remove(dst)
                os.replace(tmp, dst)
                return True, dst
            except OSError as ex:
                self.tail.append(f"ERROR: {ex}")
        self._cleanup(tmp)
        return False, None

    def download(self, base, ffmpeg, out_name, sections=True):
        j = self.job
        cmd = self.build_cmd(base, ffmpeg, out_name, sections)
        self.passes, self.pass_idx, self.last_t, self.last_pct = 1, 0, -1.0, -1.0
        self.result = None
        env = clean_env({"PYTHONIOENCODING": "utf-8"})
        self.set(0.0, _("Connecting to YouTube…"), "")
        try:
            j._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, env=env)
            win_no_throttle(getattr(j._proc, '_handle', None))
        except OSError as ex:
            self.tail.append(f"ERROR: {ex}")
            return False, None
        last_tree = 0.0
        for line in _lines(j._proc.stdout):
            self.on_ytdlp_line(line)
            if IS_WIN and time.time() - last_tree > 3 and j._proc is not None:
                last_tree = time.time()   # auch das ffmpeg, das yt-dlp startet, nicht drosseln lassen
                win_unthrottle_tree(j._proc.pid)
        rc = j._proc.wait()
        j._proc = None
        f = self.result if self.result and os.path.exists(self.result) else None
        if f is None and rc == 0:
            guess = [os.path.join(j.folder, n) for n in os.listdir(j.folder) if n.startswith(out_name + ".")]
            guess = [p for p in guess if not p.endswith((".part", ".ytdl"))]
            f = max(guess, key=os.path.getmtime) if guess else None
        return rc == 0 and f is not None, f

    def on_ytdlp_line(self, line):
        j = self.job
        line = line.strip()
        if not line:
            return
        self.tail.append(line)
        if line.startswith("SNIPLOAD_FILE:"):
            self.result = line[len("SNIPLOAD_FILE:"):].strip()
            return
        m = FMT_RE.search(line)
        if m:
            self.passes = max(1, m.group(1).count("+") + 1)
            self.set(None, _("Downloading…"))
            return
        what = lambda idx: _("audio") if (j.kind == "audio" or (self.passes > 1 and idx >= 1)) else _("video")
        m = PCT_RE.search(line)
        if m:
            pct = float(m.group(1))
            if pct + 30 < self.last_pct:
                self.pass_idx += 1
            self.last_pct = pct
            idx = min(self.pass_idx, self.passes - 1)
            frac = (idx + pct / 100) / self.passes
            self.set(frac * self.span, _("Downloading {what}…").format(what=what(idx)), self.eta(frac))
            return
        t = TIME_RE.search(line)
        if t and j.duration:
            sec = int(t.group(1)) * 3600 + int(t.group(2)) * 60 + float(t.group(3))
            if sec + 2 < self.last_t:
                self.pass_idx += 1
            self.last_t = sec
            idx = min(self.pass_idx, self.passes - 1)
            frac = (idx + min(1.0, sec / j.duration)) / self.passes
            sp = SPEED_RE.search(line)
            speed = _("{float:.1f}× speed").format(float=float(sp.group(1))) if sp else ""
            # Sehr langsam (unter 0,5x) und laenger als 20 s: der App einen Tipp geben
            if sp and float(sp.group(1)) < 0.5 and j.exact and not j.hint:
                self.slow_since = self.slow_since or time.time()
                if time.time() - self.slow_since > 20:
                    j.hint = "slow"
            elif sp:
                self.slow_since = None
            det = " · ".join(x for x in (speed, self.eta(frac)) if x)
            self.set(frac * self.span, _("Downloading {what} and cutting…").format(what=what(idx)), det)
            return
        low = line.lower()
        if "[merger]" in low:
            self.set(self.span + 0.01, _("Merging video and audio…"), "")
        elif "[extractaudio]" in low:
            self.set(self.span + 0.01, _("Converting to {upper}…").format(upper=j.audio_fmt.upper()), "")
        elif "[youtube]" in low and "downloading" in low and self.job.progress < 0.01:
            self.set(None, _("Reading video data…"))

    # -------------------------------------------------- ffmpeg: Shorts 9:16

def _lines(stream):
    """Liest Zeilen, die mit \\n ODER \\r enden (ffmpeg schreibt Fortschritt mit \\r)."""
    buf = b""
    while True:
        ch = stream.read(1)
        if not ch:
            break
        if ch in (b"\r", b"\n"):
            if buf:
                yield buf.decode("utf-8", "replace")
                buf = b""
        else:
            buf += ch
    if buf:
        yield buf.decode("utf-8", "replace")
