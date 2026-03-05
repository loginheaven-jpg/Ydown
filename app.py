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

# 템플릿 디렉토리 설정
templates = Jinja2Templates(directory="templates")

# 다운로드 폴더 자동 생성 및 정적 파일 서빙 설정 (웹 배포시 다운로드 가능하도록)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

# 다운로드 파일 보존 시간 (초). 이보다 오래된 파일은 자동 삭제.
FILE_TTL_SECONDS = 600  # 10분

def cleanup_old_files():
    """FILE_TTL_SECONDS 이상 경과한 파일을 downloads 폴더에서 삭제한다."""
    now = time.time()
    for filepath in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        if os.path.isfile(filepath):
            age = now - os.path.getmtime(filepath)
            if age > FILE_TTL_SECONDS:
                try:
                    os.remove(filepath)
                except OSError:
                    pass

@app.get("/")
async def get(request: Request):
    """메인 페이지 렌더링"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    """Render 헬스체크용 엔드포인트. WARP 프록시 상태도 표시한다."""
    warp_proxy = os.environ.get("WARP_PROXY")
    return JSONResponse({
        "status": "ok",
        "warp_proxy": warp_proxy or "disabled",
    })

@app.get("/stream/{filename:path}")
async def stream_file(filename: str):
    """다운로드 완료된 파일을 스트리밍 방식으로 전송한다.
    StaticFiles 서빙이 실패할 경우의 대체 경로."""
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(filepath):
        return JSONResponse({"error": "파일을 찾을 수 없습니다."}, status_code=404)
    return FileResponse(
        filepath,
        media_type="application/octet-stream",
        filename=filename,
    )

def build_ydl_opts(audio_format, progress_hook, postprocessor_hook):
    """yt-dlp 옵션을 구성한다. 클라우드 환경 최적화 포함."""
    opts = {
        # 오디오 전용 스트림만 선택. 영상 다운로드를 완전히 회피한다.
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'progress_hooks': [progress_hook],
        'postprocessor_hooks': [postprocessor_hook],
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': audio_format,
            'preferredquality': '320',  # 최상음질(320k) 적용
        }],
        'quiet': True,
        'noprogress': True,
        'no_warnings': True,
        # 네트워크 안정성 옵션
        'retries': 3,
        'fragment_retries': 3,
        'socket_timeout': 30,
        # 클라우드 IP 차단 우회를 위한 HTTP 헤더
        'http_headers': {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/131.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        },
        # WARP 프록시가 없을 때 폴백: ios 클라이언트는 PO token 없이도 동작
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'tv_embedded'],
            }
        },
    }

    # Cloudflare WARP SOCKS5 프록시 연동 (데이터센터 IP 차단 우회)
    warp_proxy = os.environ.get("WARP_PROXY")
    if warp_proxy:
        opts['proxy'] = warp_proxy

    # 쿠키 파일이 존재하고 비어있지 않으면 사용
    cookie_path = "cookies.txt"
    if os.path.exists(cookie_path) and os.path.getsize(cookie_path) > 100:
        opts['cookiefile'] = cookie_path

    return opts


@app.websocket("/ws/download")
async def websocket_download(websocket: WebSocket):
    """웹소켓을 통한 실시간 복수 다운로드 및 진행률 전송"""
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

        # 작업 시작 전 오래된 파일 정리 (디스크 확보)
        cleanup_old_files()

        loop = asyncio.get_running_loop()

        def my_hook(d):
            """yt-dlp 다운로드 진행 상태를 웹소켓으로 전송하는 훅"""
            if d['status'] == 'downloading':
                percent = d.get('_percent_str', 'N/A').strip()
                speed = d.get('_speed_str', 'N/A').strip()
                eta = d.get('_eta_str', 'N/A').strip()
                
                # 파일명에서 제목 추출 시도
                filename = d.get('filename', '')
                title = os.path.basename(filename) if filename else "알 수 없음"
                
                msg = f"PROGRESS: [{title}] 다운로드 중... {percent} (속도: {speed}, 남은 시간: {eta})"
                asyncio.run_coroutine_threadsafe(websocket.send_text(msg), loop)
                
            elif d['status'] == 'finished':
                msg = "PROGRESS: 다운로드 완료! 오디오 파일로 변환 중입니다..."
                asyncio.run_coroutine_threadsafe(websocket.send_text(msg), loop)

        def pp_hook(d):
            """포스트프로세서(FFmpeg 변환) 완료 시 호출되는 훅"""
            if d['status'] == 'finished':
                # 변환이 완료된 최종 파일 경로를 가져옴
                info = d.get('info_dict', {})
                filepath = info.get('filepath')
                
                # fallback: filepath가 명시되지 않은 경우 원래 파일명에서 확장자만 교체
                if not filepath:
                    original = info.get('_filename', '')
                    if original:
                        filepath = os.path.splitext(original)[0] + f".{audio_format}"
                
                if filepath and os.path.exists(filepath):
                    filename = os.path.basename(filepath)
                    encoded_filename = urllib.parse.quote(filename)
                    # 클라이언트가 다운로드 링크를 생성할 수 있도록 특수 메시지 전송
                    msg = f"FILE_READY:{encoded_filename}:{filename}"
                    asyncio.run_coroutine_threadsafe(websocket.send_text(msg), loop)

        ydl_opts = build_ydl_opts(audio_format, my_hook, pp_hook)

        await websocket.send_text(
            f"INFO: 총 {len(valid_urls)}개의 URL 작업을 시작합니다.\n"
            f"최상음질(320) {audio_format.upper()} 포맷으로 추출합니다."
        )

        # ===== URL을 개별 처리하여 하나의 실패가 전체를 중단시키지 않도록 한다 =====
        success_count = 0
        fail_count = 0

        for idx, url in enumerate(valid_urls, 1):
            # 각 URL 처리 전 heartbeat (WebSocket 타임아웃 방지)
            try:
                await websocket.send_text(f"INFO: [{idx}/{len(valid_urls)}] 작업 시작: {url}")
            except Exception:
                # WebSocket이 이미 닫힌 경우 중단
                return

            def run_single_download(target_url):
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([target_url])

            try:
                await asyncio.to_thread(run_single_download, url)
                success_count += 1
            except yt_dlp.utils.DownloadError as e:
                fail_count += 1
                error_msg = str(e)
                await websocket.send_text(f"ERROR: [{idx}] 다운로드 실패 / 원인: {error_msg[:500]}")
            except Exception as e:
                fail_count += 1
                await websocket.send_text(f"ERROR: [{idx}] 서버 오류 - {str(e)[:200]}")

        # 최종 결과 요약
        if fail_count == 0:
            await websocket.send_text("SUCCESS: 모든 다운로드 및 변환 작업이 완료되었습니다!")
        elif success_count > 0:
            await websocket.send_text(
                f"SUCCESS: {success_count}개 성공, {fail_count}개 실패. "
                f"성공한 파일은 아래에서 다운로드할 수 있습니다."
            )
        else:
            await websocket.send_text("ERROR: 모든 다운로드가 실패했습니다. URL 또는 쿠키를 확인하세요.")
        
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
    # Render 클라우드 환경에서는 0.0.0.0 및 동적 PORT 연결, 로컬에서는 127.0.0.1 사용
    is_cloud = os.environ.get("RENDER") is not None or "PORT" in os.environ
    host_ip = "0.0.0.0" if is_cloud else "127.0.0.1"
    server_port = int(os.environ.get("PORT", 8000))
    
    uvicorn.run("app:app", host=host_ip, port=server_port)
