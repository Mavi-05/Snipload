# Snipload

<img src="assets/icon_1024.png" width="96" align="right" alt="Snipload Icon">

Lädt nur den Teil eines YouTube-Videos herunter, den du wirklich brauchst – zum Beispiel
von `00:03:00` bis `00:06:00`. Als Video (MP4) oder nur den Ton (MP3).

## Download

👉 **[Neueste Snipload.exe herunterladen](../../releases/latest)** – unter *Assets* auf `Snipload.exe` klicken.

Jede Änderung am Code baut automatisch eine neue Version (siehe *Actions*).

## Funktionen

**Clip erstellen**
- Link kopieren – Snipload erkennt ihn automatisch (auch später: „Neuer Link in der Zwischenablage“)
- Vorschaubild, Titel, Kanal, Aufrufe und Datum des Videos
- **Filmstreifen-Zeitleiste** wie im Videoschnitt: Start/Ende-Griffe ziehen, Mitte verschiebt den ganzen Ausschnitt,
  beim Darüberfahren zeigt die Vorschau das Bild an genau dieser Stelle
- Zeitfelder mit −/+, Mausrad und Pfeiltasten (Umschalt = 5 s, Alt = 0,1 s, Tab wechselt den Griff)
- Links mit Zeitangabe (`&t=125`, `?t=1m30s`) setzen den Start automatisch

**Ausgabe**
- Video bis 4K oder nur Ton (MP3, M4A, WAV)
- **Shorts 9:16** (1080×1920) – Bildmitte zugeschnitten oder ganzes Bild mit unscharfem Hintergrund
- Sekundengenaues Schneiden, Dateiname mit Vorlage (`{titel}`, `{kanal}`, `{start}`, `{ende}`, `{datum}`, `{id}`)

**Arbeiten**
- **Warteschlange**: mehrere Clips sammeln, Snipload lädt sie nacheinander; der nächste Abschnitt startet
  automatisch dort, wo der letzte aufgehört hat
- **Verlauf** mit Vorschaubildern, Suche, „Nochmal“ und Größe
- Fortschritt mit Restzeit, Ton und blinkende Taskleiste, wenn ein Clip fertig ist
- **Automatische Updates**: Snipload lädt neue Versionen im Hintergrund und tauscht sich beim Neustart selbst aus
- yt-dlp-Update per Knopf, Warnung bei veralteter Version, fehlende Werkzeuge per winget installieren
- Tastenkürzel: `Strg+V` Link einfügen, `Strg+Enter` herunterladen, `Strg+1…4` Seiten wechseln

## Was im Hintergrund läuft

Snipload ist eine Oberfläche für [yt-dlp](https://github.com/yt-dlp/yt-dlp) und
[ffmpeg](https://ffmpeg.org). Beide werden beim ersten Download automatisch installiert, falls sie fehlen
(`winget install yt-dlp.yt-dlp` und `winget install Gyan.FFmpeg`).

Bitte nur Inhalte herunterladen, die du verwenden darfst.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `src/main.py` | Startpunkt |
| `src/snipload/app.py` | Hauptfenster, Seitenleiste, Ereignisse |
| `src/snipload/pages/` | die vier Seiten: Neuer Clip, Warteschlange, Verlauf, Einstellungen |
| `src/snipload/jobs.py` | Downloads, Warteschlange, Shorts-Umwandlung (yt-dlp + ffmpeg) |
| `src/snipload/updater.py` | Selbst-Update über GitHub-Releases |
| `src/snipload/tools.py` | yt-dlp/ffmpeg finden, Video-Infos, Storyboard, Updates |
| `src/snipload/widgets.py` | Bausteine: Zeitleiste, Zeitfeld, Knöpfe, Meldungen, Dialog |
| `src/snipload/theme.py` · `icons.py` | Farben, Schriften, eigene Icons |
| `assets/` | Icon |
| `tools/` | Hilfsskript für die Versionsinfo der exe |
| `.github/workflows/build.yml` | baut die exe auf Windows und veröffentlicht sie als Release |

Die Versionsnummer steht in `src/snipload/__init__.py` (`VERSION = ...`); die Build-Nummer wird automatisch angehängt.
