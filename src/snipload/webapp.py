"""Startet Snipload: lokaler Server + Fenster (Edge WebView2 unter Windows).

python -m snipload.webapp --dev   -> nur Server, Adresse wird ausgegeben (zum Testen im Browser)
"""
import os
import sys
import threading
import time

from .backend import Backend
from .server import EventHub, Server, wait_until_up
from .util import IS_WIN, config_dir, win_no_throttle


def _dark_titlebar(window):
    """Titelleiste dunkel und im Farbton der App (Windows 10/11)."""
    if not IS_WIN:
        return
    try:
        import ctypes
        hwnd = window.native.Handle.ToInt32()
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (neu/alt)
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
        cap = ctypes.c_int(0x000D0807)    # #07080d als 0x00BBGGRR
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap), ctypes.sizeof(cap))
        txt = ctypes.c_int(0x00F0E8E8)
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(txt), ctypes.sizeof(txt))
    except Exception:
        pass


def start_backend(port=None):
    hub = EventHub()
    be = Backend(hub)
    srv = Server(be, hub, port).start()
    be.server = srv
    srv.allow(be.cfg.get("folder"))
    srv.allow(config_dir())
    wait_until_up(srv.port)
    return be, srv


def main(dev=False):
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Snipload.App")
        except Exception:
            pass
        win_no_throttle()
    be, srv = start_backend(int(os.environ.get("SNIPLOAD_PORT") or 0) or None)
    if dev or "--dev" in sys.argv:
        print(srv.url, flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return
    import webview
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.settings["ALLOW_DOWNLOADS"] = False
    webview.settings["SHOW_DEFAULT_MENUS"] = bool(os.environ.get("SNIPLOAD_DEBUG"))
    geo = be.cfg.get("window") or {}
    win = webview.create_window(
        "Snipload", srv.url, width=int(geo.get("w") or 1440), height=int(geo.get("h") or 900),
        min_size=(1120, 700), background_color="#07080d", text_select=False, zoomable=False,
        maximized=bool(geo.get("max")))
    be.window = win
    win.events.closing += be.on_closing
    win.events.shown += lambda: _dark_titlebar(win)

    def remember_size(w, h):
        be.cfg["window"] = {"w": w, "h": h}
    try:
        win.events.resized += remember_size
    except Exception:
        pass

    def on_closed():
        try:
            be.save()
        finally:
            threading.Timer(0.5, lambda: os._exit(0)).start()
    win.events.closed += on_closed
    storage = os.path.join(config_dir(), "webview")
    os.makedirs(storage, exist_ok=True)
    webview.start(gui="edgechromium" if IS_WIN else None, private_mode=False, storage_path=storage,
                  debug=bool(os.environ.get("SNIPLOAD_DEBUG")))


if __name__ == "__main__":
    main()
