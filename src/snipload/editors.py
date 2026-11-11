"""Clips mit einem Klick an Schnittprogramme uebergeben.

- Premiere Pro: kleine Erweiterung ("Snipload Bridge", CEP), die im Hintergrund von Premiere laeuft und
  Auftraege aus %APPDATA%\\Snipload\\handoff\\premiere uebernimmt: Import in den Ordner "Snipload" im Projekt,
  auf Wunsch direkt an die Abspielposition in der Timeline oder als neue Sequenz.
- After Effects: Import per Skript (AfterFX.exe -r), auf Wunsch gleich als neue Komposition.
- CapCut, DaVinci Resolve, VEGAS und eigene Programme: Programm starten, Clip in die Zwischenablage legen
  (dort mit Strg+V einfuegen) und im Explorer markieren.
"""
import glob
import json
import os
import re
import subprocess
import tempfile
import time
import uuid

from .util import IS_WIN, NO_WINDOW, clean_env, config_dir

EXT_ID = "com.snipload.bridge"


def _pf():
    return [p for p in {os.environ.get("ProgramFiles", r"C:\Program Files"),
                        os.environ.get("ProgramW6432", r"C:\Program Files")} if p]


def _newest(paths):
    def key(p):
        m = re.findall(r"(20\d\d|\d{2}\.\d)", p)
        return (m[-1] if m else "", os.path.getmtime(p) if os.path.exists(p) else 0)
    paths = [p for p in paths if os.path.isfile(p) and "beta" not in p.lower()] or [p for p in paths if os.path.isfile(p)]
    return sorted(paths, key=key)[-1] if paths else None


def detect(custom=None):
    """Installierte Schnittprogramme -> [{"id","name","path","kind","direct"}]"""
    out = []
    if IS_WIN:
        for pf in _pf():
            p = _newest(glob.glob(os.path.join(pf, "Adobe", "Adobe Premiere Pro*", "Adobe Premiere Pro.exe")))
            if p and not any(e["id"] == "premiere" for e in out):
                out.append({"id": "premiere", "name": "Premiere Pro", "path": p, "kind": "premiere", "direct": True})
            p = _newest(glob.glob(os.path.join(pf, "Adobe", "Adobe After Effects*", "Support Files", "AfterFX.exe")))
            if p and not any(e["id"] == "aftereffects" for e in out):
                out.append({"id": "aftereffects", "name": "After Effects", "path": p, "kind": "aftereffects",
                            "direct": True})
            p = os.path.join(pf, "Blackmagic Design", "DaVinci Resolve", "Resolve.exe")
            if os.path.isfile(p) and not any(e["id"] == "resolve" for e in out):
                out.append({"id": "resolve", "name": "DaVinci Resolve", "path": p, "kind": "generic", "direct": False})
            p = _newest(glob.glob(os.path.join(pf, "VEGAS", "VEGAS Pro*", "vegas*.exe")))
            if p and not any(e["id"] == "vegas" for e in out):
                out.append({"id": "vegas", "name": "VEGAS Pro", "path": p, "kind": "vegas", "direct": True})
        la = os.environ.get("LOCALAPPDATA", "")
        for cand in (os.path.join(la, "CapCut", "Apps", "CapCut.exe"),
                     os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "CapCut", "CapCut.exe")):
            if os.path.isfile(cand):
                out.append({"id": "capcut", "name": "CapCut", "path": cand, "kind": "generic", "direct": False})
                break
    for i, c in enumerate(custom or []):
        if c.get("path") and os.path.isfile(c["path"]):
            out.append({"id": c.get("id") or f"custom{i}", "name": c.get("name") or os.path.basename(c["path"]),
                        "path": c["path"], "kind": "generic", "direct": False, "custom": True})
    return out


def _running(exe_name):
    if not IS_WIN:
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"], capture_output=True,
                           creationflags=NO_WINDOW, timeout=10)
        return exe_name.lower() in (r.stdout or b"").decode("utf-8", "replace").lower()
    except Exception:
        return False


def _start(path, args=()):
    flags = 0
    if IS_WIN:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([path, *args], creationflags=flags, close_fds=True, env=clean_env(),
                     cwd=os.path.dirname(path), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def copy_files_to_clipboard(files):
    """Dateien wie im Explorer kopieren (CF_HDROP) - in vielen Programmen mit Strg+V einfuegbar."""
    if not IS_WIN:
        return False
    lst = ",".join("'" + f.replace("'", "''") + "'" for f in files)
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", f"Set-Clipboard -Path {lst}"],
                       creationflags=NO_WINDOW, capture_output=True, timeout=20, env=clean_env())
        return True
    except Exception:
        return False


def reveal(path):
    if IS_WIN:
        subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"', env=clean_env())
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


