import base64
import json
import os
from pathlib import Path
import time
from urllib.parse import quote

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest

import app as module

VIDEO = "https://youtu.be/BaW_jenozKc"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "DOWNLOAD_DIR", tmp_path / "downloads")
    monkeypatch.setattr(module, "PASSWORD", "")
    monkeypatch.setenv("YDOWN_REQUIRE_PASSWORD", "0")
    monkeypatch.setattr(module, "executable", lambda name: "/runtime/" + name)
    module.ACTIVE_JOBS.clear()
    with TestClient(module.app) as instance:
        yield instance
    module.ACTIVE_JOBS.clear()


@pytest.mark.parametrize("url", [VIDEO, "https://www.youtube.com/watch?v=BaW_jenozKc&list=ignored", "https://m.youtube.com/shorts/BaW_jenozKc"])
def test_canonical_video_urls(url):
    assert module.validate_request({"urls": [url], "format": "mp3"}) == (
        ["https://www.youtube.com/watch?v=BaW_jenozKc"], "mp3")


@pytest.mark.parametrize("data", [
    None, {"urls": []}, {"urls": [VIDEO] * 11}, {"urls": [2]},
    {"urls": ["http://127.0.0.1:8000/health"]}, {"urls": ["https://youtube.com.evil.test/watch?v=BaW_jenozKc"]},
    {"urls": ["file:///etc/passwd"]}, {"urls": ["https://youtube.com/playlist?list=test"]},
    {"urls": ["https://evil@youtube.com/watch?v=BaW_jenozKc"]}, {"urls": [VIDEO], "format": "wav"},
    {"urls": [VIDEO], "format": []},
])
def test_invalid_requests(data):
    with pytest.raises(ValueError):
        module.validate_request(data)


def test_templates_and_health(client, monkeypatch):
    assert "Windows 설치 파일" in client.get("/").text
    assert client.get("/health").json()["status"] == "ok"
    monkeypatch.setattr(module, "executable", lambda name: None)
    assert client.get("/health").status_code == 503


def test_basic_auth_http_and_websocket(client, monkeypatch):
    monkeypatch.setattr(module, "PASSWORD", "secret")
    assert client.get("/").status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/", auth=("ydown", "secret")).status_code == 200
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/download"):
            pass
    authorization = "Basic " + base64.b64encode(b"ydown:secret").decode()
    with client.websocket_connect("/ws/download", headers={"Authorization": authorization}) as ws:
        ws.send_json({"urls": []})
        assert ws.receive_text().startswith("ERROR:")


def test_cross_origin_websocket_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/download", headers={"Origin": "https://evil.test"}):
            pass


def test_file_download_and_traversal(client, tmp_path):
    job = module.DOWNLOAD_DIR / ("a" * 32)
    job.mkdir()
    name = "한글 제목.mp3"
    (job / name).write_bytes(b"audio")
    response = client.get("/stream/" + job.name + "/" + quote(name))
    assert response.content == b"audio"
    assert response.headers["content-disposition"].startswith("attachment;")
    (tmp_path / "secret.mp3").write_bytes(b"private")
    for path in ["../secret.mp3", "a" * 32 + "/%2e%2e%2f%2e%2e%2fsecret.mp3", "a" * 32 + "/..%5c..%5csecret.mp3", "cookies.txt"]:
        assert client.get("/stream/" + path).status_code == 404


def test_cleanup_preserves_active_job(client):
    active = module.DOWNLOAD_DIR / ("a" * 32)
    old = module.DOWNLOAD_DIR / ("b" * 32)
    for path in (active, old):
        path.mkdir()
        (path / "audio.mp3").write_bytes(b"audio")
        os.utime(path, (0, 0))
    module.ACTIVE_JOBS.add(active.name)
    module.cleanup_old_files()
    assert active.exists()
    assert not old.exists()


