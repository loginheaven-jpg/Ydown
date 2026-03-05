FROM python:3.11-slim

# OS 레벨 필수 패키지 설치 (FFmpeg 및 유튜브 JS엔진 해석용 NodeJS 포함)
RUN apt-get update && \
    apt-get install -y ffmpeg nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 작업 폴더 지정
WORKDIR /app

# 파이썬 의존성 패키지 설치 (최신 버전 강제 업데이트 적용)
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -U -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 다운로드된 파일을 보존할 수 있도록 볼륨 지정 추천 (호스팅 환경에 따라 다름)
# VOLUME ["/app/downloads"]

# Uvicorn 실행을 위한 포트 개방
EXPOSE 8000

# 서버 실행 (Render.com에서는 환경변수 PORT를 무조건 수신해야 배포 타임아웃이 발생하지 않음)
CMD sh -c "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"