# ================================================================ Premiere Pro (CEP-Erweiterung)
MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<ExtensionManifest Version="7.0" ExtensionBundleId="com.snipload.bridge" ExtensionBundleVersion="1.1.0"
    ExtensionBundleName="Snipload" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ExtensionList>
    <Extension Id="com.snipload.bridge.bg" Version="1.1.0"/>
    <Extension Id="com.snipload.bridge.panel" Version="1.1.0"/>
  </ExtensionList>
  <ExecutionEnvironment>
    <HostList><Host Name="PPRO" Version="[12.0,99.9]"/></HostList>
    <LocaleList><Locale Code="All"/></LocaleList>
    <RequiredRuntimeList><RequiredRuntime Name="CSXS" Version="9.0"/></RequiredRuntimeList>
  </ExecutionEnvironment>
  <DispatchInfoList>
    <Extension Id="com.snipload.bridge.bg">
      <DispatchInfo>
        <Resources><MainPath>./index.html</MainPath><ScriptPath>./host.jsx</ScriptPath></Resources>
        <Lifecycle>
          <AutoVisible>false</AutoVisible>
          <StartOn>
            <Event>com.adobe.csxs.events.ApplicationActivate</Event>
            <Event>applicationActivate</Event>
          </StartOn>
        </Lifecycle>
        <UI><Type>Custom</Type><Geometry><Size><Height>1</Height><Width>1</Width></Size></Geometry></UI>
      </DispatchInfo>
    </Extension>
    <Extension Id="com.snipload.bridge.panel">
      <DispatchInfo>
        <Resources><MainPath>./index.html</MainPath><ScriptPath>./host.jsx</ScriptPath></Resources>
        <Lifecycle><AutoVisible>true</AutoVisible></Lifecycle>
        <UI><Type>Panel</Type><Menu>Snipload</Menu>
          <Geometry><Size><Height>160</Height><Width>320</Width></Size></Geometry></UI>
      </DispatchInfo>
    </Extension>
  </DispatchInfoList>
</ExtensionManifest>
"""

INDEX_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Snipload</title>
<style>body{margin:0;background:#0b0c12;color:#e8e8f0;font:12px Segoe UI,sans-serif;padding:14px}
b{color:#8f74ff}#s{margin-top:6px;color:#9a9ab0}</style></head><body>
<b>Snipload Bridge</b><div id="s">ready</div>
<script>
var cs = window.__adobe_cep__;
function poll(){
  if(!cs){return;}
  cs.evalScript('sniploadPoll()', function(r){ var e=document.getElementById('s'); if(e && r){ e.textContent=r; } });
}
setInterval(poll, 1200); poll();
</script></body></html>
"""

HOST_JSX = r"""
function sniploadDir(){ return Folder.userData.fsName.replace(/\\/g,'/') + '/Snipload/handoff/premiere'; }
function sniploadBin(name){
  var root = app.project.rootItem;
  for (var i = 0; i < root.children.numItems; i++){
    var it = root.children[i];
    if (it && it.name == name && it.type == ProjectItemType.BIN){ return it; }
  }
  return root.createBin(name);
}
function sniploadFind(bin, path){
  var want = path.replace(/\\/g,'/').toLowerCase();
  for (var i = bin.children.numItems - 1; i >= 0; i--){
    var it = bin.children[i];
    try { if (it.getMediaPath && it.getMediaPath().replace(/\\/g,'/').toLowerCase() == want){ return it; } } catch(e){}
  }
  return null;
}
function sniploadPoll(){
  try {
    var dir = new Folder(sniploadDir());
    if (!dir.exists){ return 'ready'; }
    var reqs = dir.getFiles('*.json');
    if (!reqs.length){ return 'ready'; }
    if (!app.project || !app.project.rootItem){ return 'waiting for a project'; }
    var done = 0;
    for (var r = 0; r < reqs.length; r++){
      var f = reqs[r];
      var work = new File(f.fsName.replace(/\.json$/, '.work'));
      if (!f.rename(work.name)){ continue; }      // ein anderes Fenster war schneller
      work = new File(dir.fsName + '/' + work.name);
      work.encoding = 'UTF-8'; work.open('r'); var txt = work.read(); work.close();
      var req = eval('(' + txt + ')');
      var bin = sniploadBin(req.bin || 'Snipload');
      var paths = [];
      for (var i = 0; i < req.files.length; i++){ paths.push(req.files[i]); }
      app.project.importFiles(paths, true, bin, false);
      var items = [];
      for (var j = 0; j < paths.length; j++){ var it = sniploadFind(bin, paths[j]); if (it){ items.push(it); } }
      if (items.length){
        if (req.mode == 'timeline' && app.project.activeSequence){
          var seq = app.project.activeSequence;
          var t = seq.getPlayerPosition().seconds;
          var track = seq.videoTracks[0];
          for (var k = 0; k < items.length; k++){ track.insertClip(items[k], t); }
        } else if (req.mode == 'sequence'){
          app.project.createNewSequenceFromClips(req.name || items[0].name, items, bin);
        } else {
          try { app.sourceMonitor.openProjectItem(items[0]); } catch(e){}
        }
      }
      work.remove();
      done++;
    }
    return done ? ('imported ' + done) : 'ready';
  } catch (e) {
    return 'error: ' + e;
  }
}
"""


