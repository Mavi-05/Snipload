# Snipload

<img src="assets/icon_1024.png" width="96" align="right" alt="Snipload Icon">

Lädt nur den Teil eines YouTube-Videos herunter, den du wirklich brauchst – zum Beispiel
von `00:03:00` bis `00:06:00`. Als Video (MP4) oder nur den Ton (MP3).

## Download

👉 **[Neueste Snipload.exe herunterladen](../../releases/latest)** – unter *Assets* auf `Snipload.exe` klicken.

Jede Änderung am Code baut automatisch eine neue Version (siehe *Actions*).

## Funktionen

- Link kopieren → Snipload fügt ihn automatisch ein
- Vorschaubild, Titel, Kanal und Länge des Videos
- Zeitleiste mit zwei Griffen für Start und Ende (Mitte ziehen verschiebt den ganzen Ausschnitt)
- Links mit Zeitangabe (`&t=125`, `?t=1m30s`) setzen den Start automatisch
- „Auf YouTube ab Start prüfen“ – öffnet das Video genau an der Startzeit
- Sekundengenaues Schneiden, Qualität wählbar (beste / 1080p / 720p / 480p)
- Fortschritt mit Restzeit, danach *Abspielen* und *Im Ordner zeigen*
- Verlauf der letzten Clips, mit „Nochmal“ wieder laden
- Knopf zum Aktualisieren von yt-dlp; fehlende Werkzeuge werden per winget installiert

## Was im Hintergrund läuft

Snipload ist eine Oberfläche für [yt-dlp](https://github.com/yt-dlp/yt-dlp) und
[ffmpeg](https://ffmpeg.org). Beide werden beim ersten Download automatisch installiert, falls sie fehlen
(`winget install yt-dlp.yt-dlp` und `winget install Gyan.FFmpeg`).

Bitte nur Inhalte herunterladen, die du verwenden darfst.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `src/snipload.py` | das komplette Programm (Python, CustomTkinter) |
| `assets/` | Icon |
| `tools/` | Hilfsskript für die Versionsinfo der exe |
| `.github/workflows/build.yml` | baut die exe auf Windows und veröffentlicht sie als Release |

Die Versionsnummer steht oben in `src/snipload.py` (`VERSION = ...`); die Build-Nummer wird automatisch angehängt.
