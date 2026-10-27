"""YDown browser application. Run one worker per instance."""
import asyncio
import base64
from contextlib import asynccontextmanager, suppress
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import threading
import time
from urllib.parse import parse_qs, quote, urlsplit
import urllib.request

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
import uvicorn
import yt_dlp

from settings import BASE_DIR, DOWNLOAD_DIR, INSTALLER_URL, RELEASES_URL, VERSION, executable

PASSWORD = os.environ.get("YDOWN_PASSWORD", "")
FILE_TTL_SECONDS = max(60, int(os.environ.get("YDOWN_FILE_TTL_SECONDS", "3600")))
MAX_CONCURRENT_JOBS = max(1, int(os.environ.get("YDOWN_MAX_CONCURRENT_JOBS", "2")))
MAX_DURATION = int(os.environ.get("YDOWN_MAX_DURATION_SECONDS", "3600"))
MAX_FILESIZE = int(os.environ.get("YDOWN_MAX_FILESIZE_MB", "250")) * 1024 * 1024
MAX_VIDEO_FILESIZE = int(os.environ.get("YDOWN_MAX_VIDEO_FILESIZE_MB", "2048")) * 1024 * 1024
MEDIA_FORMATS = {"mp3", "m4a", "opus", "mp4"}
VIDEO_QUALITIES = {"480", "720", "1080"}
ACTIVE_JOBS = set()
logger = logging.getLogger("ydown")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def cleanup_old_files():
    """Expire completed jobs, never a running conversion."""
    if not DOWNLOAD_DIR.exists():
        return
    for path in DOWNLOAD_DIR.iterdir():
        if path.name in ACTIVE_JOBS or path.is_symlink():
            continue
        try:
            if time.time() - path.stat().st_mtime > FILE_TTL_SECONDS:
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.is_file():
                    path.unlink()
        except OSError:
            logger.warning("Could not clean an expired download", exc_info=True)


@asynccontextmanager
async def lifespan(app):
    if os.environ.get("YDOWN_REQUIRE_PASSWORD") == "1" and not PASSWORD:
        raise RuntimeError("Set YDOWN_PASSWORD before exposing YDown to the internet.")
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    async def cleanup_loop():
        while True:
            await asyncio.to_thread(cleanup_old_files)
            await asyncio.sleep(60)
    task = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="YDown", version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)


def authorized(headers):
    if not PASSWORD:
        return True
    try:
        scheme, encoded = headers.get("authorization", "").split(" ", 1)
        username, password = base64.b64decode(encoded, validate=True).decode().split(":", 1)
        return (scheme.lower() == "basic" and username == "ydown"
                and secrets.compare_digest(password.encode(), PASSWORD.encode()))
    except (ValueError, UnicodeError):
        return False


@app.middleware("http")
async def access_control(request: Request, call_next):
    if request.url.path != "/health" and not authorized(request.headers):
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="YDown", charset="UTF-8"'})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={
        "version": VERSION, "installer_url": INSTALLER_URL, "releases_url": RELEASES_URL,
        "retention_minutes": FILE_TTL_SECONDS // 60,
    })


@app.get("/health")
async def health():
    ready = all(executable(name) for name in ("ffmpeg", "ffprobe", "node"))
    return JSONResponse({"status": "ok" if ready else "missing_dependencies", "version": VERSION,
                         "download_engine": yt_dlp.version.__version__},
                        status_code=200 if ready else 503)


_update_cache = {"expires": 0, "value": None}


