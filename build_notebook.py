#!/usr/bin/env python3
"""Build liveclip_colab.ipynb — the real LiveClip v2 pipeline.

Run: python3 build_notebook.py
Writes liveclip_colab.ipynb in the same directory.
"""
import json

CELL_MD_INTRO = """# LiveClip Studio AI — Real Clipping Pipeline (v2)

Backend for the [LiveClip Studio AI](https://github.com/Sgsuprio/LiveClip-Studio-AI) web app.
This notebook does the REAL work: it downloads your video, transcribes it with
faster-whisper, scores every window for viral hooks, cuts the top clips vertical
(9:16) with styled captions, and packages real MP4s + SRTs + `liveclip_clips.json`.

**How to use it (from the Studio page):**
1. On the Studio page, paste a YouTube URL, pick clip length / count / caption style, click **Generate Viral Clips**, then click **Open Colab Notebook** — your settings travel with the link, nothing to download or upload.
2. In Colab pick a T4 GPU runtime (Runtime → Change runtime type → T4 GPU), then Run all. If the link ever loses the settings, upload `liveclip_config.json` (Download Config Again on the page) or paste the JSON into the `config_json` field below.
3. Download `liveclip_clips.json` + `LiveClip_Export_Pack.zip` from the last cell, then load `liveclip_clips.json` back into the Studio page with **Load Colab Results** — the gallery shows your REAL clips, scores and transcripts.

Use it for your own videos or content you have the right to clip.
"""

CELL_INSTALL = """# Install the pipeline dependencies (yt-dlp, faster-whisper, ffmpeg)
!pip install -q yt-dlp faster-whisper
!apt-get install -y -qq ffmpeg > /dev/null
print("deps installed")
"""

CELL_CONFIG = """#@title LiveClip job settings
#@markdown Open this notebook from the Studio page's **Open Colab Notebook** button and your settings arrive with the link — just Run all. If the link lost them, upload `liveclip_config.json`, paste the JSON below, or fill in these fields.
import json, os, base64

source_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  #@param {type:"string"}
segment_start = 0  #@param {type:"number"}
segment_duration = 1200  #@param {type:"number"}
clip_length = "15-30s"  #@param ["15-30s", "30-60s", "60-90s"]
max_clips = 3  #@param {type:"slider", min:1, max:10, step:1}
caption_style = "hormozi"  #@param ["hormozi", "minimal", "neon"]
whisper_model = "base"  #@param ["tiny", "base", "small", "medium", "large-v3"]
language = "en"  #@param {type:"string"}
viral_hook_detection = True  #@param {type:"boolean"}
auto_silence_removal = False  #@param {type:"boolean"}
config_json = ""  #@param {type:"string"}

CONFIG = {
    "source_url": source_url,
    "segment_start": int(segment_start),
    "segment_duration": int(segment_duration),
    "clip_length": clip_length,
    "max_clips": int(max_clips),
    "caption_style": caption_style,
    "aspect_ratio": "9:16",
    "whisper_model": whisper_model,
    "language": language,
    "dynamic_captions": True,
    "viral_hook_detection": viral_hook_detection,
    "auto_silence_removal": auto_silence_removal,
}

# Settings arrive from the Studio page in this order — first one that works wins.
# The flat v2 format is accepted, and the older nested format for backwards compat.
def _apply_exported(exported, source_name):
    flat = dict(exported)
    if "clip_settings" in exported:
        flat.update(exported["clip_settings"])
    if "ai_pipeline" in exported:
        flat.update(exported["ai_pipeline"])
    for key in CONFIG:
        if key in flat and flat[key] not in (None, ""):
            CONFIG[key] = flat[key]
    print(f"settings loaded from {source_name}")

_loaded_from = None

# 1. Settings embedded in the page's Colab link (#liveclip=<base64url JSON>).
#    The Studio page builds this link on Generate, so nothing needs uploading.
try:
    from google.colab import output as _colab_output
    _hash = _colab_output.eval_js("window.location.hash || ''") or ""
    if _hash.startswith("#liveclip="):
        _raw = _hash[len("#liveclip="):]
        _padded = _raw + "=" * (-len(_raw) % 4)
        _apply_exported(json.loads(base64.urlsafe_b64decode(_padded).decode("utf-8")), "the Studio page link")
        _loaded_from = "link"
except Exception as e:
    print("link settings not found, trying the other options:", e)

# 2. Uploaded liveclip_config.json (the Download Config Again fallback).
if _loaded_from is None and os.path.exists("liveclip_config.json"):
    with open("liveclip_config.json") as f:
        _apply_exported(json.load(f), "liveclip_config.json")
    _loaded_from = "file"

# 3. JSON pasted into the config_json field above.
if _loaded_from is None and config_json.strip():
    _apply_exported(json.loads(config_json), "the pasted JSON")
    _loaded_from = "paste"

if _loaded_from is None:
    print("using the form fields above")

os.makedirs("/content/liveclip", exist_ok=True)
with open("/content/liveclip/config.json", "w") as f:
    json.dump(CONFIG, f, indent=2)
print(json.dumps(CONFIG, indent=2))
"""

