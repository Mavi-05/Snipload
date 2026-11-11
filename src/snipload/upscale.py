"""Hochskalieren: schnell (Lanczos + Schaerfen, im Abschluss-Durchgang), KI (Real-ESRGAN, laeuft auf jeder
Grafikkarte ueber Vulkan, wird bei Bedarf geladen) oder Topaz Video AI (falls installiert - nutzt dessen ffmpeg).
"""
import glob
import math
import os
import shutil
import subprocess
import tempfile
import time
import zipfile

from . import tools
from .util import NO_WINDOW, IS_WIN, clean_env

ESRGAN_ZIP = ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
              "realesrgan-ncnn-vulkan-20220424-{os}.zip")
MODELS = {
    "video": "realesr-animevideov3",      # schnell, fuer Videos/Spiele gut geeignet (x2/x3/x4)
    "quality": "realesrgan-x4plus",       # langsam, sehr fein (nur x4)
}


class UpscaleError(Exception):
    pass


def _dir():
    d = os.path.join(tools.own_dir(), "realesrgan")
    os.makedirs(d, exist_ok=True)
    return d


def esrgan_exe():
    name = "realesrgan-ncnn-vulkan.exe" if IS_WIN else "realesrgan-ncnn-vulkan"
    for p in glob.glob(os.path.join(_dir(), "**", name), recursive=True):
        return p
    return shutil.which(name)


def install_esrgan(progress=None):
    if esrgan_exe():
        return True
    tmp = os.path.join(tempfile.gettempdir(), "snipload_esrgan.zip")
    tools._fetch(ESRGAN_ZIP.format(os="windows" if IS_WIN else "ubuntu"), tmp, progress, 60)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(_dir())
    os.remove(tmp)
    exe = esrgan_exe()
    if not exe:
        raise UpscaleError("realesrgan-ncnn-vulkan not found in the download")
    if not IS_WIN:
        os.chmod(exe, 0o755)
    return True


# ---------------------------------------------------------------- Topaz Video AI
def topaz_ffmpeg():
    """ffmpeg von Topaz Video AI (Topaz Video). None, wenn nicht installiert."""
    if not IS_WIN:
        return None
    roots = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", r"C:\Program Files")]
    for root in roots:
        for sub in ("Topaz Labs LLC\\Topaz Video AI", "Topaz Labs LLC\\Topaz Video", "Topaz Labs LLC\\Topaz Video AI Beta"):
            p = os.path.join(root, sub, "ffmpeg.exe")
            if os.path.isfile(p):
                return p
    return None


def status():
    return {"esrgan": bool(esrgan_exe()), "topaz": bool(topaz_ffmpeg())}


def _run(cmd, progress_cb=None, total=None, cancel=None, cwd=None, env=None, count_dir=None):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
                         env=env or clean_env(), stdin=subprocess.DEVNULL, cwd=cwd)
    tail = []
    last = 0.0
    while True:
        line = p.stdout.readline()
        if not line:
            if p.poll() is not None:
                break
            continue
        s = line.decode("utf-8", "replace").strip()
        tail = (tail + [s])[-6:]
        if cancel and cancel():
            p.kill()
            raise UpscaleError("cancelled")
        now = time.time()
        if progress_cb and now - last > 0.5:
            last = now
            if count_dir and total:
                progress_cb(min(1.0, len(os.listdir(count_dir)) / total))
            elif s.startswith("out_time_us=") and total:
                try:
                    progress_cb(min(1.0, int(s.split("=")[1]) / 1e6 / total))
                except ValueError:
                    pass
    if p.returncode != 0:
        raise UpscaleError(" | ".join(tail[-3:]) or f"exit {p.returncode}")


