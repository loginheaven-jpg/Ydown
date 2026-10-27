from pathlib import Path

from fastapi.testclient import TestClient
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


def request(audio=True, video=True, **settings):
    return {"urls": [VIDEO], "targets": {"audio": audio, "video": video}, **settings}


def run(client, payload):
    events = []
    with client.websocket_connect("/ws/download") as ws:
        ws.send_json(payload)
        while True:
            event = ws.receive_json()
            events.append(event)
            if event["type"] == "complete":
                return events


@pytest.fixture
def downloader(monkeypatch):
    class Downloader:
        fail = None
        calls = []
        def __init__(self, options):
            self.options = options
            self.format = options["postprocessors"][0].get("preferredcodec", "mp4")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download):
            assert len(module.ACTIVE_JOBS) == 1
            self.calls.append((url, self.format))
            folder = Path(self.options["outtmpl"]).parent
            if self.format == self.fail:
                (folder / "unfinished.part").write_bytes(b"partial")
                raise module.yt_dlp.utils.DownloadError("simulated output failure")
            path = folder / ("테스트 영상." + self.format)
            path.write_bytes(self.format.encode())
            self.options["progress_hooks"][0]({"status": "finished"})
            return {"path": str(path), "title": "테스트 영상"}
        def prepare_filename(self, info):
            return info["path"]
    monkeypatch.setattr(module.yt_dlp, "YoutubeDL", Downloader)
    return Downloader


@pytest.mark.parametrize("audio,video,formats", [(True, False, ["mp3"]), (False, True, ["mp4"]),
                                              (True, True, ["mp3", "mp4"])])
def test_selected_outputs_are_independent_downloadable_files(client, downloader, audio, video, formats):
    events = run(client, request(audio, video))
    files = [event for event in events if event["type"] == "file_ready"]
    assert [Path(event["filename"]).suffix for event in files] == ["." + fmt for fmt in formats]
    for event, fmt in zip(files, formats):
        assert client.get(event["url"]).content == fmt.encode()
        assert event["kind"] == ("video" if fmt == "mp4" else "audio")
    assert events[-1]["total"] == events[-1]["success"] == len(formats)
    assert events[-1]["failed"] == 0
    assert not list(module.DOWNLOAD_DIR.glob("*/work-*"))
    assert not module.ACTIVE_JOBS


@pytest.mark.parametrize("targets", [{}, {"audio": False, "video": False}, [], None,
                                   {"audio": "false"}, {"video": 1}, {"audio": True, "unknown": True}])
def test_invalid_output_selections_are_rejected(client, targets):
    with client.websocket_connect("/ws/download") as ws:
        ws.send_json({"urls": [VIDEO], "targets": targets})
        assert ws.receive_json()["type"] == "error"
    assert not module.ACTIVE_JOBS


@pytest.mark.parametrize("settings", [{"audio_format": "mp4"}, {"audio_format": []},
                                     {"video_quality": "2160"}, {"video_quality": 1080}])
def test_selected_settings_are_validated(settings):
    with pytest.raises(ValueError):
        module.normalize_download_request(request(**settings))


def test_inactive_settings_are_ignored():
    _, outputs, quality = module.normalize_download_request(request(True, False, video_quality=None))
    assert outputs == [("audio", "mp3")]
    assert quality == "1080"
    _, outputs, quality = module.normalize_download_request(request(False, True, audio_format=None))
    assert outputs == [("video", "mp4")]


@pytest.mark.parametrize("failed_format", ["mp3", "mp4"])
def test_partial_failure_preserves_sibling_output_and_continues_next_url(client, downloader, failed_format):
    downloader.fail = failed_format
    payload = request()
    payload["urls"] *= 2
    events = run(client, payload)
    assert events[-1]["success"] == 2
    assert events[-1]["failed"] == 2
    assert events[-1]["total"] == 4
    files = [event for event in events if event["type"] == "file_ready"]
    assert len({event["url"] for event in files}) == 2
    assert {event["item"] for event in files} == {1, 2}
    for event in files:
        assert client.get(event["url"]).status_code == 200
        assert not event["filename"].endswith("." + failed_format)
    assert not list(module.DOWNLOAD_DIR.glob("*/work-*"))


@pytest.mark.parametrize("audio_format", ["m4a", "opus"])
def test_other_audio_formats_can_be_combined_with_video(client, downloader, audio_format):
    events = run(client, request(audio_format=audio_format))
    assert events[-1]["success"] == 2
    assert [fmt for _, fmt in downloader.calls] == [audio_format, "mp4"]


def test_shared_source_authentication_failure_does_not_retry_other_output(client, monkeypatch, downloader):
    def blocked(self, url, download):
        self.calls.append((url, self.format))
        raise module.yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot.")
    monkeypatch.setattr(downloader, "extract_info", blocked)
    events = run(client, request())
    assert len(downloader.calls) == 1
    assert events[-1]["success"] == 0
    assert events[-1]["failed"] == events[-1]["total"] == 2


def test_size_skip_reports_limit_instead_of_missing_file(client, monkeypatch, downloader):
    def skipped(self, url, download):
        return {"path": str(Path(self.options["outtmpl"]).parent / "large.mp4"),
                "filesize": module.MAX_VIDEO_FILESIZE + 1}
    monkeypatch.setattr(downloader, "extract_info", skipped)
    events = run(client, request(False, True))
    error = next(event for event in events if event["type"] == "error")
    assert "크기 제한" in error["message"]
    assert "찾을 수 없습니다" not in error["message"]