CELL_INGEST = """# Stage 1 — Ingest the source (whole video, or one window up to 20 min like Ssemble)
import subprocess, json

SRC = CONFIG["source_url"]
SEG_START = CONFIG["segment_start"]
SEG_DUR = CONFIG["segment_duration"]
RAW = "/content/liveclip/raw.mp4"

# Real source duration first (ffprobe on the downloaded file is the ground truth,
# but yt-dlp tells us the length before we download so we can skip segmenting).
meta = subprocess.run(
    ["yt-dlp", "--force-ipv4", "--no-playlist",
     "--extractor-args", "youtube:player_client=android",
     "--print", "%(duration)s",
     "--print", "%(title)s", "--skip-download", SRC],
    capture_output=True, text=True)
lines = meta.stdout.strip().splitlines()
FULL_DUR = float(lines[0]) if lines and lines[0] not in ("NA", "") else None
SRC_TITLE = lines[1] if len(lines) > 1 else ""
print(f"source: {SRC_TITLE or SRC}")
print(f"full duration: {FULL_DUR}s" if FULL_DUR else "full duration: unknown")

SEG_END = SEG_START + SEG_DUR
needs_window = FULL_DUR is not None and (SEG_START > 0 or SEG_END < FULL_DUR)

if not needs_window:
    subprocess.run(
        ["yt-dlp", "--force-ipv4", "--no-playlist",
         "--extractor-args", "youtube:player_client=android",
         "-f", "bv*[height<=1080]+ba/b[height<=1080]",
         "--merge-output-format", "mp4", "-o", RAW, SRC],
        check=True)
else:
    # Reliable windowed download: direct stream URLs, then ffmpeg stream-copy
    # the exact window (yt-dlp --download-sections can silently truncate audio).
    urls = subprocess.run(
        ["yt-dlp", "--force-ipv4", "--no-playlist", "-g",
         "--extractor-args", "youtube:player_client=android",
         "-f", "bv*[height<=1080]+ba/b[height<=1080]", SRC],
        capture_output=True, text=True, check=True).stdout.strip().splitlines()
    v_url, a_url = urls[0], urls[1] if len(urls) > 1 else None
    cmd = ["ffmpeg", "-y",
           "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
           "-ss", str(SEG_START), "-to", str(SEG_END), "-i", v_url]
    if a_url:
        cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
                "-ss", str(SEG_START), "-to", str(SEG_END), "-i", a_url,
                "-map", "0:v", "-map", "1:a"]
    cmd += ["-c", "copy", RAW]
    subprocess.run(cmd, check=True, capture_output=True)

dur = float(subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", RAW],
    capture_output=True, text=True, check=True).stdout.strip())
print(f"ingested {RAW}: {dur:.1f}s (segment {SEG_START}s - {SEG_START + dur:.1f}s)")
with open("/content/liveclip/source.json", "w") as f:
    json.dump({"title": SRC_TITLE, "duration": dur,
               "segment_start": SEG_START, "source_url": SRC}, f, indent=2)
"""

CELL_TRANSCRIBE = """# Stage 2 — Transcribe with faster-whisper (word-level timestamps)
# Audio is decoded to a numpy array with ffmpeg first: passing a file path makes
# faster-whisper decode through PyAV, which breaks on some PyAV versions.
from faster_whisper import WhisperModel
import json, subprocess
import numpy as np

device = "cuda"
try:
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
except ImportError:
    device = "cpu"
compute = "float16" if device == "cuda" else "int8"
print(f"transcribing on {device} ({compute}), model={CONFIG['whisper_model']}")

pcm = subprocess.run(
    ["ffmpeg", "-v", "error", "-i", "/content/liveclip/raw.mp4",
     "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
    capture_output=True, check=True).stdout
audio = np.frombuffer(pcm, dtype=np.float32)
print(f"decoded audio: {len(audio) / 16000:.1f}s")

model = WhisperModel(CONFIG["whisper_model"], device=device, compute_type=compute)
segments, info = model.transcribe(
    audio, language=CONFIG["language"] or None,
    beam_size=5, word_timestamps=True, vad_filter=True)
words = []
for seg in segments:
    for w in (seg.words or []):
        words.append({"start": round(w.start, 2), "end": round(w.end, 2),
                      "word": w.word.strip()})
words = [w for w in words if w["word"]]
print(f"detected language: {info.language} | words: {len(words)} | "
      f"span: {words[0]['start']:.1f}s - {words[-1]['end']:.1f}s")
with open("/content/liveclip/words.json", "w") as f:
    json.dump(words, f)
"""

