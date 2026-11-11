"""Englische Ausgangstexte. Neue Texte nur HINTEN anhaengen - die Uebersetzungen verweisen per Nummer."""
KEYS = [
    "Settings",  # 0
    "Install",  # 1
    "Later",  # 2
    "Updating yt-dlp …",  # 3
    "Quit",  # 4
    "Ready",  # 5
    "Installing {names} …",  # 6
    "Downloading {names} … {value:.0f} %",  # 7
    "Cancel",  # 8
    "Couldn't download {names}. Check your internet connection and try again.",  # 9
    "yt-dlp updated: {before} → {after}",  # 10
    "yt-dlp is already the latest version ({after}).",  # 11
    "Snipload has been updated to version {v}.",  # 12
    "Play",  # 13
    "Couldn't get any frames from the video.",  # 14
    "No face found in this section.",  # 15
    "No face stays in one place – no facecam detected.",  # 16
    "in the center",  # 17
    "The camera fills the whole frame – there is no separate facecam.",  # 18
    "Facecam detected {pos} – visible in all {count} checked frames.",  # 19
    "at the top left",  # 20
    "at the top right",  # 21
    "at the top",  # 22
    "at the bottom left",  # 23
    "at the bottom right",  # 24
    "at the bottom",  # 25
    "on the left",  # 26
    "on the right",  # 27
    "Facecam detected {pos} – visible in {hits} of {count} frames, missing at {miss}.",  # 28
    "Facecam detected {pos}, but only visible in {hits} of {count} frames (missing e.g. at {miss}).",  # 29
    "Best quality",  # 30
    "Original",  # 31
    "Original + Facecam",  # 32
    "Facecam only",  # 33
    "Shorts 9:16",  # 34
    "Shorts + blur",  # 35
    "Facecam split",  # 36
    "Waiting…",  # 37
    "Cutting the section…",  # 38
    "Best",  # 39
    " + original",  # 40
    "Cancelled",  # 41
    "Starting…",  # 42
    "Done",  # 43
    "Error",  # 44
    "Unknown error.",  # 45
    "YouTube blocked the download – updating yt-dlp and trying again…",  # 46
    "Connecting to YouTube…",  # 47
    "Cutting out the facecam…",  # 48
    "Downloading…",  # 49
    "audio",  # 50
    "video",  # 51
    "Merging video and audio…",  # 52
    " · Shorts",  # 53
    " · Shorts+blur",  # 54
    " · Facecam split",  # 55
    "about {int} s left",  # 56
    "about {value} min left",  # 57
    "{value} files · ",  # 58
    "{files}in {secs:.0f} s",  # 59
    "Original + Facecam {size}",  # 60
    "Facecam 1:1 · {size}",  # 61
    "{names} missing. Install it under Settings → Tools.",  # 62
    "Converting to Shorts format didn't work.",  # 63
    "Downloading {what}…",  # 64
    "{float:.1f}× speed",  # 65
    "Downloading {what} and cutting…",  # 66
    "Reading video data…",  # 67
    "Unexpected error: {ex}",  # 68
    "Converting to {upper}…",  # 69
    "Video",  # 70
    "Download",  # 71
    "Show in folder",  # 72
    "Try again",  # 73
    "Close",  # 74
    "Looking for the facecam – one moment.",  # 75
    "Change",  # 76
    "There are no frames available for this video – please set the facecam by hand.",  # 77
    "Analyzing the frames and looking for the facecam …",  # 78
    "Getting frames from the section … {i}/{n}",  # 79
    "Facecam",  # 80
    "Width",  # 81
    "Height",  # 82
    "Facecam at the bottom",  # 83
    "Clear",  # 84
    "File no longer exists",  # 85
    "Language",  # 86
    "Restart now",  # 87
    "Check for updates",  # 88
    "Update",  # 89
    "Not installed",  # 90
    "This video is private.",  # 91
    "This video isn't available (deleted, blocked or not available in your country).",  # 92
    "This video is age-restricted and needs a sign-in.",  # 93
    "YouTube is currently blocking the request. Update yt-dlp in the settings and try again.",  # 94
    "YouTube refused the download (HTTP 403). Snipload already updated yt-dlp and tried again – wait a few minutes and try once more.",  # 95
    "Snipload can't open this link.",  # 96
    "No connection. Check your internet connection.",  # 97
    "Livestreams and premieres can only be downloaded after they've ended.",  # 98
    "yt-dlp is missing",  # 99
    "This is a playlist. Please paste the link of a single video.",  # 100
    "YouTube isn't responding. Check your internet connection.",  # 101
    "No video info found.",  # 102
    "This Snipload version doesn't know its build number – please download it once by hand from GitHub.",  # 103
    "The latest version doesn't contain a Snipload.exe.",  # 104
    "The update arrived incomplete. Please try again.",  # 105
    "The update arrived damaged (wrong checksum). Please try again.",  # 106
    "Self-update only works in the finished exe.",  # 107
    "No connection to GitHub.",  # 108
    "Downloading the update failed. Check your internet connection.",  # 109
    "The downloaded file isn't a valid exe.",  # 110
    "No releases found. (Is the GitHub repo private?)",  # 111
    "GitHub is rate-limiting requests right now. Try again later.",  # 112
    "GitHub answered with error {code}.",  # 113
    "Cancelled.",  # 114
    "end",  # 115
    "{h} h {m:02d} min",  # 116
    "{sec} s",  # 117
    "{m} min {s:02d} s",  # 118
    "{m} min",  # 119
    "Creating captions…",  # 120
    "Loading chat…",  # 121
    "Finding hype moments in the chat…",  # 122
    "Sent to Premiere Pro – it appears in the “Snipload” bin of your open project.",  # 123
    "Downloading the AI speech engine…",  # 124
    "Downloading the AI upscaler…",  # 125
    "Loading the audio of the section…",  # 126
    "Transcribing with AI…",  # 127
    "This program wasn't found on your PC.",  # 128
    "Premiere integration installed. Restart Premiere once – after that clips arrive automatically.",  # 129
    "Getting captions from YouTube…",  # 130
    "Loading Twitch chat…",  # 131
    "Loading emotes and badges…",  # 132
    "Loading the chat replay (whole stream, this can take a moment)…",  # 133
    "Importing into After Effects…",  # 134
    "Chat is only available for Twitch VODs and YouTube streams.",  # 135
    "Downloading the AI model ({mb} MB, only once)…",  # 136
    "{name} opened – the clip is in your clipboard: press Ctrl+V in the media panel.",  # 137
    "Rendering…",  # 138
    "Rendering chat…",  # 139
    "Creating GIF…",  # 140
    "AI upscaling ×{n}…",  # 141
    "Snipload needs Microsoft Edge WebView2 to show its window. It is part of Windows 11 and of most Windows 10 PCs, but it is missing here.\n\nClick OK to open Microsoft's download page. Install the \"Evergreen Bootstrapper\", then start Snipload again.",  # 142
    "Update available",  # 143
    "Exported “{name}”",  # 144
    "Show",  # 145
    "Export failed: {error}",  # 146
    "Update {v} is ready – restart to install",  # 147
    "Update {v} is available",  # 148
    "Quit while exporting?",  # 149
    "{n} exports are still running. They are cancelled if you quit now.",  # 150
    "An export is still running. It is cancelled if you quit now.",  # 151
    "Keep exporting",  # 152
    "Download now",  # 153
    "Everything is set up. You can start clipping.",  # 154
    "One-time setup",  # 155
    "Snipload needs {names} to download and cut videos. They are downloaded once (about 110 MB) and kept up to date automatically.",  # 156
    "A new version is available.",  # 157
    "Downloading the update… {p} %",  # 158
    "Restart and update",  # 159
    "Download update",  # 160
    "Open the download page",  # 161
    "Keyboard shortcuts",  # 162
    "Drop the link to open it",  # 163
    "Lost the connection to Snipload. Please restart the app.",  # 164
    "Click to type a value",  # 165
    "No video open",  # 166
    "Find a video or paste a link, then cut your clip here.",  # 167
    "Find a video",  # 168
    "Opening the video…",  # 169
    "Couldn’t open this video",  # 170
    "Back",  # 171
    "This stream is still live. Open its recording (VOD) to clip it, or wait until the stream has ended.",  # 172
    "This video has no length information, so it can’t be cut.",  # 173
    "Preview without sound: this video can only be shown as still frames here. The export has sound.",  # 174
    "Open the original page",  # 175
    "Close this video",  # 176
    "Play or pause",  # 177
    "Start of the clip",  # 178
    "End of the clip",  # 179
    "Repeat the clip while playing",  # 180
    "Mute",  # 181
    "Jump to the start of the clip",  # 182
    "Jump to the end of the clip",  # 183
    "Start the clip here",  # 184
    "End the clip here",  # 185
    "Save this frame as an image",  # 186
    "Zoom out",  # 187
    "Zoom in",  # 188
    "Zoom to the clip",  # 189
    "Show the whole video",  # 190
    "Find the facecam first, or draw its frame in the picture.",  # 191
    "This clip is already in the list.",  # 192
    "Added clip {n}. Pick the next part, then export them all at once.",  # 193
    "One of the most replayed moments",  # 194
    "The chat went wild here ({n} messages)",  # 195
    "Drag the white frame to pick your clip. Scroll to zoom.",  # 196
    "Frame saved as an image",  # 197
    "Load the chat first.",  # 198
    "Exporting {n} clips",  # 199
    "Export started",  # 200
    "Search or paste a link",  # 201
    "What do you want to clip?",  # 202
    "Paste a link or type a Twitch channel",  # 203
    "Paste a link or search YouTube",  # 204
    "Live",  # 205
    "Upcoming",  # 206
    "Open in the editor",  # 207
    "Open the full stream at this moment",  # 208
    "Go to the channel",  # 209
    "Copy link",  # 210
    "Link copied",  # 211
    "Remove from this list",  # 212
    "Untitled",  # 213
    "{n} views",  # 214
    "Works with YouTube videos, streams and Shorts, and with Twitch VODs and clips. Copy a link and press Ctrl+V anywhere in Snipload to open it.",  # 215
    "Saved channels",  # 216
    "Remove from saved channels",  # 217
    "Recently opened",  # 218
    "The search didn’t work",  # 219
    "Nothing found for “{q}”",  # 220
    "Twitch search finds channels. Type the name of a streamer, or paste a link to a VOD or clip.",  # 221
    "Check the spelling, or paste the link of the video instead.",  # 222
    "Couldn’t open this channel",  # 223
    "Removed from saved channels",  # 224
    "Saved. You’ll find the channel on the start page.",  # 225
    "Saved",  # 226
    "Save channel",  # 227
    "Open on {site}",  # 228
    "This stream has no recording yet. The streamer may have turned VODs off.",  # 229
    "{n} watching",  # 230
    "Clip the running stream",  # 231
    "Nothing here yet",  # 232
    "This channel has no {what}.",  # 233
    "Export",  # 234
    "You are exporting sound only, so the picture format doesn’t matter. Change this on the Export tab.",  # 235
    "Crop",  # 236
    "Position",  # 237
    "You can also drag the frame in the picture, or the result itself.",  # 238
    "The whole picture stays visible. The space above and below is filled with a blurred copy of the video.",  # 239
    "Find it again",  # 240
    "Find the facecam",  # 241
    "Draw it myself",  # 242
    "Snipload looks at ten frames of your clip and finds the camera on its own. You can adjust the frame afterwards.",  # 243
    "Layout",  # 244
    "Facecam height",  # 245
    "Gameplay zoom",  # 246
    "Facecam zoom",  # 247
    "Remember this layout",  # 248
    "Use the same sizes for your next videos",  # 249
    "Tip: drag inside the result to move the picture, scroll to zoom, and drag the border between the two parts.",  # 250
    "Also keep the uncropped clip",  # 251
    "No speech found in this part of the video.",  # 252
    "Captions are for video exports. You are exporting sound only.",  # 253
    "You can keep working while the captions are created.",  # 254
    "AI transcription (works with every video)",  # 255
    "YouTube subtitles: {name}",  # 256
    "(automatic)",  # 257
    "From",  # 258
    "Accuracy",  # 259
    "Fast",  # 260
    "Balanced",  # 261
    "Spoken language",  # 262
    "Detect automatically",  # 263
    "Translate to English",  # 264
    "The speech model ({mb} MB) is downloaded once. Everything runs on your PC, nothing is uploaded.",  # 265
    "Create captions for this clip",  # 266
    "Animated captions like in Premiere or CapCut: word by word, in your font and colors.",  # 267
    "Your clip now reaches beyond the captions.",  # 268
    "Create them again",  # 269
    "Show captions",  # 270
    "Style",  # 271
    "Text",  # 272
    "Font",  # 273
    "Size",  # 274
    "From the top of the picture. You can also drag the captions in the preview.",  # 275
    "Words at once",  # 276
    "Lines",  # 277
    "All caps",  # 278
    "Letter spacing",  # 279
    "Colors",  # 280
    "Spoken word",  # 281
    "Box",  # 282
    "Outline",  # 283
    "Shadow",  # 284
    "Color",  # 285
    "Glow",  # 286
    "Grow",  # 287
    "Off",  # 288
    "Box behind the text",  # 289
    "Box opacity",  # 290
    "Motion",  # 291
    "New words appear with",  # 292
    "Pop",  # 293
    "Fade",  # 294
    "Slide",  # 295
    "Cut",  # 296
    "Spoken word bounces",  # 297
    "Dim the words not yet spoken",  # 298
    "Words",  # 299
    "Click a line to fix a word. Click the time to jump there.",  # 300
    "Save as",  # 301
    "Part of the video",  # 302
    "Separate .srt file",  # 303
    "For Premiere, CapCut or YouTube",  # 304
    "Check the exact look",  # 305
    "Start over",  # 306
    "Captions are hidden.",  # 307
    "Couldn’t render the preview.",  # 308
    "Exactly as it will be exported",  # 309
    "Search fonts",  # 310
    "Made for captions",  # 311
    "Your font files",  # 312
    "Installed on this PC",  # 313
    "No font with this name.",  # 314
    "Add a font file",  # 315
    "Added “{name}”",  # 316
    "Chat is for video exports. You are exporting sound only.",  # 317
    "This video has no chat replay. Chat works with Twitch VODs and with YouTube streams that have a chat replay.",  # 318
    "Nobody wrote in the chat during this part.",  # 319
    "Get the chat of your clip. Show it in the video, or save it as its own transparent video for Premiere, After Effects or CapCut.",  # 320
    "Load the chat of this clip",  # 321
    "Your clip now reaches beyond the loaded chat.",  # 322
    "{n} messages loaded",  # 323
    "Load again",  # 324
    "In the video",  # 325
    "Show the chat in the video",  # 326
    "Corner",  # 327
    "Top left",  # 328
    "Top right",  # 329
    "Bottom left",  # 330
    "Bottom right",  # 331
    "As its own file",  # 332
    "Don’t save the chat separately",  # 333
    "Transparent MOV (Premiere, After Effects, DaVinci)",  # 334
    "Transparent WebM (CapCut, browsers)",  # 335
    "Green screen MP4 (works everywhere)",  # 336
    "The chat is saved next to your clip, with the same length. Put it on a track above the video.",  # 337
    "Look",  # 338
    "Text size",  # 339
    "Bubble behind each message",  # 340
    "Dark panel behind the chat",  # 341
    "Darkness",  # 342
    "Badges",  # 343
    "Emotes",  # 344
    "Colored names",  # 345
    "Messages stay for",  # 346
    "Always",  # 347
    "Best moments",  # 348
    "The busiest moments are marked on the timeline. Click one of the chips above the timeline to jump there.",  # 349
    "Snipload reads the whole chat and marks where it was busiest. That is usually where the best clips are.",  # 350
    "Search again",  # 351
    "Find the best moments",  # 352
    "Speed",  # 353
    "Picture",  # 354
    "Brightness",  # 355
    "Contrast",  # 356
    "Sharpen",  # 357
    "AI (Real-ESRGAN)",  # 358
    "Method",  # 359
    "The AI upscaler is downloaded once (about 45 MB).",  # 360
    "The AI redraws every frame. That looks much sharper, but takes a few minutes per minute of video.",  # 361
    "Uses the Topaz Video AI installed on this PC. You need to be signed in to Topaz.",  # 362
    "Scales the picture up and sharpens it. Quick, and fine for most clips.",  # 363
    "Topaz Video AI appears here as soon as it is installed.",  # 364
    "Upscale",  # 365
    "Frames per second",  # 366
    "As in the video",  # 367
    "Sound",  # 368
    "Volume",  # 369
    "Even out the loudness",  # 370
    "The usual level for Shorts, Reels and TikTok",  # 371
    "Remove the sound",  # 372
    "Fade in",  # 373
    "Fade out",  # 374
    "Sound only",  # 375
    "Quality",  # 376
    "Best available",  # 377
    "Cut exactly to the frame",  # 378
    "Off is faster, but the clip can start a moment early",  # 379
    "Keep the file under",  # 380
    "No limit",  # 381
    "Smaller file (H.265)",  # 382
    "Half the size, but some apps can’t open it",  # 383
    "Format",  # 384
    "GIFs get big quickly. Keep them short, a few seconds work best.",  # 385
    "File name",  # 386
    "File",  # 387
    "Name",  # 388
    "Remove",  # 389
    "Several clips at once",  # 390
    "Pick a part, add it to the list, pick the next one. All clips are exported with the same settings.",  # 391
    "Add the current clip",  # 392
    "Don’t open",  # 393
    "Project bin",  # 394
    "At the playhead",  # 395
    "New sequence",  # 396
    "The clip appears in your open Premiere project by itself.",  # 397
    "The first time, Premiere needs one restart. After that every clip appears in your open project by itself.",  # 398
    "The clip is imported into After Effects and opened as a composition.",  # 399
    "{name} opens and the clip is in your clipboard: press Ctrl+V in its media panel.",  # 400
    "No editing program found on this PC. You can add one in the settings.",  # 401
    "Then open in",  # 402
    "best quality",  # 403
    "Captions",  # 404
    "Chat",  # 405
    "upscaled to {p}",  # 406
    "under {n} MB",  # 407
    "{n} clips",  # 408
    "Export {n} clips to {name}",  # 409
    "Export to {name}",  # 410
    "Export {n} clips",  # 411
    "Via clipboard",  # 412
    "No editing program found",  # 413
    "Open in",  # 414
    "Add a program…",  # 415
    "Copied. Press Ctrl+V in your editing program or in a chat.",  # 416
    "Copying files only works on Windows.",  # 417
    "Exports",  # 418
    "Saved in",  # 419
    "Clear finished",  # 420
    "Nothing exported yet",  # 421
    "Cut a clip in the editor and press Export. You can follow the progress here.",  # 422
    "Waiting for its turn",  # 423
    "Working…",  # 424
    "{n} files",  # 425
    "Sent to {name}",  # 426
    "AI upscaling didn’t work, the fast method was used instead.",  # 427
    "Something went wrong.",  # 428
    "Copy the file",  # 429
    "Search your clips",  # 430
    "Library",  # 431
    "More",  # 432
    "Clear the list (keeps your files)",  # 433
    "Clear the library?",  # 434
    "The list is emptied. Your video files stay where they are.",  # 435
    "Your clips will collect here",  # 436
    "Everything you export shows up in the library, ready to play, send to your editing program or clip again.",  # 437
    "No clip matches “{q}”",  # 438
    "Clip this video again",  # 439
    "Remove from the library",  # 440
    "Delete the files",  # 441
    "Delete the file",  # 442
    "Delete this clip?",  # 443
    "“{name}” is deleted from your PC. This can’t be undone.",  # 444
    "Delete",  # 445
    "File is gone",  # 446
    "Example: {name}.mp4",  # 447
    "General",  # 448
    "Restart Snipload?",  # 449
    "The new language is used after a restart.",  # 450
    "Save clips in",  # 451
    "Open the folder",  # 452
    "File names",  # 453
    "You can use {title}, {channel}, {start}, {end}, {date} and {id}.",  # 454
    "Play a sound when exports are done",  # 455
    "Use the graphics card for exports",  # 456
    "Much faster. Turn it off if exports fail or look wrong.",  # 457
    "Sign in with your browser",  # 458
    "For age-restricted and members-only videos. Snipload uses the sign-in of this browser.",  # 459
    "Direct import",  # 460
    "Editing programs",  # 461
    "Snipload looks for Premiere Pro, After Effects, DaVinci Resolve, VEGAS and CapCut. None of them was found. You can add any other program yourself.",  # 462
    "Connection to Premiere Pro",  # 463
    "Installed",  # 464
    "Install again",  # 465
    "Installed. Restart Premiere once, after that clips arrive in your project by themselves.",  # 466
    "A small extension that puts every exported clip into your open project.",  # 467
    "Clips arrive in Premiere",  # 468
    "AI captions",  # 469
    "Speech recognition runs on your PC. A model is downloaded the first time you use it.",  # 470
    "Upscaling",  # 471
    "AI upscaling that runs on any graphics card",  # 472
    "Found",  # 473
    "Not found",  # 474
    "Used automatically when it is installed on this PC",  # 475
    "Download engine",  # 476
    "Missing",  # 477
    "{n} days old. YouTube changes often, an update is a good idea.",  # 478
    "Up to date. Snipload updates it by itself.",  # 479
    "Reads and downloads the videos",  # 480
    "Cuts and converts the clips",  # 481
    "Checking…",  # 482
    "Version {v} is available",  # 483
    "Downloading version {v}…",  # 484
    "Version {v} is ready. It is installed when you close Snipload.",  # 485
    "You have the newest version.",  # 486
    "About",  # 487
    "Update automatically",  # 488
    "Licenses",  # 489
    "Chapters",  # 490
    "Most replayed and chat activity",  # 491
    "Find",  # 492
    "Editor",  # 493
    "Videos",  # 494
    "Streams",  # 495
    "Shorts",  # 496
    "Past broadcasts",  # 497
    "Highlights",  # 498
    "Uploads",  # 499
    "Top clips this week",  # 500
    "Top clips this month",  # 501
    "Top clips of all time",  # 502
    "Enhance",  # 503
    "Vertical",  # 504
    "Vertical, full picture",  # 505
    "Gameplay and facecam",  # 506
    "Vertical 9:16",  # 507
    "Vertical 9:16 with blur",  # 508
    "Gameplay and facecam 9:16",  # 509
    "Channels",  # 510
    "Everywhere",  # 511
    "Jump to the start or end of the clip",  # 512
    "Step 1 second (Shift: 5 seconds, Alt: one frame)",  # 513
    "Jump 10 seconds back or forward",  # 514
    "Add the clip to the list",  # 515
    "Zoom the timeline",  # 516
    "Open the link from the clipboard",  # 517
    "Switch between Find, Editor, Exports and Library",  # 518
    "Show these shortcuts",  # 519
    "The preview of this video has no sound. The export has sound.",  # 520
    "Snipload is free to use. Copying it, uploading it somewhere else or passing it off as your own is not allowed.",  # 521
]
