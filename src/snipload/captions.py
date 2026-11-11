"""Untertitel: Woerter mit Zeiten holen (YouTube oder KI), in Zeilen teilen, als animierte ASS-Untertitel
einbrennen (wie die Untertitel-Vorlagen in Premiere/CapCut) oder als .srt speichern.

Ein Wort:  {"w": "Hallo", "t0": 1.23, "t1": 1.61}   (Sekunden ab Clip-Start)
Eine Zeile: {"t0", "t1", "words": [...]}
"""
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile

from . import tools
from .util import NO_WINDOW, IS_WIN, clean_env, web_path

WHISPER_VERSION = "v1.8.2"
WHISPER_ZIP = "https://github.com/ggml-org/whisper.cpp/releases/download/{v}/whisper-blas-bin-x64.zip"
MODELS = {
    # Name: (Datei, ungefaehre Groesse in MB)
    "fast": ("ggml-base.bin", 142),
    "balanced": ("ggml-small.bin", 466),
    "best": ("ggml-large-v3-turbo-q5_0.bin", 547),
}
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{name}"

FONTS_DIR = web_path("fonts")
# Anzeigename -> (Schriftname fuer libass, Datei, CSS-Familie)
FONTS = {
    "Montserrat Black": ("Montserrat Black", "Montserrat-Black.ttf"),
    "Montserrat ExtraBold": ("Montserrat ExtraBold", "Montserrat-ExtraBold.ttf"),
    "Poppins Black": ("Poppins Black", "Poppins-Black.ttf"),
    "Poppins ExtraBold": ("Poppins ExtraBold", "Poppins-ExtraBold.ttf"),
    "Bebas Neue": ("Bebas Neue", "BebasNeue-Regular.ttf"),
    "Anton": ("Anton", "Anton-Regular.ttf"),
    "Bangers": ("Bangers", "Bangers-Regular.ttf"),
    "Luckiest Guy": ("Luckiest Guy", "LuckiestGuy-Regular.ttf"),
    "Archivo Black": ("Archivo Black", "ArchivoBlack-Regular.ttf"),
    "Kanit Black": ("Kanit Black", "Kanit-Black.ttf"),
    "Inter": ("Inter", "Inter.ttf"),
}

DEFAULT_STYLE = {
    "preset": "bold", "font": "Montserrat Black", "size": 7.0, "color": "#ffffff", "hl_color": "#ffd400",
    "hl_mode": "color", "outline": 8.0, "outline_color": "#000000", "shadow": 3.0, "shadow_color": "#000000",
    "box": False, "box_color": "#000000", "box_opacity": 0.6, "uppercase": True, "pos": 72.0,
    "words": 3, "lines": 1, "anim": "pop", "word_pop": True, "dim_upcoming": False, "spacing": 0.0,
}

PRESETS = {
    "bold": dict(DEFAULT_STYLE),
    "hormozi": dict(DEFAULT_STYLE, preset="hormozi", font="Montserrat Black", hl_color="#4ade80", words=3,
                    outline=10, shadow=0, size=7.5),
    "beast": dict(DEFAULT_STYLE, preset="beast", font="Luckiest Guy", hl_color="#ff3b3b", size=8.0, outline=11,
                  shadow=5, words=2),
    "karaoke": dict(DEFAULT_STYLE, preset="karaoke", font="Poppins Black", color="#ffffff", hl_color="#38bdf8",
                    hl_mode="color", dim_upcoming=True, words=5, lines=2, size=6.0, anim="fade", word_pop=False,
                    uppercase=False),
    "boxed": dict(DEFAULT_STYLE, preset="boxed", font="Poppins ExtraBold", hl_mode="box", hl_color="#7c5cff",
                  outline=4, shadow=0, words=3, size=6.6, uppercase=False),
    "clean": dict(DEFAULT_STYLE, preset="clean", font="Inter", hl_mode="none", color="#ffffff", outline=0,
                  shadow=0, box=True, box_opacity=0.55, uppercase=False, words=7, lines=2, size=4.6, pos=82,
                  anim="fade", word_pop=False),
    "cinema": dict(DEFAULT_STYLE, preset="cinema", font="Bebas Neue", hl_mode="none", color="#fff7e6",
                   outline=3, shadow=4, words=6, size=6.4, pos=86, anim="fade", word_pop=False, uppercase=True),
    "comic": dict(DEFAULT_STYLE, preset="comic", font="Bangers", hl_color="#ff2e93", size=8.5, outline=9,
                  shadow=6, words=2, spacing=2),
}


