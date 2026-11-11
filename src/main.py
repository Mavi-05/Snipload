"""Startpunkt fuer Snipload (auch fuer PyInstaller)."""
import sys


def selftest(out_path):
    """Prueft beim GitHub-Build, ob alles Noetige in der exe steckt (OpenCV, Gesichtserkennung, Oberflaeche, Sprachen)."""
    lines, ok = [], True
    try:
        import cv2
        import numpy as np
        from snipload import facecam
        n = len(facecam._load())
        img = np.zeros((360, 640, 3), np.uint8)
        from PIL import Image
        facecam.detect_faces(Image.fromarray(img))
        lines.append(f"cv2 {cv2.__version__}, numpy {np.__version__}, Detektoren: {n}")
        ok &= n >= 2
    except Exception as ex:  # noqa
        lines.append(f"FEHLER Facecam: {ex!r}")
        ok = False
    try:
        # Oberflaeche: Dateien vorhanden, Server startet, Programm antwortet
        import json
        import os
        import urllib.request
        import webview  # noqa
        from snipload import updater
        from snipload.util import web_path
        from snipload.webapp import start_backend
        need = ["index.html", "style.css", "home.css", "editor.css", "pages.css", "js/app.js", "js/core.js", "js/editor.js",
                "js/inspector.js", "js/home.js", "js/pages.js", "js/player.js", "js/preview.js", "js/timeline.js", "js/icons.js",
                "js/vendor/hls.light.min.js", "fonts/Geist.ttf", "fonts/Inter.ttf", "fonts/Montserrat-Black.ttf", "img/logo.png"]
        missing = [f for f in need if not os.path.isfile(web_path(*f.split("/")))]
        if missing:
            raise RuntimeError("Dateien fehlen: " + ", ".join(missing))
        be, srv = start_backend()
        base = f"http://127.0.0.1:{srv.port}"
        with urllib.request.urlopen(base + "/app/js/app.js", timeout=10) as r:
            js_type = r.headers.get("Content-Type", "")
            js_len = len(r.read())
        with urllib.request.urlopen(base + "/app/LICENSE", timeout=10) as r:
            if b"Snipload License" not in r.read():
                raise RuntimeError("Lizenz fehlt in der exe")
        req = urllib.request.Request(base + "/api/boot", data=b"{}", method="POST",
                                     headers={"X-Snip-Key": srv.token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            boot = json.loads(r.read().decode("utf-8"))
        if not boot.get("ok") or not boot["result"].get("presets"):
            raise RuntimeError("boot antwortet nicht richtig")
        if "javascript" not in js_type:
            raise RuntimeError(f"falscher Typ fuer Skripte: {js_type}")
        req = urllib.request.Request(base + "/api/boot", data=b"{}", method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            raise RuntimeError("Schnittstelle ohne Schluessel erreichbar")
        except urllib.error.HTTPError as ex:
            if ex.code != 403:
                raise
        srv.stop()
        lines.append(f"Oberflaeche ok, Version {updater.current_version()}, app.js {js_len} Bytes ({js_type})")
    except Exception as ex:  # noqa
        lines.append(f"FEHLER Oberflaeche: {ex!r}")
        ok = False
    try:
        from snipload import captions
        from snipload.util import web_path as wp
        import os as _os
        bad = [k for k, v in captions.FONTS.items() if not _os.path.isfile(wp("fonts", v[1]))]
        if bad:
            raise RuntimeError("Schriften fehlen: " + ", ".join(bad))
        ass = captions.build_ass([{"w": "Hello", "t0": 0.0, "t1": 0.4}, {"w": "world", "t0": 0.4, "t1": 0.9}], {}, 1080, 1920)
        if "Dialogue:" not in ass:
            raise RuntimeError("Untertitel leer")
        lines.append(f"Untertitel ok, {len(captions.FONTS)} Schriften")
    except Exception as ex:  # noqa
        lines.append(f"FEHLER Untertitel: {ex!r}")
        ok = False
    try:
        from snipload import i18n, locales
        counts = {c: len(locales.load(c)) for c in i18n.CODES if c != "en"}
        lines.append("Sprachen: " + ", ".join(f"{c} {n}" for c, n in counts.items()))
        ok &= all(n >= len(locales.KEYS) * 0.95 for n in counts.values())
    except Exception as ex:  # noqa
        lines.append(f"FEHLER Sprachen: {ex!r}")
        ok = False
    lines.append("SELFTEST OK" if ok else "SELFTEST FEHLGESCHLAGEN")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        code = selftest(sys.argv[2])
        import os
        os._exit(code)
    if len(sys.argv) >= 3 and sys.argv[1] == "--nettest":
        import os
        from snipload import devtest
        try:
            devtest.run(sys.argv[2])
        finally:
            os._exit(0)
    from snipload.webapp import main
    main()
