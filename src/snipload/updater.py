"""Selbst-Update: neue Snipload-Version von GitHub-Releases holen und die exe austauschen.

Ablauf:
1. check()    - fragt die neueste Release-Version ab (oeffentliche GitHub-API, ohne Anmeldung)
2. download() - laedt Snipload.exe neben die laufende exe (Snipload.update.exe) und prueft Groesse/Hash
3. install()  - startet ein kleines Hilfsskript, das wartet bis Snipload beendet ist, die exe ersetzt
                und (auf Wunsch) die neue Version startet
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from . import VERSION
from .util import NO_WINDOW, IS_WIN, clean_env

REPO = "Mavi-05/Snipload"
ASSET = "Snipload.exe"
API = os.environ.get("SNIPLOAD_UPDATE_API", f"https://api.github.com/repos/{REPO}/releases/latest")
UA = {"User-Agent": "Snipload-Updater", "Accept": "application/vnd.github+json"}

try:
    from ._build import BUILD  # wird beim GitHub-Build geschrieben, z. B. "3.0.7"
    BUILD_KNOWN = True
except Exception:
    BUILD = VERSION
    BUILD_KNOWN = False

FROZEN = getattr(sys, "frozen", False)


def current_version():
    return BUILD


def parse_version(v):
    nums = [int(x) for x in re.findall(r"\d+", v or "")][:4]
    return tuple(nums + [0] * (4 - len(nums)))


def is_newer(remote, local):
    return parse_version(remote) > parse_version(local)


def can_self_update():
    """Nur die fertige exe kann sich selbst austauschen (nicht beim Starten aus dem Quellcode)."""
    if not (FROZEN and IS_WIN) and not os.environ.get("SNIPLOAD_UPDATE_TEST"):
        return False
    folder = os.path.dirname(sys.executable)
    return os.access(folder, os.W_OK)


class UpdateError(Exception):
    pass


def check(timeout=12):
    """Gibt ein dict mit version, notes, url, size, sha256, page zurueck - oder None, wenn aktuell.

    Wirft UpdateError mit verstaendlicher Meldung, wenn die Pruefung nicht klappt.
    """
    if FROZEN and not BUILD_KNOWN:  # ohne Build-Nummer wuerde jede Version als "neuer" gelten
        raise UpdateError("Diese Snipload-Version kennt ihre Build-Nummer nicht – bitte einmal von Hand "
                          "von GitHub laden.")
    req = urllib.request.Request(API, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError("Keine Releases gefunden. (Ist das GitHub-Repo privat?)")
        if e.code == 403:
            raise UpdateError("GitHub hat die Anfrage gerade begrenzt. Später nochmal versuchen.")
        raise UpdateError(f"GitHub antwortet mit Fehler {e.code}.")
    except Exception:
        raise UpdateError("Keine Verbindung zu GitHub.")
    tag = (data.get("tag_name") or "").lstrip("vV")
    asset = next((a for a in data.get("assets") or [] if a.get("name") == ASSET), None)
    if not tag or not asset:
        raise UpdateError("Die neueste Version enthält keine Snipload.exe.")
    if not is_newer(tag, current_version()):
        return None
    sha = None
    dig = asset.get("digest") or ""
    if dig.startswith("sha256:"):
        sha = dig.split(":", 1)[1].lower()
    notes = (data.get("body") or "").strip()
    m = re.search(r"Änderung:\s*(.+)", notes) or re.search(r"Aenderung:\s*(.+)", notes)
    return {
        "version": tag,
        "notes": m.group(1).strip() if m else "",
        "url": asset.get("browser_download_url"),
        "size": int(asset.get("size") or 0),
        "sha256": sha,
        "page": data.get("html_url"),
    }


def staged_path():
    if FROZEN:
        return os.path.join(os.path.dirname(sys.executable), "Snipload.update.exe")
    return os.path.join(tempfile.gettempdir(), "Snipload.update.exe")


def download(info, progress=None, cancelled=lambda: False):
    """Laedt die neue exe herunter. progress(frac) wird regelmaessig aufgerufen. Gibt den Pfad zurueck."""
    dst = staged_path()
    part = dst + ".part"
    req = urllib.request.Request(info["url"], headers={"User-Agent": UA["User-Agent"],
                                                       "Accept": "application/octet-stream"})
    h = hashlib.sha256()
    got = 0
    try:
        with urllib.request.urlopen(req, timeout=30) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.get("size") or 0)
            while True:
                if cancelled():
                    raise UpdateError("Abgebrochen.")
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if progress and total:
                    progress(min(1.0, got / total))
    except UpdateError:
        _rm(part)
        raise
    except Exception:
        _rm(part)
        raise UpdateError("Download des Updates fehlgeschlagen. Prüf deine Internetverbindung.")
    if info.get("size") and got != info["size"]:
        _rm(part)
        raise UpdateError("Das Update ist unvollständig angekommen. Bitte nochmal versuchen.")
    if info.get("sha256") and h.hexdigest() != info["sha256"]:
        _rm(part)
        raise UpdateError("Das Update ist beschädigt angekommen (Prüfsumme falsch). Bitte nochmal versuchen.")
    with open(part, "rb") as f:
        if f.read(2) != b"MZ":
            _rm(part)
            raise UpdateError("Die heruntergeladene Datei ist keine gültige exe.")
    os.replace(part, dst)
    return dst


def install(staged, restart=True):
    """Startet das Hilfsskript, das nach dem Beenden von Snipload die exe austauscht.

    Danach muss sich Snipload selbst beenden.
    """
    exe = sys.executable if FROZEN else os.environ.get("SNIPLOAD_UPDATE_TARGET", "")
    if not exe:
        raise UpdateError("Selbst-Update geht nur in der fertigen exe.")
    script = os.path.join(tempfile.gettempdir(), "snipload_update.cmd")
    log = os.path.join(tempfile.gettempdir(), "snipload_update.log")
    start_line = f'start "" "{exe}"' if restart else "rem kein Neustart"
    # Wartet, bis die alte exe frei ist (max. ~60 s), tauscht sie aus und startet die neue.
    text = f"""@echo off
chcp 65001 >nul
set /a n=0
:retry
move /y "{staged}" "{exe}" >nul 2>&1
if not errorlevel 1 goto done
set /a n+=1
if %n% geq 60 goto fail
ping -n 2 127.0.0.1 >nul
goto retry
:done
echo ok > "{log}"
{start_line}
goto end
:fail
echo fehlgeschlagen > "{log}"
:end
(goto) 2>nul & del "%~f0"
"""
    # newline="\r\n": Windows-Zeilenenden genau EINMAL (nicht doppelt "\r\r\n" - sonst haengt ein
    # unsichtbares \r am Pfad und "start" findet die neue exe nicht)
    with open(script, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if IS_WIN else 0
    subprocess.Popen(["cmd", "/c", script], creationflags=flags, close_fds=True, env=clean_env(),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cleanup_leftovers():
    """Reste eines abgebrochenen oder alten Updates entfernen."""
    tmp = tempfile.gettempdir()
    for p in (staged_path() + ".part", staged_path(), os.path.join(tmp, "snipload_update.cmd")):
        _rm(p)


def _rm(p):
    try:
        if os.path.exists(p):
            os.remove(p)
    except OSError:
        pass