class FakeDownloader:
    def __init__(self, options):
        self.options = options
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def extract_info(self, url, download):
        if "failfail123" in url:
            raise module.yt_dlp.utils.DownloadError("simulated failure")
        output = Path(self.options["outtmpl"]).parent / "한글 제목 [BaW_jenozKc].mp3"
        output.write_bytes(b"audio")
        self.options["progress_hooks"][0]({"status": "finished"})
        return {"path": str(output)}
    def prepare_filename(self, info):
        return info["path"]


def test_batch_continues_after_error_and_file_ready(client, monkeypatch):
    monkeypatch.setattr(module.yt_dlp, "YoutubeDL", FakeDownloader)
    with client.websocket_connect("/ws/download") as ws:
        ws.send_json({"urls": ["https://youtu.be/failfail123", VIDEO], "format": "mp3"})
        messages = []
        while True:
            message = ws.receive_text()
            messages.append(message)
            if message.startswith("SUCCESS:"):
                break
    assert any(message.startswith("ERROR:") for message in messages)
    ready = next(message for message in messages if message.startswith("FILE_READY:"))
    assert client.get("/stream/" + ready.split(":")[1]).content == b"audio"
    assert messages[-1] == "SUCCESS: 1개 성공, 1개 실패."
    assert not module.ACTIVE_JOBS


def test_busy_server_rejects_new_work(client):
    module.ACTIVE_JOBS.update(str(i) for i in range(module.MAX_CONCURRENT_JOBS))
    with client.websocket_connect("/ws/download") as ws:
        ws.send_json({"urls": [VIDEO]})
        assert "다른 작업" in ws.receive_text()


def test_source_authentication_failure_offers_local_app(client, monkeypatch):
    class BlockedDownloader(FakeDownloader):
        def extract_info(self, url, download):
            raise module.yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot. Use --cookies")
    monkeypatch.setattr(module.yt_dlp, "YoutubeDL", BlockedDownloader)
    with client.websocket_connect("/ws/download") as ws:
        ws.send_json({"urls": [VIDEO], "format": "mp3"})
        assert ws.receive_text().startswith("INFO:")
        assert ws.receive_text().startswith("INFO:")
        message = ws.receive_text()
        assert "[YOUTUBE_AUTH_REQUIRED]" in message
        assert "Windows 앱" in message
        assert "--cookies" not in message
        assert ws.receive_text().startswith("ERROR:")
    assert not module.ACTIVE_JOBS


def test_proxy_cookie_runtime_and_limits(monkeypatch, tmp_path):
    monkeypatch.setenv("YDOWN_PROXY", "socks5://127.0.0.1:40000")
    monkeypatch.setenv("YDOWN_COOKIE_FILE", "/private/cookies.txt")
    monkeypatch.setattr(module, "executable", lambda name: "/runtime/" + name)
    options = module.build_ydl_opts("mp3", lambda data: None, tmp_path)
    assert options["proxy"] == "socks5://127.0.0.1:40000"
    assert options["cookiefile"] == "/private/cookies.txt"
    assert options["js_runtimes"]["node"]["path"] == "/runtime/node"
    assert options["noplaylist"] is True
    assert options["match_filter"]({"duration": None}) is None
    assert options["match_filter"]({"duration": module.MAX_DURATION + 1})
    assert options["match_filter"]({"is_live": True})