class CaptionError(Exception):
    pass


# ================================================================ Quellen
def sources(info):
    """Welche Untertitel bietet das Video? -> [{"id", "lang", "name", "auto"}] (manuelle zuerst)."""
    out = []
    raw = info or {}
    for auto, key in ((False, "subtitles"), (True, "automatic_captions")):
        subs = raw.get(key) or {}
        for lang, fmts in subs.items():
            if lang in ("live_chat", "rechat") or not isinstance(fmts, list):
                continue
            if auto and not lang.endswith("-orig") and "-" in lang and len(out) > 30:
                continue
            if not any((f or {}).get("ext") in ("json3", "vtt", "srv3") for f in fmts):
                continue
            name = next((f.get("name") for f in fmts if f.get("name")), lang)
            out.append({"id": f"{'auto' if auto else 'sub'}:{lang}", "lang": lang, "name": name, "auto": auto})
    # Automatische: nur Originalsprache (-orig) und die wichtigsten, sonst sind es >100 Uebersetzungen
    manual = [s for s in out if not s["auto"]]
    auto = [s for s in out if s["auto"]]
    orig = [s for s in auto if s["lang"].endswith("-orig")]
    keep = orig + [s for s in auto if s["lang"] in ("en", "de", "es", "fr", "pt", "ja", "ko", "tr", "ru", "zh-Hans")
                   and s not in orig]
    return manual + keep[:12]


def parse_json3(data, start=0.0, end=None):
    """YouTube-json3 -> Woerter. Automatische Untertitel haben Zeiten je Wort, manuelle nur je Zeile."""
    words = []
    events = [e for e in data.get("events") or [] if e.get("segs")]
    for idx, ev in enumerate(events):
        t0 = (ev.get("tStartMs") or 0) / 1000.0
        dur = (ev.get("dDurationMs") or 0) / 1000.0
        segs = [s for s in ev["segs"] if (s.get("utf8") or "").strip()]
        if not segs:
            continue
        if any("tOffsetMs" in s for s in segs) or len(segs) > 1:
            for i, s in enumerate(segs):
                st = t0 + (s.get("tOffsetMs") or 0) / 1000.0
                if i + 1 < len(segs):
                    en = t0 + (segs[i + 1].get("tOffsetMs") or 0) / 1000.0
                else:
                    en = t0 + dur if dur else st + 0.4
                    if idx + 1 < len(events):
                        en = min(en, (events[idx + 1].get("tStartMs") or 0) / 1000.0)
                for w in s["utf8"].split():
                    words.append({"w": w, "t0": st, "t1": max(st + 0.05, en)})
        else:
            # ganze Zeile ohne Wortzeiten: gleichmaessig verteilen
            toks = segs[0]["utf8"].split()
            n = max(1, len(toks))
            for i, w in enumerate(toks):
                a = t0 + dur * i / n
                words.append({"w": w, "t0": a, "t1": a + dur / n})
    words.sort(key=lambda w: w["t0"])
    out = []
    for w in words:
        if w["t1"] <= start or (end is not None and w["t0"] >= end):
            continue
        out.append({"w": w["w"], "t0": round(max(0.0, w["t0"] - start), 3),
                    "t1": round(max(0.05, min(w["t1"], end if end is not None else w["t1"]) - start), 3)})
    # Ueberlappungen glaetten
    for a, b in zip(out, out[1:]):
        if a["t1"] > b["t0"]:
            a["t1"] = b["t0"]
    return out


