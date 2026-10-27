# YDown

YouTube 영상을 음성이 포함된 MP4로 저장하거나 MP3, M4A, Opus 오디오를 추출하는 **브라우저 기반 앱**입니다.
영상 링크를 최대 10개 입력하면 차례로 처리하고 다운로드 버튼을 표시합니다.
오디오는 최대 320kbps로 변환하며 원본보다 음질이 향상되거나 무손실이 되는 것은 아닙니다.
MP4는 최대 480p·720p·1080p 중 선택하며 기본값은 최대 1080p입니다. 원본에서 제공하는
H.264 영상과 AAC 음성을 재인코딩 없이 합쳐 저장하므로 원본보다 높게 확대하지 않습니다.
해당 트랙이 없는 영상은 다른 다운로드 형식이나 최대 화질을 선택해야 합니다.

**현재 권장 사용 방식:** [Windows 설치 파일 다운로드](https://github.com/loginheaven-jpg/Ydown/releases/latest/download/YDown-Setup-x64.exe).
설치 후 브라우저 화면을 사용하며, 영상 다운로드와 오디오 변환은 사용 중인 PC에서 실행합니다.

**다운로드 사이트:** [ydown.yebom.org](https://ydown.yebom.org).
최신 정식 릴리스의 설치 파일, ZIP 버전, 설치·업데이트 방법을 로그인 없이 안내합니다.
릴리스 정보는 GitHub에서 가져오며, 새 정식 릴리스를 게시하면 다운로드 링크가 최신 버전을 가리킵니다.
이 사이트에서는 오디오를 추출하지 않습니다.

## 다른 Windows PC에서 사용하기

대상: **Windows 10/11 64비트 (x64)**.

1. [최신 릴리스](https://github.com/loginheaven-jpg/Ydown/releases/latest)에서
   **YDown-Setup-x64.exe**를 다운로드해 실행합니다.
2. 설치 후 시작 메뉴 또는 바탕화면의 **YDown**을 실행합니다.
3. 자동으로 열린 브라우저에서 영상 주소와 다운로드할 오디오·영상 대상을 선택합니다.
4. 완료된 파일의 **다운로드** 버튼을 눌러 원하는 폴더에 저장합니다.

**다운로드 대상**에서 **오디오 파일**, **영상 파일 (MP4·음성 포함)**을 각각 체크합니다.
둘 다 선택하면 URL마다 음원과 MP4를 각각 생성합니다. **설정**에서 오디오 형식과
영상 최대 화질을 따로 선택합니다. 선택하지 않은 대상의 설정은 비활성화되며,
형식·화질 설정은 이 브라우저에 저장됩니다. 다운로드 대상은 실행 시 오디오만 선택한 상태로 시작합니다.
영상은 오디오 체크 여부에 관계없이 소리를 포함합니다. 최소 한 대상을 선택해야 시작할 수 있습니다.
결과는 영상 제목별로 묶이고 각 파일의 저장 버튼을 제공합니다. 일부 실패 시에도 성공한 파일은 저장할 수 있습니다.
영상의 다운로드 크기 기본 한도는
영상·음성 트랙 합계 2GiB, 오디오 원본은 250MiB, 개별 영상 길이는 최대 60분입니다.

**영상 다운로드 검증 (2026-10-27):** 실제 YouTube 영상의 MP4 다운로드, Windows 번들에서
영상·음성 병합, 브라우저 파일 저장, H.264/AAC 트랙과 디코딩을 확인했습니다.
기존 MP3 실제 다운로드와 번들의 MP3/M4A/Opus 변환 검사도 통과했습니다.

Python, FFmpeg, Node.js는 모두 포함됩니다. 별도 설치와 관리자 권한이 필요하지 않습니다.
설치 대신 ZIP을 사용하려면 `YDown-버전-windows-x64.zip`을 **전체 압축 해제**하고
그 안의 `YDown.exe`를 실행하세요. EXE만 따로 옮기면 실행되지 않습니다.

**업데이트:** 앱의 `최신 버전 / 업데이트` 또는 웹 화면의 `업데이트 확인`을 누른 후
최신 설치 파일을 실행하면 같은 설치 위치에 업그레이드됩니다. 기존 앱을 종료하고
설치하세요. 포터블 사용자는 새 ZIP을 별도 폴더에 전체 압축 해제하면 됩니다.
자동으로 설치하거나 재시작하는 업데이트는 아닙니다.

앱 창을 닫으면 로컬 서버가 종료됩니다. 설치 위치는
`%LOCALAPPDATA%\Programs\YDown`, 로그와 임시 파일은 `%LOCALAPPDATA%\YDown`입니다.
임시 파일은 기본 60분 후 정리되므로 브라우저의 다운로드 버튼으로 보관할 파일을 저장하세요.
서명되지 않은 초기 설치 파일에서 Windows가 발행자를 확인하지 못할 수 있습니다.
배포 파일의 SHA256은 릴리스의 `SHA256SUMS.txt`로 확인할 수 있습니다.

> 최초 릴리스가 게시되기 전에는 위 다운로드 링크에 파일이 없습니다.
> 개발 중 생성한 설치 파일과 ZIP은 이 저장소의 `dist/`에 있습니다.

## Phase 1: 다운로드 사이트 운영

Railway 서비스의 `YDOWN_MODE`를 `download-site`로 설정하면 `download_site.py`를 실행합니다.
서비스의 기본 Docker 시작 명령(`/app/entrypoint.sh`)을 사용하며, Healthcheck Path는 `/health`입니다.
`ydown.yebom.org`는 이 서비스에 연결되어 있습니다. 다운로드 사이트에는 로그인과 추출 API가
없으며, 기존 `YDOWN_PASSWORD` 설정을 사용하지 않습니다. 설치 파일은 GitHub Releases에서 제공합니다.
Windows 앱과 기본 Docker 실행은 계속 `app.py`의 추출 기능을 사용합니다.

릴리스 정보는 GitHub API와 공개 릴리스 리다이렉트 순으로 확인합니다. 모두 실패하면
실제 다운로드·체크섬을 검증한 `packaging/published-release.json`을 사용하고,
버전을 최신으로 단정하지 않고 "공개된 정식 버전"으로 표시합니다. 설치 파일 버튼은
항상 GitHub의 최신 정식 릴리스를 가리킵니다. 정식 릴리스의 공개 파일을 검증한 후 이 기록을 갱신합니다.

사이트를 로컬에서 확인하려면:

```powershell
.\.venv\Scripts\python.exe -m uvicorn download_site:app --host 127.0.0.1 --port 18765
```

## Phase 2 검토: 상시 PC에서 설치 없이 웹으로 사용하기

Phase 2는 아직 구현하지 않았습니다. Phase 1을 유지하면서 온라인 추출 기능을 추가하는
설계와 모든 미구현 계획은 [plan.md](plan.md)에 모았습니다.

### 기존 추출 서버 실행 기능과 검증 기록

Railway에서 테스트한 YouTube 추출 기능은 검증 실패 상태입니다. 아래 내용은 서버 실행 방법이며,
다운로드 성공을 보장하는 운영 안내가 아닙니다. `/health` 성공과 화면 표시만으로 웹 사용
가능 여부를 판단하지 말고, 실제 배포 환경에서 추출과 결과 파일 저장까지 먼저 검증하세요.

한 서버에 배포하면 다른 PC나 휴대폰은 URL만 열면 됩니다. 서버가 다운로드와 변환을
실행하고 사용자가 결과를 자신의 기기에 저장합니다. 기존 앱이 이미 이 구조이므로
데스크톱 앱을 웹으로 다시 작성할 필요가 없습니다.

### Railway 배포

아래 절차는 추출 서버 실행용이며 Phase 1 다운로드 사이트와 구별됩니다.
Phase 1에서는 위의 `YDOWN_MODE=download-site` 설정을 사용하세요.

1. Railway에서 GitHub 저장소 `loginheaven-jpg/Ydown`의 `main`을 연결합니다.
   저장소 루트의 Dockerfile로 FFmpeg와 Node.js를 포함해 빌드합니다.
2. 서비스의 **Variables**에서 아래 세 변수를 설정합니다.

   | 변수 | 값 |
   | --- | --- |
   | `YDOWN_REQUIRE_PASSWORD` | `1` |
   | `YDOWN_PASSWORD` | 사용자가 정한 비밀번호 (빈 값으로 두지 않음) |
   | `YDOWN_MAX_CONCURRENT_JOBS` | 우선 `1`로 운영 |

3. 서비스의 Healthcheck Path를 `/health`로 설정하고 변경 사항을 배포합니다.
4. **Settings → Networking → Generate Domain**으로 HTTPS 주소를 발급합니다.
   앱은 Railway가 제공한 `PORT`에서 실행됩니다.
5. 해당 주소에서 사용자 이름 **ydown**과 지정한 비밀번호로 접속합니다.
   짧은 영상 한 개의 추출과 파일 다운로드까지 확인하세요.

`YDOWN_REQUIRE_PASSWORD=1`인데 `YDOWN_PASSWORD`가 없으면 앱이 시작되지 않습니다.
배포 로그에 `Set YDOWN_PASSWORD before exposing YDown to the internet.`가 나타나면
비밀번호 변수를 추가하고 다시 배포하세요. 비밀번호를 GitHub에 기록하지 마세요.

### Render 배포

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/loginheaven-jpg/Ydown)

저장소의 배포 변경이 `main`에 반영된 후 위 버튼으로 Render Blueprint를 생성합니다.
`YDOWN_PASSWORD`를 설정하고 발급받은 HTTPS 주소에 접속하세요.
브라우저 로그인 창의 사용자 이름은 **ydown**, 비밀번호는 지정한 값입니다.
이후 `main`의 CI가 통과하면 자동으로 배포합니다. 무료 플랜은 데모용 설정이며
휴면·자원 제한이 있으므로 운영 규모에 맞게 변경할 수 있습니다.

YouTube가 클라우드 서버 IP를 제한하면 웹 서버가 정상이어도 추출은 실패할 수 있습니다.
실제 호스팅 환경에서 영상 추출을 확인해야 하며, 그 경우 Windows 앱을 사용하면
각 PC의 네트워크에서 처리할 수 있습니다. 앱은 제3자 프록시 계정을 자동으로 생성하지 않습니다.
운영자가 준비한 프록시나 쿠키 파일은 아래 환경 변수로 지정할 수 있습니다.

**2026-10-12 Railway 검증 결과:** 앱 기동, 로그인과 진행 상황 연결은 정상이나,
YouTube가 서버 연결에 추가 인증을 요구해 영상 추출이 실패했습니다. 안정 버전과
최신 개발 버전으로 같은 응답을 확인했습니다. 같은 영상은 로컬 PC에서 MP3 추출에
성공했습니다. 웹 추출이 막히면 화면에 표시된 Windows 앱 다운로드 경로를 이용하세요.

### Docker로 실행하기

Docker가 설치된 서버/PC에서:

```powershell
docker compose up -d --build
```

`http://127.0.0.1:8000`에 접속합니다. 업데이트는 최신 소스를 받고 같은 명령을 실행합니다.
Compose는 기본적으로 해당 PC에서만 접속할 수 있도록 구성되어 있습니다.
외부 공개 시 비밀번호와 HTTPS를 설정하고 역방향 프록시에서 WebSocket을 지원해야 합니다.
컨테이너는 일반 사용자로 실행되며 FFmpeg와 Node.js가 포함됩니다.
작업 상태를 메모리에 보관하므로 **단일 worker / 단일 인스턴스**로 운영하세요.

## 개발 환경

Python 3.12를 사용합니다. Windows에서는 다음 순서로 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/fetch-runtime.py
.\.venv\Scripts\python.exe launch.py
```

`fetch-runtime.py`는 고정된 FFmpeg와 Node.js를 체크섬 확인 후 `runtime/`에 준비합니다.
시스템 PATH는 변경하지 않습니다. Linux/macOS 개발자는 FFmpeg/ffprobe와 Node.js 22 이상을
설치하고 `python app.py`를 실행하면 됩니다.

```powershell
# GUI 없이 로컬 서버만 실행
.\.venv\Scripts\python.exe launch.py --serve --port 8000
# 검사
.\.venv\Scripts\python.exe -m pytest -q
# Windows 설치 파일과 ZIP 생성 (Inno Setup 6 필요)
powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1
# Inno Setup 없이 ZIP만 생성
powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1 -SkipInstaller
```

빌드는 테스트 → 런타임 확인 → PyInstaller 패키징 → 독립 실행 검사 → ZIP/설치 파일 →
SHA256 생성 순으로 진행됩니다. 독립 실행 검사는 별도 작업 폴더와 제한된 PATH에서
서버, HTML, FFmpeg/Node.js 실행과 MP3/M4A/Opus 실제 변환을 검사합니다.
버전은 `version.py` 한 곳에서 관리합니다.

## 릴리스 생성과 다운로드 자동화

`.github/workflows/ci.yml`은 Windows/Linux 테스트와 실제 컨테이너 기동을 검사합니다.
`.github/workflows/release.yml`은 Windows 설치 파일과 ZIP을 빌드하고 검사합니다.

- GitHub Actions에서 **Build Windows release → Run workflow**:
  게시 없이 빌드한 파일을 Actions artifact로 다운로드합니다.
- 정식 배포: `version.py`의 버전을 올리고 변경을 반영한 후 같은 이름의 태그를 push합니다.
  예를 들어 버전이 `0.2.0`이면:

```powershell
git tag v0.2.0
git push origin v0.2.0
```

태그와 버전이 일치하고 검사에 통과하면 GitHub Release에 다음 파일을 게시합니다.

- `YDown-Setup-x64.exe` — 처음 설치와 업그레이드에 동일한 파일 이름 사용
- `YDown-0.2.0-windows-x64.zip` — 설치하지 않고 실행하는 버전
- `SHA256SUMS.txt` — 배포 파일 체크섬

모든 버전의 다운로드 진입점은 `/releases/latest`로 동일합니다.
다운로드 엔진 업데이트가 필요하면 `requirements.txt`의 yt-dlp 버전을 변경하고 새 릴리스를 생성합니다.
FFmpeg/Node.js 빌드 입력은 `packaging/runtime-manifest.json`에서 URL과 SHA256을 함께 갱신합니다.
FFmpeg 원본 아카이브는 업스트림의 보관 기간 만료에 대비해 별도의 빌드 입력 릴리스에도
보관하며, 원본과 같은 SHA256을 검증합니다. 빌드 입력 릴리스는 앱의 최신 정식 릴리스에서 제외됩니다.

## 서버 설정

| 환경 변수 | 기본값 / 용도 |
| --- | --- |
| `PORT` | `8000`, 컨테이너 또는 `python app.py` 포트 |
| `YDOWN_MODE` | 컨테이너 기본 `extractor`; `download-site`이면 공개 다운로드 사이트만 실행 |
| `YDOWN_HOST` | `127.0.0.1`, `python app.py` 접속 주소 |
| `YDOWN_DATA_DIR` | 소스 실행: 저장소 폴더, Windows 패키지: `%LOCALAPPDATA%\YDown`, 컨테이너: `/data` |
| `YDOWN_PASSWORD` | 공유 웹 서버의 비밀번호, 사용자 이름 `ydown` |
| `YDOWN_REQUIRE_PASSWORD` | `1`이면 비밀번호 없이 서버를 시작하지 않음 (Render 기본 적용) |
| `YDOWN_FILE_TTL_SECONDS` | `3600`, 작업 완료 후 임시 파일 보관 시간 |
| `YDOWN_MAX_CONCURRENT_JOBS` | `2`, 동시 작업 수 (Render 데모는 `1`) |
| `YDOWN_MAX_DURATION_SECONDS` | `3600`, 개별 영상 길이 제한; 실시간 방송 제외 |
| `YDOWN_MAX_FILESIZE_MB` | `250`, 원본 다운로드 크기 제한 |
| `YDOWN_MAX_VIDEO_FILESIZE_MB` | `2048`, MP4 영상·음성 트랙 합계와 완료 파일 크기 제한 (MiB) |
| `YDOWN_PROXY` | 운영자가 지정한 yt-dlp 프록시 주소, 기존 `WARP_PROXY`도 읽음 |
| `YDOWN_COOKIE_FILE` | 운영자가 지정한 Netscape 형식 쿠키 파일 경로 |
| `YOUTUBE_COOKIES` | 컨테이너 시작 시 권한을 제한한 쿠키 파일로 기록 |

`/health`는 서버와 필수 실행 파일 상태를 반환합니다. 파일은 추측하기 어려운 작업별
주소로 제공하고 비밀번호 설정 시 파일·API·WebSocket에도 인증을 적용합니다.
쿠키, 비밀번호, 프록시 인증 정보는 Git에 넣지 마세요.

## 구성

| 경로 | 역할 |
| --- | --- |
| `app.py` | 웹 UI, 진행 상황 WebSocket, 오디오 추출, 파일 제공, 정리, 업데이트 확인 |
| `templates/index.html` | 실제 사용하는 브라우저 화면 |
| `download_site.py`, `templates/download.html` | Phase 1 공개 다운로드·업데이트 안내 사이트 |
| `launch.py` | Windows 실행 창과 브라우저 자동 열기, headless 실행 |
| `settings.py`, `version.py` | 소스/패키지별 경로와 버전 |
| `scripts/`, `packaging/` | 런타임 준비, 설치 파일 생성, 독립 실행 검사 |
| `Dockerfile`, `render.yaml`, `compose.yaml` | 웹 서버 배포 |
| `tests/`, `.github/workflows/` | 검사와 릴리스 자동화 |

기존 중복 루트 `index.html`은 제거하고 실제 FastAPI 템플릿만 유지합니다.
