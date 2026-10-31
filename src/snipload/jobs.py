"""Downloads: Auftraege (Jobs) und die Warteschlange, die sie nacheinander abarbeitet."""
import collections
import itertools
import os
import re
import subprocess
import threading
import time

from . import tools
from .util import NO_WINDOW, IS_WIN, fmt_ytdlp

PCT_RE = re.compile(r"\[PCT\]\s*([\d.]+)%")
TIME_RE = re.compile(r"time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
SPEED_RE = re.compile(r"speed=\s*([\d.]+)x")
FMT_RE = re.compile(r"Downloading \d+ format\(s\):\s*(\S+)")

QUALITY_LABELS = {"best": "Beste Qualität", "2160": "2160p (4K)", "1440": "1440p", "1080": "1080p",
                  "720": "720p", "480": "480p"}
ASPECT_LABELS = {"original": "Original", "crop916": "Shorts 9:16", "blur916": "Shorts 9:16 + Blur"}
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
        self.stage = "Wartet…"
        self.detail = ""
        self.error = ""
        self.file = None
        self.size = 0
        self.started_at = None
        self.finished_at = None
        self.thumb = None               # Pfad zum gespeicherten Vorschaubild
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
        q = "Beste" if self.quality == "best" else f"{self.quality}p"
        a = "" if self.aspect == "original" else (" · Shorts" if self.aspect == "crop916" else " · Shorts+Blur")
        return f"MP4 · {q}{a}"

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
            self.stage = "Abgebrochen"


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
                job.error = f"Unerwarteter Fehler: {ex}"
                job.stage = "Fehler"
            job.finished_at = time.time()
            self._changed(job)


class Runner:
    """Fuehrt einen Job aus: yt-dlp (Abschnitt laden) und optional ffmpeg (Shorts-Format)."""

    def __init__(self, job, notify):
        self.job = job
        self.notify = notify
        self.tail = collections.deque(maxlen=20)

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
        return f"noch ca. {int(rest)} s" if rest < 90 else f"noch ca. {int(rest // 60) + 1} min"

    # -------------------------------------------------- Ablauf
    def run(self):
        j = self.job
        j.status = Job.RUNNING
        j.started_at = time.time()
        self.set(0.0, "Starte…", "")
        base = tools.ytdlp_cmd()
        ffmpeg = tools.find_tool("ffmpeg")
        if not base or not ffmpeg:
            missing = [n for n, ok in (("yt-dlp", base), ("ffmpeg", ffmpeg)) if not ok]
            return self.fail(f"{' und '.join(missing)} fehlt. Installiere es unter Einstellungen → Werkzeuge.")
        os.makedirs(j.folder, exist_ok=True)

        post = j.kind == "video" and j.aspect != "original"
        final = os.path.join(j.folder, f"{j.name}.{j.ext}")
        dl_name = f"{j.name}.snipload-tmp" if post else j.name
        self.span = 0.55 if post else 0.95
        ok, dl_file = self.download(base, ffmpeg, dl_name)
        if j._cancel:
            self._cleanup(dl_file if post else None)
            return self.cancelled()
        if not ok:
            return self.fail(self.error_text())
        if post:
            ok = self.reframe(ffmpeg, dl_file, final)
            self._cleanup(dl_file)
            if j._cancel:
                self._cleanup(final)
                return self.cancelled()
            if not ok:
                return self.fail(self.error_text() or "Umwandeln ins Shorts-Format hat nicht geklappt.")
            dl_file = final
        j.file = dl_file if dl_file and os.path.exists(dl_file) else self.guess_result()
        try:
            j.size = os.path.getsize(j.file) if j.file else 0
        except OSError:
            j.size = 0
        j.status = Job.DONE
        secs = time.time() - j.started_at
        self.set(1.0, "Fertig", f"in {secs:.0f} s")

    def cancelled(self):
        self.job.status = Job.CANCELLED
        self.set(None, "Abgebrochen", "")

    def fail(self, msg):
        self.job.status = Job.FAILED
        self.job.error = msg
        self.set(None, "Fehler", msg)

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
        return tools.friendly_error(lines[-1]) if lines else "Unbekannter Fehler."

    # -------------------------------------------------- yt-dlp
    def build_cmd(self, base, ffmpeg, out_name):
        j = self.job
        outtmpl = out_name.replace("%", "%%") + ".%(ext)s"
        cmd = base + [
            "--no-playlist", "--newline", "--no-colors", "--encoding", "utf-8", "--windows-filenames",
            "--no-quiet", "--progress", "--force-overwrites", "--no-mtime",
            "--progress-template", "download:[PCT] %(progress._percent_str)s",
            "--print", "after_move:SNIPLOAD_FILE:%(filepath)s",
            "-P", j.folder, "-o", outtmpl, "--ffmpeg-location", ffmpeg,
        ]
        if not j.whole:
            end = fmt_ytdlp(j.end) if j.end is not None else "inf"
            cmd += ["--download-sections", f"*{fmt_ytdlp(j.start)}-{end}"]
            if j.exact:
                cmd.append("--force-keyframes-at-cuts")
        if j.kind == "audio":
            cmd += ["-f", "ba/b", "-x", "--audio-format", j.audio_fmt, "--audio-quality", "0"]
        else:
            h = None if j.quality == "best" else int(j.quality)
            cmd += ["-f", f"bv*[height<={h}]+ba/b[height<={h}]/b" if h else "bv*+ba/b",
                    "-S", "ext:mp4:m4a", "--merge-output-format", "mp4"]
        cmd.append(j.url)
        return cmd

    def download(self, base, ffmpeg, out_name):
        j = self.job
        cmd = self.build_cmd(base, ffmpeg, out_name)
        self.passes, self.pass_idx, self.last_t, self.last_pct = 1, 0, -1.0, -1.0
        self.result = None
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        self.set(0.0, "Verbinde mit YouTube…", "")
        try:
            j._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, env=env)
        except OSError as ex:
            self.tail.append(f"ERROR: {ex}")
            return False, None
        for line in _lines(j._proc.stdout):
            self.on_ytdlp_line(line)
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
            self.set(None, "Lade herunter…")
            return
        what = lambda idx: "Ton" if (j.kind == "audio" or (self.passes > 1 and idx >= 1)) else "Video"
        m = PCT_RE.search(line)
        if m:
            pct = float(m.group(1))
            if pct + 30 < self.last_pct:
                self.pass_idx += 1
            self.last_pct = pct
            idx = min(self.pass_idx, self.passes - 1)
            frac = (idx + pct / 100) / self.passes
            self.set(frac * self.span, f"Lade {what(idx)}…", self.eta(frac))
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
            speed = f"{float(sp.group(1)):.1f}× Tempo" if sp else ""
            det = " · ".join(x for x in (speed, self.eta(frac)) if x)
            self.set(frac * self.span, f"Lade {what(idx)} und schneide…", det)
            return
        low = line.lower()
        if "[merger]" in low:
            self.set(self.span + 0.01, "Füge Bild und Ton zusammen…", "")
        elif "[extractaudio]" in low:
            self.set(self.span + 0.01, f"Wandle in {j.audio_fmt.upper()} um…", "")
        elif "[youtube]" in low and "downloading" in low and self.job.progress < 0.01:
            self.set(None, "Lese Video-Daten…")

    # -------------------------------------------------- ffmpeg: Shorts 9:16
    def reframe(self, ffmpeg, src, dst):
        j = self.job
        if j.aspect == "blur916":
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
        cmd = [ffmpeg, "-hide_banner", "-y", "-i", src, *filt,
               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", tmp_dst]
        self.set(self.span + 0.02, "Wandle ins Shorts-Format um…", "")
        dur = j.duration or 0
        t0 = time.time()
        try:
            j._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
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
                        eta = f"noch ca. {int(rest)} s" if rest < 90 else f"noch ca. {int(rest // 60) + 1} min"
                    self.set(self.span + 0.02 + frac * (0.97 - self.span), "Wandle ins Shorts-Format um…", eta)
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
