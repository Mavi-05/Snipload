<p align="center">
  <img src="assets/icon_1024.png" width="112" alt="Snipload-Symbol">
</p>

<h1 align="center">Snipload</h1>

<p align="center">
  <b>Video auf YouTube oder Twitch finden, den gewünschten Teil schneiden, fertigen Clip bekommen.</b><br>
  Mit Live-Vorschau, Hochkant-Formaten, animierten Untertiteln, Chat und einem Klick ins Schnittprogramm.
</p>

<p align="center">
  <a href="../../releases/latest"><b>⬇ Snipload.exe herunterladen</b></a> ·
  Windows 10 / 11 · kostenlos · ohne Installation ·
  <a href="README.md">English</a>
</p>

<p align="center">
  <img src="docs/editor.png" width="900" alt="Der Snipload-Editor: links das Video, rechts der fertige Hochkant-Clip, darunter die Zeitleiste">
</p>

---

## Warum Snipload?

Einen 3-Stunden-Stream komplett zu laden, um 30 Sekunden zu behalten, dauert lange und kostet Platz.
Snipload holt von YouTube oder Twitch nur den Teil, den du auswählst, schneidet ihn genau und macht daraus
im selben Schritt einen fertigen Short. Ohne Konto, ohne Werbung, ohne Browser-Erweiterung.

## Was es kann

### Finden
- **Link einfügen** (oder irgendwo in der App `Strg+V` drücken) – das Video öffnet sich im Editor.
- **YouTube durchsuchen**: Videos, Kanäle und Livestreams.
- **Twitch-Kanäle öffnen**: vergangene Streams, Highlights, Uploads und die Top-Clips der Woche, des Monats
  oder aller Zeiten. Ist der Streamer gerade live, kannst du den laufenden Stream über seine Aufzeichnung clippen.
- **Kanäle speichern**, von denen du oft clippst. Zuletzt geöffnete Videos sind einen Klick entfernt.

<p align="center"><img src="docs/find.png" width="900" alt="Suchergebnisse in Snipload"></p>

### Schneiden
- **Video im Editor ansehen** und Anfang und Ende mit der Maus, den Zeitfeldern oder `I` und `O` setzen.
- **Zeitleiste** mit Vorschaubildern, Kapiteln und der „Meistwiederholt“-Kurve von YouTube. Scrollen zoomt.
- **Beste Momente aus dem Chat**: Snipload liest den Chat eines Streams und markiert, wo am meisten los war.
- **Mehrere Clips auf einmal**: Abschnitte in eine Liste legen und alle mit denselben Einstellungen exportieren.
- **Bildgenaue Schnitte** – oder schnellere, wenn du das nicht brauchst.

### Formate
| Format | Was du bekommst |
|---|---|
| **Original** | Das Video, wie es ist, bis 4K |
| **Hochkant** | 9:16, zugeschnitten. Den Ausschnitt ziehst du dahin, wo du ihn willst |
| **Hochkant, ganzes Bild** | 9:16 mit dem ganzen Bild und unscharfem Hintergrund |
| **Gameplay und Facecam** | 9:16 mit der Facecam oben und dem Gameplay unten |
| **Nur Facecam** | Nur die Kamera als eigenes Video |
| **Nur Ton** | MP3, M4A oder WAV |
| **GIF** | Für Chats und Foren |

Das Ergebnis läuft live neben dem Video mit. Bei den Facecam-Formaten findet Snipload die Kamera von selbst;
du kannst den Rahmen verschieben, beide Teile zoomen und die Grenze dazwischen ziehen.

### Untertitel
<img src="docs/captions.png" width="900" alt="Animierte Untertitel in der Hochkant-Vorschau">

- **KI-Mitschrift** für jedes Video (läuft mit whisper.cpp auf deinem PC, nichts wird hochgeladen) oder die
  Untertitel, die YouTube schon hat.
- **Wort-für-Wort-Animation** mit acht Stilen als Ausgangspunkt.
- **Jede Schriftart**: die mitgelieferten, alle auf deinem PC installierten oder deine eigene Schriftdatei.
- Größe, Position, Farben, Kontur, Schatten, Kasten, Hervorhebung des gesprochenen Worts. Wörter korrigierst
  du direkt in der Liste.
- Ins Video eingebrannt, als eigene `.srt`-Datei oder beides.

### Chat
- **Chat herunterladen** – von Twitch-VODs und YouTube-Streams, passend zu deinem Clip, mit Abzeichen und
  Emotes (auch 7TV, BetterTTV und FrankerFaceZ).
- **Im Video zeigen** oder **als eigenes transparentes Video speichern** (MOV mit Alpha, WebM oder
  Greenscreen), um ihn im Schnittprogramm selbst zu platzieren.

### Verbessern
- Tempo, Helligkeit, Kontrast, Farbe, Schärfe, Lautstärke, Lautstärke-Angleichung, Blenden.
- **Hochskalieren** auf 1080p, 1440p oder 4K: schnell, mit KI (Real-ESRGAN, wird bei Bedarf geladen) oder
  mit Topaz Video AI, falls du es installiert hast.
- Datei unter einer Größe halten, zum Beispiel 10 MB für Discord.

