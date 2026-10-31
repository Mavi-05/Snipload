"""Facecam-Erkennung: findet den Facecam-Rahmen in einem VOD und prueft ihn ueber den ganzen Zeitraum.

Vorgehen:
1. ~10 Standbilder gleichmaessig ueber den gewaehlten Abschnitt
2. Gesichter in jedem Bild finden (OpenCV), Treffer an aehnlicher Stelle zusammenfassen
   -> die Stelle, an der am haeufigsten ein Gesicht ist, ist die Facecam
3. Um das Gesicht herum den Rahmen suchen: Kanten, die in (fast) allen Bildern an derselben
   Stelle sind (Overlay-Rand oder Grenze Kamera/Spiel)
4. Pruefen, in wie vielen Bildern die Facecam wirklich zu sehen ist (Warnung mit Zeitpunkten)

Alle Koordinaten sind normiert (0..1) bezogen auf Bildbreite/-hoehe.
"""
import os

from .util import resource_path

_cascades = None


def available():
    try:
        import cv2  # noqa
        import numpy  # noqa
        return True
    except Exception:
        return False


def _load():
    global _cascades
    if _cascades is not None:
        return _cascades
    import cv2
    out = []
    for name in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml",
                 "haarcascade_profileface.xml"):
        for p in (resource_path(name), os.path.join(getattr(getattr(cv2, "data", None), "haarcascades", "") or "",
                                                     name)):
            if p and os.path.exists(p):
                c = cv2.CascadeClassifier(p)
                if not c.empty():
                    out.append((name, c))
                    break
    _cascades = out
    return out


def detect_faces(pil_img):
    """Gesichter als Liste (x, y, w, h) normiert. Mehrere Detektoren, Treffer zusammengefasst."""
    import cv2
    import numpy as np
    rgb = np.asarray(pil_img.convert("RGB"))
    H, W = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    min_side = max(20, int(min(W, H) * 0.035))
    boxes = []
    for name, c in _load():
        for img, flip in ((gray, False), (cv2.flip(gray, 1), True)) if "profile" in name else ((gray, False),):
            found = c.detectMultiScale(img, scaleFactor=1.08, minNeighbors=6 if "default" in name else 4,
                                       minSize=(min_side, min_side))
            for (x, y, w, h) in (found if len(found) else []):
                if flip:
                    x = W - x - w
                boxes.append((x / W, y / H, w / W, h / H))
    return _merge(boxes)


def _merge(boxes, thr=0.35):
    """Ueberlappende Treffer zusammenfassen (Mittelwert)."""
    groups = []
    for b in boxes:
        for g in groups:
            if _iou(g[0], b) > thr:
                g.append(b)
                break
        else:
            groups.append([b])
    out = []
    for g in groups:
        n = len(g)
        out.append(tuple(sum(v[i] for v in g) / n for i in range(4)) + (n,))
    return out


def _iou(a, b):
    ax0, ay0, aw, ah = a[:4]
    bx0, by0, bw, bh = b[:4]
    ix = max(0.0, min(ax0 + aw, bx0 + bw) - max(ax0, bx0))
    iy = max(0.0, min(ay0 + ah, by0 + bh) - max(ay0, by0))
    inter = ix * iy
    u = aw * ah + bw * bh - inter
    return inter / u if u > 0 else 0.0


def _median(vals):
    v = sorted(vals)
    n = len(v)
    return (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2) if n else 0.0


