import json

from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

import download_site as module


def test_public_site_has_no_extraction_or_file_access(monkeypatch):
    monkeypatch.setenv("YDOWN_REQUIRE_PASSWORD", "1")
    monkeypatch.setenv("YDOWN_PASSWORD", "private-password")
    monkeypatch.setattr(module, "latest_release", lambda: {
        "version": "0.2.0", "installer_url": module.INSTALLER_URL,
        "portable_url": module.RELEASES_URL, "releases_url": module.RELEASES_URL})
    with TestClient(module.app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert module.INSTALLER_URL in response.text
        assert "v0.2.0" in response.text
        assert "private-password" not in response.text
        assert client.get("/health").json()["mode"] == "download-site"
        assert client.get("/downloads/secret.mp3").status_code == 404
        assert client.get("/api/update").status_code == 404
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/download"):
                pass


def test_latest_release_metadata_and_cache(monkeypatch):
    calls = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({"tag_name": "v1.2.3", "assets": [
                {"name": "YDown-1.2.3-windows-x64.zip"}]}).encode()
    def fetch(*args, **kwargs):
        calls.append(1)
        return Response()
    monkeypatch.setattr(module, "_cache", {"expires": 0, "value": None})
    monkeypatch.setattr(module.urllib.request, "urlopen", fetch)
    result = module.latest_release()
    assert result["version"] == "1.2.3"
    assert result["video_available"] is True
    assert result["dual_available"] is True
    assert result["portable_url"].endswith("/download/YDown-1.2.3-windows-x64.zip")
    assert module.latest_release() == result
    assert len(calls) == 1


def test_github_unavailable_uses_verified_published_record(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("offline")
    monkeypatch.setattr(module, "_cache", {"expires": 0, "value": None})
    monkeypatch.setattr(module.urllib.request, "urlopen", unavailable)
    result = module.latest_release()
    record = json.loads((module.BASE_DIR / "packaging/published-release.json").read_text())
    assert result["version"] == record["version"]
    assert result["video_available"] is True
    assert result["latest_confirmed"] is False
    assert result["installer_url"] == module.INSTALLER_URL
    assert result["portable_url"].endswith(f"/YDown-{record['version']}-windows-x64.zip")


@pytest.mark.parametrize("version, supports_video", [("0.2.0", False), ("0.3.0", True)])
def test_video_advertising_follows_published_release(monkeypatch, version, supports_video):
    monkeypatch.setattr(module, "latest_release", lambda: {
        "version": version, "video_available": supports_video,
        "installer_url": module.INSTALLER_URL, "portable_url": module.RELEASES_URL,
        "releases_url": module.RELEASES_URL})
    with TestClient(module.app) as client:
        assert ("MP4 영상은 음성과 함께" in client.get("/").text) is supports_video


def test_public_redirect_recovers_version_when_api_is_unavailable(monkeypatch):
    class Redirect:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def geturl(self):
            return "https://github.com/loginheaven-jpg/Ydown/releases/tag/v0.3.1"
    def fetch(request, **kwargs):
        if request.get_method() == "HEAD":
            return Redirect()
        raise OSError("GitHub API unavailable")
    monkeypatch.setattr(module, "_cache", {"expires": 0, "value": None})
    monkeypatch.setattr(module.urllib.request, "urlopen", fetch)
    result = module.latest_release()
    assert result["version"] == "0.3.1"
    assert result["video_available"] is True
    assert result["portable_url"].endswith("/YDown-0.3.1-windows-x64.zip")


@pytest.mark.parametrize("version, dual", [("0.3.1", False), ("0.4.0", True)])
def test_dual_selection_instructions_follow_published_version(monkeypatch, version, dual):
    monkeypatch.setattr(module, "latest_release", lambda: {
        "version": version, "video_available": True, "dual_available": dual,
        "installer_url": module.INSTALLER_URL, "portable_url": module.RELEASES_URL,
        "releases_url": module.RELEASES_URL})
    with TestClient(module.app) as client:
        assert ("둘 다 선택하면 음원과 영상을 각각 저장합니다." in client.get("/").text) is dual