def esrgan_video(src, dst, factor, info, model="video", progress=None, cancel=None, ffmpeg=None):
    """Video Bild fuer Bild mit Real-ESRGAN hochskalieren. factor: 2/3/4. Ergebnis: verlustarmes MP4."""
    exe = esrgan_exe()
    if not exe:
        raise UpscaleError("Real-ESRGAN not installed")
    ffmpeg = ffmpeg or tools.find_tool("ffmpeg")
    name = MODELS.get(model, MODELS["video"])
    if name == "realesrgan-x4plus":
        factor = 4
    factor = int(min(4, max(2, factor)))
    fps = info.get("fps") or 30.0
    dur = info.get("duration") or 0
    work = tempfile.mkdtemp(prefix="snipload_up_")
    fin, fout = os.path.join(work, "in"), os.path.join(work, "out")
    os.makedirs(fin)
    os.makedirs(fout)
    try:
        # 1) Bilder herausziehen (JPEG hoher Qualitaet spart Platz)
        _run([ffmpeg, "-hide_banner", "-y", "-i", src, "-qscale:v", "2", "-progress", "pipe:1", "-nostats",
              os.path.join(fin, "%08d.jpg")], lambda f: progress and progress(0.1 * f), dur, cancel)
        total = len(os.listdir(fin))
        if not total:
            raise UpscaleError("no frames")
        # 2) KI
        cmd = [exe, "-i", fin, "-o", fout, "-n", name, "-s", str(factor), "-f", "jpg"]
        if not os.path.isdir(os.path.join(os.path.dirname(exe), "models")):
            pass
        _run(cmd, lambda f: progress and progress(0.1 + 0.8 * f), total, cancel, cwd=os.path.dirname(exe),
             count_dir=fout)
        shutil.rmtree(fin, ignore_errors=True)
        # 3) Wieder zusammensetzen (Ton vom Original)
        _run([ffmpeg, "-hide_banner", "-y", "-framerate", f"{fps:.5f}", "-i", os.path.join(fout, "%08d.jpg"),
              "-i", src, "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
              "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest", "-progress", "pipe:1", "-nostats", dst],
             lambda f: progress and progress(0.9 + 0.1 * f), dur, cancel)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return dst


def topaz_video(src, dst, factor, info, progress=None, cancel=None, model="prob-4"):
    """Mit Topaz Video AI hochskalieren (setzt eine aktive Topaz-Lizenz voraus)."""
    tf = topaz_ffmpeg()
    if not tf:
        raise UpscaleError("Topaz Video AI not found")
    env = clean_env()
    pd = os.environ.get("ProgramData", r"C:\ProgramData")
    for app in ("Topaz Video AI", "Topaz Video"):
        md = os.path.join(pd, "Topaz Labs LLC", app, "models")
        if os.path.isdir(md):
            env.setdefault("TVAI_MODEL_DIR", md)
            env.setdefault("TVAI_MODEL_DATA_DIR", md)
            break
    w, h = info.get("w") or 1920, info.get("h") or 1080
    W, H = int(w * factor) // 2 * 2, int(h * factor) // 2 * 2
    vf = f"tvai_up=model={model}:scale=0:w={W}:h={H}:device=-2:vram=1:instances=1,scale={W}:{H}:flags=lanczos"
    mid = dst + ".topaz.mov"
    try:
        _run([tf, "-hide_banner", "-y", "-i", src, "-vf", vf, "-c:v", "prores_ks", "-profile:v", "3",
              "-c:a", "copy", "-progress", "pipe:1", "-nostats", mid],
             lambda f: progress and progress(0.9 * f), info.get("duration"), cancel, cwd=os.path.dirname(tf), env=env)
        ff = tools.find_tool("ffmpeg")
        _run([ff, "-hide_banner", "-y", "-i", mid, "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
              "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-progress", "pipe:1", "-nostats", dst],
             lambda f: progress and progress(0.9 + 0.1 * f), info.get("duration"), cancel)
    finally:
        try:
            os.remove(mid)
        except OSError:
            pass
    return dst


def factor_needed(src_h, target_h):
    if not src_h or not target_h or target_h <= src_h * 1.05:
        return 1
    return min(4, max(2, int(math.ceil(target_h / src_h))))