def test_update_cache_and_version(client, monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({"tag_name": "v9.0.0", "assets": [{"name": "YDown-Setup-x64.exe"}]}).encode()
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(module, "_update_cache", {"expires": 0, "value": None})
    response = client.get("/api/update").json()
    assert response["available"] is True
    assert response["latest_version"] == "9.0.0"


def test_public_startup_requires_password(monkeypatch):
    monkeypatch.setenv("YDOWN_REQUIRE_PASSWORD", "1")
    monkeypatch.setattr(module, "PASSWORD", "")
    with pytest.raises(RuntimeError, match="YDOWN_PASSWORD"):
        with TestClient(module.app):
            pass


@pytest.mark.parametrize("quality", ["360", "2160", 1080, [], None])
def test_invalid_video_quality(quality):
    with pytest.raises(ValueError):
        module.validate_request({"urls": [VIDEO], "format": "mp4", "quality": quality})


@pytest.mark.parametrize("quality", ["480", "720", "1080"])
def test_real_format_selection_respects_maximum_and_preserves_audio(quality, monkeypatch, tmp_path):
    monkeypatch.setattr(module, "executable", lambda name: None)
    formats = [
        {"format_id": str(height), "url": f"https://example.org/{height}.mp4", "ext": "mp4",
         "height": height, "width": height * 16 // 9, "vcodec": "avc1.640028", "acodec": "none"}
        for height in (360, 480, 720, 1080, 2160)
    ] + [{"format_id": "audio", "url": "https://example.org/audio.m4a", "ext": "m4a",
          "vcodec": "none", "acodec": "mp4a.40.2"}]
    options = module.build_ydl_opts("mp4", lambda data: None, tmp_path, quality)
    with module.yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.process_ie_result({"id": "video", "title": "test", "formats": formats}, download=False)
    video, audio = info["requested_formats"]
    assert video["height"] == int(quality)
    assert audio["acodec"] == "mp4a.40.2"
    assert options["merge_output_format"] == "mp4"


def test_combined_video_track_size_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "MAX_VIDEO_FILESIZE", 100)
    options = module.build_ydl_opts("mp4", lambda data: None, tmp_path)
    assert options["match_filter"]({"requested_formats": [{"filesize": 60}, {"filesize": 50}]})
    assert options["match_filter"]({"requested_formats": [{"filesize": 60}, {"filesize": 30}]}) is None


def test_mp4_websocket_final_path_and_download(client, monkeypatch):
    class VideoDownloader(FakeDownloader):
        def extract_info(self, url, download):
            output = Path(self.options["outtmpl"]).parent / "한글 영상.mp4"
            output.write_bytes(b"video-with-audio")
            self.options["progress_hooks"][0]({"status": "finished"})
            return {"path": str(output.with_suffix(".webm")), "filepath": str(output)}
    monkeypatch.setattr(module.yt_dlp, "YoutubeDL", VideoDownloader)
    with client.websocket_connect("/ws/download") as ws:
        ws.send_json({"urls": [VIDEO], "format": "mp4", "quality": "720"})
        messages = []
        while not messages or not messages[-1].startswith("SUCCESS:"):
            messages.append(ws.receive_text())
    assert "최대 720p" in messages[0]
    ready = next(message for message in messages if message.startswith("FILE_READY:"))
    response = client.get("/downloads/" + ready.split(":")[1])
    assert response.status_code == 200
    assert response.content == b"video-with-audio"
    assert ".mp4" in response.headers["content-disposition"]


def test_unknown_size_tracks_stop_at_combined_transfer_limit(client, monkeypatch):
    monkeypatch.setattr(module, "MAX_VIDEO_FILESIZE", 100)
    class LargeDownloader(FakeDownloader):
        def extract_info(self, url, download):
            hook = self.options["progress_hooks"][0]
            hook({"status": "downloading", "filename": "video.mp4", "downloaded_bytes": 60})
            hook({"status": "downloading", "filename": "audio.m4a", "downloaded_bytes": 50})
            raise AssertionError("Should stop before continuing transfer")
    monkeypatch.setattr(module.yt_dlp, "YoutubeDL", LargeDownloader)
    with client.websocket_connect("/ws/download") as ws:
        ws.send_json({"urls": [VIDEO], "format": "mp4"})
        messages = []
        while not messages or messages[-1] != "ERROR: 모든 다운로드가 실패했습니다.":
            messages.append(ws.receive_text())
    assert any("크기 제한" in message for message in messages)
    assert not any(message.startswith("FILE_READY:") for message in messages)