CELL_SCORE = """# Stage 3 — Score hook windows and pick the top clips.
# Multi-signal heuristic (weights documented, score is 0-100):
#   speech density up to 36 | hook words in the opener up to 24 |
#   question +10 | exclamation +6 | number/stat +8 | emotion word +8 |
#   sentence-boundary start +6 | good pace (120-180 wpm) +8 |
#   minus 5 per long silence gap inside the window (max -10).
import json, re

DUR = {"15-30s": (15, 30), "30-60s": (30, 60), "60-90s": (60, 90)}[CONFIG["clip_length"]]
MIN_LEN, WINDOW = DUR
STOPWORDS = set('''a an the and or but if then else when at by for with about into through after over
between out against during without before under around among of to in on is are was were be been
being have has had do does did will would shall should can could may might must i you he she it we
they this that these those am an the as at be by in of on to'''.split())

HOOK_OPENERS = ["why", "how", "what", "secret", "mistake", "stop", "never", "nobody",
                "truth", "hack", "free", "warning", "exposed", "shocking", "nobody tells"]
EMOTION = ["amazing", "insane", "crazy", "unbelievable", "incredible", "love", "hate",
           "fail", "failed", "win", "broke", "massive", "huge", "destroyed", "genius"]

def score_window(ws):
    text = " ".join(w["word"] for w in ws)
    low = text.lower()
    opener = " ".join(w["word"] for w in ws[:12]).lower()
    score, reasons = 0.0, []
    density = min(len(ws), 90) * 0.4
    score += density
    # Hook bonuses only apply when viral hook detection is on; off means
    # plain speech-density ranking.
    if CONFIG.get("viral_hook_detection", True):
        hits = [h for h in HOOK_OPENERS if re.search(rf"\b{h}\b", opener)]
        if hits:
            score += min(12 * len(hits), 24); reasons.append(f"hook opener ({', '.join(hits[:2])})")
        if "?" in text:
            score += 10; reasons.append("opens with a question")
        if "!" in text:
            score += 6; reasons.append("exclamation energy")
        if re.search(r"\d+\s?%|\$\d+|\b\d{2,}\b", text):
            score += 8; reasons.append("concrete number/stat")
        emo = [e for e in EMOTION if re.search(rf"\b{e}\b", low)]
        if emo:
            score += 8; reasons.append(f"emotion word ({emo[0]})")
    if ws and (ws[0]["word"][:1].isupper() or ws[0] is words[0]):
        score += 6; reasons.append("clean sentence start")
    span = max(ws[-1]["end"] - ws[0]["start"], 1)
    wpm = len(ws) / span * 60
    if 120 <= wpm <= 180:
        score += 8; reasons.append("strong speaking pace")
    elif wpm < 90 or wpm > 220:
        score -= 6
    gaps = sum(1 for a, b in zip(ws, ws[1:]) if b["start"] - a["end"] > 1.5)
    if gaps:
        score -= min(5 * gaps, 10)
    return min(100, max(0, round(score))), reasons

def window_title(text):
    m = re.split(r"[.!?]\s+", text.strip())
    s = (m[0] if m else text).strip().strip(" \"'")
    if len(s) < 12:
        s = text.strip()
    if len(s) > 70:
        s = s[:70].rsplit(" ", 1)[0] + "..."  # cut at a word boundary, never mid-word
    return s

def window_tags(text):
    toks = re.findall(r"[a-z][a-z\-]{2,}", text.lower())
    freq = {}
    for t in toks:
        if t not in STOPWORDS:
            freq[t] = freq.get(t, 0) + 1
    top = sorted(freq, key=freq.get, reverse=True)[:5]
    return ["#" + t.replace("-", "") for t in top]

SEG_START = CONFIG["segment_start"]
SEG_END = SEG_START + float(json.load(open("/content/liveclip/source.json"))["duration"])
candidates = []
t = SEG_START
while t + MIN_LEN <= SEG_END:
    ws = [w for w in words if t <= w["start"] < t + WINDOW]
    if len(ws) >= 20:
        last_end = ws[-1]["end"]
        end = min(t + WINDOW, last_end + 0.4)
        if end - t >= MIN_LEN:
            s, reasons = score_window(ws)
            candidates.append({"score": s, "start": round(t, 2), "end": round(end, 2),
                               "text": " ".join(w["word"] for w in ws), "reasons": reasons,
                               "first_word": ws[0]["start"]})
    t += 2.0

candidates.sort(key=lambda c: c["score"], reverse=True)
picked, used = [], []
for c in candidates:
    if all(abs(c["start"] - u) > WINDOW for u in used):
        if CONFIG.get("auto_silence_removal"):
            c["start"] = round(c["first_word"], 2)  # trim leading dead air
        if c["end"] - c["start"] >= MIN_LEN:
            picked.append(c); used.append(c["start"])
    if len(picked) >= CONFIG["max_clips"]:
        break
picked.sort(key=lambda c: c["start"])

for i, c in enumerate(picked, 1):
    c["title"] = window_title(c["text"])
    c["hashtags"] = window_tags(c["text"])
    c["hookReason"] = "; ".join(c["reasons"][:2]) or "Steady speech, clean moment"
    print(f"clip {i}: score {c['score']:3d}  {c['start']:7.1f}s - {c['end']:7.1f}s  {c['title']}")
    print(f"         {c['hookReason']}  {' '.join(c['hashtags'])}")

with open("/content/liveclip/picks.json", "w") as f:
    json.dump(picked, f, indent=2)
print(f"picked {len(picked)} clip(s)")
"""

