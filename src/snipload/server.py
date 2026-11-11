"""Lokaler Webserver fuer die Oberflaeche.

- liefert die Oberflaeche (web/), Videos/Bilder (mit Range-Unterstuetzung zum Spulen) und Einzelbilder
- /api/<name>: Aufrufe an backend.Api (JSON rein, JSON raus)
- /events: Live-Ereignisse (Server-Sent Events) - Fortschritt, fertige Downloads, Updates ...

Nur auf 127.0.0.1 und nur mit dem zufaelligen Schluessel der Sitzung erreichbar, damit keine
Webseite im Browser die Schnittstelle missbrauchen kann.
"""
import json
import mimetypes
import os
import queue
import secrets
import socket
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from .util import web_path

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/quicktime", ".mov")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("image/webp", ".webp")

WEB_DIR = web_path()


class EventHub:
    """Verteilt Ereignisse an alle offenen /events-Verbindungen (meist genau eine: das Fenster)."""

    def __init__(self):
        self._clients = []
        self._lock = threading.Lock()
        self._backlog = []          # Ereignisse, bevor sich die Oberflaeche verbunden hat

    def emit(self, kind, data=None):
        msg = json.dumps({"type": kind, "data": data}, ensure_ascii=False, default=str)
        with self._lock:
            if not self._clients:
                self._backlog.append(msg)
                self._backlog = self._backlog[-200:]
                return
            for q in list(self._clients):
                q.put(msg)

    def subscribe(self):
        q = queue.Queue()
        with self._lock:
            self._clients.append(q)
            for m in self._backlog:
                q.put(m)
            self._backlog = []
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._clients:
                self._clients.remove(q)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Server:
    def __init__(self, api, hub, port=None):
        self.api = api
        self.hub = hub
        self.token = secrets.token_urlsafe(18)
        self.port = port or free_port()
        self.media_roots = set()       # Ordner, aus denen /media Dateien liefern darf
        srv = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "Snipload"

            def log_message(self, *a):
                pass

            # ------------------------------------------------ Helfer
            def _authorized(self, qs):
                tok = self.headers.get("X-Snip-Key") or (qs.get("k") or [""])[0]
                return secrets.compare_digest(tok or "", srv.token)

            def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if self.command != "HEAD":
                    try:
                        self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        pass

            def _json(self, code, obj):
                self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

            def _file(self, path, cache=False):
                try:
                    size = os.path.getsize(path)
                except OSError:
                    return self._send(404, b"not found", "text/plain")
                ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
                rng = self.headers.get("Range")
                start, end = 0, size - 1
                code = 200
                if rng and rng.startswith("bytes="):
                    try:
                        a, b = rng[6:].split(",")[0].split("-")
                        if a:
                            start = int(a)
                            end = int(b) if b else size - 1
                        else:   # bytes=-500: die letzten 500 Bytes
                            start = max(0, size - int(b))
                        end = min(end, size - 1)
                        if start > end:
                            raise ValueError
                        code = 206
                    except ValueError:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                length = end - start + 1
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(length))
                if code == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Cache-Control", "max-age=3600" if cache else "no-cache")
                self.end_headers()
                if self.command == "HEAD":
                    return
                try:
                    with open(path, "rb") as f:
                        f.seek(start)
                        left = length
                        while left > 0:
                            chunk = f.read(min(1 << 16, left))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            left -= len(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    pass

            # ------------------------------------------------ GET
            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                u = urlparse(self.path)
                qs = parse_qs(u.query)
                path = unquote(u.path)
                if path in ("/", "/index.html"):
                    return self._file(os.path.join(WEB_DIR, "index.html"))
                if path.startswith("/app/"):
                    rel = os.path.normpath(path[5:]).lstrip("\\/")
                    full = os.path.join(WEB_DIR, rel)
                    if not os.path.abspath(full).startswith(os.path.abspath(WEB_DIR)):
                        return self._send(403, b"forbidden", "text/plain")
                    if rel == "LICENSE" and not os.path.isfile(full):
                        # in der exe liegt die Lizenz in web/, aus dem Quellcode gestartet im Hauptordner
                        full = os.path.join(WEB_DIR, os.pardir, os.pardir, os.pardir, "LICENSE")
                    return self._file(full, cache=rel.startswith("fonts"))
                if not self._authorized(qs):
                    return self._send(403, b"forbidden", "text/plain")
                if path == "/events":
                    return self._events()
                if path == "/media":
                    p = os.path.abspath((qs.get("p") or [""])[0])
                    if not srv.allowed(p):
                        return self._send(403, b"forbidden", "text/plain")
                    return self._file(p, cache=True)
                if path == "/frame":
                    try:
                        p = srv.api.frame_path(qs)
                    except Exception:
                        p = None
                    if not p:
                        return self._send(404, b"no frame", "text/plain")
                    return self._file(p, cache=True)
                return self._send(404, b"not found", "text/plain")

            def _events(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                q = srv.hub.subscribe()
                try:
                    self.wfile.write(b": hi\n\n")
                    self.wfile.flush()
                    while True:
                        try:
                            msg = q.get(timeout=15)
                            data = "data: " + msg.replace("\n", "\ndata: ") + "\n\n"
                        except queue.Empty:
                            data = ": ping\n\n"
                        self.wfile.write(data.encode("utf-8"))
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    pass
                finally:
                    srv.hub.unsubscribe(q)

            # ------------------------------------------------ POST /api/<name>
            def do_POST(self):
                u = urlparse(self.path)
                qs = parse_qs(u.query)
                if not self._authorized(qs):
                    return self._send(403, b"forbidden", "text/plain")
                if not u.path.startswith("/api/"):
                    return self._send(404, b"not found", "text/plain")
                name = u.path[5:]
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                except Exception:
                    return self._json(400, {"error": "bad json"})
                fn = getattr(srv.api, "api_" + name, None)
                if not callable(fn):
                    return self._json(404, {"error": f"unknown api {name}"})
                try:
                    res = fn(**body) if isinstance(body, dict) else fn(body)
                    return self._json(200, {"ok": True, "result": res})
                except ApiError as ex:
                    return self._json(200, {"ok": False, "error": str(ex), "code": ex.code})
                except Exception as ex:  # noqa
                    traceback.print_exc()
                    return self._json(200, {"ok": False, "error": f"{type(ex).__name__}: {ex}"})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.httpd.daemon_threads = True

    # ---------------------------------------------------------------- Pfade
    def allow(self, folder):
        if folder:
            self.media_roots.add(os.path.abspath(folder))

    def allowed(self, path):
        if not os.path.isfile(path):
            return False
        ap = os.path.abspath(path)
        for root in list(self.media_roots):
            try:
                if os.path.commonpath([ap, root]) == root:
                    return True
            except ValueError:
                continue
        return self.api.allowed_media(ap)

    def media_url(self, path):
        from urllib.parse import quote
        return f"/media?k={self.token}&p={quote(os.path.abspath(path))}"

    @property
    def url(self):
        return f"http://localhost:{self.port}/?k={self.token}"

    def start(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def stop(self):
        try:
            self.httpd.shutdown()
        except Exception:
            pass


class ApiError(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


def wait_until_up(port, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.3):
                return True
        except OSError:
            time.sleep(0.05)
    return False