def fetch_youtube(url, source_id, start, end, workdir):
    """Untertitel eines YouTube-Videos fuer den Abschnitt holen."""
    kind, lang = source_id.split(":", 1)
    base = tools.ytdlp_cmd()
    if not base:
        raise CaptionError("yt-dlp missing")
    out = os.path.join(workdir, "subs")
    cmd = base + tools.cookie_args() + ["--skip-download", "--no-playlist", "--sub-format", "json3",
                                        "--sub-langs", lang, "-o", out, "--no-warnings"]
    cmd.append("--write-auto-subs" if kind == "auto" else "--write-subs")
    cmd.append(url)
    r = tools.run(cmd, 120)
    files = glob.glob(out + "*.json3")
    if not files:
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise CaptionError(tools.friendly_error(err[-1]) if err else "no captions")
    with open(files[0], encoding="utf-8") as f:
        return parse_json3(json.load(f), start, end)


# ================================================================ KI (whisper.cpp)
def _wdir():
    d = os.path.join(tools.own_dir(), "whisper")
    os.makedirs(d, exist_ok=True)
    return d


def whisper_exe():
    if not IS_WIN:
        exe = shutil.which("whisper-cli")
        return exe
    for p in glob.glob(os.path.join(_wdir(), "**", "whisper-cli.exe"), recursive=True):
        return p
    return None


def model_path(model):
    name = MODELS.get(model, MODELS["balanced"])[0]
    p = os.path.join(_wdir(), "models", name)
    return p if os.path.isfile(p) and os.path.getsize(p) > 10_000_000 else None


def status():
    return {"engine": bool(whisper_exe()),
            "models": {k: {"file": v[0], "mb": v[1], "ready": bool(model_path(k))} for k, v in MODELS.items()}}


def install_whisper(progress=None):
    """whisper.cpp (Windows, CPU mit BLAS) herunterladen und entpacken."""
    if whisper_exe():
        return True
    if not IS_WIN:
        raise CaptionError("whisper-cli not found")
    tmp = os.path.join(tempfile.gettempdir(), "snipload_whisper.zip")
    tools._fetch(WHISPER_ZIP.format(v=WHISPER_VERSION), tmp, progress, 60)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(_wdir())
    os.remove(tmp)
    if not whisper_exe():
        raise CaptionError("whisper-cli.exe not found in the download")
    return True


def install_model(model, progress=None):
    if model_path(model):
        return True
    name = MODELS.get(model, MODELS["balanced"])[0]
    d = os.path.join(_wdir(), "models")
    os.makedirs(d, exist_ok=True)
    tools._fetch(MODEL_URL.format(name=name), os.path.join(d, name), progress, 120)
    if not model_path(model):
        raise CaptionError("model download incomplete")
    return True


def extract_audio(src, dst_wav, ffmpeg=None, start=None, end=None):
    ffmpeg = ffmpeg or tools.find_tool("ffmpeg")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", src]
    if end is not None and start is not None:
        cmd += ["-t", f"{end - start:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst_wav]
    r = subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW, env=clean_env(), stdin=subprocess.DEVNULL)
    if r.returncode != 0 or not os.path.exists(dst_wav):
        raise CaptionError((r.stderr or b"").decode("utf-8", "replace")[-300:] or "audio extraction failed")
    return dst_wav


