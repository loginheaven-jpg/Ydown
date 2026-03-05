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

# 서버 구동 포트명시
EXPOSE 8000

# 서버 실행 (Python을 통해 직접 실행하면 app.py 내부에서 클라우드 포트를 동적으로 인식함)
CMD ["python", "app.py"]
