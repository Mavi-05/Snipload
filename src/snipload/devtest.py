"""Echte Probe aufs Exempel fuer den GitHub-Build (Snipload.exe --nettest ergebnis.txt).

Laeuft auf einem echten Windows mit Internet und prueft, was sich am Entwicklungsrechner nicht pruefen laesst:
Werkzeuge herunterladen, Twitch (Suche, Kanal, VOD, Chat), YouTube, Untertitel einbrennen, Chat rendern, KI-Untertitel.
Jede Zeile beginnt mit OK, FEHLER oder INFO. Der Test darf fehlschlagen, ohne den Build anzuhalten (z. B. wenn YouTube
die Adresse des Build-Rechners sperrt) - er dient zum Nachsehen.
"""
import os
import subprocess
import tempfile
import time
import traceback


def run(out_path):
    lines = []

    def log(s):
        lines.append(s)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def step(name, fn):
        t0 = time.time()
        try:
            res = fn()
            log(f"OK     {name}: {res} ({time.time() - t0:.1f} s)")
            return res
        except Exception as ex:  # noqa
            tb = traceback.format_exc().strip().splitlines()
            log(f"FEHLER {name}: {ex!r} | {' / '.join(tb[-3:])[:400]}")
            return None

    from . import captions, chat, finish, search, tools
    from .jobs import Job
    from .util import NO_WINDOW, clean_env

    work = tempfile.mkdtemp(prefix="snipload_test_")

    # ---------------------------------------------------------------- Werkzeuge
    def get_tools():
        failed = tools.install(["yt-dlp", "ffmpeg"])
        if failed:
            raise RuntimeError("nicht geladen: " + ", ".join(failed))
        return f"yt-dlp {tools.ytdlp_version()}, ffmpeg {str(tools.ffmpeg_version())[:30]}"
    step("Werkzeuge laden", get_tools)
    ffmpeg = tools.find_tool("ffmpeg")

    # ---------------------------------------------------------------- Twitch
    state = {}

    def tw_search():
        items = search.twitch_search("shroud")
        state["login"] = items[0]["handle"]
        return f"{len(items)} Kanaele, erster: {items[0]['title']} ({items[0].get('followers')} Follower, live={items[0]['live']})"
    step("Twitch-Suche", tw_search)

    def tw_channel():
        best = None
        for login in [state.get("login") or "shroud", "esl_csgo", "riotgames", "gronkh"]:
            res = search.twitch_channel(login, "archives")
            if res["items"]:
                best = res
                break
        if not best:
            raise RuntimeError("kein Kanal mit VODs gefunden")
        v = best["items"][0]
        state["vod"] = v["id"]
        state["vod_url"] = v["url"]
        state["owner"] = best["channel"]["id"]
        return f"{best['channel']['title']}: {len(best['items'])} VODs, erstes: {v['title'][:40]!r} {v['duration']} s, Tabs {best['tabs']}"
    step("Twitch-Kanal", tw_channel)

    def tw_clips():
        res = search.twitch_channel(state.get("owner") or "shroud", "clips_all")
        c = res["items"][0]
        state["clip_url"] = c["url"]
        return f"{len(res['items'])} Clips, erster: {c['title'][:40]!r} {c['duration']} s vod={c.get('vod')}"
    step("Twitch-Clips", tw_clips)

    def tw_meta():
        m = search.twitch_vod_meta(state["vod"])
        sb = m.get("storyboard") or {}
        return f"Storyboard {sb.get('cols')}x{sb.get('rows')} je {sb.get('interval')} s, {len(sb.get('sheets') or [])} Blaetter, {len(m['chapters'])} Kapitel, Besitzer {m.get('owner')}"
    step("Twitch-VOD-Infos", tw_meta)

    def tw_chat():
        msgs = chat.twitch_comments(state["vod"], 600, 900)
        state["msgs"] = msgs
        ex = msgs[0] if msgs else {}
        return f"{len(msgs)} Nachrichten in 5 min, Beispiel: {ex.get('user')}: {ex.get('parts')}"[:300]
    step("Twitch-Chat", tw_chat)

    def tw_extras():
        m = search.twitch_vod_meta(state["vod"])
        owner = m.get("owner") or {}
        em = chat.third_party_emotes(owner.get("id"))
        bd = chat.twitch_badges(owner.get("login") or "")
        state["badges"] = bd
        return f"{len(em)} Emotes (7TV/BTTV/FFZ), {len(bd)} Abzeichen"
    step("Twitch-Emotes und -Abzeichen", tw_extras)

    def tw_info():
        info = tools.fetch_info(state["vod_url"])
        fmts = [f for f in info.get("formats") or [] if f.get("vcodec") not in (None, "none")]
        return f"{info.get('title', '')[:40]!r} {info.get('duration')} s, {len(fmts)} Formate, Protokolle {sorted({f.get('protocol') for f in fmts})}"
    step("Twitch-VOD ueber yt-dlp", tw_info)

    def tw_clip_info():
        info = tools.fetch_info(state["clip_url"])
        fmts = [f for f in info.get("formats") or [] if f.get("vcodec") not in (None, "none")]
        return f"{info.get('title', '')[:40]!r} {info.get('duration')} s, Formate {[(f.get('format_id'), f.get('protocol'), f.get('acodec')) for f in fmts][:4]}"
    step("Twitch-Clip ueber yt-dlp", tw_clip_info)

    # ---------------------------------------------------------------- YouTube (kann am Build-Rechner gesperrt sein)
    def yt_search():
        items = search.youtube_search("minecraft speedrun", "videos")
        state["yt"] = items[0]["url"]
        return f"{len(items)} Videos, erstes: {items[0]['title'][:50]!r} von {items[0]['channel']}"
    step("YouTube-Suche", yt_search)

    def yt_channels():
        items = search.youtube_search("mrbeast", "channels")
        return f"{len(items)} Kanaele, erster: {items[0]['title']} ({items[0].get('followers')}), Bild: {bool(items[0].get('avatar'))}"
    step("YouTube-Kanalsuche", yt_channels)

    def yt_channel():
        res = search.youtube_channel("@MrBeast", "videos")
        ch = res["channel"]
        return f"{ch['title']}: {len(res['items'])} Videos, {ch.get('followers')} Abos, Bild {bool(ch.get('avatar'))}"
    step("YouTube-Kanal", yt_channel)

    def yt_info():
        info = tools.fetch_info(state.get("yt") or "https://www.youtube.com/watch?v=jNQXAC9IVRw")
        fmts = [f for f in info.get("formats") or [] if f.get("vcodec") not in (None, "none")]
        sb = [f for f in info.get("formats") or [] if str(f.get("format_id", "")).startswith("sb")]
        return (f"{info.get('title', '')[:40]!r} {info.get('duration')} s, {len(fmts)} Formate, {len(sb)} Storyboards, "
                f"Heatmap {len(info.get('heatmap') or [])}, Untertitel {len(captions.sources(info))}")
    step("YouTube-Video ueber yt-dlp", yt_info)

    # ---------------------------------------------------------------- Rendern (Windows-Pfade, Schriften, Chat)
    src = os.path.join(work, "quelle.mp4")

    def make_src():
        r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=4",
                            "-f", "lavfi", "-i", "sine=f=440:d=4", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", src], capture_output=True, creationflags=NO_WINDOW, env=clean_env())
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode("utf-8", "replace")[-300:])
        return f"{os.path.getsize(src)} Bytes"
    step("Testvideo erzeugen", make_src)

    def render():
        words = [{"w": w, "t0": 0.2 + i * 0.4, "t1": 0.6 + i * 0.4} for i, w in enumerate("this is a caption test for snipload".split())]
        style = dict(captions.PRESETS["beast"])
        job = Job("x", {"duration": 4}, 0, 4, "video", "best", "mp3", "crop916", True, work, "ergebnis",
                  spec={"captions": {"words": words, "style": style, "burn": True}, "speed": 1.25, "fade_in": 0.3})
        info = finish.probe(src)
        lay, W, H = finish.layout_filter(job, info["w"], info["h"])
        ass = os.path.join(work, "cap test.ass")          # Leerzeichen im Pfad: so wie bei echten Dateinamen
        with open(ass, "w", encoding="utf-8") as f:
            f.write(captions.build_ass(words, style, W, H, speed=1.25))
        fonts = captions.fonts_dir_for(style, work)
        msgs = state.get("msgs") or [{"t": 0.5, "user": "mavi", "color": "#ff7a7a", "parts": [{"t": "hello chat"}], "badges": []}]
        t0 = msgs[0]["t"]
        chat_mov = os.path.join(work, "chat.mov")
        chat.render(msgs, chat_mov, 4, dict(chat.DEFAULT_STYLE), fmt="png", start=t0, badge_urls=state.get("badges"), ffmpeg=ffmpeg)
        name, enc = tools.video_encoder(allow_hw=True)
        dst = os.path.join(work, "ergebnis.mp4")
        cmd, dur = finish.build(job, ffmpeg, src, dst, info, enc, ass, fonts, chat_mov, (40, 1100, 440, 700))
        r = subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW, env=clean_env())
        if r.returncode != 0 or not os.path.exists(dst):
            raise RuntimeError(r.stderr.decode("utf-8", "replace")[-500:])
        p = finish.probe(dst)
        alpha = os.path.join(work, "chat alpha.mov")
        chat.render(msgs, alpha, 4, dict(chat.DEFAULT_STYLE, width=840, height=1440, font_size=44), fmt="mov", start=t0,
                    badge_urls=state.get("badges"), ffmpeg=ffmpeg)
        return f"{p['w']}x{p['h']} {p['duration']:.2f} s mit {name}, Chat-Datei {os.path.getsize(alpha) // 1024} KB"
    step("9:16 mit Untertiteln und Chat rendern", render)

    # ---------------------------------------------------------------- KI-Untertitel (whisper.cpp)
    def whisper():
        captions.install_whisper()
        captions.install_model("fast")
        wav = os.path.join(work, "sprache.wav")
        ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SetOutputToWaveFile('{wav}'); $s.Speak('Hello everyone, this is a test of the caption feature in Snipload.'); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=NO_WINDOW, timeout=120)
        if not os.path.exists(wav):
            raise RuntimeError("keine Sprachausgabe auf diesem Rechner")
        wav16 = os.path.join(work, "sprache16.wav")
        captions.extract_audio(wav, wav16, ffmpeg)
        res = captions.transcribe(wav16, "fast", "en", False)
        text = " ".join(w["w"] for w in res["words"])
        if "test" not in text.lower():
            raise RuntimeError(f"unerwarteter Text: {text!r}")
        return f"{len(res['words'])} Woerter: {text!r}, erste Zeiten {[(w['t0'], w['t1']) for w in res['words'][:3]]}"
    step("KI-Untertitel", whisper)

    def esrgan():
        from . import upscale
        upscale.install_esrgan()
        exe = upscale.esrgan_exe()
        models = [f for f in os.listdir(os.path.join(os.path.dirname(exe), "models"))] if exe else []
        return f"{os.path.basename(exe)}, {len(models)} Modelldateien, Topaz: {upscale.topaz_ffmpeg()}"
    step("KI-Hochskalierer laden", esrgan)

    def editors_found():
        from . import editors
        return [e["name"] for e in editors.detect([])]
    step("Schnittprogramme", editors_found)

    log("ENDE")
    return 0
