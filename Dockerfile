FROM python:3.11-slim

# OS 레벨 필수 패키지 설치 (FFmpeg, NodeJS, wget/curl)
RUN apt-get update && \
    apt-get install -y ffmpeg nodejs wget curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Cloudflare WARP 우회용 도구 설치
# wgcf: WARP 계정 등록 및 WireGuard 설정 생성
# wireproxy: 유저스페이스 WireGuard → SOCKS5 프록시 (커널 권한 불필요)
RUN wget -q -O /usr/local/bin/wgcf \
      "https://github.com/ViRb3/wgcf/releases/download/v2.2.30/wgcf_2.2.30_linux_amd64" && \
    chmod +x /usr/local/bin/wgcf && \
    wget -q -O /tmp/wireproxy.tar.gz \
      "https://github.com/pufferffish/wireproxy/releases/download/v1.0.9/wireproxy_linux_amd64.tar.gz" && \
    tar -xzf /tmp/wireproxy.tar.gz -C /usr/local/bin/ && \
    chmod +x /usr/local/bin/wireproxy && \
    rm -f /tmp/wireproxy.tar.gz

# 작업 폴더 지정
WORKDIR /app

# 파이썬 의존성 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -U -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 엔트리포인트 스크립트 실행 권한 부여
RUN chmod +x /app/entrypoint.sh

# 서버 구동 포트
EXPOSE 8000

# 엔트리포인트: WARP 프록시 → Python 앱 순차 기동
CMD ["/app/entrypoint.sh"]