def analyze(frames, aspect=16 / 9):
    """frames: Liste (t, PIL-Bild). Gibt ein Ergebnis-dict zurueck (siehe unten)."""
    import cv2
    import numpy as np
    frames = [(t, im) for t, im in frames if im is not None]
    res = {"ok": False, "box": None, "coverage": 0.0, "missing": [], "border": False, "fullscreen": False,
           "frames": len(frames), "message": ""}
    if len(frames) < 2:
        res["message"] = "Konnte keine Bilder aus dem Video holen."
        return res
    W, H = frames[0][1].size

    # 1) Gesichter in allen Bildern
    per_frame = []
    for t, im in frames:
        if im.size != (W, H):
            im = im.resize((W, H))
        per_frame.append((t, detect_faces(im)))

    # 2) Treffer ueber die Zeit clustern (gleiche Stelle = Facecam)
    clusters = []  # [mittelpunkt_x, mittelpunkt_y, [faces], set(frame_idx)]
    for fi, (t, faces) in enumerate(per_frame):
        for f in faces:
            cx, cy = f[0] + f[2] / 2, f[1] + f[3] / 2
            for c in clusters:
                if abs(c[0] - cx) < max(0.06, f[2] * 0.8) and abs(c[1] - cy) < max(0.08, f[3] * 0.8):
                    c[2].append(f)
                    c[3].add(fi)
                    n = len(c[2])
                    c[0] += (cx - c[0]) / n
                    c[1] += (cy - c[1]) / n
                    break
            else:
                clusters.append([cx, cy, [f], {fi}])
    if not clusters:
        res["message"] = "In diesem Abschnitt wurde kein Gesicht gefunden."
        return res
    best = max(clusters, key=lambda c: (len(c[3]), sum(f[4] for f in c[2])))
    if len(best[3]) < max(2, int(len(frames) * 0.25)):
        res["message"] = "Kein Gesicht, das dauerhaft an einer Stelle ist – keine Facecam erkannt."
        return res
    fx = _median([f[0] for f in best[2]])
    fy = _median([f[1] for f in best[2]])
    fw = _median([f[2] for f in best[2]])
    fh = _median([f[3] for f in best[2]])

    # Vollbild-Kamera (Just Chatting / IRL): Gesicht riesig
    if fw > 0.22:
        res.update(ok=True, fullscreen=True, box=(0.0, 0.0, 1.0, 1.0),
                   message="Die Kamera füllt das ganze Bild – es gibt keine extra Facecam.")
        _coverage(res, per_frame, (0.0, 0.0, 1.0, 1.0))
        return res

    # 3) Rahmen suchen: Kanten, die in fast allen Bildern an derselben Stelle sind
    scale = 480 / W if W > 480 else 1.0
    w_s, h_s = int(W * scale), int(H * scale)
    acc = np.zeros((h_s, w_s), np.float32)
    for _, im in frames:
        g = cv2.cvtColor(np.asarray(im.convert("RGB").resize((w_s, h_s))), cv2.COLOR_RGB2GRAY)
        g = cv2.GaussianBlur(g, (3, 3), 0)
        acc += (cv2.Canny(g, 40, 120) > 0).astype(np.float32)
    P = acc / len(frames)  # 0..1: wie oft an dieser Stelle eine Kante war

    px, py, pw, ph = fx * w_s, fy * h_s, fw * w_s, fh * h_s
    rows = (max(0, int(py - ph * 0.3)), min(h_s, int(py + ph * 1.3)))
    cols = (max(0, int(px - pw * 0.3)), min(w_s, int(px + pw * 1.3)))

    def find(line_scores, start, stop, step):
        """Staerkste beständige Kante zwischen start und stop.

        Zaehlt, wenn sie sehr beständig ist (>= 0.5) oder sich klar vom Rest abhebt (>= 0.28 und
        mindestens 3x der Durchschnitt) - z. B. wenn die Facecam kurz weg war oder Spielgrafik angrenzt.
        """
        vals = [(i, line_scores(i)) for i in range(start, stop, step)]
        if not vals:
            return None, 0.0
        # Reicht die Suche bis an den Bildrand, zaehlt der Bildrand selbst als (mittelstarke) Kante:
        # Facecams, die am Rand anliegen, haben dort keine sichtbare Linie
        if stop in (-1, w_s, h_s):
            edge_i = 0 if stop == -1 else stop - 1
            vals.append((edge_i, 0.5))
        best_i, best_v = max(vals, key=lambda iv: iv[1])
        avg = sum(v for _, v in vals) / len(vals)
        if best_v >= 0.5 or (best_v >= 0.28 and best_v >= 3 * max(avg, 0.02)):
            return best_i, best_v
        return None, best_v

    reach_x, reach_y = int(pw * 3.2), int(ph * 3.0)

    def search(rows_, cols_):
        """Ein Durchgang: Kanten muessen ueber die ganze Spanne (rows_/cols_) beständig sein."""
        cs = lambda c: float(P[rows_[0]:rows_[1], c].mean()) if 0 <= c < w_s and rows_[1] > rows_[0] else 0.0
        rs = lambda r: float(P[r, cols_[0]:cols_[1]].mean()) if 0 <= r < h_s and cols_[1] > cols_[0] else 0.0
        return (find(cs, int(px - pw * 0.15), max(-1, int(px - reach_x)), -1),
                find(cs, int(px + pw * 1.15), min(w_s, int(px + pw + reach_x)), 1),
                find(rs, int(py - ph * 0.25), max(-1, int(py - reach_y)), -1),
                find(rs, int(py + ph * 1.25), min(h_s, int(py + ph + reach_y)), 1))

    # 1. Durchgang nur auf Hoehe/Breite des Gesichts, danach zweimal ueber die ganze gefundene Box:
    # ein echter Facecam-Rand laeuft ueber die volle Breite/Hoehe, Spiel-Kanten nicht
    (left, lv), (right, rv), (top, tv), (bottom, bv) = search(rows, cols)
    for _ in range(2):
        cols2 = (left if left is not None else cols[0], (right + 1) if right is not None else cols[1])
        rows2 = (top if top is not None else rows[0], (bottom + 1) if bottom is not None else rows[1])
        (left, lv), (right, rv), (top, tv), (bottom, bv) = search(rows2, cols2)

    # Fehlt genau eine Seite: ueber typische Webcam-Seitenverhaeltnisse ergaenzen und die Variante nehmen,
    # deren Kante im Bild am staerksten ist
    ratios = (16 / 9, 4 / 3, 1.0)
    if left is not None and right is not None and (top is None) != (bottom is None):
        cands = []
        for r in ratios:
            hgt = int(round((right - left) / r))
            row = (top + hgt) if top is not None else (bottom - hgt)
            if 0 <= row < h_s and ((top is not None and row > py + ph) or (bottom is not None and row < py)):
                cands.append((float(P[row, left:right + 1].mean()), row))
        if cands:
            _, row = max(cands)
            if top is not None:
                bottom = row
            else:
                top = row
    if top is not None and bottom is not None and (left is None) != (right is None):
        cands = []
        for r in ratios:
            wid = int(round((bottom - top) * r))
            col = (left + wid) if left is not None else (right - wid)
            if 0 <= col < w_s and ((left is not None and col > px + pw) or (right is not None and col < px)):
                cands.append((float(P[top:bottom + 1, col].mean()), col))
        if cands:
            _, col = max(cands)
            if left is not None:
                right = col
            else:
                left = col
    # Immer noch offen: Bildrand, wenn das Gesicht nah dran ist, sonst typische Facecam-Groesse
    cam_w, cam_h = pw * 2.8, ph * 2.6
    if left is None:
        left = 0 if px - pw * 1.6 <= 0 else int(max(0, px + pw / 2 - cam_w / 2))
    if right is None:
        right = w_s - 1 if px + pw * 2.6 >= w_s else int(min(w_s - 1, px + pw / 2 + cam_w / 2))
    if top is None:
        top = 0 if py - ph * 1.4 <= 0 else int(max(0, py + ph * 0.45 - cam_h / 2))
    if bottom is None:
        bottom = h_s - 1 if py + ph * 2.4 >= h_s else int(min(h_s - 1, py + ph * 0.45 + cam_h / 2))
    found = sum(v is not None and v >= 0.55 for v in (lv, rv, tv, bv))
    # Rand selbst nicht mit ausschneiden (2 px nach innen)
    inset = 2
    x0 = (left + inset) / w_s
    y0 = (top + inset) / h_s
    x1 = (right - inset + 1) / w_s
    y1 = (bottom - inset + 1) / h_s
    box = (max(0.0, x0), max(0.0, y0), min(1.0, x1) - max(0.0, x0), min(1.0, y1) - max(0.0, y0))
    # Plausibilitaet: Gesicht muss drin sein, Seitenverhaeltnis vernuenftig
    ratio = (box[2] * aspect) / max(1e-6, box[3])
    if not (0.6 <= ratio <= 2.6) or box[2] < fw * 1.05 or box[3] < fh * 1.05:
        cw, chh = min(1.0, fw * 2.8), min(1.0, fw * 2.8 * aspect / (4 / 3))
        bx = min(max(0.0, fx + fw / 2 - cw / 2), 1 - cw)
        by = min(max(0.0, fy + fh * 0.45 - chh / 2), 1 - chh)
        box, found = (bx, by, cw, chh), 0
    res.update(ok=True, box=tuple(round(v, 4) for v in box), border=found >= 3)
    _coverage(res, per_frame, box)
    pos = _where(box)
    if res["coverage"] >= 1.0:
        res["message"] = f"Facecam {pos} erkannt – in allen {len(frames)} geprüften Bildern zu sehen."
    elif res["coverage"] >= 0.8:
        miss = ", ".join(_fmt(t) for t in res["missing"][:4])
        res["message"] = (f"Facecam {pos} erkannt – in {res['hits']} von {len(frames)} Bildern zu sehen, "
                          f"fehlt bei {miss}.")
    else:
        miss = ", ".join(_fmt(t) for t in res["missing"][:4])
        res["message"] = (f"Facecam {pos} erkannt, aber nur in {res['hits']} von {len(frames)} Bildern zu sehen "
                          f"(fehlt z. B. bei {miss}).")
    return res


