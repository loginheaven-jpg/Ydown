"""Verify the distribution container exposes only public download pages."""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
with urllib.request.urlopen(BASE + "/health", timeout=3) as response:
    assert json.load(response)["mode"] == "download-site"
with urllib.request.urlopen(BASE, timeout=10) as response:
    html = response.read().decode()
    assert "최신 Windows 버전 다운로드" in html
    assert "/releases/latest/download/YDown-Setup-x64.exe" in html
for path in ("/api/update", "/downloads/secret.mp3"):
    try:
        urllib.request.urlopen(BASE + path, timeout=3)
        raise AssertionError("Extraction routes must not exist on the public download site")
    except urllib.error.HTTPError as error:
        assert error.code == 404
print("Download site verified: public page, health, latest installer, no extraction routes")
