"""Downloads: Auftraege (Jobs) und die Warteschlange, die sie nacheinander abarbeitet."""
import collections
import itertools
import os
import re
import subprocess
import threading
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

    def __init__(self, url, info, start, end, kind, quality, audio_fmt, aspect, exact, folder, name):
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
        self.no_hw = False       # Grafikkarten-Encoder abgeschaltet (nach einem Fehler)
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
        j = self.job
        j.status = Job.RUNNING
        j.started_at = time.time()
        self.set(0.0, _("Starting…"), "")
        base = tools.ytdlp_cmd()
        ffmpeg = tools.find_tool("ffmpeg")
        if not base or not ffmpeg:
            missing = [n for n, ok in (("yt-dlp", base), ("ffmpeg", ffmpeg)) if not ok]
            return self.fail(_("{names} missing. Install it under Settings → Tools.").format(names=" & ".join(missing)))
        os.makedirs(j.folder, exist_ok=True)

        post = j.kind == "video" and j.aspect != "original"
        final = os.path.join(j.folder, f"{j.name}.{j.ext}")
        if j.aspect == "facecam_raw":
            final = os.path.join(j.folder, f"{j.name} [Facecam].mp4")
        dl_name = f"{j.name}.snipload-tmp" if post else j.name
        self.span = 0.55 if post else 0.95
        ok, dl_file = self.download_robust(base, ffmpeg, dl_name)
        if j._cancel:
            self._cleanup(dl_file if post else None)
            return self.cancelled()
        if not ok:
            return self.fail(self.error_text())
        if post:
            ok = self.reframe(ffmpeg, dl_file, final)
            if not ok and not j._cancel and self.encoder not in (None, "libx264"):
                tools.hw_broken = True     # Grafikkarten-Encoder hat versagt -> mit der CPU nochmal
                self.no_hw = True
                ok = self.reframe(ffmpeg, dl_file, final)
            if ok and j.also_full:
                # normales Video zusaetzlich behalten
                full = os.path.join(j.folder, f"{j.name}.mp4" if j.aspect == "facecam_raw"
                                    else f"{j.name} [Original].mp4")
                try:
                    if os.path.exists(full):
                        os.remove(full)
                    os.replace(dl_file, full)
                    j.extra_files.append(full)
                except OSError:
                    pass
            self._cleanup(dl_file)
            if j._cancel:
                self._cleanup(final)
                return self.cancelled()
            if not ok:
                return self.fail(self.error_text() or _("Converting to Shorts format didn't work."))
            dl_file = final
        j.file = dl_file if dl_file and os.path.exists(dl_file) else self.guess_result()
        try:
            j.size = os.path.getsize(j.file) if j.file else 0
        except OSError:
            j.size = 0
        j.status = Job.DONE
        secs = time.time() - j.started_at
        files = _("{value} files · ").format(value=1 + len(j.extra_files)) if j.extra_files else ""
        self.set(1.0, _("Done"), _("{files}in {secs:.0f} s").format(files=files, secs=secs))

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
        cmd = base + [
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
    def reframe(self, ffmpeg, src, dst):
        j = self.job
        if j.aspect == "facecam_raw" and j.cam_px:
            # 1:1 - exakte Pixel, keine Skalierung. Falls die geladene Datei eine andere Aufloesung hat als
            # die Analyse-Bilder, werden die Koordinaten umgerechnet.
            from . import tools as _tools
            size = _tools.probe_size(src) or (j.cam_px["ref_w"], j.cam_px["ref_h"])
            sx, sy = size[0] / j.cam_px["ref_w"], size[1] / j.cam_px["ref_h"]
            cx, cy = int(round(j.cam_px["x"] * sx)), int(round(j.cam_px["y"] * sy))
            cw, ch = int(round(j.cam_px["w"] * sx)) // 2 * 2, int(round(j.cam_px["h"] * sy)) // 2 * 2
            cw, ch = min(cw, size[0] - cx) // 2 * 2, min(ch, size[1] - cy) // 2 * 2
            filt = ["-vf", f"crop={cw}:{ch}:{cx}:{cy},setsar=1,format=yuv420p"]
            self.out_size = (cw, ch)
        elif j.aspect == "facecam" and j.layout and j.layout.get("cam"):
            from . import facecam
            inf = j.info or {}
            aspect = (inf.get("width") / inf.get("height")) if inf.get("width") and inf.get("height") else 16 / 9
            filt = ["-filter_complex", facecam.ffmpeg_filter(j.layout, aspect), "-map", "[v]", "-map", "0:a?"]
        elif j.aspect == "blur916":
            vf = ("split[a][b];"
                  "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                  "boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.06:saturation=1.15[bg];"
                  "[b]scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2[fg];"
                  "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v]")
            filt = ["-filter_complex", vf, "-map", "[v]", "-map", "0:a?"]
        else:
            vf = ("scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
                  "crop=1080:1920,setsar=1,format=yuv420p")
            filt = ["-vf", vf]
        tmp_dst = dst + ".part.mp4"
        if j.aspect == "facecam_raw":   # 1:1-Facecam: klein, also ruhig so nah am Original wie moeglich
            venc = ["-c:v", "libx264", "-preset", "medium", "-crf", "16"]
        else:                           # 1080x1920: Grafikkarte oder libx264 "veryfast"
            self.encoder, venc = tools.video_encoder(allow_hw=not self.no_hw)
        cmd = [ffmpeg, "-hide_banner", "-y", "-i", src, *filt, *venc, "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", tmp_dst]
        label = _("Cutting out the facecam…") if j.aspect == "facecam_raw" else _("Converting to Shorts format…")
        self.set(self.span + 0.02, label, "")
        dur = j.duration or 0
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
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    sec = int(line.split("=", 1)[1]) / 1e6
                except ValueError:
                    continue
                if dur > 0:
                    frac = max(0.0, min(1.0, sec / dur))
                    el = time.time() - t0
                    eta = ""
                    if frac > 0.05 and el > 1.5:
                        rest = el * (1 - frac) / frac
                        eta = _("about {int} s left").format(int=int(rest)) if rest < 90 else _("about {value} min left").format(value=int(rest // 60) + 1)
                    self.set(self.span + 0.02 + frac * (0.97 - self.span), label, eta)
        rc = j._proc.wait()
        j._proc = None
        if rc == 0 and os.path.exists(tmp_dst):
            try:
                if os.path.exists(dst):
                    os.remove(dst)
                os.replace(tmp_dst, dst)
                return True
            except OSError as ex:
                self.tail.append(f"ERROR: {ex}")
        self._cleanup(tmp_dst)
        return False


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
