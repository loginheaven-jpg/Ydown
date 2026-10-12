"""Executed inside the CI container through stdin."""
import asyncio
import base64
import json
import urllib.error
import urllib.request

from websockets.asyncio.client import connect

BASE = "http://127.0.0.1:8000"
AUTHORIZATION = "Basic " + base64.b64encode(b"ydown:ci-password").decode()


async def main():
    with urllib.request.urlopen(BASE + "/health", timeout=3) as response:
        assert json.load(response)["status"] == "ok"
    try:
        urllib.request.urlopen(BASE, timeout=3)
        raise AssertionError("Unauthenticated UI must be rejected")
    except urllib.error.HTTPError as error:
        assert error.code == 401
    request = urllib.request.Request(BASE, headers={"Authorization": AUTHORIZATION})
    with urllib.request.urlopen(request, timeout=3) as response:
        assert "Windows 설치 파일" in response.read().decode()
    async with connect("ws://127.0.0.1:8000/ws/download", additional_headers={"Authorization": AUTHORIZATION}) as ws:
        await ws.send(json.dumps({"urls": [], "format": "mp3"}))
        assert (await ws.recv()).startswith("ERROR:")
    print("Container verified: dependencies, health, template, HTTP auth, WebSocket auth")


asyncio.run(main())