def premiere_ext_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Adobe", "CEP", "extensions", EXT_ID)


def premiere_bridge_installed():
    return os.path.isfile(os.path.join(premiere_ext_dir(), "CSXS", "manifest.xml"))


def install_premiere_bridge():
    """Erweiterung ablegen und unsignierte Erweiterungen erlauben (PlayerDebugMode, nur fuer diesen Benutzer)."""
    d = premiere_ext_dir()
    os.makedirs(os.path.join(d, "CSXS"), exist_ok=True)
    with open(os.path.join(d, "CSXS", "manifest.xml"), "w", encoding="utf-8") as f:
        f.write(MANIFEST)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(INDEX_HTML)
    with open(os.path.join(d, "host.jsx"), "w", encoding="utf-8") as f:
        f.write(HOST_JSX)
    if IS_WIN:
        import winreg
        for v in range(9, 14):
            try:
                k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Adobe\CSXS.{v}")
                winreg.SetValueEx(k, "PlayerDebugMode", 0, winreg.REG_SZ, "1")
                winreg.CloseKey(k)
            except OSError:
                pass
    os.makedirs(handoff_dir("premiere"), exist_ok=True)
    return True


def handoff_dir(app_id):
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Snipload", "handoff", app_id)


def send_premiere(editor, files, mode="bin", name=None):
    if not premiere_bridge_installed():
        install_premiere_bridge()
        first = True
    else:
        first = False
    d = handoff_dir("premiere")
    os.makedirs(d, exist_ok=True)
    req = {"files": [os.path.abspath(f).replace("\\", "/") for f in files], "mode": mode,
           "name": name or os.path.splitext(os.path.basename(files[0]))[0], "bin": "Snipload", "ts": time.time()}
    tmp = os.path.join(d, f"{uuid.uuid4().hex}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(req, f, ensure_ascii=False)
    os.replace(tmp, tmp[:-4] + ".json")
    started = False
    if editor and editor.get("path") and not _running("Adobe Premiere Pro.exe"):
        _start(editor["path"])
        started = True
    return {"ok": True, "first": first, "started": started}


# ================================================================ After Effects
AE_JSX = r"""
(function(){
  var files = %s;
  var mode = %s;
  app.beginUndoGroup('Snipload');
  var folder = null;
  for (var i = 1; i <= app.project.numItems; i++){
    var it = app.project.item(i);
    if (it instanceof FolderItem && it.name == 'Snipload'){ folder = it; break; }
  }
  if (!folder){ folder = app.project.items.addFolder('Snipload'); }
  var last = null;
  for (var j = 0; j < files.length; j++){
    var io = new ImportOptions(new File(files[j]));
    var item = app.project.importFile(io);
    item.parentFolder = folder;
    last = item;
    if (mode == 'comp' && item.hasVideo){
      var comp = app.project.items.addComp(item.name.replace(/\.[^.]+$/, ''), item.width, item.height,
                                           item.pixelAspect, item.duration, item.frameRate || 30);
      comp.parentFolder = folder;
      comp.layers.add(item);
      comp.openInViewer();
    }
  }
  app.endUndoGroup();
})();
"""


def send_aftereffects(editor, files, mode="comp"):
    paths = json.dumps([os.path.abspath(f).replace("\\", "/") for f in files])
    script = AE_JSX % (paths, json.dumps(mode))
    fd, p = tempfile.mkstemp(prefix="snipload_ae_", suffix=".jsx")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(script)
    _start(editor["path"], ["-r", p])
    return {"ok": True}


# ================================================================ Alle
def send(editor, files, mode=None):
    files = [f for f in files if f and os.path.isfile(f)]
    if not files:
        return {"ok": False, "error": "no file"}
    kind = editor.get("kind")
    if kind == "premiere":
        return send_premiere(editor, files, mode or "bin")
    if kind == "aftereffects":
        return send_aftereffects(editor, files, mode or "comp")
    if kind == "vegas":
        _start(editor["path"], files[:1])
        return {"ok": True}
    # Allgemein: Programm starten, Zwischenablage, Explorer
    exe = os.path.basename(editor.get("path") or "")
    if editor.get("path") and not _running(exe):
        _start(editor["path"])
    copy_files_to_clipboard(files)
    return {"ok": True, "clipboard": True}
