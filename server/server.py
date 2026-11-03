#!/usr/bin/env python3
"""Servidor local (Flask) que expõe o yt-dlp à extensão de browser.

Fluxo: a extensão pede /info -> escolhe opções -> POST /download (cria um job)
-> consulta /status/<id> -> quando "done", o browser descarrega /file/<id>.
"""
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.request
import uuid
from urllib.parse import parse_qs, urlparse

import yt_dlp
from flask import Flask, abort, jsonify, request, send_file
from yt_dlp.version import __version__ as YTDLP_VERSION

HOST = "127.0.0.1"
PORT = int(os.environ.get("YTDLP_PORT", "9614"))
COOKIES_BROWSER = os.environ.get("YTDLP_COOKIES_BROWSER")  # ex.: chrome, firefox, edge
TMP = tempfile.gettempdir()
WORK_DIR = os.path.join(TMP, "ytdlp-extension")


def find_ffmpeg():
    """Devolve (disponível, pasta do ffmpeg ou None).

    Ordem: FFMPEG_LOCATION -> ffmpeg no PATH -> binário incluído no pacote imageio-ffmpeg.
    """
    custom = os.environ.get("FFMPEG_LOCATION")
    if custom:
        return True, custom
    if shutil.which("ffmpeg"):
        return True, None
    try:
        import imageio_ffmpeg

        bin_dir = os.path.join(TMP, "ytdlp-extension-bin")
        os.makedirs(bin_dir, exist_ok=True)
        target = os.path.join(bin_dir, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if not os.path.exists(target):
            shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), target)
            os.chmod(target, 0o755)
        return True, bin_dir
    except Exception:  # noqa: BLE001
        return False, None


HAS_FFMPEG, FFMPEG_DIR = find_ffmpeg()
HAS_DENO = shutil.which("deno") is not None  # runtime JS recomendado pelo yt-dlp para o YouTube

# Contentor de vídeo -> preferência de codecs (a resolução tem sempre prioridade)
VIDEO_SORT = {
    "mp4": ["res", "vcodec:h264", "acodec:m4a"],  # máxima compatibilidade
    "mkv": ["res"],                               # melhor qualidade, qualquer codec
    "webm": ["res", "vcodec:vp9", "acodec:opus"],
}
AUDIO_BITRATES = ["320", "256", "192", "128", "96", "64"]
# (valor, rótulo, com perdas -> permite escolher o bitrate)
AUDIO_FORMATS = [
    ("best", "Original (no conversion)", False),
    ("mp3", "MP3", True),
    ("m4a", "M4A (AAC)", True),
    ("opus", "Opus", True),
    ("flac", "FLAC (lossless)", False),
    ("wav", "WAV (lossless)", False),
]
LOSSY = {v for v, _, lossy in AUDIO_FORMATS if lossy}
SUB_FORMATS = ["srt", "vtt", "ass", "ttml", "json3"] if HAS_FFMPEG else ["vtt", "ttml", "json3"]
NATIVE_SUB_FORMATS = ("vtt", "ttml", "json3")  # não precisam de conversão com ffmpeg

JOBS = {}
os.makedirs(WORK_DIR, exist_ok=True)
app = Flask(__name__)


# ----------------------------------------------------------------- segurança
@app.before_request
def guard():
    """Só aceita pedidos para localhost vindos da extensão (anti DNS-rebinding/CSRF)."""
    if (request.host or "").split(":")[0] not in ("127.0.0.1", "localhost"):
        abort(403)
    origin = request.headers.get("Origin")
    if origin and not origin.startswith(("chrome-extension://", "moz-extension://")):
        abort(403)


# ------------------------------------------------------------------- helpers
def short(e):
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).strip()
    return msg.replace("ERROR: ", "")[:300]


def explain(msg, kind, o):
    """Traduz erros crípticos do yt-dlp em mensagens acionáveis."""
    if kind == "subtitles" and "429" in msg:
        if o.get("track") == "translated":
            return ("YouTube blocks auto-translated subtitles (HTTP 429). "
                    "Pick a manual or original-language auto-generated track instead.")
        return ("YouTube rate-limited the subtitle request (HTTP 429). "
                "Wait a few minutes and retry; see the README (cookies) if it persists.")
    if "Requested format is not available" in msg:
        if kind == "video" and not HAS_FFMPEG:
            return ("ffmpeg is needed to merge this video's streams. Install ffmpeg "
                    "(or run: pip install imageio-ffmpeg) and restart the server.")
        return ("YouTube returned no matching formats. Check /health (Deno should be installed), "
                "then restart the server so yt-dlp updates.")
    return msg


def clean_url(raw):
    p = urlparse(raw or "")
    host = p.hostname or ""
    if p.scheme not in ("http", "https") or not any(
        host == d or host.endswith("." + d) for d in ("youtube.com", "youtu.be")
    ):
        raise ValueError("Only YouTube URLs are supported.")
    q = parse_qs(p.query)
    if host.endswith("youtu.be"):
        vid = p.path.strip("/")
    elif "v" in q:
        vid = q["v"][0]
    elif p.path.startswith("/shorts/"):
        vid = p.path.split("/")[2]
    else:
        raise ValueError("No video found in this URL.")
    return f"https://www.youtube.com/watch?v={vid}"