def fetch_update():
    if time.monotonic() < _update_cache["expires"]:
        return _update_cache["value"]
    result = {"current_version": VERSION, "releases_url": RELEASES_URL,
              "installer_url": INSTALLER_URL, "available": False}
    try:
        request = urllib.request.Request(
            "https://api.github.com/repos/loginheaven-jpg/Ydown/releases/latest",
            headers={"User-Agent": "YDown/" + VERSION, "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            release = json.load(response)
        latest = release["tag_name"].removeprefix("v")
        if re.fullmatch(r"\d+\.\d+\.\d+", latest):
            result["latest_version"] = latest
            has_installer = any(a["name"] == "YDown-Setup-x64.exe" for a in release.get("assets", []))
            result["available"] = has_installer and tuple(map(int, latest.split("."))) > tuple(map(int, VERSION.split(".")))
    except Exception:
        result["message"] = "최신 버전을 확인할 수 없습니다. 릴리스 페이지를 확인하세요."
    _update_cache.update(expires=time.monotonic() + 300, value=result)
    return result


@app.get("/api/update")
async def update():
    return await asyncio.to_thread(fetch_update)


@app.get("/stream/{filename:path}")
@app.get("/downloads/{filename:path}")
async def stream_file(filename: str):
    parts = filename.split("/")
    if (len(parts) != 2 or not re.fullmatch(r"[a-f0-9]{32}", parts[0])
            or "\\" in parts[1] or Path(parts[1]).suffix not in {"." + fmt for fmt in MEDIA_FORMATS}):
        return JSONResponse({"error": "파일이 없거나 보관 시간이 지났습니다."}, status_code=404)
    filepath = (DOWNLOAD_DIR / filename).resolve()
    if not filepath.is_relative_to(DOWNLOAD_DIR.resolve()) or not filepath.is_file():
        return JSONResponse({"error": "파일이 없거나 보관 시간이 지났습니다."}, status_code=404)
    return FileResponse(filepath, media_type="application/octet-stream", filename=filepath.name)


def validate_request(data):
    if (not isinstance(data, dict) or not isinstance(data.get("format", "mp3"), str)
            or data.get("format", "mp3") not in MEDIA_FORMATS):
        raise ValueError("MP3, M4A, Opus, MP4 중 하나를 선택하세요.")
    if data.get("format") == "mp4" and (
            not isinstance(data.get("quality", "1080"), str)
            or data.get("quality", "1080") not in VIDEO_QUALITIES):
        raise ValueError("영상 최대 화질은 480p, 720p, 1080p 중 하나를 선택하세요.")
    urls = data.get("urls")
    if not isinstance(urls, list) or not 1 <= len(urls) <= 10 or not all(isinstance(u, str) for u in urls):
        raise ValueError("YouTube URL을 1~10개 입력하세요.")
    clean = []
    for url in urls:
        parsed = urlsplit(url.strip())
        if (parsed.scheme not in {"http", "https"} or parsed.username or parsed.password
                or parsed.port not in {None, 80, 443}):
            raise ValueError("올바른 YouTube 영상 주소를 입력하세요.")
        segments = parsed.path.strip("/").split("/")
        video_id = None
        if parsed.hostname == "youtu.be" and len(segments) == 1:
            video_id = segments[0]
        elif parsed.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [None])[0]
            elif len(segments) == 2 and segments[0] in {"shorts", "embed", "live"}:
                video_id = segments[1]
        if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValueError("YouTube 영상 링크만 지원합니다. 재생목록은 개별 영상으로 입력하세요.")
        clean.append("https://www.youtube.com/watch?v=" + video_id)
    return clean, data.get("format", "mp3")


def normalize_download_request(data):
    """Keep legacy single-format clients compatible; new clients select output kinds."""
    if not isinstance(data, dict) or "targets" not in data:
        urls, media_format = validate_request(data)
        return urls, [("video" if media_format == "mp4" else "audio", media_format)], data.get("quality", "1080")
    targets = data["targets"]
    if (not isinstance(targets, dict) or set(targets) - {"audio", "video"}
            or any(type(targets.get(kind, False)) is not bool for kind in ("audio", "video"))):
        raise ValueError("오디오·영상 선택값은 true 또는 false여야 합니다.")
    if not any(targets.get(kind, False) for kind in ("audio", "video")):
        raise ValueError("오디오 또는 영상을 선택하세요.")
    outputs = []
    if targets.get("audio"):
        audio_format = data.get("audio_format", "mp3")
        if not isinstance(audio_format, str) or audio_format not in MEDIA_FORMATS - {"mp4"}:
            raise ValueError("오디오 형식은 MP3, M4A, Opus 중 하나를 선택하세요.")
        outputs.append(("audio", audio_format))
    quality = data.get("video_quality", "1080") if targets.get("video") else "1080"
    if targets.get("video"):
        if not isinstance(quality, str) or quality not in VIDEO_QUALITIES:
            raise ValueError("영상 최대 화질은 480p, 720p, 1080p 중 하나를 선택하세요.")
        outputs.append(("video", "mp4"))
    urls, _ = validate_request({"urls": data.get("urls"), "format": outputs[0][1], "quality": quality})
    return urls, outputs, quality


def build_ydl_opts(media_format, progress_hook, output_dir, quality="1080"):
    video = media_format == "mp4"
    if video and quality not in VIDEO_QUALITIES:
        raise ValueError("지원하지 않는 영상 화질입니다.")
    max_size = MAX_VIDEO_FILESIZE if video else MAX_FILESIZE
    def limit(info, *, incomplete=False):
        if info.get("is_live"):
            return "진행 중인 실시간 방송은 지원하지 않습니다."
        if (info.get("duration") or 0) > MAX_DURATION:
            return f"영상 길이는 최대 {MAX_DURATION // 60}분입니다."
        tracks = info.get("requested_formats") or [info]
        if sum(track.get("filesize") or track.get("filesize_approx") or 0 for track in tracks) > max_size:
            return "다운로드 크기 제한을 초과했습니다."
        return None
    opts = {
        "format": "bestaudio/best", "outtmpl": str(output_dir / "%(title).150B [%(id)s].%(ext)s"),
        "progress_hooks": [progress_hook], "noplaylist": True, "windowsfilenames": True,
        "overwrites": True, "max_filesize": max_size, "match_filter": limit,
        "quiet": True, "noprogress": True, "retries": 3, "fragment_retries": 3, "socket_timeout": 30,
    }
    if video:
        # Copy H.264 + AAC streams into MP4, without upscaling or video re-encoding.
        opts.update(
            format=(f"bestvideo[height<={quality}][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]"
                    f"/best[height<={quality}][ext=mp4][vcodec^=avc][acodec!=none]"),
            merge_output_format="mp4",
            postprocessors=[{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        )
    else:
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": media_format,
                                   "preferredquality": "320"}]
    if executable("ffmpeg"):
        opts["ffmpeg_location"] = str(Path(executable("ffmpeg")).parent)
    if executable("node"):
        opts["js_runtimes"] = {"node": {"path": executable("node")}}
    proxy = os.environ.get("YDOWN_PROXY") or os.environ.get("WARP_PROXY")
    if proxy:
        opts["proxy"] = proxy
    if os.environ.get("YDOWN_COOKIE_FILE"):
        opts["cookiefile"] = os.environ["YDOWN_COOKIE_FILE"]
    return opts


def download_error_message(error):
    message = str(error)
    if "sign in to confirm" in message.lower() and "not a bot" in message.lower():
        return ("[YOUTUBE_AUTH_REQUIRED] YouTube가 현재 서버의 연결에 추가 인증을 요구합니다. "
                "Windows 앱에서 다시 시도해 주세요.")
    if "Requested format is not available" in message:
        return "선택한 형식과 최대 화질로 다운로드할 수 있는 영상·음원 트랙이 없습니다. 다른 형식이나 최대 화질을 선택해 주세요."
    return message[:300]


@app.websocket("/ws/download")
async def websocket_download(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if not authorized(websocket.headers) or (origin and urlsplit(origin).netloc != websocket.headers.get("host")):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    job_id = None
    worker = None
    structured = False
    disconnected = threading.Event()

    async def send(event):
        if structured:
            await websocket.send_json(event)
        elif event["type"] == "file_ready":
            await websocket.send_text(f"FILE_READY:{event['path']}:{event['filename']}")
        else:
            prefix = {"item": "INFO", "complete": "SUCCESS" if event.get("success") else "ERROR"}.get(
                event["type"], event["type"].upper())
            await websocket.send_text(prefix + ": " + event.get("message", ""))

    try:
        data = await asyncio.wait_for(websocket.receive_json(), timeout=30)
        structured = isinstance(data, dict) and "targets" in data
        urls, outputs, quality = normalize_download_request(data)
        if not all(executable(name) for name in ("ffmpeg", "ffprobe", "node")):
            raise ValueError("FFmpeg 또는 Node.js가 없습니다. Windows 설치 파일을 이용하세요.")
        if len(ACTIVE_JOBS) >= MAX_CONCURRENT_JOBS:
            raise ValueError("서버가 다른 작업을 처리하고 있습니다. 잠시 후 다시 시도하세요.")
        job_id = secrets.token_hex(16)
        output_dir = DOWNLOAD_DIR / job_id
        output_dir.mkdir(parents=True)
        ACTIVE_JOBS.add(job_id)
        loop = asyncio.get_running_loop()
        messages = asyncio.Queue(maxsize=100)
        def enqueue(message):
            if not messages.full():
                messages.put_nowait(message)
        total = len(urls) * len(outputs)
        description = " + ".join(f"MP4 영상+음성 (최대 {quality}p)" if kind == "video"
                                 else f"{fmt.upper()} 오디오" for kind, fmt in outputs)
        await send({"type": "info", "message": f"{len(urls)}개 영상에서 {description}를 다운로드합니다.", "total": total})
        success = 0
        for idx, url in enumerate(urls, 1):
            await send({"type": "item", "item": idx, "url": url, "message": f"[{idx}/{len(urls)}] {url}"})
            blocked_error = None
            for kind, media_format in outputs:
                label = "오디오" if kind == "audio" else "영상"
                if blocked_error:
                    await send({"type": "error", "item": idx, "kind": kind, "message": blocked_error})
                    continue
                transfer_sizes = {}
                max_size = MAX_VIDEO_FILESIZE if kind == "video" else MAX_FILESIZE
                stage_dir = output_dir / f"work-{idx}-{kind}"

                def hook(info, item=idx, output_kind=kind, output_label=label):
                    if disconnected.is_set():
                        raise yt_dlp.utils.DownloadError("클라이언트 연결 종료")
                    if info["status"] in {"downloading", "finished"}:
                        filename = info.get("filename", "download")
                        transfer_sizes[filename] = max(transfer_sizes.get(filename, 0), info.get("downloaded_bytes") or 0)
                        if sum(transfer_sizes.values()) > max_size:
                            raise yt_dlp.utils.DownloadError("영상과 음원을 합친 다운로드 크기 제한을 초과했습니다.")
                    if info["status"] == "downloading":
                        message = f"{output_label} 다운로드 중: " + info.get("_percent_str", "").strip()
                    elif info["status"] == "finished":
                        message = f"{output_label} 트랙 다운로드 완료. 파일을 준비하고 있습니다..."
                    else:
                        return
                    loop.call_soon_threadsafe(enqueue, {"type": "progress", "item": item,
                                                        "kind": output_kind, "message": message})

                def download():
                    stage_dir.mkdir()
                    try:
                        options = build_ydl_opts(media_format, hook, stage_dir, quality)
                        with yt_dlp.YoutubeDL(options) as ydl:
                            info = ydl.extract_info(url, download=True)
                            if info is None:
                                raise ValueError("영상이 길이 또는 크기 제한을 초과했습니다.")
                            rejection = options["match_filter"](info)
                            if rejection:
                                raise ValueError(rejection)
                            path = Path(info.get("filepath") or ydl.prepare_filename(info)).with_suffix("." + media_format).resolve()
                            if not path.is_relative_to(stage_dir.resolve()) or not path.is_file():
                                raise ValueError("변환된 파일을 찾을 수 없습니다.")
                            if path.stat().st_size > max_size:
                                raise ValueError("완료된 파일의 크기 제한을 초과했습니다.")
                            published = output_dir / f"{idx:02d} - {path.name}"
                            path.replace(published)
                            return published, info.get("title") or path.stem
                    finally:
                        shutil.rmtree(stage_dir, ignore_errors=True)

                if structured:
                    await send({"type": "progress", "item": idx, "kind": kind,
                                "message": f"[{idx}/{len(urls)}] {label} 파일을 준비하고 있습니다..."})
                worker = asyncio.create_task(asyncio.to_thread(download))
                while not worker.done():
                    try:
                        await send(await asyncio.wait_for(messages.get(), timeout=0.2))
                    except asyncio.TimeoutError:
                        pass
                while not messages.empty():
                    await send(messages.get_nowait())
                try:
                    path, title = await worker
                    relative_path = f"{job_id}/{quote(path.name)}"
                    await send({"type": "file_ready", "item": idx, "kind": kind, "title": title,
                                "path": relative_path, "url": "/downloads/" + relative_path, "filename": path.name})
                    success += 1
                except Exception as error:
                    message = f"[{idx}] {label} 다운로드 실패 - {download_error_message(error)}"
                    await send({"type": "error", "item": idx, "kind": kind, "message": message})
                    if "[YOUTUBE_AUTH_REQUIRED]" in message:
                        blocked_error = message
        await send({"type": "complete", "success": success, "failed": total - success, "total": total,
                    "message": f"{success}개 성공, {total - success}개 실패." if success else "모든 다운로드가 실패했습니다."})
    except (ValueError, asyncio.TimeoutError) as error:
        with suppress(Exception):
            await send({"type": "error", "message": str(error or '요청 시간이 초과되었습니다.')})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Download session failed")
        with suppress(Exception):
            await send({"type": "error", "message": "서버 연결이 종료되었습니다. 다시 시도하세요."})
    finally:
        disconnected.set()
        if worker:
            with suppress(Exception):
                await asyncio.shield(worker)
        if job_id:
            with suppress(OSError):
                os.utime(DOWNLOAD_DIR / job_id, None)
            ACTIVE_JOBS.discard(job_id)
        with suppress(Exception):
            await websocket.close()


if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("YDOWN_HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
