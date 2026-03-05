#!/bin/bash
# =============================================================================
# YDown 엔트리포인트: Cloudflare WARP 프록시 → Python 앱 순차 기동
# =============================================================================
# YouTube는 데이터센터 IP를 전면 차단한다.
# Cloudflare WARP를 유저스페이스 WireGuard로 연결하고,
# SOCKS5 프록시(127.0.0.1:40000)를 통해 yt-dlp 트래픽을 우회시킨다.
# =============================================================================

WARP_DIR="/app/warp-data"
PROXY_PORT=40000
WARP_OK=false

echo "[YDown] === Cloudflare WARP 프록시 초기화 시작 ==="

setup_warp() {
    mkdir -p "$WARP_DIR"
    cd "$WARP_DIR"

    # ── 1단계: WARP 계정 등록 (최초 1회, 이후 재사용) ──
    if [ ! -f "wgcf-account.toml" ]; then
        echo "[YDown] WARP 계정 등록 중..."
        if ! wgcf register --accept-tos; then
            echo "[YDown] ⚠️ WARP 계정 등록 실패 (이 지역이 차단되었을 수 있음)"
            return 1
        fi
        echo "[YDown] WARP 계정 등록 완료."
    else
        echo "[YDown] 기존 WARP 계정 재사용."
    fi

    # ── 2단계: WireGuard 프로필 생성 ──
    echo "[YDown] WireGuard 프로필 생성 중..."
    if ! wgcf generate; then
        echo "[YDown] ⚠️ WireGuard 프로필 생성 실패"
        return 1
    fi

    # ── 3단계: wireproxy 설정 파일 생성 ──
    echo "[YDown] wireproxy 설정 파일 생성 중..."

    # wgcf-profile.conf에서 DNS 행을 제거한 뒤 Socks5 섹션 추가
    grep -v '^DNS = ' wgcf-profile.conf > wireproxy.conf
    cat >> wireproxy.conf << WPEOF

[Socks5]
BindAddress = 127.0.0.1:${PROXY_PORT}
WPEOF

    echo "[YDown] wireproxy 설정 완료. 프록시 포트: ${PROXY_PORT}"

    # ── 4단계: wireproxy 백그라운드 기동 ──
    echo "[YDown] wireproxy 시작 중..."
    wireproxy -c wireproxy.conf &
    local WP_PID=$!

    # 프록시 준비 대기 (최대 20초)
    echo "[YDown] WARP SOCKS5 프록시 준비 대기 중..."
    for i in $(seq 1 20); do
        if curl -s --connect-timeout 3 -x "socks5h://127.0.0.1:${PROXY_PORT}" \
           "https://www.cloudflare.com/cdn-cgi/trace" 2>/dev/null | grep -q "warp=on"; then
            echo "[YDown] ✅ WARP 프록시 활성화 확인 (warp=on)"
            WARP_OK=true
            return 0
        fi
        # wireproxy 프로세스가 죽었으면 중단
        if ! kill -0 $WP_PID 2>/dev/null; then
            echo "[YDown] ⚠️ wireproxy 프로세스가 종료됨"
            return 1
        fi
        sleep 1
    done

    echo "[YDown] ⚠️ WARP 프록시 활성화 확인 실패 (20초 타임아웃)"
    return 1
}

# WARP 설정 시도 (실패해도 앱은 기동한다)
if setup_warp; then
    echo "[YDown] WARP 프록시가 정상 작동 중입니다."
else
    echo "[YDown] ⚠️ WARP 프록시를 사용할 수 없습니다."
    echo "[YDown]    데이터센터 IP에서는 YouTube 다운로드가 차단될 수 있습니다."
    echo "[YDown]    로컬(가정용 IP)에서는 정상 작동합니다."
fi

# ── 5단계: Python 앱 기동 ──
echo "[YDown] === YDown 서버 시작 ==="
cd /app

# WARP 프록시가 성공한 경우에만 환경변수 설정
if [ "$WARP_OK" = true ]; then
    export WARP_PROXY="socks5://127.0.0.1:${PROXY_PORT}"
    echo "[YDown] WARP_PROXY=${WARP_PROXY}"
fi

# 환경변수로 주입된 YouTube 쿠키를 파일로 기록
if [ -n "$YOUTUBE_COOKIES" ]; then
    echo "$YOUTUBE_COOKIES" > /app/cookies.txt
    echo "[YDown] cookies.txt 생성 완료 ($(wc -c < /app/cookies.txt) bytes)"
else
    echo "[YDown] YOUTUBE_COOKIES 환경변수 없음 - 쿠키 없이 실행"
fi

exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"