def _coverage(res, per_frame, box):
    bx, by, bw, bh = box
    hits, missing = 0, []
    for t, faces in per_frame:
        ok = any(bx <= f[0] + f[2] / 2 <= bx + bw and by <= f[1] + f[3] / 2 <= by + bh for f in faces)
        hits += ok
        if not ok:
            missing.append(t)
    res["hits"] = hits
    res["coverage"] = hits / max(1, len(per_frame))
    res["missing"] = missing


def _where(box):
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    v = "oben" if cy < 0.4 else ("unten" if cy > 0.6 else "")
    h = "links" if cx < 0.4 else ("rechts" if cx > 0.6 else "")
    pos = " ".join(x for x in (v, h) if x) or "in der Mitte"
    return pos


def _fmt(t):
    t = int(round(t))
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ================================================================ Layout fuer den Export
DEFAULT_LAYOUT = {"cam": None, "split": 0.40, "gx": 0.5, "cam_bottom": False}


def layout_geometry(layout, aspect=16 / 9, out_w=1080, out_h=1920):
    """Berechnet die beiden Ausschnitte (normiert) und die Hoehen im 1080x1920-Bild."""
    split = min(0.65, max(0.2, float(layout.get("split", 0.4))))
    hf = int(round(out_h * split / 2)) * 2
    hg = out_h - hf
    cx, cy, cw, ch = layout["cam"]
    # Facecam-Ausschnitt auf das Ziel-Seitenverhaeltnis bringen (mittig, ohne Verzerrung)
    target = out_w / hf
    px_w, px_h = cw * aspect, ch  # in "Bildhoehen"
    if px_w / px_h > target:
        nw = px_h * target / aspect
        cam = (cx + (cw - nw) / 2, cy, nw, ch)
    else:
        nh = px_w / target
        cam = (cx, cy + (ch - nh) / 2, cw, nh)
    # Gameplay-Ausschnitt: volle Hoehe, Breite passend, horizontal verschiebbar
    tg = out_w / hg
    gw = tg / aspect
    if gw <= 1:
        gx = (1 - gw) * min(1.0, max(0.0, float(layout.get("gx", 0.5))))
        game = (gx, 0.0, gw, 1.0)
    else:  # sehr schmales Video: Hoehe kuerzen
        gh = aspect / tg
        game = (0.0, (1 - gh) / 2, 1.0, gh)
    return {"cam": cam, "game": game, "hf": hf, "hg": hg, "cam_bottom": bool(layout.get("cam_bottom"))}


