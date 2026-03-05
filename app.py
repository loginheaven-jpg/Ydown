import asyncio
import os
import urllib.parse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
import yt_dlp

app = FastAPI()

# 템플릿 디렉토리 설정
templates = Jinja2Templates(directory="templates")

# 다운로드 폴더 자동 생성 및 정적 파일 서빙 설정 (웹 배포시 다운로드 가능하도록)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

@app.get("/")
async def get(request: Request):
    """메인 페이지 렌더링"""
    return templates.TemplateResponse("index.html", {"request": request})

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

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'progress_hooks': [my_hook],
            'postprocessor_hooks': [pp_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': audio_format,
                'preferredquality': '320', # 최상음질(320k) 적용
            }],
            'quiet': True,
            'noprogress': True
        }
        
        # 유튜브 봇 감지 완전 우회를 위한 쿠키 파일 연동
        if os.path.exists("cookies.txt"):
            ydl_opts['cookiefile'] = "cookies.txt"
        
        def run_yt_dlp():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 리스트로 전달된 URL들을 순차적으로 다운로드
                ydl.download(valid_urls)

        await websocket.send_text(f"INFO: 총 {len(valid_urls)}개의 URL 작업을 시작합니다.\n최상음질(320) 포맷으로 추출합니다.")
        
        # yt-dlp는 동기 블로킹 함수이므로 스레드에서 실행
        await asyncio.to_thread(run_yt_dlp)
        
        await websocket.send_text("SUCCESS: 모든 다운로드 및 변환 작업이 완료되었습니다!")
        
    except WebSocketDisconnect:
        print("Client disconnected")
    except yt_dlp.utils.DownloadError as e:
        await websocket.send_text(f"ERROR: 다운로드 실패 - {str(e)}")
    except Exception as e:
        await websocket.send_text(f"ERROR: 서버 오류 - {str(e)}")
    finally:
        try:
            await websocket.close()
        except:
            pass

if __name__ == "__main__":
    # Render 클라우드 환경에서는 0.0.0.0 및 동적 PORT 연결, 로컬에서는 127.0.0.1 사용
    is_cloud = os.environ.get("RENDER") is not None or "PORT" in os.environ
    host_ip = "0.0.0.0" if is_cloud else "127.0.0.1"
    server_port = int(os.environ.get("PORT", 8000))
    
    uvicorn.run("app:app", host=host_ip, port=server_port)