CELL_RENDER = """# Stage 4 — Render vertical clips with ffmpeg (9:16, styled captions) + .srt files
import subprocess, json, os

STYLE = CONFIG["caption_style"]
CROP = "crop=ih*9/16:ih"  # center-crop to 9:16, then scale to 1080x1920

def ass_header():
    if STYLE == "minimal":
        style = ("Style: Default,DejaVu Sans,20,&H00FFFFFF,&H000000FF,&H80000000,&H00000000,"
                 "-1,0,0,0,100,100,0,0,1,1,0,2,10,10,90,1")
    elif STYLE == "neon":
        style = ("Style: Default,DejaVu Sans,32,&H00FFFFFF,&H000000FF,&H00FF66CC,&H00000000,"
                 "-1,0,0,0,100,100,0,0,1,2,0,2,10,10,140,1")
    else:  # hormozi
        style = ("Style: Default,DejaVu Sans,32,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
                 "-1,0,0,0,100,100,0,0,1,2,0,2,10,10,140,1")
    return ("[Script Info]\\nScriptType: v4.00+\\nPlayResX: 1080\\nPlayResY: 1920\\n"
            "[V4+ Styles]\\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
            "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\\n"
            f"{style}\\n[Events]\\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
            "Effect, Text\\n")

def ass_ts(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def srt_ts(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60); ms = int((t % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def chunks(ws, n=4):
    for j in range(0, len(ws), n):
        yield ws[j:j + n]

for i, c in enumerate(picked, 1):
    s, e = c["start"], c["end"]
    clip_words = [w for w in words if s <= w["start"] < e]
    # .srt from real word timings (4-word chunks)
    srt_path = f"/content/liveclip/clip{i}.srt"
    with open(srt_path, "w") as f:
        for k, ch in enumerate(chunks(clip_words), 1):
            f.write(f"{k}\\n{srt_ts(ch[0]['start'] - s)} --> {srt_ts(ch[-1]['end'] - s)}\\n"
                    f"{' '.join(w['word'] for w in ch).strip()}\\n\\n")
    # .ass with the chosen caption style (same 4-word chunks)
    ass_path = f"/content/liveclip/clip{i}.ass"
    with open(ass_path, "w") as f:
        f.write(ass_header())
        for ch in chunks(clip_words):
            txt = " ".join(w["word"] for w in ch).strip()
            if STYLE != "minimal":
                txt = txt.upper()
            f.write(f"Dialogue: 0,{ass_ts(ch[0]['start'] - s)},{ass_ts(ch[-1]['end'] - s)},"
                    f"Default,,0,0,0,,{txt}\\n")
    out = f"/content/liveclip/clip{i}.mp4"
    vf = f"{CROP},scale=1080:1920,subtitles='{ass_path}'"
    cmd = ["ffmpeg", "-y", "-ss", str(s), "-to", str(e), "-i", "/content/liveclip/raw.mp4",
           "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "20",
           "-c:a", "aac", "-b:a", "128k", out]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"clip{i}.mp4  ({e - s:.0f}s, score {c['score']}, {STYLE} captions)")

import glob
for p in sorted(glob.glob("/content/liveclip/clip*.mp4")):
    print(p, round(os.path.getsize(p) / 1024 / 1024, 2), "MB")
"""