def suggest_gx(cam, aspect=16 / 9, split=0.40):
    """Gameplay-Ausschnitt so legen, dass die Facecam darin moeglichst nicht noch einmal auftaucht."""
    g = layout_geometry({"cam": cam, "split": split, "gx": 0.5}, aspect)
    gw = g["game"][2]
    if gw >= 1:
        return 0.5
    cx0, cx1 = cam[0], cam[0] + cam[2]
    margin = 0.02  # Abstand, damit auch der Rand/Rahmen der Facecam nicht mit hineinrutscht
    if (cx0 + cx1) / 2 > 0.5:   # Facecam rechts -> Ausschnitt links davon
        x = cx0 - gw - margin
    else:                         # Facecam links -> Ausschnitt rechts davon
        x = cx1 + margin
    x = min(max(0.0, x), 1 - gw)
    gx = x / (1 - gw)
    # nicht zu weit vom Bildzentrum weg (dort spielt meist die Action)
    return round(min(0.8, max(0.2, gx)), 3)


def ffmpeg_filter(layout, aspect=16 / 9):
    g = layout_geometry(layout, aspect)

    def crop(b):
        x, y, w, h = b
        return (f"crop=w=trunc(iw*{w:.5f}/2)*2:h=trunc(ih*{h:.5f}/2)*2:"
                f"x=trunc(iw*{x:.5f}):y=trunc(ih*{y:.5f})")
    top, bot = ("game", "cam") if g["cam_bottom"] else ("cam", "game")
    h_top = g["hf"] if top == "cam" else g["hg"]
    h_bot = g["hg"] if top == "cam" else g["hf"]
    return (f"[0:v]split=2[a][b];"
            f"[a]{crop(g[top])},scale=1080:{h_top}:flags=lanczos,setsar=1[t];"
            f"[b]{crop(g[bot])},scale=1080:{h_bot}:flags=lanczos,setsar=1[u];"
            f"[t][u]vstack=inputs=2,format=yuv420p[v]")


