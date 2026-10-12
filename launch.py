"""Desktop entry point. No child Python process is required in a frozen build."""
import argparse
import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn
from settings import DATA_DIR, DOWNLOAD_DIR, RELEASES_URL, VERSION


def free_port(preferred):
    for port in range(preferred, preferred + 20):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("사용할 수 있는 로컬 포트가 없습니다.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="Run without a desktop window")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=DATA_DIR / "ydown.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    from app import app
    if args.serve:
        uvicorn.run(app, host=args.host, port=args.port, log_config=None)
        return
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title("YDown " + VERSION)
    root.geometry("400x265")
    root.resizable(False, False)
    ttk.Label(root, text="YDown Audio", font=("Segoe UI", 19, "bold")).pack(pady=(20, 8))
    status = tk.StringVar(value="로컬 서버를 준비하고 있습니다...")
    ttk.Label(root, textvariable=status).pack(pady=6)
    port = free_port(args.port)
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    ttk.Button(root, text="브라우저 열기", command=lambda: webbrowser.open(url)).pack(fill="x", padx=40, pady=4)
    def open_downloads():
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(DOWNLOAD_DIR)
    ttk.Button(root, text="임시 파일 폴더 열기", command=open_downloads).pack(fill="x", padx=40, pady=4)
    ttk.Button(root, text="최신 버전 / 업데이트", command=lambda: webbrowser.open(RELEASES_URL)).pack(fill="x", padx=40, pady=4)
    def stop():
        server.should_exit = True
        root.destroy()
    ttk.Button(root, text="YDown 종료", command=stop).pack(fill="x", padx=40, pady=4)
    root.protocol("WM_DELETE_WINDOW", stop)
    deadline = time.monotonic() + 30
    def poll():
        if server.started:
            status.set(f"실행 중 · {url}")
            webbrowser.open(url)
        elif not thread.is_alive() or time.monotonic() > deadline:
            status.set("시작 실패. ydown.log를 확인하세요.")
        else:
            root.after(200, poll)
    root.after(200, poll)
    root.mainloop()
    server.should_exit = True
    thread.join(timeout=5)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("YDown failed to start")
        if getattr(sys, "frozen", False) and "--serve" not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, "YDown 시작 실패. %LOCALAPPDATA%\\YDown\\ydown.log를 확인하세요.", "YDown", 16)
        raise
