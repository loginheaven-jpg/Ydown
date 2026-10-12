# Bundled components

YDown includes unmodified FFmpeg/ffprobe (BtbN LGPL shared build), Node.js,
CPython, and Python packages. No system-wide installation is performed.

- FFmpeg: https://ffmpeg.org/ — LGPL v3 or later (this build). The build's license,
  configuration and notices are in `_internal/runtime/licenses/ffmpeg`.
  Exact download, checksum, corresponding upstream source and build recipe
  are recorded in `_internal/runtime/licenses/runtime-manifest.json`.
  Shared FFmpeg DLLs are replaceable without rebuilding YDown.
- Node.js: https://nodejs.org/ — MIT and bundled component notices.
  See `_internal/runtime/licenses/node/LICENSE`.
- CPython: https://www.python.org/ — PSF license. See
  `_internal/runtime/licenses/Python-LICENSE.txt`.
- Python packages: see `third-party-licenses.json` for package versions,
  project URLs, license information and license texts.

YDown source: https://github.com/loginheaven-jpg/Ydown
