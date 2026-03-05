import asyncio
import os
import time
import glob
import urllib.parse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn
import yt_dlp

app = FastAPI()

templates = Jinja2Templates(directory="templates")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

FILE_TTL_SECONDS = 600  # 10분

def cleanup_old_files():
    now = time.time()
    for filepath in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        if os.path.isfile(filepath):
            if now - os.path.getmtime(filepath) > FILE_TTL_SECONDS:
                try:
                    os.remove(filepath)
                except OSError:
                    pass

@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})

@app.get("/stream/{filename:path}")
async def stream_file(filename: str):
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(filepath):
        return JSONResponse({"error": "파일을 찾을 수 없습니다."}, status_code=404)
    return FileResponse(filepath, media_type="application/octet-stream", filename=filename)

def build_ydl_opts(audio_format, progress_hook, postprocessor_hook):
    return {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'progress_hooks': [progress_hook],
        'postprocessor_hooks': [postprocessor_hook],
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': audio_format,
            'preferredquality': '320',
        }],
        'quiet': True,
        'noprogress': True,
        'no_warnings': True,
        'retries': 3,
        'fragment_retries': 3,
        'socket_timeout': 30,
    }

@app.websocket("/ws/download")
async def websocket_download(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        urls = data.get("urls", [])
        audio_format = data.get("format", "mp3")

        valid_urls = [u.strip() for u in urls if u.strip()]
        if not valid_urls:
            await websocket.send_text("ERROR: 최소 한 개의 URL을 입력해주세요.")
            await websocket.close()
            return

        cleanup_old_files()
        loop = asyncio.get_running_loop()

        def my_hook(d):
            if d['status'] == 'downloading':
                percent = d.get('_percent_str', 'N/A').strip()
                speed = d.get('_speed_str', 'N/A').strip()
                eta = d.get('_eta_str', 'N/A').strip()
                filename = d.get('filename', '')
                title = os.path.basename(filename) if filename else "알 수 없음"
                msg = f"PROGRESS: [{title}] {percent} (속도: {speed}, 남은 시간: {eta})"
                asyncio.run_coroutine_threadsafe(websocket.send_text(msg), loop)
            elif d['status'] == 'finished':
                asyncio.run_coroutine_threadsafe(
                    websocket.send_text("PROGRESS: 다운로드 완료! 변환 중..."), loop)

        def pp_hook(d):
            if d['status'] == 'finished':
                info = d.get('info_dict', {})
                filepath = info.get('filepath')
                if not filepath:
                    original = info.get('_filename', '')
                    if original:
                        filepath = os.path.splitext(original)[0] + f".{audio_format}"
                if filepath and os.path.exists(filepath):
                    filename = os.path.basename(filepath)
                    encoded_filename = urllib.parse.quote(filename)
                    msg = f"FILE_READY:{encoded_filename}:{filename}"
                    asyncio.run_coroutine_threadsafe(websocket.send_text(msg), loop)

        ydl_opts = build_ydl_opts(audio_format, my_hook, pp_hook)

        await websocket.send_text(
            f"INFO: 총 {len(valid_urls)}개의 URL 작업을 시작합니다. "
            f"최상음질(320) {audio_format.upper()} 포맷으로 추출합니다."
        )

        success_count = 0
        fail_count = 0

        for idx, url in enumerate(valid_urls, 1):
            try:
                await websocket.send_text(f"INFO: [{idx}/{len(valid_urls)}] 작업 시작: {url}")
            except Exception:
                return

            def run_single_download(target_url):
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([target_url])

            try:
                await asyncio.to_thread(run_single_download, url)
                success_count += 1
            except yt_dlp.utils.DownloadError as e:
                fail_count += 1
                await websocket.send_text(f"ERROR: [{idx}] 다운로드 실패 - {str(e)[:300]}")
            except Exception as e:
                fail_count += 1
                await websocket.send_text(f"ERROR: [{idx}] 서버 오류 - {str(e)[:200]}")

        if fail_count == 0:
            await websocket.send_text("SUCCESS: 모든 다운로드 및 변환 작업이 완료되었습니다!")
        elif success_count > 0:
            await websocket.send_text(f"SUCCESS: {success_count}개 성공, {fail_count}개 실패.")
        else:
            await websocket.send_text("ERROR: 모든 다운로드가 실패했습니다.")

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        try:
            await websocket.send_text(f"ERROR: 서버 오류 - {str(e)}")
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000)