CELL_PACKAGE = """# Stage 5 — Package results for the Studio page + export ZIP
import json, zipfile, os, datetime

def fmt_hms(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

src = json.load(open("/content/liveclip/source.json"))
out_clips = []
for i, c in enumerate(picked, 1):
    s, e = c["start"], c["end"]
    clip_words = [w for w in words if s <= w["start"] < e]
    out_clips.append({
        "id": f"clip-{i}",
        "title": c["title"],
        "score": c["score"],
        "start": s, "end": e,
        "startTime": fmt_hms(s), "endTime": fmt_hms(e),
        "duration": f"{round(e - s)}s",
        "hookReason": c["hookReason"],
        "transcript": c["text"],
        "hashtags": c["hashtags"],
        "mp4": f"clip{i}.mp4",
        "srt": f"clip{i}.srt",
        "caption_style": CONFIG["caption_style"],
        "words": [{"start": round(w["start"] - s, 2), "end": round(w["end"] - s, 2),
                   "word": w["word"]} for w in clip_words],
    })

results = {
    "version": 1,
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    "source_url": CONFIG["source_url"],
    "source_title": src.get("title", ""),
    "source_duration": src.get("duration"),
    "settings": {
        "clip_length": CONFIG["clip_length"],
        "max_clips": CONFIG["max_clips"],
        "caption_style": CONFIG["caption_style"],
        "aspect_ratio": CONFIG["aspect_ratio"],
    },
    "clips": out_clips,
}
with open("/content/liveclip/liveclip_clips.json", "w") as f:
    json.dump(results, f, indent=2)

zip_path = "/content/liveclip/LiveClip_Export_Pack.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    z.write("/content/liveclip/liveclip_clips.json", "liveclip_clips.json")
    z.write("/content/liveclip/config.json", "liveclip_config.json")
    for i in range(1, len(out_clips) + 1):
        z.write(f"/content/liveclip/clip{i}.mp4", f"clip{i}.mp4")
        z.write(f"/content/liveclip/clip{i}.srt", f"clip{i}.srt")

print(f"clips: {len(out_clips)} | results: liveclip_clips.json "
      f"({os.path.getsize('/content/liveclip/liveclip_clips.json') / 1024:.1f} KB) | "
      f"pack: LiveClip_Export_Pack.zip ({os.path.getsize(zip_path) / 1024 / 1024:.1f} MB)")
print("Next: download liveclip_clips.json + LiveClip_Export_Pack.zip, then on the Studio")
print("page click 'Load Colab Results' and pick liveclip_clips.json — your real clips,")
print("scores and transcripts will appear in the gallery.")
try:
    from google.colab import files
    files.download("/content/liveclip/liveclip_clips.json")
    files.download(zip_path)
except ImportError:
    print("(not in Colab — files are in /content/liveclip/)")
"""

CELLS = [
    {"cell_type": "markdown", "metadata": {}, "source": CELL_MD_INTRO.splitlines(True)},
    {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
     "source": CELL_INSTALL.splitlines(True)},
    {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
     "source": CELL_CONFIG.splitlines(True)},
    {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
     "source": CELL_INGEST.splitlines(True)},
    {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
     "source": CELL_TRANSCRIBE.splitlines(True)},
    {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
     "source": CELL_SCORE.splitlines(True)},
    {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
     "source": CELL_RENDER.splitlines(True)},
    {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
     "source": CELL_PACKAGE.splitlines(True)},
]

NB = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.10.0"},
        "accelerator": "GPU",
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

if __name__ == "__main__":
    with open("liveclip_colab.ipynb", "w") as f:
        json.dump(NB, f, indent=1)
    print("wrote liveclip_colab.ipynb")
    # validate
    nb = json.load(open("liveclip_colab.ipynb"))
    assert nb["nbformat"] == 4
    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] != "code":
            continue
        src = "".join(c["source"])
        # IPython shell escapes (!cmd) are valid in Colab but not in compile();
        # neutralise them for the syntax check only.
        check_src = "\n".join(
            "pass  # shell command" if line.lstrip().startswith(("!", "%")) else line
            for line in src.splitlines()
        )
        compile(check_src, f"<cell {i}>", "exec")
    print(f"validated: {len(nb['cells'])} cells, all compile")
