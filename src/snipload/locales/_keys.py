"""Englische Ausgangstexte. Neue Texte nur HINTEN anhaengen - die Uebersetzungen verweisen per Nummer."""
KEYS = [
    "New clip",  # 0
    "Queue",  # 1
    "History",  # 2
    "Settings",  # 3
    "Checking tools …",  # 4
    "Link and times taken from your history.",  # 5
    "Install",  # 6
    "Later",  # 7
    "Updating yt-dlp …",  # 8
    "Okay – the update will be installed the next time you close Snipload.",  # 9
    "Installed – you're ready to go.",  # 10
    "Quit Snipload?",  # 11
    "Quit",  # 12
    "Keep downloading",  # 13
    "MENU",  # 14
    "One moment please",  # 15
    "Click here to install",  # 16
    "Update recommended",  # 17
    "Ready",  # 18
    "Install {names}?",  # 19
    "Snipload needs {names}. Install it automatically now? This takes 1–2 minutes.",  # 20
    "Installing {names} …",  # 21
    "Downloading {names} … {value:.0f} %",  # 22
    "Wait until the running download has finished.",  # 23
    "The yt-dlp update didn't work. Check your internet connection.",  # 24
    "Update now",  # 25
    "Restart now?",  # 26
    "Restart",  # 27
    "Cancel",  # 28
    "Couldn't download {names}. Check your internet connection and try again.",  # 29
    "yt-dlp updated: {before} → {after}",  # 30
    "Snipload is updating to {v} and will reopen in a moment.",  # 31
    "The update is downloading …",  # 32
    "Restart after downloads",  # 33
    "{count} download(s) are still running. Quitting will cancel them.",  # 34
    "Version {version}",  # 35
    "{names} missing",  # 36
    "yt-dlp is already the latest version ({after}).",  # 37
    "View",  # 38
    "Version {v} is ready.",  # 39
    "Update {v} is ready – Snipload will restart as soon as your downloads are finished.",  # 40
    "Snipload has been updated to version {v}.",  # 41
    "The update to {v} didn't work – Snipload keeps running with {version}.",  # 42
    "\n\nWhat's new: {notes}",  # 43
    "Snipload {get} is here",  # 44
    "You have version {version}.{notes}\n\nThe update downloads in the background – you can keep working.",  # 45
    "{count} download(s) are still running. They will be cancelled.",  # 46
    "Couldn't start the update: {ex}",  # 47
    "Couldn't restart: {ex}",  # 48
    "Play",  # 49
    "Snipload is up to date (version {version}).",  # 50
    "New version {version} available.",  # 51
    "Update {get} available",  # 52
    "Done: {t}",  # 53
    "Failed: {error}",  # 54
    "Downloading update … {value:.0f} %",  # 55
    "Restarting in {max} s – now?",  # 56
    "Restart for {get}",  # 57
    "Couldn't get any frames from the video.",  # 58
    "No face found in this section.",  # 59
    "No face stays in one place – no facecam detected.",  # 60
    "in the center",  # 61
    "The camera fills the whole frame – there is no separate facecam.",  # 62
    "Facecam detected {pos} – visible in all {count} checked frames.",  # 63
    "at the top left",  # 64
    "at the top right",  # 65
    "at the top",  # 66
    "at the bottom left",  # 67
    "at the bottom right",  # 68
    "at the bottom",  # 69
    "on the left",  # 70
    "on the right",  # 71
    "Facecam detected {pos} – visible in {hits} of {count} frames, missing at {miss}.",  # 72
    "Facecam detected {pos}, but only visible in {hits} of {count} frames (missing e.g. at {miss}).",  # 73
    "Best quality",  # 74
    "Original",  # 75
    "Original + Facecam",  # 76
    "Facecam only",  # 77
    "Shorts 9:16",  # 78
    "Shorts + blur",  # 79
    "Facecam split",  # 80
    "Waiting…",  # 81
    "Cutting the section…",  # 82
    "Best",  # 83
    " + original",  # 84
    "Cancelled",  # 85
    "Starting…",  # 86
    "Done",  # 87
    "Error",  # 88
    "Unknown error.",  # 89
    "YouTube blocked the download – updating yt-dlp and trying again…",  # 90
    "Connecting to YouTube…",  # 91
    "Cutting out the facecam…",  # 92
    "Converting to Shorts format…",  # 93
    "Downloading…",  # 94
    "audio",  # 95
    "video",  # 96
    "Merging video and audio…",  # 97
    " · Shorts",  # 98
    " · Shorts+blur",  # 99
    " · Facecam split",  # 100
    "about {int} s left",  # 101
    "about {value} min left",  # 102
    "{value} files · ",  # 103
    "{files}in {secs:.0f} s",  # 104
    "Original + Facecam {size}",  # 105
    "Facecam 1:1 · {size}",  # 106
    "{names} missing. Install it under Settings → Tools.",  # 107
    "Converting to Shorts format didn't work.",  # 108
    "Downloading {what}…",  # 109
    "{float:.1f}× speed",  # 110
    "Downloading {what} and cutting…",  # 111
    "Reading video data…",  # 112
    "Unexpected error: {ex}",  # 113
    "Converting to {upper}…",  # 114
    "Video",  # 115
    "Audio only",  # 116
    "This link doesn't work.",  # 117
    "Paste a link above – then set the start and end here.",  # 118
    "Paste",  # 119
    "No video yet",  # 120
    "Copy a YouTube link – Snipload picks it up automatically.",  # 121
    "Watch on YouTube from start",  # 122
    "Reload",  # 123
    "Whole video",  # 124
    "From link time",  # 125
    "START",  # 126
    "END",  # 127
    "Tip: click the bar, then ← → move the handle (Shift = 5 s, Alt = 0.1 s), Tab switches between start and end.",  # 128
    "QUALITY",  # 129
    "Also save the normal video",  # 130
    "Adjust …",  # 131
    "Check again",  # 132
    "Add to queue",  # 133
    "Download",  # 134
    "Next clip",  # 135
    "Show in folder",  # 136
    "Try again",  # 137
    "Close",  # 138
    "Unknown title",  # 139
    "  The time range has changed – “Check again” checks it once more.",  # 140
    " + normal video",  # 141
    "Paste YouTube link  (Ctrl + V)",  # 142
    "There's no link in the clipboard.",  # 143
    "Link taken from the clipboard.",  # 144
    "Couldn't load the video",  # 145
    "The facecam isn't visible in the whole section – take a quick look.",  # 146
    "Facecam set by you.",  # 147
    "Looking for the facecam – one moment.",  # 148
    "Paste a link first and wait until the video has loaded.",  # 149
    "The end has to be after the start.",  # 150
    "No video loaded yet",  # 151
    "Paste a YouTube link above.",  # 152
    "Check the times",  # 153
    "Paste a link, pick a section, done.",  # 154
    "Apply",  # 155
    "Section",  # 156
    "LENGTH",  # 157
    "Output",  # 158
    "CONTENT",  # 159
    "FORMAT",  # 160
    "FILE NAME",  # 161
    "SAVE TO",  # 162
    "Change",  # 163
    "Open",  # 164
    "Loading the video …",  # 165
    "Getting title, length and preview images.",  # 166
    "yt-dlp is still missing",  # 167
    "Snipload needs yt-dlp to load videos.",  # 168
    "AUDIO FORMAT",  # 169
    "Audio only has no aspect ratio.",  # 170
    "As soon as the video has loaded, Snipload looks for the facecam.",  # 171
    "Sizes & facecam …",  # 172
    "Load a video first.",  # 173
    "Start or end isn't a valid time (e.g. 00:03:00).",  # 174
    "The target folder is invalid. Choose another one.",  # 175
    "Still detecting the facecam – one moment.",  # 176
    "Added to the queue – {n} pending.",  # 177
    "{time} – {time2}  ·  {fmt_duration_words}",  # 178
    "Audio only · {get}",  # 179
    "Video · {get}",  # 180
    "Clip {rng}",  # 181
    "That's not a valid link",  # 182
    "A YouTube link starts with https://",  # 183
    "{fmt_count} views",  # 184
    "There are no frames available for this video – please set the facecam by hand.",  # 185
    "Analyzing the frames and looking for the facecam …",  # 186
    " Tip: use “Shorts 9:16” instead.",  # 187
    "The start is past the end of the video ({time}).",  # 188
    "Please set the facecam first (Adjust …).",  # 189
    "New link in the clipboard:  {short}",  # 190
    "Analysis failed: {exc}",  # 191
    "In the queue",  # 192
    "Like on YouTube, no cropping.",  # 193
    "Portrait 1080×1920 for Shorts, TikTok and Reels – the center of the frame is cut out.",  # 194
    "Portrait 1080×1920: the whole frame in the middle, blurred background above and below.",  # 195
    "Portrait 1080×1920: facecam on top, gameplay below. Snipload finds the facecam automatically and sets the sizes – under “Adjust” you can make the facecam and gameplay bigger or smaller.",  # 196
    "Just the facecam as its own video – 1:1 at original size, cut out pixel-perfect, without the border. Snipload downloads the video in best quality for this.",  # 197
    "Two files from one download: the normal video and the facecam 1:1 at original size (pixel-perfect, without the border). Downloads in best quality.",  # 198
    "Getting frames from the section … {i}/{n}",  # 199
    " Click “Adjust” and set it.",  # 200
    "Starting in a moment …",  # 201
    "Done!  ",  # 202
    "That didn't work",  # 203
    "No facecam detected.",  # 204
    "{ahead} clip(s) ahead – starts automatically.",  # 205
    "Set up facecam – Snipload",  # 206
    "Automatic",  # 207
    "FACECAM HEIGHT",  # 208
    "FACECAM ZOOM",  # 209
    "GAMEPLAY ZOOM",  # 210
    "Set the facecam by hand.",  # 211
    "Facecam",  # 212
    "Gameplay",  # 213
    "whole frame",  # 214
    "Set up facecam",  # 215
    "Drag the red frame onto the facecam – use the corners to change its size.",  # 216
    "Width",  # 217
    "Height",  # 218
    "Fine-tuning: arrow keys move by 1 px, with Shift they change the size.",  # 219
    "CHECKED FRAMES IN THE RANGE",  # 220
    "Facecam at the bottom",  # 221
    " Please set the frame by hand.",  # 222
    "THIS IS YOUR SHORT",  # 223
    "YOUR FACECAM (1:1)",  # 224
    "Drag to move · scroll to zoom · drag the divider to change the height",  # 225
    "Detect again",  # 226
    "px  ·  video {ref_w}×{ref_h}",  # 227
    "{int} % · with border",  # 228
    " Quickly check the frames below.",  # 229
    " Take a look at the frames marked in yellow.",  # 230
    "Clear",  # 231
    "No clips yet",  # 232
    "Everything you download ends up here.",  # 233
    "Clear history?",  # 234
    "The list will be cleared. Your files stay where they are, of course.",  # 235
    "Clip",  # 236
    "Search …",  # 237
    "File no longer exists",  # 238
    "Your downloaded clips.",  # 239
    "Again",  # 240
    "Nothing found",  # 241
    "End",  # 242
    "{count} clips  ·  {fmt_size}",  # 243
    "No clip matches “{q}”.",  # 244
    "Waiting",  # 245
    "Downloading",  # 246
    "Remove finished",  # 247
    "Nothing in the queue",  # 248
    "Use “Add to queue” to collect several clips –\nSnipload downloads them one after another.",  # 249
    "Create a new clip",  # 250
    "Clips that Snipload downloads one after another.",  # 251
    "Waiting – {ahead} ahead",  # 252
    "{active} pending  ·  {done} done",  # 253
    "My favorite video",  # 254
    "Channel name",  # 255
    "Language",  # 256
    "App language",  # 257
    "Restart now",  # 258
    "Save",  # 259
    "Cutting & workflow",  # 260
    "Frame-accurate cuts",  # 261
    "Start and end are exact. Turned off it's faster, but the cut may start a few seconds earlier.",  # 262
    "Sound when a clip is done",  # 263
    "Open the folder after downloading",  # 264
    "Shows the finished file right away in Explorer.",  # 265
    "Detect links in the clipboard",  # 266
    "When you copy a YouTube link, Snipload suggests it automatically.",  # 267
    "Updates",  # 268
    "Check for updates",  # 269
    "Download updates automatically",  # 270
    "New versions download in the background and are installed with a quick restart.",  # 271
    "Tools",  # 272
    "Snipload uses yt-dlp to download and ffmpeg to cut. If downloads suddenly stop working, a yt-dlp update almost always helps.",  # 273
    "Downloads the videos from YouTube",  # 274
    "Cuts and converts",  # 275
    "About Snipload",  # 276
    "Checking …",  # 277
    "Checking for updates …",  # 278
    "Set up Snipload the way you like it.",  # 279
    "Target folder",  # 280
    "File name template",  # 281
    "Placeholders: {title}  {channel}  {start}  {end}  {date}  {id}",  # 282
    "Default",  # 283
    "Clips from YouTube videos – fast, precise, no detours.",  # 284
    "Data folder",  # 285
    "Please only download content you're allowed to use.",  # 286
    "Update",  # 287
    "Not installed",  # 288
    "Not checked yet.",  # 289
    "Snipload restarts to switch the language.",  # 290
    "Example:  {ex}.mp4",  # 291
    "  (Opens on the download page.)",  # 292
    "Downloading …",  # 293
    "  ·  recent enough",  # 294
    "Version {fv}",  # 295
    "You have the latest version (checked at {get}).",  # 296
    "Version {ver}",  # 297
    "Version {get} is available.",  # 298
    "  ·  {age} days old – update recommended",  # 299
    " What's new: {notes}",  # 300
    "Downloading version {get} … {value:.0f} %",  # 301
    "Version {get} is ready.",  # 302
    "Update check failed.",  # 303
    "This video is private.",  # 304
    "This video isn't available (deleted, blocked or not available in your country).",  # 305
    "This video is age-restricted and needs a sign-in.",  # 306
    "YouTube is currently blocking the request. Update yt-dlp in the settings and try again.",  # 307
    "YouTube refused the download (HTTP 403). Snipload already updated yt-dlp and tried again – wait a few minutes and try once more.",  # 308
    "Snipload can't open this link.",  # 309
    "No connection. Check your internet connection.",  # 310
    "Livestreams and premieres can only be downloaded after they've ended.",  # 311
    "yt-dlp is missing",  # 312
    "This is a playlist. Please paste the link of a single video.",  # 313
    "YouTube isn't responding. Check your internet connection.",  # 314
    "No video info found.",  # 315
    "This Snipload version doesn't know its build number – please download it once by hand from GitHub.",  # 316
    "The latest version doesn't contain a Snipload.exe.",  # 317
    "The update arrived incomplete. Please try again.",  # 318
    "The update arrived damaged (wrong checksum). Please try again.",  # 319
    "Self-update only works in the finished exe.",  # 320
    "No connection to GitHub.",  # 321
    "Downloading the update failed. Check your internet connection.",  # 322
    "The downloaded file isn't a valid exe.",  # 323
    "No releases found. (Is the GitHub repo private?)",  # 324
    "GitHub is rate-limiting requests right now. Try again later.",  # 325
    "GitHub answered with error {code}.",  # 326
    "Cancelled.",  # 327
    "end",  # 328
    "{h} h {m:02d} min",  # 329
    "{sec} s",  # 330
    "{m} min {s:02d} s",  # 331
    "{m} min",  # 332
    "Loading video …",  # 333
    "This clip is cut frame-accurately, so the video is re-encoded – on this PC that's slow. Turn off “Frame-accurate cuts” in the settings for much faster downloads.",  # 334
    "1 clip  ·  {fmt_size}",  # 335
]