def render_preview(pil_frame, layout, height=480):
    """Kleine 9:16-Vorschau des fertigen Shorts (PIL)."""
    from PIL import Image
    W, H = pil_frame.size
    aspect = W / H
    g = layout_geometry(layout, aspect)
    out_w, out_h = int(height * 1080 / 1920), height
    k = height / 1920
    out = Image.new("RGB", (out_w, out_h))

    def part(b, h_px):
        x, y, w, h = b
        crop = pil_frame.crop((int(x * W), int(y * H), int((x + w) * W), int((y + h) * H)))
        return crop.resize((out_w, max(1, int(round(h_px * k)))), Image.LANCZOS)
    a = part(g["cam"], g["hf"])
    b = part(g["game"], g["hg"])
    first, second = (b, a) if g["cam_bottom"] else (a, b)
    out.paste(first, (0, 0))
    out.paste(second, (0, first.size[1]))
    return out


def px_to_norm(px):
    return (px["x"] / px["ref_w"], px["y"] / px["ref_h"], px["w"] / px["ref_w"], px["h"] / px["ref_h"])


def norm_to_px(box, ref_w, ref_h, even=True):
    x, y, w, h = box
    px = {"x": int(round(x * ref_w)), "y": int(round(y * ref_h)), "w": int(round(w * ref_w)),
          "h": int(round(h * ref_h)), "ref_w": ref_w, "ref_h": ref_h}
    if even:
        px["w"] -= px["w"] % 2
        px["h"] -= px["h"] % 2
    return px


# ================================================================ Pixelgenaue Verfeinerung (volle Aufloesung)
STD_RATIOS = (16 / 9, 4 / 3, 1.0, 3 / 4, 9 / 16, 21 / 9)