def transcribe(wav, model="balanced", lang="auto", translate=False, progress=None, cancel=None):
    """whisper.cpp -> Woerter mit Zeiten (Sekunden ab Anfang der wav)."""
    exe = whisper_exe()
    mp = model_path(model)
    if not exe or not mp:
        raise CaptionError("whisper not installed")
    out = os.path.splitext(wav)[0] + "_w"
    threads = max(2, min(16, (os.cpu_count() or 4)))
    cmd = [exe, "-m", mp, "-f", wav, "-l", lang or "auto", "-oj", "-of", out, "-ml", "1", "-sow", "-pp",
           "-t", str(threads)]
    if translate:
        cmd.append("-tr")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
                         env=clean_env(), stdin=subprocess.DEVNULL, cwd=os.path.dirname(exe))
    tail = []
    for raw in iter(p.stdout.readline, b""):
        line = raw.decode("utf-8", "replace").strip()
        tail = (tail + [line])[-8:]
        m = re.search(r"progress\s*=\s*(\d+)%", line)
        if m and progress:
            progress(int(m.group(1)) / 100.0)
        if cancel and cancel():
            p.kill()
            raise CaptionError("cancelled")
    p.wait()
    jf = out + ".json"
    if p.returncode != 0 or not os.path.exists(jf):
        raise CaptionError("whisper failed: " + " | ".join(tail[-3:]))
    with open(jf, encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    words = []
    for seg in data.get("transcription") or []:
        txt = (seg.get("text") or "").strip()
        off = seg.get("offsets") or {}
        t0, t1 = (off.get("from") or 0) / 1000.0, (off.get("to") or 0) / 1000.0
        if not txt or re.fullmatch(r"\[.*\]|\(.*\)|♪+", txt):
            continue
        if words and (re.fullmatch(r"[^\w\s]+", txt) or txt.startswith("'")):
            words[-1]["w"] += txt                 # Satzzeichen ans vorige Wort
            words[-1]["t1"] = max(words[-1]["t1"], t1)
            continue
        words.append({"w": txt, "t0": round(t0, 3), "t1": round(max(t1, t0 + 0.05), 3)})
    return {"words": words, "lang": (data.get("result") or {}).get("language")}


# ================================================================ Schriften: mitgeliefert, System, eigene
_ratio_cache = {}
_pil_cache = {}
_extra = {}          # Anzeigename -> (libass-Name, Datei) fuer System-/eigene Schriften


def _read_names(path):
    """(Familie, Untername, Vollname) aus der name-Tabelle einer TTF/OTF-Datei."""
    import struct
    with open(path, "rb") as f:
        data = f.read(4 * 1024 * 1024)
    if data[:4] == b"ttcf":
        off = struct.unpack(">I", data[12:16])[0]
    else:
        off = 0
    n = struct.unpack(">H", data[off + 4:off + 6])[0]
    tbl = None
    for i in range(n):
        tag, _c, o, _l = struct.unpack(">4sIII", data[off + 12 + 16 * i:off + 28 + 16 * i])
        if tag == b"name":
            tbl = o
    if tbl is None:
        return None
    count, sto = struct.unpack(">HH", data[tbl + 2:tbl + 6])
    names = {}
    for i in range(count):
        pid, eid, lid, nid, ln, no = struct.unpack(">HHHHHH", data[tbl + 6 + 12 * i:tbl + 18 + 12 * i])
        if nid not in (1, 2, 4, 16, 17):
            continue
        raw = data[tbl + sto + no:tbl + sto + no + ln]
        if pid == 3 and lid in (0x409, 0):
            txt = raw.decode("utf-16-be", "ignore")
        elif pid == 1 and nid not in names:
            txt = raw.decode("latin-1", "ignore")
        else:
            continue
        if pid == 3 or nid not in names:
            names[nid] = txt
    fam = names.get(1)
    if not fam:
        return None
    return fam, names.get(2, "Regular"), names.get(4, fam)


def system_fonts():
    """Installierte Schriften (Windows: Systemordner + Benutzerordner) und eigene Schriften von Snipload.
    -> [{"name": Anzeigename, "family", "style", "file", "source": system|user}]"""
    dirs = []
    if IS_WIN:
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(os.path.join(windir, "Fonts"))
        la = os.environ.get("LOCALAPPDATA")
        if la:
            dirs.append(os.path.join(la, "Microsoft", "Windows", "Fonts"))
    else:
        dirs += ["/usr/share/fonts", os.path.expanduser("~/.fonts")]
    dirs.append(user_fonts_dir())
    out, seen = [], set()
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if not fn.lower().endswith((".ttf", ".otf", ".ttc")):
                    continue
                path = os.path.join(root, fn)
                try:
                    r = _read_names(path)
                except Exception:
                    r = None
                if not r:
                    continue
                fam, sub, full = r
                if full in seen or fam.startswith((".", "@")):
                    continue
                seen.add(full)
                out.append({"name": full, "family": fam, "style": sub, "file": path,
                            "source": "user" if d == user_fonts_dir() else "system"})
    out.sort(key=lambda x: (x["family"].lower(), x["style"] != "Regular", x["name"].lower()))
    return out


def user_fonts_dir():
    from .util import config_dir
    d = os.path.join(config_dir(), "fonts")
    os.makedirs(d, exist_ok=True)
    return d


def add_user_font(path):
    """Eigene Schriftdatei uebernehmen (wird in den Snipload-Ordner kopiert)."""
    r = _read_names(path)
    if not r:
        raise CaptionError("not a font file")
    dst = os.path.join(user_fonts_dir(), os.path.basename(path))
    if os.path.abspath(dst) != os.path.abspath(path):
        shutil.copyfile(path, dst)
    register_font(r[2], dst)
    return {"name": r[2], "family": r[0], "style": r[1], "file": dst, "source": "user"}


def register_font(name, file):
    """System-/eigene Schrift fuer diese Sitzung bekannt machen (libass sucht nach dem Vollnamen)."""
    if name in FONTS:
        return name
    try:
        r = _read_names(file)
        full = r[2] if r else name
    except Exception:
        full = name
    _extra[name] = (full, file)
    return name


def font_entry(font):
    if font in FONTS:
        fam, fn = FONTS[font]
        return fam, os.path.join(FONTS_DIR, fn)
    if font in _extra:
        return _extra[font]
    fam, fn = FONTS["Montserrat Black"]
    return fam, os.path.join(FONTS_DIR, fn)


def font_file(font):
    return font_entry(font)[1]


def win_ratio(font):
    """libass rechnet die Schriftgroesse ueber usWinAscent+usWinDescent, CSS/PIL ueber das Em.
    Faktor Em / (WinAscent+WinDescent) direkt aus der TTF-Datei."""
    if font in _ratio_cache:
        return _ratio_cache[font]
    import struct
    r = 0.7
    try:
        with open(font_file(font), "rb") as f:
            data = f.read()
        n = struct.unpack(">H", data[4:6])[0]
        tables = {}
        for i in range(n):
            tag, _c, off, _l = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
            tables[tag] = off
        upem = struct.unpack(">H", data[tables[b"head"] + 18:tables[b"head"] + 20])[0]
        o = tables[b"OS/2"]
        wa, wd = struct.unpack(">HH", data[o + 74:o + 78])
        r = upem / float(wa + wd)
    except Exception:
        pass
    _ratio_cache[font] = r
    return r


def text_width(text, font, em_px, spacing_px=0.0):
    """Breite in Pixeln (fuer den Zeilenumbruch) - gleiche Schriftdatei wie beim Einbrennen."""
    try:
        from PIL import ImageFont
        key = (font, int(em_px))
        f = _pil_cache.get(key)
        if f is None:
            f = _pil_cache[key] = ImageFont.truetype(font_file(font), max(4, int(em_px)))
        return f.getlength(text) + spacing_px * max(0, len(text) - 1)
    except Exception:
        return len(text) * em_px * 0.6


# ================================================================ Zeilen
def group_lines(words, per_line=3, max_chars=None, gap=0.7, fits=None):
    """Woerter -> Zeilen: hoechstens per_line Woerter, Umbruch bei Pausen, Satzende und wenn die Zeile
    nicht mehr ins Bild passt (fits(text) -> bool)."""
    lines, cur = [], []
    max_chars = max_chars or (per_line * 9 + 4)
    for w in words:
        if cur:
            pause = w["t0"] - cur[-1]["t1"]
            chars = sum(len(x["w"]) + 1 for x in cur) + len(w["w"])
            end_of_sentence = re.search(r"[.!?…]$", cur[-1]["w"]) is not None
            too_wide = fits is not None and not fits(" ".join([x["w"] for x in cur] + [w["w"]]))
            if (len(cur) >= per_line or pause > gap or (fits is None and chars > max_chars) or too_wide
                    or (end_of_sentence and len(cur) >= 2)):
                lines.append(cur)
                cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return [{"t0": l[0]["t0"], "t1": l[-1]["t1"], "words": l} for l in lines]


def pages(words, style, fits=None):
    """Zeilen zu 'Seiten' zusammenfassen, die gleichzeitig zu sehen sind (1 oder 2 Zeilen)."""
    lines = group_lines(words, int(style.get("words") or 3), fits=fits)
    n = max(1, int(style.get("lines") or 1))
    out = []
    for i in range(0, len(lines), n):
        grp = lines[i:i + n]
        out.append({"t0": grp[0]["t0"], "t1": grp[-1]["t1"], "lines": [g["words"] for g in grp]})
    # Seite bis kurz vor die naechste stehen lassen (kein Flackern bei kleinen Pausen)
    for a, b in zip(out, out[1:]):
        if 0 < b["t0"] - a["t1"] < 0.5:
            a["t1"] = b["t0"]
    return out


# ================================================================ ASS
def _ass_color(hexcol, alpha=0.0):
    h = (hexcol or "#ffffff").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = int(round(max(0.0, min(1.0, alpha)) * 255))
    return f"&H{a:02X}{b:02X}{g:02X}{r:02X}"


def _ass_time(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text):
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(words, style, width, height, speed=1.0, offset=0.0):
    """Animierte Untertitel als ASS-Text. Groessen sind relativ zur Bildhoehe (wie in der Vorschau)."""
    st = dict(DEFAULT_STYLE, **(style or {}))
    if st.get("font_file") and st["font"] not in FONTS:
        register_font(st["font"], st["font_file"])
    if st["font"] not in FONTS and st["font"] not in _extra:
        st["font"] = "Montserrat Black"
    font = font_entry(st["font"])[0]
    H, W = int(height), int(width)
    em = em_px(st, W, H)                      # Schriftgroesse wie in CSS (Em in Pixeln)
    fs = max(6, round(em / win_ratio(st["font"]), 1))   # in libass-Einheiten
    bord = round(em * float(st["outline"]) / 100, 1)
    shad = round(em * float(st["shadow"]) / 100, 1)
    y = round(H * float(st["pos"]) / 100)
    x = W // 2
    box = bool(st.get("box"))
    primary = _ass_color(st["color"])
    hl = _ass_color(st["hl_color"])
    outline_c = _ass_color(st["outline_color"])
    back = _ass_color(st["box_color"] if box else st["shadow_color"], 1 - float(st["box_opacity"]) if box else 0.35)
    border_style = 3 if box else 1
    if box:
        bord = max(bord, round(em * 0.18, 1))
        outline_c = _ass_color(st["box_color"], 1 - float(st["box_opacity"]))
    spacing = float(st.get("spacing") or 0) * em / 100
    head = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Cap,{font},{fs},{primary},{primary},{outline_c},{back},0,0,0,0,100,100,{spacing:.1f},0,"
        f"{border_style},{bord},{0 if box else shad},5,{int(W * 0.05)},{int(W * 0.05)},0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    ev = []
    sp = float(speed or 1.0)
    up = bool(st.get("uppercase"))
    dim = _ass_color(st["color"], 0.45)
    mode = st.get("hl_mode") or "color"

    def T(t):
        return _ass_time((t - offset) / sp)

    maxw = W * 0.88
    up_case = bool(st.get("uppercase"))

    def fits(text):
        return text_width(text.upper() if up_case else text, st["font"], em, spacing) <= maxw

    for pg in pages(words, st, fits):
        flat = [w for line in pg["lines"] for w in line]
        if not flat:
            continue
        # Zeitfenster: jedes Wort bis zum naechsten Wort aktiv
        spans = []
        for i, w in enumerate(flat):
            a = w["t0"] if i else pg["t0"]
            b = flat[i + 1]["t0"] if i + 1 < len(flat) else pg["t1"]
            if b - a > 0.005:
                spans.append((i, a, b))
        if mode == "none" or not spans:
            spans = [(-1, pg["t0"], pg["t1"])]
        for k, (active, a, b) in enumerate(spans):
            parts = []
            idx = 0
            for li, line in enumerate(pg["lines"]):
                toks = []
                for w in line:
                    txt = _esc(w["w"].upper() if up else w["w"])
                    if idx == active:
                        tag = ""
                        if mode == "color":
                            tag = f"\\1c{hl}"
                        elif mode == "box":
                            tag = f"\\3c{hl}\\bord{max(bord, em * 0.2):.1f}\\shad0"
                        elif mode == "scale":
                            tag = f"\\1c{hl}\\fscx112\\fscy112"
                        if st.get("word_pop") and mode != "none":
                            tag += "\\fscx100\\fscy100\\t(0,70,\\fscx116\\fscy116)\\t(70,150,\\fscx108\\fscy108)"
                        toks.append("{" + tag + "}" + txt + "{\\r}")
                    elif st.get("dim_upcoming") and active >= 0 and idx > active:
                        toks.append("{\\1c" + dim + "}" + txt + "{\\r}")
                    else:
                        toks.append(txt)
                    idx += 1
                parts.append(" ".join(toks))
            text = "\\N".join(parts)
            lead = f"\\an5\\pos({x},{y})"
            if k == 0:
                anim = st.get("anim")
                if anim == "pop":
                    lead += "\\fscx72\\fscy72\\t(0,110,\\fscx104\\fscy104)\\t(110,170,\\fscx100\\fscy100)"
                elif anim == "fade":
                    lead += "\\fad(140,0)"
                elif anim == "slide":
                    lead = f"\\an5\\move({x},{y + int(em * 0.6)},{x},{y},0,140)\\fad(100,0)"
            ev.append(f"Dialogue: 0,{T(a)},{T(b)},Cap,,0,0,0,,{{{lead}}}{text}")
    return "\n".join(head + ev) + "\n"


def em_px(style, width, height):
    """Schriftgroesse (Em) in Pixeln: Prozent der Bildhoehe; im Querformat bezogen auf 9:16-Hoehe."""
    ref = min(float(height), float(width) * 16 / 9)
    return max(6.0, ref * float(style.get("size") or 7) / 100)


def srt(words, style=None, speed=1.0, offset=0.0):
    st = dict(DEFAULT_STYLE, **(style or {}))
    out = []

    def ts(t):
        t = max(0.0, (t - offset) / speed)
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    for i, pg in enumerate(pages(words, dict(st, lines=2, words=max(6, int(st["words"])))), 1):
        text = "\n".join(" ".join(w["w"] for w in line) for line in pg["lines"])
        out.append(f"{i}\n{ts(pg['t0'])} --> {ts(pg['t1'])}\n{text}\n")
    return "\n".join(out)


def fonts_dir_for(style, workdir):
    """Ordner fuer libass: mitgelieferte Schriften + ggf. die gewaehlte System-/eigene Schrift."""
    font = (style or {}).get("font")
    if (style or {}).get("font_file") and font not in FONTS:
        register_font(font, style["font_file"])
    if font in _extra:
        d = os.path.join(workdir, "fonts")
        os.makedirs(d, exist_ok=True)
        for fn in os.listdir(FONTS_DIR):
            if fn.lower().endswith(".ttf"):
                try:
                    shutil.copyfile(os.path.join(FONTS_DIR, fn), os.path.join(d, fn))
                except OSError:
                    pass
        src = _extra[font][1]
        try:
            shutil.copyfile(src, os.path.join(d, os.path.basename(src)))
        except OSError:
            pass
        return d
    return FONTS_DIR


def ffmpeg_filter(ass_path, fonts_dir=None):
    """Filter zum Einbrennen. Pfade fuer den ffmpeg-Filter maskieren (Windows: C\\:/...)."""
    def esc(p):
        p = p.replace("\\", "/")
        return p.replace(":", "\\:").replace("'", "\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")
    return f"subtitles=filename='{esc(ass_path)}':fontsdir='{esc(fonts_dir or FONTS_DIR)}'"
