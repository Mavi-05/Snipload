"""Die Schnittstelle zwischen Oberflaeche (web/) und der Technik (yt-dlp, ffmpeg, Facecam, Untertitel, Chat ...).

Jede Methode api_<name> ist ueber POST /api/<name> erreichbar. Lange Arbeiten laufen als "Task" im Hintergrund
und melden Fortschritt ueber Ereignisse (EventHub): task, job, update, tools, toast.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser

from . import APP, captions, chat, editors, facecam, finish, i18n, search, tools, updater, upscale
from .i18n import _
from .jobs import Job, JobQueue
from .server import ApiError
from .util import (build_name, clean_env, config_dir, default_folder, load_settings, safe_filename, save_settings,
                   thumbs_dir, IS_WIN)

STRINGS_FOR_UI = None


def _cache_dir(*sub):
    d = os.path.join(config_dir(), "cache", *sub)
    os.makedirs(d, exist_ok=True)
    return d


class Task:
    def __init__(self, backend, kind, label=""):
        self.id = uuid.uuid4().hex[:10]
        self.kind = kind
        self.label = label
        self.progress = 0.0
        self.status = "running"
        self.result = None
        self.error = None
        self.cancelled = False
        self.b = backend

    def emit(self):
        self.b.hub.emit("task", {"id": self.id, "kind": self.kind, "label": self.label, "progress": self.progress,
                                 "status": self.status, "error": self.error,
                                 "result": self.result if self.status == "done" else None})

    def set(self, progress=None, label=None):
        if progress is not None:
            self.progress = max(0.0, min(1.0, progress))
        if label is not None:
            self.label = label
        now = time.time()
        if now - getattr(self, "_last", 0) > 0.15 or progress in (0.0, 1.0):
            self._last = now
            self.emit()


class Backend:
    def __init__(self, hub):
        self.hub = hub
        self.server = None
        self.window = None
        self.cfg = load_settings()
        if not self.cfg.get("folder"):
            self.cfg["folder"] = default_folder()
        tools.COOKIES_BROWSER = self.cfg.get("cookies_browser") or None
        tools.HW_ALLOWED = bool(self.cfg.get("hw_encode", True))
        self.infos = {}          # vid -> volle yt-dlp-Infos
        self.meta = {}           # vid -> fuer die Oberflaeche aufbereitet
        self.frame_fmt = {}      # (vid, hi) -> Format fuer Standbilder
        self.tasks = {}
        self.queue = JobQueue(on_change=self._job_changed)
        self.quit_ok = False
        self.upd = {"state": None, "info": None, "progress": 0.0, "error": None, "path": None}
        self._fonts_cache = None
        self._lock = threading.Lock()
        updater.cleanup_leftovers()

    # ================================================================ Hilfen
    def save(self):
        save_settings(self.cfg)

    def emit(self, kind, data=None):
        self.hub.emit(kind, data)

    def toast(self, text, kind="info", action=None):
        self.emit("toast", {"text": text, "kind": kind, "action": action})

    def task(self, kind, fn, label=""):
        t = Task(self, kind, label)
        self.tasks[t.id] = t

        def run():
            try:
                t.result = fn(t)
                t.status = "done"
                t.progress = 1.0
            except Exception as ex:  # noqa
                t.status = "cancelled" if t.cancelled else "error"
                t.error = str(ex)
            t.emit()
        threading.Thread(target=run, daemon=True).start()
        t.emit()
        return {"task": t.id}

    def media(self, path):
        if not path:
            return None
        return self.server.media_url(path) if self.server else path

    def allowed_media(self, path):
        """Darf /media diese Datei liefern? (Ausgabeordner, Verlauf, Cache, Schriften)"""
        roots = [self.cfg.get("folder"), config_dir(), tempfile.gettempdir()]
        roots += [os.path.dirname(h.get("file") or "") for h in self.cfg.get("history") or [] if h.get("file")]
        for r in roots:
            if not r:
                continue
            r = os.path.abspath(r)
            try:
                if os.path.commonpath([path, r]) == r:
                    return True
            except ValueError:
                continue
        try:
            for f in self._fonts():
                if os.path.abspath(f["file"]) == path:
                    return True
        except Exception:
            pass
        return False

    # ================================================================ Start
    def api_boot(self):
        strings = {}
        if i18n.LANG != "en":
            try:
                from .locales import load
                strings = load(i18n.LANG)
            except Exception:
                strings = {}
        threading.Thread(target=self._startup_checks, daemon=True).start()
        return {
            "app": APP, "version": updater.current_version(), "lang": i18n.LANG, "languages": i18n.LANGUAGES,
            "strings": strings, "cfg": self._public_cfg(), "jobs": [self._job_dict(j) for j in self.queue.jobs],
            "editors": self._editors(), "platform": "windows" if IS_WIN else sys.platform,
            "presets": captions.PRESETS, "bundled_fonts": [{"name": k, "file": v[1], "css": k} for k, v in captions.FONTS.items()],
            "caption_default": captions.DEFAULT_STYLE, "chat_default": chat.DEFAULT_STYLE,
            "whisper": captions.status(), "upscale": upscale.status(),
            "premiere_bridge": editors.premiere_bridge_installed(),
            "can_self_update": updater.can_self_update(),
        }

    def _public_cfg(self):
        c = {k: v for k, v in self.cfg.items() if not k.startswith("_") and k not in ("history",)}
        return c

    def _startup_checks(self):
        self.api_tools_status()
        time.sleep(1.5)
        if self.cfg.get("auto_update", True):
            try:
                self.api_update_check(silent=True)
            except Exception:
                pass
        after = self.cfg.pop("_updated_to", None)
        if after:
            self.save()
            if updater.parse_version(updater.current_version()) >= updater.parse_version(after):
                self.toast(_("Snipload has been updated to version {v}.").format(v=after), "success")

    def api_set_cfg(self, key, value):
        self.cfg[key] = value
        if key == "cookies_browser":
            tools.COOKIES_BROWSER = value or None
        if key == "hw_encode":
            tools.HW_ALLOWED = bool(value)
        self.save()
        return True

    def api_set_cfg_many(self, values):
        for k, v in (values or {}).items():
            self.cfg[k] = v
        self.save()
        return True

    # ================================================================ Entdecken
    def api_resolve(self, text, platform="youtube"):
        kind, val = search.classify(text)
        if kind == "video":
            return {"kind": "video", "url": val}
        if kind == "channel":
            return {"kind": "channel", "platform": val["platform"], "id": val["id"]}
        return {"kind": "search", "query": val}

    def api_search(self, query, platform="youtube", kind="videos"):
        try:
            return {"items": search.search(query, platform, kind)}
        except search.SearchError as ex:
            raise ApiError(str(ex))

    def api_channel(self, platform, id, tab=None):
        try:
            res = search.channel(platform, id, tab)
        except search.SearchError as ex:
            raise ApiError(str(ex))
        return res

    def api_favorites(self, action="list", item=None):
        favs = self.cfg.get("favorites") or []
        if action == "add" and item:
            favs = [f for f in favs if not (f.get("platform") == item.get("platform") and f.get("id") == item.get("id"))]
            favs.insert(0, {k: item.get(k) for k in ("platform", "id", "title", "avatar", "handle", "url")})
        elif action == "remove" and item:
            favs = [f for f in favs if not (f.get("platform") == item.get("platform") and f.get("id") == item.get("id"))]
        self.cfg["favorites"] = favs[:40]
        self.save()
        return favs

    # ================================================================ Video laden
    def api_load(self, url):
        try:
            info = tools.fetch_info(url)
        except tools.InfoError as ex:
            raise ApiError(str(ex))
        vid = str(info.get("id") or hashlib.md5(url.encode()).hexdigest()[:11])
        platform = search.platform_of(info.get("webpage_url") or url)
        self.infos[vid] = info
        m = self._editor_meta(vid, info, url, platform)
        self.meta[vid] = m
        recent = [r for r in self.cfg.get("recent") or [] if r.get("id") != vid]
        recent.insert(0, {"id": vid, "url": m["url"], "title": m["title"], "thumb": m["thumb"], "channel": m["channel"],
                          "duration": m["duration"], "platform": platform, "ts": time.time()})
        self.cfg["recent"] = recent[:30]
        self.save()
        return m

    def _editor_meta(self, vid, info, url, platform):
        dur = float(info.get("duration") or 0)
        w, h = info.get("width"), info.get("height")
        if not w or not h:
            best = max([f for f in info.get("formats") or [] if f.get("height") and tools.is_video_format(f)],
                       key=lambda f: f.get("height") or 0, default=None)
            if best:
                w, h = best.get("width"), best.get("height")
        thumb = info.get("thumbnail")
        if platform == "youtube" and info.get("id"):
            thumb = f"https://i.ytimg.com/vi/{info['id']}/hqdefault.jpg"
        m = {"id": vid, "url": info.get("webpage_url") or url, "platform": platform, "title": info.get("title") or "",
             "channel": info.get("channel") or info.get("uploader") or "", "channel_url": info.get("channel_url") or
             info.get("uploader_url"), "duration": dur, "thumb": thumb, "views": info.get("view_count"),
             "date": info.get("upload_date"), "width": w, "height": h, "live": info.get("live_status") == "is_live",
             "was_live": info.get("was_live") or info.get("live_status") == "was_live",
             "chapters": [{"start": c.get("start_time"), "end": c.get("end_time"), "title": c.get("title")}
                          for c in info.get("chapters") or []],
             "heatmap": [{"s": p.get("start_time"), "e": p.get("end_time"), "v": p.get("value")}
                         for p in info.get("heatmap") or []],
             "captions": captions.sources(info), "storyboard": self._storyboard(info, dur),
             "embed": None, "play_src": None, "chat": False, "start_hint": None, "is_clip": False,
             "preview_src": self._preview_src(info), "preview_audio": self._preview_audio(info)}
        if platform == "youtube":
            m["embed"] = {"type": "youtube", "id": info.get("id")}
            m["chat"] = bool((info.get("subtitles") or {}).get("live_chat"))
        elif platform == "twitch":
            vod = chat.twitch_vod_id(m["url"])
            if vod:
                m["embed"] = {"type": "twitch", "video": vod}
                m["play_src"] = self._hls_src(info)      # direkt abspielen: volle Kontrolle, kein Twitch-Overlay
                m["chat"] = True
                try:
                    extra = search.twitch_vod_meta(vod)
                    if extra.get("storyboard"):
                        m["storyboard"] = extra["storyboard"]
                    if extra.get("chapters") and not m["chapters"]:
                        m["chapters"] = [{"start": c["start_time"], "end": c["end_time"], "title": c["title"]}
                                         for c in extra["chapters"]]
                    if extra.get("owner"):
                        m["owner"] = extra["owner"]
                except Exception:
                    pass
            else:
                m["is_clip"] = True
                direct = self._preview_src(info, progressive=True)
                if direct:
                    m["embed"] = {"type": "direct", "src": direct["url"]}
                else:
                    m["embed"] = {"type": "twitch_clip", "clip": info.get("display_id") or info.get("id")}
        elif m["preview_src"] and m["preview_src"].get("audio"):
            m["embed"] = {"type": "direct", "src": m["preview_src"]["url"]}
        tm = re.search(r"[?&#]t=(\d+h)?(\d+m)?(\d+)s?", url)
        if tm:
            hh = int((tm.group(1) or "0h")[:-1])
            mm = int((tm.group(2) or "0m")[:-1])
            m["start_hint"] = hh * 3600 + mm * 60 + int(tm.group(3))
        return m

    @staticmethod
    def _preview_src(info, progressive=False):
        """Kleine direkt abspielbare Videoquelle fuer die Live-Vorschau (9:16-Handy). Bevorzugt H.264 bis 480p."""
        cands = []
        for f in info.get("formats") or []:
            if not tools.is_video_format(f):
                continue
            proto = f.get("protocol") or ("https" if str(f.get("url", "")).startswith("http") else "")
            if proto not in ("https", "http", "m3u8", "m3u8_native"):
                continue
            has_audio = tools.has_audio(f)
            if progressive and (not has_audio or proto.startswith("m3u8")):
                continue
            h = f.get("height") or 0
            if not h:
                continue
            codec = (f.get("vcodec") or "").lower()
            if not progressive and codec and not codec.startswith(("avc", "h264", "vp9", "vp09")) and not proto.startswith("m3u8"):
                continue
            score = (0 if proto.startswith("m3u8") else 1,
                     -abs(h - (1080 if progressive else 480)),
                     1 if codec.startswith(("avc", "h264")) else 0,
                     1 if has_audio else 0)
            cands.append((score, f))
        if not cands:
            return None
        f = max(cands, key=lambda x: x[0])[1]
        return {"url": f["url"], "kind": "hls" if (f.get("protocol") or "").startswith("m3u8") else "file",
                "w": f.get("width"), "h": f.get("height"), "audio": tools.has_audio(f)}

    @staticmethod
    def _hls_src(info, target=720):
        """Stream mit Bild und Ton (Twitch-VODs) zum direkten Abspielen im Editor, moeglichst 720p."""
        cands = [f for f in info.get("formats") or []
                 if tools.is_video_format(f) and (f.get("protocol") or "").startswith("m3u8") and tools.has_audio(f) and f.get("height")]
        if not cands:
            return None
        f = min(cands, key=lambda x: (x["height"] > target, abs(x["height"] - target), -(x.get("fps") or 0)))
        return {"url": f["url"], "kind": "hls", "w": f.get("width"), "h": f.get("height"), "audio": True}

    @staticmethod
    def _preview_audio(info):
        """Tonspur als eigene Datei (YouTube liefert Bild und Ton getrennt) - fuer die direkte Wiedergabe mit Ton."""
        best = None
        for f in info.get("formats") or []:
            if f.get("vcodec") != "none" or f.get("acodec") in (None, "none") or not f.get("url"):
                continue
            if (f.get("protocol") or "") not in ("https", "http"):
                continue
            score = (1 if str(f.get("acodec", "")).startswith("mp4a") else 0, -abs((f.get("abr") or 128) - 128))
            if best is None or score > best[0]:
                best = (score, f["url"])
        return best[1] if best else None

    def _storyboard(self, info, dur):
        sbs = [f for f in info.get("formats") or [] if str(f.get("format_id", "")).startswith("sb")
               and f.get("fragments") and f.get("rows") and f.get("columns")]
        if not sbs:
            return None
        sb = max(sbs, key=lambda f: f.get("width") or 0)
        fps = sb.get("fps") or 0
        per = sb["rows"] * sb["columns"]
        interval = (1.0 / fps) if fps else ((sb["fragments"][0].get("duration") or 10) / per)
        return {"width": sb.get("width"), "height": sb.get("height"), "cols": sb["columns"], "rows": sb["rows"],
                "interval": interval, "count": int(dur / interval) + 1 if interval else None,
                "sheets": [f.get("url") for f in sb["fragments"]]}

    # ---------------------------------------------------------------- Standbilder
    def frame_path(self, qs):
        vid = (qs.get("v") or [""])[0]
        t = float((qs.get("t") or ["0"])[0])
        w = int((qs.get("w") or ["0"])[0] or 0)
        info = self.infos.get(vid)
        if not info:
            return None
        hi = w == 0 or w > 1280
        key = (vid, hi)
        fmt = self.frame_fmt.get(key)
        if fmt is None:
            fmt = tools.pick_frame_format(info, max_h=None if hi else 1080) or False
            self.frame_fmt[key] = fmt
        if not fmt:
            return None
        t = round(t * 10) / 10
        path = os.path.join(_cache_dir("frames", vid), f"{t:.1f}_{w}.jpg")
        if os.path.exists(path):
            return path
        img = tools.grab_frame(fmt, t, width=w or None)
        if img is None:
            return None
        img.convert("RGB").save(path, quality=90)
        return path

    def api_snapshot(self, vid, t):
        """Standbild in voller Aufloesung in den Ausgabeordner speichern."""
        p = self.frame_path({"v": [vid], "t": [str(t)], "w": ["0"]})
        if not p:
            raise ApiError(_("Couldn't get any frames from the video."))
        meta = self.meta.get(vid) or {}
        from .util import fmt_short
        folder = self.cfg.get("folder") or default_folder()
        os.makedirs(folder, exist_ok=True)
        name = safe_filename(f"{meta.get('title') or vid} [{fmt_short(float(t)).replace(':', '-')}]") + ".jpg"
        dst = os.path.join(folder, name)
        import shutil
        shutil.copyfile(p, dst)
        if self.server:
            self.server.allow(folder)
        return {"file": dst, "url": self.media(dst)}

    def api_name_preview(self, vid, start, end, template=None):
        info = self.infos.get(vid)
        summary = tools.info_summary(info) if info else {"title": "Video", "channel": "Channel", "id": "abc"}
        dur = (self.meta.get(vid) or {}).get("duration") or 0
        e = None if end is None else float(end)
        return safe_filename(build_name(template or self.cfg.get("name_template"), summary, float(start or 0), e,
                                        whole=(float(start or 0) <= 0 and (e is None or e >= dur - 0.5))))

    # ---------------------------------------------------------------- Facecam
    def api_facecam_detect(self, vid, start, end, aspect=16 / 9):
        info = self.infos.get(vid)
        if not info:
            raise ApiError("video not loaded")

        def work(t):
            from concurrent.futures import ThreadPoolExecutor
            fmt = tools.pick_frame_format(info, max_h=None)
            if not fmt or not facecam.available():
                return {"ok": False, "message": _("There are no frames available for this video – please set the facecam by hand."),
                        "frames": []}
            n = 10
            ts = [start + (end - start) * (i + 0.5) / n for i in range(n)]
            done = [0]

            def grab(tt):
                img = tools.grab_frame(fmt, tt, width=None)
                done[0] += 1
                t.set(0.8 * done[0] / n, _("Getting frames from the section … {i}/{n}").format(i=done[0], n=n))
                return (tt, img)
            with ThreadPoolExecutor(max_workers=3) as ex:
                frames = list(ex.map(grab, ts))
            t.set(0.85, _("Analyzing the frames and looking for the facecam …"))
            ok_frames = [(tt, im) for tt, im in frames if im is not None]
            small = [(tt, im.resize((960, max(2, int(960 * im.size[1] / im.size[0]))))) for tt, im in ok_frames]
            res = facecam.analyze(small, aspect) if small else {"ok": False, "message": _("Couldn't get any frames from the video.")}
            if res.get("ok") and not res.get("fullscreen"):
                good = [tt for tt, _x in ok_frames if tt not in set(res.get("missing") or [])]
                res["px"] = facecam.refine(ok_frames, res["box"], good)
                box = facecam.px_to_norm(res["px"]) if res.get("px") else res["box"]
                res["box"] = list(box)
                res["layout"] = facecam.suggest_layout(box, aspect, self.cfg.get("fc_sizes") or None,
                                                       cam_bottom=bool(self.cfg.get("fc_bottom")))
            out_frames = []
            d = _cache_dir("frames", vid)
            for tt, im in ok_frames:
                p = os.path.join(d, f"fc_{tt:.2f}.jpg")
                im.convert("RGB").save(p, quality=88)
                out_frames.append({"t": tt, "url": self.media(p), "w": im.size[0], "h": im.size[1],
                                   "missing": tt in set(res.get("missing") or [])})
            res["frames"] = out_frames
            for k in ("box",):
                if k in res and res[k] is not None:
                    res[k] = list(res[k])
            return json.loads(json.dumps(res, default=lambda o: list(o) if isinstance(o, tuple) else str(o)))
        return self.task("facecam", work, _("Looking for the facecam – one moment."))

    def api_facecam_preview(self, layout, aspect=16 / 9):
        """Hilfswerte fuer die Live-Vorschau des 9:16-Layouts (Geometrie wie beim Export)."""
        g = facecam.layout_geometry(layout, aspect)
        return {"cam": list(g["cam"]), "game": list(g["game"]), "hf": g["hf"], "hg": g["hg"],
                "cam_plan": {k: (list(v) if isinstance(v, tuple) else v) for k, v in g["cam_plan"].items()},
                "game_plan": {k: (list(v) if isinstance(v, tuple) else v) for k, v in g["game_plan"].items()},
                "cam_bottom": g["cam_bottom"]}

    # ---------------------------------------------------------------- Untertitel
    def api_captions_generate(self, vid, start, end, source="ai", model="balanced", lang="auto", translate=False):
        info = self.infos.get(vid)
        meta = self.meta.get(vid) or {}
        if not info:
            raise ApiError("video not loaded")

        def work(t):
            work_dir = tempfile.mkdtemp(prefix="snipload_cap_")
            if source != "ai":
                t.set(0.2, _("Getting captions from YouTube…"))
                words = captions.fetch_youtube(meta.get("url"), source, float(start), float(end), work_dir)
                return {"words": words, "source": source}
            # KI: Werkzeug + Modell sicherstellen
            if not captions.whisper_exe():
                t.set(0.02, _("Downloading the AI speech engine…"))
                captions.install_whisper(lambda f: t.set(0.02 + 0.08 * f))
            if not captions.model_path(model):
                mb = captions.MODELS.get(model, captions.MODELS["balanced"])[1]
                t.set(0.1, _("Downloading the AI model ({mb} MB, only once)…").format(mb=mb))
                captions.install_model(model, lambda f: t.set(0.1 + 0.3 * f))
            t.set(0.42, _("Loading the audio of the section…"))
            audio = self._section_audio(meta.get("url"), float(start), float(end), work_dir, t)
            t.set(0.55, _("Transcribing with AI…"))
            res = captions.transcribe(audio, model, lang, bool(translate),
                                      lambda f: t.set(0.55 + 0.44 * f), lambda: t.cancelled)
            return {"words": res["words"], "lang": res.get("lang"), "source": "ai"}
        return self.task("captions", work, _("Creating captions…"))

    def _section_audio(self, url, start, end, work_dir, task):
        base = tools.ytdlp_cmd()
        ffmpeg = tools.find_tool("ffmpeg")
        out = os.path.join(work_dir, "audio")
        from .util import fmt_ytdlp
        cmd = base + tools.cookie_args() + ["--no-playlist", "-f", "ba/b", "--download-sections",
                                            f"*{fmt_ytdlp(start)}-{fmt_ytdlp(end)}", "--ffmpeg-location", ffmpeg,
                                            "-o", out + ".%(ext)s", "--no-warnings", "--force-overwrites", url]
        r = tools.run(cmd, 600)
        files = [os.path.join(work_dir, f) for f in os.listdir(work_dir) if f.startswith("audio.")]
        if not files:
            err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            raise ApiError(tools.friendly_error(err[-1]) if err else "audio download failed")
        wav = os.path.join(work_dir, "audio16k.wav")
        captions.extract_audio(files[0], wav, ffmpeg)
        return wav

    def api_captions_srt(self, words, style=None):
        return captions.srt(words, style)

    def _fonts(self):
        if self._fonts_cache is None:
            try:
                self._fonts_cache = captions.system_fonts()
            except Exception:
                self._fonts_cache = []
        return self._fonts_cache

    def api_fonts(self):
        out = []
        for f in self._fonts():
            out.append({"name": f["name"], "family": f["family"], "style": f["style"], "source": f["source"],
                        "file": f["file"], "url": self.media(f["file"])})
        return out

    def api_add_font(self):
        files = self._dialog("open", ("Fonts (*.ttf;*.otf)",))
        if not files:
            return None
        try:
            f = captions.add_user_font(files[0])
        except captions.CaptionError as ex:
            raise ApiError(str(ex))
        self._fonts_cache = None
        f["url"] = self.media(f["file"])
        return f

    def api_caption_preview(self, vid, t, words, style, width, height, offset=0.0):
        """Exakte Vorschau: Standbild + mit libass eingebrannte Untertitel (wie im fertigen Video)."""
        frame = self.frame_path({"v": [vid], "t": [str(t)], "w": ["0"]})
        if not frame:
            raise ApiError("no frame")
        d = _cache_dir("preview")
        ass = os.path.join(d, "cap.ass")
        with open(ass, "w", encoding="utf-8") as f:
            f.write(captions.build_ass(words, style, int(width), int(height)))
        fonts_dir = captions.fonts_dir_for(style, tempfile.mkdtemp(prefix="snipload_pf_"))
        out = os.path.join(d, f"cap_{uuid.uuid4().hex[:8]}.jpg")
        ff = tools.find_tool("ffmpeg")
        vf = f"scale={int(width)}:{int(height)}:force_original_aspect_ratio=increase,crop={int(width)}:{int(height)}," \
             f"setpts=PTS+{max(0.0, float(offset)):.3f}/TB," + captions.ffmpeg_filter(ass, fonts_dir)
        subprocess.run([ff, "-v", "error", "-y", "-loop", "1", "-t", "1", "-i", frame, "-vf", vf, "-frames:v", "1", out],
                       capture_output=True, creationflags=0 if not IS_WIN else 0x08000000, env=clean_env())
        return self.media(out) if os.path.exists(out) else None

    # ---------------------------------------------------------------- Chat
    def api_chat_load(self, vid, start, end):
        meta = self.meta.get(vid) or {}

        def work(t):
            url = meta.get("url") or ""
            if meta.get("platform") == "twitch":
                vod = chat.twitch_vod_id(url)
                if not vod:
                    raise ApiError(_("Chat is only available for Twitch VODs and YouTube streams."))
                t.set(0.02, _("Loading Twitch chat…"))
                msgs = chat.twitch_comments(vod, float(start), float(end), lambda f: t.set(0.05 + 0.75 * f),
                                            lambda: t.cancelled)
                owner = meta.get("owner") or {}
                t.set(0.85, _("Loading emotes and badges…"))
                emotes = chat.third_party_emotes(owner.get("id"))
                msgs = chat.apply_emotes(msgs, emotes)
                badges = chat.twitch_badges(owner.get("login") or "") if owner.get("login") else {}
            else:
                t.set(0.05, _("Loading the chat replay (whole stream, this can take a moment)…"))
                msgs = chat.youtube_chat(url, float(start), float(end), cancel=lambda: t.cancelled)
                badges = {}
            return {"messages": msgs, "badge_urls": badges, "count": len(msgs)}
        return self.task("chat", work, _("Loading chat…"))

    def api_chat_hype(self, vid):
        """Ganzen Chat laden und die Momente mit der meisten Chat-Aktivitaet finden."""
        meta = self.meta.get(vid) or {}

        def work(t):
            dur = float(meta.get("duration") or 0)
            if meta.get("platform") == "twitch":
                vod = chat.twitch_vod_id(meta.get("url") or "")
                msgs = chat.twitch_comments(vod, 0, dur, lambda f: t.set(0.95 * f), lambda: t.cancelled)
            else:
                msgs = chat.youtube_chat(meta.get("url"), 0, None, cancel=lambda: t.cancelled)
            d = chat.density(msgs, dur, 10.0)
            d["count"] = len(msgs)
            return d
        return self.task("hype", work, _("Finding hype moments in the chat…"))

    def api_chat_preview(self, messages, style, t, badge_urls=None):
        """Chat-Stand zum Zeitpunkt t als PNG (fuer die Vorschau im Editor)."""
        r = chat.Renderer(style, badge_urls)
        st = r.st
        vis = [m for m in messages if m["t"] <= t and (not st.get("max_age") or t - m["t"] < float(st["max_age"]))][-30:]
        img = r.frame(vis)
        p = os.path.join(_cache_dir("preview"), f"chat_{uuid.uuid4().hex[:8]}.png")
        img.save(p)
        return self.media(p)

    def api_task_cancel(self, id):
        t = self.tasks.get(id)
        if t:
            t.cancelled = True
        return True

    # ================================================================ Export
    def api_export(self, vid, clips, opts):
        """clips: [{start, end, name?}] - je Clip ein Auftrag. opts: Format, Qualitaet, Extras (spec) ..."""
        info = self.infos.get(vid)
        meta = self.meta.get(vid) or {}
        if not info:
            raise ApiError("video not loaded")
        summary = tools.info_summary(info)
        thumb = self._save_thumb(vid, meta.get("thumb"))
        folder = opts.get("folder") or self.cfg.get("folder") or default_folder()
        ids = []
        for i, c in enumerate(clips):
            s, e = float(c["start"]), c.get("end")
            e = None if e is None else float(e)
            name = c.get("name") or build_name(self.cfg.get("name_template"), summary, s, e,
                                               whole=(s <= 0 and (e is None or e >= (meta.get("duration") or 0) - 0.5)))
            name = safe_filename(name)
            spec = dict(opts.get("spec") or {})
            # Untertitel beziehen sich auf den jeweiligen Clip (Zeiten ab Clip-Anfang)
            if spec.get("captions") and c.get("caption_words") is not None:
                spec["captions"] = dict(spec["captions"], words=c["caption_words"])
            job = Job(meta.get("url"), summary, s, e, opts.get("kind", "video"), opts.get("quality", "best"),
                      opts.get("audio_fmt", "mp3"), opts.get("aspect", "original"), bool(opts.get("exact", True)),
                      folder, name, spec=spec)
            job.thumb = thumb
            job.layout = opts.get("layout")
            job.cam_px = opts.get("cam_px")
            job.also_full = bool(opts.get("also_full"))
            job.open_in = opts.get("open_in")
            job.open_mode = opts.get("open_mode")
            job.vid = vid
            self.queue.add(job)
            ids.append(job.id)
        if self.server:
            self.server.allow(folder)
        self.cfg["folder"] = folder
        self.save()
        return {"jobs": ids}

    def _save_thumb(self, vid, url):
        if not url:
            return None
        p = os.path.join(thumbs_dir(), f"{safe_filename(str(vid))}.jpg")
        if os.path.exists(p):
            return p
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=search.UA)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            with open(p, "wb") as f:
                f.write(data)
            return p
        except Exception:
            return None

    def _job_dict(self, j):
        return {"id": j.id, "title": j.title, "name": j.name, "status": j.status, "progress": j.progress,
                "stage": j.stage, "detail": j.detail, "error": j.error, "file": j.file, "size": j.size,
                "files": [f for f in [j.file] + list(j.extra_files) if f],
                "file_url": self.media(j.file) if j.file and j.status == Job.DONE else None,
                "thumb": self.media(j.thumb) if j.thumb else None, "format": j.format_label(),
                "start": j.start, "end": j.end, "kind": j.kind, "aspect": j.aspect, "hint": j.hint,
                "sent_to": j.sent_to, "duration": j.duration}

    def _job_changed(self, job):
        if job is None:
            self.emit("jobs", [self._job_dict(j) for j in self.queue.jobs])
            return
        if job.status == Job.DONE and not getattr(job, "_handled", False):
            job._handled = True
            self._add_history(job)
            if self.cfg.get("sound", True) and not any(j.active for j in self.queue.jobs):
                from .util import win_sound_done
                win_sound_done()
            if getattr(job, "open_in", None):
                try:
                    res = self._send_to_editor(job.open_in, [job.file], getattr(job, "open_mode", None))
                    job.sent_to = job.open_in if res.get("ok") else None
                except Exception as ex:
                    self.toast(str(ex), "error")
        self.emit("job", self._job_dict(job))

    def _add_history(self, job):
        entry = {"title": job.title, "channel": (job.info or {}).get("channel") or "", "file": job.file or "",
                 "files": [f for f in job.extra_files if f], "url": job.url, "id": (job.info or {}).get("id"),
                 "start": 0 if job.whole else job.start, "end": None if job.whole else job.end, "kind": job.kind,
                 "format": job.format_label(), "size": job.size, "thumb": job.thumb, "aspect": job.aspect,
                 "duration": job.duration, "ts": time.time()}
        hist = [h for h in self.cfg.get("history", []) if h.get("file") != entry["file"] or not entry["file"]]
        self.cfg["history"] = [entry] + hist[:499]
        self.save()
        self.emit("library", None)

    def api_jobs(self):
        return [self._job_dict(j) for j in self.queue.jobs]

    def _job(self, id):
        for j in self.queue.jobs:
            if j.id == id:
                return j
        raise ApiError("job not found")

    def api_job_cancel(self, id):
        self._job(id).cancel()
        return True

    def api_job_remove(self, id):
        self.queue.remove(self._job(id))
        return True

    def api_job_retry(self, id):
        old = self._job(id)
        j = Job(old.url, old.info, old.start, old.end, old.kind, old.quality, old.audio_fmt, old.aspect, old.exact,
                old.folder, old.name, spec=old.spec)
        for k in ("thumb", "layout", "cam_px", "also_full", "open_in", "open_mode", "vid"):
            setattr(j, k, getattr(old, k, None))
        self.queue.remove(old)
        self.queue.add(j)
        return j.id

    def api_jobs_clear(self):
        self.queue.clear_finished()
        return True

    # ================================================================ Bibliothek
    def api_library(self):
        out = []
        for h in self.cfg.get("history") or []:
            f = h.get("file")
            exists = bool(f and os.path.exists(f))
            if exists and self.server:
                self.server.allow(os.path.dirname(f))
            out.append(dict(h, exists=exists, file_url=self.media(f) if exists else None,
                            thumb_url=self.media(h["thumb"]) if h.get("thumb") and os.path.exists(h["thumb"]) else None))
        return out

    def api_library_remove(self, file, delete_file=False):
        hist = self.cfg.get("history") or []
        self.cfg["history"] = [h for h in hist if h.get("file") != file]
        self.save()
        if delete_file and file and os.path.isfile(file):
            try:
                os.remove(file)
            except OSError as ex:
                raise ApiError(str(ex))
        return True

    def api_library_clear(self):
        self.cfg["history"] = []
        self.save()
        return True

    def api_open_file(self, path):
        if not path or not os.path.exists(path):
            raise ApiError(_("File no longer exists"))
        if IS_WIN:
            os.startfile(path)  # noqa
        else:
            subprocess.Popen(["xdg-open", path])
        return True

    def api_reveal(self, path):
        if not path or not os.path.exists(path):
            raise ApiError(_("File no longer exists"))
        editors.reveal(path)
        return True

    def api_copy_file(self, path):
        return editors.copy_files_to_clipboard([path])

    # ================================================================ Schnittprogramme
    def _editors(self):
        return editors.detect(self.cfg.get("custom_editors") or [])

    def api_editors(self):
        return {"editors": self._editors(), "premiere_bridge": editors.premiere_bridge_installed()}

    def _send_to_editor(self, editor_id, files, mode=None):
        ed = next((e for e in self._editors() if e["id"] == editor_id), None)
        if not ed:
            raise ApiError(_("This program wasn't found on your PC."))
        res = editors.send(ed, files, mode or (self.cfg.get("premiere_mode") if ed["kind"] == "premiere" else None))
        if ed["kind"] == "premiere":
            msg = _("Sent to Premiere Pro – it appears in the “Snipload” bin of your open project.")
            if res.get("first"):
                msg = _("Premiere integration installed. Restart Premiere once – after that clips arrive automatically.")
            self.toast(msg, "success")
        elif ed["kind"] == "aftereffects":
            self.toast(_("Importing into After Effects…"), "success")
        elif res.get("clipboard"):
            self.toast(_("{name} opened – the clip is in your clipboard: press Ctrl+V in the media panel.").format(
                name=ed["name"]), "info")
        return res

    def api_send_to_editor(self, editor, files, mode=None):
        return self._send_to_editor(editor, files, mode)

    def api_add_editor(self):
        files = self._dialog("open", ("Programs (*.exe)",))
        if not files:
            return None
        custom = self.cfg.get("custom_editors") or []
        custom.append({"id": f"custom{int(time.time())}", "name": os.path.splitext(os.path.basename(files[0]))[0],
                       "path": files[0]})
        self.cfg["custom_editors"] = custom
        self.save()
        return self._editors()

    def api_remove_editor(self, id):
        self.cfg["custom_editors"] = [c for c in self.cfg.get("custom_editors") or [] if c.get("id") != id]
        self.save()
        return self._editors()

    def api_install_premiere_bridge(self):
        editors.install_premiere_bridge()
        return True

    # ================================================================ Werkzeuge
    def api_tools_status(self):
        st = {"ytdlp": tools.ytdlp_version(), "ffmpeg": tools.ffmpeg_version()}
        st["ytdlp_age"] = tools.version_age_days(st.get("ytdlp") or "")
        st["whisper"] = captions.status()
        st["upscale"] = upscale.status()
        self.emit("tools", st)
        age = st["ytdlp_age"]
        if st.get("ytdlp") and age is not None and age > 7:
            last = self.cfg.get("_ytdlp_auto_at") or 0
            if time.time() - last > 20 * 3600 and not any(j.status == Job.RUNNING for j in self.queue.jobs):
                self.cfg["_ytdlp_auto_at"] = time.time()
                self.save()
                self.api_update_ytdlp(silent=True)
        if not st.get("ytdlp") or not st.get("ffmpeg"):
            self.emit("tools_missing", [n for n, k in (("yt-dlp", "ytdlp"), ("ffmpeg", "ffmpeg")) if not st.get(k)])
        return st

    def api_install_tools(self, names):
        def work(t):
            failed = tools.install(names, lambda n, f: t.set(f, _("Downloading {names} … {value:.0f} %").format(
                names=n, value=f * 100)))
            st = self.api_tools_status()
            if failed:
                raise ApiError(_("Couldn't download {names}. Check your internet connection and try again.").format(
                    names=" & ".join(failed)))
            return st
        return self.task("install", work, _("Installing {names} …").format(names=" & ".join(names)))

    def api_update_ytdlp(self, silent=False):
        def work(t):
            t.set(0.1, _("Updating yt-dlp …"))
            before, after = tools.update_ytdlp()
            st = self.api_tools_status()
            if after and before != after:
                self.toast(_("yt-dlp updated: {before} → {after}").format(before=before, after=after), "success")
            elif not silent:
                self.toast(_("yt-dlp is already the latest version ({after}).").format(after=after), "info")
            return st
        return self.task("ytdlp", work, _("Updating yt-dlp …"))

    def api_install_whisper(self, model="balanced"):
        def work(t):
            if not captions.whisper_exe():
                captions.install_whisper(lambda f: t.set(0.1 * f, _("Downloading the AI speech engine…")))
            captions.install_model(model, lambda f: t.set(0.1 + 0.9 * f, _("Downloading the AI model ({mb} MB, only once)…").format(
                mb=captions.MODELS.get(model, captions.MODELS["balanced"])[1])))
            return captions.status()
        return self.task("whisper", work, _("Downloading the AI speech engine…"))

    def api_install_esrgan(self):
        def work(t):
            upscale.install_esrgan(lambda f: t.set(f, _("Downloading the AI upscaler…")))
            return upscale.status()
        return self.task("esrgan", work, _("Downloading the AI upscaler…"))

    # ================================================================ Updates
    def api_update_check(self, silent=False):
        self.upd.update(state="checking", error=None)
        self.emit("update", self._upd_public())
        try:
            info = updater.check()
            self.upd.update(state="available" if info else "current", info=info, checked_at=time.time())
        except updater.UpdateError as ex:
            self.upd.update(state="error", error=str(ex))
        self.emit("update", self._upd_public())
        if self.upd["state"] == "available" and self.cfg.get("auto_update", True) and updater.can_self_update():
            self.api_update_download()
        return self._upd_public()

    def _upd_public(self):
        info = self.upd.get("info") or {}
        return {"state": self.upd["state"], "version": info.get("version"), "notes": info.get("notes"),
                "progress": self.upd.get("progress", 0), "error": self.upd.get("error"),
                "current": updater.current_version(), "page": info.get("page")}

    def api_update_download(self):
        info = self.upd.get("info")
        if not info or self.upd["state"] in ("downloading", "ready"):
            return self._upd_public()
        if not updater.can_self_update():
            webbrowser.open(info.get("page") or f"https://github.com/{updater.REPO}/releases/latest")
            return self._upd_public()
        self.upd.update(state="downloading", progress=0.0)

        def prog(f):
            self.upd["progress"] = f
            self.emit("update", self._upd_public())

        def work():
            try:
                self.upd["path"] = updater.download(info, prog)
                self.upd["state"] = "ready"
            except updater.UpdateError as ex:
                self.upd.update(state="error", error=str(ex))
            self.emit("update", self._upd_public())
        threading.Thread(target=work, daemon=True).start()
        return self._upd_public()

    def api_update_restart(self):
        path = self.upd.get("path")
        if not path:
            raise ApiError("no update")
        for j in self.queue.jobs:
            if j.active:
                j.cancel()
        self.cfg["_updated_to"] = (self.upd.get("info") or {}).get("version")
        self.save()
        updater.install(path, restart=True)
        self._close_window()
        return True

    # ================================================================ Fenster
    def _dialog(self, kind, file_types=()):
        if not self.window:
            return None
        import webview
        dt = {"open": webview.FileDialog.OPEN, "folder": webview.FileDialog.FOLDER}[kind]
        try:
            res = self.window.create_file_dialog(dt, directory=self.cfg.get("folder") or "", file_types=file_types)
        except Exception:
            res = self.window.create_file_dialog(dt, directory=self.cfg.get("folder") or "")
        return list(res) if res else None

    def api_pick_folder(self):
        res = self._dialog("folder")
        if res:
            self.cfg["folder"] = res[0]
            self.save()
            if self.server:
                self.server.allow(res[0])
            return res[0]
        return None

    def api_open_url(self, url):
        if url and re.match(r"^https?://", url):
            webbrowser.open(url)
        return True

    def api_restart(self):
        """Neustart (z. B. nach Sprachwechsel)."""
        flags = 0
        if IS_WIN:
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(sys.argv[0])]
        subprocess.Popen(cmd, creationflags=flags, close_fds=True, env=clean_env(), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._close_window()
        return True

    def api_quit(self, force=False):
        self.quit_ok = True
        for j in self.queue.jobs:
            if j.active:
                j.cancel()
        self._close_window()
        return True

    def _close_window(self):
        self.quit_ok = True
        if self.window:
            threading.Timer(0.3, self.window.destroy).start()

    def on_closing(self):
        """Fenster soll schliessen: bei laufenden Exporten erst fragen (Dialog in der Oberflaeche)."""
        if self.quit_ok:
            return True
        active = [j for j in self.queue.jobs if j.active]
        if active:
            self.emit("confirm_quit", {"count": len(active)})
            return False
        if self.upd.get("state") == "ready" and self.upd.get("path"):
            try:
                updater.install(self.upd["path"], restart=False)
            except Exception:
                pass
        return True
