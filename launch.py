"""
YDown 로컬 실행기
- uvicorn 서버를 백그라운드에서 시작
- 서버가 준비되면 기본 브라우저로 자동 오픈
- Ctrl+C 또는 창 닫기로 종료
"""
import subprocess
import webbrowser
import time
import sys
import os
import urllib.request
import urllib.error

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def wait_for_server(timeout=15):
    """서버가 응답할 때까지 최대 timeout초 대기."""
    for _ in range(timeout):
        try:
            urllib.request.urlopen(URL, timeout=1)
            return True
        except Exception:
            time.sleep(1)
    return False


def main():
    # 스크립트가 있는 폴더를 작업 디렉토리로 설정
    base_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 45)
    print("  YDown 로컬 서버 시작 중...")
    print("=" * 45)

    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app:app",
            "--host", HOST,
            "--port", str(PORT),
        ],
        cwd=base_dir,
    )

    print(f"서버 준비 대기 중... ({URL})")
    if wait_for_server():
        print("서버 준비 완료! 브라우저를 엽니다.")
        webbrowser.open(URL)
    else:
        print("서버 시작 실패. 터미널 출력을 확인하세요.")
        server.terminate()
        input("아무 키나 누르면 종료됩니다...")
        return

    print("\n서버가 실행 중입니다. 이 창을 닫으면 서버가 종료됩니다.")
    print("종료하려면 Ctrl+C를 누르세요.\n")

    try:
        server.wait()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다...")
        server.terminate()


if __name__ == "__main__":
    main()