### Ab ins Schnittprogramm
- **Premiere Pro**: Der Clip erscheint von selbst in deinem geöffneten Projekt – in einer Ablage, an der
  Abspielposition oder als neue Sequenz. Snipload installiert dafür eine kleine Erweiterung; beim ersten Mal
  braucht Premiere einen Neustart.
- **After Effects**: Der Clip wird importiert und als Komposition geöffnet.
- **CapCut, DaVinci Resolve, VEGAS** und jedes Programm, das du hinzufügst: Snipload öffnet es und legt den
  Clip in die Zwischenablage – einfach einfügen.

### Und sonst
- **10 Sprachen**: English · Deutsch · 日本語 · Español · Français · Português · 한국어 · 简体中文 · Türkçe · Русский
- **Läuft sofort**: Snipload lädt [yt-dlp](https://github.com/yt-dlp/yt-dlp) und
  [ffmpeg](https://ffmpeg.org) selbst und hält yt-dlp aktuell.
- **Aktualisiert sich selbst** im Hintergrund.
- **Bibliothek** mit allem, was du exportiert hast – mit Suche und Wiedergabe.

## So geht's los

1. **[`Snipload.exe` herunterladen](../../releases/latest)** (unter *Assets*) und starten. Es gibt nichts zu installieren.
2. Zeigt Windows *„Der Computer wurde durch Windows geschützt“*, klick auf **Weitere Informationen →
   Trotzdem ausführen**. Das passiert bei neuen Apps ohne Code-Signatur.
3. Beim ersten Start bietet Snipload an, yt-dlp und ffmpeg zu laden. Klick auf **Jetzt herunterladen** und
   warte etwa eine Minute.
4. Link einfügen oder suchen, Abschnitt wählen, **Export** drücken.

**Tastenkürzel:** `Leertaste` abspielen · `I` / `O` Anfang und Ende · `Q` / `W` zum Anfang und Ende springen ·
`A` Clip zur Liste · `Strg+Enter` exportieren · `Strg+K` suchen · `?` zeigt alle

## Häufige Fragen

<details>
<summary><b>Das Video spielt im Editor nicht ab</b></summary>

YouTube-Videos laufen über den Player von YouTube. Ein paar Videos erlauben das nicht (manche Musikvideos
zum Beispiel). Dann spielt Snipload das Video direkt ab, und wenn auch das nicht geht, zeigt es Standbilder.
Schneiden und Exportieren klappen in jedem Fall.
</details>

<details>
<summary><b>Der Export ist langsam</b></summary>

Bildgenaues Schneiden, Hochkant-Formate, Untertitel und Effekte bedeuten, dass das Video neu gerendert wird.
Snipload nutzt deine Grafikkarte, wenn es geht. Bei einfachen Clips kannst du im Reiter „Export“
**Bildgenau schneiden** ausschalten – das ist um ein Vielfaches schneller, der Clip kann dann aber einen
Moment zu früh beginnen. KI-Hochskalieren ist von Natur aus langsam.
</details>

<details>
<summary><b>„YouTube hat den Download verweigert (HTTP 403)“</b></summary>

YouTube ändert oft etwas, und ältere yt-dlp-Versionen funktionieren dann nicht mehr. Snipload aktualisiert
yt-dlp und versucht es von selbst noch einmal. Passiert es trotzdem, warte ein paar Minuten und probier es erneut.
</details>

<details>
<summary><b>Wo sind meine Dateien?</b></summary>

Standardmäßig im Ordner **Downloads**. Ändern kannst du das in den Einstellungen oder im Reiter „Export“.
Dateinamen folgen einer Vorlage mit `{title}`, `{channel}`, `{start}`, `{end}`, `{date}` und `{id}`.
</details>

<details>
<summary><b>Ist das sicher?</b></summary>

Der Quellcode liegt hier offen. Jede Version wird von GitHub Actions automatisch aus diesem Code gebaut
(siehe *Actions*). Snipload spricht mit YouTube und Twitch, mit GitHub (Updates und Werkzeuge), mit dem
offiziellen ffmpeg-Server, mit Hugging Face (Sprachmodell, nur wenn du KI-Untertitel nutzt) und mit den
Emote-Diensten 7TV, BetterTTV und FrankerFaceZ (nur wenn du einen Twitch-Chat lädst).
</details>

> Bitte lade nur Inhalte herunter, die du verwenden darfst.

## Lizenz

**Snipload darfst du kostenlos benutzen, aber es ist kein Open Source.** © 2026 Mavi-05, alle Rechte vorbehalten.

- **Erlaubt:** Snipload von dieser Seite herunterladen und kostenlos benutzen, privat und für deine Arbeit.
  Den Quellcode lesen. Snipload weiterempfehlen und auf diese Seite verlinken.
- **Ohne schriftliche Erlaubnis des Autors nicht erlaubt:** Snipload oder Teile davon kopieren, es woanders
  hochladen, veränderte oder umbenannte Fassungen veröffentlichen, es als eigenes Programm ausgeben oder
  promoten und es verkaufen.

Der Code ist öffentlich, damit du prüfen kannst, was das Programm tut. Die vollständigen Bedingungen stehen
in [LICENSE](LICENSE).

## So ist es gebaut

Siehe den Abschnitt [How it's built](README.md#how-its-built) in der englischen Fassung.
