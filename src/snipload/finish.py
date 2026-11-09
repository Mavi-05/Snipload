"""Abschluss-Durchgang: aus dem geladenen Abschnitt das fertige Video machen - in EINEM ffmpeg-Lauf.

Reihenfolge der Bildfilter:
  Layout (Original / 9:16 / Blur / Facecam-Split / Facecam 1:1) -> Zielgroesse -> Farbe/Schaerfe -> Tempo -> FPS
  -> Chat-Overlay -> Untertitel -> Ein-/Ausblenden
Ton: Tempo -> Lautstaerke -> Lautheit angleichen -> Ein-/Ausblenden (oder stumm)
"""
import json
import math
import os
import subprocess

from . import tools
from .util import NO_WINDOW, clean_env


def probe(path):
    """Breite, Hoehe, fps, Dauer, Ton vorhanden? (ffprobe)"""
    exe = tools.find_tool("ffprobe")
    out = {"w": None, "h": None, "fps": 30.0, "duration": None, "audio": False}
    if not exe:
        size = tools.probe_size(path)
        if size:
            out["w"], out["h"] = size
        out["audio"] = True
        return out
    try:
        r = subprocess.run([exe, "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                           capture_output=True, timeout=30, creationflags=NO_WINDOW, env=clean_env(),
                           stdin=subprocess.DEVNULL)
        data = json.loads(r.stdout or b"{}")
    except Exception:
        return out
    for s in data.get("streams") or []:
        if s.get("codec_type") == "video" and out["w"] is None and s.get("disposition", {}).get("attached_pic") != 1:
            out["w"], out["h"] = s.get("width"), s.get("height")
            try:
                n, d = (s.get("avg_frame_rate") or s.get("r_frame_rate") or "30/1").split("/")
                out["fps"] = float(n) / float(d) if float(d) else 30.0
            except Exception:
                pass
        elif s.get("codec_type") == "audio":
            out["audio"] = True
    try:
        out["duration"] = float((data.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        pass
    return out


def needs_finish(job):
    sp = job.spec or {}
    if job.kind == "audio":
        return any(sp.get(k) for k in ("speed_on", "normalize", "volume_db", "fade_in", "fade_out"))
    if job.aspect != "original":
        return True
    keys = ("captions", "chat_burn", "upscale", "eq", "sharpen", "fade_in", "fade_out", "normalize", "volume_db",
            "mute", "fps", "size_mb", "codec_hevc")
    if any(_on(sp, k) for k in keys):
        return True
    return float(sp.get("speed") or 1.0) != 1.0


def _on(sp, key):
    v = sp.get(key)
    if key == "captions":
        return bool(v and v.get("burn", True) and v.get("words"))
    if key == "upscale":
        return bool(v and v.get("target"))
    if key == "eq":
        return bool(v and any(abs(float(v.get(x, 0) or 0)) > 1e-3 for x in ("brightness", "contrast", "saturation")))
    return bool(v)


def target_size(job, src_w, src_h):
    """Endgroesse des Videos (vor Tempo/Overlays)."""
    sp = job.spec or {}
    up = (sp.get("upscale") or {}).get("target")
    if job.aspect in ("crop916", "blur916", "facecam"):
        w = int(up) if up else 1080
        w = {1080: 1080, 1440: 1440, 2160: 2160}.get(w, 1080)
        return w, w * 16 // 9
    if job.aspect == "facecam_raw" and job.cam_px:
        return None    # 1:1 - ergibt sich aus dem Ausschnitt
    if up and src_h:
        th = int(up)
        if th <= src_h:
            return src_w, src_h
        tw = int(round(src_w * th / src_h / 2)) * 2
        return tw, th
    return src_w, src_h


def layout_filter(job, src_w, src_h):
    """-> (Filtertext von [0:v] nach [lay], Breite, Hoehe)"""
    tw_th = target_size(job, src_w, src_h)
    if job.aspect == "facecam_raw" and job.cam_px:
        sx, sy = src_w / job.cam_px["ref_w"], src_h / job.cam_px["ref_h"]
        cx, cy = int(round(job.cam_px["x"] * sx)), int(round(job.cam_px["y"] * sy))
        cw, ch = int(round(job.cam_px["w"] * sx)) // 2 * 2, int(round(job.cam_px["h"] * sy)) // 2 * 2
        cw, ch = min(cw, src_w - cx) // 2 * 2, min(ch, src_h - cy) // 2 * 2
        up = ((job.spec or {}).get("upscale") or {}).get("target")
        f = f"[0:v]crop={cw}:{ch}:{cx}:{cy}"
        if up and int(up) > ch:      # Facecam auf Wunsch hochskalieren (z. B. auf 1080p)
            nh = int(up)
            nw = int(round(cw * nh / ch / 2)) * 2
            f += f",scale={nw}:{nh}:flags=lanczos"
            cw, ch = nw, nh
        return f + ",setsar=1[lay]", cw, ch
    W, H = tw_th
    if job.aspect == "facecam" and job.layout and job.layout.get("cam"):
        from . import facecam
        aspect = src_w / src_h if src_w and src_h else 16 / 9
        g = facecam.ffmpeg_filter(job.layout, aspect)          # endet mit [v], Groesse 1080x1920
        g = g.replace("[0:v]", "[0:v]", 1).replace(",format=yuv420p[v]", "[fc]")
        if W != 1080:
            g += f";[fc]scale={W}:{H}:flags=lanczos,setsar=1[lay]"
        else:
            g += ";[fc]setsar=1[lay]"
        return g, W, H
    if job.aspect == "blur916":
        g = (f"[0:v]split[ba][bb];"
             f"[ba]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
             f"boxblur=luma_radius={max(20, W // 27)}:luma_power=2,eq=brightness=-0.06:saturation=1.15[bbg];"
             f"[bb]scale={W}:{H}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos[bfg];"
             f"[bbg][bfg]overlay=(W-w)/2:(H-h)/2,setsar=1[lay]")
        return g, W, H
    if job.aspect == "crop916":
        x = float((job.spec or {}).get("crop_x", 0.5))
        g = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
             f"crop={W}:{H}:(iw-{W})*{x:.4f}:0,setsar=1[lay]")
        return g, W, H
    # Original (ggf. hochskaliert)
    if (W, H) != (src_w, src_h):
        return f"[0:v]scale={W}:{H}:flags=lanczos,setsar=1[lay]", W, H
    return "[0:v]setsar=1[lay]", W, H


def _atempo(speed):
    """atempo kann nur 0.5..2 je Stufe -> verketten."""
    parts = []
    s = speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def build(job, ffmpeg, src, dst, info, encoder_args, ass_path=None, fonts_dir=None, chat_video=None,
          chat_box=None, bitrate=None):
    """Baut den ffmpeg-Befehl. info: probe(src). Gibt (cmd, out_duration) zurueck."""
    sp = job.spec or {}
    speed = max(0.25, min(4.0, float(sp.get("speed") or 1.0)))
    src_w, src_h = info["w"] or 1920, info["h"] or 1080
    clip_dur = info.get("duration") or job.duration or 0
    out_dur = clip_dur / speed if clip_dur else 0
    cmd = [ffmpeg, "-hide_banner", "-y", "-i", src]
    if chat_video:
        cmd += ["-i", chat_video]
    audio_only = job.kind == "audio"
    vlab = None
    graph = []
    if not audio_only:
        lay, W, H = layout_filter(job, src_w, src_h)
        graph.append(lay)
        cur = "lay"
        chain = []
        eq = sp.get("eq") or {}
        if _on(sp, "eq"):
            chain.append("eq=brightness={:.3f}:contrast={:.3f}:saturation={:.3f}".format(
                float(eq.get("brightness", 0) or 0) * 0.25, 1 + float(eq.get("contrast", 0) or 0) * 0.5,
                1 + float(eq.get("saturation", 0) or 0)))
        if sp.get("sharpen"):
            chain.append("unsharp=5:5:{:.2f}:5:5:0".format(0.4 + 0.8 * float(sp.get("sharpen") or 0)))
        if speed != 1.0:
            chain.append(f"setpts=PTS/{speed:.4f}")
        if sp.get("fps"):
            chain.append(f"fps={int(sp['fps'])}")
        if chain:
            graph.append(f"[{cur}]" + ",".join(chain) + "[pre]")
            cur = "pre"
        if chat_video and chat_box:
            bx, by, bw, bh = chat_box     # Pixel in der Endgroesse
            cv = f"[1:v]scale={bw}:{bh},format=rgba"
            if speed != 1.0:
                cv += f",setpts=PTS/{speed:.4f}"
            graph.append(cv + "[chat]")
            graph.append(f"[{cur}][chat]overlay={bx}:{by}:eof_action=pass:format=auto[ov]")
            cur = "ov"
        post = []
        if ass_path:
            from . import captions
            post.append(captions.ffmpeg_filter(ass_path, fonts_dir))
        fi, fo = float(sp.get("fade_in") or 0), float(sp.get("fade_out") or 0)
        if fi > 0:
            post.append(f"fade=t=in:st=0:d={fi:.2f}")
        if fo > 0 and out_dur:
            post.append(f"fade=t=out:st={max(0.0, out_dur - fo):.3f}:d={fo:.2f}")
        post.append("format=yuv420p")
        graph.append(f"[{cur}]" + ",".join(post) + "[vout]")
        vlab = "vout"
    alab = None
    if info.get("audio") and not sp.get("mute"):
        ach = []
        if speed != 1.0:
            ach.append(_atempo(speed))
        vol = float(sp.get("volume_db") or 0)
        if vol:
            ach.append(f"volume={vol:.1f}dB")
        if sp.get("normalize"):
            ach.append("loudnorm=I=-14:TP=-1.0:LRA=11")
        fi, fo = float(sp.get("fade_in") or 0), float(sp.get("fade_out") or 0)
        if fi > 0:
            ach.append(f"afade=t=in:st=0:d={fi:.2f}")
        if fo > 0 and out_dur:
            ach.append(f"afade=t=out:st={max(0.0, out_dur - fo):.3f}:d={fo:.2f}")
        if ach:
            graph.append("[0:a]" + ",".join(ach) + ",aresample=48000[aout]")
            alab = "aout"
        else:
            alab = "0:a"
    if graph:
        cmd += ["-filter_complex", ";".join(graph)]
    if vlab:
        cmd += ["-map", f"[{vlab}]"]
    if alab:
        cmd += ["-map", f"[{alab}]" if alab == "aout" else alab]
    if audio_only:
        fmt = job.audio_fmt
        cmd += {"mp3": ["-c:a", "libmp3lame", "-q:a", "0"], "m4a": ["-c:a", "aac", "-b:a", "256k"],
                "wav": ["-c:a", "pcm_s16le"]}.get(fmt, ["-c:a", "aac", "-b:a", "256k"])
        cmd += ["-vn"]
    else:
        if bitrate:
            # Zielgroesse: feste Bitrate mit CPU-Encoder (verlaessliche Groesse)
            kb = int(bitrate)
            cmd += ["-c:v", "libx264", "-preset", "medium", "-b:v", f"{kb}k", "-maxrate", f"{int(kb * 1.25)}k",
                    "-bufsize", f"{kb * 2}k", "-pix_fmt", "yuv420p"]
        elif sp.get("codec_hevc"):
            cmd += ["-c:v", "libx265", "-preset", "fast", "-crf", "22", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"]
        else:
            cmd += list(encoder_args)
        if alab:
            ab = "128k" if bitrate else "192k"
            cmd += ["-c:a", "aac", "-b:a", ab]
        cmd += ["-movflags", "+faststart"]
    cmd += ["-progress", "pipe:1", "-nostats", dst]
    return cmd, out_dur


def size_bitrate(size_mb, duration, audio=True):
    """Video-Bitrate (kbit/s) fuer eine Zieldatei von size_mb Megabyte."""
    if not duration or duration <= 0:
        return None
    total_kbit = size_mb * 8 * 1024 * 0.94      # 6 % Reserve fuer Container
    a = 128 * duration if audio else 0
    v = (total_kbit - a) / duration
    return max(80, int(v))


def gif_cmd(ffmpeg, src, dst, fps=15, width=480, start=None, duration=None):
    f = (f"fps={fps},scale={width}:-2:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff:max_colors=200[p];"
         f"[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
    cmd = [ffmpeg, "-hide_banner", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", src]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    return cmd + ["-filter_complex", f, "-loop", "0", "-progress", "pipe:1", "-nostats", dst]


def scale_factor_for_ai(job, src_w, src_h):
    """Wie stark muss die KI hochskalieren, damit der genutzte Bildbereich die Zielgroesse erreicht? (2/3/4)"""
    tw_th = target_size(job, src_w, src_h)
    if job.aspect == "facecam_raw" and job.cam_px:
        up = ((job.spec or {}).get("upscale") or {}).get("target") or 1080
        need = int(up) / max(1, job.cam_px["h"] * src_h / job.cam_px["ref_h"])
    elif job.aspect in ("crop916", "facecam"):
        W, H = tw_th
        need = H / src_h          # 9:16 aus 16:9: die Hoehe bestimmt
        if job.aspect == "facecam" and job.layout and job.layout.get("cam"):
            cam_h = job.layout["cam"][3] * src_h
            need = max(need, (W * 9 / 16) / max(1.0, cam_h))
    else:
        W, H = tw_th
        need = H / src_h
    if need <= 1.05:
        return 1
    return min(4, max(2, int(math.ceil(need))))
