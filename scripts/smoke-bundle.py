"""Run the frozen server from an unrelated cwd, without Python/FFmpeg on PATH."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def main():
    executable = Path(sys.argv[1]).resolve()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="ydown-smoke-") as work:
        environment = os.environ.copy()
        environment.update(PATH=os.environ["SystemRoot"] + "\\System32", YDOWN_DATA_DIR=work,
                           YDOWN_PASSWORD="", YDOWN_REQUIRE_PASSWORD="0")
        process = subprocess.Popen([str(executable), "--serve", "--port", str(port)],
                                   cwd=work, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Bundled server exited: " + str(process.returncode))
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                        assert json.load(response)["status"] == "ok"
                    break
                except OSError:
                    time.sleep(0.25)
            else:
                raise RuntimeError("Bundled server did not become ready")
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as response:
                assert "Windows 설치 파일" in response.read().decode("utf-8")
            runtime = executable.parent / "_internal/runtime"
            for name in ("ffmpeg", "ffprobe", "node"):
                subprocess.run([str(runtime / (name + ".exe")), "-version" if name != "node" else "--version"],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
            # Verify real audio conversion, including the Opus encoder DLL.
            for codec, extension in (("libmp3lame", "mp3"), ("aac", "m4a"), ("libopus", "opus")):
                subprocess.run([str(runtime / "ffmpeg.exe"), "-f", "lavfi", "-i", "sine=frequency=440:duration=0.1",
                                "-c:a", codec, str(Path(work) / ("tone." + extension))],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
            print("Bundle smoke passed: isolated startup, templates, dependencies, MP3/M4A/Opus conversion")
        finally:
            process.terminate()
            process.wait(timeout=15)


if __name__ == "__main__":
    main()