def refine(frames, box, good_times=None):
    """Misst die Facecam-Kanten in voller Aufloesung nach - pixelgenau.

    frames: (t, PIL) in Originalgroesse; box: grobe Box normiert; good_times: Zeitpunkte mit sichtbarer Facecam.
    Gibt {"x","y","w","h","ref_w","ref_h","border": bool, "snapped": str|None} in Pixeln zurueck.

    Prinzip: Eine echte Facecam-Kante trennt das sich bewegende Spiel (aussen) vom Kamerabild (innen).
    Kanten im Kamerabild (Schrank, Wand) haben auf beiden Seiten ruhiges Bild, Spiel-Kanten auf beiden
    Seiten Bewegung. Ein Rahmen ist ein schmaler, ruhiger, einfarbiger Streifen zwischen zwei Linien.
    """
    import cv2
    import numpy as np
    fr = [(t, im) for t, im in frames if im is not None and (good_times is None or t in good_times)]
    if len(fr) < 2:
        fr = [(t, im) for t, im in frames if im is not None]
    W, H = fr[0][1].size
    bx, by, bw, bh = box
    L, T_, R, B = bx * W, by * H, (bx + bw) * W, (by + bh) * H
    pad = int(0.035 * W) + 10
    rx0, ry0 = max(0, int(L) - pad), max(0, int(T_) - pad)
    rx1, ry1 = min(W, int(R) + pad), min(H, int(B) + pad)
    rgbs = [np.asarray(im.convert("RGB").crop((rx0, ry0, rx1, ry1)), dtype=np.uint8) for _, im in fr]
    stack = np.stack(rgbs).astype(np.float32)                 # (n, h, w, 3)
    mean = stack.mean(axis=0)                                  # mittlere Farbe je Pixel
    tstd = stack.mean(axis=3).std(axis=0)                      # zeitliche Unruhe je Pixel
    edges = np.mean([np.maximum.reduce([cv2.Canny(np.ascontiguousarray(c[:, :, k]), 30, 90)
                                        for k in range(3)]) > 0 for c in rgbs], axis=0)
    hh, ww = edges.shape

    def side(axis, coarse, lo, hi, inward, at_frame_edge):
        n = ww if axis == "x" else hh
        if axis == "x":
            e_line = lambda c: float(edges[lo:hi, c].mean())
            t_strip = lambda a, b: float(tstd[lo:hi, max(0, min(a, b)):max(0, max(a, b)) + 1].mean()) \
                if max(a, b) >= 0 and min(a, b) < n else 0.0
            c_line = lambda c: mean[lo:hi, c].reshape(-1, 3).mean(axis=0)
            band = lambda a, b: (tstd[lo:hi, a:b], mean[lo:hi, a:b].reshape(-1, 3))
        else:
            e_line = lambda c: float(edges[c, lo:hi].mean())
            t_strip = lambda a, b: float(tstd[max(0, min(a, b)):max(0, max(a, b)) + 1, lo:hi].mean()) \
                if max(a, b) >= 0 and min(a, b) < n else 0.0
            c_line = lambda c: mean[c, lo:hi].reshape(-1, 3).mean(axis=0)
            band = lambda a, b: (tstd[a:b, lo:hi], mean[a:b, lo:hi].reshape(-1, 3))
        clamp = lambda c: max(0, min(n - 1, c))
        c0 = int(round(coarse))
        d = int(0.02 * W) + 8
        idx = [i for i in range(c0 - d, c0 + d + 1) if 2 <= i < n - 2]
        vals = {i: e_line(i) for i in idx}
        peaks = [i for i in idx if vals[i] >= 0.35 and vals[i] >= vals.get(i - 1, 0) and vals[i] >= vals.get(i + 1, 0)]
        merged = []
        for i in peaks:
            if merged and i - merged[-1][-1] <= 1:
                merged[-1].append(i)
            else:
                merged.append([i])
        peaks = [max(g, key=lambda i: vals[i]) for g in merged]
        outside = lambda p: t_strip(clamp(p - inward * 10), clamp(p - inward * 3))
        inside = lambda p: t_strip(clamp(p + inward * 3), clamp(p + inward * 10))
        dist = lambda a, b: float(np.linalg.norm(a - b))

        def boundary_pixel(p, inner_col):
            """Erstes Pixel ab Linie p nach innen, dessen Farbe zum Inneren gehoert."""
            out_col = c_line(clamp(p - inward * 3))
            c = p - inward
            for _ in range(6):
                if 0 <= c < n and dist(c_line(c), inner_col) < dist(c_line(c), out_col):
                    return c
                c += inward
            return p + inward

        # 1) Rahmen: zwei Linien, dazwischen ruhiger einfarbiger Streifen, aussen Spiel-Bewegung
        maxgap = int(0.008 * W) + 5
        pairs = []
        for a in peaks:
            for b in peaks:
                lo_l, hi_l = (a, b) if a < b else (b, a)
                if hi_l - lo_l < 2 or hi_l - lo_l > maxgap:
                    continue
                o, i_ = (lo_l, hi_l) if inward > 0 else (hi_l, lo_l)   # aussen, innen
                if (o, i_) in pairs:
                    continue
                st, cols = band(lo_l + 1, hi_l)
                if st.size == 0 or float(st.mean()) > 3.0 or float(cols.std(axis=0).max()) > 14.0:
                    continue
                if outside(o) < 4.0 and not at_frame_edge:
                    continue
                pairs.append((o, i_))
        if pairs:
            o, i_ = min(pairs, key=lambda oi: oi[0] * inward)          # aeusserster Rahmen
            band_col = band(min(o, i_) + 1, max(o, i_))[1].mean(axis=0)
            inner_col = c_line(clamp(i_ + inward * 5))
            c = i_ - inward
            for _ in range(6):
                if 0 <= c < n and dist(c_line(c), inner_col) < dist(c_line(c), band_col):
                    return c, True
                c += inward
            return i_ + inward, True

        # 2) ohne Rahmen: wichtigstes Merkmal ist, wie beständig die Linie ist (echte Kante ~immer da);
        #    Bewegung aussen (Spiel) gibt Zusatzpunkte, Ruhe auf beiden Seiten (Schrank, Wand) zaehlt nicht
        cands = []
        for p in peaks:
            out_m = outside(p)
            contrast = out_m - inside(p)
            score = vals[p] * 20 + max(-5.0, min(contrast, 15.0))
            gamey = out_m >= 4.0
            cands.append((gamey, score, p))
        if any(c[0] for c in cands):
            cands = [c for c in cands if c[0]]   # Linien mit Spiel-Bewegung aussen bevorzugen
        best = max(cands, key=lambda c: c[1]) if cands else None
        if at_frame_edge:
            # Facecam liegt am Bildrand an: der Rand selbst ist ein starker Kandidat
            edge_c = 0 if inward > 0 else n - 1
            if best is None or best[1] < 22:
                return edge_c, False
        if best is not None:
            p = best[2]
            return boundary_pixel(p, c_line(clamp(p + inward * 5))), False
        return None, False

    ix0, ix1 = int(L - rx0 + bw * W * 0.12), int(R - rx0 - bw * W * 0.12)
    iy0, iy1 = int(T_ - ry0 + bh * H * 0.12), int(B - ry0 - bh * H * 0.12)
    near = 0.03
    left, bl = side("x", L - rx0, iy0, iy1, +1, at_frame_edge=(rx0 == 0 and bx < near))
    right, br = side("x", R - rx0, iy0, iy1, -1, at_frame_edge=(rx1 == W and bx + bw > 1 - near))
    top, bt = side("y", T_ - ry0, ix0, ix1, +1, at_frame_edge=(ry0 == 0 and by < near))
    bottom, bb = side("y", B - ry0, ix0, ix1, -1, at_frame_edge=(ry1 == H and by + bh > 1 - near))

    px0 = rx0 + left if left is not None else int(round(L))
    px1 = rx0 + right + 1 if right is not None else int(round(R))
    py0 = ry0 + top if top is not None else int(round(T_))
    py1 = ry0 + bottom + 1 if bottom is not None else int(round(B))
    w, h = px1 - px0, py1 - py0
    snapped = None
    for r in STD_RATIOS:
        if abs((w / h) / r - 1) < 0.015:
            nh = int(round(w / r))
            if abs(nh - h) <= max(3, int(h * 0.015)):
                py0 += (h - nh) // 2
                h = nh
                snapped = {16 / 9: "16:9", 4 / 3: "4:3", 1.0: "1:1", 3 / 4: "3:4", 9 / 16: "9:16",
                           21 / 9: "21:9"}[r]
            break
    if w % 2:
        w -= 1
    if h % 2:
        h -= 1
    return {"x": int(px0), "y": int(py0), "w": int(w), "h": int(h), "ref_w": W, "ref_h": H,
            "border": bool(bl or br or bt or bb), "snapped": snapped}
