# 1. Python 3.11 slim 이미지 사용
FROM python:3.11-slim

# 2. 환경 변수 (시간대, Python 최적화)
ENV TZ=Asia/Seoul \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 3. 타임존 설정
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 4. 작업 디렉토리
WORKDIR /app

# 5. requirements.txt 먼저 복사 (캐시 최적화)
COPY requirements.txt .

# 6. pip 업그레이드 & 패키지 설치
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# 7. 소스 코드 복사
COPY . /app

# 8. FastAPI 기본 포트
ENV PYTHONPATH=/app
EXPOSE 8000

# 9. 실행 명령어 (uvicorn으로 FastAPI 실행)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