def base_opts(**extra):
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    if COOKIES_BROWSER:
        opts["cookiesfrombrowser"] = (COOKIES_BROWSER,)
    if FFMPEG_DIR:
        opts["ffmpeg_location"] = FFMPEG_DIR
    opts.update(extra)
    return opts


def extract(url):
    with yt_dlp.YoutubeDL(base_opts(skip_download=True)) as ydl:
        return ydl.extract_info(url, download=False)


# -------------------------------------------------------------------- rotas
@app.get("/health")
def health():
    return jsonify(ok=True, yt_dlp=YTDLP_VERSION, ffmpeg=HAS_FFMPEG, deno=HAS_DENO)


@app.get("/info")
def info():
    try:
        url = clean_url(request.args.get("url"))
        d = extract(url)
    except Exception as e:  # noqa: BLE001
        return jsonify(error=short(e)), 400

    # Resoluções disponíveis. Sem ffmpeg só é possível usar formatos com vídeo+áudio.
    fps_by_height = {}
    for f in d.get("formats") or []:
        h = f.get("height")
        if not h or f.get("vcodec") in (None, "none"):
            continue
        if not HAS_FFMPEG and f.get("acodec") in (None, "none"):
            continue
        fps_by_height[h] = max(fps_by_height.get(h, 0), f.get("fps") or 0)
    videos = [{"value": "best", "label": "Best available"}] + [
        {"value": str(h), "label": f"{h}p" + (str(int(fps)) if fps > 30 else "")}
        for h, fps in sorted(fps_by_height.items(), reverse=True)
    ]

    audio_formats = [{"value": v, "label": l, "lossy": lossy} for v, l, lossy in AUDIO_FORMATS]
    video_formats = [{"value": k, "label": k.upper()} for k in VIDEO_SORT]
    if not HAS_FFMPEG:  # sem conversões nem junção de streams
        audio_formats = audio_formats[:1]
        video_formats = [{"value": "mp4", "label": "MP4"}]

    def tracks(source, auto):
        items = []
        for code, v in (source or {}).items():
            if code == "live_chat":
                continue
            first = v[0] if v else {}
            translated = auto and "tlang" in parse_qs(urlparse(first.get("url") or "").query)
            items.append({
                "code": code,
                "name": first.get("name") or code,
                "track": "translated" if translated else ("auto" if auto else "manual"),
            })
        return sorted(items, key=lambda s: s["name"].lower())

    notices = []
    if not HAS_FFMPEG:
        notices.append("ffmpeg not found: only single-file formats are available. "
                       "Install ffmpeg or run: pip install imageio-ffmpeg")
    if not HAS_DENO:
        notices.append("Deno not found: YouTube may return fewer formats. Install Deno and restart the server.")

    return jsonify(
        url=url,
        id=d.get("id"),
        title=d.get("title"),
        thumbnail=d.get("thumbnail"),
        videos=videos,
        video_formats=video_formats,
        audio_formats=audio_formats,
        audio_qualities=[{"value": b, "label": f"{b} kbps"} for b in AUDIO_BITRATES],
        subtitles=tracks(d.get("subtitles"), False) + tracks(d.get("automatic_captions"), True),
        sub_formats=SUB_FORMATS,
        notice=" ".join(notices) or None,
    )


