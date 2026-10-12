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
    return JSONResponse({"status": "ok" if ready else "missing_dependencies", "version": VERSION},
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
            or "\\" in parts[1] or Path(parts[1]).suffix not in {".mp3", ".m4a", ".opus"}):
        return JSONResponse({"error": "파일이 없거나 보관 시간이 지났습니다."}, status_code=404)
    filepath = (DOWNLOAD_DIR / filename).resolve()
    if not filepath.is_relative_to(DOWNLOAD_DIR.resolve()) or not filepath.is_file():
        return JSONResponse({"error": "파일이 없거나 보관 시간이 지났습니다."}, status_code=404)
    return FileResponse(filepath, media_type="application/octet-stream", filename=filepath.name)


def validate_request(data):
    if (not isinstance(data, dict) or not isinstance(data.get("format", "mp3"), str)
            or data.get("format", "mp3") not in {"mp3", "m4a", "opus"}):
        raise ValueError("MP3, M4A, Opus 중 하나를 선택하세요.")
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


def build_ydl_opts(audio_format, progress_hook, output_dir):
    def limit(info, *, incomplete=False):
        if info.get("is_live"):
            return "진행 중인 실시간 방송은 지원하지 않습니다."
        if (info.get("duration") or 0) > MAX_DURATION:
            return f"영상 길이는 최대 {MAX_DURATION // 60}분입니다."
        if (info.get("filesize") or info.get("filesize_approx") or 0) > MAX_FILESIZE:
            return "다운로드 크기 제한을 초과했습니다."
        return None
    opts = {
        "format": "bestaudio/best", "outtmpl": str(output_dir / "%(title).150B [%(id)s].%(ext)s"),
        "progress_hooks": [progress_hook], "noplaylist": True, "windowsfilenames": True,
        "overwrites": True, "max_filesize": MAX_FILESIZE, "match_filter": limit,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": audio_format, "preferredquality": "320"}],
        "quiet": True, "noprogress": True, "retries": 3, "fragment_retries": 3, "socket_timeout": 30,
    }
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


@app.websocket("/ws/download")
async def websocket_download(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if not authorized(websocket.headers) or (origin and urlsplit(origin).netloc != websocket.headers.get("host")):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    job_id = None
    worker = None
    disconnected = threading.Event()
    try:
        data = await asyncio.wait_for(websocket.receive_json(), timeout=30)
        urls, audio_format = validate_request(data)
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
        def hook(info):
            if disconnected.is_set():
                raise yt_dlp.utils.DownloadError("클라이언트 연결 종료")
            if info["status"] == "downloading":
                loop.call_soon_threadsafe(enqueue, "PROGRESS: " + info.get("_percent_str", "").strip())
            elif info["status"] == "finished":
                loop.call_soon_threadsafe(enqueue, "PROGRESS: 다운로드 완료. 오디오 변환 중...")
        await websocket.send_text(f"INFO: {len(urls)}개 영상에서 {audio_format.upper()} 오디오를 추출합니다.")
        success = 0
        for idx, url in enumerate(urls, 1):
            await websocket.send_text(f"INFO: [{idx}/{len(urls)}] {url}")
            def download():
                with yt_dlp.YoutubeDL(build_ydl_opts(audio_format, hook, output_dir)) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info is None:
                        raise ValueError("영상이 길이 또는 크기 제한을 초과했습니다.")
                    path = Path(ydl.prepare_filename(info)).with_suffix("." + audio_format)
                    if not path.is_file():
                        raise ValueError("변환된 파일을 찾을 수 없습니다.")
                    return path
            worker = asyncio.create_task(asyncio.to_thread(download))
            while not worker.done():
                try:
                    await websocket.send_text(await asyncio.wait_for(messages.get(), timeout=0.2))
                except asyncio.TimeoutError:
                    pass
            while not messages.empty():
                await websocket.send_text(messages.get_nowait())
            try:
                path = await worker
                await websocket.send_text(f"FILE_READY:{job_id}/{quote(path.name)}:{path.name}")
                success += 1
            except Exception as error:
                await websocket.send_text(f"ERROR: [{idx}] 다운로드 실패 - {str(error)[:300]}")
        await websocket.send_text(f"SUCCESS: {success}개 성공, {len(urls) - success}개 실패." if success
                                  else "ERROR: 모든 다운로드가 실패했습니다.")
    except (ValueError, asyncio.TimeoutError) as error:
        with suppress(Exception):
            await websocket.send_text(f"ERROR: {error or '요청 시간이 초과되었습니다.'}")
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Download session failed")
        with suppress(Exception):
            await websocket.send_text("ERROR: 서버 연결이 종료되었습니다. 다시 시도하세요.")
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
