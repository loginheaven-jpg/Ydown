"""Public Windows distribution site, separate from the audio extraction app."""
import asyncio
import json
import re
import threading
import time
from urllib.parse import quote
import urllib.request

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from settings import BASE_DIR, INSTALLER_URL, RELEASES_URL

app = FastAPI(title="YDown 다운로드", docs_url=None, redoc_url=None, openapi_url=None)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
_cache = {"expires": 0, "value": None}
_lock = threading.Lock()


def latest_release():
    with _lock:
        if time.monotonic() < _cache["expires"]:
            return _cache["value"]
        result = {"version": None, "video_available": False, "portable_url": RELEASES_URL,
                  "installer_url": INSTALLER_URL, "releases_url": RELEASES_URL}
        try:
            request = urllib.request.Request(
                "https://api.github.com/repos/loginheaven-jpg/Ydown/releases/latest",
                headers={"User-Agent": "YDown-Download-Site", "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                release = json.load(response)
            version = release.get("tag_name", "").removeprefix("v")
            if re.fullmatch(r"\d+\.\d+\.\d+", version):
                result["version"] = version
                result["video_available"] = tuple(map(int, version.split("."))) >= (0, 3, 0)
                zip_name = f"YDown-{version}-windows-x64.zip"
                if any(asset.get("name") == zip_name for asset in release.get("assets", [])):
                    result["portable_url"] = RELEASES_URL + "/download/" + quote(zip_name)
        except (OSError, ValueError, TypeError, AttributeError):
            # Public release redirects also work when GitHub's API quota is exhausted.
            try:
                request = urllib.request.Request(RELEASES_URL, method="HEAD",
                                                 headers={"User-Agent": "YDown-Download-Site"})
                with urllib.request.urlopen(request, timeout=5) as response:
                    match = re.fullmatch(re.escape(RELEASES_URL.removesuffix("latest"))
                                         + r"tag/v?(\d+\.\d+\.\d+)", response.geturl())
                if match:
                    version = match.group(1)
                    result.update(version=version,
                                  video_available=tuple(map(int, version.split("."))) >= (0, 3, 0),
                                  portable_url=RELEASES_URL + f"/download/YDown-{version}-windows-x64.zip")
            except (OSError, ValueError, AttributeError):
                pass
        _cache.update(expires=time.monotonic() + (300 if result["version"] else 30), value=result)
        return result


@app.middleware("http")
async def headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.get("/health")
async def health():
    return {"status": "ok", "mode": "download-site"}


@app.get("/")
async def index(request: Request):
    release = await asyncio.to_thread(latest_release)
    return templates.TemplateResponse(request=request, name="download.html", context=release)
