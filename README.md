# LiveClip Studio AI

Turn a long video into vertical short clips — for real, for free.

**Live site:** https://sgsuprio.github.io/LiveClip-Studio-AI/

## How it works (no fake demo data)

1. **On the site:** paste a YouTube URL, pick clip length (15–30s / 30–60s / 60–90s),
   clip count and caption style (Hormozi / Minimal / Neon), then click
   **Generate Viral Clips** and **Open Colab Notebook**. Your settings travel
   with the Colab link itself — nothing to download or upload.
2. **In Colab:** pick a free T4 GPU runtime, then Run all. The notebook reads
   your settings from the link, downloads the video, transcribes it with
   faster-whisper, scores every window for viral hooks, cuts the top clips
   vertical (9:16, 1080×1920) with styled captions, and packages real MP4s +
   SRTs + `liveclip_clips.json`. If the link ever loses the settings, the
   notebook falls back to an uploaded `liveclip_config.json` (Download Config
   Again on the page), pasted JSON, or the form fields in its first cell.
3. **Back on the site:** click **Load Colab Results** and pick
   `liveclip_clips.json`. The gallery shows your real clips — real scores,
   transcripts, times, titles and hashtags. Download Captions gives you real
   `.srt` files built from the transcription word timings; the rendered MP4s
   are in the Colab export pack (`LiveClip_Export_Pack.zip`).

The page itself never pretends to transcribe or render video — a static site
can't. The preview player on each card is an animated stand-in, clearly
labelled as a preview.

## Files

- `index.html` — the Studio web app (GitHub Pages).
- `liveclip_colab.ipynb` — the real clipping pipeline (Google Colab).
- `build_notebook.py` — builds `liveclip_colab.ipynb` from readable Python
  source (`python3 build_notebook.py`). Edit the notebook here, not by hand.

## What the notebook does

- **Ingest:** downloads the source with yt-dlp (whole video, or one window up
  to 20 min, like Ssemble). Windowed downloads use direct stream URLs +
  ffmpeg stream-copy — `yt-dlp --download-sections` can silently truncate
  audio, so it is not used.
- **Transcribe:** faster-whisper (default `base`, word timestamps, VAD).
  Audio is decoded to a numpy array with ffmpeg first, because the file-path
  route breaks on some PyAV versions.
- **Score:** multi-signal hook scorer, 0–100 (speech density, hook words in
  the opener, questions, exclamations, numbers/stats, emotion words,
  sentence-boundary starts, speaking pace, silence-gap penalties). The
  Viral Hook Detection toggle switches the hook bonuses off for plain
  density ranking; Auto Silence Removal starts each clip at the first
  spoken word.
- **Render:** ffmpeg center-crop to 9:16, scale 1080×1920, `.ass` captions
  burned in with the chosen style, plus a real `.srt` per clip.
- **Package:** `liveclip_clips.json` (the results file the site loads) and
  `LiveClip_Export_Pack.zip` (MP4s + SRTs + results + config).

Use it for your own videos or content you have the right to clip.

## Verified

Tested end to end on a real 5-minute speech video (Denzel Washington,
“Fall Forward”): 3 clips scored 83/79/79, rendered as 1080×1920 30s MP4s
with burned-in captions, plus matching SRTs and `liveclip_clips.json`.
Page flow covered by a jsdom harness (30 checks: empty gallery on load,
auto-handoff link with the settings in the URL fragment and no file download,
real-results loading, word-timed SRT, export ZIP). Notebook settings sources
covered by a config-cell test (link fragment, uploaded file, pasted JSON,
form fields). The link handoff uses a base64url JSON fragment
(`#liveclip=...`) read by the notebook with `google.colab.output.eval_js` —
no third-party service is involved, so there is nothing that can go down or
block it.
