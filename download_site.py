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
        result = {"version": None, "portable_url": RELEASES_URL,
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
                zip_name = f"YDown-{version}-windows-x64.zip"
                if any(asset.get("name") == zip_name for asset in release.get("assets", [])):
                    result["portable_url"] = RELEASES_URL + "/download/" + quote(zip_name)
        except (OSError, ValueError, TypeError, AttributeError):
            # Fixed latest-release links remain useful if GitHub metadata is unavailable.
            pass
        _cache.update(expires=time.monotonic() + 300, value=result)
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