@app.post("/download")
def download():
    body = request.get_json(silent=True) or {}
    try:
        url = clean_url(body.get("url"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    kind = body.get("type")
    if kind not in ("video", "audio", "thumbnail", "subtitles"):
        return jsonify(error="Invalid download type."), 400
    jid = uuid.uuid4().hex
    JOBS[jid] = {
        "status": "running", "percent": 0, "message": "Starting…",
        "dir": tempfile.mkdtemp(prefix="job_", dir=WORK_DIR), "created": time.time(),
    }
    threading.Thread(target=run_job, args=(jid, url, kind, body), daemon=True).start()
    return jsonify(id=jid)


@app.get("/status/<jid>")
def status(jid):
    j = JOBS.get(jid)
    if not j:
        return jsonify(error="Job not found."), 404
    return jsonify(status=j["status"], percent=j["percent"], message=j["message"], file=j.get("file"))


@app.get("/file/<jid>")
def file(jid):
    j = JOBS.get(jid)
    if not j or j["status"] != "done":
        abort(404)
    return send_file(os.path.join(j["dir"], j["file"]), as_attachment=True, download_name=j["file"])


# --------------------------------------------------------------------- jobs
def fetch_thumbnail(url, folder):
    d = extract(url)
    img = (".jpg", ".jpeg", ".png")
    best = d.get("thumbnail") or ""
    cands = [t for t in d.get("thumbnails") or [] if t.get("url", "").split("?")[0].lower().endswith(img)]
    cands.sort(key=lambda t: (t.get("width") or 0) * (t.get("height") or 0), reverse=True)
    urls = ([best] if best.split("?")[0].lower().endswith(img) else []) + [t["url"] for t in cands]
    urls.append(f"https://i.ytimg.com/vi/{d['id']}/hqdefault.jpg")
    title = yt_dlp.utils.sanitize_filename(d.get("title") or d["id"])[:120]
    for u in dict.fromkeys(urls):  # sem duplicados, mantém a ordem
        ext = u.split("?")[0].rsplit(".", 1)[-1].lower()
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r, \
                    open(os.path.join(folder, f"{title} [{d['id']}].{ext}"), "wb") as out:
                shutil.copyfileobj(r, out)
            return
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("Could not download the thumbnail.")


def run_job(jid, url, kind, o):
    job = JOBS[jid]
    folder = job["dir"]
    seen = []

    def hook(d):
        if d["status"] == "downloading":
            if d.get("filename") not in seen:
                seen.append(d.get("filename"))
            n = len((d.get("info_dict") or {}).get("requested_formats") or [1])
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            frac = d.get("downloaded_bytes", 0) / total if total else 0
            job["percent"] = round(min((len(seen) - 1 + frac) / n, 1) * 100, 1)
            job["message"] = f"Downloading… {(d.get('_speed_str') or '').strip()}".strip()

    def pp_hook(d):
        if d["status"] == "started":
            job["message"] = "Processing…"

    try:
        if kind == "thumbnail":
            fetch_thumbnail(url, folder)
        else:
            opts = base_opts(
                outtmpl=os.path.join(folder, "%(title).120s [%(id)s].%(ext)s"),
                progress_hooks=[hook], postprocessor_hooks=[pp_hook],
            )
            q = str(o.get("quality") or "best")
            fmt = o.get("format")
            if kind == "video":
                fmt = fmt or "mp4"
                if fmt not in VIDEO_SORT:
                    raise ValueError("Invalid video format.")
                cap = f"[height<={int(q)}]" if q.isdigit() else ""
                opts.update(
                    format=f"bv*{cap}+ba/b{cap}/b" if HAS_FFMPEG else f"b{cap}/b",
                    format_sort=VIDEO_SORT[fmt],
                    merge_output_format=fmt,
                )
            elif kind == "audio":
                fmt = fmt or "best"
                if fmt not in {v for v, _, _ in AUDIO_FORMATS}:
                    raise ValueError("Invalid audio format.")
                opts["format"] = "ba/b"
                if fmt != "best":
                    if not HAS_FFMPEG:
                        raise ValueError("ffmpeg is required to convert audio.")
                    pp = {"key": "FFmpegExtractAudio", "preferredcodec": fmt}
                    if fmt in LOSSY:
                        if q not in AUDIO_BITRATES:
                            raise ValueError("Invalid audio quality.")
                        pp["preferredquality"] = q
                    opts["postprocessors"] = [pp]
            else:  # subtitles
                lang, fmt = o.get("lang"), fmt or "srt"
                if not lang or fmt not in SUB_FORMATS:
                    raise ValueError("Invalid subtitle language or format.")
                auto = o.get("track") in ("auto", "translated")
                native = fmt in NATIVE_SUB_FORMATS
                opts.update(
                    skip_download=True, writesubtitles=not auto, writeautomaticsub=auto,
                    subtitleslangs=[lang], subtitlesformat=fmt if native else "vtt/best",
                )
                if not native:
                    opts["postprocessors"] = [
                        {"key": "FFmpegSubtitlesConvertor", "format": fmt, "when": "before_dl"}
                    ]
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

        files = [
            f for f in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, f)) and not f.endswith((".part", ".ytdl"))
        ]
        if not files:
            raise RuntimeError(
                "No subtitle file was produced (the track may be unavailable or blocked by YouTube)."
                if kind == "subtitles" else "Nothing was downloaded.")
        job["file"] = max(files, key=lambda f: os.path.getsize(os.path.join(folder, f)))
        job.update(status="done", percent=100, message="Done")
    except Exception as e:  # noqa: BLE001
        job.update(status="error", message=explain(short(e), kind, o))
    job["finished"] = time.time()


def janitor():
    """Apaga ficheiros temporários 15 min depois de terminados."""
    while True:
        time.sleep(60)
        now = time.time()
        for jid, j in list(JOBS.items()):
            done = j.get("finished")
            if (done and now - done > 900) or now - j["created"] > 6 * 3600:
                shutil.rmtree(j["dir"], ignore_errors=True)
                JOBS.pop(jid, None)


if __name__ == "__main__":
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    os.makedirs(WORK_DIR, exist_ok=True)
    threading.Thread(target=janitor, daemon=True).start()
    print(f"yt-dlp {YTDLP_VERSION}")
    print(f"ffmpeg: {'OK' if HAS_FFMPEG else 'NOT FOUND - run: pip install imageio-ffmpeg'}")
    print(f"Deno:   {'OK' if HAS_DENO else 'NOT FOUND - install it from https://deno.com (fewer formats without it)'}")
    print(f"Server running at http://{HOST}:{PORT}  (Ctrl+C to stop)")
    app.run(HOST, PORT, threaded=True)
