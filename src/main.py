"""Startpunkt fuer Snipload (auch fuer PyInstaller)."""
import sys


def selftest(out_path):
    """Prueft beim GitHub-Build, ob alles Noetige in der exe steckt (OpenCV, Gesichtserkennung, Oberflaeche)."""
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
        import customtkinter  # noqa
        from snipload import app, updater  # noqa
        lines.append(f"Oberflaeche ok, Version {updater.current_version()}")
    except Exception as ex:  # noqa
        lines.append(f"FEHLER Oberflaeche: {ex!r}")
        ok = False
    lines.append("SELFTEST OK" if ok else "SELFTEST FEHLGESCHLAGEN")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2]))
    from snipload.app import main
    main()
