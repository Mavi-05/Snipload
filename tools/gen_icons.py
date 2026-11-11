"""Erzeugt web/js/icons.js aus den Lucide-Icons (ISC-Lizenz). Aufruf: python gen.py <lucide-icons-dir> <ziel.js>"""
import os, re, sys
NAMES = """
compass scissors download library settings search link play pause rotate-ccw rotate-cw repeat volume-2 volume-x x check
chevron-down chevron-right chevron-left chevron-up plus minus trash-2 folder folder-open external-link copy refresh-cw star user users
eye clock captions message-square sparkles crop smartphone monitor camera film music wand-sparkles zap info triangle-alert
ellipsis upload type layers send maximize-2 layout-grid flame radio arrow-left arrow-right arrow-up arrow-down-to-line zoom-in zoom-out scan
scan-face gauge sun contrast droplet audio-lines image file-video hard-drive languages keyboard history list-video
clapperboard arrow-left-to-line arrow-right-to-line skip-back skip-forward square timer palette move-horizontal move-vertical scaling
circle-check circle-x circle-alert package pencil save circle-arrow-up mouse-pointer-click grip-vertical text-cursor-input
rectangle-horizontal rectangle-vertical gallery-vertical between-horizontal-start badge-check undo-2 list-plus tv heart
square-split-vertical panel-top power globe cookie cpu wrench bell file-text files clipboard key-round shield-check aperture
""".split()
src, dst = sys.argv[1], sys.argv[2]
out, missing = {}, []
for n in NAMES:
    p = os.path.join(src, n + ".svg")
    if not os.path.exists(p):
        missing.append(n); continue
    s = open(p, encoding="utf-8").read()
    body = s[s.index(">", s.index("<svg")) + 1: s.rindex("</svg>")]
    body = re.sub(r"\s+", " ", body).strip().replace(" />", "/>")
    out[n] = body
if missing:
    print("FEHLEN:", missing); sys.exit(1)
with open(dst, "w", encoding="utf-8") as f:
    f.write("// Automatisch erzeugt (tools/gen_icons.py) aus Lucide – https://lucide.dev – ISC-Lizenz, siehe web/LICENSES.txt\n")
    f.write("export const ICONS = {\n")
    for n in sorted(out):
        f.write(f'  "{n}": \'{out[n]}\',\n')
    f.write("};\n")
print(len(out), "icons ->", dst)
