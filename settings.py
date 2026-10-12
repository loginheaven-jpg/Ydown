"""Paths shared by source, desktop bundles and containers."""
import os
from pathlib import Path
import shutil
import sys

from version import VERSION

BASE_DIR = Path(__file__).resolve().parent
FROZEN = getattr(sys, "frozen", False)
DATA_DIR = Path(os.environ.get("YDOWN_DATA_DIR") or (
    Path(os.environ.get("LOCALAPPDATA", Path.home())) / "YDown" if FROZEN else BASE_DIR
)).resolve()
DOWNLOAD_DIR = DATA_DIR / "downloads"
RUNTIME_DIR = BASE_DIR / "runtime"
RELEASES_URL = "https://github.com/loginheaven-jpg/Ydown/releases/latest"
INSTALLER_URL = RELEASES_URL + "/download/YDown-Setup-x64.exe"


def executable(name):
    bundled = RUNTIME_DIR / (name + (".exe" if os.name == "nt" else ""))
    return str(bundled) if bundled.is_file() else shutil.which(name)
